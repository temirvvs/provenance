import numpy as np


def blackman_harris(n):
    a = np.array([0.35875, -0.48829, 0.14128, -0.01168])
    k = np.arange(n, dtype=np.float64)
    return a[0] + a[1] * np.cos(2 * np.pi * k / n) \
        + a[2] * np.cos(4 * np.pi * k / n) \
        + a[3] * np.cos(6 * np.pi * k / n)


def average_spectrum(mono, rate, fft_size=16384, max_segments=512):
    n = mono.size
    if n < fft_size:
        raise ValueError("audio shorter than one FFT window")
    window = blackman_harris(fft_size)
    hop = max(fft_size // 2, n // max_segments)
    starts = np.arange(0, max(1, n - fft_size), hop)
    bins = fft_size // 2 + 1
    total = np.zeros(bins)
    for s in starts:
        chunk = mono[s:s + fft_size]
        if chunk.size < fft_size:
            chunk = np.pad(chunk, (0, fft_size - chunk.size))
        spec = np.fft.rfft(chunk * window)
        total += np.abs(spec) ** 2
    return total / len(starts), rate / fft_size


def spectrum_metrics(power, binw):
    """Derive cutoff, band energies and brickwall sharpness from the averaged
    power spectrum (power = mean |X|^2 per bin)."""
    peak = float(np.max(power))
    if peak <= 0:
        raise ValueError("empty spectrum")
    p = power / peak
    db = 10.0 * np.log10(p + 1e-300)
    freqs = np.arange(power.size, dtype=np.float64) * binw

    def last_above(rel):
        mask = p > rel
        idx = np.where(mask)[0]
        return (float(freqs[idx[-1]]), int(idx[-1])) if idx.size else (0.0, 0)

    cutoff65, idx65 = last_above(10 ** (-65.0 / 10.0))
    cutoff90, idx90 = last_above(10 ** (-90.0 / 10.0))

    def band_energy(lo, hi):
        m = (freqs >= lo) & (freqs < hi)
        if not np.any(m):
            return 0.0
        return float(np.sum(p[m]) / np.sum(p))

    e16 = band_energy(16000.0, 24000.0)
    e20 = band_energy(20000.0, 24000.0)
    e26 = band_energy(26000.0, 96000.0)

    sharpness = 0.0
    if idx65 > 0:
        span = int(max(8, round(2000.0 / binw)))
        below_lo = max(0, idx65 - span)
        below_drop = db[below_lo] - db[idx65]
        above_hi = min(db.size - 1, idx65 + span)
        above_drop = db[idx65] - db[above_hi]
        if below_drop > 0.5:
            sharpness = float(above_drop / below_drop)

    max_cliff = 0.0
    cliff_at = 0.0
    win = int(max(4, round(1000.0 / binw)))
    lo = max(1, int(round(8000.0 / binw)))
    hi = db.size - win
    for i in range(lo, hi):
        drop = db[i] - db[i + win]
        if drop > max_cliff:
            max_cliff = float(drop)
            cliff_at = float(freqs[i])

    slope = 0.0
    if idx65 > 0:
        lo_i = max(1, int(idx65 * 0.4))
        hi_i = max(lo_i + 1, int(idx65 * 0.85))
        x = np.log10(freqs[lo_i:hi_i])
        y = db[lo_i:hi_i]
        slope = float(np.polyfit(x, y, 1)[0])

    return {
        "peak_db": float(db[idx65] if idx65 else db[0]),
        "cutoff65_hz": cutoff65,
        "cutoff90_hz": cutoff90,
        "energy_above_16k": e16,
        "energy_above_20k": e20,
        "energy_above_26k": e26,
        "brickwall_sharpness": sharpness,
        "max_cliff_db_per_khz": max_cliff,
        "cliff_at_hz": cliff_at,
        "hf_slope_db_per_octave": slope,
        "top_band_db": float(db[-max(1, int(1000.0 / binw)):].max()) if db.size else -400,
    }
