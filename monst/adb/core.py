"""
monst.adb.core - Core ADB command execution and device management.

このモジュールはADBコマンドの実行とデバイス管理の中核機能を提供します。
スレッドセーフな実装で並列操作をサポートし、エラーハンドリングとリトライ機能を内蔵しています。
"""

from __future__ import annotations

import subprocess
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Deque, Dict, List, Optional, Set, Tuple

from config import get_config
from logging_util import logger

# ---------------------------------------------------------------------------
# Internal state management (thread-safe)
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class _State:
    """ADB操作の内部状態を管理するデータクラス。
    
    スレッドセーフなエラートラッキングと並行制御を提供します。
    """
    # エラートラッキング
    cmd_error: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    last_error_time: Dict[str, float] = field(default_factory=lambda: defaultdict(float))
    device_errors: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    # 直近エラー・再接続状態
    error_lock: threading.Lock = field(default_factory=threading.Lock)
    recent_adb_errors: Deque[float] = field(default_factory=deque)
    reconnect_lock: threading.Lock = field(default_factory=threading.Lock)
    reconnect_failures: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    reconnect_restart_inflight: Set[str] = field(default_factory=set)

    # 並行制御セマフォ
    sem: threading.Semaphore | None = None
    init_lock: threading.Lock = field(default_factory=threading.Lock)
    adb_reset_lock: threading.Lock = field(default_factory=threading.Lock)
    last_adb_reset: float = 0.0

    def ensure_semaphore(self) -> threading.Semaphore:
        """セマフォの遅延初期化（ダブルチェックロッキング）。
        
        Returns:
            並行実行数を制限するセマフォ
        """
        if self.sem is None:
            with self.init_lock:
                if self.sem is None:
                    adb_max = getattr(get_config(), "ADB_MAX_CONCURRENT", 3)
                    self.sem = threading.Semaphore(int(adb_max))
        return self.sem

_state = _State()


def _register_reconnect_failure(device_port: str) -> int:
    """Track consecutive reconnect failures per device."""
    with _state.reconnect_lock:
        _state.reconnect_failures[device_port] += 1
        return _state.reconnect_failures[device_port]


def _reset_reconnect_state(device_port: str) -> None:
    """Clear reconnect counters and pending restarts for the device."""
    with _state.reconnect_lock:
        _state.reconnect_failures.pop(device_port, None)
        _state.reconnect_restart_inflight.discard(device_port)


def _schedule_force_restart(device_port: str, failure_count: int) -> None:
    """Schedule a background NOX restart when reconnect keeps failing."""
    with _state.reconnect_lock:
        if device_port in _state.reconnect_restart_inflight:
            return
        _state.reconnect_restart_inflight.add(device_port)

    def _restart_worker() -> None:
        try:
            from monst.image.device_management import force_restart_nox_device

            if force_restart_nox_device(device_port, emergency=True):
                logger.warning(
                    "Device %s force-restarted after %d reconnect failures",
                    device_port,
                    failure_count,
                )
        except Exception as exc:  # pragma: no cover - best effort recovery
            logger.debug(
                "Emergency restart for %s failed: %s",
                device_port,
                exc,
            )
        finally:
            with _state.reconnect_lock:
                _state.reconnect_restart_inflight.discard(device_port)

    threading.Thread(target=_restart_worker, daemon=True).start()

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DEFAULT_TIMEOUT = 20  # 15秒から20秒に延長（swipeコマンドのタイムアウト改善）
_RETRY = 3  # 5回から3回に減少（過度なリトライを防止）
_ERR_INTERVAL = 3600  # エラーログの間隔（秒）
_FATAL_EXIT_CODES = {
    0xC0000005,  # STATUS_ACCESS_VIOLATION
    0xC0000402,  # ADB daemon crash observed on Windows
}
_ADB_RESET_BACKOFF = 8.0  # seconds
_ADB_RESET_VERIFY_ATTEMPTS = 5
_RECENT_ERROR_WINDOW = 30.0  # seconds
_ADB_RESET_ERROR_THRESHOLD = 5
_MAX_RECONNECT_ATTEMPTS = 3
_RECONNECT_FAILURE_RESTART_THRESHOLD = 3

