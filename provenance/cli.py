import argparse
import json
import sys

from . import __version__
from .check import check
from .probe import ProbeError


def fmt_khz(hz):
    return f"{hz / 1000.0:.1f} kHz" if hz else "none"


def render(result):
    f = result["file"]
    t = result["tags"]
    b = result["bitdepth"]
    s = result["spectrum"]
    v = result["verdict"]
    o = result["origin"]

    lines = []
    lines.append(f"provenance {result['version']}")
    lines.append("=" * 60)
    lines.append(f"FILE    {f['path']}")
    lines.append(f"        {f['size'] / 1e6:.1f} MB   {f['codec'].upper()} "
                 f"{f['sample_rate']} Hz / {f['declared_bits']}-bit / "
                 f"{f['channels']}ch   {f['duration_s']:.0f}s   "
                 f"{'MD5:UNSET' if f['md5_zero'] else 'MD5:set'}")
    lines.append("")
    lines.append("TAGS")
    if t["album"]:
        lines.append(f"  album    {t['album']}")
    if t["artist"]:
        lines.append(f"  artist   {t['artist']}")
    if t["media"]:
        lines.append(f"  media    {t['media']}")
    if t["encoder"]:
        lines.append(f"  encoder  {t['encoder']}")
    if t["replaygain"]:
        lines.append("  replaygain  present")
    lines.append("")
    lines.append("TRUE BIT DEPTH")
    lines.append(f"  declared   {b['declared_bits']}-bit")
    lines.append(f"  verdict    {b['verdict']}  (effective {b['effective_bits']} bits)")
    for r in b["reasons"]:
        lines.append(f"    - {r}")
    lv = b["levels"]
    lines.append(f"  levels     peak {lv['peak_dbfs']:.1f} dBFS   "
                 f"RMS {lv['rms_dbfs']:.1f} dBFS   "
                 f"crest {lv['crest_db']:.1f} dB   "
                 f"clipped {lv['clipped_pct']:.3f}%")
    lines.append("")
    lines.append("SPECTRUM")
    lines.append(f"  cutoff(peak-65dB)  {fmt_khz(s['cutoff65_hz'])}   "
                 f"cutoff(-90dB) {fmt_khz(s['cutoff90_hz'])}")
    lines.append(f"  energy >16k {s['energy_above_16k'] * 100:.2f}%   "
                 f">20k {s['energy_above_20k'] * 100:.2f}%   "
                 f">26k {s['energy_above_26k'] * 100:.2f}%")
    lines.append(f"  brickwall ratio  {s['brickwall_sharpness']:.2f}x   "
                 f"max cliff {s['max_cliff_db_per_khz']:.0f} dB/kHz @ "
                 f"{s['cliff_at_hz']/1000:.1f}k   hf slope "
                 f"{s['hf_slope_db_per_octave']:.1f} dB/oct   "
                 f"top-of-band {s['top_band_db']:.0f} dB")
    lines.append("")
    lines.append("VERDICT")
    lines.append(f"  {v['kind']}")
    for r in v["reasons"]:
        lines.append(f"    - {r}")
    lines.append("")
    lines.append("LIKELY ORIGIN")
    for c in o["candidates"]:
        lines.append(f"  [{c['confidence']:.2f}] {c['origin']}")
        lines.append(f"      {c['evidence'][0]}")
    if o["signals"]:
        lines.append("  signals:")
        for sig in o["signals"]:
            lines.append(f"    - {sig}")
    lines.append(f"  caveat: {o['caveat']}")
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="provenance",
        description="Audio provenance checker: true bit depth, lossy-transcode "
                    "detection, and likely origin platform.",
    )
    parser.add_argument("files", nargs="+", metavar="FILE",
                        help="audio files to analyze")
    parser.add_argument("--json", action="store_true",
                        help="emit machine-readable JSON")
    parser.add_argument("--fft", type=int, default=16384,
                        help="FFT window size (default 16384)")
    parser.add_argument("--segments", type=int, default=512,
                        help="max spectral segments averaged (default 512)")
    parser.add_argument("--version", action="version",
                        version=f"%(prog)s {__version__}")
    args = parser.parse_args(argv)

    results = []
    failed = False
    for path in args.files:
        try:
            results.append(check(path))
        except ProbeError as e:
            print(f"ERROR {path}: {e}", file=sys.stderr)
            failed = True

    if args.json:
        print(json.dumps(results, indent=2))
    else:
        for i, r in enumerate(results):
            if i:
                print()
            print(render(r))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
