class Provenance < Formula
  desc "Audio provenance & authenticity checker: true bit depth, lossy-transcode detection, and likely origin platform"
  homepage "https://github.com/temirvvs/provenance"
  url "https://github.com/temirvvs/provenance/archive/refs/tags/v0.1.2.tar.gz"
  sha256 "fa10e36903cf99c103f633637aad7b7d2ab8d70a412051d2f35756475e4304e4"
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
    assert_match "provenance 0.1.2", shell_output("#{bin}/provenance --version")
  end
end
