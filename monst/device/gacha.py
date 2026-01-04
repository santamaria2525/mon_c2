"""
monst.device.gacha - Gacha operation functions.

ガチャ関連の操作機能を提供します。
"""

from __future__ import annotations

import os
import time
from typing import List, Optional, Tuple, Set

import cv2
import numpy as np

# デバイス別のownership_screenshotパスを保存する辞書（ガチャ実行前の処理のみで使用）
_device_ownership_screenshot_paths = {}

from logging_util import logger, MultiDeviceLogger
from monst.adb import perform_action
from monst.image import (
    tap_if_found, tap_until_found, get_device_screenshot, find_and_tap_image,
    save_character_ownership_image, read_account_name, save_account_name_image, 
    save_orb_count_image, read_orb_count
)
from utils import get_resource_path, update_excel_data
from utils.path_manager import get_base_path
from utils.device_utils import get_terminal_number, get_terminal_number_only
from config import get_config

from .navigation import home
from .operations import perform_monster_sell


def _iter_png_files(directory: Optional[str]) -> List[str]:
    """指定ディレクトリからPNGファイルのみを返す。存在しない場合は空。"""
    if not directory or not os.path.isdir(directory):
        return []
    try:
        files: List[str] = []
        for entry in sorted(os.listdir(directory)):
            path = os.path.join(directory, entry)
            if os.path.isfile(path) and entry.lower().endswith(".png"):
                files.append(entry)
        return files
    except Exception as exc:
        logger.debug("PNGリスト取得失敗 (%s): %s", directory, exc)
        return []


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

_CACHED_CUSTOM_TARGETS: Optional[Tuple[str, ...]] = None
_CACHED_TARGET_FOLDER: Optional[str] = None
_TARGET_COMPLETION_IMAGES: Set[str] = {"syoji1.png", "syoji2.png", "empty.png"}
_CHARACTER_COMPLETION_LABELS: Set[str] = {"syoji1.png", "syoji2.png"}


def mon_gacha_shinshun(
    device_port: str,
    folder: str,
    gacha_limit: int = 16,
    multi_logger: Optional[MultiDeviceLogger] = None,
    continue_until_character: bool = False,
) -> bool:
    """
    旧mon6スタイルのガチャループを単一関数内にまとめたバージョン。
    """
    gacha_count = 0
    found_character = False
    completion_reason: Optional[str] = None

    tap_until_found(device_port, "gacha_black.png", "key", "gacha.png", "key", "tap")
    time.sleep(2)
    if not tap_if_found("stay", device_port, "target.png", "gacha_target"):
        _focus_target_and_prepare(device_port)
    if not tap_if_found('tap', device_port, "10ren.png", "gacha_target"):
        logger.error("%s: 初回10連を押せませんでした", get_terminal_number(device_port))
        return False

    while True:
        completion_label = _detect_completion_image(device_port, force_refresh=True)
        detected_hoshi = tap_if_found('stay', device_port, "01_hoshi_sentaku.png", "gacha_target")

        if detected_hoshi:
            _tap_hoshi_buttons(device_port)
        elif completion_label:
            if completion_label in _CHARACTER_COMPLETION_LABELS:
                found_character = True

        if gacha_count < gacha_limit:
            if completion_label:
                completion_reason = completion_label
                break
            final_check = _detect_completion_image(device_port, force_refresh=True)
            if final_check:
                completion_reason = final_check
                break
            inline_completion: Optional[str] = None
            for image_name in ("syoji1.png", "syoji2.png", "empty.png"):
                if tap_if_found('stay', device_port, image_name, "gacha_target", threshold=0.97):
                    inline_completion = image_name
                    break
            if inline_completion:
                if inline_completion in _CHARACTER_COMPLETION_LABELS:
                    found_character = True
                completion_reason = completion_reason or inline_completion
                break
            final_guard = _detect_completion_image(device_port, force_refresh=True)
            if final_guard:
                completion_reason = completion_reason or final_guard
                break
            if tap_if_found('tap', device_port, "gacharu.png", "gacha_target"):
                gacha_count += 1
        elif gacha_count == gacha_limit:
            if tap_if_found('stay', device_port, "gacharu.png", "gacha_target"):
                logger.info(f"ガチャ上限に達しました - ポート: {device_port}")
                completion_reason = "gacha_limit"
                break

        gacha_dir = get_resource_path("gacha", "gazo")
        for img_file in _iter_png_files(gacha_dir):
            tap_if_found('tap', device_port, img_file, "gacha")

        if tap_if_found('tap', device_port, "sell2.png", "key"):
            sell_operations = [("l4check.png", "pre.png"), ("l5check.png", "sonota.png")]
            for level_check_img, category_img in sell_operations:
                if not perform_monster_sell(device_port, level_check_img, category_img):
                    raise Exception(f"売却処理失敗: {level_check_img}")
            tap_until_found(device_port, "gacharu.png", "gacha_target", "back.png", "key", "tap")

        tap_if_found('swipe_down', device_port, "tama.png", "key")
        tap_if_found('swipe_down', device_port, "tama2.png", "key")
        tap_if_found('swipe_down', device_port, "hoshi_tama.png", "key")
        tap_if_found('swipe_down', device_port, "hoshi_tama2.png", "key")

        if tap_if_found("stay", device_port, "tama_road.png", "gacha"):
            perform_action(device_port, "swipe", 180, 450, 180, 600, duration=1200)
            time.sleep(0.5)

        # 画面が停滞するケース対策として、処理1巡ごとにタップを入れて遷移を促す
        perform_action(device_port, "tap", 50, 175, duration=100)

        if found_character and completion_label and tap_if_found('stay', device_port, "gacharu.png", "gacha_target"):
            completion_reason = completion_reason or completion_label
            break

    if completion_reason:
        logger.info(f"{folder} 作業完了 ({completion_reason})")
    else:
        logger.info(f"{folder} 作業完了 (reason unspecified)")
    return found_character


