DIGITAL_STORES = "Bandcamp / Qobuz / 7digital / Tidal HiFi / Deezer HiFi (lossless download)"


def band_label(cutoff65):
    if cutoff65 >= 20500.0:
        return "lossless-or-very-high-bitrate-lossy"
    if cutoff65 >= 19500.0:
        return "high-bitrate lossy (>=~256 kbps)"
    if cutoff65 >= 18500.0:
        return "mid-bitrate lossy (~160-224 kbps)"
    if cutoff65 >= 17000.0:
        return "128 kbps-class lossy"
    if cutoff65 >= 15500.0:
        return "low-bitrate lossy (64-112 kbps)"
    return "below 15.5 kHz (very low bitrate / filtered)"


def assess(kind, genuine_24, declared_bits, effective_bits, cutoff65, e16,
           e20, sharpness, media_tag, vendor_tag, md5_zero, album, artist,
           replaygain, top_band_db):
    """Best-effort origin ranking. Returns a list of dicts:
    {origin, confidence, evidence, caveat}."""
    candidates = []
    caveat = "origin cannot be proven from audio alone; this is a ranked heuristic"

    def add(origin, confidence, evidence):
        candidates.append({
            "origin": origin,
            "confidence": confidence,
            "evidence": evidence,
            "caveat": caveat,
        })

    if kind == "AUTHENTIC_LOSSLESS":
        evidence = [f"no lossy lowpass fingerprint (wideband to Nyquist, "
                    f"top band {top_band_db:.0f} dB)"]
        if genuine_24:
            evidence.append("genuine 24-bit content (not padded)")
            if media_tag and "digital" in media_tag.lower():
                evidence.append("tagged Media=Digital Media")
                add(DIGITAL_STORES, 0.75, evidence)
            else:
                add("hi-res digital store (Bandcamp/Qobuz/...) "
                    "or a 24-bit master tape transfer", 0.6, evidence)
            if album:
                evidence.append(f"album: {album}")
            add("Bandcamp (when album is released there)", 0.45, evidence)
        else:
            if declared_bits <= 16:
                evidence.append("16-bit content, full spectrum")
                if media_tag and "digital" in media_tag.lower():
                    evidence.append("tagged Media=Digital Media")
                    add("digital store lossless (Bandcamp/7digital/...)", 0.6, evidence)
                else:
                    add("CD rip (most common for 16/44.1 lossless)", 0.6, evidence)
            add("lossless digital store or CD", 0.5, evidence)

    elif kind in ("TRANSCODE", "POSSIBLE_TRANSCODE"):
        evidence = [f"lowpass cutoff ~{cutoff65:.0f} Hz",
                    f"origin likely {band_label(cutoff65)}"]
        if cutoff65 < 17000.0:
            add("SoundCloud free stream / YouTube (low-bitrate lossy)", 0.55, evidence)
        elif cutoff65 < 19500.0:
            add("SoundCloud Go+ / Spotify Free / low-bitrate stream", 0.5, evidence)
        else:
            add("high-bitrate streaming (Spotify Premium / Apple Music "
                "/ Deezer / Tidal)", 0.5, evidence)
        if genuine_24:
            add("lossy source upsampled + repacked to 24-bit FLAC "
                "(looks 'hi-res', is not)", 0.4, evidence)
        if cutoff65 >= 19500.0 and e20 > 0.0005:
            add("vinyl rip transcoded to lossy", 0.2, evidence)

    else:  # AMBIGUOUS_HI_BITRATE
        evidence = [f"cutoff ~{cutoff65:.0f} Hz (ambiguous)",
                    "full-ish bandwidth; cannot separate lossless from "
                    "very high bitrate lossy"]
        add("lossless digital release", 0.4, evidence)
        add("high-bitrate streaming transcode (Spotify/Apple/Deezer)", 0.4, evidence)

    signals = []
    if vendor_tag:
        signals.append(f"tagged with {vendor_tag} (tags rewritten by a "
                       "tagging tool, original encoder tags lost)")
    if md5_zero:
        signals.append("FLAC STREAMINFO MD5 is unset (file was re-encoded "
                       "or written without checksum)")
    if replaygain:
        signals.append("ReplayGain tags present")
    return candidates, signals, caveat
