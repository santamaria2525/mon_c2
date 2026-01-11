"""
monst.image.device_management - Device state management and recovery.

デバイス状態管理、エラー処理、回復処理を提供します。
"""

from __future__ import annotations

import os
import psutil
import re
import socket
import subprocess
import threading
import time
from collections import defaultdict
from typing import Dict, List, Set, Any, Sequence, Optional

from config import NOX_ADB_PATH, get_config_value
from logging_util import logger
from monst.adb import (
    reset_adb_server, 
    is_device_available, 
    reconnect_device,
    start_monster_strike_app,
    restart_monster_strike_app
)
from utils import send_notification_email
from utils.device_utils import get_terminal_number
from utils.device_utils import get_terminal_number
from .constants import (
    ERROR_COOLDOWN_PERIOD,
    RECOVERY_CHECK_INTERVAL,
    EMAIL_NOTIFICATION_DELAY,
    NOX_EXE_PATH,
    DEVICE_RESTART_QUEUE_DELAY,
    MAX_CONCURRENT_RESTARTS,
    NOX_FRIENDLY_MODE,
    ENABLE_AUTO_RESTART,
    ENABLE_AUTO_RECOVERY,
    RESTART_VERBOSE,
    MIN_CONSECUTIVE_ERRORS
)

# エラー管理グローバル変数
_error_count = defaultdict(int)  # デバイスごとのエラー回数
_consecutive_errors = defaultdict(int)  # デバイスごとの連続エラー数
_device_in_error_state: Set[str] = set()  # エラー状態のデバイス
_notified_devices: Set[str] = set()  # メール通知済みデバイス
_error_notified_time: Dict[str, float] = {}  # 最後のエラー通知時間
_device_restart_time: Dict[str, float] = {}  # デバイス再起動時間
_last_restart_attempt = defaultdict(int)  # 最後の再起動試行時間
_restart_in_progress = set()  # 再起動処理中のデバイス
_recovery_attempts = defaultdict(int)  # デバイスごとの回復試行回数
_scheduled_notifications = {}  # 予定されている通知
_last_adb_reset_seen: float = 0.0  # ADB??????????

# 無限ループ防止用の新しい変数
_recovery_attempts = defaultdict(int)  # デバイスごとの回復試行回数
_recovery_attempt_time = defaultdict(float)  # 最後の回復試行時間
_emergency_reset_time = 0  # 最後の緊急リセット時間
MAX_RECOVERY_ATTEMPTS = 10  # 最大回復試行回数（適正値に調整）
RECOVERY_RESET_INTERVAL = 900  # 回復試行カウントのリセット間隔（15分に短縮）

_progress_lock = threading.Lock()
_last_progress_time: Dict[str, float] = {}
_FREEZE_THRESHOLD = float(get_config_value("freeze_monitor_threshold_seconds", 600) or 600)
_FREEZE_CHECK_INTERVAL = float(get_config_value("freeze_monitor_check_interval_seconds", 60) or 60)
_GLOBAL_STALL_RESET_COOLDOWN = float(get_config_value("freeze_monitor_global_reset_cooldown_seconds", 900) or 900)
_last_global_stall_reset = 0.0
_BLACK_SCREEN_MEAN_THRESHOLD = float(get_config_value("black_screen_mean_threshold", 5) or 5)
_BLACK_SCREEN_RESTART_SECONDS = float(get_config_value("black_screen_restart_seconds", 180) or 180)
_black_screen_since: Dict[str, float] = {}
_host_wait_ports: Set[str] = set()
_host_wait_lock = threading.Lock()
_last_virtual_machine_failure = 0.0
_auto_restart_pause_lock = threading.Lock()
_auto_restart_pause_depth = 0
_auto_restart_pause_reason: Optional[str] = None


def pause_auto_restart(reason: Optional[str] = None) -> None:
    """自動再起動を一時的に停止する（ネスト対応）。"""
    global _auto_restart_pause_depth, _auto_restart_pause_reason
    with _auto_restart_pause_lock:
        _auto_restart_pause_depth += 1
        if _auto_restart_pause_depth == 1:
            _auto_restart_pause_reason = reason or "unspecified"
            logger.info("NOX自動再起動を一時停止: %s", _auto_restart_pause_reason)
        elif reason:
            _auto_restart_pause_reason = reason


def resume_auto_restart() -> None:
    """自動再起動の一時停止を解除する。"""
    global _auto_restart_pause_depth, _auto_restart_pause_reason
    with _auto_restart_pause_lock:
        if _auto_restart_pause_depth == 0:
            return
        _auto_restart_pause_depth -= 1
        if _auto_restart_pause_depth == 0:
            logger.info("NOX自動再起動を再開します。")
            _auto_restart_pause_reason = None


def is_auto_restart_paused() -> bool:
    with _auto_restart_pause_lock:
        return _auto_restart_pause_depth > 0


def get_auto_restart_pause_reason() -> Optional[str]:
    with _auto_restart_pause_lock:
        return _auto_restart_pause_reason

