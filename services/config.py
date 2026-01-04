"""Configuration helpers used by the new operations facade."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

import config as legacy_config  # type: ignore[import]
from logging_util import logger


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
        # 毎回確実に最新の config.json を反映させるため強制リロード
        cfg = legacy_config.reload_config()
        logger.info("ConfigService.load: flags=%s", {
            "on_que": getattr(cfg, "on_que", None),
            "on_event": getattr(cfg, "on_event", None),
            "on_medal": getattr(cfg, "on_medal", None),
            "on_mission": getattr(cfg, "on_mission", None),
            "on_sell": getattr(cfg, "on_sell", None),
            "on_initial": getattr(cfg, "on_initial", None),
            "on_name": getattr(cfg, "on_name", None),
            "on_gacha": getattr(cfg, "on_gacha", None),
            "on_check": getattr(cfg, "on_check", None),
            "on_count": getattr(cfg, "on_count", None),
            "on_save": getattr(cfg, "on_save", None),
            "on_id_check": getattr(cfg, "on_id_check", None),
        })

        select_flags = {
            "on_que": int(getattr(cfg, "on_que", 0)),
            "on_event": int(getattr(cfg, "on_event", 0)),
            "on_medal": int(getattr(cfg, "on_medal", 0)),
            "on_mission": int(getattr(cfg, "on_mission", 0)),
            "on_sell": int(getattr(cfg, "on_sell", 0)),
            "on_initial": int(getattr(cfg, "on_initial", 0)),
            "on_name": int(getattr(cfg, "on_name", 0)),
            "on_gacha": int(getattr(cfg, "on_gacha", 0)),
            "on_check": int(getattr(cfg, "on_check", 0)),
            "on_count": int(getattr(cfg, "on_count", 0)),
            "on_save": int(getattr(cfg, "on_save", 0)),
        }

        extra = getattr(cfg, "extra", {}) if hasattr(cfg, "extra") and isinstance(getattr(cfg, "extra"), dict) else {}
        quest = extra.get("quest", {}) if isinstance(extra.get("quest", {}), dict) else {}
        quest_preset = str(quest.get("preset", "default"))
        quest_parameters = {str(k): str(v) for k, v in quest.get("parameters", {}).items()} if isinstance(quest.get("parameters", {}), dict) else {}

        return ConfigSnapshot(
            device_count=int(getattr(cfg, "device_count", 8)),
            use_independent_processing=bool(getattr(cfg, "use_independent_processing", True)),
            select_flags=select_flags,
            name_prefix=str(getattr(cfg, "name_prefix", "a")),
            gacha_attempts=int(getattr(cfg, "on_gacha_kaisu", 30)),
            gacha_limit=int(getattr(cfg, "gacha_limit", 0)),
            continue_until_character=bool(getattr(cfg, "extra", {}).get("continue_until_character", False)),
            room_key1=str(getattr(cfg, "room_key1", "617")),
            room_key2=str(getattr(cfg, "room_key2", "618")),
            quest_preset=quest_preset,
            quest_parameters=quest_parameters,
        )

    def validate_device_count(self, count: int) -> bool:
        coerced = max(1, min(8, int(count)))
        return 1 <= coerced <= 8

    def get_ports_for_device_count(self, count: int) -> List[str]:
        return list(legacy_config.get_ports_by_count(count))

    def select_ports(self) -> List[str]:
        """Return the configured port list based on the current device count."""
        snapshot = self.load()
        cfg = legacy_config.get_config()
        ports = getattr(cfg, "select_ports", None)
        if isinstance(ports, list) and ports:
            return [str(port) for port in ports]
        return self.get_ports_for_device_count(snapshot.device_count)