def _detect_completion_image(device_port: str, threshold: float = 0.97, *, force_refresh: bool = False) -> Optional[str]:
    targets = [
        ("syoji1.png", "syoji1.png"),
        ("syoji2.png", "syoji2.png"),
        ("empty.png", "empty.png"),
    ]
    for image_name, label in targets:
        cache_time = 0 if force_refresh else 0.5
        if tap_if_found('stay', device_port, image_name, "gacha_target", threshold=threshold, cache_time=cache_time):
            logger.debug("%s: completion候補(%s)を検出しました", get_terminal_number(device_port), label)
            return label
    return None


def _enter_gacha_menu(device_port: str) -> bool:
    timeout = time.time() + 30
    while time.time() < timeout:
        if tap_if_found("stay", device_port, "gacha_black.png", "key"):
            tap_if_found("tap", device_port, "gacha_black.png", "key")
            time.sleep(2.0)
            return True
        tap_if_found("tap", device_port, "gacha.png", "key")
        time.sleep(0.5)
    return False


def _focus_target_and_prepare(device_port: str) -> bool:
    if tap_if_found("stay", device_port, "target.png", "gacha_target"):
        return True
    max_swipes = 18
    for _ in range(max_swipes):
        if tap_if_found("stay", device_port, "target.png", "gacha_target"):
            return True
        _swipe_for_target(device_port)
        time.sleep(0.5)
    return False


def _swipe_for_target(device_port: str) -> None:
    try:
        perform_action(device_port, "swipe", 150, 220, 150, 540, duration=1800)
    except Exception as exc:
        logger.debug("%s: target探索スワイプ失敗: %s", get_terminal_number(device_port), exc)


def _tap_hoshi_buttons(device_port: str) -> None:
    """Tap星玉の02/03ボタンを順に押してシーケンスを前進させる。"""
    tapped = False
    if tap_if_found('tap', device_port, "02_hoshi_icon.png", "gacha_target"):
        tapped = True
        time.sleep(0.3)
    if tap_if_found('tap', device_port, "03_hoshi_s.png", "gacha_target"):
        tapped = True
        time.sleep(0.3)
    if tapped:
        logger.debug("%s: 星玉ボタンをタップしました", get_terminal_number(device_port))


def _post_pull_cycle(device_port: str) -> None:
    _tap_auxiliary_gacha_images(device_port)
    _handle_sell_sequence(device_port)
    _handle_tama_road(device_port)
    _scroll_gacha_screen(device_port)
    _clear_gacha_overlays(device_port)
    time.sleep(0.3)

def _perform_initial_pull(device_port: str) -> bool:
    if tap_if_found("stay", device_port, "target.png", "gacha"):
        if tap_if_found("tap", device_port, "10ren.png", "gacha"):
            time.sleep(3.0)
            return True
    # targetが見えなくなった場合は再度サーチ
    if _focus_target_and_prepare(device_port) and tap_if_found("tap", device_port, "10ren.png", "gacha"):
        time.sleep(3.0)
        return True
    return False

