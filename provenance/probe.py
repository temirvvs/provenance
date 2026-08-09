import json
import shutil
import subprocess


class ProbeError(RuntimeError):
    pass


def require_tool(name):
    path = shutil.which(name)
    if not path:
        raise ProbeError(f"required tool not found: {name} (install ffmpeg/ffprobe)")
    return path


def probe(path):
    ffprobe = require_tool("ffprobe")
    cmd = [
        ffprobe, "-v", "quiet", "-print_format", "json",
        "-show_format", "-show_streams", path,
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise ProbeError(f"ffprobe failed on {path}: {proc.stderr.strip()[:300]}")
    data = json.loads(proc.stdout or "{}")
    streams = data.get("streams", [])
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
    if audio is None:
        raise ProbeError(f"no audio stream in {path}")
    return data.get("format", {}), audio


def stream_tags(audio):
    return audio.get("tags", {}) or {}


def format_tags(fmt):
    return fmt.get("tags", {}) or {}


def get(fmt, audio, key):
    tags = {**format_tags(fmt), **stream_tags(audio)}
    v = tags.get(key) or tags.get(key.lower()) or tags.get(key.upper())
    return (v or "").strip()
