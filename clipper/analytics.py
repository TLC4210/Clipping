"""Daily analytics check of our own YouTube channels.

For every niche with a YouTube account: channel totals, the last 50 uploads (including ones posted by
hand), views/likes/comments and the change since the previous check. Each run stores a snapshot in the
DB and writes a readable report to data/reports/analytics-YYYY-MM-DD.md.

Read-only: uses the youtube.readonly scope already granted to each channel's token. Audience
geography (the Reach campaigns' 50% US/CA/UK/AU/NZ rule) needs the YouTube Analytics scope, which the
tokens don't have; check that in YouTube Studio.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from . import db
from .config import data_dir, load_accounts

SNAPSHOT_SQL = """
CREATE TABLE IF NOT EXISTS video_stats (
    video_id TEXT NOT NULL, niche TEXT NOT NULL, taken_at TEXT NOT NULL,
    views INTEGER, likes INTEGER, comments INTEGER, privacy TEXT, title TEXT, published_at TEXT
);
CREATE TABLE IF NOT EXISTS channel_stats (
    niche TEXT NOT NULL, channel_id TEXT, taken_at TEXT NOT NULL,
    subscribers INTEGER, views INTEGER, videos INTEGER
);
"""


def _client(acct: dict):
    from googleapiclient.discovery import build

    from .publish_youtube import _creds

    return build("youtube", "v3", credentials=_creds(acct), cache_discovery=False)


def fetch_channel(yt) -> tuple[dict, list[dict]]:
    """(channel, videos) for the token's own channel; videos newest first, at most 50."""
    ch = yt.channels().list(part="snippet,statistics,contentDetails", mine=True).execute()["items"][0]
    uploads = ch["contentDetails"]["relatedPlaylists"]["uploads"]
    items = yt.playlistItems().list(part="contentDetails", playlistId=uploads, maxResults=50).execute().get("items", [])
    ids = [i["contentDetails"]["videoId"] for i in items]
    videos = []
    if ids:
        r = yt.videos().list(part="snippet,statistics,status,contentDetails", id=",".join(ids)).execute()
        videos = r.get("items", [])
    videos.sort(key=lambda v: v["snippet"]["publishedAt"], reverse=True)
    return ch, videos


def _prev(conn, video_id: str) -> dict | None:
    r = conn.execute("SELECT * FROM video_stats WHERE video_id=? ORDER BY taken_at DESC LIMIT 1", (video_id,)).fetchone()
    return dict(r) if r else None


def flags(v: dict) -> list[str]:
    st, cd = v.get("status", {}), v.get("contentDetails", {})
    out = []
    if st.get("uploadStatus") not in (None, "processed", "uploaded"):
        out.append(f"upload {st.get('uploadStatus')}: {st.get('rejectionReason') or st.get('failureReason') or ''}".strip())
    if st.get("privacyStatus") != "public":
        out.append(st.get("privacyStatus", "unknown"))
    blocked = (cd.get("regionRestriction") or {}).get("blocked") or []
    if blocked:
        out.append(f"blocked in {len(blocked)} countries" + (" incl. US" if "US" in blocked else ""))
    return out


