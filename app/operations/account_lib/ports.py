"""Account operation helpers."""

from __future__ import annotations

from .common import (
    pyautogui,
    time,
    openpyxl,
    ThreadPoolExecutor,
    as_completed,
    logger,
    display_message,
    get_target_folder,
    create_mm_folders,
    get_mm_folder_status,
    clean_mm_folders,
    batch_rename_folders_csv,
    batch_rename_folders_excel,
)

def _get_main_and_sub_ports(self) -> tuple[str, list[str]]:
    """メイン端末とサブ端末のポートを取得"""
    try:
        from config import get_config
        config = get_config()
        device_count = config.device_count

        # メイン端末は常に62025
        main_port = "127.0.0.1:62025"

        # サブ端末は62026から device_count-1 台分
        sub_ports = []
        for i in range(device_count - 1):  # メイン1台を除く
            port_num = 62026 + i
            sub_ports.append(f"127.0.0.1:{port_num}")

        # logger.debug(f"デバイス構成 - メイン: {main_port}, サブ: {len(sub_ports)}台")
        return main_port, sub_ports

    except Exception as e:
        logger.error(f"ポート設定取得エラー: {e}")
        return None, None
