"""
monst.device.checks - Character and progress checking operations.

キャラクター確認や進行状況チェック機能を提供します。
"""

from __future__ import annotations

import time
from typing import Optional

from config import on_check
from logging_util import logger, MultiDeviceLogger
from monst.adb import perform_action
from monst.image import tap_if_found, tap_until_found

from .navigation import home

def icon_check(
    device_port: str, 
    folder: str, 
    multi_logger: Optional[MultiDeviceLogger] = None
) -> None:
    """各種チェック機能を実行します。
    
    設定に応じて以下のチェックを実行：
    - ノマクエチェック (on_check=1)
    - 覇者の塔クリアチェック (on_check=2)  
    - 守護獣所持チェック (on_check=3)
    
    Args:
        device_port: 対象デバイスのポート
        folder: フォルダ名
        multi_logger: マルチデバイスロガー（オプション）
        
    Example:
        >>> icon_check("127.0.0.1:62001", "folder_001")
    """
    if not home(device_port, folder):
        logger.warning(f"デバイス {device_port}: home関数が失敗しましたが、処理を継続します")

    if on_check == 1:  # ノマクエチェック
        _check_normal_quest(device_port, folder)
    elif on_check == 2:  # 覇者の塔クリアチェック
        _check_tower_completion(device_port, folder)
    elif on_check == 3:  # 守護獣所持チェック
        _check_guardian_beasts(device_port, folder)

def _check_normal_quest(device_port: str, folder: str) -> None:
    """ノマクエの進行状況をチェックします。"""
    max_attempts = 10
    for attempt in range(max_attempts):
        if tap_if_found('tap', device_port, "noma.png", "key"):
            break
        tap_if_found('tap', device_port, "quest_c.png", "key")
        tap_if_found('tap', device_port, "quest.png", "key")
        tap_if_found('tap', device_port, "ichiran.png", "key")
        tap_if_found('tap', device_port, "ok.png", "key")
        tap_if_found('tap', device_port, "close.png", "key")
        time.sleep(1)

def _check_tower_completion(device_port: str, folder: str) -> None:
    """覇者の塔のクリア状況をチェックします。"""
    timeout: int = 60  # タイムアウト時間（秒単位）
    start_time: float = time.time()  # 処理開始時間を記録

    while True:
        # "hasyafin1.png" を探す
        if tap_if_found('tap', device_port, "hasyafin1.png", "key"):
            break  # 見つかった場合、ループを終了

        # 2分間見つからなかった場合
        if time.time() - start_time > timeout:
            logger.info(f"覇者未完了。対象フォルダ: {folder}")
            break

        # 他のタップ処理を実行
        tap_if_found('tap', device_port, "quest_c.png", "key")
        tap_if_found('tap', device_port, "quest.png", "key")
        tap_if_found('tap', device_port, "ichiran.png", "key")
        tap_if_found('tap', device_port, "ok.png", "key")
        tap_if_found('tap', device_port, "close.png", "key")
        time.sleep(1)  # 次のチェックまで待機

def _check_guardian_beasts(device_port: str, folder: str) -> None:
    """守護獣の所持状況をチェックします（mon6準拠）。"""
    tap_until_found(device_port, "monbox.png", "key", "monster.png", "key", "tap")
    tap_until_found(device_port, "shugo_box2.png", "key", "shugo_box.png", "key", "tap")
    tap_until_found(device_port, "shugo_ishi.png", "key", "ok.png", "key", "tap")
    
    # mon6準拠の守護獣所持チェック
    if not tap_if_found('stay', device_port, "shugo1.png", "icon"):
        logger.info(f"守護１未所持　対象フォルダ: {folder}")
    if not tap_if_found('stay', device_port, "shugo2.png", "icon"):
        logger.info(f"守護２未所持　対象フォルダ: {folder}")
    if not tap_if_found('stay', device_port, "shugo3.png", "icon"):
        logger.info(f"守護３未所持　対象フォルダ: {folder}")
    if not tap_if_found('stay', device_port, "shugo4.png", "icon"):
        logger.info(f"守護４未所持　対象フォルダ: {folder}")