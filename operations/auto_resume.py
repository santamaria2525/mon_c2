"""Auto-resume helpers for the login loop."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Optional, Sequence

from config import get_config_value
from logging_util import logger
from monst.image.device_management import (
    are_devices_ready_for_resume,
    have_devices_been_idle,
)

_DEFAULT_IDLE_SECONDS = float(get_config_value("auto_resume_idle_seconds", 240) or 240)
_DEFAULT_CHECK_SECONDS = float(get_config_value("auto_resume_check_interval", 30) or 30)
_DEFAULT_COOLDOWN_SECONDS = float(get_config_value("auto_resume_cooldown_seconds", 60) or 60)
_AUTO_RESUME_ENABLED = bool(get_config_value("auto_resume_enabled", True))
_MAX_UNREADY_DEVICES = max(0, int(get_config_value("auto_resume_allow_unready_devices", 1) or 1))


@dataclass
class _ResumeContext:
    ports: Sequence[str]
    resume_folder: int
    last_activity: float
    required_ready_count: int
    last_resume_attempt: float = 0.0


class LoginLoopAutoResumer:
    """Monitor login loop progress and restart it when everything is idle."""

    def __init__(
        self,
        runner,
        *,
        idle_seconds: float = _DEFAULT_IDLE_SECONDS,
        check_seconds: float = _DEFAULT_CHECK_SECONDS,
        cooldown_seconds: float = _DEFAULT_COOLDOWN_SECONDS,
    ) -> None:
        self.runner = runner
        self._idle_seconds = max(60.0, idle_seconds)
        self._check_seconds = max(10.0, check_seconds)
        self._cooldown_seconds = max(30.0, cooldown_seconds)

        self._lock = threading.Lock()
        self._context: Optional[_ResumeContext] = None
        self._resume_inflight = threading.Event()

        self._monitor_thread = threading.Thread(
            target=self._monitor_loop,
            name="LoginLoopAutoResume",
            daemon=True,
        )
        self._monitor_thread.start()

    # ------------------------------------------------------------------ #
    # Context management
    # ------------------------------------------------------------------ #
    def update_context(
        self,
        *,
        ports: Sequence[str],
        resume_folder: Optional[int],
    ) -> None:
        """Update the resume target after a login loop run."""
        with self._lock:
            if not _AUTO_RESUME_ENABLED or not ports or resume_folder is None:
                self._context = None
                return
            folder_value = max(1, int(resume_folder))
            self._context = _ResumeContext(
                ports=tuple(ports),
                resume_folder=folder_value,
                last_activity=time.time(),
                required_ready_count=len(ports),
                last_resume_attempt=0.0,
            )

    def mark_activity(self) -> None:
        """Note that the login loop moved forward (used to reset idle timers)."""
        with self._lock:
            if self._context:
                self._context.last_activity = time.time()

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #
    def _snapshot_context(self) -> Optional[_ResumeContext]:
        with self._lock:
            if self._context is None:
                return None
            return _ResumeContext(
                ports=self._context.ports,
                resume_folder=self._context.resume_folder,
                last_activity=self._context.last_activity,
                required_ready_count=self._context.required_ready_count,
                last_resume_attempt=self._context.last_resume_attempt,
            )

    def _monitor_loop(self) -> None:
        while True:
            time.sleep(self._check_seconds)
            context = self._snapshot_context()
            if not context:
                continue
            if self.runner.core.is_stopping() if hasattr(self.runner.core, "is_stopping") else False:
                continue
            if self.runner.is_running():
                continue

            now = time.time()
            idle_elapsed = now - context.last_activity
            if idle_elapsed < self._idle_seconds:
                continue

            if context.last_resume_attempt and (now - context.last_resume_attempt) < self._cooldown_seconds:
                continue

            if not are_devices_ready_for_resume(context.ports, max_unready=_MAX_UNREADY_DEVICES):
                continue
            if not have_devices_been_idle(context.ports, self._idle_seconds):
                continue
            if self._resume_inflight.is_set():
                continue

            logger.warning(
                "Auto-resume: no login progress for %.0fs; restarting login loop from folder %03d",
                idle_elapsed,
                context.resume_folder,
            )
            with self._lock:
                if self._context:
                    self._context.last_resume_attempt = now
            self._launch_resume(context.resume_folder)

    def _launch_resume(self, start_folder: int) -> None:
        if self._resume_inflight.is_set():
            return

        self._resume_inflight.set()

        def _runner() -> None:
            try:
                self.runner.run(start_folder=start_folder, auto_mode=True)
            except Exception:
                logger.exception("Auto-resume login loop run failed")
            finally:
                self._resume_inflight.clear()

        thread = threading.Thread(
            target=_runner,
            name="LoginLoopAutoResumeRunner",
            daemon=True,
        )
        thread.start()
