"""
monst.device.events - Event operation functions.

イベント関連の操作機能を提供します。
"""

from __future__ import annotations

import time
import os
from typing import Optional

from logging_util import MultiDeviceLogger
from monst.image.utils import get_image_path
from monst.adb import perform_action
from monst.image import tap_if_found, tap_until_found

from .navigation import home

def event_do(
    device_port: str, 
    folder: str, 
    multi_logger: Optional[MultiDeviceLogger] = None
) -> bool:
    """イベントガチャを実行します。
    
    Args:
        device_port: 対象デバイスのポート
        folder: フォルダ名
        multi_logger: マルチデバイスロガー（オプション）
        
    Returns:
        イベント処理が成功したかどうか
        
    Example:
        >>> success = event_do("127.0.0.1:62001", "folder_001")
    """
    from logging_util import logger
    
    try:
        logger.info(f"デバイス {device_port}: イベント処理を開始します")
        
        if not home(device_port, folder):
            logger.warning(f"デバイス {device_port}: home関数が失敗しましたが、処理を継続します")

        # ガチャアクセスを試みる（短いタイムアウト）
        logger.info(f"デバイス {device_port}: ガチャ画面へのアクセスを試みます")
        
        # まずガチャアクセスを試す（ガチャボタンを探す）
        if not tap_if_found('tap', device_port, "gacha.png", "key"):
            logger.info(f"デバイス {device_port}: ガチャボタンが見つかりません。イベント処理をスキップします。")
            return True  # スキップでも成功として次の処理に進む
        
        time.sleep(2)  # ガチャ画面が読み込まれるまで待機
        
        # イベントガチャが利用できるかチェック
        if tap_if_found('stay', device_port, "sel_A.png", "event"):
            logger.info(f"デバイス {device_port}: イベントガチャが利用可能です。実行します。")
            
            # イベントガチャを実行
            tap_until_found(device_port, "sel2.png", "event", "sel1.png", "event", "tap", "stay", timeout=15)
            
            # イベントタイプ判定とガチャ実行
            if tap_if_found('tap', device_port, "el.png", "event"):
                tap_until_found(device_port, "check.png", "event", "el.png", "event", "tap", "stay", timeout=15)
            elif tap_if_found('tap', device_port, "geki.png", "event"):
                tap_until_found(device_port, "check.png", "event", "geki.png", "event", "tap", "stay", timeout=15)
            elif tap_if_found('tap', device_port, "masa.png", "event"):
                tap_until_found(device_port, "check.png", "event", "masa.png", "event", "tap", "stay", timeout=15)
            else:
                tap_until_found(device_port, "check.png", "event", "vani.png", "event", "tap", "stay", timeout=15)

            # 各色クリック処理
            _perform_color_selection(device_port)
            
            # ガチャ実行
            result = _execute_event_gacha(device_port)
            if result:
                logger.info(f"デバイス {device_port}: イベントガチャが正常に完了しました")
            return result
        else:
            logger.info(f"デバイス {device_port}: イベントガチャが現在利用できません。スキップして次の処理に進みます。")
            return True  # スキップでも成功として次の処理に進む
            
    except Exception as e:
        logger.error(f"デバイス {device_port}: イベント処理中にエラー: {e}")
        return True  # エラーが発生しても次の処理に進む

def _perform_color_selection(device_port: str) -> None:
    """イベントガチャの色選択を実行します。"""
    color_actions = [
        (100, 270, 40, 390),   # 色1
        (160, 270, 40, 390),   # 色2  
        (210, 270, 210, 270),  # 色3（2回クリック）
        (270, 270, 270, 270),  # 色4（2回クリック）
        (320, 270, 120, 330),  # 色5
    ]
    
    for first_tap, first_y, second_x, second_y in color_actions:
        perform_action(device_port, 'tap', first_tap, first_y, duration=150)
        time.sleep(2)
        perform_action(device_port, 'tap', second_x, second_y, duration=150)
        time.sleep(1)

def _execute_event_gacha(device_port: str) -> bool:
    """イベントガチャの実行処理を行います。"""
    from logging_util import logger
    
    try:
        tap_until_found(device_port, "sel21.png", "event", "sel17.png", "event", "tap", "stay", timeout=15)
        tap_until_found(device_port, "sel22.png", "event", "sel21.png", "event", "tap", "stay", timeout=15)
        tap_if_found('tap', device_port, "sel22.png", "event")
        time.sleep(3)
        
        # ガチャ結果画面の処理（タイムアウト付き）
        max_attempts = 30  # 最大60秒でタイムアウト
        for attempt in range(max_attempts):
            if tap_if_found('tap', device_port, "gacha_back.png", "gacha"):
                logger.info(f"デバイス {device_port}: イベントガチャが完了しました")
                return True
            
            tap_if_found('swipe_down', device_port, "tama.png", "key")
            tap_if_found('swipe_down', device_port, "tama2.png", "key")
            perform_action(device_port, 'tap', 50, 170, duration=150)
            time.sleep(2)
        
        logger.warning(f"デバイス {device_port}: イベントガチャの結果画面処理がタイムアウトしました")
        return False
        
    except Exception as e:
        logger.error(f"デバイス {device_port}: イベントガチャ実行中にエラー: {e}")
        return False

