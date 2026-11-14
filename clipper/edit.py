"""The edit: what a clip editor does between "pick the moment" and "export".

- Timeline: the source ranges a clip is built from. Claude may join up to 3 pieces (a setup and its
  payoff from different moments), and jump cuts remove dead air inside each piece.
- Edit master: those ranges cut and joined into one file, so the layout, captions and effects all work
  in clip time.
- Effects: facecam-on-top stack layout, punch-in zooms, emoji pops, sound effects and a music bed.
  Sound effects and music come only from files you put in data/assets/sfx and data/assets/music
  (human-made, licensed for reuse). The bot never generates audio or images with AI: the Reach campaigns
  ban AI content.
"""
from __future__ import annotations

import random
from pathlib import Path

import numpy as np

from . import media
from .config import data_dir

W, H = 1080, 1920
CAM_H = 760                 # facecam panel on top; screen/game panel fills the rest
GAME_H = H - CAM_H
JUMP_MIN_GAP_S = 0.7        # quiet stretches at least this long are cut out...
JUMP_KEEP_S = 0.12          # ...keeping this much on each side so words aren't clipped
JUMP_QUIET_DB = 9.0         # "quiet" = this many dB below the piece's median loudness
ZOOM = 1.25                 # punch-in scale
EMOJI_PX = 190
EMOJI_SHOW_S = 1.3
AUDIO_EXT = {".wav", ".mp3", ".m4a", ".ogg", ".flac", ".aac"}
EMOJI_FONT = r"C:\Windows\Fonts\seguiemj.ttf"


# --------------------------------------------------------------- timeline ---
class Timeline:
    """Kept source ranges, in order. Maps source time <-> clip time."""

    def __init__(self, ranges: list[tuple[float, float]]):
        self.ranges = [(float(a), float(b)) for a, b in ranges if b > a]

    @property
    def duration(self) -> float:
        return sum(b - a for a, b in self.ranges)

    def to_out(self, t: float) -> float | None:
        off = 0.0
        for a, b in self.ranges:
            if a <= t <= b:
                return off + (t - a)
            off += b - a
        return None

    def to_src(self, t_out: float) -> float:
        off = 0.0
        for a, b in self.ranges:
            if t_out <= off + (b - a):
                return a + max(0.0, t_out - off)
            off += b - a
        return self.ranges[-1][1]

    def words(self, words: list[dict]) -> list[dict]:
        """Caption words in clip time (words in cut-out stretches are dropped)."""
        out = []
        for w in words:
            s = self.to_out(w["start"])
            if s is None:
                continue
            e = self.to_out(min(w["end"], next(b for a, b in self.ranges if a <= w["start"] <= b)))
            out.append({**w, "start": s, "end": max(s + 0.05, e or s + 0.3)})
        return out


def jump_ranges(src: dict, ranges: list[tuple[float, float]], words: list[dict], min_total: float) -> list[tuple[float, float]]:
    """Cut quiet dead air out of each range (no word starts in it and the audio drops well below normal).

    Never cuts below min_total seconds overall, never touches the first/last 0.5 s of a piece.
    """
    hop = 0.05
    out: list[tuple[float, float]] = []
    for a, b in ranges:
        path, t0 = media.source_at(src, a)
        e = media.audio_energy(path, hop_s=hop, start=t0, dur=b - a)
        if e.size < 20:
            out.append((a, b))
            continue
        quiet = e < (np.median(e) - JUMP_QUIET_DB)
        starts = [w["start"] for w in words if a <= w["start"] <= b]
        cur = a
        i = 0
        while i < len(quiet):
            if not quiet[i]:
                i += 1
                continue
            j = i
            while j < len(quiet) and quiet[j]:
                j += 1
            g0, g1 = a + i * hop + JUMP_KEEP_S, a + j * hop - JUMP_KEEP_S
            if (g1 - g0 >= JUMP_MIN_GAP_S - 2 * JUMP_KEEP_S and g0 > a + 0.5 and g1 < b - 0.5
                    and not any(g0 <= s <= g1 for s in starts)):
                out.append((cur, g0))
                cur = g1
            i = j
        out.append((cur, b))
    out = [(x, y) for x, y in out if y - x >= 0.25]
    if sum(y - x for x, y in out) < min_total:
        return ranges
    return out


