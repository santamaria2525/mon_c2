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
    from colorama import init as _colorama_init, Fore, Style
    _colorama_init()
    _USE_COLOR = True
except ImportError:  # colorama が無い場合はカラー無効
    _USE_COLOR = False
from typing import Dict, List

__all__ = ["logger", "setup_logger", "MultiDeviceLogger"]

_CONFIGURED_PATH: str | None = None

class SummaryLogFilter(logging.Filter):
    """フォルダ単位の結果のみを表示するログフィルター（重複ログ圧縮機能付き）"""
    
    def __init__(self):
        super().__init__()
        self.repeated_logs = {}  # メッセージパターン -> カウント
        self.last_messages = {}  # メッセージパターン -> 最後のメッセージ
        self.suppress_threshold = 10  # 10回以上の繰り返しで圧縮
    
    def filter(self, record):
        message = record.getMessage()
        # Drop verbose startup/info lines to keep console concise
        try:
            drop_substrings = [
                "フォルダ管理システム初期化",
                "個のフォルダをキューに追加",
                "処理範囲",
                "使用端末:",
                "開始フォルダ:",
            ]
            for s in drop_substrings:
                if s in message:
                    return False
        except Exception:
            pass
        
        # 繰り返しログの検出とカウント
        pattern = self._extract_pattern(message)
        if pattern:
            if pattern in self.repeated_logs:
                self.repeated_logs[pattern] += 1
                self.last_messages[pattern] = message
                
                # 閾値を超えた場合は抑制
                if self.repeated_logs[pattern] >= self.suppress_threshold:
                    # 最初の圧縮時のみサマリーログを出力
                    if self.repeated_logs[pattern] == self.suppress_threshold:
                        summary_msg = f"🔄 繰り返しログ検出: 「{pattern}」({self.suppress_threshold}回以上)"
                        # サマリーメッセージを一度だけ表示
                        print(summary_msg)
                    return False  # 以降のログは抑制
            else:
                self.repeated_logs[pattern] = 1
                self.last_messages[pattern] = message
        
        # 表示するログのパターン（フォルダ単位の結果最優先）
        important_patterns = [
            "✅ フォルダ",  # フォルダ成功ログ（最重要）
            "❌ フォルダ",  # フォルダ失敗ログ（最重要）
            "🔄 NOX再起動",  # NOX再起動の簡潔ログ
            "処理完了：",  # バッチ処理完了サマリー
            "システム終了",
            "システム開始",
            "継続実行可能",
            "新しいフォルダを追加",
            "成功",        # 成功ログは必ず表示
            "失敗",        # 失敗ログは必ず表示
            "エラー",      # エラーログは必ず表示
            "ERROR"        # ERRORレベルは必ず表示
        ]
        important_patterns.extend(["覇者セット開始", "覇者終了"])

        
        # 非表示にするログのパターン（詳細操作ログを抑制）
        suppress_patterns = [
            "クリック",
            "ok.pngクリック",
            "questフォルダの",
            "座標:",
            "初期化",
            "アカウント名",
            "OKボタン",
            "Monster Strike",
            "プッシュ検証",
            "ファイルプッシュ成功:",
            "アプリ再起動",
            "待機中",
            "発見",
            "入力中",
            "入力完了",
            "処理開始",
            "処理完了",
            "フレンド状況確認開始",
            "端末",
            "ログイン中",
            "確認開始",
            "確認完了",
            "状況確認",
            "開始 -",
            "完了 -",
            "WARNING",
            "再起動中",
            "再起動完了",
            "接続確認",
            "デバイス",
            "メモリ使用率",
            "極限:",
            "緊急:",
            "🔥",
            "⚠️",
            "🚨",
            "メモリクリーンアップ",
            "ガベージコレクション",
            "キャッシュ",
            "Windows メモリ",
            "メモリ不足",
            "端末台数設定:",
            "[INFO] 端末台数設定",
            "フォルダー検証成功:",
            "✅ フォルダー検証成功",
            "設定読み込み成功:",
            "room再確認成功",
            "メイン端末のログイン完了:",
            "フレンド状況確認開始",
            "端末1:",
            "端末2:",
            "端末3:",
            "端末4:",
            "端末5:",
            "端末6:",
            "端末7:",
            "端末8:",
            "[FRIEND_STATUS_CHECK]",
            "ファイルプッシュ成功:",
            "✅ ファイルプッシュ成功:",
            "データプッシュ",
            "プッシュ成功",
            "プッシュ完了",
            "ファイル転送",
            "転送成功",
            "->",
            "127.0.0.1:",
            "62025",
            "62026",
            "62027",
            "62028",
            "62029",
            "62030",
            "62031",
            "62032"
        ]
        
        folder_keywords = (
            "作業完了",
            "作業失敗",
            "作業再開",
            "作業再試行",
            "作業中断",
            "作業開始",
            "成功",
            "失敗",
        )

        # まず抑制パターンをチェック（フォルダ関連以外）
        if "フォルダ" not in message:
            for pattern in suppress_patterns:
                if pattern in message:
                    return False
        
        if "フォルダ" in message:
            if record.levelno >= logging.WARNING:
                return True
            if (
                "端末" in message
                and record.levelno < logging.WARNING
                and not any(keyword in message for keyword in folder_keywords)
            ):
                return False
            if any(keyword in message for keyword in folder_keywords):
                return True
        
        # 重要なログは通す
        for pattern in important_patterns:
            if pattern in message:
                return True
        
        # エラーレベルは必ず表示
        if record.levelno >= logging.ERROR:
            return True
            
        # デフォルトは表示しない
        return False
    
    def _extract_pattern(self, message: str) -> str:
        """メッセージからパターンを抽出（重複検出用）"""
        import re
        
        # フォルダー検証成功のパターン
        if "フォルダー検証成功" in message:
            return "フォルダー検証成功"
        
        # 端末台数設定のパターン
        if "端末台数設定" in message:
            return "端末台数設定"
            
        # その他の繰り返し可能性があるパターン
        patterns = [
            r"✅.*成功",
            r"❌.*失敗", 
            r"処理開始",
            r"処理完了",
            r"確認中",
            r"待機中",
            r"検証成功",
            r"初期化完了"
        ]
        
        for pattern in patterns:
            if re.search(pattern, message):
                # 数値や時刻などの変動部分を除いたパターンを返す
                return re.sub(r'\d+', 'X', re.sub(r'\d{2}:\d{2}:\d{2}', 'XX:XX:XX', message))
        
        return None

