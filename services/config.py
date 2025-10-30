"""Configuration helpers used by the new operations facade."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

from mon_c2 import config as config_store


@dataclass(frozen=True)
class ConfigSnapshot:
    """Lightweight projection of the runtime configuration."""

    device_count: int
    use_independent_processing: bool
    select_flags: Dict[str, int]
    name_prefix: str
    gacha_attempts: int
    gacha_limit: int
    continue_until_character: bool
    room_key1: str
    room_key2: str
    quest_preset: str
    quest_parameters: Dict[str, str]


class ConfigService:
    """Helper facade around ``mon_c2.config`` for runtime access."""

    def load(self) -> ConfigSnapshot:
        cfg = config_store.load_config()
        return ConfigSnapshot(
            device_count=cfg.nox_device_count,
            use_independent_processing=cfg.use_independent_processing,
            select_flags=dict(cfg.select_flags),
            name_prefix=str(cfg.name_prefix),
            gacha_attempts=int(cfg.gacha_attempts),
            gacha_limit=int(cfg.gacha_limit),
            continue_until_character=bool(cfg.continue_until_character),
            room_key1=str(cfg.room_key1),
            room_key2=str(cfg.room_key2),
            quest_preset=cfg.quest.preset,
            quest_parameters=dict(cfg.quest.parameters),
        )

    def validate_device_count(self, count: int) -> bool:
        coerced = max(1, min(8, int(count)))
        return 1 <= coerced <= 8

    def get_ports_for_device_count(self, count: int) -> List[str]:
        return list(config_store.get_ports_for_count(count))

    def select_ports(self) -> List[str]:
        """Return the configured port list based on the current device count."""
        snapshot = self.load()
        return self.get_ports_for_device_count(snapshot.device_count)
