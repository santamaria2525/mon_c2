# -*- coding: utf-8 -*-
"""
Threaded multi-device orchestration helpers.

This module keeps the legacy APIs while tightening error handling and logging.
"""
from __future__ import annotations

import concurrent.futures
import threading
import time
import sys
from collections import defaultdict, deque
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

from logging_util import logger, MultiDeviceLogger
from adb_utils import (
    close_monster_strike_app,
    run_adb_command,
    start_monster_strike_app,
    is_device_available,
    reconnect_device,
    reset_adb_server,
)
from monst.adb.core import run_adb_command_detailed
from monst.image import force_restart_nox_device
from monst.image.device_management import (
    record_device_progress,
    get_device_idle_time,
    have_devices_been_idle,
    is_auto_restart_paused,
    get_auto_restart_pause_reason,
)
from config import MAX_FOLDER_LIMIT
from utils.device_utils import get_terminal_number
from utils.watchdog import arm_watchdog, disarm_watchdog, touch_watchdog

def _try_stop_task_monitor() -> None:
    """Attempt to stop the external process task monitor if available."""
    try:
        from utils.process_task_monitor import stop_process_task_monitor as _stop
    except Exception:
        return
    try:
        _stop()
    except Exception:
        pass


OperationFunc = Callable[[str, str, MultiDeviceLogger], Any]
CustomArgs = Optional[Mapping[str, Any]]

_DATA_FILENAME = "data10.bin"
_DATA_DESTINATION = "/data/data/jp.co.mixi.monsterstrike/data10.bin"
_APP_SHUTDOWN_DELAY = 0.6
_APP_RESTART_DELAY = 0.3
_MAX_PARALLEL_WORKERS = 3
_START_STAGGER_SECONDS = 1.2
_DEVICE_READY_TIMEOUT = 45.0
_DEVICE_READY_POLL = 3.0
_RETRY_BACKOFF_SECONDS = 12.0
_MAX_REQUEUE_ATTEMPTS = 3
_BIN_PUSH_DIRNAME = "bin_push"
_INFLIGHT_MONITOR_INTERVAL = 30.0
_OPERATION_STALL_TIMEOUT = 300.0
_HARD_INFLIGHT_TIMEOUT = 900.0
_MONITOR_HEARTBEAT_SECONDS = 300.0
_GLOBAL_STALL_TIMEOUT = 600.0
_GLOBAL_RECOVERY_GRACE = 90.0
_STALL_ESCALATION_SECONDS = None
_STATUS_LOG_INTERVAL = 120.0
_SOFT_RESYNC_COOLDOWN = 300.0
_RESUME_KICK_SECONDS = 120.0
_HEALTH_CHECK_INTERVAL = 600.0
_HEALTH_RESTART_COOLDOWN = 300.0
_ADB_RECOVERY_COOLDOWN = 120.0
_LAST_ADB_RECOVERY = 0.0

_restart_lock = threading.Lock()
_active_restarts: Dict[str, threading.Thread] = {}


def _is_port_restarting(port: str) -> bool:
    with _restart_lock:
        thread = _active_restarts.get(port)
        return bool(thread and thread.is_alive())


def _announce_folder_completion(folder_label: str) -> None:
    """Log folder completion to both the logger and the console window."""
    message = f"フォルダ_{folder_label} 作業完了"
    logger.info(message)


def _wait_for_device_ready(port: str) -> bool:
    """Confirm that a device responds to adb within the timeout window."""
    if _is_port_restarting(port):
        return False
    deadline = time.time() + _DEVICE_READY_TIMEOUT
    last_reconnect_attempt = 0.0
    while time.time() < deadline:
        if is_device_available(port):
            return True
        now = time.time()
        if now - last_reconnect_attempt >= 10.0:
            try:
                reconnect_device(port)
            except Exception:
                logger.debug("ADB reconnect failed for %s", port)
            last_reconnect_attempt = now
        time.sleep(_DEVICE_READY_POLL)
        if _is_port_restarting(port):
            return False
    return False


def _schedule_device_restart(device_port: str, reason: str) -> None:
    """Spawn a background restart for the specified NOX port."""
    with _restart_lock:
        existing = _active_restarts.get(device_port)
        if existing and existing.is_alive():
            return

        thread = threading.Thread(
            target=_restart_worker,
            args=(device_port, reason),
            name=f"NoxRestart-{device_port}",
            daemon=True,
        )
        _active_restarts[device_port] = thread
        thread.start()


def _log_restart_request(device_port: str, folder_label: Optional[str], reason: str) -> None:
    terminal = get_terminal_number(device_port)
    if folder_label:
        logger.warning(
            "[RESTART] 端末%s (port=%s) フォルダ_%s 作業中に再起動要求: %s",
            terminal,
            device_port,
            folder_label,
            reason,
        )
    else:
        logger.warning(
            "[RESTART] 端末%s (port=%s) で再起動要求: %s",
            terminal,
            device_port,
            reason,
        )


def _request_device_restart(device_port: str, reason: str, folder_label: Optional[str] = None) -> None:
    """Log restart intent with folder context, then schedule the restart."""
    pause_note = ""
    if is_auto_restart_paused():
        paused_reason = get_auto_restart_pause_reason() or "pause_request"
        pause_note = f" (auto-restart paused: {paused_reason})"
    _log_restart_request(device_port, folder_label, f"{reason}{pause_note}")
    if is_auto_restart_paused():
        logger.info(
            "再起動要求を抑制: port=%s, reason=%s (auto-restart paused)",
            device_port,
            reason,
        )
        return
    _schedule_device_restart(device_port, reason)


