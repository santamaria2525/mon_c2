# -*- coding: utf-8 -*-
"""
Excel ベースのアカウントバックアップをレガシーに頼らず実行するためのモジュール。
"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Optional, Sequence

import openpyxl  # type: ignore

from adb_utils import reset_adb_server
from logging_util import MultiDeviceLogger, logger
from utils import display_message, get_target_folder

from mon_c2.services import ConfigService, MultiDeviceService
from missing_functions import device_operation_excel_and_save


class AccountBackupExecutor:
    """Handle Excel-driven account backup logic."""

    def __init__(
        self,
        core,
        config_service: ConfigService,
        multi_device_service: MultiDeviceService,
    ) -> None:
        self.core = core
        self.config_service = config_service
        self.multi_device_service = multi_device_service

    def run(self) -> None:
        ports = self._resolve_ports()
        if not ports:
            return

        workbook = self._load_workbook("mon_aco.xlsx")
        if workbook is None:
            return

        sheet = workbook.active
        total_rows = sheet.max_row

        current_row = self._resolve_start_row(total_rows)
        if current_row is None:
            return

        logger.info("Excelバックアップ開始: port=%s, start_row=%d", ports, current_row)
        reset_adb_server()

        while current_row <= total_rows and not self.core.is_stopping():
            self.multi_device_service.remove_all_nox()

            chunk = []
            for port in ports:
                if current_row > total_rows:
                    break
                chunk.append((port, current_row))
                current_row += 1

            if not chunk:
                break

            logger.debug("バックアップ対象: %s", chunk)
            self._process_chunk(workbook, chunk)

        logger.info("Excelバックアップ終了")

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    def _resolve_ports(self) -> Sequence[str]:
        snapshot = self.config_service.load()
        ports = self.config_service.get_ports_for_device_count(snapshot.device_count)
        if not ports:
            logger.error("Excelバックアップ: ポート設定が取得できませんでした。config.json を確認してください。")
        return ports

    def _load_workbook(self, filename: str):
        path = Path(filename)
        if not path.exists():
            logger.error("Excelバックアップ: %s が見つかりません。", filename)
            display_message("エラー", f"{filename} が見つかりません。")
            return None
        try:
            return openpyxl.load_workbook(str(path))
        except Exception as exc:
            logger.error("Excelバックアップ: %s の読み込みに失敗しました (%s)", filename, exc)
            display_message("エラー", f"{filename} の読み込みに失敗しました。\n{exc}")
            return None

    def _resolve_start_row(self, total_rows: int) -> Optional[int]:
        row = get_target_folder()
        if row is None:
            logger.info("Excelバックアップ: 行番号が選択されませんでした。処理を中断します。")
            return None
        try:
            value = int(row)
        except ValueError:
            logger.error("Excelバックアップ: 無効な行番号 %s", row)
            display_message("エラー", "行番号は整数で入力してください。")
            return None
        if value < 1 or value > total_rows:
            logger.error("Excelバックアップ: 行番号 %d は範囲外です (1-%d)", value, total_rows)
            display_message("エラー", f"行番号は 1 から {total_rows} の範囲で指定してください。")
            return None
        return value

    def _process_chunk(self, workbook, assignments: Sequence[tuple[str, int]]) -> None:
        events = []
        logger.debug("バックアップ処理: %s", assignments)
        ml = MultiDeviceLogger([port for port, _ in assignments])

        with ThreadPoolExecutor(max_workers=len(assignments)) as executor:
            futures = []
            for port, row in assignments:
                event = threading.Event()
                events.append((event, port))
                future = executor.submit(
                    device_operation_excel_and_save,
                    port,
                    workbook,
                    row,
                    row,
                    event,
                    ml,
                )
                futures.append((port, future))

        for event, _ in events:
            event.wait()

        for port, future in futures:
            try:
                future.result()
            except Exception as exc:  # pragma: no cover - defensive logging
                logger.error("Excelバックアップ: %s で例外が発生しました: %s", port, exc)

        ml.summarize_results("Excelバックアップ")


__all__ = ["AccountBackupExecutor"]
