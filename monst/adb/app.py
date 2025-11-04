"""
monst.adb.app - Application lifecycle management.

Monster Strikeアプリの起動・停止・再起動を管理します。
"""

from __future__ import annotations

import time

from .core import run_adb_command, APP_PACKAGE, APP_ACTIVITY

def close_monster_strike_app(device_port: str) -> None:
    """Monster Strikeアプリを強制終了します。
    
    Args:
        device_port: 対象デバイスのポート
    """
    run_adb_command(["shell", "am", "force-stop", APP_PACKAGE], device_port)
    time.sleep(0.5)

def start_monster_strike_app(device_port: str) -> None:
    """Monster Strikeアプリを起動します。
    
    Args:
        device_port: 対象デバイスのポート
    """
    run_adb_command(
        ["shell", "am", "start", "-n", f"{APP_PACKAGE}/{APP_ACTIVITY}"], 
        device_port
    )
    time.sleep(2)

def restart_monster_strike_app(device_port: str) -> None:
    """Monster Strikeアプリを再起動します。
    
    Args:
        device_port: 対象デバイスのポート
    """
    from logging_util import logger
    logger.info(f"● {device_port}: アプリ再起動")
    close_monster_strike_app(device_port)
    time.sleep(1)
    start_monster_strike_app(device_port)
    time.sleep(3)