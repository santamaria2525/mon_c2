# -*- coding: utf-8 -*-
"""
Lightweight JSON-based configuration loader for the cleaned codebase.
"""

from __future__ import annotations

import sys
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List

CONFIG_FILENAME = "config.json"

def _resolve_config_directory() -> Path:
    """
    Determine where the runtime configuration file should live.

    * Source execution      -> alongside this module
    * PyInstaller executable -> alongside the extracted executable
    """
    if getattr(sys, "frozen", False):
        try:
            return Path(sys.executable).resolve().parent
        except Exception:
            return Path.cwd()
    return Path(__file__).resolve().parent


_CONFIG_DIR = _resolve_config_directory()
_CONFIG_PATH = _CONFIG_DIR / CONFIG_FILENAME

_DEFAULT_PORTS = [
    "127.0.0.1:62025",
    "127.0.0.1:62026",
    "127.0.0.1:62027",
    "127.0.0.1:62028",
    "127.0.0.1:62029",
    "127.0.0.1:62030",
    "127.0.0.1:62031",
    "127.0.0.1:62032",
]

MAX_FOLDER_LIMIT = 3000

SELECT_FLAG_KEYS = [
    "on_que",
    "on_event",
    "on_medal",
    "on_mission",
    "on_sell",
    "on_initial",
    "on_name",
    "on_gacha",
    "on_check",
    "on_count",
    "on_save",
]

DEFAULT_SELECT_FLAGS = {
    "on_que": 1,
    "on_event": 3,
    "on_medal": 0,
    "on_mission": 0,
    "on_sell": 0,
    "on_initial": 0,
    "on_name": 0,
    "on_gacha": 0,
    "on_check": 0,
    "on_count": 0,
    "on_save": 0,
}

CONFIG_COMMENTS = {
    "__comment_flags": "【セレクトメニュー処理フラグ】下記の順番で実行される",
    "__comment_details": "【on_check】1:ノマクエ、2:覇者済み、3:守護獣所持、【on_que】1:オーブカウンターイベクエ、2:守護獣クエ",
    "__comment_event": "【on_event】1:未使用、2:爆獲れルーレット、3:フレンド招待2人確認",
    "__comment_order": "実行順序: on_check → on_event → on_que → on_medal → on_initial → on_mission → on_name → on_gacha → on_sell → on_count → on_save",
}


@dataclass
class QuestConfig:
    preset: str = "default"
    parameters: Dict[str, str] = field(default_factory=dict)


@dataclass
class ConfigModel:
    nox_device_count: int = 8
    use_independent_processing: bool = True
    select_flags: Dict[str, int] = field(default_factory=lambda: dict(DEFAULT_SELECT_FLAGS))
    name_prefix: str = "a"
    gacha_attempts: int = 30
    gacha_limit: int = 0
    continue_until_character: bool = False
    room_key1: str = "617"
    room_key2: str = "618"
    quest: QuestConfig = field(default_factory=QuestConfig)


def _ensure_config_file() -> None:
    if not _CONFIG_PATH.exists():
        try:
            _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        save_config(ConfigModel())


def _coerce_device_count(value) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return 8
    return max(1, min(8, number))


def _coerce_int(value, default):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _coerce_select_flags(raw: Dict[str, object]) -> Dict[str, int]:
    flags: Dict[str, int] = dict(DEFAULT_SELECT_FLAGS)
    for key in SELECT_FLAG_KEYS:
        if key in raw:
            try:
                flags[key] = int(raw[key])
            except (TypeError, ValueError):
                flags[key] = DEFAULT_SELECT_FLAGS.get(key, 0)
    return flags


def _coerce_quest(value) -> QuestConfig:
    if not isinstance(value, dict):
        return QuestConfig()
    preset = str(value.get("preset", "default"))
    params_raw = value.get("parameters", {})
    if isinstance(params_raw, dict):
        params = {str(k): str(v) for k, v in params_raw.items()}
    else:
        params = {}
    return QuestConfig(preset=preset, parameters=params)


def load_config() -> ConfigModel:
    _ensure_config_file()
    try:
        raw = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return ConfigModel()

    model = ConfigModel(
        nox_device_count=_coerce_device_count(raw.get("nox_device_count", 8)),
        use_independent_processing=bool(raw.get("use_independent_processing", True)),
        select_flags=_coerce_select_flags(raw),
        name_prefix=str(raw.get("name_prefix", "a")),
        gacha_attempts=_coerce_int(raw.get("on_gacha_kaisu"), 30),
        gacha_limit=_coerce_int(raw.get("gacha_limit", 0), 0),
        continue_until_character=bool(raw.get("continue_until_character", False)),
        room_key1=str(raw.get("room_key1", "617")),
        room_key2=str(raw.get("room_key2", "618")),
        quest=_coerce_quest(raw.get("quest", {})),
    )
    return model


def save_config(config: ConfigModel) -> None:
    payload: Dict[str, object] = {
        "nox_device_count": config.nox_device_count,
        "use_independent_processing": config.use_independent_processing,
        **CONFIG_COMMENTS,
    }
    payload.update(config.select_flags)
    payload["name_prefix"] = config.name_prefix
    payload["on_gacha_kaisu"] = config.gacha_attempts
    payload["gacha_limit"] = config.gacha_limit
    payload["continue_until_character"] = config.continue_until_character
    payload["room_key1"] = config.room_key1
    payload["room_key2"] = config.room_key2
    payload["quest"] = {
        "preset": config.quest.preset,
        "parameters": dict(config.quest.parameters),
    }
    _CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    _CONFIG_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def get_ports_for_count(count: int) -> List[str]:
    size = _coerce_device_count(count)
    return _DEFAULT_PORTS[:size]