def note_black_screen(device_port: str, screen_mean: float) -> None:
    """Track black-screen duration and restart if it persists."""
    if screen_mean <= _BLACK_SCREEN_MEAN_THRESHOLD:
        now = time.time()
        since = _black_screen_since.get(device_port)
        if since is None:
            _black_screen_since[device_port] = now
            return
        if now - since >= _BLACK_SCREEN_RESTART_SECONDS:
            logger.warning(
                "%s: black screen detected for %.0fs; restarting",
                device_port,
                now - since,
            )
            _queue_device_restart(device_port, restart_type="black_screen")
            _black_screen_since[device_port] = now
    else:
        _black_screen_since.pop(device_port, None)

def _reset_recovery_attempts_if_expired(device_port: str, current_time: float) -> None:
    """時間経過により回復試行回数をリセットします。
    
    Args:
        device_port: デバイスポート
        current_time: 現在時刻
    """
    last_attempt_time = _recovery_attempt_time.get(device_port, 0)
    
    # 15分以上経過している場合、回復試行回数をリセット
    if current_time - last_attempt_time > RECOVERY_RESET_INTERVAL:
        if _recovery_attempts.get(device_port, 0) > 0:
            _recovery_attempts[device_port] = 0
            _recovery_attempt_time[device_port] = current_time

def _increment_recovery_attempts(device_port: str) -> None:
    """回復試行回数を増やします。
    
    Args:
        device_port: デバイスポート
    """
    current_time = time.time()
    _recovery_attempts[device_port] += 1
    _recovery_attempt_time[device_port] = current_time

# デバイス再起動制御用の新しい変数
_restart_queue_lock = threading.Lock()  # 再起動キューのロック
_last_global_restart_time = 0  # 最後にデバイス再起動が実行された時間

def is_device_in_error_state(device_port: str) -> bool:
    """デバイスがエラー状態かどうかを確認します。
    
    Args:
        device_port: デバイスポート
        
    Returns:
        エラー状態かどうか
    """
    return device_port in _device_in_error_state

def monitor_device_health(device_ports: list[str]) -> None:
    """
    デバイスの健全性を監視し、必要に応じて再起動を実行する (working version)
    
    Args:
        device_ports: 監視対象のデバイスポートリスト
    """
    # Aggressive restart logic - prioritize force restart
    for port in device_ports:
        if port in _device_in_error_state:
            ce = _consecutive_errors.get(port, 0)
            recovery_attempts = _recovery_attempts.get(port, 0)
            
            # 再起動条件（フリーズを早期検出）
            if ce >= 5 or recovery_attempts >= 3:  # 5回連続エラーまたは3回回復失敗で再起動
                # 条件ログは不要 - 再起動ログで十分
                if force_restart_nox_device(port, emergency=True):
                    # 強制再起動は既にforce_restart_nox_device内で2行ログ出力済み
                    # Reset error state on successful restart
                    _error_count[port] = 0
                    _consecutive_errors[port] = 0
                    _recovery_attempts[port] = 0
                    _device_in_error_state.discard(port)

