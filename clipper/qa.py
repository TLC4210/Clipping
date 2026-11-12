"""Automatic checks every clip must pass before it can be approved/published."""
from __future__ import annotations

from pathlib import Path

from . import media

IG_MAX_BYTES = 300 * 1024 * 1024  # conservative; Meta's documented Reels limits vary by source


def check(clip: dict, src: dict, cfg: dict) -> tuple[bool, list[str]]:
    problems: list[str] = []
    path = Path(clip["path"] or "")
    if not path.exists():
        return False, ["rendered file missing"]
    info = media.probe(path)
    if (info["width"], info["height"]) != (1080, 1920):
        problems.append(f"resolution {info['width']}x{info['height']} != 1080x1920")
    lo, hi = cfg["clip_min_s"], cfg["clip_max_s"]
    if not (lo - 1.5 <= info["duration"] <= hi + 1.5):
        problems.append(f"duration {info['duration']:.1f}s outside {lo}-{hi}s")
    if info["duration"] > 180:
        problems.append("longer than 3:00 — would not be a YouTube Short")
    if not info["has_audio"]:
        problems.append("no audio track")
    if info["size"] > IG_MAX_BYTES:
        problems.append("file too large for Instagram API")
    if info["vcodec"] != "h264" or info["acodec"] != "aac":
        problems.append(f"codecs {info['vcodec']}/{info['acodec']} (need h264/aac)")

    if not src.get("rights_basis"):
        problems.append("source has no rights basis")
    if (src.get("rights_basis") or "").startswith("creativeCommon"):
        ass = path.with_suffix(".ass")
        if not ass.exists() or "(CC BY)" not in ass.read_text():
            problems.append("CC BY attribution missing from video")
        if src.get("url") and src["url"] not in (clip.get("description") or ""):
            problems.append("CC BY source link missing from description")

    caption = f"{clip.get('title') or ''} {clip.get('description') or ''}".lower()
    for token in cfg.get("caption_must_include", []):
        if token.lower() not in caption:
            problems.append(f"campaign caption requirement missing: {token}")
    if (src.get("rights_basis") or "").startswith("campaign:") and src.get("url") and src["url"] not in (clip.get("description") or ""):
        problems.append("source link missing from description")

    title = clip.get("title") or ""
    if not title or len(title) > 100:
        problems.append("title empty or > 100 chars")
    if not (clip.get("hook") or "").strip():
        problems.append("hook empty")
    for term in cfg.get("exclude_title_terms", []):
        if term.lower() in title.lower():
            problems.append(f"excluded term in title: {term}")
    return (not problems), problems
