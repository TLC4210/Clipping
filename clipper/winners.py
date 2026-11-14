"""Learn from competitors: which moments of our allowlisted creators' videos already went viral as Shorts.

For each joined campaign creator:
1. Search YouTube for recent Shorts about them from OTHER channels, sorted by views.
2. Match each Short to one of the creator's own uploads already in our DB (title keywords).
3. Find the moment: compare the Short's words with the source's transcript and take the best
   matching window.
4. Save it to data/winners.json. The picker then gets those windows as extra candidates labelled
   with the competitor's views. Claude still decides the cut and writes its own hook and title, so we
   take the proven moment, not the competitor's edit or wording.

Competitor audio is only used to read what was said in the Short; nothing of theirs is kept or posted.
"""
from __future__ import annotations

import json
import re
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import media, rights
from .config import data_dir, load_creators

MIN_VIEWS = 100_000
TITLES_KEY = "_titles"  # in winners.json: every winning competitor title per creator, matched or not
STOP = set("""the a an and of to in on for with is it his he was what this that at my our we i you be by from
just got gets did does vs ft new so all out up how why who when after before into they them their its
your are not but have has had about over one two get let made make me him her she""".split())


def winners_path() -> Path:
    return data_dir() / "winners.json"


def load() -> dict:
    p = winners_path()
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def hints_for(source_id: str) -> list[dict]:
    return load().get(source_id, [])


def crew_names(eligible: dict) -> set[str]:
    """Names that prove a title is about our creators. 'CORE' alone is too generic (pet 'core moments')."""
    out = set()
    for k, c in eligible.items():
        out.add(c.get("name", k).split("(")[0].strip())
        out |= set((c.get("member_hashtags") or {}).keys())
    return {n for n in out if n and n.lower() != "core"}


def names_crew(title: str, crew: set[str]) -> bool:
    return any(re.search(rf"\b{re.escape(n)}\b", title, re.I) for n in crew)


def clean_title(title: str) -> str:
    """Drop hashtags and '| channel' tails; keep the words and emojis."""
    title = re.sub(r"#\w+", "", title.split(" | ")[0])
    return " ".join(title.split())


def top_titles(creator_key: str, k: int = 5) -> list[tuple[str, int]]:
    """The k most-viewed competitor Short titles saved for this creator: (title, views)."""
    """creator_key=None: across every creator."""
    data = load()
    seen: dict[str, int] = {t["title"]: t["views"] for key, ts in data.get(TITLES_KEY, {}).items()
                            if creator_key in (None, key) for t in ts}
    for sid, hints in data.items():
        if sid == TITLES_KEY:
            continue
        for h in hints:
            if creator_key in (None, h.get("creator")):
                seen[h["short_title"]] = max(seen.get(h["short_title"], 0), h["views"])
    return sorted(seen.items(), key=lambda t: -t[1])[:k]


def _toks(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9$]+", text.lower()) if w not in STOP and len(w) > 2}


def _words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9']+", text.lower())


def search_queries(key: str, c: dict) -> list[str]:
    name = c.get("name", key).split("(")[0].strip()
    tags = [t for t in c.get("caption_must_include", []) if t.startswith("#")]
    return list(dict.fromkeys([name] + tags))[:2]


def competitor_shorts(yt, key: str, c: dict, days: int = 30) -> list[dict]:
    from .discover import _iso_duration_s

    own = set(rights.creator_channel_ids(c))
    after = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    ids: list[str] = []
    for q in search_queries(key, c):
        r = yt.search().list(part="id", q=q, type="video", videoDuration="short", order="viewCount",
                             publishedAfter=after, maxResults=50, relevanceLanguage="en").execute()
        ids += [i["id"]["videoId"] for i in r.get("items", [])]
    ids = list(dict.fromkeys(ids))
    out = []
    for i in range(0, len(ids), 50):
        for v in yt.videos().list(part="snippet,statistics,contentDetails", id=",".join(ids[i:i + 50])).execute()["items"]:
            sn = v["snippet"]
            views = int(v["statistics"].get("viewCount", 0))
            if sn["channelId"] in own or views < MIN_VIEWS or _iso_duration_s(v["contentDetails"]["duration"]) > 180:
                continue
            out.append({"id": v["id"], "title": sn["title"], "channel": sn["channelTitle"], "views": views,
                        "published": sn["publishedAt"][:10]})
    return sorted(out, key=lambda r: -r["views"])


def match_source(short: dict, sources: list[dict], creator_names: set[str]) -> dict | None:
    """The creator upload whose title shares the most distinctive words with the Short's title."""
    tt = _toks(short["title"]) - creator_names
    best, best_n = None, 1
    for s in sources:
        n = len(tt & _toks(s["title"] or ""))
        if n > best_n:
            best, best_n = s, n
    return best


def locate(short_words: list[dict], source_words: list[dict], short_len: float) -> tuple[float, float, float] | None:
    """Best (start, end, score) window of source_words matching the Short's speech (word-trigram overlap)."""
    sw = [w for x in short_words for w in _words(x["text"])]
    if len(sw) < 6 or not source_words:
        return None
    grams = {tuple(sw[i:i + 3]) for i in range(len(sw) - 2)}
    flat: list[tuple[float, str]] = [(x["start"], w) for x in source_words for w in _words(x["text"])]
    hits = [flat[i][0] for i in range(len(flat) - 2) if (flat[i][1], flat[i + 1][1], flat[i + 2][1]) in grams]
    if not hits:
        return None
    win = max(short_len, 15.0)
    best_t, best_n = hits[0], 0
    for t in hits:  # densest cluster of matching trigrams
        n = sum(1 for h in hits if t <= h <= t + win)
        if n > best_n:
            best_t, best_n = t, n
    score = best_n / max(1, len(grams))
    if best_n < 3 or score < 0.15:
        return None
    return best_t - 1.0, best_t + win, round(score, 2)