def mark_device_error(device_port: str, error_message: str) -> None:
    """デバイスをエラー状態としてマークし、必要に応じて再起動を実行します。
    
    Args:
        device_port: デバイスポート
        error_message: エラーメッセージ
    """
    global _error_count, _device_in_error_state, _notified_devices, _error_notified_time, _consecutive_errors, _scheduled_notifications
    current_time = time.time()
    if current_time - _last_adb_reset_seen < 30:
        return
    
    # 回復試行回数のタイムリセット処理
    _reset_recovery_attempts_if_expired(device_port, current_time)
    
    # 重要なエラーかどうかを判定
    is_critical_error = any(keyword in error_message.lower() for keyword in [
        "連続失敗", "短時間内連続失敗", "deadobjectexception", "device not found"
    ])
    
    # エラーカウントを増加
    _error_count[device_port] = _error_count.get(device_port, 0) + 1
    _consecutive_errors[device_port] = _consecutive_errors.get(device_port, 0) + 1
    error_count = _error_count[device_port]
    consecutive_errors = _consecutive_errors[device_port]
    
    # 初めてのエラーの場合はログ出力とエラー状態設定
    if device_port not in _device_in_error_state:
        if not RESTART_VERBOSE and consecutive_errors >= 3:  # 3回以上でのみログ出力
            logger.warning(f"{device_port}: エラー検出 ({consecutive_errors}回)")
        _device_in_error_state.add(device_port)
        _error_notified_time[device_port] = current_time
    else:
        # 連続エラー数の通知（5回ごとに変更し、自動復旧を試行）
        if consecutive_errors % 5 == 0:
            if not RESTART_VERBOSE:
                logger.warning(f"{device_port}: 連続エラー ({consecutive_errors}回) - 自動復旧を試行中...")
            
            # ADB接続の自動復旧を試行
            try:
                if reconnect_device(device_port):
                    logger.info(f"{device_port}: ADB再接続に成功しました")
                    # エラーカウンターをリセット
                    _consecutive_errors[device_port] = 0
                    if device_port in _device_in_error_state:
                        _device_in_error_state.remove(device_port)
                else:
                    logger.warning(f"{device_port}: ADB再接続に失敗しました")
            except Exception as e:
                logger.error(f"{device_port}: 自動復旧中にエラー: {e}")
    
    # 再起動条件をチェック（重要エラーの場合は早期判定）
    restart_threshold = 5 if is_critical_error else 10
    if consecutive_errors >= restart_threshold:
        # 回復試行回数上限チェック（タイムリセット後）
        recovery_attempts = _recovery_attempts.get(device_port, 0)
        if recovery_attempts >= MAX_RECOVERY_ATTEMPTS:
            if not RESTART_VERBOSE:
                logger.warning(f"{device_port}: 回復試行回数上限に達しました ({recovery_attempts}回)")
            # 緊急時全NOXリセット判定
            if _should_trigger_emergency_reset():
                if not RESTART_VERBOSE:
                    logger.critical("● 緊急事態: 全NOXリセットを実行します")
                _emergency_reset_all_nox()
            return
        
        # 緊急時全NOXリセット判定
        if _should_trigger_emergency_reset():
            if not RESTART_VERBOSE:
                logger.critical("● 緊急事態: 全NOXリセットを実行します")
            _emergency_reset_all_nox()
            return
        
        # グローバル再起動レート制限チェック
        global _last_global_restart_time
        current_time = time.time()
        # 重要エラーの場合はグローバル制限を短縮
        global_limit = 60 if is_critical_error else 120
        if current_time - _last_global_restart_time < global_limit:
            return
        
        # Aggressive restart: emergency mode for immediate action
        if force_restart_nox_device(device_port, emergency=True):  # 緊急モードで即座再起動
            # 強制再起動は既にforce_restart_nox_device内で2行ログ出力済み
            # Reset error state on successful restart
            _error_count[device_port] = 0
            _consecutive_errors[device_port] = 0
            _recovery_attempts[device_port] = 0
            _device_in_error_state.discard(device_port)

def mark_device_recovered(device_port: str) -> None:
    """デバイスを回復状態としてマークします。
    
    Args:
        device_port: 回復したデバイスポート
    """
    global _error_count, _device_in_error_state, _notified_devices, _consecutive_errors, _scheduled_notifications
    
    # スケジュールされた通知があればキャンセル
    if device_port in _scheduled_notifications:
        _scheduled_notifications[device_port].cancel()
        del _scheduled_notifications[device_port]
    
    if device_port in _device_in_error_state:
        # 復旧ログは不要 - 回復完了ログで十分
        _device_in_error_state.remove(device_port)
        _error_count[device_port] = 0
        _consecutive_errors[device_port] = 0  # 連続エラーもリセット
        _recovery_attempts[device_port] = 0  # 回復試行回数もリセット
        _notified_devices.discard(device_port)
def record_device_progress(device_port: str) -> None:
    """端末で進捗が確認できたタイミングを記録する。"""
    with _progress_lock:
        _last_progress_time[device_port] = time.time()


def get_device_idle_time(device_port: str) -> float:
    """直近の進捗からの経過秒数を返す。進捗が無い場合は無限大扱い。"""
    with _progress_lock:
        last_seen = _last_progress_time.get(device_port)
    if last_seen is None:
        return float("inf")
    return time.time() - last_seen

def have_devices_been_idle(device_ports: Sequence[str], idle_threshold: float) -> bool:
    """すべての端末が指定秒数以上進捗していないかを判定する。"""
    if not device_ports:
        return False
    now = time.time()
    with _progress_lock:
        for device_port in device_ports:
            last_seen = _last_progress_time.get(device_port)
            if last_seen is None:
                return False
            if now - last_seen < idle_threshold:
                return False
    return True


def are_devices_ready_for_resume(device_ports: Sequence[str], max_unready: int = 0) -> bool:
    """全端末がエラー状態でなくADB応答も正常かを確認する。

    max_unready で許容する「再起動中などで未応答の端末」数を指定できる。
    """
    if not device_ports:
        return False

    unready = 0
    for device_port in device_ports:
        if is_device_in_error_state(device_port):
            if device_port in _restart_in_progress and unready < max_unready:
                unready += 1
                continue
            return False

        if not is_device_available(device_port):
            if device_port in _restart_in_progress and unready < max_unready:
                unready += 1
                continue
            return False

    return True

def set_host_wait_mode(device_port: str, active: bool) -> None:
    """覇者ホスト待機中の端末を登録/解除する。"""
    with _host_wait_lock:
        if active:
            _host_wait_ports.add(device_port)
        else:
            _host_wait_ports.discard(device_port)


def _is_host_wait_mode(device_port: str) -> bool:
    with _host_wait_lock:
        return device_port in _host_wait_ports

def _is_any_host_waiting() -> bool:
    with _host_wait_lock:
        return bool(_host_wait_ports)

