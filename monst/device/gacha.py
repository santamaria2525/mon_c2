"""
monst.device.gacha - Gacha operation functions.

ガチャ関連の操作機能を提供します。
"""

from __future__ import annotations

import os
import time
from typing import List, Optional, Tuple

import cv2
import numpy as np

# デバイス別のownership_screenshotパスを保存する辞書（ガチャ実行前の処理のみで使用）
_device_ownership_screenshot_paths = {}

from logging_util import logger, MultiDeviceLogger
from monst.adb import perform_action
from monst.image import (
    tap_if_found, tap_until_found, get_device_screenshot,
    save_character_ownership_image, read_account_name, save_account_name_image, 
    save_orb_count_image, read_orb_count
)
from utils import get_resource_path, update_excel_data
from utils.device_utils import get_terminal_number, get_terminal_number_only
from config import get_config

from .navigation import home


def _check_green_text_in_region(device_port: str) -> bool:
    """指定範囲内で緑文字をチェック（連続検出による確認）"""
    try:
        # 複数回チェックして誤検出を減らす
        detection_count = 0
        check_attempts = 3
        
        for i in range(check_attempts):
            screenshot = get_device_screenshot(device_port, cache_time=0.5, force_refresh=True)
            if screenshot is None:
                continue
                
            # 指定された範囲
            x1, x2, y1, y2 = 12, 200, 480, 580
            h, w = screenshot.shape[:2]
            
            # 座標範囲チェック
            if y1 < 0 or y2 > h or x1 < 0 or x2 > w or y1 >= y2 or x1 >= x2:
                continue
                
            # 指定領域を切り出し
            region = screenshot[y1:y2, x1:x2]
            
            # 緑色文字の検出
            if _detect_green_text(region):
                detection_count += 1
                
            # 短時間の間隔を空けて再検出
            if i < check_attempts - 1:
                time.sleep(0.3)
        
        # 2回以上検出されたら真の所持と判定
        required_detections = 2
        is_detected = detection_count >= required_detections
        
        logger.info(f"緑文字検出結果: {detection_count}/{check_attempts} 回検出 -> {is_detected}")
        return is_detected
        
    except Exception as e:
        logger.error(f"緑文字チェック中にエラー: {e}")
        return False

def mon_gacha_shinshun(
    device_port: str, 
    folder: str, 
    gacha_limit: int = 16, 
    multi_logger: Optional[MultiDeviceLogger] = None,
    continue_until_character: bool = False
) -> bool:
    """完全なガチャ実行関数（ultrathink完全版）
    
    所持確認の誤動作とキャラ獲得の誤認識を完全に排除した版です。
    
    Args:
        device_port: 対象デバイスのポート
        folder: フォルダ名
        gacha_limit: ガチャ実行回数の上限
        multi_logger: マルチデバイスロガー（オプション）
        continue_until_character: キャラが出るまで続けるかどうか
        
    Returns:
        キャラクターを獲得したかどうか
        
    Example:
        >>> found = mon_gacha_shinshun("127.0.0.1:62001", "folder_001", 16, continue_until_character=True)
        >>> if found:
        ...     print("キャラクター獲得!")
    """
    # 完全版ガチャシステムに委譲
    from .gacha_perfect import execute_perfect_gacha
    
    terminal_num = get_terminal_number(device_port)
    logger.info(f"{terminal_num}: ultrathink完全版ガチャシステム実行開始")
    
    try:
        result = execute_perfect_gacha(
            device_port=device_port,
            folder=folder,
            gacha_limit=gacha_limit,
            continue_until_character=continue_until_character
        )
        
        if result:
            logger.info(f"{terminal_num}: ガチャ処理成功")
        else:
            logger.warning(f"{terminal_num}: ガチャ処理失敗")
            
        return result
        
    except Exception as e:
        logger.error(f"{terminal_num}: 完全版ガチャシステムエラー: {e}")
        return False


# === 既存補助関数（下位互換性のため保持） ===

