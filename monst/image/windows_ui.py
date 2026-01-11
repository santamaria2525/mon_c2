"""
monst.image.windows_ui - Windows UI automation utilities.

Windows画面での画像検索とUI操作機能を提供します。
"""

from __future__ import annotations

import os
import time
from typing import Optional, Tuple

import cv2
import numpy as np
import pyautogui

from logging_util import logger
from .utils import get_image_path_for_windows


class WindowsActionAbort(RuntimeError):
    """Raised when Windows UI automation should abort (e.g. PyAutoGUI failsafe)."""


def find_image_on_windows(
    image_path: str,
    confidence: float = 0.5,
    *,
    log: bool = True,
) -> Optional[Tuple[int, int]]:
    """Windows画面上で画像を検索します。
    
    Args:
        image_path: 画像ファイルの絶対パス
        confidence: 検出の信頼度閾値
        
    Returns:
        画像の中心座標、見つからない場合はNone
        
    Example:
        >>> coords = find_image_on_windows("C:/path/to/button.png", 0.8)
        >>> if coords:
        ...     print(f"Found at {coords}")
    """
    if not os.path.exists(image_path):
        if not (image_path and image_path.lower().endswith("koshin.png")):
            logger.error(f"[ERROR] 画像が見つかりません: {image_path}")
        return None

    try:
        # スクリーンショットを取得
        screen = pyautogui.screenshot()
        screen = np.array(screen)
        screen = cv2.cvtColor(screen, cv2.COLOR_RGB2GRAY)  # グレースケール化

        # テンプレート画像読み込み
        template = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
        if template is None:
            logger.error(f"[ERROR] 画像の読み込みに失敗しました: {image_path}")
            return None

        # テンプレートマッチング実行
        result = cv2.matchTemplate(screen, template, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(result)

        # 閾値以上のマッチがあれば座標を返す
        if max_val >= confidence:
            center_x = max_loc[0] + template.shape[1] // 2
            center_y = max_loc[1] + template.shape[0] // 2
            if log:
                logger.debug(
                    f"Windows画像検索成功: {image_path} 座標({center_x}, {center_y}) 信頼度={max_val:.3f}"
                )
            return (center_x, center_y)
        else:
            if log:
                pass
    except pyautogui.FailSafeException as exc:
        logger.error("Windows画面操作を中断: PyAutoGUI failsafe (%s)", exc)
        raise WindowsActionAbort("pyautogui failsafe") from exc
    except Exception as e:
        logger.error(f"Windows画面での画像検索中にエラー: {e}")

    return None

def find_and_tap_image_on_windows(
    image_name: str,
    *subfolders: str,
    confidence: float = 0.6,
    log: bool = True,
) -> Optional[Tuple[int, int]]:
    """Windows画面で画像を検索し、座標を返します。
    
    Args:
        image_name: 画像ファイル名
        subfolders: サブフォルダ名（可変長引数）
        confidence: マッチング閾値
        
    Returns:
        座標タプル、見つからなければNone
        
    Example:
        >>> coords = find_and_tap_image_on_windows("button.png", "ui", "main")
        >>> if coords:
        ...     x, y = coords
        ...     pyautogui.click(x, y)
    """
    # 画像ファイルのパスを取得
    image_path = get_image_path_for_windows(image_name, *subfolders)
    if not image_path or not os.path.exists(image_path):
        if not (image_path and image_path.lower().endswith("koshin.png")):
            logger.error(f"[ERROR] 画像ファイルが見つかりません: {image_path}")
        return None

    try:
        # スクリーンショットを取得
        screen = pyautogui.screenshot()
        screen = np.array(screen)
        screen = cv2.cvtColor(screen, cv2.COLOR_RGB2GRAY)  # グレースケール化

        # テンプレート画像読み込み
        template = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
        if template is None:
            logger.error(f"[ERROR] 画像の読み込みに失敗しました: {image_path}")
            return None

        # テンプレートマッチング実行
        result = cv2.matchTemplate(screen, template, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(result)

        # 閾値以上のマッチがあれば座標を返す
        if max_val >= confidence:
            center_x = max_loc[0] + template.shape[1] // 2
            center_y = max_loc[1] + template.shape[0] // 2
            if log:
                logger.debug(
                    f"Windows画像検索成功: {image_name} 座標({center_x}, {center_y}) 信頼度={max_val:.3f}"
                )
            return (center_x, center_y)
        else:
            if log:
                pass
    except pyautogui.FailSafeException as exc:
        logger.error("Windows画面操作を中断: PyAutoGUI failsafe (%s)", exc)
        raise WindowsActionAbort("pyautogui failsafe") from exc
    except Exception as e:
        logger.error(f"Windows画面での画像検索中にエラー: {e}")

    return None

def tap_if_found_on_windows(
    action: str,
    image_name: str,
    *subfolders: str,
    confidence: float = 0.6,
    log: bool = True,
) -> bool:
    """Windows画面で画像を検索し、見つかった場合にアクションを実行します。
    
    Args:
        action: 実行するアクション ("tap", "swipe_down", "swipe_up", "stay")
        image_name: 検索する画像ファイル名
        subfolders: サブフォルダ名（可変長引数）
        confidence: マッチング閾値
        
    Returns:
        アクションの成功/失敗
        
    Example:
        >>> # Windows上で"button.png"を見つけてクリック
        >>> success = tap_if_found_on_windows("tap", "button.png", "ui")
        >>> if success:
        ...     print("クリックしました")
    """
    # 連続実行防止のための短い待機
    time.sleep(0.1)

    # 画像を検索
    coords = find_and_tap_image_on_windows(
        image_name,
        *subfolders,
        confidence=confidence,
        log=log,
    )

    if coords is not None:
        x, y = coords
        try:
            # 検出した位置での操作を実行
            if action == "tap":
                pyautogui.click(x, y)
            elif action == "swipe_down":
                pyautogui.moveTo(x, y)
                pyautogui.dragTo(x, y + 100, duration=0.3)
            elif action == "swipe_up":
                pyautogui.moveTo(x, y)
                pyautogui.dragTo(x, y - 100, duration=0.5)
            elif action == "stay":
                time.sleep(1)  # 操作なし、待機のみ
            else:
                logger.error(f"[ERROR] 無効なアクション: {action}")
                return False
            
            return True
        except pyautogui.FailSafeException as exc:
            logger.error("Windows画面操作を中断: PyAutoGUI failsafe (%s)", exc)
            raise WindowsActionAbort("pyautogui failsafe") from exc
        except Exception as e:
            logger.error(f"Windows画面でのアクション実行中にエラー: {e}")
            return False

    return False

def tap_until_found_on_windows(
    target_image: str,
    target_subfolder: str,
    action_image: str,
    action_subfolder: str,
    action: str = 'tap',
    target_action: str = 'stay',
    timeout: int = 120,
    log: bool = True,
) -> bool:
    """Windows画面でターゲット画像が見つかるまでアクションを実行します。
    
    Args:
        target_image: 探す対象の画像ファイル名
        target_subfolder: 対象画像のサブフォルダ
        action_image: アクション実行時の画像ファイル名
        action_subfolder: アクション画像のサブフォルダ
        action: 実行するアクション
        target_action: ターゲット画像が見つかった時に実行するアクション
        timeout: タイムアウト秒数
        
    Returns:
        成功/失敗
        
    Example:
        >>> # Windows上で"result.png"が出るまで"next.png"をクリック
        >>> success = tap_until_found_on_windows(
        ...     "result.png", "dialogs",
        ...     "next.png", "buttons",
        ...     action="tap"
        ... )
    """
    start_time = time.time()

    # 最初にターゲットが既に表示されているかチェック
    if tap_if_found_on_windows(target_action, target_image, target_subfolder, log=log):
        return True

    while time.time() - start_time < timeout:
        # ターゲット画像を再チェック
        if tap_if_found_on_windows(target_action, target_image, target_subfolder, log=log):
            return True

        # アクションを実行
        tap_if_found_on_windows(action, action_image, action_subfolder, log=log)

        # 短い待機
        time.sleep(1)

    # タイムアウト
    logger.warning(f"Windows画面での操作がタイムアウトしました: {target_image}")
    return False
