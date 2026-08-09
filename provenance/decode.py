import subprocess

import numpy as np

from .probe import require_tool, ProbeError


def decode_pcm(path, channels, rate, bits):
    """Decode at the container's native depth (s16le or s24le) so the low bits
    of the histogram are the file's true LSBs. Never use -ac/-ar (resampler
    re-dithers) and never ask for s32le (24-bit content is right-aligned there,
    making genuine 24-bit look like padded 16-bit)."""
    fmt = "s16le" if bits <= 16 else "s24le"
    ffmpeg = require_tool("ffmpeg")
    cmd = [
        ffmpeg, "-v", "quiet", "-i", path,
        "-f", fmt, "-acodec", f"pcm_{fmt}",
        "-ac", str(channels), "-ar", str(rate), "-",
    ]
    proc = subprocess.run(cmd, capture_output=True)
    if proc.returncode != 0:
        raise ProbeError(
            f"ffmpeg decode failed on {path}: "
            f"{proc.stderr.decode(errors='replace')[:300]}"
        )
    bps = 2 if bits <= 16 else 3
    raw = np.frombuffer(proc.stdout, dtype=np.uint8)
    usable = len(raw) - (len(raw) % (bps * channels))
    raw = raw[:usable]
    if bps == 2:
        v = raw.reshape(-1, 2).astype(np.int32)
        v = v[:, 0] | (v[:, 1] << 8)
        v = np.where(v >= 0x8000, v - 0x10000, v)
    else:
        raw = raw.reshape(-1, 3)
        v = (
            raw[:, 0].astype(np.int32)
            | (raw[:, 1].astype(np.int32) << 8)
            | (raw[:, 2].astype(np.int32) << 16)
        )
        v = np.where(v >= 0x800000, v - 0x1000000, v)
    return v.reshape(-1, channels)


def decode_s24(path, channels, rate):
    """Backwards-compatible 24-bit decoder (3-byte packed)."""
    return decode_pcm(path, channels, rate, 24)


def decode_mono_float(path, channels, rate):
    """Numpy downmix (exact arithmetic, no dither) for spectral analysis.
    Bit-depth analysis must use the raw decode_s24 output instead."""
    v = decode_s24(path, channels, rate)
    return v.mean(axis=1).astype(np.float64) / float(0x7FFFFF)
