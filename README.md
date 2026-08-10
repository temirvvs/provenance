<div align="center">

# provenance

**Audio provenance & authenticity checker** — reveal a music file's *true* bit depth, detect lossy → lossless transcodes (the "MP3 labeled as hi-res" scam), and guess where the file originally came from.

[![Python](https://img.shields.io/badge/python-%3E%3D3.10-blue)](#install)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Dependency: numpy](https://img.shields.io/badge/deps-numpy-orange)](#install)

</div>

---

## What it does

Given a single audio file, `provenance` answers three questions:

| # | Question | Detection method |
|---|---|---|
| 1 | **Is this file really the bit depth it claims?** | Analyzes low-bit activity. A dithered 24-bit master toggles its LSB ~50% of the time; 16-bit content shifted into a 24-bit container leaves bits 0–7 idle. |
| 2 | **Was this "lossless" file re-encoded from a lossy source?** | Spectral analysis. Lossy codecs (MP3/AAC/Ogg) lowpass the spectrum, leaving a hard brickwall and silence above the cutoff. Genuine masters carry noise to Nyquist. |
| 3 | **Where did this file likely come from?** | Ranked heuristics from cutoff frequency bands (fingerprints the source codec/bitrate), FLAC STREAMINFO MD5 presence, and tags. |

> ⚠️ **Origin is a heuristic, not proof.** Lossless files contain no provenance watermark, and different stores sell the same master. Caveats are printed with every report.

---

## Install

Requires **Python ≥ 3.10**, **numpy**, and **ffmpeg** on your `PATH`.

```sh
pip install git+https://github.com/temirvvs/provenance.git
```

Or install from a local checkout (editable, for development):

```sh
git clone https://github.com/temirvvs/provenance.git
cd provenance
python -m venv .venv && source .venv/bin/activate
pip install -e .
```

## Usage

```sh
provenance track.flac             # human-readable report
provenance --json track.flac      # machine-readable JSON (one object per file)
provenance a.flac b.flac ...      # analyze multiple files
provenance ~/music/               # scan a directory recursively for *.flac
```

### Example report

```
FILE    ~/downloads/Sickboyrari_Bloodrain_07_Amongst The Dead.flac
        19.4 MB   FLAC 44100 Hz / 24-bit / 2ch   107s   MD5:UNSET

TRUE BIT DEPTH
  declared   24-bit
  verdict    GENUINE_24  (effective 23 bits)
    - lowest bit toggles on 50.0% of samples (the ~50% expected for dithered 24-bit content)
  levels     peak 0.0 dBFS   RMS -11.8 dBFS   crest 11.8 dB   clipped 0.446%

SPECTRUM
  cutoff(peak-65dB)  20.2 kHz   cutoff(-90dB) 22.1 kHz
  energy >16k 0.01%   >20k 0.00%   >26k 0.00%
  brickwall ratio  0.57x   max cliff 11 dB/kHz @ 19.9k   top-of-band -67 dB

VERDICT
  AUTHENTIC_LOSSLESS
    - no lossy brickwall (steepest drop 11 dB/kHz; content persists to the top
      of the band, -67 dB at Nyquist) -> genuine wideband signal

LIKELY ORIGIN
  [0.75] Bandcamp / Qobuz / 7digital / Tidal HiFi / Deezer HiFi (lossless download)
  [0.45] Bandcamp (when album is released there)
  signals:
    - FLAC STREAMINFO MD5 is unset (file was re-encoded or written without checksum)
    - ReplayGain tags present
  caveat: origin cannot be proven from audio alone; this is a ranked heuristic
```

---

## How it works

### Decode at native depth (the critical step)

`ffmpeg` decodes 24-bit files to **packed `s24le`** (3 bytes) and 16-bit files
to `s16le`, always at the file's native sample rate and channel count. Two
common decode choices silently break the analysis:

- **Resampling** (`-ac`/`-ar` downmix/rate change) re-dithers the signal and
  fakes low-bit noise.
- **`s32le`** right-aligns 24-bit samples inside a 32-bit word, shifting the
  real LSB up to bit 8 — which makes genuine 24-bit content *look* like
  padded 16-bit (this exact bug produced a false "inauthentic" verdict in
  early development).

### Verdicts

| Kind | Meaning |
|---|---|
| `AUTHENTIC_LOSSLESS` | Wideband spectrum to Nyquist, no lossy brickwall |
| `TRANSCODE` | Lossless container re-encoded from a lossy source (MP3→FLAC, etc.) |
| `POSSIBLE_TRANSCODE` | Steep lowpass + empty top band, not sharp enough to be certain |
| `UPSCALED_16_IN_24` | Genuine lossless chain, but 16-bit content in a 24-bit container (fake hi-res) |
| `AMBIGUOUS_HI_BITRATE` | No hard cliff but empty top band — dark master or gentle codec lowpass |

### Transcode detection

A lossy codec lowpasses the spectrum. `provenance` finds the steepest drop in
any 1 kHz window above 8 kHz (`max_cliff_db_per_khz`) and checks whether the
top band is empty (`< -85 dB`). The discriminator is **both together**: a real
master can drop steeply into silence (a "dark" master), but a lossy encode
drops hard *at a codec cutoff* with nothing above it.

### Origin heuristics

- **Cutoff frequency** fingerprints the source: ~16 kHz → 128 kbps MP3 /
  96–128 kbps AAC; ~20.5 kHz → 256 kbps AAC / 320 kbps MP3; wideband →
  lossless.
- **FLAC STREAMINFO MD5**: unset MD5 strongly suggests the file was
  re-encoded (genuine FLAC downloads ship with the checksum).
- **Tags**: encoder vendor string, `MEDIA`, ReplayGain.

---

## Testing

A synthetic regression suite validates the tool against known ground truth:

```sh
python scripts/make_fixtures.py /tmp/provtest --verify
```

This generates 5 fixtures — genuine 24-bit, 16-bit padded into 24-bit
(`UPSCALED_16_IN_24`), genuine 16-bit CD-style, and 128k/320k MP3→FLAC
transcodes (`TRANSCODE`) — runs `provenance` on each, and asserts the expected
verdicts. Currently **5/5 pass**.

---

## Limitations

- **Origin is a guess.** No lossless file contains its provenance. The tool
  ranks the most probable sources and explains why.
- **Dark masters.** Genuine content that is silent above ~16 kHz with no
  dither can be misread as a transcode; high-confidence transcode verdicts
  require the hard-cliff signature.
- **320k MP3 / 256k AAC** have cutoffs near 20 kHz, close to CD bandwidth —
  spectrally hard to separate from true lossless.

---

## License

[MIT](LICENSE) © 2026 Ghaith Altemimi