APP_PACKAGE = "jp.co.mixi.monsterstrike"
APP_ACTIVITY = "jp.co.mixi.monsterstrike.MonsterStrike"

# ---------------------------------------------------------------------------
# Low-level subprocess wrapper
# ---------------------------------------------------------------------------

def _run(cmd: List[str], timeout: int) -> Tuple[Optional[str], Optional[str], int]:
    """subprocess.runの薄いラッパー（PC環境適応版）。
    
    Args:
        cmd: 実行するコマンドリスト
        timeout: タイムアウト秒数
        
    Returns:
        (stdout, stderr, returncode) のタプル。例外は発生させない。
    """
    try:
        # Windows環境での文字エンコーディング適応
        import platform
        encoding = "utf-8"
        if platform.system() == "Windows":
            # Windows環境では複数のエンコーディングを試行
            try:
                # pushコマンドの場合はプログレスバー出力を抑制
                is_push_command = len(cmd) >= 2 and "push" in cmd
                stderr_setting = subprocess.DEVNULL if is_push_command else subprocess.PIPE
                
                cp = subprocess.run(
                    cmd,
                    timeout=timeout,
                    stdout=subprocess.PIPE,
                    stderr=stderr_setting,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                )
                return cp.stdout, cp.stderr if not is_push_command else None, cp.returncode
            except UnicodeDecodeError:
                # UTF-8で失敗した場合はShift_JISを試行
                try:
                    # pushコマンドの場合はプログレスバー出力を抑制
                    is_push_command = len(cmd) >= 2 and "push" in cmd
                    stderr_setting = subprocess.DEVNULL if is_push_command else subprocess.PIPE
                    
                    cp = subprocess.run(
                        cmd,
                        timeout=timeout,
                        stdout=subprocess.PIPE,
                        stderr=stderr_setting,
                        text=True,
                        encoding="shift_jis",
                        errors="replace",
                    )
                    return cp.stdout, cp.stderr if not is_push_command else None, cp.returncode
                except:
                    # 最後の手段として binary mode で実行
                    cp = subprocess.run(
                        cmd,
                        timeout=timeout,
                        capture_output=True,
                    )
                    stdout = cp.stdout.decode('utf-8', errors='replace') if cp.stdout else None
                    stderr = cp.stderr.decode('utf-8', errors='replace') if cp.stderr else None
                    return stdout, stderr, cp.returncode
        else:
            cp = subprocess.run(
                cmd,
                timeout=timeout,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            return cp.stdout, cp.stderr, cp.returncode
    except subprocess.TimeoutExpired:
        return None, "<timeout>", 1
    except Exception as exc:  # pragma: no cover
        return None, str(exc), 1

# ---------------------------------------------------------------------------
# Public API

def _normalize_return_code(rc: int) -> int:
    """Return the unsigned representation of a Windows process exit code."""
    return rc if rc >= 0 else rc + (1 << 32)

def _is_fatal_adb_failure(rc: int, err: Optional[str], out: Optional[str]) -> bool:
    """Detect ADB crashes / non-responsive daemon scenarios."""
    normalized = _normalize_return_code(rc)
    if normalized in _FATAL_EXIT_CODES or (normalized & 0xC0000000) == 0xC0000000:
        return True
    combined = " ".join(part for part in (err, out) if part).lower()
    if any(keyword in combined for keyword in ("not responding", "daemon not running", "daemon still not running", "cannot connect to daemon")):
        return True
    return False

def _recover_from_adb_crash(device_port: Optional[str]) -> None:
    """Attempt to recover from an unrecoverable ADB crash."""
    logger.warning("ADB daemon appears to have crashed; attempting synchronized restart")
    if not reset_adb_server(force=True):
        logger.error("ADB reset failed; manual intervention may be required")
        return
    time.sleep(1.5)
    if device_port:
        try:
            if reconnect_device(device_port):
                logger.info("Device %s reconnected after ADB restart", device_port)
        except Exception as exc:
            logger.debug("Device %s reconnect attempt after ADB reset raised: %s", device_port, exc)

# Public API
# ---------------------------------------------------------------------------

def run_adb_command_detailed(
    args: List[str], 
    device_port: Optional[str] = None, 
    timeout: int = _DEFAULT_TIMEOUT
) -> Tuple[Optional[str], Optional[str], int]:
    """ADBコマンドを実行し、詳細な結果を返します（診断用）。
    
    Args:
        args: ADBコマンドの引数リスト
        device_port: 対象デバイスのポート（例: "127.0.0.1:62001"）
        timeout: タイムアウト秒数
        
    Returns:
        (stdout, stderr, returncode) のタプル
        
    Example:
        >>> stdout, stderr, rc = run_adb_command_detailed(["push", "file.txt", "/sdcard/"])
        >>> if rc != 0:
        ...     print(f"Error: {stderr}")
    """
    cfg = get_config()
    base_cmd = [cfg.NOX_ADB_PATH]
    if device_port:
        base_cmd += ["-s", device_port]
    cmd = base_cmd + args

    key = f"{device_port or ''}|{' '.join(args)}"
    sem = _state.ensure_semaphore()

    with sem:
        out, err, rc = _run(cmd, timeout)
        
        # 詳細な診断情報をログ出力
        if rc != 0:
            logger.debug(f"ADB command failed: {' '.join(cmd)}")
            logger.debug(f"Return code: {rc}")
            logger.debug(f"Stdout: {out}")
            logger.debug(f"Stderr: {err}")
        
        return out, err, rc

def run_adb_command(
    args: List[str], 
    device_port: Optional[str] = None, 
    timeout: int = _DEFAULT_TIMEOUT
) -> Optional[str]:
    """ADBコマンドを実行し、標準出力を返します。

    Args:
        args: ADBコマンドの引数リスト
        device_port: 対象デバイスのポート（例: "127.0.0.1:62001"）
        timeout: タイムアウト秒数

    Returns:
        成功時は標準出力、失敗時はNone
    """
    cfg = get_config()
    base_cmd = [cfg.NOX_ADB_PATH]
    if device_port:
        base_cmd += ["-s", device_port]
    cmd = base_cmd + args
    cmd_str = " ".join(cmd)

    key = f"{device_port or ''}|{' '.join(args)}"
    sem = _state.ensure_semaphore()

    with sem:
        for attempt in range(_RETRY + 1):
            out, err, rc = _run(cmd, timeout)
            if rc == 0:
                # 成功: エラーカウンターをリセットして出力を返す
                _state.cmd_error.pop(key, None)
                return out

            fatal_failure = _is_fatal_adb_failure(rc, err, out)
            if fatal_failure and attempt < _RETRY:
                _recover_from_adb_crash(device_port)
                continue

            # エラー: 自動復旧機構付きログ出力
            now = time.time()
            with _state.error_lock:
                _state.recent_adb_errors.append(now)
                while (
                    _state.recent_adb_errors
                    and now - _state.recent_adb_errors[0] > _RECENT_ERROR_WINDOW
                ):
                    _state.recent_adb_errors.popleft()
            cnt = _state.cmd_error[key] = _state.cmd_error.get(key, 0) + 1
            raw_error = (err or out or "").strip()
            if not raw_error:
                raw_error = "<no output>"
            error_message = raw_error[:200]
            error_lower = error_message.lower()

            # 重要な接続エラーは即座に復旧を試行
            if any(x in error_lower for x in ("connection reset", "protocol fault", "device offline")):
                if device_port and attempt == 0:  # 最初の試行時のみ復旧を試行
                    logger.warning("Critical ADB error detected, attempting recovery for %s", device_port)
                    if reconnect_device(device_port):
                        logger.info("Device %s successfully reconnected, retrying command", device_port)
                        continue  # 復旧成功時は直ちにリトライ

            if fatal_failure:
                logger.error(
                    "ADB fatal error (%s): rc=%s msg=%s",
                    cmd_str,
                    rc,
                    error_message,
                )

            if now - _state.last_error_time.get(key, 0) > _ERR_INTERVAL:
                # タイムアウトエラーの場合は特別な処理
                if error_message == "<timeout>":
                    logger.warning("ADB timeout (%s): Command timed out after %d seconds", key, timeout)
                # デバイス接続エラーの場合はDEBUGレベルでログ出力
                elif "not found" in error_lower or "connect failed" in error_lower:
                    logger.debug("ADB connection error (%s): %s", key, error_message)
                else:
                    logger.error("ADB error (%s): %s", key, error_message)
                _state.last_error_time[key] = now
                _state.cmd_error[key] = 1  # ログ出力後にカウンターリセット

            # デバイス別エラー統計
            if device_port:
                _state.device_errors[device_port] += 1

                # NOXフリーズの可能性があるエラーを自動復旧システムに報告
                freeze_indicators = ["device", "not found", "timeout", "connect failed", "offline"]
                if any(indicator in error_lower for indicator in freeze_indicators):
                    try:
                        from monst.image.device_management import mark_device_error
                        mark_device_error(device_port, f"ADBエラー（フリーズ疑い）: {error_message}")
                    except ImportError:
                        pass  # オプション機能のため無視

            if attempt < _RETRY:
                time.sleep(0.5 * (attempt + 1))
                continue
            return None  # リトライ回数超過

def perform_action_enhanced(
    device_port: str,
    action: str,
    x: int,
    y: int,
    x2: Optional[int] = None,
    y2: Optional[int] = None,
    duration: int = 150,
    retry_count: int = 3
) -> bool:
    """ULTRATHINK版: 強化されたデバイス操作関数
    
    Args:
        device_port: 対象デバイスのポート
        action: "tap" または "swipe"
        x, y: 開始座標
        x2, y2: 終了座標（swipe時のみ必要）
        duration: 操作時間（ミリ秒）
        retry_count: 失敗時のリトライ回数
        
    Returns:
        操作成功時はTrue、失敗時はFalse
    """
    import time
    from logging_util import logger
    
    for attempt in range(retry_count):
        try:
            if action == "tap":
                # ダブルタップで確実性向上（詳細ログ付き）
                logger.info(f"[ADB-DEBUG] デバイス{device_port}: タップ実行中 座標=({x},{y}) 試行={attempt+1}/{retry_count}")
                
                res1 = run_adb_command(
                    ["shell", "input", "swipe", str(x), str(y), str(x), str(y), str(duration)],
                    device_port
                )
                logger.info(f"[ADB-DEBUG] 1回目タップ結果: {res1 is not None}")
                
                time.sleep(0.1)
                
                res2 = run_adb_command(
                    ["shell", "input", "swipe", str(x), str(y), str(x), str(y), str(duration)],
                    device_port
                )
                logger.info(f"[ADB-DEBUG] 2回目タップ結果: {res2 is not None}")
                
                success = (res1 is not None) and (res2 is not None)
                if success:
                    logger.info(f"[ADB-DEBUG] 強化クリック成功 デバイス={device_port} 座標=({x}, {y}) 試行={attempt+1}")
                    return True
                else:
                    logger.warning(f"[ADB-DEBUG] 強化クリック失敗 デバイス={device_port} res1={res1 is not None} res2={res2 is not None}")
                    
            elif action == "swipe" and x2 is not None and y2 is not None:
                res = run_adb_command(
                    ["shell", "input", "swipe", str(x), str(y), str(x2), str(y2), str(duration)],
                    device_port
                )
                if res is not None:
                    logger.debug(f"[ULTRATHINK] 強化スワイプ成功 ({x},{y}→{x2},{y2}, 試行: {attempt+1})")
                    return True
            else:
                logger.error(f"[ULTRATHINK] 無効なパラメーター ({action})")
                return False
                
            # 失敗時は少し待ってからリトライ
            if attempt < retry_count - 1:
                logger.warning(f"[ADB-DEBUG] 操作失敗、リトライ中... (試行: {attempt+1}/{retry_count})")
                time.sleep(0.5)  # より長い待機時間でNOXの応答を待つ
                
        except Exception as exc:
            logger.error(f"[ULTRATHINK] 強化操作例外 (試行: {attempt+1}): {exc}")
            if attempt < retry_count - 1:
                time.sleep(0.5)
    
    logger.error(f"[ULTRATHINK] 強化操作が{retry_count}回失敗しました ({action} {x},{y})")
    return False


def perform_action(
    device_port: str,
    action: str,
    x: int,
    y: int,
    x2: Optional[int] = None,
    y2: Optional[int] = None,
    duration: int = 150,
) -> bool:
    """デバイス上でタップやスワイプ操作を実行します。
    
    Args:
        device_port: 対象デバイスのポート
        action: "tap" または "swipe"
        x, y: 開始座標
        x2, y2: 終了座標（swipe時のみ必要）
        duration: 操作時間（ミリ秒）
        
    Returns:
        操作成功時はTrue、失敗時はFalse
        
    Example:
        >>> perform_action("127.0.0.1:62001", "tap", 100, 200)
        True
        
        >>> perform_action("127.0.0.1:62001", "swipe", 100, 200, 300, 400)
        True
    """
    try:
        if action == "tap":
            res = run_adb_command(
                ["shell", "input", "swipe", str(x), str(y), str(x), str(y), str(duration)],
                device_port
            )
            return res is not None
        if action == "swipe" and x2 is not None and y2 is not None:
            res = run_adb_command(
                ["shell", "input", "swipe", str(x), str(y), str(x2), str(y2), str(duration)],
                device_port
            )
            return res is not None
        logger.error("perform_action: invalid parameters (%s)", action)
        return False
    except Exception as exc:
        logger.error("perform_action exception: %s", exc)
        return False

def reset_adb_server(force: bool = False) -> bool:
    """ADBサーバーを再起動します。"""
    cfg = get_config()
    if getattr(cfg, "skip_adb_reset", False) and not force:
        logger.info("reset_adb_server: skip_adb_reset=True のためADBリセットを行いません")
        return True
    if not cfg.NOX_ADB_PATH:
        logger.error("NOX_ADB_PATH not set in config.json")
        return False

    with _state.adb_reset_lock:
        now = time.time()
        elapsed = now - _state.last_adb_reset
        if elapsed < max(2.0, _ADB_RESET_BACKOFF if not force else _ADB_RESET_BACKOFF / 2):
            with _state.error_lock:
                recent_error_count = len(_state.recent_adb_errors)
            if not force:
                if recent_error_count < _ADB_RESET_ERROR_THRESHOLD:
                    logger.debug("ADB reset skipped due to throttle (%.2fs since last)", elapsed)
                    return True
                logger.warning(
                    "ADB reset throttle bypassed (%d rapid errors within %.0fs)",
                    recent_error_count,
                    _RECENT_ERROR_WINDOW,
                )
            else:
                logger.debug("ADB reset (forced) skipped due to rapid repeat (%.2fs since last)", elapsed)
                return True

        logger.warning("Restarting ADB server%s", " (forced)" if force else "")
        kill_cmd = [cfg.NOX_ADB_PATH, "kill-server"]
        start_cmd = [cfg.NOX_ADB_PATH, "start-server"]
        for cmd in (kill_cmd, start_cmd):
            _run(cmd, timeout=10)

        for attempt in range(_ADB_RESET_VERIFY_ATTEMPTS):
            wait_seconds = 1.0 + attempt * 0.5
            time.sleep(wait_seconds)
            if check_adb_server():
                _state.last_adb_reset = time.time()
                with _state.error_lock:
                    _state.recent_adb_errors.clear()
                with _state.reconnect_lock:
                    _state.reconnect_failures.clear()
                    _state.reconnect_restart_inflight.clear()
                try:
                    from monst.image.device_management import notify_adb_reset

                    notify_adb_reset(_state.last_adb_reset)
                except Exception:
                    pass
                logger.debug(
                    "ADB server restart confirmed after %.1fs",
                    time.time() - now,
                )
                return True

        _state.last_adb_reset = time.time()
        logger.error("ADB server restart could not be confirmed")
        return False


def is_device_available(device_port: str) -> bool:
    """デバイスが利用可能かチェックします。
    
    Args:
        device_port: チェック対象のデバイスポート
        
    Returns:
        デバイスが利用可能でping応答があればTrue
    """
    try:
        out = run_adb_command(["devices"], None, timeout=3)
        if not out or device_port not in out or "device" not in out:
            return False
        echo = run_adb_command(["shell", "echo", "ping"], device_port, timeout=5)
        return bool(echo and "ping" in echo)
    except Exception as e:
        logger.debug(f"Device availability check failed for {device_port}: {e}")
        return False

def reconnect_device(device_port: str) -> bool:
    """デバイスに再接続を試行します。
    
    Args:
        device_port: 再接続対象のデバイスポート
        
    Returns:
        再接続成功時はTrue
    """
    cfg = get_config()
    last_error = "Unknown error"

    for attempt in range(1, _MAX_RECONNECT_ATTEMPTS + 1):
        _run([cfg.NOX_ADB_PATH, "disconnect", device_port], timeout=5)
        time.sleep(0.5)

        if attempt > 1:
            time.sleep(min(0.5 * attempt, 1.5))

        if not check_adb_server():
            logger.warning(
                "ADB server not responding, restarting before reconnect (attempt %d/%d)",
                attempt,
                _MAX_RECONNECT_ATTEMPTS,
            )
            reset_adb_server(force=True)

        out, err, rc = _run([cfg.NOX_ADB_PATH, "connect", device_port], timeout=10)
        response = (out or err or "").strip()
        normalized = response.lower()

        if rc == 0 and ("connected" in normalized or "already connected" in normalized):
            time.sleep(1)
            if is_device_available(device_port):
                logger.info("Device %s successfully reconnected and verified", device_port)
                _reset_reconnect_state(device_port)
                try:
                    from monst.image.device_management import mark_device_recovered

                    mark_device_recovered(device_port)
                except Exception:
                    pass
                return True

        last_error = response or "Unknown error"

        if attempt < _MAX_RECONNECT_ATTEMPTS:
            logger.warning(
                "Reconnect attempt %d/%d failed for %s: %s",
                attempt,
                _MAX_RECONNECT_ATTEMPTS,
                device_port,
                last_error,
            )
            if attempt >= 2:
                reset_adb_server(force=True)
            time.sleep(min(1.0 * attempt, 3.0))

    logger.error(
        "Failed to reconnect device %s after %d attempts: %s",
        device_port,
        _MAX_RECONNECT_ATTEMPTS,
        last_error,
    )
    failure_count = _register_reconnect_failure(device_port)
    if failure_count >= _RECONNECT_FAILURE_RESTART_THRESHOLD:
        logger.warning(
            "Device %s failed to reconnect %d times; scheduling emulator restart",
            device_port,
            failure_count,
        )
        _schedule_force_restart(device_port, failure_count)
    return False

def check_adb_server() -> bool:
    """ADBサーバーが稼働中かチェックします。
    
    Returns:
        ADBサーバーが正常に動作していればTrue
    """
    _, _, rc = _run([get_config().NOX_ADB_PATH, "devices"], timeout=5)
    return rc == 0
