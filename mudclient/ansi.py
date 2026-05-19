from __future__ import annotations

import re

ANSI_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
UNSAFE_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def strip_ansi(text: str) -> str:
    return ANSI_RE.sub("", text)


def sanitize_for_terminal(text: str) -> str:
    # Keep tabs/newlines/carriage returns, remove most other control chars.
    return UNSAFE_RE.sub("", text)
