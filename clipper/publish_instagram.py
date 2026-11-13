"""Publish Reels with the Instagram Graph API (Content Publishing).

Flow: create REELS container -> (resumable upload) -> poll status_code -> media_publish -> permalink.
Limit: 100 API-published posts per account per rolling 24 h (check content_publishing_limit).

Video source, in order: `gcs_bucket` (auto-upload to Google Cloud Storage, see storage.py),
`public_base_url` (you sync files there yourself), else resumable upload (Facebook Login hosts only).

Tokens: Instagram Login long-lived tokens last 60 days. `refresh_token()` swaps one for a fresh
60-day token; it runs before each publish once the token file is older than `refresh_after_days`.
"""
from __future__ import annotations

import os
import time
from pathlib import Path

import requests

from . import storage
from .config import ROOT

REFRESH_AFTER_DAYS = 7  # tokens last 60 days; refreshing weekly leaves lots of slack if the PC is off


def _token_path(acct: dict) -> Path:
    return ROOT / acct["access_token_file"]


def _token(acct: dict) -> str:
    p = _token_path(acct)
    if not p.exists():
        raise RuntimeError(f"No Instagram token at {p}")
    return p.read_text(encoding="utf-8").strip()


def token_age_days(acct: dict) -> float:
    return (time.time() - _token_path(acct).stat().st_mtime) / 86400


def refresh_token(acct: dict, force: bool = False) -> dict:
    """Exchange the long-lived token for a fresh 60-day one and rewrite the token file.

    Only works for Instagram Login tokens (graph.instagram.com) that are at least 24 h old
    and not yet expired. Returns a small status dict; never prints the token.
    """
    host = acct.get("api_host", "graph.instagram.com")
    if host != "graph.instagram.com":
        return {"status": "skipped", "why": f"refresh only supported for graph.instagram.com, not {host}"}
    age = token_age_days(acct)
    days = acct.get("refresh_after_days", REFRESH_AFTER_DAYS)
    if not force and age < days:
        return {"status": "fresh", "age_days": round(age, 1)}
    if age < 1:
        return {"status": "skipped", "why": "token is under 24 h old; Instagram refuses to refresh it yet"}
    data = _check(requests.get("https://graph.instagram.com/refresh_access_token",
                               params={"grant_type": "ig_refresh_token", "access_token": _token(acct)},
                               timeout=30))
    new = data["access_token"]
    p = _token_path(acct)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(new, encoding="utf-8")
    os.replace(tmp, p)
    return {"status": "refreshed", "expires_in_days": round(int(data.get("expires_in", 0)) / 86400, 1)}


def _base(acct: dict) -> str:
    return f"https://{acct.get('api_host', 'graph.instagram.com')}/{acct.get('api_version', 'v24.0')}"


def _check(r: requests.Response) -> dict:
    try:
        data = r.json()
    except ValueError:
        r.raise_for_status()
        raise
    if r.status_code >= 400 or "error" in data:
        raise RuntimeError(f"Instagram API error {r.status_code}: {data.get('error', data)}")
    return data


def publishing_quota(acct: dict) -> dict:
    r = requests.get(f"{_base(acct)}/{acct['ig_user_id']}/content_publishing_limit",
                     params={"fields": "quota_usage,config", "access_token": _token(acct)}, timeout=30)
    return _check(r)


def publish(acct: dict, path: Path, caption: str, poll_s: int = 15, timeout_s: int = 600,
            niche: str | None = None) -> dict:
    try:
        refresh_token(acct)
    except Exception:
        pass  # the current token is still valid for weeks; try again next run
    token = _token(acct)
    base = _base(acct)
    ig = acct["ig_user_id"]
    params = {"media_type": "REELS", "caption": caption[:2200], "access_token": token,
              "share_to_feed": str(acct.get("share_to_feed", True)).lower()}
    public = (acct.get("public_base_url") or "").rstrip("/")
    staged = None
    if storage.enabled(acct):
        staged = storage.upload(acct, path, niche)
        params["video_url"] = staged["url"]
        try:
            container = _check(requests.post(f"{base}/{ig}/media", data=params, timeout=60))["id"]
        except Exception:
            _cleanup(acct, staged)
            raise
    elif public:
        params["video_url"] = f"{public}/{path.name}"  # you must sync data/clips/<niche>/ to this location
        container = _check(requests.post(f"{base}/{ig}/media", data=params, timeout=60))["id"]
    else:
        params["upload_type"] = "resumable"
        container = _check(requests.post(f"{base}/{ig}/media", data=params, timeout=60))["id"]
        size = path.stat().st_size
        with open(path, "rb") as fh:
            r = requests.post(
                f"https://rupload.facebook.com/ig-api-upload/{acct.get('api_version', 'v24.0')}/{container}",
                headers={"Authorization": f"OAuth {token}", "offset": "0", "file_size": str(size)},
                data=fh, timeout=600)
        _check(r)

    try:
        return _finish(base, ig, token, container, poll_s, timeout_s)
    finally:
        _cleanup(acct, staged)


def _cleanup(acct: dict, staged: dict | None) -> None:
    if staged and acct.get("gcs_delete_after_publish", True):
        try:
            storage.delete(acct, staged["name"])
        except Exception:
            pass  # a leftover object costs fractions of a cent; never fail a publish over it


def _finish(base: str, ig: str, token: str, container: str, poll_s: int, timeout_s: int) -> dict:
    deadline = time.time() + timeout_s
    while True:
        st = _check(requests.get(f"{base}/{container}", params={"fields": "status_code,status",
                                                                  "access_token": token}, timeout=30))
        code = st.get("status_code")
        if code == "FINISHED":
            break
        if code in ("ERROR", "EXPIRED"):
            raise RuntimeError(f"Container {container} {code}: {st.get('status')}")
        if time.time() > deadline:
            raise TimeoutError(f"Container {container} still {code} after {timeout_s}s")
        time.sleep(poll_s)

    media_id = _check(requests.post(f"{base}/{ig}/media_publish",
                                    data={"creation_id": container, "access_token": token}, timeout=60))["id"]
    link = _check(requests.get(f"{base}/{media_id}", params={"fields": "permalink", "access_token": token},
                               timeout=30)).get("permalink")
    return {"remote_id": media_id, "url": link}
