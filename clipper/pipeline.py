"""Orchestration: fetch -> mine -> render -> QA -> (approve) -> publish."""
from __future__ import annotations

import json
import traceback
from pathlib import Path

from . import db, fetch, highlights, qa, render
from .config import load_accounts, load_creators, niche as get_niche


def _cfg(niche_name: str) -> dict:
    cfg = get_niche(niche_name)
    cfg["_name"] = niche_name
    return cfg


def creator_of(src: dict) -> tuple[str | None, dict]:
    """The allowlisted creator (rights/creators.yaml) a source came from, if any."""
    try:
        key = (json.loads(src.get("meta") or "{}") or {}).get("creator")
    except (TypeError, ValueError):
        key = None
    if not key:
        return None, {}
    return key, load_creators()[0].get(key, {})


def cfg_for_source(niche_name: str, src: dict) -> dict:
    """Niche config plus the creator campaign's rules (focus, caption, source offset)."""
    cfg = _cfg(niche_name)
    key, c = creator_of(src)
    if c:
        cfg["focus"] = c.get("focus")
        cfg["caption_must_include"] = list(c.get("caption_must_include") or [])
        cfg["min_start_s"] = float((c.get("source") or {}).get("start_offset_s") or 0)
        cfg["creator_key"] = key
        cfg["member_hashtags"] = dict(c.get("member_hashtags") or {})
    return cfg


def member_tags(pick: dict, cfg: dict) -> list[str]:
    """Hashtags for each crew member named in the pick's title/hook/description (CORE rule)."""
    import re

    text = " ".join(str(pick.get(k) or "") for k in ("title", "hook", "description"))
    tags = []
    for name, tag in (cfg.get("member_hashtags") or {}).items():
        if re.search(rf"\b{re.escape(name)}\b", text, re.I) and tag not in tags:
            tags.append(tag)
    return tags


def describe(src: dict, pick: dict, cfg: dict) -> str:
    parts = [pick.get("description", "").strip()]
    basis = src.get("rights_basis") or ""
    if basis.startswith("creativeCommon"):
        parts.append(f"Footage: {src.get('channel_title')} — licensed CC BY: {src.get('url')}")
    elif basis.startswith("permission"):
        parts.append(f"Footage: {src.get('channel_title')} (used with permission): {src.get('url')}")
    elif basis.startswith("campaign:"):
        parts.append(f"Footage: {src.get('channel_title')} — {src.get('url')}")
    must = [t for t in cfg.get("caption_must_include", []) if t.lower() not in " ".join(parts).lower()]
    tags = must + [t for t in member_tags(pick, cfg) if t not in must] + list(cfg.get("hashtags", []))
    parts.append(" ".join(dict.fromkeys(tags)))
    return "\n\n".join(p for p in parts if p)


def fetch_pending(conn, niche_name: str, limit: int = 3, yt=None) -> list[str]:
    done = []
    from . import winners

    proven = winners.load()
    rows = conn.execute("SELECT * FROM sources WHERE niche=? AND status='discovered' ORDER BY views DESC",
                        (niche_name,)).fetchall()
    # Sources with moments that already went viral for competitors come first (most proven views first).
    rows = sorted(rows, key=lambda r: -sum(h["views"] for h in proven.get(r["id"], []) if "start" in h))
    yt_blocked = False
    for row in rows:
        if len(done) >= limit:
            break
        if yt_blocked and row["id"].startswith("yt:"):
            continue
        try:
            if row["id"].startswith("tw:"):
                from . import twitch

                twitch.fetch(conn, row)
            else:
                fetch.fetch_youtube(conn, row, yt=yt)
            done.append(row["id"])
        except Exception as e:  # keep going; one bad source shouldn't stop the run
            if "not a bot" in str(e):
                # YouTube's temporary bot check on this connection: not the source's fault. Keep it queued,
                # skip YouTube for the rest of this run and fill the slots from other sources (Twitch).
                yt_blocked = True
                print(f"YouTube bot check; skipping YouTube downloads this run ({row['id']} stays queued)")
                continue
            db.update(conn, "sources", row["id"], status="failed", reject_reason=f"fetch: {e}"[:500])
    return done


