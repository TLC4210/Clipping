"""Render a 1080x1920 clip: 9:16 layout, hook text, word-by-word captions, credit line, loudness."""
from __future__ import annotations

import re
from datetime import date
from pathlib import Path

from . import media
from .config import data_dir

W, H = 1080, 1920
FONT = "Inter"


def _ts(t: float) -> str:
    t = max(0.0, t)
    h, rem = divmod(t, 3600)
    m, s = divmod(rem, 60)
    return f"{int(h)}:{int(m):02d}:{s:05.2f}"


def _esc(text: str) -> str:
    return text.replace("\\", "\\\\").replace("{", "(").replace("}", ")").replace("\n", " ")


def build_ass(duration: float, hook: str, words: list[dict], clip_start: float, credit: str | None,
              hook_seconds: float, banner: str | None = None) -> str:
    lines = [
        "[Script Info]", "ScriptType: v4.00+", f"PlayResX: {W}", f"PlayResY: {H}", "WrapStyle: 0",
        "ScaledBorderAndShadow: yes", "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, "
        "Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, "
        "MarginL, MarginR, MarginV, Encoding",
        f"Style: Hook,{FONT},84,&H00FFFFFF,&H00FFFFFF,&H30000000,&H30000000,-1,0,0,0,100,100,0,0,3,18,0,8,60,60,230,1",
        f"Style: Cap,{FONT},78,&H00FFFFFF,&H0000E5FF,&H00000000,&H96000000,-1,0,0,0,100,100,0,0,1,6,2,2,80,80,520,1",
        f"Style: Credit,{FONT},34,&H00FFFFFF,&H00FFFFFF,&H00000000,&H78000000,0,0,0,0,100,100,0,0,1,2,0,2,40,40,90,1",
        f"Style: Banner,{FONT},46,&H0000E5FF,&H00FFFFFF,&H30000000,&H30000000,-1,0,0,0,100,100,0,0,3,12,0,8,60,60,410,1",
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    if hook:
        lines.append(f"Dialogue: 2,{_ts(0)},{_ts(min(hook_seconds, duration))},Hook,,0,0,0,,"
                     f"{{\\fad(0,250)}}{_esc(hook.upper())}")
    if banner:
        lines.append(f"Dialogue: 2,{_ts(0)},{_ts(min(hook_seconds, duration))},Banner,,0,0,0,,{_esc(banner)}")
    if credit:
        lines.append(f"Dialogue: 1,{_ts(0)},{_ts(duration)},Credit,,0,0,0,,{_esc(credit)}")
    # captions: groups of up to 3 words, current word highlighted
    rel = [{**w, "start": w["start"] - clip_start, "end": w["end"] - clip_start} for w in words]
    rel = [w for w in rel if w["end"] > 0 and w["start"] < duration]
    groups = [rel[i: i + 3] for i in range(0, len(rel), 3)]
    for g in groups:
        for j, w in enumerate(g):
            s = max(0.0, w["start"])
            e = min(duration, g[j + 1]["start"] if j + 1 < len(g) else w["end"])
            if e <= s:
                continue
            txt = " ".join(
                ("{\\c&H0000E5FF&}" + _esc(x["text"].upper()) + "{\\c&H00FFFFFF&}") if k == j
                else _esc(x["text"].upper())
                for k, x in enumerate(g)
            )
            lines.append(f"Dialogue: 0,{_ts(s)},{_ts(e)},Cap,,0,0,0,,{txt}")
    return "\n".join(lines) + "\n"


def credit_line(src: dict) -> str | None:
    basis = (src.get("rights_basis") or "")
    if src.get("kind") == "inbox":
        return None
    who = src.get("channel_title") or "original creator"
    if basis.startswith("creativeCommon"):
        return f"Footage: {who} (CC BY)"
    return f"Footage: {who}"


def banner_for(cfg: dict, src: dict) -> str | None:
    until = cfg.get("spoiler_card_until")
    title = (src.get("title") or "").lower()
    if until and date.today().isoformat() <= str(until) and re.search(r"\bgta\s*(6|vi)\b", title):
        return "SPOILER-FREE"
    return None


def render(src: dict, pick: dict, cfg: dict, out_path: Path | None = None) -> Path:
    start, end = float(pick["start"]), float(pick["end"])
    dur = end - start
    info = media.probe(src["local_path"])
    out_dir = data_dir("clips", src["niche"])
    out_path = out_path or out_dir / f"{src['id'].replace(':', '_')}_{int(start)}_{int(end)}.mp4"
    ass_path = out_path.with_suffix(".ass")
    ass_path.write_text(build_ass(dur, pick.get("hook", ""), pick.get("words", []), start, credit_line(src),
                                  cfg.get("hook_seconds", 2.5), banner_for(cfg, src)), encoding="utf-8")

    zoom = float(cfg.get("zoom", 1.35))
    if cfg.get("layout") == "full_crop":
        vchain = f"[0:v]fps=30,scale=-2:{H},crop={W}:{H},setsar=1"
    else:
        vchain = (
            f"[0:v]fps=30,split=2[a][b];"
            f"[a]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},boxblur=25:3,"
            f"eq=brightness=-0.12[bg];"
            f"[b]crop=trunc(iw/{zoom}/2)*2:ih,scale={W}:-2[fg];"
            f"[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1"
        )
    vchain += f",ass={ass_path.name}[v]"

    cmd = ["ffmpeg", "-y", "-v", "error", "-ss", f"{start:.3f}", "-t", f"{dur:.3f}", "-i", str(Path(src['local_path']).resolve())]
    if info["has_audio"]:
        amap = ["-map", "0:a:0"]
    else:
        cmd += ["-f", "lavfi", "-t", f"{dur:.3f}", "-i", "anullsrc=r=48000:cl=stereo"]
        amap = ["-map", "1:a:0"]
    cmd += [
        "-filter_complex", vchain, "-map", "[v]", *amap,
        "-af", "loudnorm=I=-14:TP=-1.5:LRA=11",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", "-r", "30",
        "-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-ac", "2",
        "-movflags", "+faststart", "-shortest", str(out_path.resolve()),
    ]
    media.run(cmd, cwd=ass_path.parent)
    return out_path