def _check_character_acquisition(device_port: str) -> bool:
    """キャラクター獲得の判定を行います。"""
    if tap_if_found('stay', device_port, "01_hoshi_sentaku.png", "hoshi"):
        time.sleep(6)
        while not tap_if_found('stay', device_port, "shinshun_zenshin.png", "end"):
            for img_file in sorted(os.listdir(get_resource_path("hoshi", "gazo"))):
                # 02_hoshi_icon.pngは星玉検知後の選択画面でのみクリック
                if img_file == "02_hoshi_icon.png":
                    # hoshi_tamaまたはhoshi_tama2が先に検知されている場合のみクリック
                    if (tap_if_found('stay', device_port, "hoshi_tama.png", "gacha") or 
                        tap_if_found('stay', device_port, "hoshi_tama2.png", "gacha")):
                        tap_if_found('tap', device_port, img_file, "hoshi")
                else:
                    tap_if_found('tap', device_port, img_file, "hoshi")
                time.sleep(1)
        return True
    
    character_images: List[str] = ["shinshun_icon.png", "shinshun_zenshin.png", "syoji1.png", "syoji2.png"]
    return any(tap_if_found('stay', device_port, img, "end") for img in character_images)

def _check_gacha_available(device_port: str) -> bool:
    """ガチャが実行可能かチェック（オーブ切れなど）。"""
    if tap_if_found('stay', device_port, "empty.png", "end"):
        return False
    return True

def _execute_simple_gacha_action(device_port: str) -> bool:
    """シンプルなガチャ実行。成功したらTrueを返す"""
    # まず10renボタンを優先的に探す
    if tap_if_found('tap', device_port, "10ren.png", "gacha"):
        time.sleep(2)  # ガチャアニメーション待機
        
        # 10renクリック後に緑文字チェック
        if _check_green_text_in_region(device_port):
            return "character_found"  # 特別な戻り値でキャラ獲得を示す
        
        return True
    
    # 10renが見つからない場合、直接10renボタンを再検索
    if tap_if_found('tap', device_port, "10ren.png", "gacha"):
        time.sleep(2)  # ガチャアニメーション待機
        
        # 10renクリック後に緑文字チェック
        if _check_green_text_in_region(device_port):
            return "character_found"  # 特別な戻り値でキャラ獲得を示す
        
        return True
    
    # 10renが見つからない場合、gacharuボタンを試す
    if tap_if_found('stay', device_port, "gacharu.png", "end"):
        # gacharuをクリックする前に緑文字チェック
        if _check_green_text_in_region(device_port):
            return "character_found"  # 特別な戻り値でキャラ獲得を示す
        
        # 緑文字がない場合はガチャ実行
        if tap_if_found('tap', device_port, "gacharu.png", "end"):
            # gacharuクリック成功、アニメーション/画面切り替わり待機
            time.sleep(3)  # 少し長めの待機時間
            
            # クリック後に緑文字チェック
            if _check_green_text_in_region(device_port):
                return "character_found"  # 特別な戻り値でキャラ獲得を示す
            
            return True
        else:
            # gacharuクリックに失敗した場合はFalseを返す
            return False
    
    # どのボタンも見つからない
    return False

def _handle_gacha_interface(device_port: str) -> None:
    """ガチャ画面の操作（画像タップ、スクロールなど）。"""
    # 他の画像をタップ（02_hoshi_iconとtama関連を除外）
    for img_file in sorted(os.listdir(get_resource_path("gacha", "gazo"))):
        if img_file.endswith('.png'):
            # 特定の画像はスキップ（専用処理で対応）
            if img_file in ["02_hoshi_icon.png", "tama.png", "tama2.png", "hoshi_tama.png", "hoshi_tama2.png", "gacharu.png", "target.png"]:
                continue
            tap_if_found('tap', device_port, img_file, "gacha", max_y=540)
    
    # 売却処理
    if tap_if_found('tap', device_port, "sell2.png", "key"):
        from .operations import perform_monster_sell
        sell_operations: List[Tuple[str, str]] = [("l4check.png", "pre.png"), ("l5check.png", "sonota.png")]
        for level_check_img, category_img in sell_operations:
            if not perform_monster_sell(device_port, level_check_img, category_img):
                raise Exception(f"売却処理失敗: {level_check_img}")
        tap_until_found(device_port, "gacharu.png", "end", "back.png", "key", "tap")

    # スクロール操作
    tap_if_found('swipe_down', device_port, "tama.png", "key")
    tap_if_found('swipe_down', device_port, "tama2.png", "key")
    tap_if_found('swipe_down', device_port, "hoshi_tama.png", "key")
    tap_if_found('swipe_down', device_port, "hoshi_tama2.png", "key")

