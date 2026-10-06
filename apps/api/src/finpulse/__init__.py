"""FinPulse backend."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("finpulse-api")
except PackageNotFoundError:  # running from a source tree without an install
    __version__ = "0.0.0+unknown"
