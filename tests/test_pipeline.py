"""End-to-end test on a synthetic 16:9 'gameplay' video (no network, no API keys needed)."""
import json
import os
import subprocess
from pathlib import Path

import pytest


@pytest.fixture()
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("CLIPPER_DATA", str(tmp_path / "data"))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    import importlib

    import clipper.config as config
    importlib.reload(config)
    for m in ("db", "media", "rights", "highlights", "render", "qa", "fetch", "discover", "pipeline"):
        importlib.reload(importlib.import_module(f"clipper.{m}"))
    return tmp_path


def make_video(path: Path, seconds=90):
    # 1280x720 test pattern; audio is quiet noise with two loud bursts (at ~30s and ~70s)
    vol = "if(between(t,28,33)+between(t,68,72),0.9,0.05)"
    subprocess.run([
        "ffmpeg", "-y", "-v", "error",
        "-f", "lavfi", "-i", f"testsrc2=size=1280x720:rate=30:duration={seconds}",
        "-f", "lavfi", "-i", f"anoisesrc=d={seconds}:c=pink:r=48000:a=1",
        "-filter_complex", f"[1:a]volume='{vol}':eval=frame[a]",
        "-map", "0:v", "-map", "[a]", "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", "-shortest", str(path),
    ], check=True)


def test_inbox_to_rendered_clip(env):
    from clipper import db, fetch, pipeline
    from clipper.config import data_dir

    make_video(data_dir("inbox", "gta") / "my_gameplay.mp4")
    conn = db.connect()
    added = fetch.ingest_inbox(conn, "gta")
    assert len(added) == 1
    clip_ids = pipeline.mine_and_render(conn, "gta", limit=1)
    assert clip_ids, "no clips produced"
    rows = [dict(r) for r in conn.execute("SELECT * FROM clips")]
    passing = [r for r in rows if r["status"] == "rendered"]
    assert passing, [r["qa_report"] for r in rows]
    from clipper import media
    info = media.probe(passing[0]["path"])
    assert (info["width"], info["height"]) == (1080, 1920)
    assert info["has_audio"]
    # the loud bursts should be inside the chosen windows
    spans = [(r["start_s"], r["end_s"]) for r in passing]
    assert any(s <= 30 <= e for s, e in spans) or any(s <= 70 <= e for s, e in spans), spans

    # approve + dry-run publish (accounts disabled in example config -> nothing to do)
    assert pipeline.approve(conn, all_passing=True, niche_name="gta") == len(passing)
    assert pipeline.publish_approved(conn, "gta", live=False) == []


def test_one_account_per_platform_enforced(env):
    from clipper import db
    import sqlite3

    conn = db.connect()
    db.upsert_source(conn, id="file:x", niche="gta", kind="inbox", status="fetched")
    conn.execute("INSERT INTO clips (source_id, niche, start_s, end_s, created_at) VALUES ('file:x','gta',0,20,'t')")
    conn.execute("INSERT INTO posts (clip_id, platform, account, status, posted_at) VALUES (1,'youtube','gta','published','t')")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO posts (clip_id, platform, account, status, posted_at) "
                     "VALUES (1,'youtube','minecraft','published','t')")


def _video(license="creativeCommon", title="GTA 5 funny moments", desc="", channel="UCabc"):
    return {"id": "vid1", "snippet": {"title": title, "description": desc, "channelId": channel,
                                      "channelTitle": "Gamer", "liveBroadcastContent": "none"},
            "status": {"license": license},
            "contentDetails": {"duration": "PT12M3S"}, "statistics": {"viewCount": "120000"}}


def test_rights_gate(env):
    from clipper import rights
    from clipper.config import niche

    cfg = {**niche("gta"), "_name": "gta"}
    assert rights.check(_video(), cfg)[0]
    assert not rights.check(_video(license="youtube"), cfg)[0]
    assert not rights.check(_video(title="GTA 6 LEAKED gameplay"), cfg)[0]
    assert not rights.check(_video(desc="All credit goes to the original creator"), cfg)[0]


