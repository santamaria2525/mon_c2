# -*- coding: utf-8 -*-
"""Hasya (覇者) two-set workflow executor."""

from __future__ import annotations

import concurrent.futures
import time
from typing import Callable, Iterable, List, Optional, Sequence

import pyautogui
from logging_util import MultiDeviceLogger, logger
from memory_monitor import force_cleanup, memory_monitor
from monst.device.hasya import (
    device_operation_hasya,
    device_operation_hasya_wait,
)
from utils.gui_dialogs import multi_press_enhanced
from utils.set_processing import find_next_set_folders
from monst.image import tap_if_found_on_windows
from functools import partial
from monst.image.device_management import pause_auto_restart, resume_auto_restart

from services import MultiDeviceService

from device_operations import continue_hasya_with_base_folder, continue_hasya

_MAX_WORKERS = 4


class HasyaExecutor:
    """Execute the legacy Hasya two-set workflow with modern guards."""

    def __init__(
        self,
        multi_device_service: MultiDeviceService,
    ) -> None:
        self.multi_device_service = multi_device_service

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    def run(self, base_folder: int, ports: Sequence[str]) -> None:
        current_base = base_folder
        device_count = len(ports)

        pause_auto_restart("hasya_menu")
        try:
            while True:
                logger.info("Hasya workflow start base=%03d ports=%s", current_base, ports)
                self._prepare_memory()

                used_folders, used_ports = self._write_bin(current_base, ports)
                if not used_folders or not used_ports:
                    logger.warning("初期BINが不足しているため Hasya 処理を終了します。")
                    self._restore_memory_defaults()
                    break
                self._run_set(used_folders, used_ports, set_number=1)

                second_base = max(int(folder) for folder in used_folders) + 1
                used_folders, used_ports = self._write_bin(second_base, ports)
                if not used_folders or not used_ports:
                    logger.warning("2セット目のBINが不足しているため Hasya 処理を終了します。")
                    self._restore_memory_defaults()
                    break
                try:
                    second_base = int(used_folders[0])
                except Exception:
                    pass
                self._run_set(used_folders, used_ports, set_number=2)

                self._restore_memory_defaults()
                logger.info("Hasya workflow finished base=%03d-%03d", current_base, second_base)

                next_start = max(int(folder) for folder in used_folders) + 1
                next_idx, next_folders = find_next_set_folders(next_start, device_count)
                if not next_folders or len(next_folders) < device_count:
                    logger.info("次のフォルダセットが見つからないため終了します。")
                    break

                try:
                    current_base = int(next_folders[0])
                except ValueError:
                    logger.warning("次フォルダの解析に失敗しました: %s", next_folders)
                    break
        finally:
            resume_auto_restart()

        logger.info("Hasya workflow complete。")

    # ------------------------------------------------------------------ #
    # Core steps
    # ------------------------------------------------------------------ #
    def _run_set(self, folders: Sequence[str], ports: Sequence[str], *, set_number: int) -> None:
        if not folders or not ports:
            logger.warning("Hasya set %d: no folders/ports to process", set_number)
            return
        set_base = int(folders[0])
        logger.debug("Hasya set %d: base=%03d", set_number, set_base)
        folder_range = self._format_folder_range_from_list(folders)

        # 1) Login & preparation
        prep_success = self._run_parallel(
            ports,
            lambda port, folder, ml: device_operation_hasya(port, folder, ml),
            folders=folders,
            name=f"Hasya set {set_number} preparation",
        )
        self._log_hasya_phase(folder_range, "覇者セット開始", prep_success)

        # 2) Windows macro kick-off
        logger.info("Hasya set %d: start_app/macro kick-off for base %03d", set_number, set_base)
        try:
            continue_hasya_with_base_folder(set_base)
        except Exception as exc:
            logger.error(
                "continue_hasya_with_base_folder failed for base %03d: %s. Fallback to continue_hasya().",
                set_base,
                exc,
            )
            continue_hasya()

        # 3) Host / sub confirmation
        host_ports, sub_ports = self._split_host_sub_ports(ports)
        if host_ports:
            host_success = self._run_parallel(
                host_ports,
                lambda port, ml: device_operation_hasya_wait(port, ml),
                name=f"Hasya set {set_number} host wait",
            )
            self._log_hasya_phase(folder_range, "覇者終了", host_success)

        self._press_macro_keys()
        self._perform_macro_cleanup(len(ports))

        # 4) Immediately move on to the next set (no per-device cleanup needed here)

    # ------------------------------------------------------------------ #
    # Parallel helpers
    # ------------------------------------------------------------------ #
    def _run_parallel(
        self,
        ports: Sequence[str],
        operation: Callable[..., bool],
        *,
        folders: Optional[Sequence[str]] = None,
        name: str,
    ) -> bool:
        if not ports:
            return False

        ml = MultiDeviceLogger(list(ports), list(folders) if folders else None)
        worker_count = min(len(ports), _MAX_WORKERS)
        with concurrent.futures.ThreadPoolExecutor(max_workers=worker_count) as executor:
            futures = {}
            for idx, port in enumerate(ports):
                folder = folders[idx] if folders else None
                if folder is not None:
                    futures[executor.submit(operation, port, folder, ml)] = port
                else:
                    futures[executor.submit(operation, port, ml)] = port

            for future in concurrent.futures.as_completed(futures):
                port = futures[future]
                try:
                    result = future.result()
                    logger.debug("%s: %s => %s", name, port, result)
                except Exception as exc:
                    logger.error("%s: %s 実行中に例外が発生しました: %s", name, port, exc)

        success, total = ml.summarize_results(name, suppress_summary=True)
        return success == total

    # ------------------------------------------------------------------ #
    # Memory handling
    # ------------------------------------------------------------------ #
    def _prepare_memory(self) -> None:
        force_cleanup()
        memory_monitor.cleanup_aggressive_mode = True
        memory_monitor.consecutive_critical_count = 0
        memory_monitor.check_interval = 30

    def _restore_memory_defaults(self) -> None:
        memory_monitor.cleanup_aggressive_mode = False
        memory_monitor.consecutive_critical_count = 0
        memory_monitor.check_interval = 60

    # ------------------------------------------------------------------ #
    # Bin push wrapper
    # ------------------------------------------------------------------ #
    def _write_bin(self, base_folder: int, ports: Sequence[str]) -> tuple[List[str], List[str]]:
        try:
            next_base, used_folders = self.multi_device_service.run_push(base_folder, ports)
            if not used_folders:
                logger.warning("Hasya BIN 書き込み対象が見つかりません: %03d", base_folder)
                return [], []
            if len(used_folders) < len(ports):
                logger.warning(
                    "Hasya BIN 書き込み: %d 台中 %d 台のみ成功", len(ports), len(used_folders)
                )
            used_ports = list(ports)[: len(used_folders)]
            logger.debug(
                "Hasya BIN 書き込み範囲: %03d-%03d",
                base_folder,
                base_folder + len(used_folders) - 1,
            )
        except Exception as exc:
            logger.error("Hasya BIN 書き込み失敗: %s", exc)
            return [], []
        time.sleep(3)
        return list(used_folders), used_ports

    # ------------------------------------------------------------------ #
    # Utility helpers
    # ------------------------------------------------------------------ #
    def _split_host_sub_ports(self, ports: Sequence[str]) -> tuple[List[str], List[str]]:
        host_indices = {3, 7}
        host_ports = [port for idx, port in enumerate(ports) if idx in host_indices]
        sub_ports = [port for idx, port in enumerate(ports) if idx not in host_indices]
        return host_ports, sub_ports

    def _press_macro_keys(self) -> None:
        try:
            multi_press_enhanced()
        except Exception as exc:
            logger.debug("multi_press_enhanced 実行中に例外: %s", exc)

    def _perform_macro_cleanup(self, device_count: int) -> None:
        try:
            self._clear_macro_fin(device_count)
            self._clear_hasya_fin()
        except Exception as exc:
            logger.debug("マクロクリーンアップ中に例外: %s", exc)

    def _clear_macro_fin(self, device_count: int) -> None:
        hits = 0
        misses = 0
        while hits < 40 and misses < 3:
            if tap_if_found_on_windows("tap", "macro_fin.png", "macro"):
                hits += 1
                misses = 0
                time.sleep(1)
            else:
                misses += 1
                time.sleep(1)

        if hits < 6:
            logger.warning("macro_fin.png detections were fewer than expected (%d)", hits)

        for _ in range(3):
            tap_if_found_on_windows("tap", "ok.png", "macro")
            time.sleep(1)

    def _clear_hasya_fin(self) -> None:
        hits = 0
        misses = 0
        while hits < 10 and misses < 2:
            if tap_if_found_on_windows("tap", "hasya_fin.png", "macro"):
                pyautogui.press("enter")
                hits += 1
                misses = 0
                logger.debug("hasya_fin.png detected on Windows UI -> Enter pressed")
                time.sleep(1)
            else:
                misses += 1
                time.sleep(1)

        if hits == 0:
            logger.warning("hasya_fin.png was not detected during cleanup")

    # ------------------------------------------------------------------ #
    # Logging helpers
    # ------------------------------------------------------------------ #
    def _format_folder_range_from_list(self, folders: Sequence[str]) -> str:
        if not folders:
            return "000-000"
        try:
            values = sorted(int(folder) for folder in folders)
        except Exception:
            values = [int(folders[0])]
        return f"{values[0]:03d}-{values[-1]:03d}"

    def _log_hasya_phase(self, folder_range: str, phase_label: str, success: bool) -> None:
        label = folder_range or "フォルダ範囲不明"
        if success:
            logger.info("%s%s", label, phase_label)
        else:
            logger.error("%s%s失敗", label, phase_label)


__all__ = ["HasyaExecutor"]
tap_if_found_on_windows = partial(tap_if_found_on_windows, log=False)
