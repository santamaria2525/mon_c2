"""
monst.image.recognition - OCR and text recognition utilities.

OCRとテキスト認識機能を提供します。
"""

from __future__ import annotations

from typing import Optional
import time
import re
import os
import shutil

import cv2
import numpy as np
import pytesseract

from logging_util import logger
from monst.adb import perform_action
from .constants import TESSERACT_CMD_PATH
from .core import get_device_screenshot, tap_if_found
from pathlib import Path

_TESSERACT_AVAILABLE = False

def _detect_tesseract_cmd() -> Optional[str]:
    """複数の候補パスからTesseract実行ファイルを探す。"""
    candidates = []

    def _add_candidate(path: Optional[str]) -> None:
        if path and path not in candidates:
            candidates.append(path)

    _add_candidate(TESSERACT_CMD_PATH)
    _add_candidate(os.environ.get("TESSERACT_CMD_PATH"))

    which_path = shutil.which("tesseract.exe") or shutil.which("tesseract")
    _add_candidate(which_path)

    local_tool = Path(__file__).resolve().parents[2] / "tools" / "Tesseract-OCR" / "tesseract.exe"
    _add_candidate(str(local_tool))

    for candidate in candidates:
        if candidate and os.path.isfile(candidate):
            return candidate
    return None

_DETECTED_TESSERACT = _detect_tesseract_cmd()
if _DETECTED_TESSERACT:
    pytesseract.pytesseract.tesseract_cmd = _DETECTED_TESSERACT
    _TESSERACT_AVAILABLE = True
    logger.info(f"Tesseract OCRを使用します: {_DETECTED_TESSERACT}")
else:
    logger.warning("Tesseract OCRが見つからないためOCR機能をスキップします。数値の自動読み取りは無効になります。")

def is_ocr_available() -> bool:
    """現在の環境でTesseract OCRが使用可能かを返す。"""
    return _TESSERACT_AVAILABLE

def _is_valid_account_name(text: str) -> bool:
    """3～4桁の数字パターンかチェックします。"""
    if not text or len(text) < 3 or len(text) > 4:
        return False
    return bool(re.match(r'^[0-9]{3,4}$', text))

def _optimal_ocr_preprocessing(image: np.ndarray, target_type: str = "text") -> np.ndarray:
    """OCR前処理を実行します。"""
    # グレースケール変換
    if len(image.shape) == 3:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    else:
        gray = image
    
    if target_type == "text":
        # アカウント名用処理
        h, w = gray.shape
        enlarged = cv2.resize(gray, (w * 5, h * 5), interpolation=cv2.INTER_CUBIC)
        blurred = cv2.GaussianBlur(enlarged, (3, 3), 0)
        adaptive = cv2.adaptiveThreshold(blurred, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2)
        kernel = np.ones((2, 2), np.uint8)
        cleaned = cv2.morphologyEx(adaptive, cv2.MORPH_CLOSE, kernel)
        kernel_sharp = np.array([[-1,-1,-1], [-1,9,-1], [-1,-1,-1]])
        return cv2.filter2D(cleaned, -1, kernel_sharp)
    else:
        # オーブ数用処理
        h, w = gray.shape
        enlarged = cv2.resize(gray, (w * 4, h * 4), interpolation=cv2.INTER_CUBIC)
        clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
        contrasted = clahe.apply(enlarged)
        _, binary = cv2.threshold(contrasted, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        kernel = np.ones((2, 2), np.uint8)
        return cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel)

def _enhanced_ocr(image: np.ndarray, whitelist: str, target_type: str = "text") -> str:
    """OCR処理を実行します。"""
    if not _TESSERACT_AVAILABLE:
        return ""
    try:
        processed = _optimal_ocr_preprocessing(image, target_type)
        
        if target_type == "text":
            configs = [
                f'--psm 8 --oem 3 -c tessedit_char_whitelist={whitelist}',
                f'--psm 7 --oem 3 -c tessedit_char_whitelist={whitelist}',
                f'--psm 6 --oem 3 -c tessedit_char_whitelist={whitelist}',
            ]
        else:
            configs = [
                f'--psm 10 --oem 3 -c tessedit_char_whitelist={whitelist}',
                f'--psm 8 --oem 3 -c tessedit_char_whitelist={whitelist}',
                f'--psm 7 --oem 3 -c tessedit_char_whitelist={whitelist}',
                f'--psm 6 --oem 3 -c tessedit_char_whitelist={whitelist}',
            ]
        
        best_result = ""
        max_confidence = 0
        
        for config in configs:
            try:
                data = pytesseract.image_to_data(processed, config=config, output_type=pytesseract.Output.DICT)
                texts = data['text']
                confidences = data['conf']
                
                for i, text in enumerate(texts):
                    if text.strip() and confidences[i] > max_confidence:
                        allowed_chars = set(whitelist)
                        filtered_text = ''.join(c for c in text if c in allowed_chars)
                        if filtered_text:
                            best_result = filtered_text
                            max_confidence = confidences[i]
            except Exception:
                continue
        
        return best_result
    except Exception as e:
        logger.error(f"OCR処理中にエラー: {e}")
        return ""

