# -*- coding: utf-8 -*-
"""Shared helper utilities for operations modules."""

from __future__ import annotations

import config as legacy_config  # type: ignore
from logging_util import logger
from utils import close_windows_by_title

MACRO_MENU_WINDOW_TITLES = (
    "NOX Automation Tool - Menu",
    "MSTools Dialog",
)


def cleanup_macro_windows() -> int:
    """Close lingering macro selection dialogs and return the number closed."""
    closed = 0
    for title in MACRO_MENU_WINDOW_TITLES:
        try:
            closed += close_windows_by_title(title)
        except Exception as exc:  # pragma: no cover - best effort cleanup
            logger.debug("Failed to close macro window '%s': %s", title, exc)
    return closed


def apply_select_configuration(
    select_flags: dict[str, int],
    *,
    name_prefix: str,
    gacha_attempts: int,
    gacha_limit: int,
    continue_until_character: bool,
    room_key1: str,
    room_key2: str,
) -> None:
    """Project cleaned configuration values onto the legacy config module."""
    for key, value in select_flags.items():
        setattr(legacy_config, key, int(value))
    legacy_config.on_gacha_kaisu = int(gacha_attempts)
    legacy_config.gacha_limit = int(gacha_limit)
    legacy_config.continue_until_character = bool(continue_until_character)
    legacy_config.name_prefix = name_prefix
    legacy_config.room_key1 = room_key1
    legacy_config.room_key2 = room_key2
