from __future__ import annotations

from datetime import datetime
from pathlib import Path

from .ansi import strip_ansi
from .config import default_config_dir


class SessionLogger:
    def __init__(self, base_dir: Path | None = None, keep_ansi: bool = False) -> None:
        cfg = base_dir or default_config_dir()
        self.logs_dir = cfg / "logs"
        self.keep_ansi = keep_ansi
        self.file: Path | None = None

    def start(self) -> Path:
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        self.file = self.logs_dir / f"session-{ts}.log"
        self.file.write_text("", encoding="utf-8")
        return self.file

    def stop(self) -> None:
        self.file = None

    def write_line(self, text: str) -> None:
        if not self.file:
            return
        payload = text if self.keep_ansi else strip_ansi(text)
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self.file.open("a", encoding="utf-8") as f:
            f.write(f"[{stamp}] {payload}\n")