def _press_gacharu_with_guard(device_port: str, folder: Optional[str], targets: Tuple[str, ...]) -> Union[bool, str]:
    if folder and targets and _detect_target_completion(device_port, folder, targets):
        logger.info("%s: 終了画像が表示されているためgacharuを押しません", get_terminal_number(device_port))
        return "completion"
    buttons = [
        ("gacharu.png", "gacha"),
        ("gacharu.png", "end"),
        ("gacharu.png", "key"),
    ]
    for image, folder_name in buttons:
        if tap_if_found("tap", device_port, image, folder_name):
            time.sleep(3.0)
            return True
    return False

def _execute_gacha_action(device_port: str) -> bool:
    """10連ボタン→単発ボタンの順で実行し、押せなければFalseを返す。"""
    if _execute_ten_pull(device_port):
        return True

    fallback_buttons = [
        ("gacharu.png", "gacha"),
        ("gacharu.png", "end"),
        ("gacharu.png", "key"),
    ]
    for image_name, folder in fallback_buttons:
        if tap_if_found("tap", device_port, image_name, folder):
            time.sleep(3.0)
            return True

    # 画面がズレた場合は再度ガチャ画面へ戻す
    tap_if_found("tap", device_port, "gacha_black.png", "key")
    return False


def _execute_ten_pull(device_port: str) -> bool:
    if tap_if_found("tap", device_port, "10ren.png", "gacha"):
        time.sleep(3.0)
        return True
    if tap_if_found("tap", device_port, "gacharu.png", "end"):
        time.sleep(3.0)
        return True
    return False


def _clear_gacha_overlays(device_port: str) -> None:
    buttons = ["yes.png", "yes2.png", "ok.png", "ok2.png", "close.png"]
    for _ in range(5):
        cleared = False
        for button in buttons:
            if tap_if_found("tap", device_port, button, "end") or tap_if_found(
                "tap", device_port, button, "ui"
            ):
                time.sleep(0.3)
                cleared = True
        if not cleared:
            break


def _detect_target_completion(device_port: str, folder: Optional[str], targets: Tuple[str, ...]) -> bool:
    if not folder or not targets:
        return False
    for image_name in targets:
        if tap_if_found("stay", device_port, image_name, folder):
            return True
    return False


def _load_custom_target_images() -> Tuple[Optional[str], Tuple[str, ...]]:
    global _CACHED_CUSTOM_TARGETS, _CACHED_TARGET_FOLDER
    if _CACHED_CUSTOM_TARGETS is not None:
        return _CACHED_TARGET_FOLDER, _CACHED_CUSTOM_TARGETS

    base = get_base_path()
    for folder_name in ("gacha_target", "gacha_targets"):
        folder_path = os.path.join(base, "gazo", folder_name)
        if os.path.isdir(folder_path):
            all_images = [
                f for f in os.listdir(folder_path)
                if f.lower().endswith(".png") and os.path.isfile(os.path.join(folder_path, f))
            ]
            images = tuple(
                sorted(
                    f
                    for f in all_images
                    if f.lower() in _TARGET_COMPLETION_IMAGES
                )
            )
            if images:
                _CACHED_TARGET_FOLDER = folder_name
                _CACHED_CUSTOM_TARGETS = images
                return folder_name, images

    _CACHED_TARGET_FOLDER = None
    _CACHED_CUSTOM_TARGETS = tuple()
    return None, tuple()


def _tap_auxiliary_gacha_images(device_port: str) -> None:
    directory = get_resource_path("gacha", "gazo")
    if not directory:
        return
    excluded = {"02_hoshi_icon.png", "tama.png", "tama2.png", "hoshi_tama.png", "hoshi_tama2.png", "gacharu.png", "10ren.png", "target.png"}
    for img_file in _iter_png_files(directory):
        if img_file not in excluded:
            tap_if_found("tap", device_port, img_file, "gacha")


def _handle_sell_sequence(device_port: str) -> None:
    if tap_if_found("tap", device_port, "sell2.png", "key"):
        sell_operations = [("l4check.png", "pre.png"), ("l5check.png", "sonota.png")]
        for level_check_img, category_img in sell_operations:
            if not perform_monster_sell(device_port, level_check_img, category_img):
                raise RuntimeError(f"売却処理失敗: {level_check_img}")
        tap_until_found(device_port, "gacharu.png", "end", "back.png", "key", "tap")


