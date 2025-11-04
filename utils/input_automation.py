"""
Input automation utilities for Monster Strike Bot

This module handles input automation including:
- Keyboard shortcuts and hotkeys
- Mouse automation
- Multi-key press operations
"""

import time
import pyautogui
from logging_util import logger
# Avoid circular import - define constant locally
KEY_PRESS_DELAY = 0.2

def multi_press() -> bool:
    """
    複数のキーを押す（Ctrl+各キー）
    
    Returns:
        bool: 成功かどうか
    """
    try:
        hotkeys = ['q', 'w', 'e', 'r', 'a', 's', 'd', 'f']
        
        for key in hotkeys:
            # Ctrl+キーの組み合わせを送信
            pyautogui.hotkey('ctrl', key)
            time.sleep(KEY_PRESS_DELAY)  # キー間の待機
            
        time.sleep(1)  # 操作完了後の待機
        return True
    except Exception as e:
        logger.error(f"キー操作中にエラー: {e}")
        return False