"""
monst.device.operations - 各種デバイス操作機能

このモジュールは、モンスターストライクの自動化に必要な
さまざまなデバイス操作機能を提供します。

主な機能:
- メダル処理操作
- ミッション取得処理
- オーブカウント機能
- アカウント名読み取り
- エラーハンドリングと回復処理

各関数は再利用可能で、マルチデバイス環境での動作を前提として設計されています。
"""

from __future__ import annotations

import time
import os
import pyperclip
from typing import List, Optional, Tuple
from PIL import Image
import cv2
import numpy as np

from config import name_prefix
from logging_util import logger, MultiDeviceLogger
from login_operations import handle_screens
from monst.adb import perform_action, send_key_event
from monst.image import (
    tap_if_found, tap_until_found, type_folder_name, find_image_count,
    read_orb_count, read_account_name, save_account_name_image, save_orb_count_image,
    save_character_ownership_image, is_ocr_available
)
from utils.data_persistence import update_excel_data, update_orb_player_id

from .navigation import home

def medal_change(
    device_port: str, 
    folder: str, 
    multi_logger: Optional[MultiDeviceLogger] = None
) -> None:
    """メダル交換処理を実行します
    
    指定されたデバイスでメダル交換画面に移動し、
    必要な操作を実行してメダル処理を完了します。
    
    Args:
        device_port: 対象デバイスのポート番号
        folder: 処理対象のフォルダ名
        multi_logger: マルチデバイス用ロガー（オプション）
        
    Note:
        この関数は画面遷移エラーに対する自動回復機能を含みます。
    """
    home(device_port, folder)

    tap_until_found(device_port, "monbox.png", "key", "monster.png", "key", "tap")
    while not tap_if_found('tap', device_port, "hikikae1.png", "key"):
        perform_action(device_port, 'swipe', 100, 500, 100, 400, duration=300)
    time.sleep(1)
    tap_if_found('tap', device_port, "hikikae1.png", "key")
    tap_until_found(device_port, "medal1.png", "key", "ok_2.png", "key", "tap", "tap")
    tap_until_found(device_port, "medal2.png", "key", "ok_2.png", "key", "tap", "tap")
    while not (tap_if_found('tap', device_port, "hikikae_p.png", "key") or tap_if_found('tap', device_port, "medal_fusoku.png", "key")):
        tap_if_found('tap', device_port, "hikikae_g.png", "key")        
    time.sleep(1)
    tap_if_found('tap', device_port, "hikikae_p.png", "key")
    tap_if_found('tap', device_port, "hikikae_p.png", "key")
    tap_if_found('tap', device_port, "hikikae_p.png", "key")
    tap_if_found('tap', device_port, "hikikae_p.png", "key")
    tap_if_found('tap', device_port, "hikikae_p.png", "key")
    tap_if_found('tap', device_port, "hikikae_p.png", "key")
    tap_if_found('tap', device_port, "yes.png", "key")
    time.sleep(1)
    tap_if_found('tap', device_port, "ok_2.png", "key")

def mon_initial(
    device_port: str, 
    folder: str, 
    multi_logger: Optional[MultiDeviceLogger] = None
) -> None:
    """旧mon6準拠の初期設定処理を実行する。"""
    home(device_port, folder)

    tap_until_found(device_port, "option.png", "key", "sonota.png", "key", "tap")
    tap_until_found(device_port, "waku.png", "key", "option.png", "key", "tap")
    time.sleep(1)

    # サウンド設定などをすべてOFFにする
    while not tap_if_found('stay', device_port, "op_end.png", "key"):
        tap_if_found('swipe_up', device_port, "waku.png", "key")
        time.sleep(1)
        for _ in range(3):
            tap_if_found('tap', device_port, "off.png", "key")

    # ニックネーム変更画面まで戻る
    while not tap_if_found('stay', device_port, "nicname.png", "key"):
        tap_if_found('swipe_down', device_port, "waku.png", "key")
        for _ in range(3):
            tap_if_found('tap', device_port, "off.png", "key")

    tap_until_found(device_port, "name_hen.png", "key", "name_ok.png", "key", "tap")
    tap_until_found(device_port, "name_ok.png", "key", "name_ok2.png", "key", "tap")
    tap_until_found(device_port, "zz_home.png", "key", "zz_home2.png", "key", "tap")

