"""
missing_functions.py - Temporary stubs for missing functions

リファクタリング中に削除された関数の一時的なスタブです。
"""

from __future__ import annotations

import time
from typing import Any, Optional

from logging_util import logger, MultiDeviceLogger

# 覇者関連の関数は monst.device.hasya から import
from monst.device.hasya import (
    device_operation_hasya,
    device_operation_hasya_wait, 
    device_operation_hasya_fin,
    device_operation_hasya_host_fin,
    continue_hasya,
    load_macro
)

def device_operation_excel_and_save(
    device_port: str, 
    workbook: Any, 
    start_row: int, 
    end_row: int, 
    completion_event: Any, 
    multi_logger: Optional[MultiDeviceLogger] = None
) -> bool:
    """Excel操作と保存の実装。ガチャボタン誤作動防止機能付き。"""
    from adb_utils import close_monster_strike_app, start_monster_strike_app, run_adb_command, pull_file_from_nox
    from login_operations import device_operation_login
    from image_detection import tap_if_found
    from utils import get_resource_path
    
    try:
        # アプリを閉じる
        close_monster_strike_app(device_port)
        
        # データファイルをプッシュ
        folder_name = str(start_row).zfill(3)
        src = get_resource_path(f"{folder_name}/data10.bin", "bin_push")
        run_adb_command(['push', src, "/data/data/jp.co.mixi.monsterstrike/data10.bin"], device_port)
        
        # アプリを起動
        start_monster_strike_app(device_port)
        
        # ログイン処理（ガチャボタン誤作動防止機能付き）
        max_attempts = 6
        for attempt in range(max_attempts):
            if device_operation_login(device_port, folder_name, multi_logger, home_early=False):
                # ルーム画面到達確認とガチャボタンチェック
                room_confirmed = False
                room_check_attempts = 0
                max_room_checks = 10
                
                while not room_confirmed and room_check_attempts < max_room_checks:
                    # ガチャボタン誤作動防止 - 最優先チェック
                    if tap_if_found('tap', device_port, "gacha_shu.png", "login"):
                        logger.warning(f"デバイス {device_port}: Excel処理中にガチャボタンを検出しました。ホーム画面に戻ります。")
                        tap_if_found('tap', device_port, "zz_home.png", "login")
                        tap_if_found('tap', device_port, "zz_home2.png", "login")
                        time.sleep(1)
                        room_check_attempts += 1
                        continue
                    
                    # ルーム画面確認
                    if tap_if_found('stay', device_port, "room.png", "login"):
                        room_confirmed = True
                        break
                    
                    # ホーム画面処理
                    tap_if_found('tap', device_port, "zz_home.png", "login")
                    tap_if_found('tap', device_port, "zz_home2.png", "login")
                    
                    from adb_utils import perform_action
                    perform_action(device_port, 'tap', 50, 170, duration=150)
                    
                    room_check_attempts += 1
                    time.sleep(0.5)
                
                if room_confirmed:
                    # ファイル保存
                    pull_file_from_nox(device_port, folder_name)
                    
                    if completion_event:
                        completion_event.set()
                    
                    if multi_logger:
                        multi_logger.log_success(device_port)
                    
                    logger.info(f"Excel処理完了: {device_port}, フォルダ {folder_name}")
                    return True
                else:
                    logger.warning(f"ルーム画面に到達できませんでした: {device_port}")
            
        logger.error(f"Excel処理に失敗しました: {device_port}, フォルダ {folder_name}")
        if multi_logger:
            multi_logger.log_error(device_port, "Excel処理失敗")
        return False
        
    except Exception as e:
        logger.error(f"Excel処理中にエラーが発生しました: {device_port}, {str(e)}")
        if multi_logger:
            multi_logger.log_error(device_port, str(e))
        return False

def device_init_only(device_port: str) -> bool:
    """サブ端末専用：アカウント初期化+アプリ起動のみ（ログイン処理なし）"""
    from adb_utils import close_monster_strike_app, start_monster_strike_app, remove_data10_bin_from_nox
    import time
    
    try:
        logger.info(f"シングル初期化開始: {device_port}")
        
        # アプリを閉じる
        close_monster_strike_app(device_port)
        time.sleep(1)
        
        # data10.binを削除（アカウント初期化）
        remove_data10_bin_from_nox(device_port)
        time.sleep(1)
        
        # アプリを起動
        start_monster_strike_app(device_port)
        time.sleep(3)  # アプリ起動待機
        
        logger.info(f"シングル初期化完了: {device_port}")
        return True
        
    except Exception as e:
        logger.error(f"シングル初期化エラー ({device_port}): {e}")
        return False

def device_operation_nobin(
    device_port: str, 
    folder: str, 
    multi_logger: Optional[MultiDeviceLogger] = None
) -> bool:
    """No bin操作の実装（mon6準拠）- フルバージョン。"""
    from adb_utils import close_monster_strike_app, start_monster_strike_app, remove_data10_bin_from_nox
    from login_operations import device_operation_login
    from image_detection import tap_if_found
    
    try:
        # アプリを閉じる
        close_monster_strike_app(device_port)
        
        # data10.binを削除
        remove_data10_bin_from_nox(device_port)
        
        # アプリを起動
        start_monster_strike_app(device_port)
        
        # ログイン処理
        if not device_operation_login(device_port, folder, multi_logger):
            error_msg = f"ログイン失敗 (フォルダ：{folder})"
            logger.error(error_msg)
            if multi_logger:
                multi_logger.log_error(device_port, error_msg)
            return False
        
        # ガチャボタン誤作動防止
        if tap_if_found('tap', device_port, "gacha_shu.png", "login"):
            logger.warning(f"no bin処理中にガチャボタンを検出しました。ホーム画面に戻ります。")
            tap_if_found('tap', device_port, "zz_home.png", "login")
            tap_if_found('tap', device_port, "zz_home2.png", "login")
            time.sleep(1)
        
        if multi_logger:
            multi_logger.log_success(device_port)
        
        logger.info(f"no bin処理完了: {device_port}, フォルダ {folder}")
        return True
        
    except Exception as e:
        error_msg = f"no bin処理中にエラーが発生しました: {str(e)}"
        logger.error(error_msg)
        if multi_logger:
            multi_logger.log_error(device_port, error_msg)
        return False

# device_operation_quest は monst.device.quest で実装済み

# continue_hasya と load_macro は上記でインポート済み