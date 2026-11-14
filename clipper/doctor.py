"""`clipper doctor`: check a setup and say what's missing, in the order SETUP-WINDOWS.md fixes it.

Each check returns (level, name, detail): level is "ok", "warn" (works, but something is off or
optional is missing) or "fail" (that part of the bot won't run). Reads only; changes nothing.
"""
from __future__ import annotations

import importlib
import os
import shutil
import subprocess
import sys
from pathlib import Path

from .config import ROOT, data_dir, load_accounts, load_creators, load_niches

OK, WARN, FAIL = "ok", "warn", "fail"


def _imports() -> list[tuple[str, str, str]]:
    out = []
    for mod, why, required in [
        ("yaml", "config files", True), ("numpy", "audio analysis", True), ("yt_dlp", "downloads", True),
        ("googleapiclient", "YouTube API", True), ("google_auth_oauthlib", "YouTube login", True),
        ("anthropic", "Claude picks, titles and edits", True), ("PIL", "emoji pop-ups", False),
        ("whisper", "captions when a source has none", False),
    ]:
        try:
            importlib.import_module(mod)
            out.append((OK, f"package {mod}", why))
        except Exception as e:  # ImportError, or a DLL blocked by Windows App Control
            msg = f"{why}: {type(e).__name__}: {e}"[:200]
            if "Application Control" in str(e):
                msg += " (Windows blocked a DLL: see Troubleshooting in SETUP-WINDOWS.md)"
            out.append((FAIL if required else WARN, f"package {mod}", msg))
    return out


def _windows_font(name: str) -> bool:
    dirs = [Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts",
            Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "Windows" / "Fonts"]
    return any(p.name.lower().startswith(name.lower()) for d in dirs if d.is_dir() for p in d.iterdir())


def checks() -> list[tuple[str, str, str]]:
    out: list[tuple[str, str, str]] = []
    v = sys.version_info
    out.append((OK if v >= (3, 12) else FAIL, "python", f"{v.major}.{v.minor}.{v.micro} (need 3.12+)"))
    for tool in ("ffmpeg", "ffprobe"):
        out.append((OK if shutil.which(tool) else FAIL, tool, shutil.which(tool) or "not on PATH: winget install Gyan.FFmpeg"))
    out += _imports()

    env = {k: bool(os.environ.get(k)) for k in ("YOUTUBE_API_KEY", "ANTHROPIC_API_KEY")}
    out.append((OK if (ROOT / ".env").exists() else FAIL, ".env", "copy .env.example to .env"
                if not (ROOT / ".env").exists() else "found"))
    out.append((OK if env["YOUTUBE_API_KEY"] else FAIL, "YOUTUBE_API_KEY", "set" if env["YOUTUBE_API_KEY"] else "missing in .env (Part 4)"))
    out.append((OK if env["ANTHROPIC_API_KEY"] else WARN, "ANTHROPIC_API_KEY",
                "set" if env["ANTHROPIC_API_KEY"] else "missing: clips fall back to basic picks, no edits (Part 6)"))

    if not (ROOT / "config" / "accounts.yaml").exists():
        out.append((FAIL, "config/accounts.yaml", "copy config/accounts.example.yaml (Part 2)"))
    else:
        for niche, accts in (load_accounts() or {}).items():
            yt, ig = (accts or {}).get("youtube") or {}, (accts or {}).get("instagram") or {}
            if yt.get("enabled"):
                tok = ROOT / yt.get("token_file", "")
                cs = ROOT / yt.get("oauth_client_secret", "")
                lvl = OK if tok.is_file() and cs.is_file() else FAIL
                out.append((lvl, f"youtube {niche}", f"privacy {yt.get('privacy')}" if lvl == OK else
                            f"run: python -m clipper auth-youtube --niche {niche}" if cs.is_file() else
                            f"missing {yt.get('oauth_client_secret')} (Part 4)"))
            else:
                out.append((WARN, f"youtube {niche}", "not enabled in accounts.yaml"))
            if ig.get("enabled"):
                tok = ROOT / ig.get("access_token_file", "")
                lvl = OK if tok.is_file() and ig.get("ig_user_id") and (ig.get("gcs_bucket") or ig.get("public_base_url")) else FAIL
                out.append((lvl, f"instagram {niche}", "ready" if lvl == OK else "needs token file, ig_user_id and gcs_bucket (Part 5)"))

    creators, _ = load_creators()
    joined = [k for k, c in creators.items() if c.get("joined")]
    out.append((OK if joined else WARN, "campaigns joined", ", ".join(joined) if joined else
                "none in rights/joined.yaml: streams clips need a joined campaign (Part 7)"))

    from . import edit

    for niche, cfg in load_niches().items():
        if cfg.get("music"):
            n_yt, n_all = len(edit.music_files("youtube", niche)), len(edit.music_files("instagram", niche))
            out.append((OK if n_yt else WARN, f"music {niche}", f"{n_yt} tracks for YouTube, {n_all} for Instagram"
                        if n_yt else f"music is on but data/assets/music/youtube/{niche} is empty (Part 8)"))
    n_sfx = len(edit.sfx_library())
    out.append((OK if n_sfx else WARN, "sound effects", f"{n_sfx} in data/assets/sfx" if n_sfx else "none yet (Part 8)"))
    out.append((OK if _windows_font("Inter") else WARN, "Inter font", "installed" if _windows_font("Inter")
                else "not installed: captions fall back to Arial (Part 1)"))
    out.append((OK if _windows_font("seguiemj") else WARN, "emoji font", "Segoe UI Emoji" if _windows_font("seguiemj")
                else "not found: emoji pop-ups are skipped"))

    if os.name == "nt":
        missing = []
        for name in ("Daily winners research", "Daily clip making", "Daily analytics check"):
            r = subprocess.run(["schtasks", "/Query", "/TN", f"\\Clipper\\{name}"], capture_output=True)
            if r.returncode != 0:
                missing.append(name)
        out.append((OK if not missing else WARN, "scheduled jobs", "all 3 installed" if not missing else
                    f"missing {', '.join(missing)}: run scripts\\install-schedule.ps1 (Part 9)"))
    data_dir()
    return out


def report() -> tuple[str, bool]:
    rows = checks()
    mark = {OK: "OK  ", WARN: "WARN", FAIL: "FAIL"}
    width = max(len(n) for _, n, _ in rows)
    lines = [f"[{mark[lvl]}] {name.ljust(width)}  {detail}" for lvl, name, detail in rows]
    fails = sum(1 for lvl, _, _ in rows if lvl == FAIL)
    warns = sum(1 for lvl, _, _ in rows if lvl == WARN)
    lines.append("")
    lines.append("Ready to run." if not fails else f"{fails} problem(s) to fix before the bot can run.")
    if warns:
        lines.append(f"{warns} warning(s): optional parts or things to check.")
    return "\n".join(lines), fails == 0