def mission_get(
    device_port: str,
    folder: str,
    multi_logger: Optional[MultiDeviceLogger] = None
) -> None:
    """セレクトメニュー用の簡易ミッション受取処理"""
    # Step2: m_mission_bが見えるまでm_missionをタップ
    for _ in range(40):
        if tap_if_found('stay', device_port, "m_mission_b.png", "mission"):
            break
        tap_if_found('tap', device_port, "m_mission.png", "mission")
        handle_screens(device_port, "mission")
        time.sleep(0.4)

    # Step3: m_tujoを最低1度クリック
    tujo_clicked = False
    for _ in range(40):
        if tap_if_found('stay', device_port, "m_tujo.png", "mission"):
            tap_if_found('tap', device_port, "m_tujo.png", "mission")
            time.sleep(0.5)
            tap_if_found('tap', device_port, "m_tujo.png", "mission")
            tujo_clicked = True
            break
        handle_screens(device_port, "mission")
        time.sleep(0.4)
    if not tujo_clicked:
        logger.warning("%s: m_tujoを検出できませんでした", device_port)

    # Step4: m_tujofin1個 + m_mitatsu3個が揃うまで受取処理を継続
    while True:
        mitatsu_ready = find_image_count(device_port, "m_mitatsu.png", 3, 0.8, "mission")
        tujo_ready = tap_if_found('stay', device_port, "m_tujofin.png", "mission") or tap_if_found('stay', device_port, "m_tujofin2.png", "mission")
        if mitatsu_ready and tujo_ready:
            break
        progressed = tap_if_found('tap', device_port, "ikkatu.png", "mission")
        progressed = tap_if_found('tap', device_port, "m_ok.png", "mission") or progressed
        if not progressed:
            handle_screens(device_port, "mission")
        time.sleep(0.4)

    tap_if_found('tap', device_port, "zz_home.png", "key")


def _wait_for_room_ready(device_port: str, timeout: float = 60.0) -> bool:
    """roomアイコンを2回連続で検知したらログイン完了とみなす。"""
    start = time.time()
    while time.time() - start < timeout:
        if tap_if_found('stay', device_port, "room.png", "key"):
            time.sleep(1.5)
            if tap_if_found('stay', device_port, "room.png", "key"):
                return True
        time.sleep(0.5)
    logger.warning("%s: roomを検知できずログイン確認に失敗", device_port)
    return False
    

def name_change(
    device_port: str, 
    folder: str, 
    multi_logger: Optional[MultiDeviceLogger] = None
) -> None:
    """名前変更処理を実行します。
    
    Args:
        device_port: 対象デバイスのポート
        folder: フォルダ名
        multi_logger: マルチデバイスロガー（オプション）
    """
    home(device_port, folder)

    tap_until_found(device_port, "option.png", "key", "sonota.png", "key", "tap")
    tap_until_found(device_port, "waku.png", "key", "option.png", "key", "tap")
    time.sleep(1)
    tap_if_found('tap', device_port, "name.png", "key")
    time.sleep(1)
    
    # バックスペースでクリア
    send_key_event(device_port, key_event=67, times=8)
    
    # name_prefix + folder の組み合わせでテキスト入力
    combined_name = name_prefix + folder
    send_key_event(device_port, text=combined_name)
    
    # Enterで確定
    send_key_event(device_port, key_event=66)
    tap_if_found('tap', device_port, "name_ok.png", "key")
    time.sleep(1)
    tap_if_found('tap', device_port, "name_ok2.png", "key")

def id_check(
    device_port: str, 
    folder: str, 
    multi_logger: Optional[MultiDeviceLogger] = None
) -> str:
    """ID確認処理を実行します。
    
    Args:
        device_port: 対象デバイスのポート
        folder: フォルダ名
        multi_logger: マルチデバイスロガー（オプション）
        
    Returns:
        読み取ったIDまたは空文字列
    """
    try:
        # ①ホームボタンを押してホームに戻る
        from monst.image import home
        home(device_port, folder)
        time.sleep(2)
        
        # ②friends_searchが見つかるまでfriendsを押し続ける
        tap_until_found(device_port, "friends_search.png", "ui", "friends.png", "ui", "tap")
        time.sleep(2)
        
        # ③friends_noが表示されるまでfriends_searchを押し続ける
        tap_until_found(device_port, "friends_no.png", "ui", "friends_search.png", "ui", "tap")
        time.sleep(2)
        
        # ④指定座標でスクリーンショットを撮影してID画像を保存
        id_image_path = _capture_and_save_id_image(device_port, folder)
        
        if not id_image_path:
            logger.warning("ID画像保存に失敗しました")
        
        # ⑤friends_copy.pngを検索してクリック（IDをクリップボードにコピー）
        copied_id = _click_friends_copy_and_get_id_safe(device_port, folder)
        
        # ID画像が取得できた場合、専用Excelに保存
        if id_image_path:
            try:
                from utils.id_check_persistence import save_id_check_data_with_id
                result = save_id_check_data_with_id(folder, id_image_path, copied_id)
                if not result:
                    logger.error(f"❌ ID確認Excel保存が失敗しました")
            except Exception as e:
                logger.error(f"❌ ID確認Excel保存エラー: {e}", exc_info=True)
        else:
            logger.warning("⚠️ ID画像が取得できないため、Excel保存をスキップします")

        if copied_id:
            try:
                update_orb_player_id("orb_data.xlsx", folder, copied_id)
            except Exception as e:
                logger.error(f"orbデータへのID追記に失敗しました: {e}")
        
        return "ID_CHECK_COMPLETED" if id_image_path else "ID_CHECK_FAILED"
        
    except Exception as e:
        logger.error(f"ID確認処理中にエラー: {e}")
        return "ID_CHECK_ERROR"