def mon_gacha_until_character(device_port: str, folder: str, multi_logger: Optional[MultiDeviceLogger] = None) -> bool:
    """キャラクターの緑文字が見つかるまでガチャを続ける関数。
    
    Args:
        device_port: 対象デバイスのポート
        folder: フォルダ名
        multi_logger: マルチデバイスロガー（オプション）
        
    Returns:
        キャラクターを獲得したかどうか
        
    Example:
        >>> success = mon_gacha_until_character("127.0.0.1:62001", "folder_001")
        >>> if success:
        ...     print("緑文字のキャラクター獲得!")
    """
    return mon_gacha_shinshun(device_port, folder, gacha_limit=999, multi_logger=multi_logger, continue_until_character=True)

def check_character_ownership_at_position(device_port: str, target_position: tuple) -> bool:
    """target位置を基準に所持状況を確認し、1つでも未所持があるかをチェック。
    
    Args:
        device_port: 対象デバイスのポート
        target_position: target.pngの検出座標 (x, y)
        
    Returns:
        True: 1つでも未所持キャラがある（ガチャ実行すべき）
        False: 全て所持済み（ガチャスキップ）
    """
    try:
        # スクリーンショット取得
        screenshot = get_device_screenshot(device_port, cache_time=1.0, force_refresh=True)
        if screenshot is None:
            logger.error(f"{device_port}: スクリーンショット取得失敗、ガチャをスキップ")
            return False
        
        # target位置を基準にtarget.pngと同じ画角＋下に40px拡張
        x, y = target_position
        # target.pngのサイズ: 163x25px
        target_width, target_height = 163, 25
        # find_and_tap_imageは中心座標を返すので、左上座標に変換
        left_x = x - target_width // 2
        top_y = y - target_height // 2
        # target.pngの左上座標から計算
        x1, x2 = max(0, left_x), min(screenshot.shape[1], left_x + target_width)
        y1, y2 = max(0, top_y), min(screenshot.shape[0], top_y + target_height + 40)  # target高さ+40px
        
        character_regions = [
            (x1, x2, y1, y2),   # target位置から拡張: (x1, x2, y1, y2)
        ]
        
        
        unowned_count = 0
        
        # 座標範囲チェック
        x1, x2, y1, y2 = character_regions[0]
        h, w = screenshot.shape[:2]
        
        if y1 < 0 or y2 > h or x1 < 0 or x2 > w or y1 >= y2 or x1 >= x2:
            return True  # エラー時はガチャ実行
            
        # 指定領域を切り出し
        region = screenshot[y1:y2, x1:x2]
        
        # 緑色文字の検出
        has_green_text = _detect_green_text(region)
        should_gacha = not has_green_text
        
        # スクリーンショット保存とExcel出力
        screenshot_path = _save_ownership_screenshot_and_excel(device_port, region, target_position, has_green_text)
        
        # デバイス別辞書に保存
        global _device_ownership_screenshot_paths
        _device_ownership_screenshot_paths[device_port] = screenshot_path
        
        return should_gacha
        
    except Exception as e:
        logger.error(f"{device_port}: 所持状況確認中にエラー: {e}")
        # エラー時は安全側に倒してガチャを実行
        return True

def _detect_green_text(region: np.ndarray) -> bool:
    """画像領域内で緑色文字を検出。
    
    Args:
        region: 検査対象の画像領域
        
    Returns:
        緑色文字が検出されたかどうか
    """
    try:
        # 画像が空でないかチェック
        if region is None or region.size == 0:
            logger.warning("画像領域が空です")
            return False
            
        # HSV色空間に変換
        hsv = cv2.cvtColor(region, cv2.COLOR_BGR2HSV)
        
        # 緑色の範囲を定義（所持済み文字の緑色）
        # より厳密な緑色範囲を設定して誤検出を減らす
        # 色相(H): 65-75 (より狭い緑色の範囲)
        # 彩度(S): 150-255 (より鮮やかな色のみ)  
        # 明度(V): 150-255 (より明るい色のみ)
        lower_green = np.array([65, 150, 150])
        upper_green = np.array([75, 255, 255])
        
        # 緑色のマスクを作成
        mask = cv2.inRange(hsv, lower_green, upper_green)
        
        # 緑色ピクセルの数をカウント
        green_pixels = cv2.countNonZero(mask)
        
        # より厳しい閾値を設定して誤検出を減らす
        threshold = 100  # 最低100ピクセル（従来の50から増加）
        
        # デバッグ用ログ出力（条件付き）
        if green_pixels > 0:  # 緑色ピクセルが検出された場合のみログ出力
            logger.info(f"緑色ピクセル数: {green_pixels}, 閾値: {threshold}")
        
        return green_pixels >= threshold
        
    except Exception as e:
        logger.error(f"緑色文字検出中にエラー: {e}")
        return False