# ---------------------------------------------------------------------------
# constants & helpers
# ---------------------------------------------------------------------------

_LOG_DIR = "logs"
_MAX_BYTES = 5 * 1024 * 1024  # 5 MB
_BACKUP_COUNT = 2  # バックアップ数削減
_FORMAT = "% (asctime)s | % (levelname)-8s | % (message)s".replace("% ", "%")

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

def setup_logger(log_file_path: str = "app.log", level: int = logging.INFO) -> logging.Logger:
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

    formatter = logging.Formatter(_FORMAT)
    summary_filter = SummaryLogFilter()

    file_handler = RotatingFileHandler(
        target_path,
        maxBytes=_MAX_BYTES,
        backupCount=_BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    file_handler.addFilter(summary_filter)
    logger_.addHandler(file_handler)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(_ColorFormatter(_FORMAT))
    console_handler.setLevel(logging.INFO)
    console_handler.addFilter(summary_filter)
    logger_.addHandler(console_handler)

    logger_.setLevel(level)
    _CONFIGURED_PATH = target_path
    logger_.debug("Logger initialised -> %s", target_path)
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
        self._folder_map: Dict[str, str] = {}
        if folders:
            for idx, port in enumerate(device_ports):
                if idx < len(folders):
                    self._folder_map[port] = folders[idx]
                else:
                    self._folder_map[port] = ""
        else:
            for port in device_ports:
                self._folder_map[port] = ""

    # -------------------------------------------------- public callbacks ---#

    def log_success(self, device_port: str) -> None:
        with self._lock:
            self._results[device_port] = True
            self._errors.pop(device_port, None)

    def log_error(self, device_port: str, message: str) -> None:
        with self._lock:
            self._results[device_port] = False
            self._errors[device_port] = message

    def get_error(self, device_port: str) -> str:
        with self._lock:
            return self._errors.get(device_port, "")
    
    def update_task_status(self, device_port: str, folder: str, operation: str) -> None:
        """タスクモニターに処理状況を更新（複数の方法を試行）"""
        try:
            try:
                from utils.process_task_monitor import update_process_task, is_process_task_monitor_running
                if is_process_task_monitor_running():
                    update_process_task(device_port, folder, operation)
                    return
            except ImportError:
                pass
            
            # 方法2: CompactTaskMonitor（tkinter競合の可能性あり）
            try:
                from tools.monitoring.compact_task_monitor import update_compact_task, is_compact_task_monitor_running
                if is_compact_task_monitor_running():
                    update_compact_task(device_port, folder, operation)
                    return
            except ImportError:
                pass
            
            # 方法3: SuperTaskMonitor
            try:
                from tools.monitoring.task_monitor_v2 import update_super_task, is_super_task_monitor_running
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

    def summarize_results(self, operation_name: str, suppress_summary: bool = False) -> tuple[int, int]:
        """Summarise run – now includes folder range like "001-008" so the
        log directly shows *which* folders were processed.
        """
        total = len(self._results)
        success = sum(self._results.values())

        if suppress_summary:
            if success != total:
                logger.error("%s: %d/%d 成功", operation_name, success, total)
                for port, ok in self._results.items():
                    if not ok:
                        folder = self._folder_map.get(port, "")
                        if folder:
                            logger.error(
                                "  行%s (%s): %s",
                                folder,
                                port,
                                self._errors.get(port, "原因不明の失敗"),
                            )
                        else:
                            logger.error("  %s: %s", port, self._errors.get(port, "原因不明の失敗"))
            return success, total

        # ---- success path ---------------------------------------------------
        if success == total:
            logger.info("%s: %d/%d 成功", operation_name, success, total)
            return success, total

        # ---- partial failure ------------------------------------------------
        logger.error("%s: %d/%d 成功", operation_name, success, total)

        # per-device details with row numbers
        for port, ok in self._results.items():
            if not ok:
                folder = self._folder_map.get(port, "")
                if folder:
                    logger.error(
                        "  行%s (%s): %s",
                        folder,
                        port,
                        self._errors.get(port, "原因不明の失敗"),
                    )
                else:
                    logger.error("  %s: %s", port, self._errors.get(port, "原因不明の失敗"))
        return success, total

