"""Orchestration: fetch -> mine -> render -> QA -> (approve) -> publish."""
from __future__ import annotations

import json
import traceback
from pathlib import Path

from . import db, fetch, highlights, qa, render
from .config import load_accounts, niche as get_niche


def _cfg(niche_name: str) -> dict:
    cfg = get_niche(niche_name)
    cfg["_name"] = niche_name
    return cfg


def describe(src: dict, pick: dict, cfg: dict) -> str:
    parts = [pick.get("description", "").strip()]
    basis = src.get("rights_basis") or ""
    if basis.startswith("creativeCommon"):
        parts.append(f"Footage: {src.get('channel_title')} — licensed CC BY: {src.get('url')}")
    elif basis.startswith("permission"):
        parts.append(f"Footage: {src.get('channel_title')} (used with permission): {src.get('url')}")
    parts.append(" ".join(cfg.get("hashtags", [])))
    return "\n\n".join(p for p in parts if p)


def fetch_pending(conn, niche_name: str, limit: int = 3, yt=None) -> list[str]:
    done = []
    rows = conn.execute(
        "SELECT * FROM sources WHERE niche=? AND status='discovered' ORDER BY views DESC LIMIT ?",
        (niche_name, limit)).fetchall()
    for row in rows:
        try:
            fetch.fetch_youtube(conn, row, yt=yt)
            done.append(row["id"])
        except Exception as e:  # keep going; one bad source shouldn't stop the run
            db.update(conn, "sources", row["id"], status="failed", reject_reason=f"fetch: {e}"[:500])
    return done


def mine_and_render(conn, niche_name: str, limit: int = 3) -> list[int]:
    cfg = _cfg(niche_name)
    made = []
    rows = conn.execute("SELECT * FROM sources WHERE niche=? AND status='fetched' LIMIT ?",
                        (niche_name, limit)).fetchall()
    for row in rows:
        src = dict(row)
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
            try:
                path = render.render(src, pick, cfg)
                clip = {**dict(conn.execute("SELECT * FROM clips WHERE id=?", (clip_id,)).fetchone()),
                        "path": str(path)}
                ok, problems = qa.check(clip, src, cfg)
                db.update(conn, "clips", clip_id, path=str(path), status="rendered" if ok else "qa_failed",
                          qa_report=json.dumps(problems))
                made.append(clip_id)
            except Exception as e:
                db.update(conn, "clips", clip_id, status="qa_failed", qa_report=json.dumps([f"render: {e}"]))
                traceback.print_exc()
        db.update(conn, "sources", src["id"], status="mined")
    return made


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
    accts = load_accounts().get(niche_name, {})
    cap = cfg.get("daily_cap_per_account", 3)
    results = []
    clips = conn.execute("SELECT * FROM clips WHERE niche=? AND status='approved' ORDER BY score DESC",
                         (niche_name,)).fetchall()
    for clip in clips[: limit or len(clips)]:
        tags = cfg.get("hashtags", [])
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
                    r = publish_instagram.publish(acct, Path(clip["path"]), caption)
                conn.execute("INSERT INTO posts (clip_id, platform, account, remote_id, url, status, posted_at) "
                             "VALUES (?,?,?,?,?,'published',?)",
                             (clip["id"], platform, niche_name, r["remote_id"], r["url"], db.now()))
                conn.commit()
                results.append({"clip": clip["id"], "platform": platform, "status": "published", "url": r["url"]})
            except Exception as e:
                results.append({"clip": clip["id"], "platform": platform, "status": f"failed: {e}"})
        posted = conn.execute("SELECT COUNT(*) FROM posts WHERE clip_id=? AND status='published'",
                              (clip["id"],)).fetchone()[0]
        if posted:
            db.update(conn, "clips", clip["id"], status="published")
    return results