def mine_and_render(conn, niche_name: str, limit: int = 3) -> list[int]:
    made = []
    rows = conn.execute("SELECT * FROM sources WHERE niche=? AND status='fetched' LIMIT ?",
                        (niche_name, limit)).fetchall()
    for row in rows:
        src = dict(row)
        cfg = cfg_for_source(niche_name, src)
        try:
            picks = highlights.find(src, cfg)
        except Exception as e:
            db.update(conn, "sources", src["id"], status="failed", reject_reason=f"mine: {e}"[:500])
            traceback.print_exc()
            continue
        for pick in picks:
            desc = describe(src, pick, cfg)
            cur = conn.execute(
                "INSERT INTO clips (source_id, niche, start_s, end_s, score, hook, title, description, reason, "
                "status, created_at) VALUES (?,?,?,?,?,?,?,?,?, 'planned', ?)",
                (src["id"], niche_name, pick["start"], pick["end"], pick["score"], pick["hook"], pick["title"],
                 desc, pick["reason"], db.now()))
            conn.commit()
            clip_id = cur.lastrowid
            db.update(conn, "clips", clip_id, edit=json.dumps(edit_plan(src, pick)))
            try:
                render_versions(conn, clip_id, src, pick, cfg)
                made.append(clip_id)
            except Exception as e:
                db.update(conn, "clips", clip_id, status="qa_failed", qa_report=json.dumps([f"render: {e}"]))
                traceback.print_exc()
        db.update(conn, "sources", src["id"], status="mined")
        _cleanup(src, cfg)
    return made


def _cleanup(src: dict, cfg: dict) -> None:
    if src["id"][:3] in ("yt:", "tw:") and not cfg.get("keep_sources", False):
        # ~600 MB each; clips are already cut. Glob too: yt-dlp can leave several caption files.
        vid = src["id"].split(":", 1)[1] if src["id"].startswith("yt:") else "tw_" + src["id"].split(":", 1)[1]
        files = {Path(p) for p in (src.get("local_path"), src.get("captions_path")) if p}
        if src.get("local_path"):
            files |= set(Path(src["local_path"]).parent.glob(f"{vid}.*"))
        for p in files:
            p.unlink(missing_ok=True)


def render_versions(conn, clip_id: int, src: dict, pick: dict, cfg: dict) -> tuple[bool, Path]:
    """Render the clip (YouTube version) and, when its music is YouTube-only, an Instagram version.

    Both are QA-checked; the clip passes only if both do.
    """
    from . import edit

    path = render.render(src, pick, cfg, platform="youtube")
    clip = {**dict(conn.execute("SELECT * FROM clips WHERE id=?", (clip_id,)).fetchone()), "path": str(path)}
    ok, problems = qa.check(clip, src, cfg)
    ig_path = None
    n = src.get("niche")
    music_differs = cfg.get("music") and set(edit.music_files("youtube", n)) != set(edit.music_files("instagram", n))
    sfx_differs = any(x["name"].lower() not in edit.sfx_library("instagram") for x in pick.get("sfx") or [])
    if music_differs or sfx_differs:
        ig_path = render.render(src, pick, cfg, out_path=path.with_name(path.stem + ".ig.mp4"), platform="instagram")
        ig_ok, ig_problems = qa.check({**clip, "path": str(ig_path)}, src, cfg)
        ok = ok and ig_ok
        problems += [f"instagram version: {p}" for p in ig_problems]
    db.update(conn, "clips", clip_id, path=str(path), ig_path=str(ig_path) if ig_path else None,
              status="rendered" if ok else "qa_failed", qa_report=json.dumps(problems))
    return ok, path


def edit_plan(src: dict, pick: dict) -> dict:
    keys = ("ranges", "zooms", "emojis", "sfx", "words")
    return {**{k: pick.get(k) for k in keys}, "facecam": src.get("facecam")}


def rerender(conn, clip_ids: list[int]) -> list[dict]:
    """Render clips again from their saved edit plan (after a layout or style change), no new picks.

    Re-downloads the source if it was already deleted (long sources: only the clip's pieces).
    """
    out = []
    cleanup: dict[str, tuple[dict, dict]] = {}  # sources downloaded here: deleted once, after all their clips
    for cid in sorted(clip_ids, key=lambda i: (conn.execute("SELECT source_id FROM clips WHERE id=?", (i,)).fetchone() or [""])[0]):
        clip = conn.execute("SELECT * FROM clips WHERE id=?", (cid,)).fetchone()
        plan = json.loads(clip["edit"] or "null") if clip else None
        if not plan:
            out.append({"clip": cid, "status": "skipped: no saved edit plan"})
            continue
        row = conn.execute("SELECT * FROM sources WHERE id=?", (clip["source_id"],)).fetchone()
        src = dict(row)
        refetched = not (src.get("local_path") and Path(src["local_path"]).exists())
        if refetched:
            status = src["status"]
            db.update(conn, "sources", src["id"], status="discovered")
            row = conn.execute("SELECT * FROM sources WHERE id=?", (src["id"],)).fetchone()
            try:
                if src["id"].startswith("tw:"):
                    from . import twitch

                    twitch.fetch(conn, row)
                else:
                    fetch.fetch_youtube(conn, row)
            finally:
                db.update(conn, "sources", src["id"], status=status)
            src = dict(conn.execute("SELECT * FROM sources WHERE id=?", (src["id"],)).fetchone())
        cfg = cfg_for_source(clip["niche"], src)
        if src["id"].startswith("yt:") and fetch.is_long(src):
            src["segments"] = fetch.fetch_sections(src, [(a - 1, b + 1) for a, b in plan["ranges"]])
        src["facecam"] = plan.get("facecam")
        pick = {**plan, "start": clip["start_s"], "end": clip["end_s"], "hook": clip["hook"]}
        if refetched:
            cleanup[src["id"]] = (src, cfg)
        try:
            ok, path = render_versions(conn, cid, src, pick, cfg)
            out.append({"clip": cid, "status": "rendered" if ok else "qa_failed", "path": str(path)})
        except Exception as e:
            out.append({"clip": cid, "status": f"failed: {e}"[:300]})
    for src, cfg in cleanup.values():
        _cleanup(src, cfg)
    return out


