"""Rights gate: decides whether a source may be downloaded and clipped."""
from __future__ import annotations

import re

from .config import load_permissions

# Signs that a "CC" upload is actually somebody else's content re-uploaded.
REUPLOAD_PATTERNS = re.compile(
    r"\b(re-?upload(ed)?|not my (video|content|clip)|credits? (go(es)? )?to|all credit|"
    r"no copyright infringement intended|i do not own|fair use)\b",
    re.I,
)


def check(video: dict, niche_cfg: dict) -> tuple[bool, str]:
    """Return (allowed, basis_or_reason) for a YouTube video resource dict.

    `video` is a videos.list item with snippet + status parts.
    """
    snippet = video.get("snippet", {})
    status = video.get("status", {})
    title = snippet.get("title", "")
    desc = snippet.get("description", "")
    channel_id = snippet.get("channelId", "")

    for term in niche_cfg.get("exclude_title_terms", []):
        if term.lower() in title.lower():
            return False, f"excluded term in title: {term!r}"

    if REUPLOAD_PATTERNS.search(title) or REUPLOAD_PATTERNS.search(desc):
        return False, "looks like a re-upload of someone else's content"

    if snippet.get("liveBroadcastContent") in ("live", "upcoming"):
        return False, "live or upcoming broadcast"

    for p in load_permissions():
        if p.get("channel_id") == channel_id:
            niches = p.get("niches")
            if niches and niche_cfg.get("_name") not in niches:
                continue
            return True, f"permission: {p.get('evidence', 'on file')}"

    if status.get("license") == "creativeCommon":
        return True, "creativeCommon (CC BY) — attribution required"

    return False, f"license is {status.get('license', 'unknown')!r} and no permission on file"