def _save_ownership_screenshot_and_excel(device_port: str, region: np.ndarray, target_position: tuple, has_green_text: bool) -> str:
    """所持状況のスクリーンショット保存とExcel出力
    
    Args:
        device_port: デバイスポート
        region: 切り出した画像領域
        target_position: target.pngの座標
        has_green_text: 緑文字が検出されたか
        
    Returns:
        str: 保存されたスクリーンショットのパス
    """
    try:
        import cv2
        import os
        from datetime import datetime
        from utils.data_persistence import update_excel_data
        
        # タイムスタンプ生成
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # スクリーンショット保存
        # device_portから数値を抽出（文字化け回避）
        try:
            port_num = device_port.split(':')[-1]
            terminal_id = port_num[-1] if port_num else "0"
        except:
            terminal_id = "0"
        
        screenshots_dir = "ownership_screenshots"
        os.makedirs(screenshots_dir, exist_ok=True)
        
        screenshot_filename = f"ownership_terminal{terminal_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        screenshot_path = os.path.join(screenshots_dir, screenshot_filename)
        
        # BGR画像として保存（OpenCVのデフォルト）
        cv2.imwrite(screenshot_path, region)
        
        # Excel データ更新は _save_gacha_completion_data で実行するため、ここでは実行しない
        
        
        return screenshot_path
        
    except Exception as e:
        logger.error(f"所持状況スクリーンショット保存エラー: {e}")
        return None


def _save_gacha_completion_data_with_target_image(device_port: str, folder: str) -> bool:
    """ガチャ実行前の所持確認時のデータ保存処理（target.png位置の画像を使用）"""
    max_retries = 3
    
    for retry in range(max_retries):
        try:
            terminal_num = get_terminal_number(device_port)
        
            # ①フォルダナンバー: 引数として既に取得済み
            
            # ②アカウント名を読み取り
            account_name = read_account_name(device_port)
            if not account_name:
                account_name = "Unknown"
            
            # ③アカウント名スクリーンショット画像を保存
            account_image_path = save_account_name_image(device_port, folder)
            
            # ④オーブ数を読み取り
            orb_count = read_orb_count(device_port, folder)
            if orb_count is None:
                orb_count = 0
            
            # ⑤オーブ数部分の画像を保存
            orb_image_path = save_orb_count_image(device_port, folder)
            
            # ⑥所持キャラ確認時の切り取り画像を保存（target.png位置の画像を使用）
            global _device_ownership_screenshot_paths
            try:
                character_ownership_image_path = _device_ownership_screenshot_paths.get(device_port) or save_character_ownership_image(device_port, folder)
            except Exception as e:
                logger.error(f"所持キャラ画像保存エラー: {e}")
                character_ownership_image_path = None
            
            # 既存のorb_data.xlsxファイルに保存
            excel_filename = "orb_data.xlsx"
            success = update_excel_data(
                filename=excel_filename,
                folder=folder,
                orbs=orb_count,
                found_character=True,  # キャラ獲得時のみ呼び出されるためTrue
                account_name=account_name,
                account_image=account_image_path or "",
                orb_image=orb_image_path or "",
                character_ownership_image=character_ownership_image_path or ""
            )
            
            if success:
                return True
            else:
                if retry < max_retries - 1:
                    logger.warning(f"{terminal_num}: ガチャ結果データ保存失敗、再試行 ({retry+1}/{max_retries})")
                    time.sleep(2)  # 2秒待機してリトライ
                else:
                    logger.error(f"{terminal_num}: ガチャ結果データ保存失敗（最大リトライ回数到達）")
                    return False
                    
        except Exception as e:
            logger.error(f"ガチャ完了データ保存中にエラー: {e}")
            if retry < max_retries - 1:
                time.sleep(2)  # 2秒待機してリトライ
            else:
                return False
    
    return False