def approve(conn, clip_ids: list[int] | None = None, all_passing: bool = False, niche_name: str | None = None) -> int:
    if all_passing:
        q, args = "SELECT id FROM clips WHERE status='rendered'", []
        if niche_name:
            q += " AND niche=?"
            args.append(niche_name)
        clip_ids = [r[0] for r in conn.execute(q, args)]
    n = 0
    for cid in clip_ids or []:
        row = conn.execute("SELECT status FROM clips WHERE id=?", (cid,)).fetchone()
        if row and row["status"] == "rendered":
            db.update(conn, "clips", cid, status="approved")
            n += 1
    return n


def reject(conn, clip_ids: list[int]) -> None:
    for cid in clip_ids:
        db.update(conn, "clips", cid, status="rejected")


def publish_approved(conn, niche_name: str, live: bool = False, limit: int | None = None) -> list[dict]:
    """Publish approved clips to the niche's YouTube + Instagram accounts (one account per platform)."""
    from . import publish_instagram, publish_youtube

    cfg = _cfg(niche_name)
    creators = load_creators()[0]
    accts = load_accounts().get(niche_name, {})
    cap = cfg.get("daily_cap_per_account", 3)
    results = []
    clips = conn.execute("SELECT * FROM clips WHERE niche=? AND status='approved' ORDER BY score DESC",
                         (niche_name,)).fetchall()
    for clip in clips[: limit or len(clips)]:
        tags = cfg.get("hashtags", [])
        src = dict(conn.execute("SELECT * FROM sources WHERE id=?", (clip["source_id"],)).fetchone())
        ckey, creator = creator_of(src)
        if creator and not creator.get("auto_publish", False):
            results.append({"clip": clip["id"], "status": f"held: {ckey} campaign needs manual steps "
                            "(pre-approval / overlay / rules) — see rights/creators.yaml"})
            continue
        submit = None
        if creator:
            urls = (creator.get("campaign") or {}).get("urls") or []
            submit = {"campaign": ckey, "submit_at": urls[0] if urls else None,
                      "deadline": "within 30 minutes of posting"}
        for platform in ("youtube", "instagram"):
            acct = accts.get(platform) or {}
            if not acct.get("enabled"):
                continue
            if conn.execute("SELECT 1 FROM posts WHERE clip_id=? AND platform=?", (clip["id"], platform)).fetchone():
                continue
            if db.posts_today(conn, platform, niche_name) >= cap:
                results.append({"clip": clip["id"], "platform": platform, "status": "skipped: daily cap"})
                continue
            if not live:
                results.append({"clip": clip["id"], "platform": platform, "status": "dry_run",
                                "title": clip["title"], "file": clip["path"]})
                continue
            try:
                if platform == "youtube":
                    r = publish_youtube.upload(acct, Path(clip["path"]), clip["title"], clip["description"], tags)
                else:
                    caption = f"{clip['title']}\n\n{clip['description']}"
                    r = publish_instagram.publish(acct, Path(clip["ig_path"] or clip["path"]), caption,
                                                  niche=niche_name)
                conn.execute("INSERT INTO posts (clip_id, platform, account, remote_id, url, status, posted_at) "
                             "VALUES (?,?,?,?,?,'published',?)",
                             (clip["id"], platform, niche_name, r["remote_id"], r["url"], db.now()))
                conn.commit()
                results.append({"clip": clip["id"], "platform": platform, "status": "published", "url": r["url"],
                                **({"SUBMIT_NOW": submit} if submit else {})})
            except Exception as e:
                results.append({"clip": clip["id"], "platform": platform, "status": f"failed: {e}"})
        posted = conn.execute("SELECT COUNT(*) FROM posts WHERE clip_id=? AND status='published'",
                              (clip["id"],)).fetchone()[0]
        if posted:
            db.update(conn, "clips", clip["id"], status="published")
    return results
