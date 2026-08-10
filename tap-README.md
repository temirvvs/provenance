# homebrew-provenance

Homebrew tap for [provenance](https://github.com/temirvvs/provenance), an audio provenance & authenticity checker.

## Install

```sh
brew install temirvvs/provenance/provenance
```

Requires a Homebrew-installed `ffmpeg` (pulled in automatically as a dependency).

## Usage

```sh
provenance file.flac            # human-readable report
provenance --json file.flac     # machine-readable output
```

## Updating

After a new release of provenance, update `Formula/provenance.rb`:

1. Bump `url` to the new tag (`refs/tags/v0.2.0.tar.gz`)
2. Replace `sha256` (fetch via `curl -sL <tarball-url> | shasum -a 256`)
3. Bump the `test` block assertion to match the new `--version` output
