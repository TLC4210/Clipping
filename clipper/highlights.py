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

from . import media

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
                },
                "required": ["candidate", "start", "end", "hook", "title", "description", "reason",
                             "graphic_violence_first_7s", "quality"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["picks"],
    "additionalProperties": False,
}

SYSTEM = """You are the editor for a short-form gaming clip channel (YouTube Shorts + Instagram Reels).
You get numbered candidate windows from one source video, each with 3 frames (start, peak, end),
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
Return only picks with quality >= 6. Return fewer picks rather than weak ones."""


def _claude_pick(src: dict, cands: list[dict], words: list[dict], cfg: dict, n: int) -> list[dict] | None:
    if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
        return None
    import anthropic

    content: list[dict] = [{
        "type": "text",
        "text": (
            f"Niche: {cfg.get('display')}\nTitle style: {cfg.get('title_style')}\n"
            f"Source title: {src.get('title')}\nSource channel: {src.get('channel_title')}\n"
            f"Clip length: {cfg['clip_min_s']}-{cfg['clip_max_s']} s. Pick at most {n}."
            + (f"\nCampaign requirement (reject candidates that fail it): {cfg['focus']}" if cfg.get("focus") else "")
        ),
    }]
    for i, c in enumerate(cands):
        mid = c["peak"]
        content.append({"type": "text", "text": (
            f"\n### Candidate {i}: {c['start']:.1f}s-{c['end']:.1f}s (peak {mid:.1f}s, signal {c['score']:.2f})\n"
            "Transcript: " + (" ".join(w["text"] for w in media.words_between(words, c["start"], c["end"]))[:1200]
                              or "(none)")
        )})
        for t in (c["start"] + 0.5, mid, max(c["start"], c["end"] - 1)):
            content.append({"type": "image", "source": {
                "type": "base64", "media_type": "image/jpeg",
                "data": media.frame_jpeg_b64(src["local_path"], t)}})

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
        out.append({**p, "start": round(start, 2), "end": round(end, 2), "score": p["quality"] + c["score"] / 10,
                    "title": fit_title(p["title"]), "hook": " ".join(p["hook"].split()[:7])})
    out.sort(key=lambda x: -x["score"])
    return out[:n]


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
        "graphic_violence_first_7s": False, "quality": 0,
    } for i, c in enumerate(sorted(cands, key=lambda c: -c["score"])[:n])]


def find(src: dict, cfg: dict) -> list[dict]:
    path = src["local_path"]
    info = media.probe(path)
    words = media.load_json3_words(src.get("captions_path")) or (
        media.transcribe_local(path) if os.environ.get("CLIPPER_WHISPER") else [])
    score = per_second_scores(info["duration"], media.audio_energy(path), media.scene_cuts(path), words)
    n = cfg["clips_per_source"]
    cands = candidate_windows(score, cfg, k=max(4, n * 4))
    cands = [c for c in cands if c["start"] >= cfg.get("min_start_s", 0)]
    if not cands:
        return []
    picks = _claude_pick(src, cands, words, cfg, n) or _heuristic_pick(src, cands, cfg, n)
    for p in picks:
        p["words"] = media.words_between(words, p["start"], p["end"])
    return picks
