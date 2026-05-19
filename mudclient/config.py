from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

APP_DIR = "mudclient"


def default_config_dir() -> Path:
    base = Path.home()
    if (appdata := base / "AppData" / "Local").exists():
        return appdata / APP_DIR
    if (xdg := Path.home() / ".config").exists():
        return xdg / APP_DIR
    return base / f".{APP_DIR}"


@dataclass
class HighlightRule:
    pattern: str
    style: str = "ansiyellow"


@dataclass
class TriggerRule:
    pattern: str
    response: str = ""
    enabled: bool = False


@dataclass
class ClientConfig:
    encoding: str = "utf-8"
    log_raw_ansi: bool = False
    highlights: list[HighlightRule] = field(default_factory=list)
    triggers: list[TriggerRule] = field(default_factory=list)


class ConfigStore:
    def __init__(self, config_dir: Path | None = None) -> None:
        self.config_dir = config_dir or default_config_dir()
        self.path = self.config_dir / "config.json"

    def load(self) -> ClientConfig:
        if not self.path.exists():
            return ClientConfig()
        data = json.loads(self.path.read_text(encoding="utf-8"))
        return ClientConfig(
            encoding=data.get("encoding", "utf-8"),
            log_raw_ansi=bool(data.get("log_raw_ansi", False)),
            highlights=[HighlightRule(**r) for r in data.get("highlights", []) if "pattern" in r],
            triggers=[TriggerRule(**r) for r in data.get("triggers", []) if "pattern" in r],
        )

    def save(self, config: ClientConfig) -> None:
        self.config_dir.mkdir(parents=True, exist_ok=True)
        payload: dict[str, Any] = asdict(config)
        self.path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
