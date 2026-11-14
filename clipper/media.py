"""ffmpeg/ffprobe helpers and signal extraction (audio energy, scene cuts, captions)."""
from __future__ import annotations

import base64
import json
import re
import subprocess
from pathlib import Path

import numpy as np

SR = 16000


def run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, check=True, capture_output=True, **kw)


def probe(path) -> dict:
    out = run(["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)])
    info = json.loads(out.stdout)
    v = next((s for s in info["streams"] if s["codec_type"] == "video"), None)
    a = next((s for s in info["streams"] if s["codec_type"] == "audio"), None)
    return {
        "duration": float(info["format"].get("duration", 0)),
        "width": int(v["width"]) if v else 0,
        "height": int(v["height"]) if v else 0,
        "has_audio": a is not None,
        "size": int(info["format"].get("size", 0)),
        "vcodec": v.get("codec_name") if v else None,
        "acodec": a.get("codec_name") if a else None,
    }


def audio_energy(path, hop_s: float = 0.5, start: float | None = None, dur: float | None = None) -> np.ndarray:
    """RMS loudness (dBFS) per hop, of the whole file or [start, start+dur]. Empty array if no audio."""
    seek = (["-ss", f"{start:.3f}"] if start is not None else []) + (["-t", f"{dur:.3f}"] if dur is not None else [])
    proc = subprocess.run(
        ["ffmpeg", "-v", "error", *seek, "-i", str(path), "-vn", "-ac", "1", "-ar", str(SR), "-f", "s16le", "-"],
        capture_output=True,
    )
    if proc.returncode != 0 or not proc.stdout:
        return np.array([])
    x = np.frombuffer(proc.stdout, dtype=np.int16).astype(np.float32) / 32768.0
    hop = int(SR * hop_s)
    n = len(x) // hop
    if n == 0:
        return np.array([])
    frames = x[: n * hop].reshape(n, hop)
    rms = np.sqrt(np.mean(frames**2, axis=1) + 1e-12)
    return 20 * np.log10(rms)


def scene_cuts(path, threshold: float = 12.0) -> list[float]:
    """Timestamps (s) of scene changes, using ffmpeg's scdet on a downscaled 4 fps stream."""
    proc = subprocess.run(
        [
            "ffmpeg", "-v", "info", "-i", str(path), "-an",
            "-vf", f"fps=4,scale=320:-2,scdet=threshold={threshold}", "-f", "null", "-",
        ],
        capture_output=True,
        text=True,
    )
    return [float(m) for m in re.findall(r"lavfi\.scd\.time:\s*([\d.]+)", proc.stderr)]


def frame_jpeg_b64(path, t: float, width: int = 384) -> str:
    out = run(
        ["ffmpeg", "-v", "error", "-ss", f"{t:.2f}", "-i", str(path), "-frames:v", "1",
         "-vf", f"scale={width}:-2", "-f", "image2", "-c:v", "mjpeg", "-q:v", "5", "-"]
    )
    return base64.b64encode(out.stdout).decode()


def load_json3_words(path) -> list[dict]:
    """Parse YouTube json3 captions into [{'start','end','text'}] (word level when available)."""
    if not path or not Path(path).exists():
        return []
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    words: list[dict] = []
    for ev in data.get("events", []):
        segs = ev.get("segs") or []
        t0 = ev.get("tStartMs", 0) / 1000
        dur = ev.get("dDurationMs", 0) / 1000
        for i, seg in enumerate(segs):
            # Auto-captions carry sound tags ("[BELL]", "[Music]") and ">>" speaker-change markers;
            # they are not speech and must not be burned into the clip.
            txt = re.sub(r"\[[^\]]*\]|>>|&gt;&gt;", " ", seg.get("utf8") or "").strip()
            if not txt:
                continue
            s = t0 + seg.get("tOffsetMs", 0) / 1000
            words.append({"start": s, "end": t0 + dur, "text": txt})
    words.sort(key=lambda w: w["start"])
    for a, b in zip(words, words[1:]):  # end each word at the next word's start
        a["end"] = min(a["end"], b["start"]) if b["start"] > a["start"] else a["end"]
    for w in words:
        if w["end"] <= w["start"]:
            w["end"] = w["start"] + 0.3
    return words


_WHISPER = {}


def _whisper_model():
    """openai-whisper on CPU (faster-whisper's PyAV DLLs are blocked by Windows App Control here)."""
    import os

    import whisper

    name = os.environ.get("CLIPPER_WHISPER_MODEL", "small")
    if name not in _WHISPER:
        _WHISPER[name] = whisper.load_model(name, device="cpu")
    return _WHISPER[name]


def transcribe_ranges(path, ranges: list[tuple[float, float]], language: str | None = "en") -> list[dict]:
    """Word-level speech-to-text for only the given (start, end) windows of a source.

    Used when YouTube captions are missing (they are often rate-limited). Transcribing a dozen
    30-60 s windows takes a few minutes on CPU instead of the whole multi-hour stream.
    Returns [] if whisper is not installed.
    """
    try:
        model = _whisper_model()
    except ImportError:
        return []
    words: list[dict] = []
    for start, end in _merge_ranges(ranges):
        pcm = subprocess.run(
            ["ffmpeg", "-v", "error", "-ss", f"{start:.2f}", "-t", f"{end - start:.2f}", "-i", str(path),
             "-vn", "-ac", "1", "-ar", str(SR), "-f", "s16le", "-"],
            capture_output=True,
        ).stdout
        if not pcm:
            continue
        audio = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
        res = model.transcribe(audio, language=language, word_timestamps=True, fp16=False,
                               condition_on_previous_text=False)
        for seg in res.get("segments", []):
            for w in seg.get("words") or []:
                txt = w["word"].strip()
                if txt:
                    words.append({"start": start + w["start"], "end": start + w["end"], "text": txt})
    words.sort(key=lambda w: w["start"])
    return words


def _merge_ranges(ranges: list[tuple[float, float]]) -> list[tuple[float, float]]:
    out: list[list[float]] = []
    for a, b in sorted((max(0.0, a), b) for a, b in ranges if b > a):
        if out and a <= out[-1][1]:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return [(a, b) for a, b in out]


def source_at(src: dict, t: float) -> tuple[str, float]:
    """(file, time in that file) for source time t: a downloaded section of a long source, else the source."""
    for s in src.get("segments") or []:
        if s["start"] <= t <= s["end"]:
            return s["path"], t - s["start"]
    return src["local_path"], t


def words_between(words: list[dict], start: float, end: float) -> list[dict]:
    return [w for w in words if w["start"] >= start and w["end"] <= end + 0.25]
