from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("provenance")
except PackageNotFoundError:  # running from source without install
    __version__ = "0.1.2"
