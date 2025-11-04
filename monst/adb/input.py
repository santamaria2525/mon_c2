"""
monst.adb.input - Device input utilities (keys, text).

NOX ULTRA-THINK 最終安定版 - ADB接続安定化 + シンプル確実方式
"""

from __future__ import annotations

import time
from typing import Optional

from .core import run_adb_command
from logging_util import logger

def send_key_event(
    device_port: str, 
    *, 
    key_event: Optional[int] = None, 
    text: Optional[str] = None, 
    times: int = 1, 
    delay: float = 0.1
) -> bool:
    """NOX対応 - ADB接続安定化 + 確実送信"""
    ok = True
    
    if text is not None:
        ok = _send_text_stable_method(device_port, text)
        time.sleep(delay)
        
    elif key_event is not None:
        for i in range(times):
            # ADB接続安定化
            result = _send_keyevent_with_retry(device_port, key_event)
            ok &= result
            if not result:
                pass
            time.sleep(delay)
    else:
        pass
        ok = False
        
    return ok

def _send_text_stable_method(device_port: str, text: str) -> bool:
    """NOX完璧解決策 - 物理キーコード方式（バックスペース・Enterと同じ方式）"""
    return _send_text_keyevent_complete(device_port, text)

def _send_numbers_keycode(device_port: str, numbers: str) -> bool:
    """数字のみを物理キーコードで送信（バックスペースと同じ方式）"""
    
    # 数字→キーコードマッピング
    number_keycodes = {
        '0': 7, '1': 8, '2': 9, '3': 10, '4': 11,
        '5': 12, '6': 13, '7': 14, '8': 15, '9': 16
    }
    
    pass
    
    # 1. バックスペースでクリア（これは確実に動作）
    for i in range(5):  # 5回バックスペース
        backspace_result = _send_keyevent_with_retry(device_port, 67)
        pass
        time.sleep(0.2)
    
    # 2. 数字を1桁ずつ物理キーコードで送信
    success_count = 0
    for digit in numbers:
        keycode = number_keycodes[digit]
        result = _send_keyevent_with_retry(device_port, keycode)
        if result:
            success_count += 1
        time.sleep(0.3)  # 適切な間隔
    
    # 3. Enter確定（これも確実に動作）
    enter_result = _send_keyevent_with_retry(device_port, 66)
    pass
    
    success_rate = success_count / len(numbers)
    pass
    
    return success_rate >= 0.8  # 80%以上成功で成功判定

def _send_text_keyevent_complete(device_port: str, text: str) -> bool:
    """完全keyevent方式 - 全ての文字をkeyeventで送信"""
    
    # Android KeyCode完全マッピング
    keycodes = {
        # 数字
        '0': 7, '1': 8, '2': 9, '3': 10, '4': 11,
        '5': 12, '6': 13, '7': 14, '8': 15, '9': 16,
        # アルファベット (小文字)
        'a': 29, 'b': 30, 'c': 31, 'd': 32, 'e': 33, 'f': 34,
        'g': 35, 'h': 36, 'i': 37, 'j': 38, 'k': 39, 'l': 40,
        'm': 41, 'n': 42, 'o': 43, 'p': 44, 'q': 45, 'r': 46,
        's': 47, 't': 48, 'u': 49, 'v': 50, 'w': 51, 'x': 52,
        'y': 53, 'z': 54,
    }
    
    pass
    
    # 1. バックスペースでクリア（確実に動作）
    for i in range(5):
        _send_keyevent_with_retry(device_port, 67)  # BACKSPACE
        time.sleep(0.2)
    
    # 2. 文字を1つずつkeyeventで送信
    success_count = 0
    text_lower = text.lower()  # 小文字に変換
    
    for i, char in enumerate(text_lower):
        if char in keycodes:
            keycode = keycodes[char]
            result = _send_keyevent_with_retry(device_port, keycode)
            if result:
                success_count += 1
            time.sleep(0.4)  # 文字間隔
        else:
            pass
    
    # 3. Enter確定（確実に動作）
    enter_result = _send_keyevent_with_retry(device_port, 66)  # ENTER
    
    success_rate = success_count / len(text_lower) if len(text_lower) > 0 else 0
    pass
    
    return success_rate >= 0.8  # 80%以上成功で成功判定

