"""
device_state.py - デバイス状態管理モジュール

デバイスポートとフォルダ名のマッピングを管理します。
"""

from typing import Dict, List, Optional
from logging_util import logger

# グローバルなデバイス-フォルダマッピング
_device_folder_mapping: Dict[str, str] = {}

def setup_device_folder_mapping(device_ports: List[str], loaded_folders: List[str]) -> None:
    """デバイスポートとフォルダのマッピングを設定します。
    
    Args:
        device_ports: デバイスポートのリスト
        loaded_folders: 読み込まれたフォルダのリスト
    """
    global _device_folder_mapping
    _device_folder_mapping.clear()
    
    # デバイスポートとフォルダを対応付け
    for i, device_port in enumerate(device_ports):
        if i < len(loaded_folders):
            folder = loaded_folders[i]
            _device_folder_mapping[device_port] = folder
            logger.debug(f"デバイスマッピング設定: {device_port} -> {folder}")
        else:
            logger.warning(f"フォルダが不足しています: デバイス {device_port} に対応するフォルダがありません")

def get_folder_for_device(device_port: str) -> Optional[str]:
    """指定されたデバイスポートに対応するフォルダを取得します。
    
    Args:
        device_port: デバイスポート
        
    Returns:
        対応するフォルダ名、見つからない場合はNone
    """
    folder = _device_folder_mapping.get(device_port)
    if folder is None:
        logger.warning(f"デバイスポート {device_port} に対応するフォルダが見つかりません")
    return folder

def get_device_folder_mapping() -> Dict[str, str]:
    """現在のデバイス-フォルダマッピングを取得します。
    
    Returns:
        デバイスポート -> フォルダ名の辞書
    """
    return _device_folder_mapping.copy()

def clear_device_folder_mapping() -> None:
    """デバイス-フォルダマッピングをクリアします。"""
    global _device_folder_mapping
    _device_folder_mapping.clear()
    logger.debug("デバイス-フォルダマッピングをクリアしました")