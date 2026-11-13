"""Instagram bucket staging + token refresh, with all network calls faked."""
import os
import time
from pathlib import Path

import pytest


class Resp:
    def __init__(self, data, status=200):
        self._d, self.status_code, self.text = data, status, str(data)

    def json(self):
        return self._d


@pytest.fixture()
def ig(tmp_path, monkeypatch):
    monkeypatch.setenv("CLIPPER_ROOT", str(tmp_path))
    import importlib

    import clipper.config as config
    importlib.reload(config)
    from clipper import publish_instagram, storage
    importlib.reload(storage)
    importlib.reload(publish_instagram)
    (tmp_path / "secrets").mkdir()
    tok = tmp_path / "secrets" / "ig.txt"
    tok.write_text("OLD")
    acct = {"ig_user_id": "123", "access_token_file": "secrets/ig.txt", "gcs_bucket": "bkt"}
    return publish_instagram, storage, acct, tok


def _age(path: Path, days: float):
    t = time.time() - days * 86400
    os.utime(path, (t, t))


def test_refresh_only_when_old(ig, monkeypatch):
    pi, _, acct, tok = ig
    calls = []
    monkeypatch.setattr(pi.requests, "get", lambda url, params=None, timeout=None: calls.append(params) or
                        Resp({"access_token": "NEW", "expires_in": 5184000}))
    _age(tok, 2)
    assert pi.refresh_token(acct)["status"] == "fresh" and not calls
    _age(tok, 8)
    r = pi.refresh_token(acct)
    assert r == {"status": "refreshed", "expires_in_days": 60.0}
    assert calls[0] == {"grant_type": "ig_refresh_token", "access_token": "OLD"}
    assert tok.read_text() == "NEW"
    assert pi.refresh_token({**acct, "api_host": "graph.facebook.com"}, force=True)["status"] == "skipped"


def test_publish_stages_in_bucket_then_deletes(ig, monkeypatch, tmp_path):
    pi, storage, acct, tok = ig
    _age(tok, 2)
    clip = tmp_path / "clip 1.mp4"
    clip.write_bytes(b"video")
    events = []

    class Sess:
        def post(self, url, params=None, headers=None, data=None, timeout=None):
            events.append(("upload", url, params["name"], data.read()))
            return Resp({})

        def delete(self, url, timeout=None):
            events.append(("delete", url))
            return Resp({}, 204)

    monkeypatch.setattr(storage, "_session", lambda acct: Sess())

    def post(url, data=None, timeout=None):
        if url.endswith("/media"):
            events.append(("container", data["video_url"]))
            return Resp({"id": "C1"})
        return Resp({"id": "M1"})

    def get(url, params=None, timeout=None):
        return Resp({"status_code": "FINISHED"} if "status_code" in params.get("fields", "") else
                    {"permalink": "https://instagram.com/reel/x"})

    monkeypatch.setattr(pi.requests, "post", post)
    monkeypatch.setattr(pi.requests, "get", get)
    r = pi.publish(acct, clip, "hi", niche="gta", poll_s=0)
    assert r == {"remote_id": "M1", "url": "https://instagram.com/reel/x"}
    assert events[0] == ("upload", "https://storage.googleapis.com/upload/storage/v1/b/bkt/o", "gta/clip 1.mp4",
                         b"video")
    assert events[1] == ("container", "https://storage.googleapis.com/bkt/gta/clip%201.mp4")
    assert events[2] == ("delete", "https://storage.googleapis.com/storage/v1/b/bkt/o/gta%2Fclip%201.mp4")