def _capture_and_save_id_image(device_port: str, folder: str) -> str:
    """指定座標でスクリーンショットを撮影し、ID部分の画像を保存します。
    
    Args:
        device_port: デバイスポート
        folder: フォルダ名
        
    Returns:
        str: 保存した画像パス（失敗時は空文字列）
    """
    try:
        # スクリーンショットを撮影
        from monst.adb import run_adb_command
        screenshot_path = f"temp_id_screenshot_{folder}.png"
        
        result = run_adb_command(["shell", "screencap", "/sdcard/screenshot.png"], device_port)
        if result is None:
            logger.error("スクリーンショット撮影に失敗")
            return ""
        
        # スクリーンショットをPCに転送
        result = run_adb_command(["pull", "/sdcard/screenshot.png", screenshot_path], device_port)
        if result is None:
            logger.error("スクリーンショット転送に失敗")
            return ""
        
        # 画像を読み込み、指定領域を切り取り
        image = cv2.imread(screenshot_path)
        if image is None:
            logger.error("画像読み込みに失敗")
            return ""
        
        # 座標範囲で画像を切り取り (108:395, 255:415の範囲)  
        # OpenCVは[y:y+h, x:x+w]の順序
        height, width = image.shape[:2]
        
        # 座標の妥当性をチェック
        x1, y1, x2, y2 = 108, 395, 255, 415
        if y2 > height or x2 > width:
            logger.error(f"座標が画像範囲外: ({x1},{y1})-({x2},{y2}), 画像サイズ: {width}x{height}")
            return ""
            
        cropped = image[y1:y2, x1:x2]
        
        # 切り取った画像を保存（ID画像として保存）
        save_dir = os.path.join("orb_images", folder)
        os.makedirs(save_dir, exist_ok=True)
        
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        id_filename = f"id_{timestamp}.png"
        id_filepath = os.path.join(save_dir, id_filename)
        cv2.imwrite(id_filepath, cropped)
        
        # 一時ファイルを削除
        try:
            os.remove(screenshot_path)
        except:
            pass
            
        return id_filepath
        
    except Exception as e:
        logger.error(f"ID画像保存処理でエラー: {e}")
        return ""

def mon_sell(
    device_port: str, 
    folder: str, 
    multi_logger: Optional[MultiDeviceLogger] = None
) -> bool:
    """モンスター売却処理を実行します。
    
    Args:
        device_port: 対象デバイスのポート
        folder: フォルダ名
        multi_logger: マルチデバイスロガー（オプション）
        
    Returns:
        売却処理が成功したかどうか
    """
    home(device_port, folder)

    tap_until_found(device_port, "monbox.png", "key", "monster.png", "key", "tap")
    tap_until_found(device_port, "sell.png", "key", "monbox.png", "key", "swipe_up", "tap", timeout=30)

    sell_operations: List[Tuple[str, str]] = [("l4check.png", "pre.png"), ("l5check.png", "sonota.png")]
    for level_check_img, category_img in sell_operations:
        if not perform_monster_sell(device_port, level_check_img, category_img):
            raise SellOperationError(f"売却処理失敗: {level_check_img}")

    if multi_logger:
        multi_logger.log_success(device_port)
    return True

def perform_monster_sell(device_port: str, level_check_img: str, category_img: str) -> bool:
    """モンスター売却の実行処理"""
    max_attempts: int = 8
    for _ in range(max_attempts):
        while not tap_if_found('stay', device_port, "sentaku.png", "sell"):
            tap_if_found('tap', device_port, "ikkatsu.png", "sell")
            tap_if_found('tap', device_port, "ok2.png", "sell")
            time.sleep(1)

        while not tap_if_found('stay', device_port, level_check_img, "sell"):
            tap_if_found('tap', device_port, "l4.png" if level_check_img == "l4check.png" else "l5.png", "sell")
            tap_if_found('tap', device_port, category_img, "sell")

        if tap_until_found(device_port, "kakunin.png", "sell", "kakunin.png", "sell", "stay", "tap", timeout=10):
            time.sleep(1)
            if tap_if_found('stay', device_port, "jogen.png", "sell"):
                tap_if_found('tap', device_port, "ok2.png", "sell")
            tap_until_found(device_port, "ok.png", "sell", "ok.png", "sell", "stay", "tap", timeout=10)
            
            while not tap_if_found('stay', device_port, "off.png", "sell"):
                for img in ["yes.png", "yes2.png", "yes3.png"]:
                    tap_if_found('tap', device_port, img, "sell")
                time.sleep(2)

        if tap_if_found('stay', device_port, "end.png", "sell"):
            tap_if_found('tap', device_port, "ok2.png", "sell")
            return True

    return False