# ----------------------------------------------------------------- master ---
def master(src: dict, ranges: list[tuple[float, float]], out_path: Path) -> dict:
    """Cut and join the ranges into one file (source resolution, 30 fps). Returns its probe info."""
    first, _ = media.source_at(src, ranges[0][0])
    info = media.probe(first)
    w, h = info["width"] - info["width"] % 2, info["height"] - info["height"] % 2
    cmd = ["ffmpeg", "-y", "-v", "error"]
    parts = []
    for i, (a, b) in enumerate(ranges):
        path, t = media.source_at(src, a)
        cmd += ["-ss", f"{t:.3f}", "-t", f"{b - a:.3f}", "-i", str(Path(path).resolve())]
        parts.append(f"[{i}:v]fps=30,scale={w}:{h},setsar=1[v{i}]")
        if info["has_audio"]:
            parts.append(f"[{i}:a]aformat=sample_rates=48000:channel_layouts=stereo,asetpts=PTS-STARTPTS[a{i}]")
    n = len(ranges)
    if info["has_audio"]:
        parts.append("".join(f"[v{i}][a{i}]" for i in range(n)) + f"concat=n={n}:v=1:a=1[v][a]")
        maps = ["-map", "[v]", "-map", "[a]", "-c:a", "aac", "-b:a", "192k"]
    else:
        parts.append("".join(f"[v{i}]" for i in range(n)) + f"concat=n={n}:v=1:a=0[v]")
        maps = ["-map", "[v]"]
    cmd += ["-filter_complex", ";".join(parts), *maps, "-c:v", "libx264", "-preset", "veryfast", "-crf", "16",
            "-pix_fmt", "yuv420p", str(out_path)]
    media.run(cmd)
    return media.probe(out_path)