def _send_text_keyboard_tap(device_port: str, text: str) -> bool:
    """NOX完璧解決策 - 仮想キーボード座標タップでテキスト送信"""
    
    # NOX標準解像度でのQWERTYキーボード座標マッピング
    keyboard_coords = {
        # 数字行
        '1': (72, 400),   '2': (144, 400),  '3': (216, 400),  '4': (288, 400),  '5': (360, 400),
        '6': (432, 400),  '7': (504, 400),  '8': (576, 400),  '9': (648, 400),  '0': (720, 400),
        # QWERTY行
        'q': (72, 470),   'w': (144, 470),  'e': (216, 470),  'r': (288, 470),  't': (360, 470),
        'y': (432, 470),  'u': (504, 470),  'i': (576, 470),  'o': (648, 470),  'p': (720, 470),
        # ASDF行  
        'a': (108, 540),  's': (180, 540),  'd': (252, 540),  'f': (324, 540),  'g': (396, 540),
        'h': (468, 540),  'j': (540, 540),  'k': (612, 540),  'l': (684, 540),
        # ZXCV行
        'z': (144, 610),  'x': (216, 610),  'c': (288, 610),  'v': (360, 610),  'b': (432, 610),
        'n': (504, 610),  'm': (576, 610),
    }
    
    pass
    
    # 1. バックスペースでクリア（確実に動作）
    for i in range(5):
        _send_keyevent_with_retry(device_port, 67)  # BACKSPACE
        time.sleep(0.2)
    
    # 2. 文字を1つずつ座標タップで送信
    success_count = 0
    text_lower = text.lower()
    
    for char in text_lower:
        if char in keyboard_coords:
            x, y = keyboard_coords[char]
            result = run_adb_command(["shell", "input", "tap", str(x), str(y)], device_port)
            if result is not None:
                success_count += 1
                pass
            else:
                pass
            time.sleep(0.5)  # タップ間隔
        else:
            pass
    
    # 3. Enter確定（確実に動作）
    _send_keyevent_with_retry(device_port, 66)  # ENTER
    
    success_rate = success_count / len(text_lower) if len(text_lower) > 0 else 0
    pass
    
    return success_rate >= 0.8  # 80%以上成功で成功判定

def _send_keyevent_with_retry(device_port: str, keycode: int, max_retries: int = 3) -> bool:
    """キーイベントを再試行で安定送信"""
    
    for attempt in range(max_retries):
        try:
            result = run_adb_command(["shell", "input", "keyevent", str(keycode)], device_port)
            if result is not None:
                return True
        except Exception as e:
            pass
        
        if attempt < max_retries - 1:
            time.sleep(0.5)  # 再試行前の待機
    
    return False

def _send_with_connection_check(device_port: str, command: list) -> bool:
    """接続確認付きコマンド送信"""
    
    try:
        # 接続確認
        check_result = run_adb_command(["shell", "echo", "test"], device_port)
        if check_result is None or "test" not in check_result:
            return False
        
        # 実際のコマンド実行
        result = run_adb_command(command, device_port)
        return result is not None
        
    except Exception as e:
        return False

def send_text_robust(device_port: str, text: str, max_retries: int = 3) -> bool:
    """安定版テキスト送信"""
    return send_key_event(device_port, text=text)

def press_home_button(device_port: str) -> bool:
    """ホームボタン（安定版）"""
    return send_key_event(device_port, key_event=3)

def press_back_button(device_port: str) -> bool:
    """バックボタン（安定版）"""
    return send_key_event(device_port, key_event=4)