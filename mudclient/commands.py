from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ParsedCommand:
    name: str
    args: list[str]


def parse_local_command(text: str) -> ParsedCommand | None:
    if not text.startswith("/"):
        return None
    parts = text[1:].strip().split()
    if not parts:
        return ParsedCommand(name="help", args=[])
    return ParsedCommand(parts[0].lower(), parts[1:])


def validate_host(host: str) -> bool:
    host = host.strip()
    return bool(host) and " " not in host


def validate_port(port: int) -> bool:
    return 1 <= int(port) <= 65535