def clear_device_cache(device_port: str) -> None:
    """デバイスのキャッシュをクリアします。
    
    Args:
        device_port: デバイスポート
    """
    from .core import _last_screenshot, _last_screenshot_time, _last_screen_digest, _screenshot_lock
    
    with _screenshot_lock:
        if device_port in _last_screenshot:
            del _last_screenshot[device_port]
            _last_screenshot_time[device_port] = 0
            _last_screen_digest.pop(device_port, None)

def _queue_device_restart(device_port: str, restart_type: str = "normal") -> None:
    """デバイス再起動をキューに追加します（安全な間隔で実行）。
    
    Args:
        device_port: デバイスポート
        restart_type: 再起動の理由
    """
    if is_auto_restart_paused():
        reason = get_auto_restart_pause_reason()
        logger.debug(
            "%s: 自動再起動ポーズ中のため再起動キューをスキップ (%s)",
            device_port,
            reason or "reason_unknown",
        )
        return
    if _is_host_wait_mode(device_port) or _is_any_host_waiting():
        logger.debug("%s: 覇者ホスト待機中のため再起動キューをスキップ (%s)", device_port, restart_type)
        return

    # 回復試行回数上限チェック
    if _recovery_attempts.get(device_port, 0) >= MAX_RECOVERY_ATTEMPTS:
        logger.warning(f"{device_port}: 再起動キュー上限到達。緊急モードで即時再起動を試行します")
        def _emergency_restart():
            success = force_restart_nox_device(device_port, emergency=True)
            if not success:
                logger.error(f"{device_port}: 緊急再起動に失敗。全体リセットを検討します")
        threading.Thread(target=_emergency_restart, daemon=True).start()
        return
    
    # 回復試行回数を増やす
    _increment_recovery_attempts(device_port)
    
    def _execute_restart():
        try:
            # グローバルロックを取得して再起動を制御
            with _restart_queue_lock:
                if is_auto_restart_paused():
                    logger.debug(
                        "%s: 自動再起動ポーズ中のため遅延再起動をキャンセル",
                        device_port,
                    )
                    return
                global _last_global_restart_time
                current_time = time.time()
                
                # 最後の再起動から十分な時間が経過しているかチェック
                if current_time - _last_global_restart_time < DEVICE_RESTART_QUEUE_DELAY:
                    wait_time = DEVICE_RESTART_QUEUE_DELAY - (current_time - _last_global_restart_time)
                    time.sleep(wait_time)
                
                # 現在再起動中のデバイス数を確認
                if len(_restart_in_progress) >= MAX_CONCURRENT_RESTARTS:
                    # 30秒後に再度試行
                    threading.Timer(30.0, _execute_restart).start()
                    return
                
                # 再起動実行
                success = force_restart_nox_device(device_port)
                
                if success:
                    _last_global_restart_time = time.time()
                    # 再起動成功時に回復試行回数をリセット
                    _recovery_attempts[device_port] = 0
                else:
                    if not RESTART_VERBOSE:
                        logger.warning(f"{device_port}: 再起動失敗")
                    
        except Exception as e:
            logger.error(f"{device_port}: 再起動処理中にエラー: {e}")
    
    # 別スレッドで実行
    restart_thread = threading.Thread(target=_execute_restart, daemon=True)
    restart_thread.start()

def _should_trigger_emergency_reset() -> bool:
    """緊急時全NOXリセットが必要かどうかを判定します。
    
    Returns:
        緊急リセットが必要な場合True
    """
    if is_auto_restart_paused():
        reason = get_auto_restart_pause_reason()
        logger.debug(
            "自動再起動ポーズ中のため緊急リセット判定をスキップ (%s)",
            reason or "reason_unknown",
        )
        return False
    global _emergency_reset_time
    current_time = time.time()
    if current_time - _last_adb_reset_seen < 30 or _is_any_host_waiting():
        return False
    
    # 最後の緊急リセットから20分以内は実行しない（実用的な値）
    if current_time - _emergency_reset_time < 1200 or _is_any_host_waiting():
        return False
    
    # 現在エラー状態のデバイス数を確認
    error_devices = len(_device_in_error_state)
    
    # 全8端末中4端末以上がエラー状態の場合緊急リセット（実用的な条件）
    if error_devices >= 4:
        logger.critical(f"緊急リセット判定: エラー状態デバイス {error_devices}台")
        _emergency_reset_time = current_time
        return True
    
    # 再起動中のデバイス数が多い場合（実用的な条件）
    if len(_restart_in_progress) >= 3:
        logger.critical(f"緊急リセット判定: 再起動中デバイス {len(_restart_in_progress)}台")
        _emergency_reset_time = current_time
        return True
    
    # 連続エラーが多いデバイスが複数ある場合（実用的な条件）
    high_error_devices = sum(1 for count in _consecutive_errors.values() if count >= 50)
    if high_error_devices >= 3:
        logger.critical(f"緊急リセット判定: 高エラー端末 {high_error_devices}台")
        _emergency_reset_time = current_time
        return True
    
    # 回復試行回数上限に達したデバイスが複数ある場合（実用的な条件）
    max_recovery_devices = sum(1 for count in _recovery_attempts.values() if count >= MAX_RECOVERY_ATTEMPTS)
    if max_recovery_devices >= 3:
        logger.critical(f"緊急リセット判定: 回復試行上限到達端末 {max_recovery_devices}台")
        _emergency_reset_time = current_time
        return True
    
    # エラー状態のデバイスと回復試行上限到達デバイスの合計が多い場合（実用的な条件）
    total_problem_devices = error_devices + max_recovery_devices
    if total_problem_devices >= 4:
        logger.critical(f"緊急リセット判定: 問題デバイス合計 {total_problem_devices}台 (エラー{error_devices}台+回復上限{max_recovery_devices}台)")
        _emergency_reset_time = current_time
        return True
    
    return False