def _log_device_summary(ports: Sequence[str], inflight_folders: Mapping[str, int]) -> None:
    """Emit per-device status snapshot for stall diagnosis."""
    for port in ports:
        folder_value = inflight_folders.get(port)
        folder_label = f"{folder_value:03d}" if folder_value is not None else "-"
        idle_time = get_device_idle_time(port)
        restarting = _is_port_restarting(port)
        adb_ready = is_device_available(port)
        terminal = get_terminal_number(port)
        logger.info(
            "[STATUS] 端末%s port=%s folder=%s idle=%ds restarting=%s adb=%s",
            terminal,
            port,
            folder_label,
            int(idle_time),
            restarting,
            adb_ready,
        )


def _log_stall_diagnostics(port: str, folder_label: str) -> bool:
    """Force ADB/screenshot checks for stalled devices and return failure state."""
    terminal = get_terminal_number(port)
    adb_error = False
    screenshot_error = False
    try:
        out, err, rc = run_adb_command_detailed(["get-state"], device_port=port, timeout=10)
        if rc != 0:
            adb_error = True
        logger.info(
            "[STALL] 端末%s フォルダ_%s ADB get-state rc=%s out=%s err=%s",
            terminal,
            folder_label,
            rc,
            (out or "").strip(),
            (err or "").strip(),
        )
    except Exception as exc:
        adb_error = True
        logger.warning("[STALL] 端末%s フォルダ_%s ADB診断失敗: %s", terminal, folder_label, exc)

    try:
        from monst.image.core import get_device_screenshot  # lazy import

        img = get_device_screenshot(port, force_refresh=True)
        if img is None:
            screenshot_error = True
            logger.warning("[STALL] 端末%s フォルダ_%s スクショ取得失敗", terminal, folder_label)
        else:
            logger.info(
                "[STALL] 端末%s フォルダ_%s スクショ取得OK (%sx%s)",
                terminal,
                folder_label,
                img.shape[1],
                img.shape[0],
            )
    except Exception as exc:
        screenshot_error = True
        logger.warning("[STALL] 端末%s フォルダ_%s スクショ診断失敗: %s", terminal, folder_label, exc)

    if adb_error or screenshot_error:
        global _LAST_ADB_RECOVERY
        now = time.time()
        if now - _LAST_ADB_RECOVERY >= _ADB_RECOVERY_COOLDOWN:
            _LAST_ADB_RECOVERY = now
            logger.warning(
                "[RECOVERY] ADB再起動を試行します (原因: %s%s)",
                "adb" if adb_error else "",
                "+screenshot" if screenshot_error else "",
            )
            try:
                reset_adb_server(force=True)
            except Exception as exc:
                logger.debug("ADB reset failed: %s", exc)
        if not _is_port_restarting(port):
            _request_device_restart(
                port,
                f"diagnostic failure ({'adb' if adb_error else ''}{'+screenshot' if screenshot_error else ''})",
                folder_label,
            )
        return True
    return False


def _soft_resync_all(ports: Sequence[str]) -> None:
    """Lightweight resync without NOX restart."""
    logger.warning("[RECOVERY] 全端末が停止状態のため軽い再同期を実施します")
    for port in ports:
        try:
            if not is_device_available(port):
                reconnect_device(port)
        except Exception as exc:
            logger.debug("soft resync reconnect failed for %s: %s", port, exc)
        record_device_progress(port)


def _restart_worker(device_port: str, reason: str) -> None:
    terminal = get_terminal_number(device_port)
    try:
        logger.warning("%s: NOX再起動を開始 (%s)", terminal, reason)
        success = force_restart_nox_device(device_port, emergency=True)
        if success:
            logger.info("%s: NOX再起動完了 (%s)", terminal, reason)
        else:
            logger.error("%s: NOX再起動に失敗 (%s)", terminal, reason)
    except Exception as exc:  # pragma: no cover - best effort
        logger.exception("%s: NOX再起動処理で例外 (%s)", terminal, reason)
        logger.debug("Restart exception details: %s", exc)
    finally:
        with _restart_lock:
            _active_restarts.pop(device_port, None)


def _watchdog_timeout_for_ports(port_count: int) -> float:
    """Scale watchdog timeout with the number of concurrent devices."""
    return max(900.0, min(5400.0, port_count * 300.0))


@contextmanager
def _watchdog_context(operation_name: str, ports: Sequence[str]):
    """Arm the watchdog for long-running multi-device operations."""
    active_ports = [port for port in ports if port]
    if not active_ports:
        yield
        return
    timeout = _watchdog_timeout_for_ports(len(active_ports))
    arm_watchdog(timeout=timeout, label=f"{operation_name}:start")
    touch_watchdog(f"{operation_name}:start")
    try:
        yield
    finally:
        disarm_watchdog()


def _snapshot_custom_args(custom_args: CustomArgs) -> Dict[str, Any]:
    """Return a shallow copy so each worker can mutate safely."""
    return dict(custom_args or {})


def _missing_data_message(base_folder_int: int) -> str:
    return f"フォルダ_{base_folder_int:03d}-{MAX_FOLDER_LIMIT:03d} に {_DATA_FILENAME} が見つかりません"


def _abort_due_to_missing_data(at_folder: int) -> None:
    """Log and terminate the application when BIN data is unavailable."""
    logger.error(_missing_data_message(at_folder))
    try:
        _try_stop_task_monitor()
    except Exception:
        pass
    sys.exit(0)


