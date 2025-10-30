# -*- coding: utf-8 -*-
"""Utilities for allocating main/sub device ports."""

from __future__ import annotations

from typing import List, Tuple

from logging_util import logger

from mon_c2.services.config import ConfigService


class PortAllocationService:
    """Return deterministic main/sub port allocations based on device count."""

    def __init__(self, config_service: ConfigService | None = None) -> None:
        self.config_service = config_service or ConfigService()

    def get_main_and_sub_ports(self) -> Tuple[str, List[str]]:
        snapshot = self.config_service.load()
        device_count = max(1, snapshot.device_count)
        main_port = "127.0.0.1:62025"
        sub_ports: List[str] = []
        for offset in range(1, device_count):
            sub_ports.append(f"127.0.0.1:{62025 + offset}")
        if device_count < 2:
            logger.warning("PortAllocationService: device_count < 2, sub ports empty.")
        return main_port, sub_ports


__all__ = ["PortAllocationService"]
