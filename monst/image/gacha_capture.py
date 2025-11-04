"""
monst.image.gacha_capture - ガチャ関連画像キャプチャ機能

ガチャ処理における画像保存機能を提供します。
所持キャラ確認時の緑文字部分画像を保存する機能を含みます。
"""

from __future__ import annotations

import os
import time
from typing import Optional

import cv2

from logging_util import logger
from .core import get_device_screenshot

def save_character_ownership_image(device_port: str, folder: str) -> Optional[str]:
    """所持キャラ確認時の緑文字部分画像を保存します。
    
    Args:
        device_port: 対象デバイスのポート
        folder: フォルダ名
        
    Returns:
        保存された画像ファイルのパス（保存に失敗した場合はNone）
    """
    screenshot = get_device_screenshot(device_port, cache_time=0, force_refresh=True)
    if screenshot is None:
        logger.error(f"スクリーンショット取得失敗: {device_port}")
        return None

    # 緑文字チェック範囲: x:12-200, y:480-580
    roi = screenshot[480:580, 12:200]
    
    try:
        # 大改修前の成功バージョンに基づく画像保存
        save_dir = os.path.join("orb_images", folder)
        os.makedirs(save_dir, exist_ok=True)
        
        # ファイル名にタイムスタンプを含める
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        filename = f"character_ownership_{timestamp}.png"
        filepath = os.path.join(save_dir, filename)
        
        # 画像を保存
        success = cv2.imwrite(filepath, roi)
        
        if success and os.path.exists(filepath):
            return filepath  # 相対パスを返す（大改修前の動作）
        else:
            logger.error(f"所持キャラ確認画像保存失敗: {filepath}")
            return None
        
    except Exception as e:
        logger.error(f"所持キャラ確認画像保存中にエラー: {e}")
        return None

def save_full_gacha_screen_image(device_port: str, folder: str) -> Optional[str]:
    """ガチャ画面全体のスクリーンショットを保存します。
    
    Args:
        device_port: 対象デバイスのポート
        folder: フォルダ名
        
    Returns:
        保存された画像ファイルのパス（保存に失敗した場合はNone）
    """
    screenshot = get_device_screenshot(device_port, cache_time=0, force_refresh=True)
    if screenshot is None:
        logger.error(f"スクリーンショット取得失敗: {device_port}")
        return None
    
    try:
        # 大改修前の成功バージョンに基づく画像保存
        save_dir = os.path.join("orb_images", folder)
        os.makedirs(save_dir, exist_ok=True)
        
        # ファイル名にタイムスタンプを含める
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        filename = f"gacha_screen_{timestamp}.png"
        filepath = os.path.join(save_dir, filename)
        
        # 画像を保存
        cv2.imwrite(filepath, screenshot)
        return filepath
        
    except Exception as e:
        logger.error(f"ガチャ画面スクリーンショット保存中にエラー: {e}")
        return None

def save_account_name_image(device_port: str, folder: str) -> Optional[str]:
    """アカウント名部分の画像を保存します。
    
    Args:
        device_port: 対象デバイスのポート
        folder: フォルダ名
        
    Returns:
        保存された画像ファイルのパス（保存に失敗した場合はNone）
    """
    screenshot = get_device_screenshot(device_port, cache_time=0, force_refresh=True)
    if screenshot is None:
        logger.error(f"スクリーンショット取得失敗: {device_port}")
        return None

    # アカウント名領域（適切な座標に調整）
    # 通常画面上部のアカウント名部分
    roi = screenshot[20:60, 80:300]
    
    try:
        # 大改修前の成功バージョンに基づく画像保存
        save_dir = os.path.join("orb_images", folder)
        os.makedirs(save_dir, exist_ok=True)
        
        # ファイル名にタイムスタンプを含める
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        filename = f"account_name_{timestamp}.png"
        filepath = os.path.join(save_dir, filename)
        
        # 画像を保存
        success = cv2.imwrite(filepath, roi)
        
        if success and os.path.exists(filepath):
            return filepath  # 相対パスを返す（大改修前の動作）
        else:
            logger.error(f"アカウント名画像保存失敗: {filepath}")
            return None
        
    except Exception as e:
        logger.error(f"アカウント名画像保存中にエラー: {e}")
        return None

