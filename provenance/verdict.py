CUTOFF_BANDS = [
    (15500.0, "64-112 kbps MP3 / AAC-HE (low bitrate)"),
    (17000.0, "128 kbps MP3 / 96-128 kbps AAC"),
    (18500.0, "160-192 kbps MP3 / 128-160 kbps AAC / Vorbis ~q4-5"),
    (19500.0, "224-256 kbps MP3 / 192-224 kbps AAC / Vorbis q6-7 / Opus 128"),
    (20500.0, "256-320 kbps MP3 / 256 kbps AAC / Vorbis q8-9 / Opus 192"),
]

# Standardized codec lowpass knees. Real encoders use a near-ideal filter whose
# -5..-60 dB transition spans only ~1-2 kHz and sits at one of these. A
# producer-darkened master uses a real EQ: wide rolloff at an arbitrary knee.
CODEC_KNEES = [16000.0, 16500.0, 20500.0]


def classify(cutoff65, e16, genuine_24, top_band_db, max_cliff, cliff_at,
             transition_khz=0.0):
    """Return (kind, detail). kind in {AUTHENTIC_LOSSLESS, TRANSCODE,
    POSSIBLE_TRANSCODE, AMBIGUOUS_HI_BITRATE}."""
    reasons = []
    top_empty = top_band_db < -85.0
    has_cliff = max_cliff >= 30.0
    # A lossy lowpass is a near-ideal filter: passband -> silence in under
    # ~2 kHz. A real EQ lowpass (even a steep 48-96 dB/oct one) rolls off over
    # several kHz. This is the discriminator between codec and dark master.
    codec_like = 0.0 < transition_khz < 2.0
    standard_knee = any(abs(cutoff65 - knee) < 1000.0 for knee in CODEC_KNEES)

    if has_cliff and top_empty:
        if codec_like and (standard_knee or max_cliff >= 45.0):
            kind = "TRANSCODE"
            reasons.append(
                f"near-ideal lowpass brickwall: {max_cliff:.0f} dB drop in "
                f"1 kHz at {cliff_at:.0f} Hz, transition only "
                f"{transition_khz:.1f} kHz wide, nothing above (top band "
                f"{top_band_db:.0f} dB) -> lossy encode"
            )
        elif codec_like:
            kind = "POSSIBLE_TRANSCODE"
            reasons.append(
                f"near-ideal lowpass (transition {transition_khz:.1f} kHz) at "
                f"non-standard cutoff {cliff_at:.0f} Hz; could be a codec or "
                "a digital brickwall EQ"
            )
        else:
            kind = "AMBIGUOUS_HI_BITRATE"
            reasons.append(
                f"steep-ish drop ({max_cliff:.0f} dB/kHz at "
                f"{cliff_at:.0f} Hz) but the rolloff is {transition_khz:.1f} "
                "kHz wide at a non-codec knee: consistent with an "
                "intentionally dark/limited master, not a codec filter"
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
