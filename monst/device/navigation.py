"""
monst.device.navigation - Navigation and home screen operations.

ナビゲーションとホーム画面操作を提供します。
"""

from __future__ import annotations

from typing import Optional

from login_operations import handle_screens
from logging_util import MultiDeviceLogger
from monst.adb import perform_action
from monst.image import tap_if_found

def home(
    device_port: str, 
    folder: str, 
    multi_logger: Optional[MultiDeviceLogger] = None
) -> bool:
    """デバイスをホーム画面に移動します。
    
    Args:
        device_port: 対象デバイスのポート
        folder: フォルダ名
        multi_logger: マルチデバイスロガー（オプション）
        
    Returns:
        ホーム画面への移動が成功したかどうか
        
    Example:
        >>> success = home("127.0.0.1:62001", "folder_001")
    """
    import time
    from logging_util import logger
    
    max_attempts = 10  # 最大試行回数を制限
    
    for attempt in range(max_attempts):
        # room.pngが見つかったら成功
        if tap_if_found('stay', device_port, "room.png", "login"):
            return True
            
        # ホームボタンを押してホーム画面に戻る
        handle_screens(device_port, "login")
        tap_if_found('tap', device_port, "zz_home.png", "login")
        tap_if_found('tap', device_port, "zz_home2.png", "login")
        perform_action(device_port, 'tap', 50, 170, duration=150)
        time.sleep(1)
        
        # ホーム画面が表示されたら成功とみなす
        if tap_if_found('stay', device_port, "zz_home.png", "login") or tap_if_found('stay', device_port, "zz_home2.png", "login"):
            return True
    
    logger.warning(f"デバイス {device_port}: home関数でホーム画面に戻れませんでした")
    return False