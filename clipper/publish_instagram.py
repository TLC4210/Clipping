"""Publish Reels with the Instagram Graph API (Content Publishing).

Flow: create REELS container -> (resumable upload) -> poll status_code -> media_publish -> permalink.
Limit: 100 API-published posts per account per rolling 24 h (check content_publishing_limit).
"""
from __future__ import annotations

import time
from pathlib import Path

import requests

from .config import ROOT


def _token(acct: dict) -> str:
    p = ROOT / acct["access_token_file"]
    if not p.exists():
        raise RuntimeError(f"No Instagram token at {p}")
    return p.read_text().strip()


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


def publish(acct: dict, path: Path, caption: str, poll_s: int = 15, timeout_s: int = 600) -> dict:
    token = _token(acct)
    base = _base(acct)
    ig = acct["ig_user_id"]
    params = {"media_type": "REELS", "caption": caption[:2200], "access_token": token,
              "share_to_feed": str(acct.get("share_to_feed", True)).lower()}
    public = (acct.get("public_base_url") or "").rstrip("/")
    if public:
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
