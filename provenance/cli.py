import argparse
import json
import os
import sys

from . import __version__
from .check import check
from .probe import ProbeError
from .style import style_for

ICONS = {
    "AUTHENTIC_LOSSLESS": "\u2713",
    "TRANSCODE": "\u2717",
    "POSSIBLE_TRANSCODE": "\u26a0",
    "AMBIGUOUS_HI_BITRATE": "\u25d0",
}
DEPTH_ICONS = {"PADDED_16_TO_24": "\u26a0"}
RULE = "\u2500" * 60
BAR_FULL = "\u2588"
BAR_EMPTY = "\u2591"


def fmt_khz(hz):
    return f"{hz / 1000.0:.1f} kHz" if hz else "none"


def conf_bar(conf):
    filled = int(round(conf * 10))
    return BAR_FULL * filled + BAR_EMPTY * (10 - filled)


def render(result, st):
    f = result["file"]
    t = result["tags"]
    b = result["bitdepth"]
    s = result["spectrum"]
    v = result["verdict"]
    o = result["origin"]

    W = 11
    lines = []

    def field(label, value):
        return f"  {st.cyan(label):<{W}} {value}"

    def bullet(text):
        return f"    {st.grey('-')} {text}"

    def section(title):
        return st.cyan_bold(f"\u25a0 {title}")

    # header
    lines.append(st.cyan_bold(f"provenance {result['version']}"))
    lines.append(st.dim(RULE))

    # file
    lines.append(section("FILE"))
    lines.append(field("path", st.bold(f["path"])))
    lines.append(field(
        "size",
        f"{f['size'] / 1e6:.1f} MB   {f['codec'].upper()} "
        f"{f['sample_rate']} Hz / {f['declared_bits']}-bit / "
        f"{f['channels']}ch   {f['duration_s']:.0f}s"))
    md5 = "unset" if f["md5_zero"] else "set"
    lines.append(field("md5", st.dim(md5)))
    lines.append("")

    # tags
    if any((t["album"], t["artist"], t["media"], t["encoder"],
            t["replaygain"])):
        lines.append(section("TAGS"))
        if t["album"]:
            lines.append(field("album", t["album"]))
        if t["artist"]:
            lines.append(field("artist", t["artist"]))
        if t["media"]:
            lines.append(field("media", t["media"]))
        if t["encoder"]:
            lines.append(field("encoder", t["encoder"]))
        if t["replaygain"]:
            lines.append(field("replaygain", st.dim("present")))
        lines.append("")

    # true bit depth
    lines.append(section("TRUE BIT DEPTH"))
    lines.append(field("declared", f"{b['declared_bits']}-bit"))
    paint = st.depth_kind(b["verdict"])
    icon = DEPTH_ICONS.get(b["verdict"], ICONS["AUTHENTIC_LOSSLESS"])
    lines.append(field(
        "verdict",
        f"{paint(icon)} {st.bold(paint(b['verdict']))}  "
        f"{st.dim('(effective ' + str(b['effective_bits']) + ' bits)')}"))
    for r in b["reasons"]:
        lines.append(bullet(r))
    lv = b["levels"]
    lines.append(field(
        "levels",
        f"peak {lv['peak_dbfs']:.1f} dBFS   "
        f"RMS {lv['rms_dbfs']:.1f} dBFS   "
        f"crest {lv['crest_db']:.1f} dB   "
        f"clipped {lv['clipped_pct']:.3f}%"))
    lines.append("")

    # spectrum
    lines.append(section("SPECTRUM"))
    lines.append(field("cutoff65", st.cyan(fmt_khz(s['cutoff65_hz']))))
    lines.append(field("cutoff-90", st.cyan(fmt_khz(s['cutoff90_hz']))))
    lines.append(field(
        "energy",
        f">16k {s['energy_above_16k'] * 100:.2f}%   "
        f">20k {s['energy_above_20k'] * 100:.2f}%   "
        f">26k {s['energy_above_26k'] * 100:.2f}%"))
    lines.append(field(
        "brickwall",
        f"{s['brickwall_sharpness']:.2f}x   "
        f"max cliff {s['max_cliff_db_per_khz']:.0f} dB/kHz @ "
        f"{s['cliff_at_hz']/1000:.1f}k   hf slope "
        f"{s['hf_slope_db_per_octave']:.1f} dB/oct   "
        f"top-of-band {s['top_band_db']:.0f} dB"))
    lines.append("")

    # verdict
    lines.append(section("VERDICT"))
    paint = st.verdict_kind(v["kind"])
    icon = ICONS.get(v["kind"], "\u25d0")
    lines.append(f"  {paint(icon)} {st.bold(paint(v['kind']))}")
    for r in v["reasons"]:
        lines.append(bullet(r))
    lines.append("")

    # likely origin
    lines.append(section("LIKELY ORIGIN"))
    if o["candidates"]:
        top_conf = max(c["confidence"] for c in o["candidates"])
        for c in o["candidates"]:
            paint = st.green if c["confidence"] == top_conf else st.dim
            bar = conf_bar(c["confidence"])
            bar_color = (st.green if c["confidence"] == top_conf
                         else st.grey)
            lines.append(
                f"  {paint('%.2f' % c['confidence'])} {bar_color(bar)} "
                f"{paint(c['origin'])}")
            for ev in c["evidence"][:2]:
                lines.append(f"      {st.dim(ev)}")
    else:
        lines.append(f"  {st.dim('no candidates')}")
    if o["signals"]:
        lines.append(f"  {st.dim('signals:')}")
        for sig in o["signals"]:
            lines.append(f"    {st.grey('-')} {sig}")
    lines.append(f"  {st.dim('caveat:')} {o['caveat']}")
    return "\n".join(lines)


def expand_paths(args):
    """Accept files and/or directories. Directories are scanned recursively
    for FLAC files, preserving a deterministic (sorted) order."""
    paths = []
    for a in args:
        if os.path.isdir(a):
            for root, _dirs, files in os.walk(a):
                for name in sorted(files):
                    if name.lower().endswith(".flac"):
                        paths.append(os.path.join(root, name))
        else:
            paths.append(a)
    return paths


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="provenance",
        description="Audio provenance checker: true bit depth, lossy-transcode "
                    "detection, and likely origin platform.",
    )
    parser.add_argument("files", nargs="+", metavar="FILE",
                        help="audio files (or directories scanned for "
                             "*.flac recursively)")
    parser.add_argument("--json", action="store_true",
                        help="emit machine-readable JSON")
    parser.add_argument("--fft", type=int, default=16384,
                        help="FFT window size (default 16384)")
    parser.add_argument("--segments", type=int, default=512,
                        help="max spectral segments averaged (default 512)")
    parser.add_argument("--version", action="version",
                        version=f"%(prog)s {__version__}")
    args = parser.parse_args(argv)

    st = style_for(sys.stdout)
    results = []
    failed = False
    paths = expand_paths(args.files)
    if not paths:
        print(st.red("no FLAC files found"), file=sys.stderr)
        return 1
    for path in paths:
        try:
            results.append(check(path))
        except ProbeError as e:
            print(st.red(f"ERROR {path}: {e}"), file=sys.stderr)
            failed = True

    if args.json:
        print(json.dumps(results, indent=2))
    else:
        for i, r in enumerate(results):
            if i:
                print()
                print(st.dim(RULE))
            print(render(r, st))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
