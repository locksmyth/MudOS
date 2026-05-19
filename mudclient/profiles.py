from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .config import default_config_dir


@dataclass
class Profile:
    name: str
    host: str
    port: int
    encoding: str = "utf-8"
    notes: str = ""
    auto_login_commands: list[str] = field(default_factory=list)
    auto_login_enabled: bool = False


class ProfileStore:
    def __init__(self, config_dir: Path | None = None) -> None:
        self.config_dir = config_dir or default_config_dir()
        self.path = self.config_dir / "profiles.json"

    def list_profiles(self) -> list[Profile]:
        return list(self._load_all().values())

    def save_profile(self, profile: Profile) -> None:
        profiles = self._load_all()
        profiles[profile.name] = profile
        self._save_all(profiles)

    def delete_profile(self, name: str) -> bool:
        profiles = self._load_all()
        if name not in profiles:
            return False
        del profiles[name]
        self._save_all(profiles)
        return True

    def get(self, name: str) -> Profile | None:
        return self._load_all().get(name)

    def _load_all(self) -> dict[str, Profile]:
        if not self.path.exists():
            return {}
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        out: dict[str, Profile] = {}
        for item in raw:
            try:
                p = Profile(**item)
            except (TypeError, ValueError):
                continue
            out[p.name] = p
        return out

    def _save_all(self, profiles: dict[str, Profile]) -> None:
        self.config_dir.mkdir(parents=True, exist_ok=True)
        data = [asdict(p) for p in sorted(profiles.values(), key=lambda x: x.name.lower())]
        self.path.write_text(json.dumps(data, indent=2), encoding="utf-8")
