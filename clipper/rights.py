"""Rights gate: decides whether a source may be downloaded and clipped.

A YouTube video is allowed only if ONE of these holds:
  1. its channel is an eligible creator in rights/creators.yaml (joined, active, in date, niche matches,
     video inside the campaign's source window), or
  2. its channel is in rights/permissions.yaml (written permission), or
  3. it is licensed Creative Commons (CC BY).
Anything on the creators.yaml `blocked:` list is always rejected.
"""
from __future__ import annotations

import re
from datetime import date

from .config import load_creators, load_permissions

# Signs that a "CC" upload is actually somebody else's content re-uploaded.
REUPLOAD_PATTERNS = re.compile(
    r"\b(re-?upload(ed)?|not my (video|content|clip)|credits? (go(es)? )?to|all credit|"
    r"no copyright infringement intended|i do not own|fair use)\b",
    re.I,
)


def _as_date(v) -> date | None:
    if v is None or v == "":
        return None
    if isinstance(v, date):
        return v
    return date.fromisoformat(str(v)[:10])


def creator_channel_ids(c: dict) -> list[str]:
    ids = [(c.get("youtube") or {}).get("channel_id")]
    ids += [y.get("channel_id") for y in c.get("also_youtube") or []]
    return [i for i in ids if i]


def creator_eligible(c: dict, niche_name: str | None, today: date | None = None) -> tuple[bool, str]:
    today = today or date.today()
    if c.get("status") != "active":
        return False, f"status is {c.get('status')!r}"
    if not c.get("joined"):
        return False, "campaign not joined yet (set joined: true after joining)"
    until = _as_date(c.get("valid_until"))
    if until and today > until:
        return False, f"expired {until}"
    if niche_name and niche_name not in (c.get("niches") or []):
        return False, f"not allowed for niche {niche_name!r}"
    return True, "ok"


def in_source_window(c: dict, published_at: str | None) -> tuple[bool, str]:
    src = c.get("source") or {}
    if src.get("any_date") or not published_at:
        return True, "ok"
    pub = _as_date(published_at)
    after, before = _as_date(src.get("published_after")), _as_date(src.get("published_before"))
    if after and pub < after:
        return False, f"published {pub} before campaign window {after}"
    if before and pub >= before:
        return False, f"published {pub} after campaign window {before}"
    return True, "ok"


def find_creator(channel_id: str) -> tuple[str | None, dict | None]:
    creators, _ = load_creators()
    for key, c in creators.items():
        if channel_id and channel_id in creator_channel_ids(c):
            return key, c
    return None, None


def is_blocked(channel_id: str, channel_title: str) -> str | None:
    _, blocked = load_creators()
    for b in blocked:
        if b.get("youtube_channel_id") and b["youtube_channel_id"] == channel_id:
            return b.get("reason", "blocked")
        if b.get("name") and channel_title and b["name"].strip().lower() == channel_title.strip().lower():
            return b.get("reason", "blocked")
    return None


def check(video: dict, niche_cfg: dict) -> tuple[bool, str]:
    """Return (allowed, basis_or_reason) for a YouTube video resource dict (snippet + status parts)."""
    snippet = video.get("snippet", {})
    status = video.get("status", {})
    title = snippet.get("title", "")
    desc = snippet.get("description", "")
    channel_id = snippet.get("channelId", "")
    niche_name = niche_cfg.get("_name")

    reason = is_blocked(channel_id, snippet.get("channelTitle", ""))
    if reason:
        return False, f"blocked creator: {reason}"

    for term in niche_cfg.get("exclude_title_terms", []):
        if term.lower() in title.lower():
            return False, f"excluded term in title: {term!r}"

    if snippet.get("liveBroadcastContent") in ("live", "upcoming"):
        return False, "live or upcoming broadcast"

    key, creator = find_creator(channel_id)
    if creator:
        ok, why = creator_eligible(creator, niche_name)
        if not ok:
            return False, f"creator {key}: {why}"
        ok, why = in_source_window(creator, snippet.get("publishedAt"))
        if not ok:
            return False, f"creator {key}: {why}"
        return True, f"campaign:{key}"

    if REUPLOAD_PATTERNS.search(title) or REUPLOAD_PATTERNS.search(desc):
        return False, "looks like a re-upload of someone else's content"

    for p in load_permissions():
        if p.get("channel_id") == channel_id:
            niches = p.get("niches")
            if niches and niche_name not in niches:
                continue
            return True, f"permission: {p.get('evidence', 'on file')}"

    if niche_cfg.get("discovery", {}).get("license") == "creativeCommon" and status.get("license") == "creativeCommon":
        return True, "creativeCommon (CC BY) — attribution required"

    return False, f"license is {status.get('license', 'unknown')!r}, not a joined creator campaign, no permission on file"
