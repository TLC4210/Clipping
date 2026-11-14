"""Twitch sources: the most-viewed Twitch clips of each joined campaign creator.

Most viral Shorts of streamers are cut from live streams, which never reach YouTube. Twitch clips are
the moments viewers already chose to clip, ranked by views, so they are a proven shortlist.
Only creators in rights/creators.yaml with a `twitch:` handle and a joined, in-date campaign whose
rules allow stream footage are used (all four streams campaigns say "any video/stream/clip").

No Twitch account or API key: yt-dlp reads the public clips page.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from . import db, rights
from .config import data_dir, load_creators

MIN_CLIP_VIEWS = 500


def handles(c: dict) -> list[str]:
    tw = c.get("twitch") or []
    return [tw] if isinstance(tw, str) else list(tw)


def top_clips(handle: str, period: str = "7d", limit: int = 20) -> list[dict]:
    from yt_dlp import YoutubeDL

    url = f"https://www.twitch.tv/{handle}/clips?filter=clips&range={period}"
    with YoutubeDL({"quiet": True, "no_warnings": True, "extract_flat": True, "playlistend": limit}) as ydl:
        info = ydl.extract_info(url, download=False)
    return [e for e in (info.get("entries") or []) if e]


def discover(conn, niche_name: str, period: str = "7d", per_creator: int = 20) -> dict:
    """Add the top Twitch clips of every eligible creator in this niche as sources."""
    from .config import niche as get_niche

    cfg = get_niche(niche_name)
    lo, hi = cfg["clip_min_s"], cfg.get("discovery", {}).get("max_duration_s", 600)
    creators, _ = load_creators()
    stats = {"found": 0, "new_ok": 0, "skipped": 0}
    for key, c in creators.items():
        if not rights.creator_eligible(c, niche_name)[0]:
            continue
        yt_ids = rights.creator_channel_ids(c)
        for h in handles(c):
            try:
                clips = top_clips(h, period, per_creator)
            except Exception as e:  # one creator's page failing shouldn't stop the others
                print(f"twitch {h}: {e}")
                continue
            for e in clips:
                stats["found"] += 1
                views, dur = int(e.get("view_count") or 0), float(e.get("duration") or 0)
                published = (datetime.fromtimestamp(e["timestamp"], timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                             if e.get("timestamp") else None)
                ok, why = rights.in_source_window(c, published)
                if views < MIN_CLIP_VIEWS or not (lo + 3 <= dur <= hi) or not ok:
                    stats["skipped"] += 1
                    continue
                inserted = db.upsert_source(
                    conn, id=f"tw:{e['id']}", niche=niche_name, kind="twitch", url=e["url"],
                    title=e.get("title") or f"{c.get('name', key)} Twitch clip",
                    # The creator's YouTube channel id: lets winners matching and the avatar check work.
                    channel_id=yt_ids[0] if yt_ids else None, channel_title=c.get("name", key).split("(")[0].strip(),
                    license="twitch-clip", rights_basis=f"campaign:{key}", duration_s=dur, views=views,
                    published_at=published, status="discovered", meta={"creator": key, "twitch": h})
                if inserted:
                    stats["new_ok"] += 1
    return stats


def fetch(conn, source_row) -> Path:
    """Download one Twitch clip (mp4). Twitch clips have no captions; Whisper covers that when mining."""
    from yt_dlp import YoutubeDL

    clip_id = source_row["id"].split(":", 1)[1]
    out_dir = data_dir("sources", source_row["niche"])
    key = (json.loads(source_row["meta"] or "{}") or {}).get("creator")
    c = load_creators()[0].get(key or "", {})
    ok, why = rights.creator_eligible(c, source_row["niche"]) if c else (False, "creator no longer listed")
    if not ok:
        db.update(conn, "sources", source_row["id"], status="rejected", reject_reason=why)
        raise PermissionError(why)
    with YoutubeDL({"format": "best[ext=mp4]/best", "outtmpl": str(out_dir / f"tw_{clip_id}.%(ext)s"),
                    "quiet": True, "no_warnings": True, "noprogress": True, "retries": 3}) as ydl:
        ydl.extract_info(source_row["url"], download=True)
    files = [p for p in out_dir.glob(f"tw_{clip_id}.*") if p.suffix in (".mp4", ".mkv", ".webm", ".mov")]
    if not files:
        raise FileNotFoundError(f"download produced no video for {source_row['id']}")
    db.update(conn, "sources", source_row["id"], local_path=str(files[0]), status="fetched")
    return files[0]
