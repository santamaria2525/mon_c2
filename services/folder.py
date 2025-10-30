# -*- coding: utf-8 -*-
"""Wrapper utilities around folder_progression_system for the cleaned codebase."""

from __future__ import annotations

from typing import List, Optional, Tuple

from logging_util import logger
from mon_c2.services.config import ConfigService

try:
    from folder_progression_system import FolderProgressionSystem, ensure_continuous_processing, find_next_set_folders
except Exception:  # pragma: no cover - fallback when module missing
    FolderProgressionSystem = None  # type: ignore
    ensure_continuous_processing = None  # type: ignore
    find_next_set_folders = None  # type: ignore


class FolderProgressionService:
    """Small abstraction around the legacy folder progression helpers."""

    def __init__(self, config_service: ConfigService | None = None) -> None:
        self.config_service = config_service or ConfigService()

    def validate(self, folder: int) -> bool:
        if FolderProgressionSystem is None:
            return True
        try:
            return FolderProgressionSystem.validate_folder(folder)
        except Exception as exc:  # pragma: no cover - logging only
            logger.warning("Folder validation failed (%s): %s", folder, exc)
            return True

    def summary(self) -> dict:
        if FolderProgressionSystem is None:
            return {}
        try:
            return FolderProgressionSystem.get_folder_status_summary()
        except Exception:
            return {}

    def next_valid(self, folder: int) -> Optional[int]:
        if ensure_continuous_processing is None:
            return None
        try:
            return ensure_continuous_processing(folder)
        except Exception as exc:
            logger.warning("Folder progression failed (%s): %s", folder, exc)
            return None

    def next_set(self, base_folder: int, device_count: int) -> Tuple[Optional[int], List[str]]:
        if find_next_set_folders is None:
            return None, []
        try:
            return find_next_set_folders(base_folder, device_count)
        except Exception as exc:
            logger.warning("find_next_set_folders error (%s): %s", base_folder, exc)
            return None, []


__all__ = ["FolderProgressionService"]