def _resolve_bin_push_root() -> Optional[Path]:
    """Locate the bin_push directory using utils.get_resource_path when available."""
    try:
        from utils import get_resource_path  # type: ignore import-error
    except Exception:
        get_resource_path = None  # type: ignore[assignment]

    candidate: Optional[str] = None
    if get_resource_path:
        try:
            candidate = get_resource_path(_BIN_PUSH_DIRNAME)
        except Exception as exc:
            logger.debug(f"bin_push パスの取得に失敗: {exc}")
            candidate = None

    path = Path(candidate) if candidate else Path(_BIN_PUSH_DIRNAME)
    if not path.exists():
        logger.error("bin_push フォルダが見つかりません")
        return None
    return path


def _collect_data_folders(bin_root: Path, start: int, stop_after: Optional[int] = None) -> List[int]:
    """Return folder numbers that contain data10.bin in ascending order."""
    results: List[int] = []
    start_index = max(start, 0)
    for folder_int in range(start_index, MAX_FOLDER_LIMIT + 1):
        data_path = bin_root / f"{folder_int:03d}" / _DATA_FILENAME
        if data_path.exists():
            results.append(folder_int)
            if stop_after is not None and len(results) >= stop_after:
                break
    return results


def _request_nox_restart(port: str) -> bool:
    """Attempt to restart a problematic NOX instance."""
    try:
        logger.warning("Requesting NOX restart (port=%s)", port)
        restarted = force_restart_nox_device(port, emergency=True)
        if restarted:
            logger.info("NOX restart accepted (port=%s)", port)
        else:
            logger.error("NOX restart failed (port=%s)", port)
        return restarted
    except Exception as exc:
        logger.exception("NOX restart request raised an exception (port=%s): %s", port, exc)
        return False


def _format_adb_failure(stdout: Optional[str], stderr: Optional[str], rc: int) -> str:
    parts = []
    if stdout:
        cleaned = stdout.strip()
        if cleaned:
            parts.append(cleaned)
    if stderr:
        cleaned = stderr.strip()
        if cleaned:
            parts.append(cleaned)
    if not parts:
        parts.append("no adb output")
    detail = " | ".join(parts)
    return f"rc={rc} detail={detail[:300]}"


def _perform_push(port: str, data_path: Path) -> Tuple[bool, Optional[str]]:
    """Execute the push sequence once."""
    time.sleep(_APP_SHUTDOWN_DELAY)
    close_monster_strike_app(port)
    time.sleep(_APP_RESTART_DELAY)
    stdout, stderr, rc = run_adb_command_detailed(
        ["push", str(data_path), _DATA_DESTINATION],
        device_port=port,
    )
    if rc != 0:
        return False, _format_adb_failure(stdout, stderr, rc)
    time.sleep(_APP_RESTART_DELAY)
    start_monster_strike_app(port)
    return True, None


def _push_data_file(port: str, folder_name: str, bin_root: Path) -> bool:
    """Push data10.bin to the specified device and restart the app."""
    data_path = bin_root / folder_name / _DATA_FILENAME
    if not data_path.exists():
        logger.error(f"push failed {folder_name}: {_DATA_FILENAME} not found")
        return False

    try:
        success, failure_detail = _perform_push(port, data_path)
        if success:
            return True
        reason = failure_detail or "unknown error"
        logger.error("push failed %s (port=%s): %s", folder_name, port, reason)
    except Exception:
        logger.exception("push worker exception (port=%s folder=%s)", port, folder_name)
        return False

    if not _request_nox_restart(port):
        return False

    time.sleep(10)
    try:
        success, failure_detail = _perform_push(port, data_path)
        if success:
            logger.info("push retry succeeded (port=%s folder=%s)", port, folder_name)
            return True
        reason = failure_detail or "unknown error"
        logger.error("push retry failed (port=%s folder=%s): %s", port, folder_name, reason)
    except Exception:
        logger.exception("push retry raised an exception (port=%s folder=%s)", port, folder_name)

    return False


def run_push(base_folder_int: int, device_ports: List[str]) -> Tuple[Optional[int], List[str]]:
    """Push data10.bin to each requested device and restart the app."""
    bin_root = _resolve_bin_push_root()
    if bin_root is None:
        return base_folder_int, []

    ports = [port for port in device_ports if port]
    if not ports:
        logger.info("run_push: no target devices")
        return base_folder_int, []

    with _watchdog_context(f"push:{base_folder_int:03d}", ports):
        candidates = _collect_data_folders(bin_root, base_folder_int, stop_after=len(ports))
        if not candidates:
            logger.error(_missing_data_message(base_folder_int))
            return base_folder_int, []

        assignments = [(port, f"{folder:03d}") for port, folder in zip(ports, candidates)]
        results: List[Optional[str]] = [None] * len(assignments)

        def worker(port: str, folder_name: str) -> Optional[str]:
            touch_watchdog(f"push:{folder_name}:start")
            try:
                return folder_name if _push_data_file(port, folder_name, bin_root) else None
            finally:
                touch_watchdog(f"push:{folder_name}:finish")

        with concurrent.futures.ThreadPoolExecutor(max_workers=len(assignments)) as executor:
            future_map = {
                executor.submit(worker, port, folder_name): index
                for index, (port, folder_name) in enumerate(assignments)
            }
            for future in concurrent.futures.as_completed(future_map):
                index = future_map[future]
                try:
                    results[index] = future.result()
                except Exception:
                    logger.exception("run_push worker error")
                    results[index] = None

        used = [folder_name for folder_name in results if folder_name]
        next_base = base_folder_int + len(used)
        touch_watchdog(f"push:next_base:{next_base:03d}")
        return next_base, used


    results: List[Optional[str]] = [None] * len(assignments)

    def worker(port: str, folder_name: str) -> Optional[str]:
        return folder_name if _push_data_file(port, folder_name, bin_root) else None

