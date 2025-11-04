"""Lightweight no-op facade: task monitor UI disabled.

All functions are kept for compatibility but perform no work.
"""

from typing import List, Optional


def is_running() -> bool:
    return False


def start_monitor(device_ports: List[str], preference: Optional[str] = None) -> None:
    return None


def update_task(device_port: str, folder: str, operation: str) -> None:
    return None


def stop_monitor() -> None:
    return None
