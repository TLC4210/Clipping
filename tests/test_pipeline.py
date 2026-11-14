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

    # approve + dry-run publish (no accounts configured -> nothing to do; ignore the real accounts.yaml)
    assert pipeline.approve(conn, all_passing=True, niche_name="gta") == len(passing)
    pipeline.load_accounts = lambda: {}
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
    assert {k: stats[k] for k in ("found", "new_ok", "rejected")} == {"found": 2, "new_ok": 1, "rejected": 1}
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


CREATORS = {
    "lacy": {"name": "Lacy", "niches": ["streams"], "youtube": {"channel_id": "UClacy"}, "status": "active",
             "joined": True, "valid_until": "2099-01-01", "source": {"any_date": True},
             "focus": "Lacy main focus", "caption_must_include": ["Lacy", "#Lacy"], "auto_publish": True,
             "campaign": {"urls": ["https://contentrewards.com/c/campaigns/x"]}},
    "kai": {"name": "Kai", "niches": ["gta", "streams"], "youtube": {"channel_id": "UCkai"}, "status": "active",
            "joined": True, "valid_until": "2099-01-01",
            "source": {"published_after": "2026-10-21", "published_before": "2026-11-01"}},
    "notjoined": {"name": "X", "niches": ["streams"], "youtube": {"channel_id": "UCx"}, "status": "active",
                  "joined": False, "valid_until": "2099-01-01"},
}
BLOCKED = [{"name": "The Shawn Ryan Show", "reason": "no permission"}]


def test_creator_allowlist_gate(env, monkeypatch):
    from clipper import rights
    from clipper.config import niche

    monkeypatch.setattr(rights, "load_creators", lambda: (CREATORS, BLOCKED))
    streams = {**niche("streams"), "_name": "streams"}
    gta = {**niche("gta"), "_name": "gta"}

    def vid(ch, pub="2026-11-01T00:00:00Z", title="stream", license="youtube", chtitle="Some"):
        return {"snippet": {"title": title, "description": "", "channelId": ch, "channelTitle": chtitle,
                            "publishedAt": pub, "liveBroadcastContent": "none"}, "status": {"license": license}}

    assert rights.check(vid("UClacy"), streams) == (True, "campaign:lacy")
    assert not rights.check(vid("UClacy"), gta)[0]                                   # wrong niche
    assert not rights.check(vid("UCx"), streams)[0]                                  # not joined
    assert rights.check(vid("UCkai", pub="2026-10-25T00:00:00Z"), gta)[0]            # inside window
    assert not rights.check(vid("UCkai", pub="2026-11-05T00:00:00Z"), gta)[0]        # outside window
    assert not rights.check(vid("UCrandom"), streams)[0]                             # unknown, not CC
    assert not rights.check(vid("UCsrs", license="creativeCommon", chtitle="The Shawn Ryan Show"), gta)[0]


def test_creator_discovery_and_caption_rules(env, monkeypatch):
    from clipper import db, discover, pipeline, qa, rights
    import clipper.pipeline as pl

    monkeypatch.setattr(rights, "load_creators", lambda: (CREATORS, BLOCKED))
    monkeypatch.setattr(discover, "load_creators", lambda: (CREATORS, BLOCKED))
    monkeypatch.setattr(pl, "load_creators", lambda: (CREATORS, BLOCKED))

    class Req:
        def __init__(self, d): self.d = d
        def execute(self): return self.d

    class YT:
        def channels(self):
            class C:
                def list(self, **kw):
                    assert "UClacy" in kw["id"]
                    return Req({"items": [{"contentDetails": {"relatedPlaylists": {"uploads": "UUlacy"}}}]})
            return C()

        def playlistItems(self):
            class P:
                def list(self, **kw):
                    return Req({"items": [{"contentDetails": {"videoId": "lacyvod"}}]})
            return P()

        def videos(self):
            class V:
                def list(self, **kw):
                    return Req({"items": [{"id": "lacyvod", "snippet": {
                        "title": "lacy stream", "description": "", "channelId": "UClacy", "channelTitle": "Lacy",
                        "publishedAt": "2026-11-10T00:00:00Z", "liveBroadcastContent": "none"},
                        "status": {"license": "youtube"}, "contentDetails": {"duration": "PT4H10M"},
                        "statistics": {"viewCount": "10"}}]})
            return V()

    conn = db.connect()
    stats = discover.run("streams", conn, yt=YT())
    assert stats["new_ok"] == 1
    src = dict(conn.execute("SELECT * FROM sources").fetchone())
    assert src["rights_basis"] == "campaign:lacy" and json.loads(src["meta"])["creator"] == "lacy"

    cfg = pipeline.cfg_for_source("streams", src)
    assert cfg["focus"] == "Lacy main focus"
    desc = pipeline.describe(src, {"description": "He lost it."}, cfg)
    assert "#Lacy" in desc and src["url"] in desc


