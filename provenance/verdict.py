CUTOFF_BANDS = [
    (15500.0, "64-112 kbps MP3 / AAC-HE (low bitrate)"),
    (17000.0, "128 kbps MP3 / 96-128 kbps AAC"),
    (18500.0, "160-192 kbps MP3 / 128-160 kbps AAC / Vorbis ~q4-5"),
    (19500.0, "224-256 kbps MP3 / 192-224 kbps AAC / Vorbis q6-7 / Opus 128"),
    (20500.0, "256-320 kbps MP3 / 256 kbps AAC / Vorbis q8-9 / Opus 192"),
]


def classify(cutoff65, e16, e20, sharpness, is_lossless_container, genuine_24,
             effective_bits, top_band_db, max_cliff, cliff_at):
    """Return (kind, detail). kind in {AUTHENTIC_LOSSLESS, TRANSCODE,
    POSSIBLE_TRANSCODE, AMBIGUOUS_HI_BITRATE}."""
    reasons = []
    top_empty = top_band_db < -85.0
    has_cliff = max_cliff >= 30.0
    cliff_near_cutoff = abs(cliff_at - cutoff65) < 3000.0

    if has_cliff and top_empty:
        if max_cliff >= 45.0 or cliff_near_cutoff:
            kind = "TRANSCODE"
            reasons.append(
                f"hard lowpass brickwall: {max_cliff:.0f} dB drop in 1 kHz "
                f"at {cliff_at:.0f} Hz right at the cutoff, with nothing "
                f"above (top band {top_band_db:.0f} dB) -> lossy encode"
            )
        else:
            kind = "POSSIBLE_TRANSCODE"
            reasons.append(
                f"steep lowpass (max {max_cliff:.0f} dB/kHz at "
                f"{cliff_at:.0f} Hz) with empty top band"
            )
        if cutoff65 >= 20500.0:
            reasons.append("cutoff near Nyquist; band hint is uncertain")
            return kind, reasons
        band = None
        for threshold, label in CUTOFF_BANDS:
            if cutoff65 < threshold:
                band = label
                break
        if band is None:
            band = CUTOFF_BANDS[-1][1]
        reasons.append(f"consistent with {band}")
        if e16 <= 0.0005:
            reasons.append("almost no energy above 16 kHz")
        if genuine_24:
            reasons.append("note: genuinely 24-bit content that still bricks "
                           "around the cutoff suggests an upsampled lossy source")
        return kind, reasons

    if top_empty:
        return "AMBIGUOUS_HI_BITRATE", [
            f"no hard cliff (max {max_cliff:.0f} dB/kHz) but the top of "
            f"the band is empty ({top_band_db:.0f} dB); could be a gentle "
            "codec lowpass or a dark/limited master", ]

    return "AUTHENTIC_LOSSLESS", [
        f"no lossy brickwall (steepest drop {max_cliff:.0f} dB/kHz; "
        f"content persists to the top of the band, "
        f"{top_band_db:.0f} dB at Nyquist) -> genuine wideband signal", ]


def describe(is_lossless_container, codec):
    return {
        "is_lossless_container": is_lossless_container,
        "codec": codec,
    }
