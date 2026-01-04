"""Background watchdog that detects stalled automation loops."""

from __future__ import annotations

import os
import threading
import time
from pathlib import Path
from typing import Optional

from logging_util import logger
from .path_manager import get_base_path

try:  # pragma: no cover - optional dependency
    import faulthandler  # type: ignore
except Exception:  # pragma: no cover - best effort fallback
    faulthandler = None  # type: ignore

__all__ = [
    "arm_watchdog",
    "disarm_watchdog",
    "touch_watchdog",
    "shutdown_watchdog",
    "start_watchdog_heartbeat",
    "stop_watchdog_heartbeat",
]

_WATCHDOG_DISABLED = os.environ.get("MS_WATCHDOG_DISABLED", "").lower() in {"1", "true", "yes"}


class OperationWatchdog:
    """Single background thread that enforces forward progress."""

    def __init__(self) -> None:
        self._timeout = 900.0
        self._armed = False
        self._last_touch = time.time()
        self._last_label = "init"
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._run, name="ProgressWatchdog", daemon=True)
        self._thread.start()

    def arm(self, timeout: Optional[float], label: str) -> None:
        with self._lock:
            if timeout is not None and timeout > 0:
                self._timeout = timeout
            self._armed = True
            self._last_touch = time.time()
            self._last_label = label
            logger.debug("Watchdog armed (timeout=%ss, label=%s)", int(self._timeout), label)

    def disarm(self) -> None:
        with self._lock:
            if self._armed:
                logger.debug("Watchdog disarmed (last label=%s)", self._last_label)
            self._armed = False

    def touch(self, label: Optional[str] = None) -> None:
        with self._lock:
            if label:
                self._last_label = label
            self._last_touch = time.time()

    def shutdown(self) -> None:
        self._stop_event.set()
        self._thread.join(timeout=2.0)

    # ------------------------------------------------------------------ #
    def _run(self) -> None:
        while not self._stop_event.wait(timeout=5.0):
            with self._lock:
                if not self._armed:
                    continue
                timeout = self._timeout
                last_touch = self._last_touch
                last_label = self._last_label
            elapsed = time.time() - last_touch
            if elapsed > timeout:
                self._handle_timeout(elapsed, last_label)

    def _handle_timeout(self, elapsed: float, label: str) -> None:
        logger.critical(
            "Watchdog timeout: %.0fs without progress (last update: %s). Forcing shutdown.",
            elapsed,
            label,
        )
        self._dump_traceback(elapsed, label)
        os._exit(71)

    def _dump_traceback(self, elapsed: float, label: str) -> None:
        try:
            log_dir = Path(get_base_path()) / "logs"
            log_dir.mkdir(parents=True, exist_ok=True)
            dump_path = log_dir / "watchdog_timeout.log"
            timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
            with dump_path.open("a", encoding="utf-8") as handle:
                handle.write(
                    f"[{timestamp}] timeout after {elapsed:.1f}s (last={label})\n"
                )
                if faulthandler is not None:
                    faulthandler.dump_traceback(file=handle)
                handle.write("\n")
        except Exception as exc:  # pragma: no cover - best effort logging
            logger.debug("Failed to write watchdog dump: %s", exc)


_WATCHDOG: Optional[OperationWatchdog] = None
_HEARTBEAT_THREAD: Optional[threading.Thread] = None
_HEARTBEAT_STOP = threading.Event()


def _ensure_watchdog() -> Optional[OperationWatchdog]:
    global _WATCHDOG
    if _WATCHDOG_DISABLED:
        return None
    if _WATCHDOG is None:
        _WATCHDOG = OperationWatchdog()
    return _WATCHDOG


def arm_watchdog(timeout: Optional[float] = None, label: str = "operation") -> None:
    watchdog = _ensure_watchdog()
    if watchdog is not None:
        watchdog.arm(timeout, label)


def disarm_watchdog() -> None:
    if _WATCHDOG is not None:
        _WATCHDOG.disarm()


def touch_watchdog(label: Optional[str] = None) -> None:
    if _WATCHDOG is not None:
        _WATCHDOG.touch(label)


def shutdown_watchdog() -> None:
    global _WATCHDOG
    if _WATCHDOG is not None:
        _WATCHDOG.shutdown()
        _WATCHDOG = None


def start_watchdog_heartbeat(interval: float = 30.0) -> None:
    """Start a background thread that periodically touches the watchdog."""
    if _WATCHDOG_DISABLED:
        return
    global _HEARTBEAT_THREAD
    if _HEARTBEAT_THREAD and _HEARTBEAT_THREAD.is_alive():
        return
    _HEARTBEAT_STOP.clear()

    def _heartbeat() -> None:
        while not _HEARTBEAT_STOP.wait(interval):
            touch_watchdog("global_heartbeat")

    _HEARTBEAT_THREAD = threading.Thread(target=_heartbeat, name="WatchdogHeartbeat", daemon=True)
    _HEARTBEAT_THREAD.start()


def stop_watchdog_heartbeat() -> None:
    global _HEARTBEAT_THREAD
    if _HEARTBEAT_THREAD is None:
        return
    _HEARTBEAT_STOP.set()
    _HEARTBEAT_THREAD.join(timeout=2.0)
    _HEARTBEAT_THREAD = None
