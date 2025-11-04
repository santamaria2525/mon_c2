"""Light-weight task monitor helpers used by the modern toolkit.

The original implementation spawned a rich monitoring UI.  For the cleaned
codebase we keep the public API compatible while simplifying the internal
behaviour.  State is persisted to a JSON file so that external tools can
poll the latest device information without tightly coupling to this process.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

_STATE_LOCK = threading.Lock()
_DATA_FILE = Path.home() / ".mon_c2" / "task_monitor.json"
_DATA_FILE.parent.mkdir(parents=True, exist_ok=True)

_state: Dict[str, object] = {
    "active": False,
    "devices": {},  # port -> {"folder": str | None, "operation": str | None, "updated_at": float}
    "started_at": None,
    "updated_at": None,
}


def _write_state() -> None:
    with _STATE_LOCK:
        _state["updated_at"] = time.time()
        try:
            _DATA_FILE.write_text(json.dumps(_state, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as exc:  # pragma: no cover - safeguard for I/O issues
            logger.error("Failed to write task-monitor state: %s", exc)


def _ensure_device(port: str) -> None:
    devices = _state.setdefault("devices", {})
    if port not in devices:
        devices[port] = {"folder": None, "operation": None, "updated_at": None}


def start_process_task_monitor(device_ports: List[str]) -> None:
    """Initialise monitoring state for the given device ports."""
    with _STATE_LOCK:
        _state["active"] = True
        _state["started_at"] = time.time()
        _state["devices"] = {}
        for port in device_ports:
            _state["devices"][port] = {"folder": None, "operation": None, "updated_at": None}
    logger.info("Process task monitor started for %s", device_ports)
    _write_state()


def stop_process_task_monitor() -> None:
    """Mark the background monitor as stopped and persist state."""
    with _STATE_LOCK:
        if not _state.get("active"):
            return
        _state["active"] = False
    logger.info("Process task monitor stopped")
    _write_state()


def is_process_task_monitor_running() -> bool:
    """Return True when the monitor is considered active."""
    with _STATE_LOCK:
        return bool(_state.get("active"))


def update_process_task(device_port: str, folder: str, operation: Optional[str] = None) -> None:
    """Update the monitored state for a specific device."""
    with _STATE_LOCK:
        _ensure_device(device_port)
        device_entry = _state["devices"][device_port]
        device_entry["folder"] = folder
        if operation is not None:
            device_entry["operation"] = operation
        device_entry["updated_at"] = time.time()
    logger.debug("Task monitor update: port=%s folder=%s op=%s", device_port, folder, operation)
    _write_state()


def update_process_task_folder(device_port: str, folder_number: int) -> None:
    """Helper that only records the current folder number for the device."""
    update_process_task(device_port, f"{folder_number:03d}")


def read_state() -> Dict[str, object]:
    """Expose a copy of the current state (useful for tests or tooling)."""
    with _STATE_LOCK:
        return json.loads(json.dumps(_state))


__all__ = [
    "start_process_task_monitor",
    "stop_process_task_monitor",
    "is_process_task_monitor_running",
    "update_process_task",
    "update_process_task_folder",
    "read_state",
]