def _emergency_reset_all_nox() -> None:
    """緊急時全NOXリセット処理を実行します。
    
    全NOXプロセスを強制終了し、段階的に再起動します。
    """
    if is_auto_restart_paused():
        reason = get_auto_restart_pause_reason()
        logger.warning(
            "自動再起動ポーズ中のため緊急NOXリセットをスキップします (%s)",
            reason or "reason_unknown",
        )
        return
    if _is_any_host_waiting():
        logger.warning("覇者ホスト待機中のため緊急NOXリセットをスキップします")
        return
    try:
        logger.critical("🚨 緊急事態: 全NOXリセットを開始します")
        
        # ステップ1: 全NOXプロセスを強制終了
        _force_terminate_all_nox()
        
        # ステップ2: 状態をリセット
        _reset_all_device_states()
        
        # ステップ3: 段階的再起動
        _staged_nox_restart()
        
        logger.critical("🚨 緊急全NOXリセット完了")
        
    except Exception as e:
        logger.critical(f"🚨 緊急全NOXリセット中にエラー: {e}")

def _force_terminate_all_nox() -> None:
    """全NOXプロセスを強制終了します。"""
    try:
        logger.critical("● 全NOXプロセス強制終了開始")
        
        # すべてのNOXプロセスを強制終了
        kill_commands = [
            ['taskkill', '/F', '/IM', 'Nox.exe'],
            ['taskkill', '/F', '/IM', 'NoxVMHandle.exe'],
            ['taskkill', '/F', '/IM', 'Nox_vbox_headless.exe'],
            ['taskkill', '/F', '/FI', 'IMAGENAME eq Nox*.exe'],
            ['taskkill', '/F', '/FI', 'WINDOWTITLE eq Nox_*'],
        ]
        
        for cmd in kill_commands:
            try:
                subprocess.run(cmd, capture_output=True, timeout=15)
                time.sleep(2)
            except Exception:
                continue
        
        # psutilを使った確実な終了
        try:
            for proc in psutil.process_iter(['pid', 'name']):
                try:
                    name = proc.info['name'] or ''
                    if 'nox' in name.lower():
                        proc.kill()
                        proc.wait(timeout=5)
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.TimeoutExpired):
                    continue
        except Exception:
            pass
        
        # ADBサーバーリセット
        try:
            reset_adb_server()
        except Exception:
            pass
        
        # 終了確認のため少し待機
        time.sleep(10)
        
        logger.critical("● 全NOXプロセス強制終了完了")
        
    except Exception as e:
        logger.critical(f"● 全NOXプロセス強制終了中にエラー: {e}")