def test_title_fit_and_language_filter(env):
    from clipper import discover, highlights

    long = "This GTA heist went completely wrong in nine seconds and nobody saw it coming"
    t = highlights.fit_title(long)
    assert len(t) <= 60 and long.startswith(t) and not t.endswith(" ")
    assert highlights.fit_title("Short title") == "Short title"

    def v(title, audio=None):
        sn = {"title": title}
        if audio:
            sn["defaultAudioLanguage"] = audio
        return {"snippet": sn}

    assert discover.language_ok(v("GTA 5 funny moments", "en-US"), ["en"])[0]
    assert discover.language_ok(v("GTA 5 funny moments"), ["en"])[0]          # unset audio passes
    assert not discover.language_ok(v("MICHAEL'S FINAL FIGHT", "hi"), ["en"])[0]
    assert not discover.language_ok(v("जीटीए 5 मज़ेदार पल"), ["en"])[0]       # non-Latin title
    assert discover.language_ok(v("anything", "hi"), [])[0]                   # [] = any language


def test_verify_rules_and_range_merge(env):
    from clipper import highlights, media

    good = {"requirement_frames": 6, "one_continuous_moment": True, "matches_title_and_hook": True, "notes": "ok"}
    assert highlights.judge_verify(good, has_focus=True)[0]
    # Creator only in the last frames (the "Dad drives the Porsche" failure)
    assert not highlights.judge_verify({**good, "requirement_frames": 2}, has_focus=True)[0]
    assert highlights.judge_verify({**good, "requirement_frames": 2}, has_focus=False)[0]
    # Jumps to an unrelated scene (the pull-ups -> whiteboard failure)
    assert not highlights.judge_verify({**good, "one_continuous_moment": False}, has_focus=False)[0]
    assert not highlights.judge_verify({**good, "matches_title_and_hook": False}, has_focus=False)[0]

    assert media._merge_ranges([(50, 80), (-3, 20), (15, 30), (79, 90)]) == [(0.0, 30), (50, 90)]


def test_winner_moment_locator(env):
    from clipper import winners

    def words(text, t0, step=0.4):
        return [{"start": t0 + i * step, "end": t0 + i * step + 0.3, "text": w} for i, w in enumerate(text.split())]

    filler = words(" ".join(f"filler{i} talk{i}" for i in range(400)), 0, 0.5)
    moment = "bro paid twelve thousand dollars for the food in japan and the waiter could not believe it at all"
    source = filler + words(moment, 600.0)
    short = words("he paid twelve thousand dollars for the food in japan and the waiter could not believe it", 0)
    start, end, score = winners.locate(short, source, 20)
    assert 595 <= start <= 602 and end > start and score >= 0.5
    assert winners.locate(words("totally unrelated words about minecraft blocks and creepers today", 0), source, 20) is None

    src = [{"id": "yt:a", "title": "CORE $1 VS $10,000 RESTAURANTS IN JAPAN"}, {"id": "yt:b", "title": "CORE FAMILY FEUD"}]
    assert winners.match_source({"title": "Lacy tries the $10,000 restaurant in Japan"}, src, {"lacy"})["id"] == "yt:a"


def test_winning_titles_reach_picker(env):
    from clipper import highlights, winners

    winners.winners_path().write_text(json.dumps({
        "_titles": {"lacy": [{"title": "Lacy Bought A Porsche 😭", "views": 900_000},
                             {"title": "Lacy Got Banned Again", "views": 300_000}]},
        "yt:a": [{"short_id": "s1", "short_title": "Lacy Paid $10K For Food In Japan 💀", "views": 2_000_000,
                  "creator": "lacy", "start": 10, "end": 40}],
    }), encoding="utf-8")
    assert [t for t, _ in winners.top_titles("lacy")] == [
        "Lacy Paid $10K For Food In Japan 💀", "Lacy Bought A Porsche 😭", "Lacy Got Banned Again"]
    assert winners.top_titles("jason") == []
    assert "Lacy Bought A Porsche" in highlights._winning_titles_text("core")  # falls back to the crew's
    crew = winners.crew_names({"core": {"name": "CORE", "member_hashtags": {"Lacy": "#Lacy", "Ron": "#StableRonaldo"}},
                               "clix": {"name": "Clix (Cody Conrod)"}})
    assert crew == {"Lacy", "Ron", "Clix"}
    assert not winners.names_crew("Ranking TOP 7 DOG TAIL Core Moments!! 🐶", crew)
    assert not winners.names_crew("Jynxzi Finds Out Yeat Was Max Rank", crew)
    assert winners.names_crew("Ron Knew Clix Was Lying 😭", crew)
    assert winners.clean_title("Lacy & Clix Help Find a Teen 😳 | DoubleCoverage #doublecoverage") == "Lacy & Clix Help Find a Teen 😳"
    text = highlights._winning_titles_text("lacy")
    assert "Lacy Bought A Porsche" in text and "900,000 views" in text
    assert highlights._winning_titles_text(None) == ""


