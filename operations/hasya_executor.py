# -*- coding: utf-8 -*-
"""
Hasya (覇者) two-set workflow executor.
"""

from __future__ import annotations

import concurrent.futures
import time
from typing import Callable, Iterable, List, Optional, Sequence

from logging_util import MultiDeviceLogger, logger
from memory_monitor import force_cleanup, memory_monitor
from monst.device.hasya import (
    device_operation_hasya,
    device_operation_hasya_fin,
    device_operation_hasya_host_fin,
    device_operation_hasya_wait,
)
from utils.gui_dialogs import multi_press_enhanced
from utils.set_processing import find_next_set_folders
from monst.image import tap_if_found_on_windows

from mon_c2.services import MultiDeviceService

from device_operations import continue_hasya_with_base_folder

_MAX_WORKERS = 4


class HasyaExecutor:
    """Execute the legacy覇者二セットを安全に移植したワークフロー."""

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

        while True:
            logger.info("覇者二セット開始: フォルダ%03d / ポート%s", current_base, ports)
            self._prepare_memory()

            if not self._write_bin(current_base, ports):
                logger.warning("初期BINが不足しています。覇者処理を終了します。")
                self._restore_memory_defaults()
                break
            self._run_set(current_base, ports, set_number=1)

            second_base = current_base + device_count
            if not self._write_bin(second_base, ports):
                logger.warning("2セット目のBINが不足しています。覇者処理を終了します。")
                self._restore_memory_defaults()
                break
            self._run_set(second_base, ports, set_number=2)

            self._restore_memory_defaults()
            logger.info("覇者二セット完了: フォルダ%03d-%03d", current_base, second_base)

            next_idx, next_folders = find_next_set_folders(second_base + device_count, device_count)
            if not next_folders or len(next_folders) < device_count:
                logger.info("次のフォルダセットが見つからないため覇者処理を終了します。")
                break

            try:
                current_base = int(next_folders[0])
            except ValueError:
                logger.warning("次フォルダの解析に失敗しました: %s", next_folders)
                break

        logger.info("覇者処理を終了しました。")

    # ------------------------------------------------------------------ #
    # Core steps
    # ------------------------------------------------------------------ #
    def _run_set(self, set_base: int, ports: Sequence[str], *, set_number: int) -> None:
        logger.debug("覇者セット%d: base=%03d", set_number, set_base)
        folders = [f"{set_base + idx:03d}" for idx, _ in enumerate(ports)]

        # 1) ログイン & 覇者準備
        self._run_parallel(
            ports,
            lambda port, folder, ml: device_operation_hasya(port, folder, ml),
            folders=folders,
            name=f"覇者{set_number}セット準備",
        )

        # 2) Windowsマクロ起動
        continue_hasya_with_base_folder(set_base)
        self._press_macro_keys()

        # 3) ホスト待機・完了確認
        host_ports, sub_ports = self._split_host_sub_ports(ports)
        if host_ports:
            self._run_parallel(
                host_ports,
                lambda port, ml: device_operation_hasya_wait(port, ml),
                name=f"覇者{set_number}セットホスト待機",
            )

        if sub_ports:
            self._run_parallel(
                sub_ports,
                lambda port, ml: device_operation_hasya_fin(port, ml),
                name=f"覇者{set_number}セットサブ確認",
            )

        if host_ports:
            self._run_parallel(
                host_ports,
                lambda port, ml: device_operation_hasya_host_fin(port, ml),
                name=f"覇者{set_number}セットホスト確認",
            )

        self._perform_macro_cleanup(len(ports))

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
    ) -> None:
        if not ports:
            return

        ml = MultiDeviceLogger(list(ports))
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
                    logger.error("%s: %s 実行中に例外: %s", name, port, exc)

        ml.summarize_results(name)

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
    def _write_bin(self, base_folder: int, ports: Sequence[str]) -> bool:
        try:
            next_base, used_folders = self.multi_device_service.run_push(base_folder, ports)
            if not used_folders:
                logger.warning("覇者bin書き込み対象が見つかりません: %03d", base_folder)
                return False
            if len(used_folders) < len(ports):
                logger.warning("覇者bin書き込み: %d端末中 %d 件のみ検出", len(ports), len(used_folders))
            logger.debug(
                "覇者bin書き込み: %03d-%03d",
                base_folder,
                base_folder + len(used_folders) - 1,
            )
        except Exception as exc:
            logger.error("覇者bin書き込み失敗: %s", exc)
            return False
        time.sleep(3)
        return True

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
            logger.debug("multi_press_enhanced 実行失敗: %s", exc)

    def _perform_macro_cleanup(self, device_count: int) -> None:
        try:
            for _ in range(3):
                tap_if_found_on_windows("tap", "ok.png", "macro")
                time.sleep(2)
            multi_press_enhanced()
            for _ in range(device_count):
                tap_if_found_on_windows("tap", "macro_fin.png", "macro")
                time.sleep(2)
        except Exception as exc:
            logger.debug("マクロ後処理で例外: %s", exc)


__all__ = ["HasyaExecutor"]
