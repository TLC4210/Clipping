"""Render a 1080x1920 clip: 9:16 layout, hook text, word-by-word captions, credit line, loudness."""
from __future__ import annotations

import random
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


# Burned-in captions are censored: uncensored swearing gets Shorts limited ads and less reach.
PROFANITY = re.compile(r"\b(f+u+c+k\w*|motherf\w*|sh+i+t+\w*|bitch\w*|ass(?:hole)?s?|dick(?:s|head)?|pussy\w*|"
                       r"cunt\w*|n+i+g+g+\w*|fag\w*|retard\w*|whore\w*|slut\w*)\b", re.I)


def censor(text: str) -> str:
    return PROFANITY.sub(lambda m: m.group(0)[0] + "*" * (len(m.group(0)) - 1), text)


def build_ass(duration: float, hook: str, words: list[dict], clip_start: float, credit: str | None,
              hook_seconds: float, banner: str | None = None, stacked: bool = False,
              disclosure: str | None = None) -> str:
    # Stacked layout (facecam on top): hook at the very top, captions on the seam between cam and screen.
    hook_v, cap_v, banner_v, cap_align = (110, 760 + 40, 250, 8) if stacked else (230, 520, 410, 2)
    lines = [
        "[Script Info]", "ScriptType: v4.00+", f"PlayResX: {W}", f"PlayResY: {H}", "WrapStyle: 0",
        "ScaledBorderAndShadow: yes", "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, "
        "Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, "
        "MarginL, MarginR, MarginV, Encoding",
        f"Style: Hook,{FONT},84,&H00FFFFFF,&H00FFFFFF,&H30000000,&H30000000,-1,0,0,0,100,100,0,0,3,18,0,8,60,60,{hook_v},1",
        f"Style: Cap,{FONT},78,&H00FFFFFF,&H0000E5FF,&H00000000,&H96000000,-1,0,0,0,100,100,0,0,1,6,2,{cap_align},80,80,{cap_v},1",
        f"Style: Credit,{FONT},34,&H00FFFFFF,&H00FFFFFF,&H00000000,&H78000000,0,0,0,0,100,100,0,0,1,2,0,2,40,40,90,1",
        f"Style: Banner,{FONT},46,&H0000E5FF,&H00FFFFFF,&H30000000,&H30000000,-1,0,0,0,100,100,0,0,3,12,0,8,60,60,{banner_v},1",
        f"Style: Disclose,{FONT},44,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,3,10,0,7,40,40,36,1",
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    if hook:
        lines.append(f"Dialogue: 2,{_ts(0)},{_ts(min(hook_seconds, duration))},Hook,,0,0,0,,"
                     f"{{\\fad(0,250)}}{_esc(censor(hook).upper())}")
    if banner:
        lines.append(f"Dialogue: 2,{_ts(0)},{_ts(min(hook_seconds, duration))},Banner,,0,0,0,,{_esc(banner)}")
    if disclosure:  # paid campaign clip: FTC disclosure at the start (Content Rewards terms 12.9)
        lines.append(f"Dialogue: 3,{_ts(0)},{_ts(min(DISCLOSURE_S, duration))},Disclose,,0,0,0,,{_esc(disclosure)}")
    if credit:
        lines.append(f"Dialogue: 1,{_ts(0)},{_ts(duration)},Credit,,0,0,0,,{_esc(credit)}")
    # captions: groups of up to 3 words, current word highlighted
    rel = [{**w, "text": censor(w["text"]), "start": w["start"] - clip_start, "end": w["end"] - clip_start}
           for w in words]
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


DISCLOSURE_S = 4.0


def is_paid(src: dict) -> bool:
    """A clip made for a paid campaign (Content Rewards): it needs a paid-promotion disclosure."""
    return (src.get("rights_basis") or "").startswith("campaign:")


def disclosure_for(cfg: dict, src: dict) -> str | None:
    return cfg.get("disclosure_text", "#AD · PAID CLIP") if is_paid(src) else None


def banner_for(cfg: dict, src: dict) -> str | None:
    until = cfg.get("spoiler_card_until")
    title = (src.get("title") or "").lower()
    if until and date.today().isoformat() <= str(until) and re.search(r"\bgta\s*(6|vi)\b", title):
        return "SPOILER-FREE"
    return None


def render(src: dict, pick: dict, cfg: dict, out_path: Path | None = None, platform: str = "youtube") -> Path:
    """Edit master (joined pieces, jump cuts) -> layout + punch-in zooms -> emoji pops -> captions,
    with sound effects and an optional music bed mixed under the clip's own audio."""
    from . import edit

    tl = edit.Timeline(pick.get("ranges") or [(float(pick["start"]), float(pick["end"]))])
    start, end, dur = float(pick["start"]), float(pick["end"]), tl.duration
    out_dir = data_dir("clips", src["niche"])
    out_path = out_path or out_dir / f"{src['id'].replace(':', '_')}_{int(start)}_{int(end)}.mp4"
    ass_path = out_path.with_suffix(".ass")
    cam = src.get("facecam") if cfg.get("layout") == "facecam_stack" else None
    ass_path.write_text(build_ass(dur, pick.get("hook", ""), tl.words(pick.get("words", [])), 0.0,
                                  credit_line(src) if cfg.get("burn_credit") else None,
                                  cfg.get("hook_seconds", 2.5), banner_for(cfg, src), stacked=bool(cam),
                                  disclosure=disclosure_for(cfg, src)),
                        encoding="utf-8")
    master = out_path.with_name(out_path.stem + ".master.mp4")
    info = edit.master(src, tl.ranges, master)
    iw, ih = info["width"], info["height"]

    def at(t):
        return tl.to_out(float(t))

    zooms = [(at(z["t"]), float(z.get("dur") or 1.0)) for z in pick.get("zooms") or [] if at(z["t"]) is not None]
    z = edit.zoom_expr(zooms)
    if cam:
        parts = [edit.stack_chain(iw, ih, cam, z)]
    elif cfg.get("layout") == "full_crop":
        parts = [f"[0:v]fps=30,scale=-2:{H},crop={W}:{H},setsar=1[base]"]
    else:
        parts = [edit.blur_chain(iw, ih, float(cfg.get("zoom", 1.35)), z)]

    inputs = ["-i", str(master.resolve())]
    n_in = 1
    cur = "base"
    for k, e in enumerate(pick.get("emojis") or []):
        t, png = at(e["t"]), edit.emoji_png(e.get("emoji", ""))
        if t is None or png is None:
            continue
        inputs += ["-loop", "1", "-framerate", "30", "-t", f"{dur:.3f}", "-i", str(png)]
        x = W - edit.EMOJI_PX - 60 if k % 2 == 0 else 60
        y0 = (edit.CAM_H - edit.EMOJI_PX - 40) if cam else 470  # stacked: bottom corner of the cam, clear of captions
        parts.append(f"[{cur}][{n_in}:v]overlay=x={x}:y='{y0}+80*max(0,1-(t-{t:.2f})/0.15)':"
                     f"enable='between(t,{t:.2f},{t + edit.EMOJI_SHOW_S:.2f})'[e{k}]")
        cur, n_in = f"e{k}", n_in + 1
    parts.append(f"[{cur}]ass={ass_path.name}[v]")

    if info["has_audio"]:
        mix = ["[0:a]"]
    else:
        inputs += ["-f", "lavfi", "-t", f"{dur:.3f}", "-i", "anullsrc=r=48000:cl=stereo"]
        mix, n_in = [f"[{n_in}:a]"], n_in + 1
    lib = edit.sfx_library(platform)
    for k, s in enumerate(pick.get("sfx") or []):
        t, f = at(s["t"]), lib.get(str(s.get("name", "")).lower())
        if t is None or f is None:
            continue
        ms = int(t * 1000)
        inputs += ["-i", str(f)]
        parts.append(f"[{n_in}:a]aformat=sample_rates=48000:channel_layouts=stereo,"
                     f"volume={cfg.get('sfx_volume', 0.7)},adelay={ms}|{ms}[s{k}]")
        mix.append(f"[s{k}]")
        n_in += 1
    songs = edit.music_files(platform, src.get("niche")) if cfg.get("music") else []
    if songs:  # same clip -> same track on every re-render
        inputs += ["-stream_loop", "-1", "-i", str(random.Random(out_path.stem).choice(songs))]
        parts.append(f"[{n_in}:a]aformat=sample_rates=48000:channel_layouts=stereo,"
                     f"volume={cfg.get('music_volume', 0.1)},atrim=0:{dur:.3f}[mus]")
        mix.append("[mus]")
        n_in += 1
    alabel = mix[0]
    if len(mix) > 1:
        parts.append("".join(mix) + f"amix=inputs={len(mix)}:normalize=0:duration=first[amx]")
        alabel = "[amx]"
    parts.append(f"{alabel}loudnorm=I=-14:TP=-1.5:LRA=11[aout]")

    cmd = ["ffmpeg", "-y", "-v", "error", *inputs, "-filter_complex", ";".join(parts),
           "-map", "[v]", "-map", "[aout]", "-t", f"{dur:.3f}",
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", "-r", "30",
           "-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-ac", "2",
           "-movflags", "+faststart", str(out_path.resolve())]
    try:
        media.run(cmd, cwd=ass_path.parent)
    finally:
        master.unlink(missing_ok=True)
    return out_path