def save_orb_count_image(device_port: str, folder: str) -> Optional[str]:
    """オーブ数部分の画像を保存します。
    
    Args:
        device_port: 対象デバイスのポート
        folder: フォルダ名
        
    Returns:
        保存された画像ファイルのパス（保存に失敗した場合はNone）
    """
    screenshot = get_device_screenshot(device_port, cache_time=0, force_refresh=True)
    if screenshot is None:
        logger.error(f"スクリーンショット取得失敗: {device_port}")
        return None

    # オーブ数領域（適切な座標に調整）
    # 通常画面上部のオーブ数部分
    roi = screenshot[20:60, 350:450]
    
    try:
        # 大改修前の成功バージョンに基づく画像保存
        save_dir = os.path.join("orb_images", folder)
        os.makedirs(save_dir, exist_ok=True)
        
        # ファイル名にタイムスタンプを含める
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        filename = f"orb_count_{timestamp}.png"
        filepath = os.path.join(save_dir, filename)
        
        # 画像を保存
        success = cv2.imwrite(filepath, roi)
        
        if success and os.path.exists(filepath):
            return filepath  # 相対パスを返す（大改修前の動作）
        else:
            logger.error(f"オーブ数画像保存失敗: {filepath}")
            return None
        
    except Exception as e:
        logger.error(f"オーブ数画像保存中にエラー: {e}")
        return None

def save_complete_gacha_data(device_port: str, folder: str, found_character: bool = False) -> dict:
    """ガチャ結果の完全なデータ保存を実行します。
    
    Args:
        device_port: 対象デバイスのポート
        folder: フォルダ名
        found_character: キャラクターを見つけたかどうか
        
    Returns:
        保存されたデータの辞書
    """
    result = {
        "success": False,
        "account_name": None,
        "account_image": None,
        "orb_count": 0,
        "orb_image": None,
        "character_ownership_image": None,
        "error": None
    }
    
    try:
        # アカウント名の読み取りと画像保存
        from .recognition import read_account_name, read_orb_count
        
        account_name = read_account_name(device_port)
        if account_name:
            result["account_name"] = account_name
            result["account_image"] = save_account_name_image(device_port, folder)
        
        # オーブ数の読み取りと画像保存
        orb_count = read_orb_count(device_port)
        if orb_count:
            result["orb_count"] = orb_count
            result["orb_image"] = save_orb_count_image(device_port, folder)
        
        # キャラ所持確認画像の保存
        if found_character:
            result["character_ownership_image"] = save_character_ownership_image(device_port, folder)
        
        # エクセルデータの更新（端末固有のフォルダ名を使用）
        from utils.data_persistence import update_excel_data
        from utils.device_utils import get_terminal_number_only
        
        # フォルダ名はそのまま使用（端末番号追加せず）
        unique_folder = folder
        
        excel_success = update_excel_data(
            filename="orb_data.xlsx",
            folder=unique_folder,  # ユニークなフォルダ名を使用
            orbs=result["orb_count"],
            found_character=found_character,
            account_name=result["account_name"],
            account_image=result["account_image"],
            orb_image=result["orb_image"],
            character_ownership_image=result["character_ownership_image"]
        )
        
        result["success"] = excel_success
        
        if excel_success:
            pass
        else:
            logger.error(f"ガチャデータ保存失敗: {device_port}, フォルダ: {folder}")
            
    except Exception as e:
        logger.error(f"ガチャデータ保存中にエラー: {e}")
        result["error"] = str(e)
    
    return result