#!/usr/bin/env python3
"""Generate synthetic test fixtures for provenance and (optionally) verify
that the tool classifies each one correctly.

Usage:
    python scripts/make_fixtures.py OUT_DIR            # generate fixtures
    python scripts/make_fixtures.py OUT_DIR --verify   # generate + assert verdicts
"""
import argparse
import os
import shutil
import subprocess
import sys
import tempfile

import numpy as np

SR = 44100
SECONDS = 3
RNG = np.random.default_rng(42)


def synth_mix(noise_floor_db, dither_amp, duration=SECONDS, sr=SR):
    """A musically-plausible mix: bass, mid and high tones plus a broadband
    noise floor extending to Nyquist (as a real master has) plus dither at the
    given bit depth."""
    n = int(duration * sr)
    t = np.arange(n) / sr
    x = (
        0.35 * np.sin(2 * np.pi * 55.0 * t)
        + 0.25 * np.sin(2 * np.pi * 440.0 * t)
        + 0.10 * np.sin(2 * np.pi * 12000.0 * t)
    )
    noise = RNG.uniform(-10 ** (noise_floor_db / 20.0),
                        10 ** (noise_floor_db / 20.0), n)
    dither = RNG.uniform(-dither_amp, dither_amp, n)
    x = np.clip(x + noise + dither, -1.0, 1.0)
    return x


def quantize(x, bits):
    scale = 2 ** (bits - 1) - 1
    return (x * scale).astype(np.int64)


def write_s24(path, samples):
    packed = bytearray()
    for v in samples:
        v &= 0xFFFFFF
        packed += bytes([v & 0xFF, (v >> 8) & 0xFF, (v >> 16) & 0xFF])
    with open(path, "wb") as f:
        f.write(bytes(packed))


def ffmpeg(*args):
    subprocess.run(["ffmpeg", "-v", "quiet", "-y", *args], check=True)


def flac_from_s24(pcm, out):
    ffmpeg("-f", "s24le", "-ar", str(SR), "-ac", "2", "-i", pcm,
           "-c:a", "flac", out)


def flac_from_s16(pcm, out):
    ffmpeg("-f", "s16le", "-ar", str(SR), "-ac", "2", "-i", pcm,
           "-c:a", "flac", out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out_dir")
    ap.add_argument("--verify", action="store_true")
    ap.add_argument("--provenance", default=None,
                    help="path to the provenance CLI (default: discover)")
    args = ap.parse_args()

    os.makedirs(args.out_dir, exist_ok=True)
    tmp = tempfile.mkdtemp()
    expected = {}

    # Genuine 24-bit master: content + analog-style noise floor to Nyquist,
    # dithered at 24-bit depth so the LSB toggles.
    g24 = quantize(synth_mix(noise_floor_db=-50.0, dither_amp=1.0 / 2**23), 24)
    p24 = os.path.join(tmp, "genuine24.s24le")
    write_s24(p24, g24)
    flac_from_s24(p24, os.path.join(args.out_dir, "genuine24.flac"))
    expected["genuine24.flac"] = ("GENUINE_24", "AUTHENTIC_LOSSLESS")

    # 16-bit content shifted into a 24-bit container (fake hi-res): the exact
    # upshift a lossy pipeline applies, so bits 0-7 are idle.
    g16 = quantize(synth_mix(noise_floor_db=-52.0, dither_amp=1.0 / 2**15), 16)
    p16 = os.path.join(tmp, "genuine16.s16le")
    with open(p16, "wb") as f:
        g16.astype(np.int16).tofile(f)

    padded = (g16 << 8) & 0xFFFFFF
    pp = os.path.join(tmp, "padded.s24le")
    write_s24(pp, padded)
    flac_from_s24(pp, os.path.join(args.out_dir, "padded16to24.flac"))
    expected["padded16to24.flac"] = ("PADDED_16_TO_24", "UPSCALED_16_IN_24")

    # Genuine 16-bit CD-style master.
    flac_from_s16(p16, os.path.join(args.out_dir, "genuine16.flac"))
    expected["genuine16.flac"] = ("GENUINE_16", "AUTHENTIC_LOSSLESS")

    # Lossy -> lossless transcodes at two bitrates.
    for br, name in (("128k", "mp3_128_to_24"), ("320k", "mp3_320_to_24")):
        mp3 = os.path.join(tmp, f"{name}.mp3")
        ffmpeg("-f", "s16le", "-ar", str(SR), "-ac", "2", "-i", p16,
               "-c:a", "libmp3lame", "-b:a", br, mp3)
        ffmpeg("-i", mp3, "-c:a", "flac",
               os.path.join(args.out_dir, f"{name}.flac"))
        expected[f"{name}.flac"] = ("GENUINE_24", "TRANSCODE")

    print(f"fixtures written to {args.out_dir}:")
    for k in sorted(expected):
        print(f"  {k}")

    if not args.verify:
        shutil.rmtree(tmp, ignore_errors=True)
        return

    import json
    prov = args.provenance or shutil.which("provenance")
    if not prov:
        candidates = [
            os.path.join(os.path.dirname(__file__), "..", ".venv", "bin",
                         "provenance"),
        ]
        for c in candidates:
            if os.path.exists(c):
                prov = c
                break
    if not prov:
        print("ERROR: 'provenance' not found; install the tool or pass "
              "--provenance PATH", file=sys.stderr)
        sys.exit(2)

    files = [os.path.join(args.out_dir, k) for k in expected]
    out = subprocess.run([prov, "--json", *files],
                         capture_output=True, check=True)
    results = {os.path.basename(r["file"]["path"]): r
               for r in json.loads(out.stdout)}
    failures = 0
    for name, (want_depth, want_verdict) in sorted(expected.items()):
        r = results[name]
        got_depth = r["bitdepth"]["verdict"]
        got_verdict = r["verdict"]["kind"]
        ok = got_depth == want_depth and got_verdict == want_verdict
        print(f"  {'PASS' if ok else 'FAIL'} {name}: "
              f"{got_depth} / {got_verdict} "
              f"(expected {want_depth} / {want_verdict})")
        failures += 0 if ok else 1
    shutil.rmtree(tmp, ignore_errors=True)
    print(f"\n{len(expected) - failures}/{len(expected)} passed")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
