"""Get source media onto disk.

- YouTube sources: downloaded with yt-dlp ONLY if the rights gate passed (CC BY or permission).
  The license is re-checked right before download.
- Inbox: any file you drop into data/inbox/<niche>/ (your own gameplay, files creators sent you).
"""
from __future__ import annotations

import hashlib
import shutil
import time
from pathlib import Path

from . import db, rights
from .config import data_dir, niche as get_niche

VIDEO_EXT = {".mp4", ".mkv", ".mov", ".webm"}
AUDIO_EXT = {".m4a", ".opus", ".mp3", ".ogg"}
# Longer sources (stream VODs, often 5-10 GB in 1080p) are fetched as audio + captions only. The moments
# are picked from those, then only the candidate windows are downloaded as video (fetch_sections).
LONG_SOURCE_S = 30 * 60
AUDIO_FORMAT = "wa[ext=m4a]/wa/ba"
SECTION_PAD_S = 10.0  # video kept on each side of a candidate (the picker may move edges by 6 s)


def is_long(source_row) -> bool:
    return float(source_row["duration_s"] or 0) > LONG_SOURCE_S


def _ydl_opts(out_dir: Path, audio_only: bool = False) -> dict:
    return {
        "format": AUDIO_FORMAT if audio_only else "bv*[height<=1080][ext=mp4]+ba[ext=m4a]/b[height<=1080]/b",
        "merge_output_format": "mp4",
        "outtmpl": str(out_dir / "%(id)s.%(ext)s"),
        "writeautomaticsub": True,
        "writesubtitles": True,
        "subtitleslangs": ["en.*", "en"],
        "subtitlesformat": "json3",
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "retries": 3,
    }


def fetch_youtube(conn, source_row, yt=None) -> Path:
    """Download one approved YouTube source. Re-verifies rights first."""
    from yt_dlp import YoutubeDL

    if source_row["status"] != "discovered" or not source_row["rights_basis"]:
        raise ValueError(f"{source_row['id']} has not passed the rights gate")
    video_id = source_row["id"].split(":", 1)[1]
    if yt is not None:  # re-check license right before download (licenses can change)
        cfg = get_niche(source_row["niche"])
        cfg["_name"] = source_row["niche"]
        items = yt.videos().list(part="snippet,status", id=video_id).execute().get("items", [])
        ok, basis = rights.check(items[0], cfg) if items else (False, "video gone")
        if ok and not basis.startswith("campaign:"):
            from .discover import language_ok

            ok, why = language_ok(items[0], cfg.get("discovery", {}).get("languages") or [])
            basis = basis if ok else why
        if not ok:
            db.update(conn, "sources", source_row["id"], status="rejected", reject_reason=basis)
            raise PermissionError(basis)

    out_dir = data_dir("sources", source_row["niche"])
    audio_only = is_long(source_row)
    try:
        with YoutubeDL(_ydl_opts(out_dir, audio_only)) as ydl:
            ydl.extract_info(source_row["url"], download=True)
    except Exception as e:
        if "subtitle" not in str(e).lower():
            raise
        # Captions are optional (moment picking falls back to audio). YouTube often rate-limits
        # the subtitle request (HTTP 429) on its own, so retry the video without subtitles.
        opts = _ydl_opts(out_dir, audio_only)
        opts.update(writesubtitles=False, writeautomaticsub=False)
        with YoutubeDL(opts) as ydl:
            ydl.extract_info(source_row["url"], download=True)
        # Captions make the moment picks much better, so try them once more on their own.
        time.sleep(20)
        try:
            with YoutubeDL({**_ydl_opts(out_dir, audio_only), "skip_download": True}) as ydl:
                ydl.extract_info(source_row["url"], download=True)
        except Exception:
            pass
    path = out_dir / f"{video_id}.mp4"
    if not path.exists():
        cands = [p for p in out_dir.glob(f"{video_id}.*") if p.suffix in VIDEO_EXT | AUDIO_EXT]
        if not cands:
            raise FileNotFoundError(f"download produced no video for {video_id}")
        path = cands[0]
    subs = sorted(out_dir.glob(f"{video_id}*.json3"))
    db.update(
        conn,
        "sources",
        source_row["id"],
        local_path=str(path),
        captions_path=str(subs[0]) if subs else None,
        status="fetched",
    )
    return path


def fetch_sections(src: dict, ranges: list[tuple[float, float]]) -> list[dict]:
    """Download only these time ranges of a long YouTube source as 1080p video.

    Returns segments [{start, end, path}] in source time; media.source_at() maps a source time to the
    segment file. Cuts are re-encoded at the exact times (force_keyframes_at_cuts), so segment time 0
    is exactly `start`.
    """
    from yt_dlp import YoutubeDL
    from yt_dlp.utils import download_range_func

    from .media import _merge_ranges, probe

    out_dir = Path(src["local_path"]).parent
    vid = src["id"].split(":", 1)[1]
    ranges = _merge_ranges([(round(a), round(b)) for a, b in ranges])
    opts = {**_ydl_opts(out_dir), "writesubtitles": False, "writeautomaticsub": False,
            "outtmpl": str(out_dir / f"{vid}.sec%(section_start)d.%(ext)s"),
            "download_ranges": download_range_func(None, ranges), "force_keyframes_at_cuts": True}
    with YoutubeDL(opts) as ydl:
        ydl.extract_info(src["url"], download=True)
    segs = []
    for a, _ in ranges:
        p = out_dir / f"{vid}.sec{int(a)}.mp4"
        if p.exists():
            segs.append({"start": float(a), "end": float(a) + probe(p)["duration"], "path": str(p)})
    return segs


def ingest_inbox(conn, niche_name: str) -> list[str]:
    """Register files from data/inbox/<niche>/ as owned sources."""
    inbox = data_dir("inbox", niche_name)
    added = []
    for f in sorted(inbox.iterdir()):
        if f.suffix.lower() not in VIDEO_EXT:
            continue
        h = hashlib.sha1()
        with open(f, "rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                h.update(chunk)
        sid = f"file:{h.hexdigest()[:16]}"
        dest = data_dir("sources", niche_name) / f"{sid.split(':')[1]}{f.suffix.lower()}"
        if not dest.exists():
            shutil.move(str(f), dest)
        else:
            f.unlink()
        from .media import probe

        info = probe(dest)
        if db.upsert_source(
            conn,
            id=sid,
            niche=niche_name,
            kind="inbox",
            title=f.stem,
            license="owned",
            rights_basis="inbox: owner-supplied file",
            duration_s=info["duration"],
            local_path=str(dest),
            status="fetched",
        ):
            added.append(sid)
    return added