# ---------------------------------------------------------------- layouts ---
def _even(x: float) -> int:
    return max(2, int(x) // 2 * 2)


def _crop_box(iw: int, ih: int, cx: float, cy: float, bw: float, bh: float, aspect: float) -> tuple[int, int, int, int]:
    """Largest crop of aspect `aspect` inside the box (bw x bh) centred on (cx, cy), kept inside the frame."""
    if bw / bh > aspect:
        cw, ch = bh * aspect, bh
    else:
        cw, ch = bw, bw / aspect
    cw, ch = min(cw, iw), min(ch, ih)
    x = min(max(0.0, cx - cw / 2), iw - cw)
    y = min(max(0.0, cy - ch / 2), ih - ch)
    return _even(cw), _even(ch), _even(x), _even(y)


def zoom_expr(zooms: list[tuple[float, float]]) -> str | None:
    """Per-frame scale factor: ZOOM inside any punch-in window, else 1 (instant cut in and out)."""
    if not zooms:
        return None
    on = "+".join(f"between(t,{a:.2f},{a + d:.2f})" for a, d in zooms)
    return f"(1+{ZOOM - 1:.3f}*min(1,{on}))"


def _zoomed(label_in: str, label_out: str, w: int, h: int, z: str | None) -> str:
    if not z:
        return f"[{label_in}]null[{label_out}]"
    return (f"[{label_in}]scale=w='trunc({w}*{z}/2)*2':h='trunc({h}*{z}/2)*2':eval=frame,"
            f"crop={w}:{h}[{label_out}]")


def stack_chain(iw: int, ih: int, cam: dict, z: str | None) -> str:
    """Facecam on top (CAM_H), the screen/game below, from input [0:v] to [base]."""
    cx, cy = (cam["x"] + cam["w"] / 2) * iw, (cam["y"] + cam["h"] / 2) * ih
    cw, ch, cxp, cyp = _crop_box(iw, ih, cx, cy, cam["w"] * iw, cam["h"] * ih, W / CAM_H)
    gx = cam.get("content_x", 0.5) * iw
    gw, gh, gxp, gyp = _crop_box(iw, ih, gx, ih / 2, iw, ih, W / GAME_H)
    return (f"[0:v]split=2[c0][g0];"
            f"[c0]crop={cw}:{ch}:{cxp}:{cyp},scale={W}:{CAM_H},setsar=1[c1];"
            + _zoomed("c1", "cam", W, CAM_H, z) + ";"
            f"[g0]crop={gw}:{gh}:{gxp}:{gyp},scale={W}:{GAME_H},setsar=1[game];"
            f"[cam][game]vstack=inputs=2[base]")


def blur_chain(iw: int, ih: int, zoom: float, z: str | None) -> str:
    """Blurred full-frame background with the zoomed source in the middle, [0:v] -> [base]."""
    fw = _even(iw / zoom)
    fg_h = _even(W * ih / fw)
    return (f"[0:v]split=2[a][b];"
            f"[a]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},boxblur=25:3,"
            f"eq=brightness=-0.12[bg];"
            f"[b]crop={fw}:ih,scale={W}:{fg_h},setsar=1[f1];"
            + _zoomed("f1", "fg", W, fg_h, z) + ";"
            f"[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1[base]")


# ---------------------------------------------------------------- effects ---
def sfx_library(platform: str = "youtube") -> dict[str, Path]:
    """Sound effects you supplied -> {name: path}.

    data/assets/sfx/<name>.wav|mp3...        licensed for every platform
    data/assets/sfx/youtube/<name>.wav|mp3... YouTube Audio Library (YouTube only; left out of Instagram versions)
    """
    dirs = [data_dir("assets", "sfx")] + ([data_dir("assets", "sfx", "youtube")] if platform == "youtube" else [])
    return {p.stem.lower().replace(" ", "_"): p for d in dirs for p in sorted(d.iterdir())
            if p.is_file() and p.suffix.lower() in AUDIO_EXT}


MUSIC_POOLS = ("youtube", "anywhere")  # data/assets/music/<pool>


def music_files(platform: str = "youtube", niche: str | None = None) -> list[Path]:
    """Music the bot may put under a clip for this platform and niche.

    data/assets/music/youtube[/<niche>]:  YouTube Audio Library tracks (standard licence: YouTube only)
    data/assets/music/anywhere[/<niche>]: tracks licensed for every platform (YouTube and Instagram)
    Files directly in a pool folder fit any niche; files in a <niche> subfolder only that niche.
    """
    pools = ["anywhere"] + (["youtube"] if platform == "youtube" else [])
    dirs = [data_dir("assets", "music", pool) for pool in pools]
    if niche:
        dirs += [data_dir("assets", "music", pool, niche) for pool in pools]
    return [p for d in dirs for p in sorted(d.iterdir()) if p.is_file() and p.suffix.lower() in AUDIO_EXT]


def emoji_png(emoji: str) -> Path | None:
    """The emoji drawn with Windows' colour emoji font (cached). None if it can't be drawn."""
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        return None
    key = "-".join(f"{ord(c):x}" for c in emoji)
    out = data_dir("assets", "emoji") / f"{key}.png"
    if out.exists():
        return out
    try:
        font = ImageFont.truetype(EMOJI_FONT, 109)  # the font's native colour-bitmap size
    except OSError:
        return None
    im = Image.new("RGBA", (260, 260), (0, 0, 0, 0))
    ImageDraw.Draw(im).text((20, 20), emoji, font=font, embedded_color=True)
    box = im.getbbox()
    if not box:
        return None
    im = im.crop(box)
    im = im.resize((EMOJI_PX, int(EMOJI_PX * im.height / im.width)), Image.LANCZOS)
    im.save(out)
    return out
