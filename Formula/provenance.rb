class Provenance < Formula
  desc "Audio provenance & authenticity checker: true bit depth, lossy-transcode detection, and likely origin platform"
  homepage "https://github.com/temirvvs/provenance"
  url "https://github.com/temirvvs/provenance/archive/refs/tags/v0.1.1.tar.gz"
  sha256 "1d628b361e983ae7061ed7844928f14a8ef7fe9c193735090d30740f61014e0e"
  license "MIT"

  depends_on "ffmpeg"
  depends_on "python@3.13"

  def install
    python = Formula["python@3.13"].opt_bin/"python3.13"
    venv = libexec/"venv"
    system python, "-m", "venv", venv
    system venv/"bin/pip", "install", "."
    bin.install_symlink venv/"bin/provenance"
  end

  test do
    assert_match "provenance 0.1.1", shell_output("#{bin}/provenance --version")
  end
end