def test_analytics_check_and_report(env):
    from clipper import analytics, db

    class Q:
        def __init__(self, r): self.r = r
        def execute(self): return self.r

    def make_yt(views):
        class YT:
            def channels(self): return self
            def playlistItems(self): return self
            def videos(self): return self

            def list(self, **kw):
                if kw.get("mine"):
                    return Q({"items": [{"id": "UC1", "snippet": {"title": "Clipped Live"},
                                         "statistics": {"subscriberCount": "10", "viewCount": str(views), "videoCount": "1"},
                                         "contentDetails": {"relatedPlaylists": {"uploads": "UU1"}}}]})
                if "playlistId" in kw:
                    return Q({"items": [{"contentDetails": {"videoId": "v1"}}]})
                return Q({"items": [{"id": "v1", "snippet": {"title": "Lacy Got Hit With A Bill", "publishedAt": "2026-11-13T10:00:00Z"},
                                     "statistics": {"viewCount": str(views), "likeCount": "5", "commentCount": "1"},
                                     "status": {"privacyStatus": "public", "uploadStatus": "processed"},
                                     "contentDetails": {"regionRestriction": {"blocked": ["US", "CA"]}}}]})
        return YT()

    conn = db.connect()
    first = analytics.check(conn, "streams", {}, yt=make_yt(100))
    assert first["views_change"] is None and first["videos_list"][0]["flags"] == ["blocked in 2 countries incl. US"]
    second = analytics.check(conn, "streams", {}, yt=make_yt(250))
    assert second["views_change"] == 150 and second["videos_list"][0]["views_change"] == 150
    md = analytics.report_md([second, {"niche": "gta", "error": "RuntimeError: no token"}], "2026-11-14")
    assert "250 (+150)" in md and "Needs a look" in md and "gta: could not check" in md


def test_core_member_hashtags(env):
    from clipper import pipeline

    cfg = {"caption_must_include": ["CORE", "#CORE"], "hashtags": ["#stream", "#shorts"],
           "member_hashtags": {"Lacy": "#Lacy", "Ron": "#StableRonaldo", "Stable Ronaldo": "#StableRonaldo",
                               "Adapt": "#Adapt", "Jason": "#JasonTheWeen"}}
    pick = {"title": "Lacy Tried Japanese McDonald's Nuggets With Adapt", "hook": "Nugget taste test",
            "description": "Stable Ronaldo hypes the soda. Ron loses it."}
    desc = pipeline.describe({"rights_basis": "campaign:core", "url": "u", "channel_title": "CORE"}, pick, cfg)
    last = desc.splitlines()[-1]
    assert last == "#CORE #Lacy #StableRonaldo #Adapt #stream #shorts"
    assert "Ronaldo" not in pipeline.member_tags({"title": "Ronny and Lacy"}, cfg) and pipeline.member_tags(
        {"title": "Ronny and Lacy"}, cfg) == ["#Lacy"]


def test_twitch_discover_rules(env, monkeypatch):
    from clipper import db, twitch

    creators = {"jason": {"name": "JasonTheWeen", "niches": ["streams"], "twitch": "jasontheween",
                          "youtube": {"channel_id": "UCjason"}, "basis": "campaign", "status": "active",
                          "joined": True, "valid_until": "2099-01-01", "source": {"any_date": True}}}
    monkeypatch.setattr(twitch, "load_creators", lambda: (creators, []))
    monkeypatch.setattr(twitch.rights, "load_creators", lambda: (creators, []), raising=False)
    clips = [
        {"id": "1", "url": "https://twitch.tv/c/1", "title": "HE TRYNA IGNORE IT", "view_count": 9796, "duration": 16, "timestamp": 1794200686},
        {"id": "2", "url": "https://twitch.tv/c/2", "title": "keep him", "view_count": 4047, "duration": 7, "timestamp": 1794103403},
        {"id": "3", "url": "https://twitch.tv/c/3", "title": "low views", "view_count": 120, "duration": 30, "timestamp": 1794103403},
    ]
    monkeypatch.setattr(twitch, "top_clips", lambda h, period, limit: clips)
    conn = db.connect()
    stats = twitch.discover(conn, "streams")
    assert stats == {"found": 3, "new_ok": 1, "skipped": 2}   # 7 s clip and 120-view clip skipped
    row = dict(conn.execute("SELECT * FROM sources WHERE id='tw:1'").fetchone())
    assert row["rights_basis"] == "campaign:jason" and row["channel_id"] == "UCjason" and row["status"] == "discovered"