def bakuage_roulette_do(
    device_port: str, 
    folder: str, 
    multi_logger: Optional[MultiDeviceLogger] = None
) -> bool:
    """爆獲れルーレット実行処理を行います。
    
    Args:
        device_port: 対象デバイスのポート
        folder: フォルダ名
        multi_logger: マルチデバイスロガー（オプション）
        
    Returns:
        爆獲れルーレット処理が成功したかどうか
    """
    from logging_util import logger
    
    try:
        logger.info(f"デバイス {device_port}: 爆獲れルーレット処理を開始します")
        
        # ①ログイン処理とroom発見（確実にroomが確認できるようにroom発見後3秒後改めてroomを発見）
        from login_operations import device_operation_login
        if not device_operation_login(device_port, folder, multi_logger):
            logger.warning(f"デバイス {device_port}: ログインに失敗しました")
            return False
            
        # room発見後3秒待機して改めてroomを確認
        time.sleep(3)
        if not tap_if_found('stay', device_port, "room.png", "login"):
            logger.warning(f"デバイス {device_port}: room再確認に失敗しました")
            return False
        
        # ②event2_1.pngを探す
        if not tap_if_found('stay', device_port, "event2_1.png", "event"):
            logger.info(f"デバイス {device_port}: event2_1.pngが見つかりません。このフォルダの作業を終了します")
            return True  # 見つからなくても成功として次のフォルダに
        
        # ③event2_1.pngをクリック
        if not tap_if_found('tap', device_port, "event2_1.png", "event"):
            logger.warning(f"デバイス {device_port}: event2_1.pngのクリックに失敗しました")
            return False
            
        # event2_yes.pngが見つかるまでevent2_2.pngとevent2_ok.pngを探してクリック
        # event2_ok.pngを優先
        max_attempts = 30  # 最大試行回数
        for attempt in range(max_attempts):
            if tap_if_found('stay', device_port, "event2_yes.png", "event"):
                break  # event2_yes.pngが見つかったのでループ終了
                
            # event2_ok.pngを優先してクリック
            if tap_if_found('tap', device_port, "event2_ok.png", "event"):
                time.sleep(1)
                continue
                
            # event2_2.pngをクリック
            if tap_if_found('tap', device_port, "event2_2.png", "event"):
                time.sleep(1)
                continue
                
            time.sleep(0.5)  # 短い待機
        else:
            logger.warning(f"デバイス {device_port}: event2_yes.pngが見つかりませんでした")
            return False
        
        # ④event2_3.pngを見つけるまでevent2_yes.pngをクリック
        for attempt in range(max_attempts):
            if tap_if_found('stay', device_port, "event2_3.png", "event"):
                break  # event2_3.pngが見つかったのでループ終了
                
            if tap_if_found('tap', device_port, "event2_yes.png", "event"):
                time.sleep(1)
                continue
                
            time.sleep(0.5)
        else:
            logger.warning(f"デバイス {device_port}: event2_3.pngが見つかりませんでした")
            return False
        
        # event2_3.pngを10秒間押しっぱなし → event2_4.png → event2_yes.pngの処理
        retry_event3_count = 0
        max_event3_retries = 5  # event2_3長押しの最大リトライ回数
        
        while retry_event3_count < max_event3_retries:
            # event2_3.pngを10秒間押しっぱなし
            from monst.image import find_and_tap_image
            x, y = find_and_tap_image(device_port, "event2_3.png", "event")
            if x is not None and y is not None:
                # 10秒間（10000ms）の長押し
                perform_action(device_port, 'tap', x, y, duration=10000)
                logger.info(f"デバイス {device_port}: event2_3.pngを10秒間長押ししました")
            else:
                logger.warning(f"デバイス {device_port}: event2_3.pngが見つからず、長押しに失敗しました")
                return False
            
            time.sleep(1)  # 長押し後の待機
            
            # event2_ok.pngが出た場合は再度event2_3長押しからやり直し
            if tap_if_found('stay', device_port, "event2_ok.png", "event"):
                logger.info(f"デバイス {device_port}: event2_ok.pngが表示されました。event2_ok.pngをクリックして再トライします")
                if tap_if_found('tap', device_port, "event2_ok.png", "event"):
                    retry_event3_count += 1
                    time.sleep(1)
                    continue  # event2_3長押しからやり直し
                else:
                    logger.warning(f"デバイス {device_port}: event2_ok.pngのクリックに失敗しました")
                    return False
            
            # ⑤event2_4.pngを押してevent2_yes.pngを押す
            if tap_if_found('tap', device_port, "event2_4.png", "event"):
                time.sleep(1)
                
                # event2_4.png押下後にevent2_ok.pngが出た場合は再度event2_3長押しからやり直し
                if tap_if_found('stay', device_port, "event2_ok.png", "event"):
                    logger.info(f"デバイス {device_port}: event2_4.png押下後にevent2_ok.pngが表示されました。event2_ok.pngをクリックして再トライします")
                    if tap_if_found('tap', device_port, "event2_ok.png", "event"):
                        retry_event3_count += 1
                        time.sleep(1)
                        continue  # event2_3長押しからやり直し
                    else:
                        logger.warning(f"デバイス {device_port}: event2_ok.pngのクリックに失敗しました")
                        return False
                
                # event2_yes.pngが出た場合は成功
                if tap_if_found('tap', device_port, "event2_yes.png", "event"):
                    logger.info(f"デバイス {device_port}: event2_4.png → event2_yes.pngの処理が成功しました")
                    break  # 成功したのでループを抜ける
                else:
                    logger.warning(f"デバイス {device_port}: event2_4.png後のevent2_yes.pngクリックに失敗しました")
                    return False
            else:
                logger.warning(f"デバイス {device_port}: event2_4.pngのクリックに失敗しました")
                return False
                
        else:
            logger.warning(f"デバイス {device_port}: event2_3長押し処理が最大リトライ回数に達しました")
            return False
        
        # ⑥event2_5.pngを押してevent2_yes.pngを押す
        if tap_if_found('tap', device_port, "event2_5.png", "event"):
            time.sleep(1)
            if not tap_if_found('tap', device_port, "event2_yes.png", "event"):
                logger.warning(f"デバイス {device_port}: event2_5.png後のevent2_yes.pngクリックに失敗しました")
                return False
        else:
            logger.warning(f"デバイス {device_port}: event2_5.pngのクリックに失敗しました")
            return False
        
        # ⑦event2_okを見つけてクリックできるまで再トライ
        for attempt in range(max_attempts):
            if tap_if_found('tap', device_port, "event2_ok.png", "event"):
                logger.info(f"デバイス {device_port}: 爆獲れルーレット処理が完了しました")
                return True
            time.sleep(0.5)  # 短い待機
        else:
            logger.warning(f"デバイス {device_port}: 最終のevent2_okクリックに失敗しました")
            return False
        
    except Exception as e:
        logger.error(f"デバイス {device_port}: 爆獲れルーレット処理中にエラー: {e}")
        return False