def _execute_operation_batch(
    ports: Sequence[str],
    folders: Sequence[str],
    operation: OperationFunc,
    operation_name: str,
    custom_args: CustomArgs = None,
) -> int:
    """Execute an operation across devices in parallel and return success count."""
    if not ports or not folders:
        return 0

    multi_logger = MultiDeviceLogger(list(ports), list(folders))
    base_kwargs = _snapshot_custom_args(custom_args)
    success_count = 0
    assignments = list(enumerate(zip(ports, folders)))
    for port in ports:
        record_device_progress(port)

    def worker(order: int, port: str, folder: str) -> bool:
        delay = min(order * _START_STAGGER_SECONDS, 5.0)
        if delay:
            time.sleep(delay)

        touch_watchdog(f"{operation_name}:start:{folder}")
        record_device_progress(port)

        restarting = _is_port_restarting(port)
        if not _wait_for_device_ready(port):
            message = f"フォルダ_{folder}: {operation_name}準備待ちタイムアウト"
            multi_logger.log_error(port, message)
            logger.warning(f"[WAIT] {message}")
            if not restarting:
                _request_device_restart(port, f"{operation_name} wait timeout ({folder})", folder)
            touch_watchdog(f"{operation_name}:wait_failed:{folder}")
            return False

        heartbeat_label = f"{operation_name}:heartbeat:{port}:{folder}"
        heartbeat_stop = threading.Event()

        def _heartbeat() -> None:
            while not heartbeat_stop.wait(60.0):
                touch_watchdog(heartbeat_label)
                record_device_progress(port)

        heartbeat_thread = threading.Thread(target=_heartbeat, name=f"HB-{port}-{folder}", daemon=True)
        heartbeat_thread.start()

        try:
            result = operation(port, folder, multi_logger, **base_kwargs)
            if result:
                multi_logger.log_success(port)
                _announce_folder_completion(folder)
                record_device_progress(port)
                touch_watchdog(f"{operation_name}:success:{folder}")
                return True
            message = f"フォルダ_{folder}: {operation_name}失敗"
            multi_logger.log_error(port, message)
            logger.warning(f"[NG] {message}")
            _request_device_restart(port, f"{operation_name} returned False ({folder})", folder)
            touch_watchdog(f"{operation_name}:failed:{folder}")
            return False
        except Exception as exc:
            message = f"フォルダ_{folder}: {operation_name}失敗 ({exc})"
            multi_logger.log_error(port, message)
            logger.exception(f"[NG] フォルダ_{folder}: {operation_name}失敗", exc_info=True)
            _request_device_restart(port, f"{operation_name} exception ({folder})", folder)
            touch_watchdog(f"{operation_name}:exception:{folder}")
            return False
        finally:
            heartbeat_stop.set()
            heartbeat_thread.join(timeout=1.0)

    max_workers = min(len(assignments), _MAX_PARALLEL_WORKERS)
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_map = {
            executor.submit(worker, order, port, folder): (port, folder)
            for order, (port, folder) in assignments
        }
        for future in concurrent.futures.as_completed(future_map):
            try:
                if future.result():
                    success_count += 1
            except Exception:
                logger.exception("operation worker エラー")

    return success_count


def run_loop(
    base_folder_int: int,
    operation: OperationFunc,
    ports: List[str],
    operation_name: str,
    additional_operation: Optional[Callable[[int], Any]] = None,
    save_data_files: bool = False,
    custom_thread_function: Optional[Callable[..., Any]] = None,
    custom_thread_args: Optional[List[Tuple[Any, ...]]] = None,
    custom_args: CustomArgs = None,
) -> Tuple[Optional[int], bool]:
    """Run the classic fixed assignment loop (legacy behaviour)."""
    if not ports:
        logger.warning("run_loop: 対象デバイスがありません")
        return base_folder_int, False
    if base_folder_int > MAX_FOLDER_LIMIT:
        logger.warning(f"run_loop: ベースフォルダ {base_folder_int:03d} が上限を超えています")
        return base_folder_int, True

    with _watchdog_context(operation_name, ports):
        folders = _assign_folders(base_folder_int, ports)
        touch_watchdog(f"{operation_name}:assign:{base_folder_int:03d}")
        _execute_operation_batch(ports, folders, operation, operation_name, custom_args)
        next_base = base_folder_int + len(folders)

        if additional_operation:
            try:
                additional_operation(next_base)
            except Exception:
                logger.exception("additional_operation実行エラー")

        touch_watchdog(f"{operation_name}:next:{next_base:03d}")
        return next_base, False