def orb_count(
    device_port: str, 
    folder: str, 
    found_character: Optional[bool], 
    multi_logger: Optional[MultiDeviceLogger] = None
) -> bool:
    """オーブ数カウント処理を実行します（効率化版）
    
    ホーム画面でアカウント名とオーブ数を読み取り、
    エクセルファイルに結果を記録します。複数回の試行により
    OCR精度を向上させています。
    
    Args:
        device_port: 対象デバイスのポート番号
        folder: 処理対象のフォルダ名
        found_character: ガチャでキャラクターを獲得した場合True
        multi_logger: マルチデバイス用ロガー（オプション）
        
    Returns:
        bool: オーブカウント処理が成功した場合True
        
    Note:
        - OCR処理は複数回試行して精度を向上
        - 失敗時は自動的にリトライを実行
        - 結果はエクセルファイルとログに記録
    """
    
    # 短時間待機で画面を安定化
    time.sleep(0.5)
    
    # アカウント名を読み取り
    account_name = read_account_name(device_port)
    
    # 画像を保存
    account_image_path = save_account_name_image(device_port, folder)
    orb_image_path = save_orb_count_image(device_port, folder)
    character_ownership_image_path = save_character_ownership_image(device_port, folder)

    if not is_ocr_available():
        logger.warning("Tesseract OCR が利用できないためオーブ数の自動読み取りをスキップします。")
        if multi_logger:
            multi_logger.log_error(device_port, "Tesseract OCR not available")
        return False

    # オーブ読み取り（最大10回試行）
    max_retries = 10
    
    for retry in range(max_retries):
        try:
            orbs = read_orb_count(device_port, folder)
            
            if orbs is not None:
                # Excelに記録
                excel_success = update_excel_data(
                    "orb_data.xlsx",
                    folder,
                    orbs,
                    found_character,
                    account_name,
                    account_image_path,
                    orb_image_path,
                    character_ownership_image=character_ownership_image_path,
                )
                
                if excel_success:
                    if multi_logger:
                        multi_logger.log_success(device_port)
                    account_info = f" ({account_name})" if account_name else ""
                    logger.info(f"● {folder}: {orbs}オーブ{account_info}")
                    return True
                else:
                    # Excel保存失敗時もリトライ
                    if retry < max_retries - 1:
                        time.sleep(2)
                    continue
                
        except Exception:
            pass
        
        # 失敗時は待機時間を段階的に増加
        if retry < max_retries - 1:
            wait_time = min(2 + retry * 0.5, 5)  # 2秒から最大5秒まで段階的に増加
            time.sleep(wait_time)

    # 最終的に失敗した場合はFalseを返す
    logger.error(f"● {folder}: オーブ読み取り失敗")
    return False

def _click_friends_copy_and_get_id_safe(device_port: str, folder: str) -> str:
    """排他制御付きでfriends_copy.pngを検索してクリックし、IDを安全に取得します。
    
    Args:
        device_port: デバイスポート
        folder: フォルダ名（ログ用）
        
    Returns:
        str: クリップボードから取得したID（失敗時は空文字列）
    """
    try:
        from utils.clipboard_manager import copy_id_with_exclusive_access
        
        def copy_action():
            """コピー操作を実行する内部関数"""
            try:
                # friends_copy.pngを検索してクリック
                if tap_if_found('tap', device_port, "friends_copy.png", "ui"):
                    logger.info(f"📋 {device_port}({folder}): friends_copy.pngをクリックしました")
                    return True
                else:
                    logger.warning(f"📋 {device_port}({folder}): friends_copy.pngが見つかりませんでした")
                    return False
            except Exception as e:
                logger.error(f"📋 {device_port}({folder}): コピー操作エラー: {e}")
                return False
        
        # 排他制御付きでIDコピーを実行
        extracted_id = copy_id_with_exclusive_access(device_port, copy_action)
        
        if extracted_id:
            # ID取得成功
            return extracted_id
        else:
            logger.error(f"📋 {device_port}({folder}): ID取得失敗")
            return ""
            
    except Exception as e:
        logger.error(f"📋 {device_port}({folder}): ID取得処理でエラー: {e}")
        return ""

def _click_friends_copy_and_get_id(device_port: str) -> str:
    """レガシー関数（互換性維持用）"""
    return _click_friends_copy_and_get_id_safe(device_port, "---")
