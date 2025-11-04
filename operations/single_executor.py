# -*- coding: utf-8 -*-
"""Single-device operations (write / reset / save)."""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Sequence

from adb_utils import (
    close_monster_strike_app,
    remove_data10_bin_from_nox,
    reset_adb_server,
    run_adb_command,
    start_monster_strike_app,
    pull_file_from_nox,
)
from app_crash_recovery import check_app_crash, ensure_app_running
from logging_util import logger
from utils import display_message, get_base_path, get_resource_path

from domain import LoginWorkflow
from services import ConfigService


class SingleDeviceExecutor:
    """Operations that target a single device."""

    def __init__(self, core, config_service: ConfigService) -> None:
        self.core = core
        self.config_service = config_service
        self.login_workflow = LoginWorkflow(core)

    # ------------------------------------------------------------------ #
    # Public entry points
    # ------------------------------------------------------------------ #
    def write(self) -> None:
        port = self._resolve_port()
        if not port:
            return

        folder = self._resolve_folder()
        if folder is None:
            return
        folder_str = f"{folder:03d}"

        src = get_resource_path(f"{folder_str}/data10.bin", "bin_push")
        if not src or not Path(src).exists():
            message = f"フォルダ{folder_str}のdata10.binが見つかりません。"
            logger.error(message)
            display_message("エラー", message)
            return

        logger.info("シングル書き込み開始 port=%s folder=%s", port, folder_str)

        reset_adb_server()
        close_monster_strike_app(port)
        run_adb_command(["push", src, "/data/data/jp.co.mixi.monsterstrike/data10.bin"], port)
        start_monster_strike_app(port)

        if not ensure_app_running(port):
            message = "アプリの起動を確認できませんでした。再度お試しください。"
            logger.error(message)
            display_message("エラー", message)
            return

        success = self.login_workflow.execute(port, folder_str)
        if not success:
            logger.warning("シングル書き込み: ログインに失敗しました (port=%s)", port)

        if check_app_crash(port):
            logger.warning("シングル書き込み: クラッシュ履歴を検出しました (port=%s)", port)

        logger.info("シングル書き込み完了 port=%s folder=%s", port, folder_str)

    def initialize(self) -> None:
        port = self._resolve_port()
        if not port:
            return

        logger.info("シングル初期化開始 port=%s", port)
        reset_adb_server()
        close_monster_strike_app(port)
        remove_data10_bin_from_nox(port)
        start_monster_strike_app(port)
        logger.info("シングル初期化完了 port=%s", port)

    def save(self) -> None:
        port = self._resolve_port()
        if not port:
            return

        save_folder = self._resolve_save_folder()
        if save_folder is None:
            return

        reset_adb_server()
        logger.info("シングル保存開始 port=%s -> %s", port, save_folder)

        save_dir = Path(get_base_path()) / "bin_pull" / save_folder
        save_dir.mkdir(parents=True, exist_ok=True)
        save_file = save_dir / "data10.bin"

        success = pull_file_from_nox(port, save_folder)

        if not success or not save_file.exists() or save_file.stat().st_size == 0:
            message = "データの保存に失敗しました。"
            logger.error("シングル保存失敗 port=%s folder=%s", port, save_folder)
            display_message("エラー", message)
            return

        logger.info("シングル保存完了 %s", save_file)

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    def _resolve_port(self) -> Optional[str]:
        try:
            port = self.core.select_device_port()
            if port:
                return port
        except Exception:
            pass

        available_ports = self._available_ports()
        if not available_ports:
            logger.error("利用可能なポートが見つかりませんでした。")
            return None

        print("\n-- 使用するデバイスポートを選択してください --")
        for idx, candidate in enumerate(available_ports, 1):
            print(f"  {idx}. {candidate}")

        while True:
            prompt = f"ポート番号を入力 (1-{len(available_ports)}, 0=キャンセル, 空=1番目): "
            choice = input(prompt).strip()
            if choice == "0":
                return None
            if choice == "":
                return available_ports[0]
            try:
                idx = int(choice)
                if 1 <= idx <= len(available_ports):
                    return available_ports[idx - 1]
            except ValueError:
                pass
            print("無効な入力です。")

    def _available_ports(self) -> Sequence[str]:
        snapshot = self.config_service.load()
        return self.config_service.get_ports_for_device_count(snapshot.device_count)

    def _resolve_folder(self) -> Optional[int]:
        folder = self.core.get_start_folder()
        if folder is None:
            return None
        try:
            value = int(folder)
            if value <= 0:
                raise ValueError
            return value
        except ValueError:
            logger.error("無効なフォルダ番号が指定されました: %s", folder)
            display_message("エラー", "フォルダ番号は正の整数で入力してください。")
            return None

    def _resolve_save_folder(self) -> Optional[str]:
        folder: Optional[str] = None
        try:
            folder = self.core.get_start_folder()
        except Exception:
            folder = None

        if folder:
            folder = str(folder).strip()

        while not folder:
            print("\n-- 保存先のフォルダ名を入力してください --")
            folder = input("フォルダ名 (空=single, 0=キャンセル): ").strip()
            if folder == "0":
                return None
            if folder == "":
                folder = "single"
            if any(ch in folder for ch in '<>:"/\\|?*'):
                print("使用できない文字が含まれています。")
                folder = None
        return folder


__all__ = ["SingleDeviceExecutor"]
