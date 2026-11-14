"""Upload to YouTube with the Data API v3 (videos.insert, resumable).

Quota: videos.insert has its own bucket since 2026-06-01 (1 unit/call, 100 calls/day default).
Since 2026-11-02, uploads from unverified API projects are no longer forced to private.
"""
from __future__ import annotations

from pathlib import Path

from .config import ROOT

SCOPES = ["https://www.googleapis.com/auth/youtube.upload", "https://www.googleapis.com/auth/youtube.readonly"]


def _creds(acct: dict, interactive: bool = False):
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    token = ROOT / acct["token_file"]
    creds = Credentials.from_authorized_user_file(str(token), SCOPES) if token.exists() else None
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        token.write_text(creds.to_json())
    if not creds or not creds.valid:
        if not interactive:
            raise RuntimeError(f"No valid YouTube token at {token}. Run: clipper auth-youtube --niche <niche>")
        from google_auth_oauthlib.flow import InstalledAppFlow

        flow = InstalledAppFlow.from_client_secrets_file(str(ROOT / acct["oauth_client_secret"]), SCOPES)
        creds = flow.run_local_server(port=0, open_browser=True)
        token.parent.mkdir(parents=True, exist_ok=True)
        token.write_text(creds.to_json())
    return creds


def authorize(acct: dict) -> str:
    """One-time interactive login for the channel owner. Returns the channel title."""
    from googleapiclient.discovery import build

    yt = build("youtube", "v3", credentials=_creds(acct, interactive=True), cache_discovery=False)
    me = yt.channels().list(part="snippet", mine=True).execute()["items"][0]
    if acct.get("channel_id") and me["id"] != acct["channel_id"]:
        (ROOT / acct["token_file"]).unlink(missing_ok=True)  # don't keep a login for the wrong channel
        raise RuntimeError(f"Logged in as channel '{me['snippet']['title']}' ({me['id']}) but config expects "
                           f"{acct['channel_id']}. Run auth-youtube again and pick the right channel.")
    return f"{me['snippet']['title']} ({me['id']})"


def upload(acct: dict, path: Path, title: str, description: str, tags: list[str]) -> dict:
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload

    yt = build("youtube", "v3", credentials=_creds(acct), cache_discovery=False)
    body = {
        "snippet": {
            "title": title[:100],
            "description": description[:5000],
            "tags": [t.lstrip("#") for t in tags][:15],
            "categoryId": str(acct.get("category_id", "20")),
        },
        "status": {
            "privacyStatus": acct.get("privacy", "private"),
            "selfDeclaredMadeForKids": False,
            "containsSyntheticMedia": False,
        },
    }
    media = MediaFileUpload(str(path), mimetype="video/mp4", chunksize=8 * 1024 * 1024, resumable=True)
    req = yt.videos().insert(part="snippet,status", body=body, media_body=media, notifySubscribers=True)
    resp = None
    while resp is None:
        _, resp = req.next_chunk()
    vid = resp["id"]
    return {"remote_id": vid, "url": f"https://www.youtube.com/shorts/{vid}"}


def stats(acct: dict, video_ids: list[str]) -> dict[str, dict]:
    from googleapiclient.discovery import build

    yt = build("youtube", "v3", credentials=_creds(acct), cache_discovery=False)
    out = {}
    for i in range(0, len(video_ids), 50):
        r = yt.videos().list(part="statistics", id=",".join(video_ids[i: i + 50])).execute()
        out.update({it["id"]: it["statistics"] for it in r.get("items", [])})
    return out