def test_discover_with_fake_api(env):
    from clipper import db, discover

    class Req:
        def __init__(self, data): self.data = data
        def execute(self): return self.data

    class FakeYT:
        def search(self):
            class S:
                def list(self, **kw):
                    assert kw["videoLicense"] == "creativeCommon"
                    return Req({"items": [{"id": {"videoId": "vid1"}}, {"id": {"videoId": "vid2"}}]})
            return S()

        def videos(self):
            class V:
                def list(self, **kw):
                    a = _video()
                    b = {**_video(license="youtube"), "id": "vid2"}
                    return Req({"items": [a, b]})
            return V()

    conn = db.connect()
    stats = discover.run("gta", conn, yt=FakeYT(), queries=["gta"])
    assert stats == {"found": 2, "new_ok": 1, "rejected": 1}
    ok = conn.execute("SELECT * FROM sources WHERE status='discovered'").fetchall()
    assert [r["id"] for r in ok] == ["yt:vid1"]
    assert ok[0]["duration_s"] == 723


def test_json3_captions(env, tmp_path):
    from clipper import media

    p = tmp_path / "c.json3"
    p.write_text(json.dumps({"events": [
        {"tStartMs": 1000, "dDurationMs": 2000, "segs": [{"utf8": "no"}, {"utf8": " way", "tOffsetMs": 400}]},
        {"tStartMs": 3000, "dDurationMs": 1000, "segs": [{"utf8": "\n"}]},
    ]}))
    words = media.load_json3_words(p)
    assert [w["text"] for w in words] == ["no", "way"]
    assert words[0]["start"] == 1.0 and words[0]["end"] == 1.4


def test_claude_picker_request_and_parsing(env, monkeypatch):
    """Capture the real SDK request body with a mock transport and feed back a structured response."""
    import anthropic
    import httpx2 as httpx

    from clipper import config, highlights

    src_path = config.data_dir("sources", "gta") / "v.mp4"
    make_video(src_path, 60)
    captured = {}
    picks = {"picks": [
        {"candidate": 0, "start": 20.0, "end": 41.0, "hook": "Watch the car", "title": "This GTA jump was insane",
         "description": "A jump that went wrong.", "reason": "clear payoff", "graphic_violence_first_7s": False,
         "quality": 8},
        {"candidate": 1, "start": 0, "end": 30, "hook": "x", "title": "gory", "description": "d", "reason": "r",
         "graphic_violence_first_7s": True, "quality": 9},
    ]}

    def handler(request: httpx.Request):
        captured["body"] = json.loads(request.content)
        captured["beta"] = request.headers.get("anthropic-beta")
        return httpx.Response(200, json={
            "id": "msg_1", "type": "message", "role": "assistant", "model": "claude-opus-5-5",
            "content": [{"type": "text", "text": json.dumps(picks)}],
            "stop_reason": "end_turn", "stop_sequence": None,
            "usage": {"input_tokens": 10, "output_tokens": 10}})

    real = anthropic.Anthropic
    monkeypatch.setattr(anthropic, "Anthropic",
                        lambda: real(api_key="test", http_client=httpx.Client(transport=httpx.MockTransport(handler))))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")

    cfg = {**config.niche("gta"), "_name": "gta"}
    cands = [{"start": 18.0, "end": 48.0, "peak": 30.0, "score": 2.0}, {"start": 0.0, "end": 30.0, "peak": 10, "score": 1.0}]
    out = highlights._claude_pick({"local_path": str(src_path), "title": "t"}, cands, [], cfg, 3)

    body = captured["body"]
    assert body["model"] == "claude-opus-5-5"
    assert body["fallbacks"] == "default" and "server-side-fallback-2026-07-01" in captured["beta"]
    assert body["output_config"]["format"]["type"] == "json_schema"
    assert sum(1 for b in body["messages"][0]["content"] if b["type"] == "image") == 6
    # violent pick dropped for GTA (violence_safe_hook), the other kept and clamped
    assert len(out) == 1 and out[0]["title"] == "This GTA jump was insane"
    assert out[0]["start"] == 20.0 and out[0]["end"] == 41.0
