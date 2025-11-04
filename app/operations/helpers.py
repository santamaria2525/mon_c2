"""Helper utilities for the operations manager."""

from __future__ import annotations

from typing import Any

from logging_util import logger


# ---------------------------------------------------------------------------
# Lazy multi-device entry points
# ---------------------------------------------------------------------------
def run_push(*args: Any, **kwargs: Any):
    from multi_device import run_push as _func
    return _func(*args, **kwargs)


def run_loop(*args: Any, **kwargs: Any):
    from multi_device import run_loop as _func
    return _func(*args, **kwargs)


def run_loop_enhanced(*args: Any, **kwargs: Any):
    from multi_device import run_loop_enhanced as _func
    return _func(*args, **kwargs)


def remove_all_nox(*args: Any, **kwargs: Any):
    from multi_device import remove_all_nox as _func
    return _func(*args, **kwargs)


def run_in_threads(*args: Any, **kwargs: Any):
    from multi_device import run_in_threads as _func
    return _func(*args, **kwargs)


# ---------------------------------------------------------------------------
# Logging helpers
# ---------------------------------------------------------------------------
FRIEND_PROCESS_VERBOSE = False
SUCCESS_TOKENS = {"\u6210\u529f", "success"}


def log_folder_result(folder: str, operation: str, status: str, details: str = "") -> None:
    """Format and print folder-level results in a consistent style."""
    status_icon = "[OK]" if status in SUCCESS_TOKENS else "[NG]"
    message = f"{status_icon} folder{folder}: {operation}{status}"
    if details:
        message += f" ({details})"
    print(message)


def debug_log(message: str) -> None:
    """Emit verbose logs for friend-processing when explicitly enabled."""
    if FRIEND_PROCESS_VERBOSE:
        logger.info(message)


# ---------------------------------------------------------------------------
# Image helpers
# ---------------------------------------------------------------------------
def find_and_click_with_protection(
    port: str,
    image_name: str,
    category: str,
    device_name: str,
    max_attempts: int = 30,
    threshold: float = 0.8,
    sleep_time: float = 0.5,
) -> bool:
    """Search for an image and tap it with loop-protection safeguards."""
    from monst.image import find_image_on_device
    from monst.adb import perform_action
    from loop_protection import loop_protection
    import time

    attempt = 0
    while attempt < max_attempts:
        x, y = find_image_on_device(port, image_name, category, threshold=threshold)
        if x is not None and y is not None:
            logger.debug(f"{device_name}: matched {image_name} at ({x}, {y})")
            perform_action(port, 'tap', x, y)
            return True

        attempt += 1
        if attempt % 10 == 0:
            logger.debug(f"{device_name}: searching {image_name} (attempt {attempt})")

        if attempt >= max_attempts:
            logger.warning(f"{device_name}: {image_name} not found after {max_attempts} attempts")
            operation_key = f"{device_name}_{image_name}_search"
            if loop_protection.should_backtrack(operation_key, attempt):
                backtrack_step = loop_protection.execute_backtrack(operation_key, attempt)
                if backtrack_step is not None:
                    logger.warning(
                        f"Loop protection triggered for {device_name} while searching {image_name}"
                    )
                    return find_and_click_with_protection(
                        port,
                        image_name,
                        category,
                        device_name,
                        max_attempts,
                        threshold,
                        sleep_time,
                    )
            logger.error(f"{device_name}: {image_name} search aborted by loop protection")
            loop_protection.reset_operation(operation_key, 0)
            return False

        time.sleep(sleep_time)

    return False


# ---------------------------------------------------------------------------
# Folder utilities
# ---------------------------------------------------------------------------
def write_account_folders(base_folder: int) -> None:
    """Validate availability of account folders before processing."""
    from utils import get_resource_path
    import os

    logger.debug(f"Account folder rewrite start: {base_folder}~{base_folder + 7}")

    try:
        for i in range(8):
            folder_num = base_folder + i
            folder_str = f"{folder_num:03d}"
            src = get_resource_path(f"{folder_str}/data10.bin", "bin_push")
            if src is None or not os.path.exists(src):
                logger.warning(f"Warning folder{folder_str}: data10.bin file not found")
                continue

            file_size = os.path.getsize(src)
            if file_size == 0:
                logger.warning(f"Warning folder{folder_str}: data10.bin file is empty")
                continue

            logger.debug(f"OK folder{folder_str}: valid ({file_size:,} bytes)")

        logger.debug(f"Account folder preparation complete: {base_folder} to {base_folder + 7}")

        logger.info("Terminal-Folder mapping:")
        for i in range(8):
            terminal_num = i + 1
            folder_num = base_folder + i
            logger.debug(f"   Terminal{terminal_num} -> Folder{folder_num:03d}")

    except Exception as exc:
        logger.error(f"ERROR: Account folder rewrite error: {exc}")
        raise