def read_account_name(device_port: str) -> Optional[str]:
    """アカウント名（数字部分）を読み取ります。"""
    screenshot = get_device_screenshot(device_port, cache_time=0, force_refresh=True)
    if screenshot is None:
        return None

    # 絶対座標でROI設定：x:1,y:80からx:60,y:100
    roi = screenshot[80:100, 1:60]
    
    try:
        # 数字のみを対象とする
        for attempt in range(5):
            result = _enhanced_ocr(roi, "0123456789", "text")
            if result:
                number_only = ''.join(c for c in result if c.isdigit())
                if number_only and _is_valid_account_name(number_only):
                    return number_only
            if attempt < 4:
                time.sleep(0.1)
        
        # フォールバック処理
        if not _TESSERACT_AVAILABLE:
            return None
        gray_roi = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        for thresh_val in [120, 150, 180]:
            _, thresh = cv2.threshold(gray_roi, thresh_val, 255, cv2.THRESH_BINARY)
            h_roi, w_roi = thresh.shape
            enlarged_thresh = cv2.resize(thresh, (w_roi * 3, h_roi * 3), interpolation=cv2.INTER_CUBIC)
            result = pytesseract.image_to_string(enlarged_thresh, config='--psm 8 --oem 3 -c tessedit_char_whitelist=0123456789')
            number_only = ''.join(c for c in result if c.isdigit())
            if number_only and _is_valid_account_name(number_only):
                return number_only
        
        return None
            
    except Exception as e:
        logger.error(f"アカウント名読み取り中にエラー: {e}")
        return None

def save_account_name_image(device_port: str, folder: str) -> Optional[str]:
    """アカウント名部分の画像を保存します。"""
    screenshot = get_device_screenshot(device_port, cache_time=0, force_refresh=True)
    if screenshot is None:
        return None

    # 絶対座標でROI設定：x:1,y:80からx:60,y:100
    roi = screenshot[80:100, 1:60]
    
    try:
        # 画像保存用ディレクトリを作成
        save_dir = os.path.join("orb_images", folder)
        os.makedirs(save_dir, exist_ok=True)
        
        # ファイル名にタイムスタンプを含める
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        filename = f"account_{timestamp}.png"
        filepath = os.path.join(save_dir, filename)
        
        # 画像を保存
        cv2.imwrite(filepath, roi)
        return filepath
        
    except Exception as e:
        logger.error(f"アカウント名画像保存中にエラー: {e}")
        return None

def read_orb_count(device_port: str, folder_name: str) -> Optional[int]:
    """オーブ数を読み取ります。"""
    screenshot = get_device_screenshot(device_port, cache_time=0, force_refresh=True)
    if screenshot is None:
        return None

    # 絶対座標でROI設定：x:285,y:32からx:330,y:50
    roi = screenshot[32:50, 285:330]

    if not _TESSERACT_AVAILABLE:
        return None

    try:
        result = _enhanced_ocr(roi, "0123456789", "numbers")
        if result and result.isdigit():
            orb_value = int(result)
            if orb_value >= 1000:
                return orb_value
        
        # フォールバック処理
        gray_roi = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        valid_results = []
        
        for thresh_val in [140, 160, 180, 200]:
            _, thresh = cv2.threshold(gray_roi, thresh_val, 255, cv2.THRESH_BINARY)
            h_roi, w_roi = thresh.shape
            enlarged_thresh = cv2.resize(thresh, (w_roi * 3, h_roi * 3), interpolation=cv2.INTER_CUBIC)
            result = pytesseract.image_to_string(enlarged_thresh, config='--psm 8 --oem 3 -c tessedit_char_whitelist=0123456789')
            number_only = ''.join(c for c in result if c.isdigit())
            if number_only and number_only.isdigit():
                value = int(number_only)
                if value >= 1000:
                    valid_results.append(value)
        
        if valid_results:
            sorted_results = sorted(valid_results)
            return sorted_results[len(sorted_results) // 2]
        
        return None
            
    except Exception as e:
        logger.error(f"オーブ数読み取り中にエラー: {e}")
    
    return None

def save_orb_count_image(device_port: str, folder: str) -> Optional[str]:
    """オーブ数部分の画像を保存します。"""
    screenshot = get_device_screenshot(device_port, cache_time=0, force_refresh=True)
    if screenshot is None:
        return None

    # 絶対座標でROI設定：x:285,y:32からx:330,y:50
    roi = screenshot[32:50, 285:330]
    
    try:
        # 画像保存用ディレクトリを作成
        save_dir = os.path.join("orb_images", folder)
        os.makedirs(save_dir, exist_ok=True)
        
        # ファイル名にタイムスタンプを含める
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        filename = f"orb_{timestamp}.png"
        filepath = os.path.join(save_dir, filename)
        
        # 画像を保存
        cv2.imwrite(filepath, roi)
        return filepath
        
    except Exception as e:
        logger.error(f"オーブ数画像保存中にエラー: {e}")
        return None
