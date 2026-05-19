from __future__ import annotations

import re

ANSI_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
UNSAFE_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1a\x1c-\x1f\x7f]")
ANSI_SGR_RE = re.compile(r"\x1b\[([0-9;]*)m")
BARE_SGR_RE = re.compile(r"(?<!\x1b)\[([0-9;]*)m")


def strip_ansi(text: str) -> str:
    return ANSI_RE.sub("", text)


def normalize_ansi_sequences(text: str) -> str:
    """Convert bare SGR markers like ``[31m`` into real ANSI escapes."""
    return BARE_SGR_RE.sub(lambda m: f"\x1b[{m.group(1)}m", text)


def sanitize_for_terminal(text: str) -> str:
    # Keep tabs/newlines/carriage returns, remove most other control chars.
    # Some MUD servers omit the ESC byte for SGR sequences (e.g. "[31m").
    return UNSAFE_RE.sub("", normalize_ansi_sequences(text))


def split_ansi_segments(text: str) -> list[tuple[str, str | None]]:
    """Split text into (segment, style_tag) tuples for Tk rendering."""
    out: list[tuple[str, str | None]] = []
    style: str | None = None
    i = 0
    for m in ANSI_SGR_RE.finditer(text):
        if m.start() > i:
            out.append((text[i:m.start()], style))
        codes = [c for c in m.group(1).split(';') if c]
        if not codes or '0' in codes:
            style = None
        else:
            fg = next((c for c in reversed(codes) if c in {'30','31','32','33','34','35','36','37','90','91','92','93','94','95','96','97'}), None)
            style = f"ansi_{fg}" if fg else style
        i = m.end()
    if i < len(text):
        out.append((text[i:], style))
    return out
