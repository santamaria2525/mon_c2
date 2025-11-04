"""
フレンド状況確認モジュール

フレンド状況確認処理を実装します：
1. ログイン処理（room発見まで、3秒後再確認）
2. UI順序: friends.png → friends_syotai.png → friends_ok → friend_hosyu
3. friend_2nin検出と結果ログ出力
"""

import time
from typing import Optional
from logging_util import logger, MultiDeviceLogger
from utils.device_utils import get_terminal_number
from login_operations import device_operation_login


def friend_status_check(
    device_port: str, 
    folder: str, 
    multi_logger: Optional[MultiDeviceLogger] = None
) -> bool:
    """
    フレンド状況確認処理を実行
    
    Args:
        device_port: デバイスポート
        folder: フォルダ名
        multi_logger: マルチデバイスロガー
        
    Returns:
        bool: 処理が正常に完了した場合はTrue
    """
    terminal_num = get_terminal_number(device_port)
    
    try:
        # ①ログイン処理 - room発見まで確実にログイン
        if not _login_with_room_verification(device_port, folder, multi_logger):
            logger.error(f"{terminal_num}: ログイン処理失敗")
            return False
        
        # ②UI操作シーケンス実行（friend_hosyuend.png検出まで）
        if not _execute_friend_ui_sequence(device_port):
            logger.error(f"{terminal_num}: フレンドUI操作失敗")
            return False
        
        # ③friend_hosyuend.png発見後にfriend_2nin検出と結果判定
        result = _check_friend_2nin_status(device_port, folder)
        
        return True
        
    except Exception as e:
        print(f"❌ フォルダ{folder}: フレンド状況確認失敗 ({e})")
        return False


def _login_with_room_verification(
    device_port: str,
    folder: str,
    multi_logger: Optional[MultiDeviceLogger] = None
) -> bool:
    """
    room.pngを基準に端末のログイン完了を判断する。

    手順:
      1. room.pngを検出したらui/obuclear.pngを探し、見つかればタップする。
      2. room.pngが見つからない場合はログイン処理を継続する。
      3. obuclear.pngが存在しない状態でroom.pngを2回連続で検出したら終了。
    """
    terminal_num = get_terminal_number(device_port)

    from image_detection import tap_if_found

    max_login_attempts = 5
    max_idle_checks = 12

    login_attempts = 0
    idle_checks = 0
    needs_login = True
    room_without_obuclear_seen = False

    while login_attempts < max_login_attempts:
        if needs_login:
            if not device_operation_login(device_port, folder, multi_logger):
                logger.error(f"{terminal_num}: device_operation_login failed during room verification")
                return False
            login_attempts += 1
            needs_login = False
            room_without_obuclear_seen = False
            idle_checks = 0
            time.sleep(1.0)
        else:
            idle_checks += 1
            if idle_checks > max_idle_checks:
                logger.debug(f"{terminal_num}: retrying login because room confirmation is taking too long")
                needs_login = True
                idle_checks = 0
                continue
            time.sleep(0.5)

        room_visible = tap_if_found('stay', device_port, "room.png", "login")
        if not room_visible:
            logger.info(f"{terminal_num}: room.png not detected, continuing login flow")
            needs_login = True
            room_without_obuclear_seen = False
            time.sleep(1.0)
            continue

        idle_checks = 0

        if tap_if_found('tap', device_port, "obuclear.png", "ui"):
            logger.info(f"{terminal_num}: obuclear.png detected and tapped")
            room_without_obuclear_seen = False
            time.sleep(1.0)
            continue

        if room_without_obuclear_seen:
            logger.info(f"{terminal_num}: room confirmed without obuclear twice, finishing")
            return True

        room_without_obuclear_seen = True
        logger.info(f"{terminal_num}: room detected without obuclear, waiting for second confirmation")
        time.sleep(1.5)

    logger.warning(f"{terminal_num}: failed to confirm room without obuclear within retry limit")
    return False


def _execute_friend_ui_sequence(device_port: str) -> bool:
    """
    フレンドUI操作シーケンスを実行
    
    UI順序: friends.png → friends_syotai.png → friends_ok → friend_hosyu
    friend_hosyuend.pngが見つかるまで繰り返し実行
    
    Args:
        device_port: デバイスポート
        
    Returns:
        bool: UI操作が成功した場合はTrue
    """
    terminal_num = get_terminal_number(device_port)
    
    try:
        from image_detection import tap_if_found
        
        # UI操作シーケンス定義
        ui_targets = [
            "friends.png",
            "friends_syotai.png", 
            "friends_ok.png",
            "friend_hosyu.png"
        ]
        
        max_total_attempts = 100  # 全体の最大試行回数
        
        for attempt in range(max_total_attempts):
            # friend_hosyuend.pngが見つかったら完了
            if tap_if_found('stay', device_port, "friend_hosyuend.png", "ui"):
                return True
            
            # 各UI要素を探してタップ
            for ui_target in ui_targets:
                if tap_if_found('tap', device_port, ui_target, "ui"):
                    # friend_hosyuは長めの待機、それ以外は短い待機
                    wait_time = 1.0 if ui_target == "friend_hosyu.png" else 0.3
                    time.sleep(wait_time)
                    break  # 1つ見つかったら次のループへ
            
            time.sleep(0.2)  # 次の試行まで短い待機
        
        # 最大試行回数に達した場合は失敗
        logger.error(f"{terminal_num}: friend_hosyuend.png検出に失敗（最大試行回数到達）")
        return False
        
    except Exception as e:
        logger.error(f"{terminal_num}: フレンドUI操作エラー: {e}")
        return False


def _check_friend_2nin_status(device_port: str, folder: str) -> bool:
    """
    friend_hosyuend.png検出後にfriend_2nin画像を検出して結果を判定
    
    Args:
        device_port: デバイスポート
        folder: フォルダ名
        
    Returns:
        bool: friend_2ninが検出された場合はTrue
    """
    try:
        from image_detection import tap_if_found
        
        # friend_2nin検出試行
        if tap_if_found('stay', device_port, "friend_2nin.png", "ui"):
            print(f"✅ フォルダ{folder}: フレンド状況確認成功")
            return True
        else:
            print(f"❌ フォルダ{folder}: フレンド状況確認失敗 (friend_2nin未検出)")
            return False
            
    except Exception as e:
        print(f"❌ フォルダ{folder}: フレンド状況確認失敗 ({e})")
        return False
