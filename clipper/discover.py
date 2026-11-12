"""Find candidate source videos with the YouTube Data API v3.

search.list (own quota bucket since 2026-06-01) finds candidates filtered to Creative Commons;
videos.list (1 unit) re-verifies license, duration and stats before anything is stored.
"""
from __future__ import annotations

import os
import re
from datetime import datetime, timedelta, timezone

from . import db, rights
from .config import load_creators, niche as get_niche


def _iso_duration_s(d: str) -> float:
    m = re.fullmatch(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", d or "")
    if not m:
        return 0.0
    days, h, mi, s = (int(x or 0) for x in m.groups())
    return days * 86400 + h * 3600 + mi * 60 + s


def youtube_client(api_key: str | None = None):
    from googleapiclient.discovery import build

    key = api_key or os.environ.get("YOUTUBE_API_KEY")
    if not key:
        raise SystemExit("YOUTUBE_API_KEY is not set (see .env.example).")
    return build("youtube", "v3", developerKey=key, cache_discovery=False)


def search_ids(yt, query: str, cfg: dict) -> list[str]:
    disc = cfg["discovery"]
    after = (datetime.now(timezone.utc) - timedelta(days=disc["published_within_days"])).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    params = dict(
        part="id",
        q=query,
        type="video",
        maxResults=min(50, disc["max_results_per_query"]),
        order="viewCount",
        publishedAfter=after,
        videoEmbeddable="true",
        safeSearch="moderate",
    )
    if disc.get("license") == "creativeCommon":
        params["videoLicense"] = "creativeCommon"
    resp = yt.search().list(**params).execute()
    return [it["id"]["videoId"] for it in resp.get("items", []) if it.get("id", {}).get("videoId")]


def fetch_details(yt, ids: list[str]) -> list[dict]:
    out = []
    for i in range(0, len(ids), 50):
        resp = yt.videos().list(part="snippet,status,contentDetails,statistics", id=",".join(ids[i : i + 50])).execute()
        out.extend(resp.get("items", []))
    return out


def evaluate(video: dict, cfg: dict) -> tuple[bool, str]:
    disc = cfg["discovery"]
    ok, basis = rights.check(video, cfg)
    if not ok:
        return False, basis
    dur = _iso_duration_s(video.get("contentDetails", {}).get("duration", ""))
    if dur < disc["min_duration_s"] or dur > disc["max_duration_s"]:
        return False, f"duration {dur:.0f}s outside range"
    views = int(video.get("statistics", {}).get("viewCount", 0))
    if views < disc["min_views"] and not basis.startswith("campaign:"):
        return False, f"only {views} views"
    return True, basis


def creator_upload_ids(yt, niche_name: str, per_channel: int = 25) -> list[str]:
    """Recent uploads (incl. stream VODs) from every eligible allowlisted creator for this niche.

    Uses channels.list + playlistItems.list (1 unit each) instead of search.list.
    """
    creators, _ = load_creators()
    channel_ids = []
    for c in creators.values():
        if rights.creator_eligible(c, niche_name)[0]:
            channel_ids += rights.creator_channel_ids(c)
    ids: list[str] = []
    for i in range(0, len(channel_ids), 50):
        resp = yt.channels().list(part="contentDetails", id=",".join(channel_ids[i: i + 50])).execute()
        for ch in resp.get("items", []):
            uploads = ch["contentDetails"]["relatedPlaylists"]["uploads"]
            items = yt.playlistItems().list(part="contentDetails", playlistId=uploads,
                                            maxResults=min(50, per_channel)).execute().get("items", [])
            ids += [it["contentDetails"]["videoId"] for it in items]
    return ids


def run(niche_name: str, conn=None, yt=None, queries: list[str] | None = None) -> dict:
    cfg = get_niche(niche_name)
    cfg["_name"] = niche_name
    conn = conn or db.connect()
    yt = yt or youtube_client()
    stats = {"found": 0, "new_ok": 0, "rejected": 0}
    ids: list[str] = []
    for q in queries if queries is not None else cfg["queries"]:
        ids.extend(search_ids(yt, q, cfg))
    ids.extend(creator_upload_ids(yt, niche_name))
    ids = list(dict.fromkeys(ids))
    stats["found"] = len(ids)
    for v in fetch_details(yt, ids):
        ok, basis = evaluate(v, cfg)
        sn = v["snippet"]
        creator_key, _ = rights.find_creator(sn.get("channelId", ""))
        inserted = db.upsert_source(
            conn,
            id=f"yt:{v['id']}",
            niche=niche_name,
            kind="youtube",
            url=f"https://www.youtube.com/watch?v={v['id']}",
            title=sn.get("title"),
            channel_id=sn.get("channelId"),
            channel_title=sn.get("channelTitle"),
            license=v.get("status", {}).get("license"),
            rights_basis=basis if ok else None,
            duration_s=_iso_duration_s(v.get("contentDetails", {}).get("duration", "")),
            views=int(v.get("statistics", {}).get("viewCount", 0)),
            published_at=sn.get("publishedAt"),
            status="discovered" if ok else "rejected",
            reject_reason=None if ok else basis,
            meta={"creator": creator_key} if creator_key else None,
        )
        if inserted:
            stats["new_ok" if ok else "rejected"] += 1
    return stats
