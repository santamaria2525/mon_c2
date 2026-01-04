# -*- coding: utf-8 -*-
"""
Core runtime setup for the cleaned Monster Strike Bot.

The implementation is intentionally close to the proven logic in the legacy
``app/core.py`` module but trimmed to highlight the responsibilities:
    * configure the working directory and logging
    * manage global shutdown signals
    * expose small utility helpers used by CLI/GUI layers
"""

from __future__ import annotations

import logging
import os
import signal
import sys
import threading
from typing import Optional

from logging_util import logger, setup_logger
from memory_monitor import start_memory_monitoring, stop_memory_monitoring
from utils import (
    get_base_path,
    get_log_file_path,
    set_working_directory,
    start_error_dialog_monitor,
    start_watchdog_heartbeat,
    stop_error_dialog_monitor,
    stop_watchdog_heartbeat,
)


def install_global_exception_hook() -> None:
    """Ensure uncaught exceptions are logged instead of silently swallowing."""

    def _hook(exctype, value, tb):
        try:
            logger.error("Uncaught exception", exc_info=(exctype, value, tb))
        except Exception:
            pass

    try:
        sys.excepthook = _hook  # type: ignore[attr-defined]
    except Exception:
        pass


class ApplicationCore:
    """Runtime bootstrapper shared by CLI and GUI interfaces."""

    def __init__(self) -> None:
        self.stop_event = threading.Event()
        self._monitor_preference: Optional[str] = None
        self._shutdown_lock = threading.Lock()
        self._shutdown_invoked = False

        self._setup_shutdown_handlers()
        install_global_exception_hook()
        self._setup_environment()

    # ------------------------------------------------------------------ #
    # Initialisation helpers
    # ------------------------------------------------------------------ #
    def _setup_shutdown_handlers(self) -> None:
        """Register signal handlers for graceful termination."""

        def _shutdown(signum, _frame):
            logger.info("Shutdown signal (%s) received; stopping application.", signum)
            self.shutdown(exit_code=0)

        try:
            signal.signal(signal.SIGINT, _shutdown)
            signal.signal(signal.SIGTERM, _shutdown)
        except Exception:
            pass

    def _setup_environment(self) -> None:
        """Configure console I/O, working directory, logging, and monitoring."""
        self._configure_console_encoding()
        set_working_directory()
        self._boost_process_priority()

        base_path = get_base_path()
        # ログは実行ファイルと同じ階層（scripts/exe いずれも）に出力する
        log_file_path = get_log_file_path(base_dir=base_path)
        setup_logger(log_file_path=log_file_path, level=logging.DEBUG)

        # Limit OpenCV threads to avoid oversubscription on multi-device runs.
        try:
            import cv2  # type: ignore

            cv2.setNumThreads(1)
        except Exception:
            pass

        # Configure pyautogui failsafe from config (default True).
        try:
            from config import get_config_value
            import pyautogui  # type: ignore

            failsafe = bool(get_config_value("pyautogui_failsafe", True))
            pyautogui.FAILSAFE = failsafe
        except Exception:
            pass

        start_memory_monitoring()
        try:
            start_error_dialog_monitor()
        except Exception as exc:
            logger.debug("Failed to start error dialog monitor: %s", exc)
        try:
            start_watchdog_heartbeat()
        except Exception as exc:
            logger.debug("Failed to start watchdog heartbeat: %s", exc)

    def _configure_console_encoding(self) -> None:
        """Best-effort UTF-8 console fallback for bundled executables."""
        try:
            os.environ.setdefault("PYTHONUTF8", "1")
            os.environ.setdefault("PYTHONIOENCODING", "utf-8")
        except Exception:
            pass

        try:
            import ctypes

            kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
            kernel32.SetConsoleOutputCP(65001)
            kernel32.SetConsoleCP(65001)
        except Exception:
            pass

        for stream_name in ("stdout", "stderr"):
            base_stream = getattr(sys, f"__{stream_name}__", None)
            current_stream = getattr(sys, stream_name, None)

            if base_stream is not None:
                try:
                    reconfigure = getattr(base_stream, "reconfigure", None)
                    if callable(reconfigure):
                        reconfigure(encoding="utf-8", errors="replace")
                except Exception:
                    pass

            if current_stream is None:
                continue

            try:
                reconfigure = getattr(current_stream, "reconfigure", None)
                if callable(reconfigure):
                    reconfigure(encoding="utf-8", errors="replace")
                    continue
            except Exception:
                pass

    def _boost_process_priority(self) -> None:
        """Prefer thisツール（とNOX子プロセス）のCPUスケジューリングを優先させる."""
        try:
            import psutil  # type: ignore

            proc = psutil.Process()
            # Windows固有: HIGHで十分。REALTIMEはリスクが高いので避ける。
            if hasattr(psutil, "HIGH_PRIORITY_CLASS"):
                proc.nice(psutil.HIGH_PRIORITY_CLASS)  # type: ignore[arg-type]
            # 全コアを使えるように設定（環境によっては既定で全コアだが明示）
            try:
                proc.cpu_affinity(list(range(os.cpu_count() or 1)))  # type: ignore[attr-defined]
            except Exception:
                pass
        except Exception:
            try:
                # psutilが無い場合のフォールバック（Windows専用）
                import ctypes

                priority_high = 0x00000080  # HIGH_PRIORITY_CLASS
                handle = ctypes.windll.kernel32.GetCurrentProcess()
                ctypes.windll.kernel32.SetPriorityClass(handle, priority_high)
            except Exception:
                pass

            try:
                wrapped = getattr(current_stream, "wrapped", None)
                if wrapped is not None and base_stream is not None:
                    current_stream.wrapped = base_stream  # type: ignore[attr-defined]
            except Exception:
                pass

    # ------------------------------------------------------------------ #
    # Public helpers
    # ------------------------------------------------------------------ #
    def setup_console_title(self, title: str = "MonsterStrike Bot") -> None:
        """Set the console window title."""
        try:
            import ctypes

            ctypes.windll.kernel32.SetConsoleTitleW(title)
        except Exception:
            pass

    def shutdown(self, exit_code: int = 0) -> None:
        """Gracefully stop monitors and terminate the process."""
        with self._shutdown_lock:
            if self._shutdown_invoked:
                return
            self._shutdown_invoked = True

        self.stop_event.set()
        try:
            stop_memory_monitoring()
        except Exception:
            pass
        try:
            stop_error_dialog_monitor()
        except Exception:
            pass
        try:
            stop_watchdog_heartbeat()
        except Exception:
            pass

        try:
            sys.exit(exit_code)
        finally:
            os._exit(exit_code)

    def handle_console_visibility(self, args: list[str]) -> None:
        """Minimise or hide the console according to CLI flags."""
        if "--minimize-console" not in args and "--hide" not in args:
            return

        try:
            import ctypes

            window_handle = ctypes.windll.kernel32.GetConsoleWindow()
            if not window_handle:
                return

            if "--hide" in args:
                ctypes.windll.user32.ShowWindow(window_handle, 0)  # SW_HIDE
                logger.info("Console hidden.")
            else:
                ctypes.windll.user32.ShowWindow(window_handle, 6)  # SW_MINIMIZE
                logger.info("Console minimised.")
        except Exception:
            pass

    def is_stopping(self) -> bool:
        """Return True when the application is shutting down."""
        return self.stop_event.is_set()

    def set_monitor_preference(self, pref: Optional[str]) -> None:
        """Persist the preferred task monitor backend."""
        if pref in (None, "compact", "process", "super"):
            self._monitor_preference = pref
        else:
            self._monitor_preference = None

    def get_monitor_preference(self) -> Optional[str]:
        """Return the selected task monitor backend, if any."""
        return self._monitor_preference

    def get_start_folder(self) -> Optional[int]:
        """Prompt the user for a folder number and validate the response."""
        from utils import display_message, get_target_folder  # lazy import

        base = get_target_folder()
        if base is None:
            logger.info("Folder not selected; falling back to folder 1.")
            return 1

        if base.strip() == "":
            logger.info("Empty folder input; starting at folder 1.")
            return 1

        try:
            return int(base)
        except ValueError:
            logger.error("Invalid folder input: %s", base)
            display_message("エラー", "有効なフォルダ番号を入力してください。")
            return None

    def select_device_port(self) -> Optional[str]:
        """Prompt the user to select a device port."""
        from utils import select_device_port  # lazy import

        port = select_device_port()
        if not port:
            logger.warning("No device port selected.")
            return None
        return port
