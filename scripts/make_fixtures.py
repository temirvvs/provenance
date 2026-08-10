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
    """Write mono samples as interleaved stereo (L=R), matching flac_from_s24's
    -ac 2 read. Writing mono bytes and reading them as stereo would decimate
    each channel and alias high tones away."""
    packed = bytearray()
    for v in samples:
        for _ in range(2):
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


def butter_lowpass_4(x, fc, sr):
    """4th-order Butterworth lowpass (24 dB/oct) in pure numpy, via the
    bilinear transform. This is what a producer's mastering EQ sounds like:
    a wide, multi-kHz rolloff at an arbitrary knee - unlike a codec's
    near-ideal ~2 kHz brickwall at a standardized cutoff."""
    k = 1.0 / np.tan(np.pi * fc / sr)
    k2 = k * k
    sections = []
    for a in (np.cos(5 * np.pi / 8.0), np.cos(7 * np.pi / 8.0)):
        a0 = k2 - 2.0 * a * k + 1.0
        a1 = -2.0 * k2 + 2.0
        a2 = k2 + 2.0 * a * k + 1.0
        sections.append((
            np.array([1.0, 2.0, 1.0]) / a0,
            np.array([1.0, a1 / a0, a2 / a0]),
        ))
    for b, a in sections:
        y = np.empty_like(x)
        xm1 = xm2 = 0.0
        ym1 = ym2 = 0.0
        for i in range(x.size):
            xi = x[i]
            y[i] = b[0] * xi + b[1] * xm1 + b[2] * xm2 \
                - a[1] * ym1 - a[2] * ym2
            xm2, xm1 = xm1, xi
            ym2, ym1 = ym1, y[i]
        x = y
    return x


def classify_unit_checks():
    """Pin classify() branches that no real encoder can reach via ffmpeg."""
    from provenance.verdict import classify

    cases = [
        # (args, expected_kind)
        # POSSIBLE_TRANSCODE: codec-like transition at a NON-standard knee
        # with a mild cliff. Real codecs are always steep (>= 45 dB/kHz), so
        # only crafted inputs hit this branch.
        (dict(cutoff65=19000.0, e16=0.0001, genuine_24=False, top_band_db=-90.0,
              max_cliff=40.0, cliff_at=19500.0, transition_khz=1.0),
         "POSSIBLE_TRANSCODE"),
        # TRANSCODE via standard knee even with a mild cliff
        (dict(cutoff65=16100.0, e16=0.0001, genuine_24=False, top_band_db=-90.0,
              max_cliff=40.0, cliff_at=16500.0, transition_khz=1.0),
         "TRANSCODE"),
        # TRANSCODE via steep cliff even at a non-standard knee
        (dict(cutoff65=19000.0, e16=0.0001, genuine_24=False, top_band_db=-90.0,
              max_cliff=60.0, cliff_at=19500.0, transition_khz=1.0),
         "TRANSCODE"),
        # AMBIGUOUS_HI_BITRATE: wide rolloff = dark/limited master, not codec
        (dict(cutoff65=12000.0, e16=0.0001, genuine_24=False, top_band_db=-90.0,
              max_cliff=99.0, cliff_at=12000.0, transition_khz=9.0),
         "AMBIGUOUS_HI_BITRATE"),
        # AMBIGUOUS_HI_BITRATE: empty top but no hard cliff
        (dict(cutoff65=16000.0, e16=0.0001, genuine_24=False, top_band_db=-90.0,
              max_cliff=20.0, cliff_at=16000.0, transition_khz=1.0),
         "AMBIGUOUS_HI_BITRATE"),
        # AUTHENTIC_LOSSLESS: content persists to the top of the band
        (dict(cutoff65=0.0, e16=0.1, genuine_24=True, top_band_db=-40.0,
              max_cliff=15.0, cliff_at=0.0, transition_khz=0.0),
         "AUTHENTIC_LOSSLESS"),
    ]
    failures = 0
    for kwargs, want in cases:
        kind, _ = classify(**kwargs)
        ok = kind == want
        print(f"  {'PASS' if ok else 'FAIL'} classify({kwargs['cutoff65']}, "
              f"top={kwargs['top_band_db']}, cliff={kwargs['max_cliff']}, "
              f"t={kwargs['transition_khz']}) -> {kind} (expected {want})")
        failures += 0 if ok else 1
    return failures


