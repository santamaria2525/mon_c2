"""
monst.device.core - Core device operation orchestration.

デバイス操作の中核となるオーケストレーション機能を提供します。
"""

from __future__ import annotations

from typing import Optional

from config import (
    get_config, on_save, on_mission, on_que, on_check, on_event, 
    on_medal, on_gacha, on_count, on_sell, on_name, on_initial, on_id_check
)
from logging_util import logger, MultiDeviceLogger
from login_operations import device_operation_login
from monst.adb import pull_file_from_nox
from utils.device_utils import get_terminal_number

from .checks import icon_check
from .events import event_do
from .exceptions import LoginError, GachaOperationError, SellOperationError
from .gacha import mon_gacha_shinshun
from .operations import medal_change, mon_initial, mission_get, name_change, mon_sell, orb_count, id_check

def device_operation_select(
    device_port: str,
    folder: str,
    multi_logger: Optional[MultiDeviceLogger] = None,
    **login_kwargs,
) -> bool:
    """デバイス操作のメインエントリーポイント。
    
    設定に基づいて各種操作を順次実行します。
    
    Args:
        device_port: 対象デバイスのポート
        folder: 操作対象のフォルダ名
        multi_logger: マルチデバイスロガー（オプション）
        
    Returns:
        全操作が成功した場合はTrue、失敗した場合はFalse
        
    Raises:
        LoginError: ログインに失敗した場合
        GachaOperationError: ガチャ操作に失敗した場合
        SellOperationError: 売却操作に失敗した場合
        
    Example:
        >>> success = device_operation_select("127.0.0.1:62001", "folder_001")
        >>> if success:
        ...     print("All operations completed successfully")
    """
    try:
        # デバイス健全性チェック（開始前）
        from monst.image.device_management import monitor_device_health
        monitor_device_health([device_port])
        
        # ログイン処理を実行
        if not device_operation_login(device_port, folder, multi_logger, **login_kwargs):
            raise LoginError(f"ログイン失敗 (フォルダ：{folder})")
        
        # ガチャボタン誤作動防止チェック
        from image_detection import tap_if_found
        if tap_if_found('tap', device_port, "gacha_shu.png", "login"):
            tap_if_found('tap', device_port, "zz_home.png", "login")
            tap_if_found('tap', device_port, "zz_home2.png", "login")
            import time
            time.sleep(1)

        found_character: Optional[bool] = None
        
        # 処理結果を記録するリスト
        operations_completed = []
        
        # 各作業を設定に従って実行（config.jsonのフラグ順序で実行）
        if on_que == 1:
            # on_queは別の関数で処理されるため、ここではスキップ
            pass
            
        if on_event == 1:
            if event_do(device_port, folder):
                operations_completed.append("EVENT")
            else:
                operations_completed.append("EVENT_FAIL")
        elif on_event == 2:
            from .events import bakuage_roulette_do
            if bakuage_roulette_do(device_port, folder, multi_logger):
                operations_completed.append("BAKUAGE_ROULETTE")
            else:
                operations_completed.append("BAKUAGE_ROULETTE_FAIL")
        elif on_event == 3:
            # フレンド状況確認処理
            try:
                from .friends import friend_status_check
                if friend_status_check(device_port, folder, multi_logger):
                    operations_completed.append("FRIEND_STATUS_CHECK")
                else:
                    operations_completed.append("FRIEND_STATUS_CHECK_FAIL")
            except Exception as e:
                operations_completed.append("FRIEND_STATUS_CHECK_ERROR")
            
        if on_medal == 1:
            try:
                medal_change(device_port, folder)
                operations_completed.append("MEDAL")
            except Exception as e:
                operations_completed.append("MEDAL_FAIL")
            
        if on_mission == 1:
            try:
                mission_get(device_port, folder)
                operations_completed.append("MISSION")
            except Exception as e:
                operations_completed.append("MISSION_FAIL")
            
        if on_sell == 1:
            try:
                mon_sell(device_port, folder)
                operations_completed.append("SELL")
            except Exception as e:
                operations_completed.append("SELL_FAIL")
            
        if on_initial == 1:
            try:
                mon_initial(device_port, folder)
                operations_completed.append("INITIAL")
            except Exception as e:
                operations_completed.append("INITIAL_FAIL")
            
        if on_name == 1:
            try:
                name_change(device_port, folder)
                operations_completed.append("NAME")
            except Exception as e:
                operations_completed.append("NAME_FAIL")
            
        if on_gacha == 1:
            try:
                config = get_config()
                gacha_limit = config.gacha_limit
                continue_until_character = config.continue_until_character
                found_character = mon_gacha_shinshun(device_port, folder, gacha_limit, multi_logger, continue_until_character=continue_until_character)
                operations_completed.append(f"GACHA({found_character})")
            except Exception as e:
                operations_completed.append("GACHA_FAIL")
                found_character = False
            
        if on_check in [1, 2, 3]:
            try:
                icon_check(device_port, folder)
                operations_completed.append("CHECK")
            except Exception as e:
                operations_completed.append("CHECK_FAIL")
            
        if on_count == 1:
            max_orb_count_retries = 10
            orb_count_success = False
            
            for orb_retry in range(max_orb_count_retries):
                try:
                    if orb_count(device_port, folder, found_character=found_character):
                        orb_count_success = True
                        break
                except Exception as e:
                    pass
                
                if orb_retry < max_orb_count_retries - 1:
                    import time
                    time.sleep(2)
            
            if orb_count_success:
                operations_completed.append("COUNT")
            else:
                operations_completed.append("COUNT_FAIL")
            
        if on_id_check == 1:
            try:
                # フリーズチェック（ID処理前）
                monitor_device_health([device_port])
                
                player_id = id_check(device_port, folder)
                if player_id:
                    operations_completed.append(f"ID_CHECK({player_id})")
                else:
                    operations_completed.append("ID_CHECK_FAIL")
            except Exception as e:
                # エラー時もフリーズ疑いとしてマーク
                from monst.image.device_management import mark_device_error
                mark_device_error(device_port, f"ID_CHECK処理エラー: {e}")
                operations_completed.append("ID_CHECK_FAIL")
        # on_id_check == 0 の場合はIDチェックをスキップ
            
        if on_save == 1:
            try:
                pull_file_from_nox(device_port, folder)
                operations_completed.append("SAVE")
            except Exception as e:
                operations_completed.append("SAVE_FAIL")

        
        # 1行でフォルダ処理結果をログ出力
        ops_summary = " ".join(operations_completed) if operations_completed else "NONE"
        logger.info(f"{get_terminal_number(device_port)}: {folder} [{ops_summary}]")
        
        if multi_logger:
            multi_logger.log_success(device_port)
        return True

    except LoginError as e:
        logger.error(f"{get_terminal_number(device_port)}: {folder} [LOGIN_ERROR]")
        if multi_logger:
            multi_logger.log_error(device_port, str(e))
        if on_save == 1:
            try:
                pull_file_from_nox(device_port, folder)
            except Exception as save_e:
                pass
        return False
    except (GachaOperationError, SellOperationError) as e:
        logger.error(f"{get_terminal_number(device_port)}: {folder} [OPERATION_ERROR]")
        if multi_logger:
            multi_logger.log_error(device_port, str(e))
        if on_save == 1:
            try:
                pull_file_from_nox(device_port, folder)
                pass
            except Exception as save_e:
                pass
        return False
    except Exception as e:
        logger.error(f"{get_terminal_number(device_port)}: {folder} [ERROR]")
        if multi_logger:
            multi_logger.log_error(device_port, str(e))
        if on_save == 1:
            try:
                pull_file_from_nox(device_port, folder)
            except Exception as save_e:
                pass
        return False
