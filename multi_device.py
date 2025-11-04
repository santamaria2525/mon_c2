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
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

from logging_util import logger, MultiDeviceLogger
from adb_utils import close_monster_strike_app, run_adb_command, start_monster_strike_app
from monst.image import force_restart_nox_device
from config import MAX_FOLDER_LIMIT

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
_BIN_PUSH_DIRNAME = "bin_push"


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


def _perform_push(port: str, data_path: Path) -> bool:
    """Execute the push sequence once."""
    time.sleep(_APP_SHUTDOWN_DELAY)
    close_monster_strike_app(port)
    time.sleep(_APP_RESTART_DELAY)
    result = run_adb_command(["push", str(data_path), _DATA_DESTINATION], port)
    if result is None:
        return False
    time.sleep(_APP_RESTART_DELAY)
    start_monster_strike_app(port)
    return True


def _push_data_file(port: str, folder_name: str, bin_root: Path) -> bool:
    """Push data10.bin to the specified device and restart the app."""
    data_path = bin_root / folder_name / _DATA_FILENAME
    if not data_path.exists():
        logger.error(f"push failed {folder_name}: {_DATA_FILENAME} not found")
        return False

    try:
        if _perform_push(port, data_path):
            return True
        logger.error(f"push failed {folder_name}")
    except Exception:
        logger.exception("push worker exception (port=%s folder=%s)", port, folder_name)

    if not _request_nox_restart(port):
        return False

    time.sleep(10)
    try:
        if _perform_push(port, data_path):
            logger.info("push retry succeeded (port=%s folder=%s)", port, folder_name)
            return True
        logger.error("push retry failed (port=%s folder=%s)", port, folder_name)
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

    candidates = _collect_data_folders(bin_root, base_folder_int, stop_after=len(ports))
    if not candidates:
        logger.error(_missing_data_message(base_folder_int))
        return base_folder_int, []

    assignments = [(port, f"{folder:03d}") for port, folder in zip(ports, candidates)]
    results: List[Optional[str]] = [None] * len(assignments)

    def worker(port: str, folder_name: str) -> Optional[str]:
        return folder_name if _push_data_file(port, folder_name, bin_root) else None

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
    return next_base, used


    results: List[Optional[str]] = [None] * len(assignments)

    def worker(port: str, folder_name: str) -> Optional[str]:
        return folder_name if _push_data_file(port, folder_name, bin_root) else None

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
                logger.exception("run_push worker エラー")
                results[index] = None

    used = [folder_name for folder_name in results if folder_name]
    next_base = base_folder_int + len(used)
    return next_base, used


    results: List[Optional[str]] = [None] * len(assignments)

    def worker(port: str, folder_name: str) -> Optional[str]:
        return folder_name if _push_data_file(port, folder_name, bin_root) else None

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
                logger.exception("run_push worker エラー")
                results[index] = None

    used = [folder_name for folder_name in results if folder_name]
    next_base = base_folder_int + len(used)
    return next_base, used


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

    def worker(order: int, port: str, folder: str) -> bool:
        delay = min(order * _START_STAGGER_SECONDS, 5.0)
        if delay:
            time.sleep(delay)

        if not _wait_for_device_ready(port):
            message = f"フォルダ_{folder}: {operation_name}準備待ちタイムアウト"
            multi_logger.log_error(port, message)
            logger.warning(f"[WAIT] {message}")
            return False

        try:
            result = operation(port, folder, multi_logger, **base_kwargs)
            if result:
                multi_logger.log_success(port)
                logger.debug(f"[OK] フォルダ_{folder}: {operation_name}成功")
                return True
            message = f"フォルダ_{folder}: {operation_name}失敗"
            multi_logger.log_error(port, message)
            logger.warning(f"[NG] {message}")
            return False
        except Exception as exc:
            message = f"フォルダ_{folder}: {operation_name}失敗 ({exc})"
            multi_logger.log_error(port, message)
            logger.exception(f"[NG] フォルダ_{folder}: {operation_name}失敗", exc_info=True)
            return False

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

    folders = _assign_folders(base_folder_int, ports)
    _execute_operation_batch(ports, folders, operation, operation_name, custom_args)
    next_base = base_folder_int + len(folders)

    if additional_operation:
        try:
            additional_operation(next_base)
        except Exception:
            logger.exception("additional_operation実行エラー")

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
        logger.warning("run_loop_enhanced: 対象デバイスがありません")
        return base_folder_int, False
    if base_folder_int > MAX_FOLDER_LIMIT:
        logger.warning(f"run_loop_enhanced: ベースフォルダ {base_folder_int:03d} が上限を超えています")
        return base_folder_int, True

    try:
        logger.info(f"ログインループ開始 フォルダ {base_folder_int:03d} から")
    except Exception:
        pass

    _ = use_independent_processing  # Retained for API compatibility.

    bin_root = _resolve_bin_push_root()

    if bin_root is None:

        return None, True

    available_folders = _collect_data_folders(bin_root, base_folder_int)
    if not available_folders:

        logger.error(_missing_data_message(base_folder_int))

        return None, True

    assignment_lock = threading.Lock()
    processed_lock = threading.Lock()
    folder_iter = iter(available_folders)
    processed_success: List[int] = []
    base_kwargs = _snapshot_custom_args(custom_args)

    multi_logger = MultiDeviceLogger(ports)

    def fetch_next_folder() -> Optional[int]:
        with assignment_lock:
            try:
                return next(folder_iter)
            except StopIteration:
                return None

    def worker(port: str) -> None:
        while True:
            folder_value = fetch_next_folder()
            if folder_value is None:
                return

            folder_name = f"{folder_value:03d}"
            multi_logger.update_task_status(port, folder_name, f"{operation_name}準備中")

            if not _push_data_file(port, folder_name, bin_root):
                multi_logger.log_error(port, f"push失敗 ({folder_name})")
                logger.error(f"[NG] フォルダ_{folder_name}: push失敗")
                continue

            multi_logger.update_task_status(port, folder_name, f"{operation_name}実行中")

            try:
                operation(port, folder_name, multi_logger, **base_kwargs)
                multi_logger.log_success(port)
                logger.info(f"[OK] フォルダ_{folder_name}: {operation_name}成功")
                with processed_lock:
                    processed_success.append(folder_value)
            except Exception as exc:
                multi_logger.log_error(port, str(exc))
                logger.exception(f"[NG] フォルダ_{folder_name}: {operation_name}失敗")
            finally:
                multi_logger.update_task_status(port, folder_name, f"{operation_name}完了")

            if additional_operation:
                try:
                    additional_operation(folder_value + 1)
                except Exception:
                    logger.exception("additional_operation実行エラー")

    with concurrent.futures.ThreadPoolExecutor(max_workers=len(ports)) as executor:
        futures = [executor.submit(worker, port) for port in ports]
        for future in concurrent.futures.as_completed(futures):
            try:
                future.result()
            except Exception:
                logger.exception("run_loop_enhanced workerスレッドエラー")

    processed_success.sort()
    if processed_success:
        first = processed_success[0]
        last = processed_success[-1]
        logger.info(f"{operation_name}: {len(processed_success)}フォルダ処理 ({first:03d}-{last:03d})")
    else:
        logger.warning(f"{operation_name}: 成功したフォルダはありませんでした")

    next_base = available_folders[-1] + 1
    should_stop = next_base > MAX_FOLDER_LIMIT
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