def _handle_tama_road(device_port: str) -> None:
    if tap_if_found("stay", device_port, "tama_road.png", "gacha"):
        try:
            perform_action(device_port, "swipe", 180, 450, 180, 600, duration=1200)
            time.sleep(0.5)
        except Exception as exc:
            logger.debug("%s: tama_road swipe failure %s", get_terminal_number(device_port), exc)


def _scroll_gacha_screen(device_port: str) -> None:
    anchors = [
        ("tama.png", "gacha"),
        ("tama2.png", "gacha"),
        ("hoshi_tama.png", "gacha"),
        ("hoshi_tama2.png", "gacha"),
    ]
    for image_name, folder in anchors:
        coords = _locate_anchor(device_port, image_name, folder)
        if coords:
            _swipe_from_coordinates(device_port, coords)
            return
    # フォールバック: 画面中央で下方向にドラッグ
    try:
        perform_action(device_port, "swipe", 160, 160, 160, 520, duration=1500)
    except Exception:
        pass
    time.sleep(0.6)


def _locate_anchor(device_port: str, image_name: str, folder: str) -> Optional[Tuple[int, int]]:
    coords = find_and_tap_image(
        device_port, image_name, folder, cache_time=0, threshold=0.75
    )
    if not coords or coords[0] is None or coords[1] is None:
        return None
    x, y = int(coords[0]), int(coords[1])
    logger.debug("%s: anchor %s detected at (%d,%d)", get_terminal_number(device_port), image_name, x, y)
    return x, y


def _swipe_from_coordinates(device_port: str, coords: Tuple[int, int]) -> None:
    x, y = coords
    terminal = get_terminal_number(device_port)
    start_y = min(y + 40, 560)
    end_y = min(start_y + 280, 580)
    if end_y - start_y < 120:
        start_y = max(y, 120)
        end_y = min(start_y + 320, 580)
    try:
        perform_action(device_port, "swipe", x, start_y, x, end_y, duration=1500)
        logger.debug("%s: swipe from (%d,%d) -> (%d,%d)", terminal, x, start_y, x, end_y)
        time.sleep(0.8)
    except Exception as exc:
        logger.debug("%s: swipe failure %s", terminal, exc)

def _check_character_drop(device_port: str) -> bool:
    hoshi_dir = get_resource_path("hoshi", "gazo")
    if tap_if_found("stay", device_port, "01_hoshi_sentaku.png", "gacha_target"):
        time.sleep(6)
        while not tap_if_found("stay", device_port, "shinshun_zenshin.png", "end"):
            for img_file in _iter_png_files(hoshi_dir):
                tap_if_found("tap", device_port, img_file, "hoshi")
                time.sleep(1)
        return True

    character_images = ["syoji1.png", "syoji2.png"]
    return any(tap_if_found("stay", device_port, img, "end") for img in character_images)


# === 既存補助関数（下位互換性のため保持） ===

def _check_character_acquisition(device_port: str) -> bool:
    """キャラクター獲得の判定を行います。"""
    hoshi_dir = get_resource_path("hoshi", "gazo")
    if tap_if_found('stay', device_port, "01_hoshi_sentaku.png", "gacha_target"):
        time.sleep(6)
        while not tap_if_found('stay', device_port, "shinshun_zenshin.png", "end"):
            for img_file in _iter_png_files(hoshi_dir):
                # 02_hoshi_icon.pngは星玉検知後の選択画面でのみクリック
                if img_file == "02_hoshi_icon.png":
                    if (tap_if_found('stay', device_port, "hoshi_tama.png", "gacha") or 
                        tap_if_found('stay', device_port, "hoshi_tama2.png", "gacha")):
                        tap_if_found('tap', device_port, img_file, "hoshi")
                else:
                    tap_if_found('tap', device_port, img_file, "hoshi")
                time.sleep(1)
        return True
    
    character_images: List[str] = ["shinshun_icon.png", "shinshun_zenshin.png", "syoji1.png", "syoji2.png"]
    return any(tap_if_found('stay', device_port, img, "end") for img in character_images)

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
    resource_dir = get_resource_path("gacha", "gazo")
    target_dir = get_resource_path("gacha_target", "gazo") or resource_dir
    if not resource_dir:
        return
    excluded = {"02_hoshi_icon.png", "tama.png", "tama2.png", "hoshi_tama.png", "hoshi_tama2.png", "gacharu.png", "target.png"}
    for img_file in _iter_png_files(resource_dir):
        if img_file in excluded:
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
        target_resource = get_resource_path("target.png", "ui")
        if not target_resource:
            logger.info("target.png が見つからないため既定のターゲット探索をスキップします")
            return None

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

