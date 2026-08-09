import numpy as np

FULL24 = 0x7FFFFF


def bit_usage(samples):
    """Per-bit usage histogram for packed 24-bit samples. bits[b] = fraction of
    meaningful samples that have bit b set. The highest used bit yields the
    effective depth; low-bit activity distinguishes genuine 24-bit from padded
    16-bit (and 16-bit from padded lower depths)."""
    flat = np.abs(samples.reshape(-1)).astype(np.uint64)
    meaningful = flat != 0
    total = int(np.count_nonzero(meaningful))
    if total == 0:
        return {
            "meaningful_samples": 0,
            "effective_bits": 0,
            "lsb_usage_pct": 0.0,
            "bits16_usage_pct": 0.0,
            "bits8_usage_pct": 0.0,
        }
    mag = flat[meaningful]
    usage = []
    for b in range(24):
        usage.append(float(np.count_nonzero(mag & (1 << b))) / total * 100.0)
    active = [b for b in range(24) if usage[b] > 1.0]
    effective = 1 + max(active) if active else 0
    lowest_active_bit = min(active) if active else 24
    return {
        "meaningful_samples": total,
        "effective_bits": effective,
        "lowest_active_bit": lowest_active_bit,
        "padding_bits": lowest_active_bit,
        "lsb_usage_pct": usage[0],
        "bits16_usage_pct": usage[15],
        "bits8_usage_pct": usage[7],
    }


def level_stats(samples):
    flat = np.abs(samples.reshape(-1)).astype(np.float64)
    peak = float(np.max(flat)) / FULL24
    peak_db = 20.0 * np.log10(peak) if peak > 0 else -400.0
    rms = float(np.sqrt(np.mean(flat ** 2))) / FULL24
    rms_db = 20.0 * np.log10(rms) if rms > 0 else -400.0
    clipped = float(np.mean(flat >= FULL24)) * 100.0
    return {
        "peak_dbfs": peak_db,
        "rms_dbfs": rms_db,
        "clipped_pct": clipped,
        "crest_db": peak_db - rms_db,
    }


def verdict(declared_bits, usage, levels):
    """Classify the true bit depth of the audio content."""
    lsb = usage["lsb_usage_pct"]
    bits8 = usage["bits8_usage_pct"]
    b16 = usage["bits16_usage_pct"]
    low = usage["lowest_active_bit"]
    pad = usage["padding_bits"]
    eff = usage["effective_bits"]
    reasons = []

    if declared_bits == 24:
        if lsb >= 10.0:
            verdict = "GENUINE_24"
            reasons.append(
                f"lowest bit toggles on {lsb:.1f}% of samples "
                "(the ~50% expected for dithered 24-bit content)"
            )
        elif low >= 8 and b16 >= 40.0 and bits8 < 1.0:
            verdict = "PADDED_16_TO_24"
            reasons.append(
                f"bits 0-7 idle ({lsb:.2f}%) but bits 8-23 carry the "
                f"signal ({b16:.1f}% toggle on bit 15) -> 16-bit content "
                f"shifted into a 24-bit container"
            )
        else:
            verdict = "INCONCLUSIVE_24"
            reasons.append(
                "low-byte activity too weak to prove 24-bit content "
                "(very quiet or compressed audio?)"
            )
        if pad:
            reasons.append(f"lowest active bit = {low} (padding {pad} bits)")
    elif declared_bits == 16:
        if lsb >= 25.0:
            verdict = "GENUINE_16"
            reasons.append(f"lowest byte active on {lsb:.1f}% of samples")
        else:
            verdict = f"REDUCED_TO_{eff}BIT"
            reasons.append(
                f"content only exercises {eff} bits "
                f"(low-byte activity {lsb:.1f}%)"
            )
    else:
        verdict = f"GENUINE_{declared_bits}"
        reasons.append(f"declared {declared_bits}-bit; verifying with histogram")

    if levels["clipped_pct"] > 1.0:
        reasons.append(
            f"{levels['clipped_pct']:.2f}% of samples at full scale "
            "(digital clipping / brickwall-limited master)"
        )
    return {
        "verdict": verdict,
        "reasons": reasons,
        "effective_bits": eff,
        "declared_bits": declared_bits,
        "usage": usage,
        "levels": levels,
    }