def _run_silent_taskkill(command: str) -> None:
    """taskkillコマンドを静かに実行するヘルパー。"""
    try:
        subprocess.run(
            command,
            shell=True,
            capture_output=True,
            timeout=15,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except Exception as exc:
        logger.debug("taskkill実行エラー (%s): %s", command, exc)

def _reset_all_device_states() -> None:
    """全デバイスの状態をリセットします。"""
    try:
        logger.critical("● 全デバイス状態リセット開始")
        
        global _error_count, _consecutive_errors, _device_in_error_state
        global _notified_devices, _error_notified_time, _device_restart_time
        global _last_restart_attempt, _restart_in_progress
        global _recovery_attempts, _recovery_attempt_time
        
        # 全状態をクリア
        _error_count.clear()
        _consecutive_errors.clear()
        _device_in_error_state.clear()
        _notified_devices.clear()
        _error_notified_time.clear()
        _device_restart_time.clear()
        _last_restart_attempt.clear()
        _restart_in_progress.clear()
        _recovery_attempts.clear()
        _recovery_attempt_time.clear()
        
        logger.critical("● 全デバイス状態リセット完了")
        
    except Exception as e:
        logger.critical(f"● 全デバイス状態リセット中にエラー: {e}")

def _staged_nox_restart() -> None:
    """段階的にNOXを再起動します。"""
    try:
        logger.critical("🔄 NOX再起動開始")
        
        # 優先度順のデバイスリスト（重要なデバイスから）
        priority_devices = [
            ("127.0.0.1:62026", 2),  # ユーザーが言及した2番端末
            ("127.0.0.1:62025", 1),
            ("127.0.0.1:62027", 3),
            ("127.0.0.1:62028", 4),
            ("127.0.0.1:62029", 5),
            ("127.0.0.1:62030", 6),
            ("127.0.0.1:62031", 7),
            ("127.0.0.1:62032", 8),
        ]
        
        # 一括起動（最大8台）
        threads = []
        logger.critical(f"● NOX全台一括起動 ({len(priority_devices)}台)")
        for device_port, instance_number in priority_devices:
            thread = threading.Thread(
                target=_restart_single_nox_safely,
                args=(device_port, instance_number),
                daemon=True
            )
            threads.append(thread)
            thread.start()

        for thread in threads:
            thread.join(timeout=300)
        
        logger.critical("🔄 NOX再起動完了")
        
    except Exception as e:
        logger.critical(f"🔄 NOX再起動エラー: {e}")

def _restart_single_nox_safely(device_port: str, instance_number: int) -> None:
    """1つのNOXを安全に再起動します。"""
    try:
        logger.critical(f"● NOX起動: {device_port} (インスタンス {instance_number})")
        
        # 強化版再起動を実行
        success = _restart_nox_instance_enhanced(instance_number, device_port)
        
        if success:
            logger.critical(f"● NOX起動成功: {device_port}")
        else:
            logger.critical(f"● NOX起動失敗: {device_port}")
            
    except Exception as e:
        logger.critical(f"● NOX起動中にエラー: {device_port} - {e}")

def emergency_reset_all_nox_manual() -> None:
    """手動で緊急時全NOXリセットを実行します。
    
    この関数は管理者が手動で全NOXをリセットする際に使用します。
    """
    try:
        logger.critical("🚨 手動緊急全NOXリセット開始")
        _emergency_reset_all_nox()
        logger.critical("🚨 手動緊急全NOXリセット完了")
    except Exception as e:
        logger.critical(f"🚨 手動緊急全NOXリセット中にエラー: {e}")

def get_nox_status_summary() -> Dict[str, Any]:
    """NOXの状態サマリーを取得します。
    
    Returns:
        NOXの状態情報を含む辞書
    """
    try:
        return {
            "error_devices": len(_device_in_error_state),
            "restart_in_progress": len(_restart_in_progress),
            "error_device_list": list(_device_in_error_state),
            "restart_devices": list(_restart_in_progress),
            "consecutive_errors": dict(_consecutive_errors),
            "recovery_attempts": dict(_recovery_attempts),
            "last_emergency_reset": _emergency_reset_time,
        }
    except Exception as e:
        logger.error(f"NOX状態サマリー取得中にエラー: {e}")
        return {"error": str(e)}

def _queue_device_recovery(device_port: str) -> None:
    """デバイス回復処理をキューに追加します（回復試行回数制限付き）。
    
    Args:
        device_port: デバイスポート
    """
    # 回復試行回数上限チェック
    if _recovery_attempts.get(device_port, 0) >= MAX_RECOVERY_ATTEMPTS:
        return
    
    def _execute_recovery():
        try:
            pass
            success = recover_device(device_port)
            
            if success:
                pass
            else:
                pass
                
        except Exception as e:
            pass
    
    # 別スレッドで実行
    recovery_thread = threading.Thread(target=_execute_recovery, daemon=True)
    recovery_thread.start()

def force_restart_nox_device(device_port: str, emergency: bool = False) -> bool:
    """
    NOXデバイスを強制的に再起動する (working version from mon6)
    
    Args:
        device_port: デバイスポート
        emergency: 緊急モード（クールダウンを無視）
        
    Returns:
        bool: 再起動に成功したかどうか
    """
    # インスタンス番号を取得
    match = re.match(r"127\.0\.0\.1:(\d+)", device_port)
    if not match:
        logger.error(f"デバイスポート形式が不正: {device_port}")
        return False
    
    port_number = int(match.group(1))
    instance_number = port_number - 62024
    
    if is_auto_restart_paused():
        reason = get_auto_restart_pause_reason()
        logger.debug(
            "%s: 自動再起動ポーズ中のためNOX再起動をスキップ (%s)",
            device_port,
            reason or "reason_unknown",
        )
        return False
    if _is_host_wait_mode(device_port) or _is_any_host_waiting():
        logger.info("%s: 覇者ホスト待機中のためNOX再起動を抑止します", device_port)
        return False

    # 再起動管理処理
    global _restart_in_progress, _last_restart_attempt, _device_in_error_state
    current_time = time.time()
    
    # 同時に複数の再起動を避ける
    if device_port in _restart_in_progress:
        return False
    
    # 前回の再起動からの時間を確認 - 緊急モードでは無視
    if not emergency:
        last_restart = _last_restart_attempt.get(device_port, 0)
        if current_time - last_restart < ERROR_COOLDOWN_PERIOD:  # クールダウン期間
            return False
    else:
        pass  # 緊急再起動の場合はクールダウンを無視
    
    # 再起動処理開始
    _restart_in_progress.add(device_port)
    _last_restart_attempt[device_port] = current_time
    
    from utils.device_utils import get_terminal_number
    terminal_num = get_terminal_number(device_port)
    logger.debug(f"{terminal_num}: 回復開始")  # 1行目: 検出
    
    try:
        # ADB接続の解除
        try:
            disconnect_cmd = [NOX_ADB_PATH, 'disconnect', device_port]
            subprocess.run(
                disconnect_cmd, 
                timeout=5, 
                capture_output=True, 
                text=True, 
                encoding='utf-8', 
                errors='replace'
            )
        except Exception:
            pass
        
        try:
            # Noxのプロセスを探す際にインスタンス番号でフィルタリング
            nox_processes = []
            nox_vm_processes = []
            
            for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                try:
                    # コマンドラインでインスタンス番号をチェック
                    cmdline = proc.cmdline() if hasattr(proc, 'cmdline') else []
                    instance_match = False
                    
                    # インスタンス番号を含むか確認
                    for cmd in cmdline:
                        if f"Nox_{instance_number}" in cmd:
                            instance_match = True
                            break
                    
                    # 該当するインスタンスのプロセスのみ追加
                    if proc.info['name'] and 'Nox.exe' in proc.info['name'] and instance_match:
                        nox_processes.append(proc)
                    elif proc.info['name'] and 'NoxVMHandle.exe' in proc.info['name'] and instance_match:
                        nox_vm_processes.append(proc)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            
            # 該当するプロセスを終了
            for proc in nox_processes + nox_vm_processes:
                try:
                    proc.kill()
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
        except Exception:
            pass
        
        # 通常のtaskkillコマンドも実行（静かに）
        _run_silent_taskkill(f'taskkill /F /FI "IMAGENAME eq Nox.exe" /FI "WINDOWTITLE eq Nox_{instance_number}"')
        _run_silent_taskkill(f'taskkill /F /FI "IMAGENAME eq NoxVMHandle.exe" /FI "WINDOWTITLE eq *{instance_number}"')
        
        # 十分な待機時間
        time.sleep(10)
        
        # ADBサーバーのリセット
        try:
            reset_adb_server()
        except Exception:
            pass
        
        # 追加の待機時間
        time.sleep(5)
        
        # Noxの再起動
        try:
            nox_path = r"C:\Program Files (x86)\Nox\bin\Nox.exe"
            nox_command = f'"{nox_path}" -clone:Nox_{instance_number}'
            
            # サブプロセスとして実行
            process = subprocess.Popen(nox_command, shell=True)
            
            # より長めの起動完了待機時間
            wait_time = 60 + (instance_number % 4) * 10
            time.sleep(wait_time)
            
            # ADB接続を確立（複数回試行）
            connected = False
            for connect_attempt in range(5):
                try:
                    connect_cmd = [NOX_ADB_PATH, 'connect', device_port]
                    result = subprocess.run(
                        connect_cmd, 
                        timeout=5, 
                        capture_output=True, 
                        text=True, 
                        encoding='utf-8', 
                        errors='replace'
                    )
                    
                    # 結果の確認
                    if result and hasattr(result, 'stdout'):
                        stdout = result.stdout
                        if "connected" in stdout or "already connected" in stdout:
                            connected = True
                            
                            # デバイスの応答を確認
                            check_cmd = [NOX_ADB_PATH, '-s', device_port, 'shell', 'echo', 'connected_test']
                            check_result = subprocess.run(
                                check_cmd, 
                                timeout=5, 
                                capture_output=True, 
                                text=True, 
                                encoding='utf-8', errors='replace'
                            )
                            
                            if check_result.returncode == 0 and "connected_test" in check_result.stdout:
                                # 完全に応答可能な状態
                                break
                            else:
                                connected = False  # まだ完全には接続されていない
                except Exception as e:
                    pass
                
                # 次の試行前に待機
                time.sleep(5)
            
            if not connected:
                logger.debug(f"デバイス {device_port} への接続に失敗しました")
                _restart_in_progress.discard(device_port)
                logging.disable(logging.NOTSET)   # ← ログ抑制を解除しておく
                return False
            
            # デバイス状態をリセット
            _error_count[device_port] = 0
            _consecutive_errors[device_port] = 0
            _device_in_error_state.discard(device_port)
            
            # さらに待機してからアプリ起動
            time.sleep(10)
            
            # アプリを起動
            start_monster_strike_app(device_port)
            
            # アプリが起動するまで待機
            time.sleep(10)
            
            # 再起動完了
            logger.info(f"{terminal_num}: 再起動完了")  # 2行目: 完了
            _restart_in_progress.discard(device_port)
            
            # 成功を通知
            return True
            
        except Exception:
            _restart_in_progress.discard(device_port)
            return False
            
    except Exception:
        _restart_in_progress.discard(device_port)
        return False

def recover_device(device_port: str) -> bool:
    """デバイス回復処理（強制再起動優先モード）"""
    global _consecutive_errors, _recovery_attempts
    
    # 回復試行回数を記録
    _recovery_attempts[device_port] = _recovery_attempts.get(device_port, 0) + 1
    recovery_count = _recovery_attempts[device_port]
    consecutive_errors = _consecutive_errors.get(device_port, 0)
    
    from utils.device_utils import get_terminal_number
    terminal_num = get_terminal_number(device_port)
    logger.debug(f"{terminal_num}: 回復開始")
    
    # 強制再起動優先条件（安定性重視で大幅制限）
    if recovery_count >= 10 or consecutive_errors >= 50:  # 10回回復失敗または50回連続エラーで強制再起動
        if force_restart_nox_device(device_port, emergency=True):  # 緊急モードで再起動
            logger.debug(f"{terminal_num}: 回復完了")
            # 成功時は全カウンターをリセット
            _error_count[device_port] = 0
            _consecutive_errors[device_port] = 0
            _recovery_attempts[device_port] = 0
            _device_in_error_state.discard(device_port)
            return True
        else:
            return False
    
    try:
        # 軽度な回復処理（初回のみ）
        if recovery_count == 1 and reconnect_device(device_port):
            logger.debug(f"{terminal_num}: 回復完了")
            return True
        
        # アプリ再起動
        if restart_monster_strike_app(device_port):
            return True
            
        return False
        
    except Exception:
        return False

def _restart_nox_instance_enhanced(instance_number: int, device_port: str) -> bool:
    """強化版NOXインスタンス再起動"""
    try:
        # シンプルなNOX起動
        nox_command = f'"{NOX_EXE_PATH}" -clone:Nox_{instance_number}'
        process = subprocess.Popen(nox_command, shell=True)
        time.sleep(20)  # 起動待機
        
        # 接続確認
        for _ in range(30):
            if is_device_available(device_port):
                return True
            time.sleep(2)
        
        return False
        
    except Exception:
        return False

def monitor_nox_health() -> None:
    """NOXヘルスモニタリング（シンプル版）"""
    try:
        # 基本的なヘルスチェック
        error_devices = len(_device_in_error_state)
        restart_devices = len(_restart_in_progress)
        
        if error_devices > 0 or restart_devices > 0:
            pass
        
        # 緊急リセット判定
        if _should_trigger_emergency_reset():
            logger.warning("NOXヘルス: 緊急リセット条件に該当")
            
    except Exception as e:
        logger.error(f"NOXヘルスモニタリング中にエラー: {e}")


def notify_adb_reset(ts: float | None = None) -> None:
    global _last_adb_reset_seen
    try:
        _last_adb_reset_seen = float(ts if ts is not None else time.time())
    except Exception:
        _last_adb_reset_seen = time.time()


def notify_virtual_machine_failure() -> None:
    """NOX仮想マシン起動失敗を検知した際に呼び出し、全体リセットを実行する。"""
    global _last_virtual_machine_failure
    now = time.time()
    try:
        cfg = get_config()
        enabled = bool(cfg.extra.get("enable_global_nox_reset_on_vm_fail", False))
    except Exception:
        enabled = False
    if not enabled:
        logger.warning("NOX仮想マシン起動失敗を検知。全NOXリセットは無効化されています。")
        return
    if _is_any_host_waiting():
        logger.warning("覇者ホスト待機中のため仮想マシン失敗リセットをスキップ")
        return
    if now - _last_virtual_machine_failure < 60:
        return
    _last_virtual_machine_failure = now
    logger.warning("NOX仮想マシン起動失敗を検知。全NOXリセットを実行します。")
    _emergency_reset_all_nox()


def _freeze_monitor_loop() -> None:
    while True:
        time.sleep(_FREEZE_CHECK_INTERVAL)
        now = time.time()
        with _progress_lock:
            tracked_ports = list(_last_progress_time.keys())
            stale_ports = [
                port for port, stamp in _last_progress_time.items()
                if now - stamp >= _FREEZE_THRESHOLD
            ]
            for port in stale_ports:
                _last_progress_time[port] = now
        if tracked_ports and len(stale_ports) == len(tracked_ports):
            global _last_global_stall_reset
            if now - _last_global_stall_reset >= _GLOBAL_STALL_RESET_COOLDOWN:
                logger.critical("全端末で10分以上進捗が無いため緊急NOXリセットを実行します")
                _last_global_stall_reset = now
                _emergency_reset_all_nox()
                continue
        for port in stale_ports:
            if port in _restart_in_progress or _is_host_wait_mode(port):
                continue
            terminal = get_terminal_number(port)
            logger.warning("%s: 10分以上進捗が無いためNOXを再起動します", terminal)
            _queue_device_restart(port, restart_type="freeze_timeout")


def _start_freeze_monitor() -> None:
    thread = threading.Thread(target=_freeze_monitor_loop, name="FreezeMonitor", daemon=True)
    thread.start()


_start_freeze_monitor()