def test_caption_censor(env):
    from clipper.render import censor

    assert censor("FUCKING CHAD yo") == "F****** CHAD yo"
    assert censor("shit like that") == "s*** like that"
    assert censor("class assessment Dickens") == "class assessment Dickens"
    assert censor("pass the classic") == "pass the classic"


def test_long_source_fetches_only_candidate_sections(env, monkeypatch):
    """Stream VODs: audio + captions first, then only the candidate windows as video."""
    from clipper import fetch, highlights, media, pipeline, render
    from clipper.config import data_dir

    assert fetch.is_long({"duration_s": 3 * 3600}) and not fetch.is_long({"duration_s": 600})
    assert fetch._ydl_opts(Path("."), audio_only=True)["format"] == fetch.AUDIO_FORMAT

    full = env / "full.mp4"
    make_video(full, 90)
    audio = data_dir("sources", "gta") / "abc123.m4a"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(full), "-vn", "-c:a", "copy", str(audio)], check=True)
    asked = []

    def fake_sections(src, ranges):  # what yt-dlp does with download_ranges + exact cuts
        asked.extend(ranges)
        segs = []
        for a, b in media._merge_ranges([(round(a), round(b)) for a, b in ranges]):
            p = audio.parent / f"abc123.sec{int(a)}.mp4"
            subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", str(a), "-t", str(b - a), "-i", str(full),
                            "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", str(p)], check=True)
            segs.append({"start": float(a), "end": float(a) + media.probe(p)["duration"], "path": str(p)})
        return segs

    monkeypatch.setattr(fetch, "fetch_sections", fake_sections)
    monkeypatch.setenv("CLIPPER_WHISPER", "0")
    src = {"id": "yt:abc123", "niche": "gta", "local_path": str(audio), "captions_path": None,
           "title": "long stream", "rights_basis": "owned", "url": "https://youtu.be/abc123"}
    cfg = pipeline._cfg("gta")
    picks = highlights.find(src, cfg)
    assert picks and asked
    assert sum(b - a for a, b in media._merge_ranges(asked)) <= 90
    for p in picks:  # every pick lies inside one downloaded section
        assert highlights._covered(src, p["start"], p["end"])
    path, t = media.source_at(src, picks[0]["start"])
    assert path != src["local_path"] and 0 <= t < picks[0]["start"]
    out = render.render(src, picks[0], cfg)
    info = media.probe(out)
    assert (info["width"], info["height"]) == (1080, 1920) and info["has_audio"]
    assert abs(info["duration"] - (picks[0]["end"] - picks[0]["start"])) < 1.0