def run_loop_enhanced(
    base_folder_int: int,
    operation: OperationFunc,
    ports: List[str],
    operation_name: str,
    additional_operation: Optional[Callable[[int], Any]] = None,
    save_data_files: bool = False,
    custom_thread_function: Optional[Callable[..., Any]] = None,
    custom_thread_args: Optional[List[Tuple[Any, ...]]] = None,
    custom_args: CustomArgs = None,
    use_independent_processing: bool = True,
) -> Tuple[Optional[int], bool]:
    """Run operations so that each device picks the next available folder immediately."""
    if not ports:
        logger.warning("run_loop_enhanced: ????????????")
        return base_folder_int, False
    if base_folder_int > MAX_FOLDER_LIMIT:
        logger.warning(f"run_loop_enhanced: ??????? {base_folder_int:03d} ??????????")
        return base_folder_int, True

    try:
        logger.info(f"????????? ???? {base_folder_int:03d} ??")
    except Exception:
        pass

    with _watchdog_context(operation_name, ports):
        _ = use_independent_processing  # Retained for API compatibility.

        bin_root = _resolve_bin_push_root()

        if bin_root is None:
            return None, True

        available_folders = _collect_data_folders(bin_root, base_folder_int)
        if not available_folders:
            logger.error(_missing_data_message(base_folder_int))
            return None, True

        assignment_lock = threading.Lock()
        assignment_cv = threading.Condition(assignment_lock)
        folder_queue = deque(available_folders)
        inflight_folders: Dict[str, int] = {}
        inflight_start_times: Dict[str, float] = {}
        folder_reservations: Dict[int, str] = {}
        unlimited_completion_watch = False
        try:
            from config import get_config
            cfg = get_config()
            unlimited_completion_watch = bool(cfg.get("on_gacha"))
        except Exception:
            pass
        last_completion_time = time.time()
        global_recovery_until = 0.0
        processed_lock = threading.Lock()
        processed_success: List[int] = []
        folder_retry_counts: Dict[int, int] = defaultdict(int)
        skipped_folders: List[int] = []
        port_backoff_until: Dict[str, float] = defaultdict(float)
        consecutive_full_stall_cycles = 0
        stall_alarm_deadlines: Dict[str, float] = {}
        stall_counts: Dict[str, int] = defaultdict(int)
        idle_counts: Dict[str, int] = defaultdict(int)
        last_status_log_time = 0.0
        last_soft_resync_time = 0.0
        last_resume_kick_time = 0.0
        last_health_check_time = 0.0
        health_restart_cooldown: Dict[str, float] = defaultdict(float)
        base_kwargs = _snapshot_custom_args(custom_args)

        multi_logger = MultiDeviceLogger(ports)

        def fetch_next_folder(port: str) -> Optional[int]:
            nonlocal global_recovery_until
            with assignment_cv:
                while True:
                    if global_recovery_until:
                        delay = global_recovery_until - time.time()
                        if delay > 0:
                            assignment_cv.wait(timeout=min(delay, 1.0))
                            continue
                        else:
                            global_recovery_until = 0.0
                    backoff_until = port_backoff_until.get(port, 0.0)
                    remaining = backoff_until - time.time()
                    if remaining > 0:
                        assignment_cv.wait(timeout=min(remaining, 1.0))
                        continue
                    port_backoff_until.pop(port, None)

                    if folder_queue:
                        attempts = len(folder_queue)
                        while attempts > 0:
                            folder_value = folder_queue.popleft()
                            reserved_for = folder_reservations.get(folder_value)
                            if reserved_for and reserved_for != port:
                                folder_queue.append(folder_value)
                                attempts -= 1
                                continue
                            inflight_folders[port] = folder_value
                            inflight_start_times[port] = time.time()
                            folder_reservations[folder_value] = port
                            return folder_value
                        assignment_cv.wait(timeout=1.0)
                        continue
                    if not inflight_folders:
                        return None
                    assignment_cv.wait(timeout=1.0)

        def _mark_folder_complete(port: str, folder_value: int, *, success: bool) -> None:
            with assignment_cv:
                inflight_folders.pop(port, None)
                inflight_start_times.pop(port, None)
                owner = folder_reservations.get(folder_value)
                if owner == port:
                    folder_reservations.pop(folder_value, None)
                if success:
                    folder_retry_counts.pop(folder_value, None)
                assignment_cv.notify_all()

        def _requeue_folder(port: str, folder_value: int, reason: str, *, keep_reservation: bool = False) -> bool:
            with assignment_cv:
                attempts = folder_retry_counts.get(folder_value, 0) + 1
                folder_retry_counts[folder_value] = attempts
                inflight_folders.pop(port, None)
                inflight_start_times.pop(port, None)
                if not keep_reservation:
                    owner = folder_reservations.get(folder_value)
                    if owner == port:
                        folder_reservations.pop(folder_value, None)
                if attempts > _MAX_REQUEUE_ATTEMPTS:
                    skipped_folders.append(folder_value)
                    assignment_cv.notify_all()
                    return False
                folder_queue.appendleft(folder_value)
                assignment_cv.notify_all()
            logger.debug(
                "%s: requeue (%s) attempt #%d",
                f"フォルダ_{folder_value:03d}",
                reason,
                attempts,
            )
            return True

        def _requeue_without_penalty(port: str, folder_value: int) -> None:
            _requeue_folder(port, folder_value, "global_requeue", keep_reservation=False)

        def _all_ports_ready() -> bool:
            for port in ports:
                if _is_port_restarting(port):
                    return False
                if not is_device_available(port):
                    return False
            return True

        def _begin_global_recovery(reason: str) -> None:
            nonlocal global_recovery_until, last_completion_time, consecutive_full_stall_cycles
            with assignment_cv:
                for port, folder_value in list(inflight_folders.items()):
                    _requeue_without_penalty(port, folder_value)
                global_recovery_until = 0.0
                consecutive_full_stall_cycles = 0
                stall_alarm_deadlines.clear()
            last_completion_time = time.time()
            logger.warning(
                "[IDLE] %s: 全端末で長時間進行がありません (理由: %s)",
                operation_name,
                reason,
            )
            if have_devices_been_idle(ports, _GLOBAL_STALL_TIMEOUT or 600.0):
                if _all_ports_ready():
                    logger.info("[IDLE] 全端末の起動状態を確認済み。ループを継続します。")
                else:
                    logger.warning("[IDLE] 一部端末が復旧待ちのため個別再起動を待機します。")
        def _assignment_active(port: str, folder_value: int) -> bool:
            with assignment_cv:
                return inflight_folders.get(port) == folder_value

        def worker(port: str) -> None:
            nonlocal last_completion_time

            while True:
                folder_value = fetch_next_folder(port)
                if folder_value is None:
                    with assignment_cv:
                        has_reservation = any(owner == port for owner in folder_reservations.values())
                        if has_reservation or folder_queue:
                            assignment_cv.wait(timeout=1.0)
                            continue
                    return

                folder_name = f"{folder_value:03d}"
                touch_watchdog(f"{operation_name}:assign:{folder_name}")
                record_device_progress(port)
                multi_logger.update_task_status(port, folder_name, f"{operation_name}準備中")

                def _requeue_and_request_new_assignment(reason: str, *, keep_reservation: bool = False) -> bool:
                    touch_watchdog(f"{operation_name}:requeue:{folder_name}")
                    should_retry_elsewhere = _requeue_folder(
                        port, folder_value, reason, keep_reservation=keep_reservation
                    )
                    if should_retry_elsewhere:
                        port_backoff_until[port] = time.time() + _RETRY_BACKOFF_SECONDS
                        return True
                    multi_logger.log_error(port, f"{operation_name}失敗({folder_name})")
                    logger.error(f"[NG] フォルダ_{folder_name}: {operation_name}断念 ({reason})")
                    _mark_folder_complete(port, folder_value, success=False)
                    touch_watchdog(f"{operation_name}:skip:{folder_name}")
                    return False

                request_new_assignment = False

                while True:
                    if not _assignment_active(port, folder_value):
                        logger.info(
                            "[INFO] フォルダ_%s: 割当てが解除されたため再取得します",
                            folder_name,
                        )
                        request_new_assignment = True
                        break

                    ready = _wait_for_device_ready(port)
                    if not ready:
                        if _is_port_restarting(port):
                            logger.info(
                                f"[WAIT] フォルダ_{folder_name}: NOX再起動完了を待機中 (port={port})"
                            )
                            time.sleep(_DEVICE_READY_POLL)
                            continue

                        logger.warning(f"[WAIT] フォルダ_{folder_name}: {operation_name}で端末待機中")
                        _request_device_restart(port, f"{operation_name} wait timeout ({folder_name})", folder_name)
                        touch_watchdog(f"{operation_name}:wait_retry:{folder_name}")
                        request_new_assignment = True
                        _requeue_and_request_new_assignment("device_not_ready", keep_reservation=True)
                        break

                    if not _assignment_active(port, folder_value):
                        logger.info(
                            "[INFO] フォルダ_%s: 再割当て済みのため処理を中断します",
                            folder_name,
                        )
                        request_new_assignment = True
                        break

                    if not _push_data_file(port, folder_name, bin_root):
                        multi_logger.log_error(port, f"push失敗({folder_name})")
                        logger.error(f"[NG] フォルダ_{folder_name}: push失敗")
                        _request_device_restart(port, f"{operation_name} push failed ({folder_name})", folder_name)
                        touch_watchdog(f"{operation_name}:push_failed:{folder_name}")
                        request_new_assignment = True
                        _requeue_and_request_new_assignment("push_failed")
                        break

                    touch_watchdog(f"{operation_name}:push_ok:{folder_name}")
                    multi_logger.update_task_status(port, folder_name, f"{operation_name}実行中")

                    if not _assignment_active(port, folder_value):
                        logger.info(
                            "[INFO] フォルダ_%s: 再割当て済みのため処理を中断します",
                            folder_name,
                        )
                        request_new_assignment = True
                        break

                    try:
                        operation(port, folder_name, multi_logger, **base_kwargs)
                        error_message = multi_logger.get_error(port)
                        if error_message:
                            logger.warning(f"[NG] フォルダ_{folder_name}: {error_message}")
                            multi_logger.update_task_status(port, folder_name, "エラー終了")
                            _mark_folder_complete(port, folder_value, success=False)
                            touch_watchdog(f"{operation_name}:error:{folder_name}")
                            request_new_assignment = True
                            break
                        multi_logger.log_success(port)
                        _announce_folder_completion(folder_name)
                        record_device_progress(port)
                        last_completion_time = time.time()
                        with processed_lock:
                            processed_success.append(folder_value)
                        touch_watchdog(f"{operation_name}:success:{folder_name}")
                        multi_logger.update_task_status(port, folder_name, f"{operation_name}完了")
                        _mark_folder_complete(port, folder_value, success=True)
                        request_new_assignment = True
                        if additional_operation:
                            try:
                                additional_operation(folder_value + 1)
                            except Exception:
                                logger.exception("additional_operation実行エラー")
                        break
                    except Exception as exc:
                        multi_logger.log_error(port, str(exc))
                        logger.error(f"[NG] フォルダ_{folder_name}: {operation_name}失敗 ({exc})")
                        _request_device_restart(port, f"{operation_name} exception ({folder_name})", folder_name)
                        touch_watchdog(f"{operation_name}:exception:{folder_name}")
                        request_new_assignment = True
                        _requeue_and_request_new_assignment("operation_exception")
                        break

                if request_new_assignment:
                    continue

        stop_inflight_monitor = threading.Event()

        def _monitor_inflight() -> None:
            nonlocal consecutive_full_stall_cycles
            nonlocal global_recovery_until
            nonlocal last_status_log_time
            nonlocal last_soft_resync_time
            nonlocal last_resume_kick_time
            nonlocal last_health_check_time
            heartbeat_last_log = 0.0
            while not stop_inflight_monitor.wait(_INFLIGHT_MONITOR_INTERVAL):
                try:
                    stalled: List[Tuple[str, int]] = []
                    now = time.time()
                    with assignment_cv:
                        inflight_snapshot = dict(inflight_folders)
                        for port, folder_value in list(inflight_folders.items()):
                            if _is_port_restarting(port):
                                inflight_start_times[port] = now
                                continue
                            idle_time = get_device_idle_time(port)
                            if idle_time >= _OPERATION_STALL_TIMEOUT:
                                stalled.append((port, folder_value))
                                inflight_start_times[port] = now
                            start_time = inflight_start_times.get(port)
                            if start_time and now - start_time >= _HARD_INFLIGHT_TIMEOUT:
                                logger.warning(
                                    "[HARD] 端末%s フォルダ_%03d: %ds超過のため強制再割当",
                                    get_terminal_number(port),
                                    folder_value,
                                    int(now - start_time),
                                )
                                _request_device_restart(port, f"{operation_name} hard timeout", f"{folder_value:03d}")
                                _requeue_folder(port, folder_value, "hard_timeout", keep_reservation=True)
                                inflight_start_times[port] = now
                                continue
                        stalled_ports = [port for port, _ in stalled]
                        all_inflight_stalled = bool(stalled_ports) and len(stalled_ports) == len(ports)
                        if _STALL_ESCALATION_SECONDS:
                            active_ports = list(inflight_snapshot.keys())
                            for port in active_ports:
                                if port not in stalled_ports:
                                    stall_alarm_deadlines.pop(port, None)
                            for port in stalled_ports:
                                stall_alarm_deadlines.setdefault(port, now + _STALL_ESCALATION_SECONDS)
                        else:
                            stall_alarm_deadlines.clear()

                        if all_inflight_stalled:
                            consecutive_full_stall_cycles += 1
                        else:
                            consecutive_full_stall_cycles = 0
                    if now - last_status_log_time >= _STATUS_LOG_INTERVAL:
                        _log_device_summary(ports, inflight_snapshot)
                        last_status_log_time = now
                    if now - heartbeat_last_log >= _MONITOR_HEARTBEAT_SECONDS:
                        logger.info(
                            "[MONITOR] inflight=%d queue=%d stalled=%d",
                            len(inflight_snapshot),
                            len(folder_queue),
                            len(stalled),
                        )
                        heartbeat_last_log = now
                    for port in ports:
                        if _is_port_restarting(port):
                            idle_counts.pop(port, None)
                            continue
                        if port in stalled_ports:
                            idle_counts.pop(port, None)
                            continue
                        idle_time = get_device_idle_time(port)
                        if idle_time < _OPERATION_STALL_TIMEOUT:
                            idle_counts.pop(port, None)
                            continue
                        folder_value = inflight_snapshot.get(port)
                        folder_label = f"{folder_value:03d}" if folder_value is not None else "-"
                        idle_counts[port] = idle_counts.get(port, 0) + 1
                        if idle_counts[port] == 1:
                            logger.info("[STALL] \u7aef\u672b%s \u30d5\u30a9\u30eb\u30c0_%s: 600\u79d2\u64cd\u4f5c\u306a\u3057(\u672a\u5272\u5f53)\u3092\u691c\u77e5 (\u518d\u8d77\u52d5\u306f\u4fdd\u7559)",
                                get_terminal_number(port),
                                folder_label,
                            )
                            if _log_stall_diagnostics(port, folder_label) and folder_value is not None:
                                _requeue_folder(port, folder_value, "stall_diagnostic", keep_reservation=True)
                            continue
                        logger.warning("[STALL] \u7aef\u672b%s \u30d5\u30a9\u30eb\u30c0_%s: 600\u79d2\u64cd\u4f5c\u306a\u3057(\u672a\u5272\u5f53)\u306e\u305f\u3081\u7aef\u672b\u518d\u8d77\u52d5\u3092\u5b9f\u884c\u3057\u307e\u3059",
                            get_terminal_number(port),
                            folder_label,
                        )
                        _request_device_restart(port, f"{operation_name} idle ({folder_label})", folder_label)
                        idle_counts.pop(port, None)
                    for port in list(stall_counts.keys()):
                        if port not in stalled_ports:
                            stall_counts.pop(port, None)

                    for port, folder_value in stalled:
                        folder_name = f"{folder_value:03d}"
                        strikes = stall_counts[port] = stall_counts.get(port, 0) + 1
                        if strikes == 1:
                            logger.info(
                                "[STALL] ??%s ????_%s: 600??????? (??????)",
                                get_terminal_number(port),
                                folder_name,
                            )
                            if _log_stall_diagnostics(port, folder_name) and folder_value is not None:
                                _requeue_folder(port, folder_value, "stall_diagnostic", keep_reservation=True)
                                stall_counts.pop(port, None)
                                continue
                            continue
                        logger.warning(
                            "[STALL] ????_%s: %s ????????????????????",
                            folder_name,
                            int(_OPERATION_STALL_TIMEOUT),
                        )
                        _request_device_restart(port, f"{operation_name} stalled ({folder_name})", folder_name)
                        stall_counts.pop(port, None)
                        touch_watchdog(f"{operation_name}:stall:{folder_name}")
                        _requeue_folder(port, folder_value, "stall_requeue", keep_reservation=True)
                    if consecutive_full_stall_cycles >= 2:
                        _begin_global_recovery("???STALL????")
                    if _STALL_ESCALATION_SECONDS:
                        expired_ports = [port for port, deadline in stall_alarm_deadlines.items() if now >= deadline]
                        for port in expired_ports:
                            stall_alarm_deadlines.pop(port, None)
                            folder_value = inflight_folders.get(port)
                            if folder_value is not None:
                                logger.warning(
                                    "[STALL] ???%s??????????????????????????",
                                    port,
                                )
                                _request_device_restart(port, f"{operation_name} stall timeout", f"{folder_value:03d}" if folder_value is not None else None)
                                touch_watchdog(f"{operation_name}:stall_escalation:{folder_value:03d}")
                                stall_counts.pop(port, None)
                                _requeue_folder(port, folder_value, "stall_escalation", keep_reservation=True)
                    if (
                        not unlimited_completion_watch
                        and _GLOBAL_STALL_TIMEOUT
                        and now - last_completion_time >= _GLOBAL_STALL_TIMEOUT
                    ):
                        _begin_global_recovery("10??????")
                    if (
                        _GLOBAL_STALL_TIMEOUT
                        and have_devices_been_idle(ports, _GLOBAL_STALL_TIMEOUT)
                        and _all_ports_ready()
                        and now - last_soft_resync_time >= _SOFT_RESYNC_COOLDOWN
                    ):
                        _soft_resync_all(ports)
                        last_soft_resync_time = now
                    if now - last_health_check_time >= _HEALTH_CHECK_INTERVAL:
                        last_health_check_time = now
                        inflight_snapshot = dict(inflight_folders)
                        unready_ports = []
                        for port in ports:
                            if _is_port_restarting(port):
                                unready_ports.append(port)
                                continue
                            if not is_device_available(port):
                                unready_ports.append(port)
                        if not unready_ports:
                            logger.info(
                                "[HEALTH] 全端末の正常起動を確認。ループを再開します"
                            )
                            with assignment_cv:
                                assignment_cv.notify_all()
                        else:
                            logger.warning(
                                "[HEALTH] 未起動/未応答端末=%s。必要端末のみ再起動を試行します",
                                ",".join(unready_ports),
                            )
                            for port in unready_ports:
                                if now - health_restart_cooldown.get(port, 0.0) < _HEALTH_RESTART_COOLDOWN:
                                    continue
                                health_restart_cooldown[port] = now
                                folder_value = inflight_snapshot.get(port)
                                folder_label = f"{folder_value:03d}" if folder_value is not None else None
                                _request_device_restart(
                                    port,
                                    "health_check",
                                    folder_label,
                                )
                            with assignment_cv:
                                assignment_cv.notify_all()
                    if (
                        now - last_completion_time >= _RESUME_KICK_SECONDS
                        and _all_ports_ready()
                        and now - last_resume_kick_time >= _RESUME_KICK_SECONDS
                    ):
                        with assignment_cv:
                            if inflight_folders or folder_queue:
                                logger.warning(
                                    "[RESUME] all ports ready but no progress; waking workers"
                                )
                                assignment_cv.notify_all()
                                last_resume_kick_time = now
                    if global_recovery_until:
                        remaining = global_recovery_until - now
                        if remaining > 0 and _all_ports_ready():
                            logger.info("[RECOVERY] ????????????????????")
                            global_recovery_until = 0.0
                            with assignment_cv:
                                assignment_cv.notify_all()
                except Exception as exc:
                    logger.exception("InflightMonitor error: %s", exc)

        monitor_thread = threading.Thread(
            target=_monitor_inflight, name="InflightMonitor", daemon=True
        )
        monitor_thread.start()

        with concurrent.futures.ThreadPoolExecutor(max_workers=len(ports)) as executor:
            futures = [executor.submit(worker, port) for port in ports]
            for future in concurrent.futures.as_completed(futures):
                try:
                    future.result()
                except Exception:
                    logger.exception("run_loop_enhanced worker???????")

        stop_inflight_monitor.set()
        monitor_thread.join(timeout=_INFLIGHT_MONITOR_INTERVAL)

        processed_success.sort()
        if processed_success:
            first = processed_success[0]
            last = processed_success[-1]
            if first == last:
                range_label = f"{first:03d}"
            else:
                range_label = f"{first:03d}-{last:03d}"
            logger.info(
                "%s: フォルダ範囲 %s の作業が完了 (%d台)",
                operation_name,
                range_label,
                len(processed_success),
            )
        else:
            logger.warning("%s: 作業完了フォルダなし", operation_name)

        if skipped_folders:
            skipped_folders.sort()
            first_skip = skipped_folders[0]
            last_skip = skipped_folders[-1]
            if first_skip == last_skip:
                logger.error(
                    f"{operation_name}: ????????????????_{first_skip:03d}?????"
                )
            else:
                logger.error(
                    f"{operation_name}: ????????? {len(skipped_folders)}?"
                    f"({first_skip:03d}-{last_skip:03d})"
                )

        next_base = available_folders[-1] + 1
        has_more_folders = bool(_collect_data_folders(bin_root, next_base, stop_after=1))
        should_stop = not has_more_folders
        touch_watchdog(f"{operation_name}:next:{next_base:03d}")
        return next_base, should_stop

def remove_all_nox(device_ports: List[str]) -> None:
    """Placeholder for compatibility with legacy scripts."""
    logger.info(f"remove_all_nox: 対象ポート {len(device_ports)} 台")


def run_in_threads(function: Callable[..., Any], args_list: List[Tuple[Any, ...]]) -> None:
    """Execute function in parallel threads for each argument tuple."""
    if not args_list:
        return

    with concurrent.futures.ThreadPoolExecutor(max_workers=len(args_list)) as executor:
        futures = [executor.submit(function, *args) for args in args_list]
        for future in concurrent.futures.as_completed(futures):
            future.result()