def _yt_captions(url: str, out_dir: Path, stem: str) -> list[dict]:
    from yt_dlp import YoutubeDL

    opts = {"skip_download": True, "writeautomaticsub": True, "writesubtitles": True,
            "subtitleslangs": ["en.*", "en"], "subtitlesformat": "json3", "quiet": True, "no_warnings": True,
            "outtmpl": str(out_dir / f"{stem}.%(ext)s")}
    try:
        with YoutubeDL(opts) as ydl:
            ydl.extract_info(url, download=True)
    except Exception:
        return []
    subs = sorted(out_dir.glob(f"{stem}*.json3"))
    return media.load_json3_words(subs[0]) if subs else []


def _short_words(short_id: str, tmp: Path) -> list[dict]:
    """What is said in the competitor Short: its captions, else Whisper on its audio (deleted after)."""
    url = f"https://www.youtube.com/shorts/{short_id}"
    words = _yt_captions(url, tmp, f"short_{short_id}")
    if words:
        return words
    from yt_dlp import YoutubeDL

    try:
        with YoutubeDL({"format": "ba/b", "quiet": True, "no_warnings": True,
                        "outtmpl": str(tmp / f"short_{short_id}.%(ext)s")}) as ydl:
            ydl.extract_info(url, download=True)
    except Exception:
        return []
    files = [p for p in tmp.glob(f"short_{short_id}.*") if p.suffix not in (".json3", ".part")]
    if not files:
        return []
    dur = media.probe(files[0])["duration"]
    return media.transcribe_ranges(files[0], [(0, dur)])


def research(conn, niche_name: str, yt=None, per_creator: int = 15) -> dict:
    """Find winning moments for every joined creator in this niche and save them to data/winners.json."""
    from .discover import youtube_client

    yt = yt or youtube_client()
    creators, _ = load_creators()
    saved = load()
    report = {"shorts_checked": 0, "matched_source": 0, "located": 0, "by_creator": {}}
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        eligible = {k: c for k, c in creators.items() if rights.creator_eligible(c, niche_name)[0]}
        # Match against every joined creator's uploads: the crews appear in each other's videos
        # (e.g. a viral "Lacy" Short cut from a CORE channel video).
        chans = [ch for c in eligible.values() for ch in rights.creator_channel_ids(c)]
        sources = [dict(r) for r in conn.execute(
            f"SELECT * FROM sources WHERE niche=? AND status IN ('discovered','fetched','mined') "
            f"AND channel_id IN ({','.join('?' * len(chans))})", (niche_name, *chans))] if chans else []
        all_names = set().union(*(_toks(c.get("name", k)) | {k} for k, c in eligible.items())) if eligible else set()
        crew = crew_names(eligible)
        for key, c in eligible.items():
            names = all_names | {"stream", "streamer", "viral", "shorts", "ron", "marlon"}
            found = []
            shorts = competitor_shorts(yt, key, c)
            saved.setdefault(TITLES_KEY, {})[key] = [
                {"title": clean_title(s["title"]), "views": s["views"]} for s in shorts
                if names_crew(s["title"], crew) and len(clean_title(s["title"]).split()) >= 3][:20]
            for short in shorts[:per_creator]:
                report["shorts_checked"] += 1
                src = match_source(short, sources, names)
                if not src:
                    continue
                report["matched_source"] += 1
                spot = None
                if src["id"].startswith("yt:"):
                    src_words = (media.load_json3_words(src["captions_path"]) if src.get("captions_path")
                                 and Path(src["captions_path"]).exists() else [])
                    if not src_words:
                        src_words = _yt_captions(src["url"], tmp, f"src_{src['id'].split(':')[1]}")
                    sw = _short_words(short["id"], tmp)
                    spot = locate(sw, src_words, (sw[-1]["end"] - sw[0]["start"]) if sw else 30)
                hint = {"short_id": short["id"], "short_title": short["title"], "competitor": short["channel"],
                        "views": short["views"], "published": short["published"], "creator": key}
                if not spot and src["id"].startswith("tw:"):
                    spot = (0.0, float(src["duration_s"] or 0), 1.0)  # a Twitch clip IS the moment
                if spot:
                    hint.update(start=round(spot[0], 1), end=round(spot[1], 1), match=spot[2])
                    report["located"] += 1
                hints = [h for h in saved.get(src["id"], []) if h["short_id"] != short["id"]] + [hint]
                saved[src["id"]] = sorted(hints, key=lambda h: -h["views"])
                found.append({"views": short["views"], "short": short["title"][:60], "source": src["title"][:50],
                              "at": f"{hint['start']:.0f}-{hint['end']:.0f}s" if spot else "moment not found"})
            report["by_creator"][key] = found
    winners_path().write_text(json.dumps(saved, ensure_ascii=False, indent=1), encoding="utf-8")
    return report


def hint_candidates(source_id: str, duration: float, cfg: dict) -> list[dict]:
    """Located winning moments as picker candidates (sized to our clip length)."""
    lo, hi = cfg["clip_min_s"], cfg["clip_max_s"]
    out = []
    for h in hints_for(source_id):
        if "start" not in h:
            continue
        start = max(0.0, h["start"])
        end = min(duration, max(h["end"], start + lo), start + hi)
        if end - start >= lo:
            out.append({"start": round(start, 2), "end": round(end, 2), "peak": (start + end) / 2,
                        "score": 10.0, "proven": h})
    return out