def render_checks():
    """Pin the CLI renderer: every verdict kind renders, colors off on plain
    streams, and no candidate / md5 edge cases are handled."""
    from provenance.cli import render
    from provenance.style import Style

    base = {
        "version": "0.1.3",
        "file": {"path": "x.flac", "size": 1.5e6, "codec": "flac",
                 "sample_rate": 44100, "declared_bits": 24, "channels": 2,
                 "duration_s": 180, "md5_zero": False},
        "tags": {"album": "A", "artist": "B", "media": "", "encoder": "Lavf",
                 "replaygain": ""},
        "bitdepth": {"declared_bits": 24, "verdict": "GENUINE_24",
                     "effective_bits": 23, "reasons": ["r1"],
                     "levels": {"peak_dbfs": -3.2, "rms_dbfs": -10.1,
                                "crest_db": 7.0, "clipped_pct": 0.0}},
        "spectrum": {"cutoff65_hz": 12000, "cutoff90_hz": 20100,
                     "energy_above_16k": 0.0, "energy_above_20k": 0.0,
                     "energy_above_26k": 0.0, "brickwall_sharpness": 0.0,
                     "max_cliff_db_per_khz": 76.0, "cliff_at_hz": 19751,
                     "hf_slope_db_per_octave": -0.1, "top_band_db": -109.0},
        "verdict": {"kind": "AUTHENTIC_LOSSLESS", "reasons": ["ok"]},
        "origin": {"candidates": [
            {"confidence": 0.6, "origin": "O1", "evidence": ["e1", "e2"]},
            {"confidence": 0.4, "origin": "O2", "evidence": ["e1"]}],
            "signals": ["s1"], "caveat": "c"},
    }
    checks = []
    for kind in ["AUTHENTIC_LOSSLESS", "TRANSCODE", "POSSIBLE_TRANSCODE",
                 "AMBIGUOUS_HI_BITRATE"]:
        r = dict(base)
        r["verdict"] = {"kind": kind, "reasons": ["a", "b"]}
        out = render(r, Style(on=True))
        checks.append((kind in out and "\x1b[" in out
                       and "0.60" in out and "0.40" in out, kind))
    r = dict(base)
    r["origin"] = {"candidates": [], "signals": [], "caveat": "x"}
    checks.append(("no candidates" in render(r, Style(on=True)),
                   "empty candidates"))
    checks.append(("\x1b[" not in render(base, Style(on=False)),
                   "plain mode"))
    r = dict(base)
    r["file"]["md5_zero"] = True
    checks.append(("unset" in render(r, Style(on=False)), "md5 unset"))

    failures = 0
    for ok, name in checks:
        print(f"  {'PASS' if ok else 'FAIL'} render {name}")
        failures += 0 if ok else 1
    return failures


def dir_expansion_checks(out_dir):
    """CLI accepts directories: recursive scan, sorted order, and an error
    when a directory contains no FLAC files."""
    from provenance.cli import expand_paths

    checks = []
    found = expand_paths([out_dir])
    expected = sorted(os.path.join(r, n)
                      for r, _d, fs in os.walk(out_dir)
                      for n in fs if n.lower().endswith(".flac"))
    checks.append((found == expected, "recursive scan == expected list"))

    # mixed file + dir inputs are allowed and order is preserved
    single = found[0]
    mixed = expand_paths([single, out_dir])
    checks.append((mixed[0] == single and set(mixed) == set(found),
                   "mixed file+dir inputs"))

    failures = 0
    for ok, name in checks:
        print(f"  {'PASS' if ok else 'FAIL'} expand {name}")
        failures += 0 if ok else 1
    return failures


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
    stereo = np.repeat(g16.astype(np.int16), 2)
    with open(p16, "wb") as f:
        stereo.tofile(f)

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

    # Genuine DARK master: the producer lowpassed the mix at an arbitrary,
    # non-codec knee (12.5 kHz) with a real 24 dB/oct EQ. Top band is empty
    # and there is a steep-ish drop - but the rolloff is wide and the knee is
    # not a codec frequency, so it must NOT be called a transcode.
    dark = quantize(
        butter_lowpass_4(synth_mix(noise_floor_db=-80.0, dither_amp=1.0 / 2**23),
                         fc=12500.0, sr=SR),
        24)
    p_dark = os.path.join(tmp, "darkmaster.s24le")
    write_s24(p_dark, dark)
    flac_from_s24(p_dark, os.path.join(args.out_dir, "darkmaster.flac"))
    expected["darkmaster.flac"] = ("GENUINE_24", "AMBIGUOUS_HI_BITRATE")

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

    print("\nclassify() branch checks:")
    failures += classify_unit_checks()

    print("render() smoke checks:")
    failures += render_checks()

    print("dir-expansion checks:")
    failures += dir_expansion_checks(args.out_dir)
    shutil.rmtree(tmp, ignore_errors=True)
    total = len(expected) + 6 + 7 + 2
    print(f"\n{total - failures}/{total} passed")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
