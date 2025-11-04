"""GUI dialog helpers."""

from __future__ import annotations

from .common import (
    sys,
    time,
    threading,
    tk,
    simpledialog,
    ttk,
    messagebox,
    contextmanager,
    Dict,
    Callable,
    Optional,
    List,
    pyautogui,
    logger,
)

def multi_press_enhanced() -> bool:
    """
    Multi-device macro helper (Ctrl+hotkeys with timing adjustments).
    """
    try:
        hotkeys = ['q', 'w', 'e', 'r', 'a', 's', 'd', 'f']

        logger.info("Ctrl+QWERASDF send start")

        for key in hotkeys:
            time.sleep(2.0)  # allow window switching before each key
            pyautogui.hotkey('ctrl', key)
            time.sleep(0.5)

        time.sleep(2)  # settle after the final send
        logger.info("Ctrl+QWERASDF send done")
        return True
    except Exception as e:
        logger.error(f"multi_press_enhanced error: {e}")
        return False


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
            time.sleep(0.2)  # キー間の待機
            
        time.sleep(1)  # 操作完了後の待機
        return True
    except Exception as e:
        logger.error(f"キー操作中にエラー: {e}")
        return False