def check(conn, niche_name: str, acct: dict, yt=None, today: str | None = None) -> dict:
    conn.executescript(SNAPSHOT_SQL)
    yt = yt or _client(acct)
    ch, videos = fetch_channel(yt)
    now = db.now()
    cs = ch["statistics"]
    prev_ch = conn.execute("SELECT * FROM channel_stats WHERE niche=? ORDER BY taken_at DESC LIMIT 1",
                           (niche_name,)).fetchone()
    ours = {r["remote_id"]: dict(r) for r in conn.execute(
        "SELECT p.remote_id, c.id AS clip_id, s.meta FROM posts p JOIN clips c ON c.id=p.clip_id "
        "JOIN sources s ON s.id=c.source_id WHERE p.platform='youtube'")}
    rows = []
    for v in videos:
        s, sn = v.get("statistics", {}), v["snippet"]
        views, likes, comments = (int(s.get(k, 0)) for k in ("viewCount", "likeCount", "commentCount"))
        p = _prev(conn, v["id"])
        age_h = (datetime.now(timezone.utc) - datetime.fromisoformat(sn["publishedAt"].replace("Z", "+00:00"))).total_seconds() / 3600
        rows.append({"id": v["id"], "title": sn["title"], "published": sn["publishedAt"][:16].replace("T", " "),
                     "age_h": round(age_h, 1), "views": views, "likes": likes, "comments": comments,
                     "views_change": views - p["views"] if p else None, "flags": flags(v),
                     "clip_id": (ours.get(v["id"]) or {}).get("clip_id")})
        conn.execute("INSERT INTO video_stats VALUES (?,?,?,?,?,?,?,?,?)",
                     (v["id"], niche_name, now, views, likes, comments, v.get("status", {}).get("privacyStatus"),
                      sn["title"], sn["publishedAt"]))
    subs, total, nvid = (int(cs.get(k, 0)) for k in ("subscriberCount", "viewCount", "videoCount"))
    conn.execute("INSERT INTO channel_stats VALUES (?,?,?,?,?,?)", (niche_name, ch["id"], now, subs, total, nvid))
    conn.commit()
    public = [r for r in rows if "private" not in r["flags"] and "unlisted" not in r["flags"]]
    return {
        "niche": niche_name, "channel": ch["snippet"]["title"], "subscribers": subs, "views": total, "videos": nvid,
        "subscribers_change": subs - prev_ch["subscribers"] if prev_ch else None,
        "views_change": total - prev_ch["views"] if prev_ch else None,
        "public_videos": len(public),
        "best_public": max(public, key=lambda r: r["views"])["title"] if public else None,
        "videos_list": rows,
    }


def _fmt_change(n) -> str:
    return "" if n is None else f" ({'+' if n >= 0 else ''}{n:,})"


def report_md(results: list[dict], day: str) -> str:
    out = [f"# Analytics check {day}", ""]
    for r in results:
        if "error" in r:
            out += [f"## {r['niche']}: could not check", "", f"{r['error']}", ""]
            continue
        out += [f"## {r['channel']} ({r['niche']})", "",
                f"- Subscribers: {r['subscribers']:,}{_fmt_change(r['subscribers_change'])}",
                f"- Channel views: {r['views']:,}{_fmt_change(r['views_change'])}",
                f"- Uploads checked: {len(r['videos_list'])} ({r['public_videos']} public)", ""]
        vids = r["videos_list"][:20]
        if vids:
            out += ["| Posted | Title | Views | Likes | Comments | Notes |", "|---|---|---:|---:|---:|---|"]
            for v in vids:
                out.append(f"| {v['published']} | {v['title'][:60].replace('|', '/')} | {v['views']:,}"
                           f"{_fmt_change(v['views_change'])} | {v['likes']:,} | {v['comments']:,} | "
                           f"{', '.join(v['flags'])} |")
            out.append("")
        warn = [v for v in r["videos_list"] if any("blocked" in f or "upload" in f for f in v["flags"])]
        if warn:
            out += ["**Needs a look:**"] + [f"- {v['title'][:60]}: {', '.join(v['flags'])}" for v in warn] + [""]
    return "\n".join(out)


def run(conn, niches: list[str] | None = None) -> dict:
    accts = load_accounts()
    results = []
    for niche_name, a in accts.items():
        if niches and niche_name not in niches:
            continue
        acct = (a or {}).get("youtube") or {}
        if not acct.get("enabled"):
            continue
        try:
            results.append(check(conn, niche_name, acct))
        except Exception as e:  # one channel's expired token shouldn't hide the others
            results.append({"niche": niche_name, "error": f"{type(e).__name__}: {e}"[:300]})
    day = date.today().isoformat()
    path = data_dir("reports") / f"analytics-{day}.md"
    path.write_text(report_md(results, day), encoding="utf-8")
    summary = [{k: r.get(k) for k in ("niche", "channel", "subscribers", "subscribers_change", "views",
                                      "views_change", "public_videos", "best_public", "error") if k in r}
               for r in results]
    return {"report": str(path), "channels": summary}
