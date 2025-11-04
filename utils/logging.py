"""
logging_util.py ‑ refactored for smaller, self‑rotating log files and simpler
thread‑safe error suppression.  Public API (``logger`` / ``setup_logger`` /
``MultiDeviceLogger``) remains unchanged.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from collections import Counter
from datetime import datetime, timedelta
from logging.handlers import RotatingFileHandler

try:
    from colorama import Fore, Style
    from colorama import init as _colorama_init

    _colorama_init()
    _USE_COLOR = True
except ImportError:  # colorama が無い場合はカラー無効
    _USE_COLOR = False
from typing import Dict, List

__all__ = ["logger", "setup_logger", "MultiDeviceLogger"]

_CONFIGURED_PATH: str | None = None

_FORMAT = '%(asctime)s [%(levelname)s] %(name)s: %(message)s'
_DATEFMT = '%Y-%m-%d %H:%M:%S'
_MAX_BYTES = 2 * 1024 * 1024  # 2 MiB log files
_BACKUP_COUNT = 5  # keep five rotations



class SummaryLogFilter(logging.Filter):
    """Show folder-level results only (simplified)"""

    IMPORTANT = [" フォルダ", " フォルダ", "成功", "失敗", "ERROR"]
    SUPPRESS = [
        "クリック",
        "ok.pngクリック",
        "座標:",
        "初期化",
        "待機中",
        "発見",
        "処理開始",
        "処理完了",
        "確認開始",
        "確認完了",
        "端末",
        "127.0.0.1:",
        "ファイルプッシュ成功:",
        "プッシュ完了",
        "転送成功",
    ]

    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()

        if "フォルダ" in msg and any(p in msg for p in ["成功", "失敗"]):
            return True

        if any(p in msg for p in self.IMPORTANT):
            return True

        if any(p in msg for p in self.SUPPRESS):
            return False

        return record.levelno >= logging.ERROR


def _ensure_log_dir(path: str) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)


# ---------------------------------------------------------------------------
# rate‑limited error logger implementation
# ---------------------------------------------------------------------------


class _RateLimiter:
    """Caps the rate of identical log entries per *interval* seconds."""

    def __init__(self, interval: int = 300):  # 5-minute window
        self._interval = interval
        self._last: Dict[str, float] = {}
        self._counts: Counter[str] = Counter()
        self._lock = threading.Lock()

    def should_log(self, key: str) -> bool:
        now = time.time()
        with self._lock:
            last = self._last.get(key, 0.0)
            if now - last >= self._interval:
                self._last[key] = now
                self._counts[key] = 0
                return True

            self._counts[key] += 1
            # still log every 10th suppressed message
            # log every 50th suppressed message to keep track
            return self._counts[key] % 50 == 0


_rate_limiter = _RateLimiter()


class _CompressedLogger(logging.Logger):
    """Logger that drops repetitive *error* entries using _RateLimiter."""

    def error(self, msg, *args, **kwargs):  # type: ignore[override]
        key = str(msg).split(":", 1)[0]
        if _rate_limiter.should_log(key):
            super().error(msg, *args, **kwargs)


# must be set before the first getLogger() call
logging.setLoggerClass(_CompressedLogger)

# ---------------------------------------------------------------------------
# color console formatter
# ---------------------------------------------------------------------------

if _USE_COLOR:
    _LEVEL_COLOR = {
        logging.DEBUG: Fore.CYAN,
        logging.INFO: Fore.GREEN,
        logging.WARNING: Fore.YELLOW,
        logging.ERROR: Fore.RED,
        logging.CRITICAL: Fore.MAGENTA,
    }

    class _ColorFormatter(logging.Formatter):
        def format(self, record: logging.LogRecord) -> str:  # type: ignore[override]
            msg = super().format(record)
            color = _LEVEL_COLOR.get(record.levelno, "")
            reset = Style.RESET_ALL if color else ""
            return f"{color}{msg}{reset}"

else:
    _ColorFormatter = logging.Formatter  # type: ignore

# ---------------------------------------------------------------------------
# logger factory
# ---------------------------------------------------------------------------


def setup_logger(log_file_path: str = 'app.log', level: int = logging.INFO) -> logging.Logger:
    """Configure the root logger exactly once; allow reconfiguration on demand."""
    global _CONFIGURED_PATH

    target_path = os.path.abspath(log_file_path)
    logger_ = logging.getLogger()

    existing_handlers = list(logger_.handlers)
    if existing_handlers:
        if _CONFIGURED_PATH == target_path:
            return logger_
        for handler in existing_handlers:
            logger_.removeHandler(handler)
            try:
                handler.close()
            except Exception:
                pass

    _ensure_log_dir(target_path)

    formatter = logging.Formatter(_FORMAT, datefmt=_DATEFMT)

    file_handler = RotatingFileHandler(
        target_path,
        maxBytes=_MAX_BYTES,
        backupCount=_BACKUP_COUNT,
        encoding='utf-8',
    )
    file_handler.setFormatter(formatter)
    logger_.addHandler(file_handler)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(_ColorFormatter(_FORMAT, datefmt=_DATEFMT))
    console_handler.setLevel(logging.INFO)
    console_handler.addFilter(SummaryLogFilter())
    logger_.addHandler(console_handler)

    logger_.setLevel(level)
    _CONFIGURED_PATH = target_path
    logger_.debug('Logger initialised -> %s', target_path)
    return logger_

logger = logging.getLogger()
if not logger.handlers:
    logger.addHandler(logging.NullHandler())

# ---------------------------------------------------------------------------
# Multi‑device helper (public API unchanged, implementation simplified)
# ---------------------------------------------------------------------------


class MultiDeviceLogger:
    """Collects per‑device success/error state and prints summary once done."""

    def __init__(self, device_ports: List[str], folders: List[str] | None = None):
        self._results: Dict[str, bool] = {p: False for p in device_ports}
        self._errors: Dict[str, str] = {}
        self._folders = folders or ["" for _ in device_ports]
        self._lock = threading.Lock()
        self._device_ports = device_ports

    # -------------------------------------------------- public callbacks ---#

    def log_success(self, device_port: str) -> None:
        with self._lock:
            self._results[device_port] = True

    def log_error(self, device_port: str, message: str) -> None:
        with self._lock:
            self._results[device_port] = False
            self._errors[device_port] = message

    def update_task_status(self, device_port: str, folder: str, operation: str) -> None:
        """タスクモニターに処理状況を更新（複数の方法を試行）"""
        try:
            try:
                from utils.process_task_monitor import (
                    is_process_task_monitor_running,
                    update_process_task,
                )

                if is_process_task_monitor_running():
                    update_process_task(device_port, folder, operation)
                    return
            except ImportError:
                pass

            # 方法2: CompactTaskMonitor（tkinter競合の可能性あり）
            try:
                from tools.monitoring.compact_task_monitor import (
                    is_compact_task_monitor_running,
                    update_compact_task,
                )

                if is_compact_task_monitor_running():
                    update_compact_task(device_port, folder, operation)
                    return
            except ImportError:
                pass

            # 方法3: SuperTaskMonitor
            try:
                from tools.monitoring.task_monitor_v2 import (
                    is_super_task_monitor_running,
                    update_super_task,
                )

                if is_super_task_monitor_running():
                    update_super_task(device_port, folder, operation)
                    return
            except ImportError:
                pass

            # 方法4: 従来のタスクモニター
            try:
                from tools.monitoring.task_monitor import update_device_task

                update_device_task(device_port, folder, operation)
                return
            except ImportError:
                pass

        except Exception:
            pass  # タスクモニターが利用できない場合は無視

    # --------------------------------------------------- final summary ----#

    def summarize_results(self, operation_name: str) -> None:
        """Summarise run – now includes folder range like "001-008" so the
        log directly shows *which* folders were processed.
        """
        total = len(self._results)
        success = sum(self._results.values())

        # ---- calculate folder span (if all names look numeric) -------------
        folder_range = ""
        try:
            nums = [int(f) for f in self._folders if str(f).isdigit()]
            if nums:
                folder_range = f"{min(nums):03d}-{max(nums):03d}"
        except Exception:
            # any parsing failure → just leave folder_range empty
            pass

        # ---- success path ---------------------------------------------------
        if success == total:
            if folder_range:
                logger.info("%s: %d/%d 成功 (%s)", operation_name, success, total, folder_range)
            else:
                logger.info("%s: %d/%d 成功", operation_name, success, total)
            return

        # ---- partial failure ------------------------------------------------
        if folder_range:
            logger.error("%s: %d/%d 成功 (%s)", operation_name, success, total, folder_range)
        else:
            logger.error("%s: %d/%d 成功", operation_name, success, total)

        # per‑device details
        for port, ok in self._results.items():
            if not ok:
                logger.error("  %s: %s", port, self._errors.get(port, "原因不明の失敗"))
