"""Find the best moments in a source.

1. Signals: per-second score from audio loudness peaks, scene-cut density and speech density.
2. Candidates: windows around score peaks, non-max suppressed.
3. Picker: Claude looks at frames + transcript + signals for each candidate, picks the best,
   tightens the cut, and writes hook / title / description. Falls back to a heuristic if no API key.
"""
from __future__ import annotations

import json
import os

import numpy as np

from . import edit, media

MODEL = "claude-opus-5-5"


# ---------------------------------------------------------------- signals ---
def per_second_scores(duration: float, energy_db: np.ndarray, cuts: list[float], words: list[dict],
                      hop_s: float = 0.5) -> np.ndarray:
    n = max(1, int(np.ceil(duration)))
    score = np.zeros(n)
    if energy_db.size:
        per_s = int(round(1 / hop_s))
        e = energy_db[: (len(energy_db) // per_s) * per_s].reshape(-1, per_s).max(axis=1)
        e = e[:n]
        z = (e - np.median(e)) / (np.std(e) + 1e-6)
        score[: len(z)] += np.clip(z, -2, 4)
    if cuts:
        c = np.zeros(n)
        for t in cuts:
            if 0 <= int(t) < n:
                c[int(t)] += 1
        score += 0.5 * np.convolve(c, np.ones(5) / 5, mode="same") * 5
    if words:
        w = np.zeros(n)
        for wd in words:
            if 0 <= int(wd["start"]) < n:
                w[int(wd["start"])] += 1
        score += 0.15 * np.clip(np.convolve(w, np.ones(5) / 5, mode="same"), 0, 5)
    return score


def candidate_windows(score: np.ndarray, cfg: dict, k: int) -> list[dict]:
    """Pick up to k non-overlapping windows centred (slightly early) on the strongest peaks."""
    lo, hi = cfg["clip_min_s"], cfg["clip_max_s"]
    target = (lo + hi) / 2
    n = len(score)
    if n < lo:
        return []
    gap = cfg.get("min_gap_between_clips_s", 2)
    smooth = np.convolve(score, np.ones(3) / 3, mode="same")
    order = np.argsort(-smooth)
    taken: list[tuple[float, float]] = []
    out = []
    for peak in order:
        start = max(0.0, peak - 0.35 * target)  # build up before the peak, payoff after
        end = min(float(n), start + target)
        start = max(0.0, end - target)
        if end - start < lo:
            continue
        if any(not (end + gap <= a or start >= b + gap) for a, b in taken):
            continue
        win_score = float(smooth[int(start): int(end)].mean() + 0.5 * smooth[peak])
        taken.append((start, end))
        out.append({"start": round(start, 2), "end": round(end, 2), "peak": float(peak), "score": win_score})
        if len(out) >= k:
            break
    return out


# ----------------------------------------------------------------- picker ---
SCHEMA = {
    "type": "object",
    "properties": {
        "picks": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "candidate": {"type": "integer"},
                    "start": {"type": "number"},
                    "end": {"type": "number"},
                    "hook": {"type": "string"},
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                    "reason": {"type": "string"},
                    "graphic_violence_first_7s": {"type": "boolean"},
                    "quality": {"type": "integer"},
                    "extra_pieces": {"type": "array", "items": {
                        "type": "object", "additionalProperties": False, "required": ["candidate", "start", "end"],
                        "properties": {"candidate": {"type": "integer"}, "start": {"type": "number"},
                                       "end": {"type": "number"}}}},
                    "zooms": {"type": "array", "items": {
                        "type": "object", "additionalProperties": False, "required": ["t", "dur"],
                        "properties": {"t": {"type": "number"}, "dur": {"type": "number"}}}},
                    "emojis": {"type": "array", "items": {
                        "type": "object", "additionalProperties": False, "required": ["t", "emoji"],
                        "properties": {"t": {"type": "number"}, "emoji": {"type": "string"}}}},
                    "sfx": {"type": "array", "items": {
                        "type": "object", "additionalProperties": False, "required": ["t", "name"],
                        "properties": {"t": {"type": "number"}, "name": {"type": "string"}}}},
                },
                "required": ["candidate", "start", "end", "hook", "title", "description", "reason",
                             "graphic_violence_first_7s", "quality", "extra_pieces", "zooms", "emojis", "sfx"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["picks"],
    "additionalProperties": False,
}

SYSTEM = """You are the editor for a short-form gaming clip channel (YouTube Shorts + Instagram Reels).
You get numbered candidate windows from one source video, each with frames from across the window (3, or 6 for campaign clips),
the transcript inside the window (may be empty for no-commentary gameplay) and signal stats.

Pick the windows that work as standalone vertical clips: a clear moment (funny fail, clutch play,
chaos, surprising reveal, satisfying build) that a scroller understands in 1-2 seconds without context.
A clip is not "the best moment"; it is a moment that survives without the video around it. Keep a pick
only if all three hold:
1. It opens on something already happening (motion or a complete line), not on a setup that needs the
   previous minute.
2. There is a turn: an attempt, then something that complicates or pays it off.
3. It ends on the payoff or a punchline, not a trail-off.
Skip menus, loading screens, idle walking, talking-head intros, sponsor reads, and anything that looks
like a leaked or pre-release build or a story spoiler.
Keep each cut inside one situation: if the frames show the video jumping to a different location or
activity, end the cut before the jump or skip the candidate.
If a campaign requirement names a creator, that creator must be clearly on screen and the main subject
for most of the cut (use the channel avatar to recognise them when it shows a face). A clip about
someone else with the creator only at the end fails; skip it.

For each pick:
- start/end: tighten within the candidate (you may move each edge by up to 6 s). Start at most 1.5 s
  before the action becomes visible, so frame 0 is already moving; end right after the payoff.
  Respect the min/max length you are given.
- hook: max 7 words, shown on screen over the first seconds; most viewers watch muted, so it must make
  sense with no sound. Make it specific to this clip (a number, a name, the thing on screen), never a
  generic "wait for it". Plain words, no emojis, no hashtags, must be true to what happens.
- title: 40-60 characters (60 is where desktop search truncates; the first 40 must carry the point for
  mobile). A concrete detail beats an adjective. At most two ALL-CAPS words. Different words from the
  hook. Follow the niche style you are given. No claims the clip does not show.
- description: 1-2 sentences, no hashtags (they are added later), no links.
- graphic_violence_first_7s: true if the first 7 seconds of your cut show gore/brutal violence.
- quality: 1-10, how likely this clip is to hold a scroller.
Return only picks with quality >= 6. Return fewer picks rather than weak ones.

You also plan the edit, like a short-form editor would. All times are in source seconds and must fall
inside the cut:
- extra_pieces: usually []. Use it only when the setup and its payoff sit in different candidates of the
  same situation (e.g. the bet in candidate 1, the result in candidate 3). The clip plays the main cut and
  the extra pieces in time order, so the total must stay within the clip length. Never join unrelated
  moments.
- zooms: 1-3 punch-ins on the strongest beats: a big reaction, the punchline, the reveal. t = when the
  zoom starts (on the beat, not before), dur 0.6-1.6 s. Not in the first second.
- emojis: 0-2 pop-ups on the funniest beat or the punchline (😭 💀 😂 🔥 😳 🤯 💰 🚨). One emoji
  each, matching the tone. None on serious or sad moments.
- sfx: sound effects from the list you are given, 0-2, on a beat (impact, reveal, punchline). Only names
  from the list; if the list is empty, return []. Never over speech that needs to be heard.
Jump cuts (removing dead air) and the music bed are done automatically; do not plan them."""


def _winning_titles_text(creator_key: str | None) -> str:
    """Competitors' best-performing titles for this creator, as the pattern to follow."""
    from . import winners

    # A creator with no titles of its own (CORE: searches return pet videos) borrows the crew's best.
    titles = (winners.top_titles(creator_key) or winners.top_titles(None)) if creator_key else []
    if not titles:
        return ""
    lines = "\n".join(f"- \"{t}\" ({v:,} views)" for t, v in titles)
    return ("\nTitles that won for this creator on competitor channels (model yours on these: same shape, "
            "length and tone, changed to fit your clip; never copy one word for word unless it is the "
            "proven moment's own title, and even then change it a little):\n" + lines)


def _claude_pick(src: dict, cands: list[dict], words: list[dict], cfg: dict, n: int) -> list[dict] | None:
    if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
        return None
    import anthropic

    content: list[dict] = [{
        "type": "text",
        "text": (
            f"Niche: {cfg.get('display')}\nTitle style: {cfg.get('title_style')}\n"
            f"Source title: {src.get('title')}\nSource channel: {src.get('channel_title')}\n"
            f"Clip length: {cfg['clip_min_s']}-{cfg['clip_max_s']} s. Pick at most {n * 2}, best first "
            f"(only {n} will be used; the rest are backups if a pick fails the final check)."
            + (f"\nCampaign requirement (reject candidates that fail it): {cfg['focus']}" if cfg.get("focus") else "")
            + _winning_titles_text(cfg.get("creator_key"))
            + "\nSound effects available: " + (", ".join(sorted(edit.sfx_library())) or "none")
        ),
    }]
    avatar = _avatar_b64(src.get("channel_id")) if cfg.get("focus") else None
    if avatar:
        content += [{"type": "text", "text": "Channel avatar (reference; may be a logo):"},
                    {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": avatar}}]
    for i, c in enumerate(cands):
        mid = c["peak"]
        pv = c.get("proven")
        proof = (f"PROVEN MOMENT: a competitor's Short of this moment got {pv['views']:,} views. Their title: "
                 f"\"{pv['short_title']}\". If you pick this candidate, base your title on theirs: keep its "
                 "structure, names and key detail, but change it a little (swap a word or two, reword the verb "
                 "or the ending) so it is not identical. Drop anything the footage does not show. Write your "
                 "own hook.\n") if pv else ""
        content.append({"type": "text", "text": (
            f"\n### Candidate {i}: {c['start']:.1f}s-{c['end']:.1f}s (peak {mid:.1f}s, signal {c['score']:.2f})\n"
            + proof + "Transcript: " + (" ".join(w["text"] for w in media.words_between(words, c["start"], c["end"]))[:1200]
                              or "(none)")
        )})
        if cfg.get("focus"):  # campaign clips: enough frames to see who is on screen through the window
            times = [c["start"] + 0.5 + (c["end"] - c["start"] - 1.5) * j / 5 for j in range(6)]
        else:
            times = [c["start"] + 0.5, mid, max(c["start"], c["end"] - 1)]
        for t in times:
            content.append({"type": "image", "source": {
                "type": "base64", "media_type": "image/jpeg",
                "data": media.frame_jpeg_b64(*media.source_at(src, t))}})

    client = anthropic.Anthropic()
    try:
        resp = client.beta.messages.create(
            model=MODEL,
            max_tokens=16000,
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            thinking={"type": "adaptive"},
            output_config={"effort": "medium", "format": {"type": "json_schema", "schema": SCHEMA}},
            system=SYSTEM,
            messages=[{"role": "user", "content": content}],
        )
    except anthropic.RateLimitError:
        return None
    except anthropic.APIStatusError as e:
        if e.status_code >= 500:
            return None
        raise
    except anthropic.APIConnectionError:
        return None
    if resp.stop_reason == "refusal":
        return None
    text = next((b.text for b in resp.content if b.type == "text"), None)
    if not text:
        return None
    picks = json.loads(text)["picks"]
    out = []
    for p in picks:
        if not (0 <= p["candidate"] < len(cands)):
            continue
        c = cands[p["candidate"]]
        start = max(c["start"] - 6, min(p["start"], c["end"]))
        end = min(c["end"] + 6, max(p["end"], start + cfg["clip_min_s"]))
        end = min(end, start + cfg["clip_max_s"])
        start = max(0.0, start)
        if cfg.get("violence_safe_hook") and p["graphic_violence_first_7s"]:
            continue
        ranges = edit_ranges((round(start, 2), round(end, 2)), p.get("extra_pieces") or [], cands, cfg)
        out.append({**p, "start": ranges[0][0], "end": ranges[-1][1], "ranges": ranges,
                    **edit_cues(p, ranges), "score": p["quality"] + c["score"] / 10,
                    "title": fit_title(p["title"]), "hook": " ".join(p["hook"].split()[:7])})
    out.sort(key=lambda x: -x["score"])
    return out[: n * 2]


def edit_ranges(main: tuple[float, float], extra: list[dict], cands: list[dict], cfg: dict) -> list[tuple[float, float]]:
    """Main cut + extra pieces (each kept within its candidate +-6 s), in time order, within the max length."""
    pieces = [main]
    for x in extra[:2]:
        if 0 <= x.get("candidate", -1) < len(cands):
            c = cands[x["candidate"]]
            a = max(0.0, c["start"] - 6, min(x["start"], c["end"]))
            b = min(c["end"] + 6, max(x["end"], a + 1.0))
            if b - a >= 1.0:
                pieces.append((a, b))
    ranges = [(round(a, 2), round(b, 2)) for a, b in media._merge_ranges(pieces)]
    over = sum(b - a for a, b in ranges) - cfg["clip_max_s"]
    while over > 0 and ranges:  # too long: trim the end of the last piece (drop it if that empties it)
        a, b = ranges[-1]
        if b - a - over >= 1.0:
            ranges[-1] = (a, round(b - over, 2))
            break
        ranges.pop()
        over -= b - a
    return ranges or [main]


def edit_cues(p: dict, ranges: list[tuple[float, float]]) -> dict:
    """Keep only cues inside the cut, with sane values; sfx only from the supplied library."""
    def inside(t):
        return any(a + 0.3 <= t <= b - 0.3 for a, b in ranges)

    lib = edit.sfx_library()
    zooms = [{"t": z["t"], "dur": min(1.6, max(0.5, z["dur"]))} for z in p.get("zooms") or [] if inside(z["t"])][:3]
    emojis = [e for e in p.get("emojis") or [] if inside(e["t"]) and 0 < len(e["emoji"]) <= 8
              and not any(ch.isalnum() for ch in e["emoji"])][:2]
    sfx = [x for x in p.get("sfx") or [] if inside(x["t"]) and x["name"].lower() in lib][:2]
    return {"zooms": zooms, "emojis": emojis, "sfx": sfx}


# ------------------------------------------------------------ facecam ----
FACECAM_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["has_facecam", "x", "y", "w", "h", "content_x"],
    "properties": {"has_facecam": {"type": "boolean"}, "x": {"type": "number"}, "y": {"type": "number"},
                   "w": {"type": "number"}, "h": {"type": "number"}, "content_x": {"type": "number"}},
}
FACECAM_SYSTEM = """You look at frames from a livestream and locate the streamer's webcam overlay: the
rectangle showing the camera feed of the streamer (a person filmed by a camera), drawn over the game or
screen. Give its box as fractions of the frame width/height (x, y = top-left corner; w, h = size), tight to
the camera image, excluding decorative borders and chat. If there is no webcam overlay, or the whole
frame is the camera (IRL / just-chatting full-cam shots), has_facecam is false and the box is 0s.
content_x: horizontal centre (fraction of width) of the most important screen content outside the
webcam (the game action, the website being shown); 0.5 if unsure."""


def detect_facecam(src: dict, times: list[float]) -> dict | None:
    """Where the streamer's webcam box is (same in every frame given), or None (use the blur layout)."""
    if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
        return None
    import anthropic

    content: list[dict] = [{"type": "text", "text": f"{len(times)} frames from the same stream:"}]
    for t in times:
        content.append({"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                                     "data": media.frame_jpeg_b64(*media.source_at(src, t), width=768)}})
    try:
        resp = anthropic.Anthropic().beta.messages.create(
            model=MODEL, max_tokens=4000, betas=["server-side-fallback-2026-07-01"], fallbacks="default",
            thinking={"type": "adaptive"},
            output_config={"effort": "low", "format": {"type": "json_schema", "schema": FACECAM_SCHEMA}},
            system=FACECAM_SYSTEM, messages=[{"role": "user", "content": content}])
    except (anthropic.RateLimitError, anthropic.APIConnectionError, anthropic.APIStatusError):
        return None
    text = next((b.text for b in resp.content if b.type == "text"), None)
    if resp.stop_reason == "refusal" or not text:
        return None
    return facecam_box(json.loads(text))


def facecam_box(v: dict) -> dict | None:
    """Sanity-check the detected box; None when there is no usable webcam overlay."""
    if not v.get("has_facecam"):
        return None
    x, y, w, h = (float(v[k]) for k in ("x", "y", "w", "h"))
    if not (0.06 <= w <= 0.7 and 0.06 <= h <= 0.7 and x >= -0.01 and y >= -0.01
            and x + w <= 1.01 and y + h <= 1.01):
        return None
    return {"x": max(0.0, x), "y": max(0.0, y), "w": w, "h": h,
            "content_x": min(0.95, max(0.05, float(v.get("content_x") or 0.5)))}


# ------------------------------------------------------------ verify pass ---
VERIFY_FRAMES = 8
VERIFY_SCHEMA = {
    "type": "object",
    "properties": {
        "requirement_frames": {"type": "integer"},
        "one_continuous_moment": {"type": "boolean"},
        "matches_title_and_hook": {"type": "boolean"},
        "notes": {"type": "string"},
    },
    "required": ["requirement_frames", "one_continuous_moment", "matches_title_and_hook", "notes"],
    "additionalProperties": False,
}

VERIFY_SYSTEM = """You check a finished short clip before it is posted. You get evenly spaced frames from
the whole clip (in order), its on-screen hook and title, and possibly a campaign requirement plus the
creator's channel avatar as a reference (the avatar may be a logo rather than a face).

Answer strictly from what the frames show:
- requirement_frames: how many of the frames satisfy the campaign requirement (e.g. the named creator is
  clearly visible and is the main subject, not a passer-by or the back of a head). If there is no
  requirement, return the number of frames.
- one_continuous_moment: true if the frames show one situation; false if the clip cuts to a different,
  unrelated scene part-way (a new location or activity). Camera-angle changes within the same moment are fine.
- matches_title_and_hook: true if what happens on screen supports the hook and title.
- notes: one short sentence on the main problem, or "ok"."""


def _avatar_b64(channel_id: str | None) -> str | None:
    """The source channel's avatar (cached), used as a who-is-who reference for the verify pass."""
    if not channel_id or not os.environ.get("YOUTUBE_API_KEY"):
        return None
    import base64
    import urllib.request

    from .config import data_dir

    cache = data_dir("avatars") / f"{channel_id}.jpg"
    if not cache.exists():
        try:
            from .discover import youtube_client

            items = youtube_client().channels().list(part="snippet", id=channel_id).execute().get("items", [])
            thumbs = items[0]["snippet"]["thumbnails"] if items else {}
            url = (thumbs.get("medium") or thumbs.get("default") or {}).get("url")
            if not url:
                return None
            with urllib.request.urlopen(url, timeout=20) as r:
                cache.write_bytes(r.read())
        except Exception:
            return None
    return base64.b64encode(cache.read_bytes()).decode()


def verify_pick(src: dict, pick: dict, cfg: dict) -> tuple[bool, str]:
    """Second look at the final cut: creator focus, one continuous moment, hook/title truthful.

    Returns (ok, reason). If the API is unavailable the clip passes here (QA and your review still apply).
    """
    if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
        return True, "not verified (no API key)"
    import anthropic

    tl = edit.Timeline(pick.get("ranges") or [(pick["start"], pick["end"])])
    span = max(0.1, tl.duration - 0.6)
    times = [tl.to_src(0.3 + span * i / (VERIFY_FRAMES - 1)) for i in range(VERIFY_FRAMES)]
    focus = cfg.get("focus")
    content: list[dict] = [{"type": "text", "text": (
        f"Hook: {pick['hook']}\nTitle: {pick['title']}\nSource channel: {src.get('channel_title')}\n"
        + (f"Campaign requirement: {focus}" if focus else "Campaign requirement: none"))}]
    avatar = _avatar_b64(src.get("channel_id")) if focus else None
    if avatar:
        content += [{"type": "text", "text": "Channel avatar (reference):"},
                    {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": avatar}}]
    content.append({"type": "text", "text": f"{VERIFY_FRAMES} frames from the clip, in order:"})
    for t in times:
        content.append({"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                                     "data": media.frame_jpeg_b64(*media.source_at(src, t))}})
    try:
        resp = anthropic.Anthropic().beta.messages.create(
            model=MODEL, max_tokens=4000, betas=["server-side-fallback-2026-07-01"], fallbacks="default",
            thinking={"type": "adaptive"},
            output_config={"effort": "low", "format": {"type": "json_schema", "schema": VERIFY_SCHEMA}},
            system=VERIFY_SYSTEM, messages=[{"role": "user", "content": content}])
    except (anthropic.RateLimitError, anthropic.APIConnectionError):
        return True, "not verified (API unavailable)"
    except anthropic.APIStatusError as e:
        if e.status_code >= 500:
            return True, "not verified (API unavailable)"
        raise
    text = next((b.text for b in resp.content if b.type == "text"), None)
    if resp.stop_reason == "refusal" or not text:
        return True, "not verified (no answer)"
    return judge_verify(json.loads(text), bool(focus))


def judge_verify(v: dict, has_focus: bool, frames: int = VERIFY_FRAMES) -> tuple[bool, str]:
    need = -(-frames * 5 // 8)  # creator must be the subject in at least 5 of 8 frames
    if has_focus and v["requirement_frames"] < need:
        return False, f"creator not the focus ({v['requirement_frames']}/{frames} frames): {v['notes']}"
    if not v["one_continuous_moment"]:
        return False, f"cuts to an unrelated scene: {v['notes']}"
    if not v["matches_title_and_hook"]:
        return False, f"hook/title don't match the footage: {v['notes']}"
    return True, f"verified ({v['requirement_frames']}/{frames} frames)"


def fit_title(title: str, limit: int = 60) -> str:
    """Trim to the desktop-search limit at a word boundary (yt-package rule)."""
    title = " ".join(title.split())
    if len(title) <= limit:
        return title
    cut = title[:limit].rsplit(" ", 1)[0].rstrip(" ,;:-|")
    return cut or title[:limit]


def _heuristic_pick(src: dict, cands: list[dict], cfg: dict, n: int) -> list[dict]:
    disp = cfg.get("display", "")
    return [{
        "candidate": i, "start": c["start"], "end": c["end"], "score": c["score"],
        "hook": "Wait for it...", "title": f"{disp} moment you have to see",
        "description": f"Clip from {src.get('title') or 'gameplay'}.", "reason": "heuristic: loudness/scene peak",
        "graphic_violence_first_7s": False, "quality": 0, "ranges": [(c["start"], c["end"])],
    } for i, c in enumerate(sorted(cands, key=lambda c: -c["score"])[:n])]


def _covered(src: dict, start: float, end: float) -> bool:
    """True if [start, end] lies inside one downloaded section of the source."""
    start = max(0.0, start)
    return any(s["start"] <= start and end <= s["end"] + 0.05 for s in src.get("segments") or [])


def find(src: dict, cfg: dict) -> list[dict]:
    path = src["local_path"]
    info = media.probe(path)
    audio_only = not info["width"]  # long source: audio + captions only so far (fetch.LONG_SOURCE_S)
    words = media.load_json3_words(src.get("captions_path"))
    cuts = [] if audio_only else media.scene_cuts(path)
    score = per_second_scores(info["duration"], media.audio_energy(path), cuts, words)
    n = cfg["clips_per_source"]
    cands = candidate_windows(score, cfg, k=max(4, n * 4))
    cands = [c for c in cands if c["start"] >= cfg.get("min_start_s", 0)]
    from . import winners

    proven = [h for h in winners.hint_candidates(src["id"], info["duration"], cfg)
              if h["start"] >= cfg.get("min_start_s", 0)]
    # Proven moments first; drop signal candidates that overlap them.
    cands = proven + [c for c in cands if not any(c["start"] < h["end"] and h["start"] < c["end"] for h in proven)]
    if not cands:
        return []
    if not words and os.environ.get("CLIPPER_WHISPER", "1") != "0":
        # No YouTube captions (often HTTP 429): transcribe just the candidate windows (+ the 6 s the
        # picker may extend each edge) so Claude gets the dialogue and the clip gets burned-in captions.
        langs = (cfg.get("discovery") or {}).get("languages") or [None]
        words = media.transcribe_ranges(path, [(c["start"] - 6, c["end"] + 6) for c in cands], language=langs[0])
    last = max(0.0, info["duration"] - 0.25)  # never cut or sample past the real end of the source
    for c in cands:
        c["end"] = min(c["end"], last)
        c["peak"] = min(c["peak"], last)
    if audio_only:
        # Download just the candidate windows as video (tens of MB instead of a whole 1080p VOD).
        from .fetch import SECTION_PAD_S, fetch_sections

        src["segments"] = fetch_sections(src, [(c["start"] - SECTION_PAD_S, c["end"] + SECTION_PAD_S)
                                               for c in cands])
        cands = [c for c in cands if _covered(src, c["start"] - 6, min(c["end"] + 6, last))]
        if not cands:
            return []
    if cfg.get("layout") == "facecam_stack" and "facecam" not in src:
        src["facecam"] = detect_facecam(src, [c["peak"] for c in cands[:3]])
    claude = _claude_pick(src, cands, words, cfg, n)
    # Claude returning [] means "nothing good here": no clip. The heuristic is only for when the API is unavailable.
    picks = claude if claude is not None else _heuristic_pick(src, cands, cfg, n)
    kept = []
    for p in picks:
        ranges = [(a, min(b, last)) for a, b in p.get("ranges") or [(p["start"], p["end"])] if min(b, last) > a]
        if len(ranges) == 1 and ranges[0][1] - ranges[0][0] < cfg["clip_min_s"]:
            ranges = [(max(0.0, ranges[0][1] - cfg["clip_min_s"]), ranges[0][1])]
        if not ranges or (audio_only and not all(_covered(src, a, b) for a, b in ranges)):
            continue
        p["ranges"], p["start"], p["end"] = ranges, ranges[0][0], ranges[-1][1]
        if claude is not None:
            ok, why = verify_pick(src, p, cfg)
            p["reason"] = f"{p['reason']} [{why}]"
            if not ok:
                print(f"dropped {src['id']} {p['start']:.0f}-{p['end']:.0f}s: {why}")
                continue
        if cfg.get("jump_cuts"):
            p["ranges"] = edit.jump_ranges(src, p["ranges"], words, cfg["clip_min_s"])
        p["words"] = media.words_between(words, p["start"], p["end"])
        kept.append(p)
        if len(kept) >= n:
            break
    return kept