def event4_menu_do(
    device_port: str,
    folder: str,
    multi_logger: Optional[MultiDeviceLogger] = None,
) -> bool:
    """Handle the custom Event 4 menu flow."""
    from logging_util import logger

    logger.info(f"[EVENT4] Device {device_port}: start processing (folder={folder})")

    # ev4_start.png だけを確実に検知する（event4_start.png は存在しない）
    start_candidates = ("ev4_start.png",)
    start_found = False
    max_start_wait = 30  # seconds
    start_poll_interval = 1.0
    start_time = time.time()
    attempt = 0

    # 事前にパス存在を確認してログ出力（パス問題の切り分け用）
    start_path = get_image_path("ev4_start.png", "event4")
    if start_path:
        exists = os.path.exists(start_path)
        logger.info(f"[EVENT4] start image path: {start_path} (exists={exists})")

    while time.time() - start_time < max_start_wait:
        attempt += 1
        found_this_round = False
        for image in start_candidates:
            # 強制リフレッシュで見落としを防ぐ（ログイン直後の重要検知）
            if tap_if_found("tap", device_port, image, "event4", cache_time=0, threshold=0.70):
                start_found = True
                found_this_round = True
                logger.info(f"[EVENT4] Device {device_port}: tapped start button {image}")
                time.sleep(1.0)
                break
        if start_found:
            break
        logger.info(
            f"[EVENT4] Device {device_port}: ev4_start polling attempt {attempt} -> found={found_this_round}"
        )
        time.sleep(start_poll_interval)

    if not start_found:
        logger.info(f"[EVENT4] Device {device_port}: start image missing, skip folder")
        return True

    action_sequence = [
        ("ev4_2.png", "tap"),
        ("ev4_3.png", "tap"),
        ("ev4_4.png", "swipe_down"),
        ("ev4_5.png", "tap"),
        ("ev4_6.png", "tap"),
        ("ev4_7.png", "tap"),
        ("ev4_8.png", "tap"),
        ("ev4_9.png", "swipe_down"),
        ("ev4_start.png", "tap"),
    ]
    end_candidates = ("ev4_end.png",)

    start_time = time.time()
    max_duration = 180

    while time.time() - start_time < max_duration:
        for end_image in end_candidates:
            if tap_if_found("tap", device_port, end_image, "event4"):
                logger.info(f"[EVENT4] Device {device_port}: detected end image {end_image}")
                return True

        action_executed = False
        for image_name, action in action_sequence:
            if tap_if_found(action, device_port, image_name, "event4"):
                action_executed = True
                if image_name == "ev4_4.png":
                    logger.info(f"[EVENT4] Device {device_port}: swipe-down action executed")
                else:
                    logger.debug(f"[EVENT4] Device {device_port}: handled {image_name}")
                time.sleep(0.8)
                break

        if not action_executed:
            logger.info(f"[EVENT4] Device {device_port}: fallback tap at safe position")
            perform_action(device_port, "tap", 40, 180, duration=150)
            time.sleep(1.0)

    logger.warning(f"[EVENT4] Device {device_port}: timed out during menu processing")
    return False