def _save_gacha_completion_data(device_port: str, folder: str) -> bool:
    """キャラ所持確認後のデータ保存処理
    
    Args:
        device_port: 対象デバイスのポート
        folder: フォルダ名
        
    Returns:
        bool: 保存成功の場合True、失敗の場合False
    """
    max_retries = 3
    
    for retry in range(max_retries):
        try:
            terminal_num = get_terminal_number(device_port)
        
            # ①フォルダナンバー: 引数として既に取得済み
            
            # ②アカウント名を読み取り
            account_name = read_account_name(device_port)
            if not account_name:
                account_name = "Unknown"
            
            # ③アカウント名スクリーンショット画像を保存
            account_image_path = save_account_name_image(device_port, folder)
            
            # ④オーブ数を読み取り
            orb_count = read_orb_count(device_port, folder)
            if orb_count is None:
                orb_count = 0
            
            # ⑤オーブ数部分の画像を保存
            orb_image_path = save_orb_count_image(device_port, folder)
            
            # ⑥所持キャラ確認時の切り取り画像を保存（防御的プログラミング）
            try:
                character_ownership_image_path = save_character_ownership_image(device_port, folder)
            except Exception as e:
                logger.error(f"所持キャラ画像保存エラー: {e}")
                character_ownership_image_path = None
            
            # 既存のorb_data.xlsxファイルに保存
            excel_filename = "orb_data.xlsx"
            success = update_excel_data(
                filename=excel_filename,
                folder=folder,
                orbs=orb_count,
                found_character=True,  # キャラ獲得時のみ呼び出されるためTrue
                account_name=account_name,
                account_image=account_image_path or "",
                orb_image=orb_image_path or "",
                character_ownership_image=character_ownership_image_path or ""
            )
            
            if success:
                return True
            else:
                if retry < max_retries - 1:
                    logger.warning(f"{terminal_num}: ガチャ結果データ保存失敗、再試行 ({retry+1}/{max_retries})")
                    time.sleep(2)  # 2秒待機してリトライ
                else:
                    logger.error(f"{terminal_num}: ガチャ結果データ保存失敗（最大リトライ回数到達）")
                    return False
                    
        except Exception as e:
            logger.error(f"ガチャ完了データ保存中にエラー: {e}")
            if retry < max_retries - 1:
                time.sleep(2)  # 2秒待機してリトライ
            else:
                return False
    
    return False

def _search_target_with_swipe(device_port: str) -> tuple:
    """target.pngを探すためのスワイプ機構
    
    50:550から50:50までスワイプしながらtarget.pngを検索します。
    
    Args:
        device_port: 対象デバイスのポート
        
    Returns:
        tuple: target.pngが見つかった場合(x, y)座標、見つからない場合None
    """
    try:
        terminal_num = get_terminal_number(device_port)
        max_swipes = 10  # 最大スワイプ回数
        
        for swipe_count in range(max_swipes):
            # まずtarget.pngを探す
            from monst.image.core import find_and_tap_image
            x, y = find_and_tap_image(device_port, "target.png", "key")
            if x is not None and y is not None:
                if y < 500:  # y軸500より高い位置にある場合のみクリア（下部を除外）
                    logger.info(f"{terminal_num}: target.png発見 位置({x}, {y}) - 条件クリア（スワイプ{swipe_count}回目）")
                    return (x, y)  # 座標を返す
                else:
                    pass  # y軸500以上のため継続
            
            # target.pngが見つからない場合、50:550から50:350にスワイプ
            perform_action(device_port, 'swipe', 50, 550, 50, 350, duration=1000)
            time.sleep(1.5)  # スワイプ後の待機時間
            
        logger.warning(f"{terminal_num}: {max_swipes}回スワイプしてもtarget.pngが見つからない")
        return None
        
    except Exception as e:
        logger.error(f"target.png検索中にエラー: {e}")
        return None