def test_editor_timeline_layout_and_effects(env):
    """Joined pieces + jump cut + facecam stack + punch-in + emoji + sfx + music all render to a valid Short."""
    from clipper import edit, highlights, media, render
    from clipper.config import data_dir

    tl = edit.Timeline([(10, 20), (50, 55)])
    assert tl.duration == 15 and tl.to_out(52) == 12 and tl.to_out(30) is None and tl.to_src(12) == 52
    assert [w["start"] for w in tl.words([{"start": 11, "end": 11.5, "text": "a"},
                                          {"start": 30, "end": 31, "text": "b"}])] == [1]

    # 40 s source: talking noise with a dead-quiet stretch at 14-17 s
    src_path = data_dir("sources", "streams") / "cam.mp4"
    subprocess.run([
        "ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc2=size=1280x720:rate=30:duration=40",
        "-f", "lavfi", "-i", "anoisesrc=d=40:c=pink:r=48000:a=0.5",
        "-filter_complex", "[1:a]volume='if(between(t,14,17),0.001,1)':eval=frame[a]",
        "-map", "0:v", "-map", "[a]", "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", str(src_path)],
        check=True)
    src = {"id": "tw:cam", "niche": "streams", "local_path": str(src_path), "channel_title": "Lacy",
           "rights_basis": "campaign:lacy"}
    cut = edit.jump_ranges(src, [(5.0, 25.0)], [], min_total=10)
    assert len(cut) == 2 and 14 <= cut[0][1] <= 14.5 and 16.5 <= cut[1][0] <= 17, cut
    assert edit.jump_ranges(src, [(5.0, 25.0)], [], min_total=19) == [(5.0, 25.0)]  # never below the minimum

    cfg = {"clip_min_s": 12, "clip_max_s": 60, "layout": "facecam_stack", "music": True, "hook_seconds": 2}
    cands = [{"start": 4.0, "end": 26.0}, {"start": 30.0, "end": 38.0}]
    ranges = highlights.edit_ranges((5.0, 25.0), [{"candidate": 1, "start": 31.0, "end": 36.0}], cands, cfg)
    assert ranges == [(5.0, 25.0), (31.0, 36.0)]
    assert highlights.edit_ranges((5.0, 25.0), [{"candidate": 1, "start": 31.0, "end": 36.0}], cands,
                                  {**cfg, "clip_max_s": 22}) == [(5.0, 25.0), (31.0, 33.0)]

    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "sine=f=900:d=0.4",
                    str(data_dir("assets", "sfx", "youtube") / "ding.wav")], check=True)
    assert "ding" in edit.sfx_library("youtube") and "ding" not in edit.sfx_library("instagram")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "sine=f=220:d=5",
                    str(data_dir("assets", "music", "youtube", "streams") / "bed.mp3")], check=True)
    assert edit.music_files("youtube", "streams") and not edit.music_files("youtube", "gta")
    assert edit.music_files("instagram", "streams") == []  # YouTube-only licence
    pick = {"candidate": 0, "zooms": [{"t": 8.0, "dur": 1.0}, {"t": 99.0, "dur": 1.0}],
            "emojis": [{"t": 20.0, "emoji": "\U0001f62d"}, {"t": 21.0, "emoji": "lol"}],
            "sfx": [{"t": 20.0, "name": "ding"}, {"t": 21.0, "name": "airhorn"}]}
    cues = highlights.edit_cues(pick, ranges)
    assert len(cues["zooms"]) == 1 and len(cues["emojis"]) == 1 and [x["name"] for x in cues["sfx"]] == ["ding"]
    assert highlights.facecam_box({"has_facecam": True, "x": 0.7, "y": 0.05, "w": 0.25, "h": 0.25, "content_x": 0.4})
    assert highlights.facecam_box({"has_facecam": True, "x": 0, "y": 0, "w": 1, "h": 1, "content_x": 0.5}) is None

    src["facecam"] = {"x": 0.7, "y": 0.05, "w": 0.25, "h": 0.25, "content_x": 0.4}
    words = [{"start": 6.0 + i, "end": 6.6 + i, "text": f"w{i}"} for i in range(6)]
    full = {**pick, **cues, "start": 5.0, "end": 36.0, "ranges": cut + [(31.0, 36.0)], "hook": "Lacy did it",
            "words": words}
    out = render.render(src, full, cfg)
    info = media.probe(out)
    assert (info["width"], info["height"]) == (1080, 1920) and info["has_audio"]
    expected = sum(b - a for a, b in full["ranges"])
    assert abs(info["duration"] - expected) < 0.5, (info["duration"], expected)
    assert not out.with_name(out.stem + ".master.mp4").exists()
    assert edit.emoji_png("\U0001f62d").exists()
    ig = render.render(src, full, cfg, out_path=out.with_name("ig.mp4"), platform="instagram")  # no music pool
    assert media.probe(ig)["has_audio"]


def test_music_report(env, monkeypatch):
    from clipper import music

    assert music.song_credits("Crazy GTA moment\nSong: Metro Boomin - Superhero\nSubscribe for more!\n🎵 Phonk beat") == [
        "Song: Metro Boomin - Superhero", "🎵 Phonk beat"]

    class Q:
        def __init__(self, d): self.d = d
        def execute(self): return self.d

    class Videos:
        def list(self, **kw):
            if kw.get("chart"):
                return Q({"items": [{"snippet": {"title": "Hit Song", "channelTitle": "Star"},
                                     "statistics": {"viewCount": "900"}}]})
            return Q({"items": [{"id": "a", "snippet": {"title": "gta edit", "description": "song: Phonk X"},
                                 "statistics": {"viewCount": "5000"}}]})

    class Search:
        def list(self, **kw): return Q({"items": [{"id": {"videoId": "a"}}]})

    class YT:
        def videos(self): return Videos()
        def search(self): return Search()

    out = music.run(yt=YT())
    text = open(out["report"], encoding="utf-8").read()
    assert "Hit Song" in text and "song: Phonk X (5,000 views)" in text and out["library"]["youtube"] == 0
