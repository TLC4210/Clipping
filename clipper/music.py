"""Daily trending-music check: what to download for the bot's music bed.

Runs with the 3am research job and writes data/reports/music-YYYY-MM-DD.md. Uses the official YouTube
Data API only:

1. YouTube's US music chart: what's trending right now. These are commercial songs. The bot can't put
   them in a clip (no licence); they can only be added by hand in the YouTube/Instagram app when posting.
2. Song credits in the descriptions of the most-viewed recent Shorts for each niche (many creators list
   the song they used).
3. Claude turns that into a download list: YouTube Audio Library searches (genre + mood) per niche that
   match the feel of what's winning, and how many tracks to get, given what's already in the library.

Where downloaded tracks go (see edit.music_files):
  data/assets/music/youtube   YouTube Audio Library, standard licence (YouTube only)
  data/assets/music/anywhere  tracks licensed for every platform (also used on Instagram)
"""
from __future__ import annotations

import json
import os
import re
from collections import Counter
from datetime import date, datetime, timedelta, timezone

from . import edit
from .config import data_dir, load_niches

MODEL = "claude-opus-5-5"
SONG_LINE = re.compile(r"(?:\bsong\b|\bmusic\b|\baudio\b|\bsound\b|\btrack\b|\bbeat\b|♪|♫|🎵|🎶)", re.I)
SKIP_LINE = re.compile(r"(?:subscribe|copyright|fair use|business|contact|discord|instagram\.com|tiktok\.com)", re.I)
DEFAULT_QUERIES = {"gta": ["gta 5 shorts", "gta 6 edit"], "minecraft": ["minecraft shorts", "minecraft funny"],
                   "streams": ["lacy stream", "jason the ween"]}


def song_credits(description: str) -> list[str]:
    """Lines of a description that credit the music ("Song: ...", "🎵 ...")."""
    out = []
    for line in (description or "").splitlines():
        line = " ".join(line.split())
        if 6 <= len(line) <= 140 and SONG_LINE.search(line) and not SKIP_LINE.search(line):
            out.append(line)
    return out[:3]


def chart(yt, region: str = "US", n: int = 15) -> list[dict]:
    r = yt.videos().list(part="snippet,statistics", chart="mostPopular", videoCategoryId="10",
                         regionCode=region, maxResults=n).execute()
    return [{"title": v["snippet"]["title"], "channel": v["snippet"]["channelTitle"],
             "views": int(v["statistics"].get("viewCount", 0))} for v in r.get("items", [])]


def niche_shorts(yt, query: str, days: int = 14, n: int = 25) -> list[dict]:
    after = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    r = yt.search().list(part="id", q=query, type="video", videoDuration="short", order="viewCount",
                         publishedAfter=after, maxResults=n, relevanceLanguage="en").execute()
    ids = [i["id"]["videoId"] for i in r.get("items", [])]
    if not ids:
        return []
    vids = yt.videos().list(part="snippet,statistics", id=",".join(ids)).execute().get("items", [])
    return [{"id": v["id"], "title": v["snippet"]["title"], "views": int(v["statistics"].get("viewCount", 0)),
             "credits": song_credits(v["snippet"].get("description", ""))} for v in vids]


def library_counts() -> dict[str, int]:
    counts = {pool: len(list(data_dir("assets", "music", pool).rglob("*.*"))) for pool in edit.MUSIC_POOLS}
    for name in load_niches():
        counts[f"youtube/{name}"] = len(edit.music_files("youtube", name))
    return counts | {"sfx": len(edit.sfx_library())}


PLAN_SYSTEM = """You plan the music library for a short-form clip channel group (YouTube Shorts +
Instagram Reels; niches: GTA, Minecraft, livestream clips). The bot mixes a quiet music bed under each
clip's own audio, from tracks the owner downloads once. It can never use commercial songs; it can only
use YouTube Audio Library tracks (standard licence: YouTube only, goes in the "youtube" folder) or tracks
licensed for every platform ("anywhere" folder, used for Instagram too). Never suggest AI-generated music:
the clip campaigns ban AI content.

From what is trending and what winning Shorts in each niche use, write a short download list in Markdown:
- For each niche: 2-3 YouTube Audio Library searches as filters that exist there (Genre: e.g. Hip Hop &
  Rap, Dance & Electronic, Cinematic, Ambient, Rock, Pop; Mood: e.g. Bright, Dark, Dramatic, Funky, Happy,
  Calm, Angry, Inspirational) plus what to listen for (tempo, energy, no vocals), and how many tracks.
  Explain in one line which trending songs/credits that feel matches. Livestream clips mostly win on the
  streamer's own voice, so keep their bed minimal (lo-fi/no vocals) or say none is needed.
- Sound effects to look for in the Audio Library's sound-effects tab (names to save files as, e.g.
  vine_boom, whoosh, record_scratch, ding), only if the library has few.
- Commercial songs worth adding by hand in the app on a standout clip (from the chart/credits), clearly
  labelled as manual only.
Do not invent specific Audio Library track titles. Be brief: this is read on a phone."""


