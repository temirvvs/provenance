import os

import numpy as np

from . import __version__
from .probe import probe, ProbeError, get
from .decode import decode_pcm
from .flac_md5 import flac_md5
from .analysis import average_spectrum, spectrum_metrics
from .bitdepth import bit_usage, level_stats, verdict as bit_verdict
from .verdict import classify
from .platform import assess


def check(path):
    fmt, audio = probe(path)
    rate = int(float(audio.get("sample_rate", 0)))
    channels = int(audio.get("channels", 0))
    declared_bits = int(audio.get("bits_per_raw_sample")
                        or audio.get("bits_per_sample") or 0)
    codec = audio.get("codec_name", "")
    container = audio.get("codec_name", "") or fmt.get("format_name", "")
    duration = float(fmt.get("duration", 0) or audio.get("duration", 0) or 0)
    size = os.path.getsize(path)

    md5_zero = False
    if codec.lower() == "flac":
        sig = flac_md5(path)
        if sig:
            md5_zero = sig == "00000000000000000000000000000000"

    samples = decode_pcm(path, channels, rate, declared_bits)
    usage = bit_usage(samples)
    levels = level_stats(samples)
    depth = bit_verdict(declared_bits, usage, levels)

    mono = samples.mean(axis=1).astype(np.float64) / float(0x7FFFFF)
    power, binw = average_spectrum(mono, rate)
    spec = spectrum_metrics(power, binw)

    kind, reasons = classify(
        spec["cutoff65_hz"], spec["energy_above_16k"],
        depth["verdict"] == "GENUINE_24",
        spec["top_band_db"], spec["max_cliff_db_per_khz"],
        spec["cliff_at_hz"], spec["transition_khz"],
    )

    if kind == "AUTHENTIC_LOSSLESS" and depth["verdict"] == "PADDED_16_TO_24":
        kind = "UPSCALED_16_IN_24"
        reasons = depth["reasons"] + [
            "not a lossy transcode, but the content is 16-bit shifted into "
            "a 24-bit container -> falsely marketed as hi-res",
        ]

    candidates, signals, caveat = assess(
        kind,
        depth["verdict"] == "GENUINE_24",
        declared_bits, usage["effective_bits"],
        spec["cutoff65_hz"], spec["energy_above_16k"],
        spec["energy_above_20k"], spec["brickwall_sharpness"],
        get(fmt, audio, "MEDIA"),
        get(fmt, audio, "ENCODER") or get(fmt, audio, "vendor_string"),
        md5_zero,
        get(fmt, audio, "ALBUM"),
        get(fmt, audio, "ALBUMARTIST"),
        bool(get(fmt, audio, "replaygain_track_gain")
             or get(fmt, audio, "REPLAYGAIN_TRACK_GAIN")),
        spec["top_band_db"],
    )

    return {
        "version": __version__,
        "file": {
            "path": path,
            "size": size,
            "container": container,
            "codec": codec,
            "duration_s": round(duration, 3),
            "sample_rate": rate,
            "channels": channels,
            "declared_bits": declared_bits,
            "md5_zero": md5_zero,
        },
        "tags": {
            "album": get(fmt, audio, "ALBUM"),
            "artist": get(fmt, audio, "ALBUMARTIST")
                     or get(fmt, audio, "ARTIST"),
            "media": get(fmt, audio, "MEDIA"),
            "encoder": get(fmt, audio, "ENCODER")
                       or get(fmt, audio, "vendor_string"),
            "replaygain": bool(get(fmt, audio, "replaygain_track_gain")
                               or get(fmt, audio, "REPLAYGAIN_TRACK_GAIN")),
        },
        "bitdepth": depth,
        "spectrum": spec,
        "verdict": {"kind": kind, "reasons": reasons},
        "origin": {"candidates": candidates, "signals": signals,
                   "caveat": caveat},
    }
