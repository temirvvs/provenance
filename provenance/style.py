"""ANSI styling for the provenance CLI.

Colors are enabled only when stdout is a TTY, forced on with
CLICOLOR_FORCE / FORCE_COLOR, and disabled whenever NO_COLOR is set.
When disabled every painter returns its input untouched, so output stays
plain-text for pipes, files, and tests.
"""

import os
import sys


class Style:
    RESET = "\033[0m"

    def __init__(self, on):
        self.on = on
        self.bold = self._paint("\033[1m")
        self.dim = self._paint("\033[2m")
        self.cyan = self._paint("\033[36m")
        self.cyan_bold = self._paint("\033[1;36m")
        self.green = self._paint("\033[32m")
        self.yellow = self._paint("\033[33m")
        self.red = self._paint("\033[31m")
        self.magenta = self._paint("\033[35m")
        self.grey = self._paint("\033[90m")

    def _paint(self, code):
        def wrap(text):
            if not self.on or not text:
                return text
            return f"{code}{text}{Style.RESET}"
        return wrap

    def verdict_kind(self, kind):
        """Painter for a verdict kind, by severity."""
        if kind == "AUTHENTIC_LOSSLESS":
            return self.green
        if kind == "TRANSCODE":
            return self.red
        if kind == "POSSIBLE_TRANSCODE":
            return self.yellow
        return self.magenta

    def depth_kind(self, verdict):
        if verdict.startswith("GENUINE"):
            return self.green
        return self.yellow


def color_enabled(stream=None):
    if "NO_COLOR" in os.environ:
        return False
    if os.environ.get("CLICOLOR_FORCE") or os.environ.get("FORCE_COLOR"):
        return True
    if stream is None:
        stream = sys.stdout
    return bool(getattr(stream, "isatty", lambda: False)())


def style_for(stream=None):
    return Style(color_enabled(stream))