def plan(trending: list[dict], by_niche: dict[str, list[dict]], counts: dict) -> str | None:
    if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
        return None
    import anthropic

    facts = {"library_now": counts, "us_music_chart": trending[:15],
             "song_credits_in_top_niche_shorts": {k: [s for s in v if s["credits"]][:15] for k, v in by_niche.items()},
             "top_niche_short_titles": {k: [s["title"] for s in v[:10]] for k, v in by_niche.items()}}
    try:
        resp = anthropic.Anthropic().beta.messages.create(
            model=MODEL, max_tokens=8000, betas=["server-side-fallback-2026-07-01"], fallbacks="default",
            thinking={"type": "adaptive"}, output_config={"effort": "low"}, system=PLAN_SYSTEM,
            messages=[{"role": "user", "content": json.dumps(facts, ensure_ascii=False)}])
    except (anthropic.RateLimitError, anthropic.APIConnectionError, anthropic.APIStatusError):
        return None
    if resp.stop_reason == "refusal":
        return None
    return next((b.text for b in resp.content if b.type == "text"), None)


def report_md(day: str, counts: dict, trending: list[dict], by_niche: dict[str, list[dict]], advice: str | None) -> str:
    out = [f"# Music check {day}", "",
           f"Library now: {counts['youtube']} YouTube-only tracks, {counts['anywhere']} all-platform tracks, "
           f"{counts['sfx']} sound effects.", "",
           "## What to download", "", advice or "_(Claude unavailable today; use the lists below.)_", "",
           "## Trending on YouTube (US music chart)", "",
           "Commercial songs: the bot can't use these. Add one by hand in the app only when posting a standout clip.",
           ""]
    out += [f"{i}. {t['title']} ({t['channel']}, {t['views']:,} views)" for i, t in enumerate(trending, 1)]
    out += ["", "## Songs credited in top Shorts per niche", ""]
    for niche_name, shorts in by_niche.items():
        credits = Counter()
        for s in shorts:
            for c in s["credits"]:
                credits[c] += s["views"]
        out.append(f"**{niche_name}** ({len(shorts)} Shorts checked, {sum(1 for s in shorts if s['credits'])} credit a song)")
        out += [f"- {c} ({v:,} views)" for c, v in credits.most_common(8)] or ["- none credited"]
        out.append("")
    out += ["Where downloads go: `data/assets/music/youtube/<niche>` (YouTube Audio Library), "
            "`data/assets/music/anywhere/<niche>` (licensed for every platform), `data/assets/sfx/<name>.wav`."]
    return "\n".join(out) + "\n"


def run(yt=None) -> dict:
    from .discover import youtube_client

    yt = yt or youtube_client()
    trending = chart(yt)
    by_niche: dict[str, list[dict]] = {}
    for name, cfg in load_niches().items():
        shorts: dict[str, dict] = {}
        for q in cfg.get("music_queries") or DEFAULT_QUERIES.get(name, []):
            for s in niche_shorts(yt, q):
                shorts[s["id"]] = s
        by_niche[name] = sorted(shorts.values(), key=lambda s: -s["views"])
    counts = library_counts()
    advice = plan(trending, by_niche, counts)
    day = date.today().isoformat()
    path = data_dir("reports") / f"music-{day}.md"
    path.write_text(report_md(day, counts, trending, by_niche, advice), encoding="utf-8")
    return {"report": str(path), "library": counts, "chart_top": [t["title"] for t in trending[:3]],
            "credits_found": {k: sum(1 for s in v if s["credits"]) for k, v in by_niche.items()},
            "advice": bool(advice)}
