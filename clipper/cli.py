"""Command line entry point:  python -m clipper <command> ..."""
from __future__ import annotations

import argparse
import json
import sys

from . import db, discover, fetch, pipeline
from .config import load_accounts, load_dotenv, load_niches


def _print(obj) -> None:
    print(json.dumps(obj, indent=2, default=str))


def cmd_discover(a):
    _print(discover.run(a.niche, a.conn))


def cmd_fetch(a):
    yt = discover.youtube_client() if not a.no_recheck else None
    _print({"fetched": pipeline.fetch_pending(a.conn, a.niche, a.limit, yt=yt)})


def cmd_ingest(a):
    _print({"added": fetch.ingest_inbox(a.conn, a.niche)})


def cmd_make(a):
    _print({"clips": pipeline.mine_and_render(a.conn, a.niche, a.limit)})


def cmd_run(a):
    out = {}
    if not a.skip_discover:
        out["discover"] = discover.run(a.niche, a.conn)
    out["inbox"] = fetch.ingest_inbox(a.conn, a.niche)
    yt = discover.youtube_client() if not a.skip_discover else None
    out["fetched"] = pipeline.fetch_pending(a.conn, a.niche, a.limit, yt=yt)
    out["clips"] = pipeline.mine_and_render(a.conn, a.niche, a.limit + len(out["inbox"]))
    if a.auto_approve:
        out["approved"] = pipeline.approve(a.conn, all_passing=True, niche_name=a.niche)
    if a.publish:
        out["publish"] = pipeline.publish_approved(a.conn, a.niche, live=a.live)
    _print(out)


def cmd_review(a):
    q = "SELECT c.id, c.niche, c.status, c.score, c.start_s, c.end_s, c.hook, c.title, c.path, c.qa_report, " \
        "s.title AS source_title, s.rights_basis FROM clips c JOIN sources s ON s.id = c.source_id"
    args = []
    conds = []
    if a.niche:
        conds.append("c.niche = ?")
        args.append(a.niche)
    if a.status:
        conds.append("c.status = ?")
        args.append(a.status)
    if conds:
        q += " WHERE " + " AND ".join(conds)
    q += " ORDER BY c.id DESC LIMIT ?"
    args.append(a.limit)
    _print([dict(r) for r in a.conn.execute(q, args)])


def cmd_approve(a):
    _print({"approved": pipeline.approve(a.conn, a.ids, all_passing=a.all_passing, niche_name=a.niche)})


def cmd_reject(a):
    pipeline.reject(a.conn, a.ids)
    _print({"rejected": a.ids})


def cmd_publish(a):
    _print(pipeline.publish_approved(a.conn, a.niche, live=a.live, limit=a.limit))


def cmd_auth_youtube(a):
    from . import publish_youtube

    acct = load_accounts()[a.niche]["youtube"]
    print("Authorized:", publish_youtube.authorize(acct))


def cmd_creators(a):
    from datetime import date

    from . import rights
    from .config import load_creators

    creators, blocked = load_creators()
    rows = []
    for key, c in creators.items():
        ok, why = rights.creator_eligible(c, None)
        rows.append({
            "key": key, "niches": c.get("niches"), "status": c.get("status"), "joined": c.get("joined"),
            "valid_until": str(c.get("valid_until")), "auto_publish": c.get("auto_publish"),
            "bot_will_use": ok, "why_not": None if ok else why,
            "campaign": (c.get("campaign") or {}).get("name"), "pay": (c.get("campaign") or {}).get("pay"),
        })
    _print({"today": date.today().isoformat(), "creators": rows, "blocked": [b["name"] for b in blocked]})


def cmd_status(a):
    out = {}
    for t in ("sources", "clips", "posts"):
        out[t] = {r[0]: r[1] for r in a.conn.execute(f"SELECT status, COUNT(*) FROM {t} GROUP BY status")}
    out["niches"] = list(load_niches())
    _print(out)


def main(argv=None):
    load_dotenv()
    p = argparse.ArgumentParser(prog="clipper", description="Automated GTA/Minecraft clipping pipeline")
    sub = p.add_subparsers(dest="cmd", required=True)

    def add(name, fn, niche=True, limit=None):
        sp = sub.add_parser(name)
        if niche:
            sp.add_argument("--niche", required=True)
        if limit is not None:
            sp.add_argument("--limit", type=int, default=limit)
        sp.set_defaults(fn=fn)
        return sp

    add("discover", cmd_discover)
    add("fetch", cmd_fetch, limit=3).add_argument("--no-recheck", action="store_true",
                                                  help="skip live license re-check before download")
    add("ingest", cmd_ingest)
    add("make", cmd_make, limit=3)
    sp = add("run", cmd_run, limit=2)
    sp.add_argument("--skip-discover", action="store_true")
    sp.add_argument("--auto-approve", action="store_true", help="approve every clip that passes QA")
    sp.add_argument("--publish", action="store_true")
    sp.add_argument("--live", action="store_true", help="actually upload (default is dry run)")
    sp = sub.add_parser("review")
    sp.add_argument("--niche")
    sp.add_argument("--status", default="rendered")
    sp.add_argument("--limit", type=int, default=20)
    sp.set_defaults(fn=cmd_review)
    sp = sub.add_parser("approve")
    sp.add_argument("ids", nargs="*", type=int)
    sp.add_argument("--all-passing", action="store_true")
    sp.add_argument("--niche")
    sp.set_defaults(fn=cmd_approve)
    sp = sub.add_parser("reject")
    sp.add_argument("ids", nargs="+", type=int)
    sp.set_defaults(fn=cmd_reject)
    sp = add("publish", cmd_publish, limit=None)
    sp.add_argument("--limit", type=int)
    sp.add_argument("--live", action="store_true", help="actually upload (default is dry run)")
    add("auth-youtube", cmd_auth_youtube)
    add("status", cmd_status, niche=False)
    add("creators", cmd_creators, niche=False)

    a = p.parse_args(argv)
    a.conn = db.connect()
    a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
