"""
device_operations.py - Backward compatibility layer for monst.device package.

このファイルは既存コードとの互換性を保つためのエイリアスレイヤーです。
新しいコードでは monst.device パッケージを直接使用することを推奨します。

Migration path:
  from device_operations import device_operation_select
  ↓
  from monst.device import device_operation_select
"""

from __future__ import annotations

import warnings

# 新しいパッケージから全ての公開関数をインポート
from monst.device import (
    device_operation_select,
    home,
    icon_check,
    event_do,
    mon_gacha_shinshun,
    device_operation_quest,
    reset_quest_state,
    get_quest_state,
    medal_change,
    mon_initial,
    mission_get,
    name_change,
    mon_sell,
    orb_count,
    DeviceOperationError,
    LoginError,
    GachaOperationError,
    SellOperationError,
    ScreenshotError,
)

# 売却関連の関数
from monst.device import perform_monster_sell

# マクロ関連の関数 (working version restored)
# continue_hasya と load_macro は上記で定義済み

# マクロ機能のエクスポート（互換性のため）
__all__ = [
    'device_operation_select', 'home', 'icon_check', 'event_do', 'mon_gacha_shinshun',
    'device_operation_quest', 'medal_change', 'mon_initial', 'mission_get', 'name_change',
    'mon_sell', 'orb_count', 'perform_monster_sell', 'continue_hasya', 'load_macro',
    'continue_hasya_with_base_folder'
]

# 廃止予定の警告（最初の呼び出し時のみ）
_deprecation_warned = False

def _warn_deprecation():
    global _deprecation_warned
    if not _deprecation_warned:
        warnings.warn(
            "device_operations.py is deprecated. Use 'from monst.device import ...' instead.",
            DeprecationWarning,
            stacklevel=3
        )
        _deprecation_warned = True

# 主要な関数にラッパーを追加（将来的な廃止準備）
_original_device_operation_select = device_operation_select

def device_operation_select(*args, **kwargs):
    _warn_deprecation()
    return _original_device_operation_select(*args, **kwargs)

_original_mon_gacha_shinshun = mon_gacha_shinshun

def mon_gacha_shinshun(*args, **kwargs):
    _warn_deprecation()
    return _original_mon_gacha_shinshun(*args, **kwargs)

# ==============================================
# WORKING VERSION MACRO FUNCTIONALITY RESTORED
# ==============================================

import time
import subprocess
import pyautogui
from config import room_key1, room_key2
from utils import replace_multiple_lines_in_file, activate_window_and_right_click
from monst.image import tap_if_found_on_windows, tap_until_found_on_windows

def continue_hasya():
    """
    覆者継続処理を実行します（working version 完全準拠）
    """
    settings_file_9 = r"C:\Users\santa\Desktop\MM\[周回マクロ設定]\【設定】(9)保存した設定.txt"
    settings_file_10 = r"C:\Users\santa\Desktop\MM\[周回マクロ設定]\【設定】(10)保存した設定.txt"
    start_app = r"C:\Users\santa\Desktop\MM\start_app.exe"

    # 端末ごとの設定
    devices = [
        ("1", "62025", "81", "Q", room_key1, settings_file_9),
        ("2", "62026", "87", "W", room_key1, settings_file_9),
        ("3", "62027", "69", "E", room_key1, settings_file_9),
        ("4", "62028", "82", "R", room_key1, settings_file_10),  # load10.png 使用
        ("5", "62029", "65", "A", room_key2, settings_file_9),
        ("6", "62030", "83", "S", room_key2, settings_file_9),
        ("7", "62031", "68", "D", room_key2, settings_file_9),
        ("8", "62032", "70", "F", room_key2, settings_file_10)  # load10.png 使用
    ]

    for window_name, port, code, key, room_key, settings_file in devices:
        # ファイル書き換え処理
        success = False
        retries = 3
        while not success and retries > 0:
            try:
                replace_multiple_lines_in_file(settings_file, {
                    24: f"tar_device=127.0.0.1:{port}",
                    25: f"output= -P 50037 -s 127.0.0.1:{port}",
                    27: f"main_key={code}",
                    28: f"main_keyF={key}",
                    33: f"room_key={room_key}"
                })
                success = True
            except Exception as e:
                print(f"[ERROR] ファイルの書き換えに失敗しました（{window_name}）：{e}")
                retries -= 1
                time.sleep(2)  # 失敗時にリトライ

        time.sleep(1)  # 書き換え後に少し待機

        # アプリ起動
        subprocess.run(start_app)
        time.sleep(8)  # アプリ起動を十分に待つ（4秒→8秒に延長）

        # **load09.png と load10.png を条件で切り替え**
        load_image = "load10.png" if window_name in ["4", "8"] else "load09.png"

        # 画面のロード完了まで待機
        while not tap_if_found_on_windows("tap", "load.png", "macro"):
            tap_if_found_on_windows("tap", "macro.png", "macro")
            # koushinまたはkoshinの両方をチェック（画像名の違いに対応）
            if (tap_if_found_on_windows("stay", "koushin.png", "macro") or 
                tap_if_found_on_windows("stay", "koshin.png", "macro")):
                tap_if_found_on_windows("tap", "close.png", "macro")
        tap_until_found_on_windows(load_image, "macro", "load.png", "macro")
        tap_until_found_on_windows("kaishi.png", "macro", load_image, "macro")
        tap_until_found_on_windows("nox.png", "macro", "kaishi.png", "macro")
        tap_if_found_on_windows("tap", "ok.png", "macro")

        time.sleep(2)  # 確実に次の処理へ移るため待機

        # ウィンドウをアクティブにして右クリック
        activate_window_and_right_click(window_name)

def load_macro(number: int):
    """
    マクロ読み込み処理を実行します（working version 完全準拠）
    
    Args:
        number: マクロ番号
    """
    settings_file = fr"C:\Users\santa\Desktop\MM\[周回マクロ設定]\【設定】({number})保存した設定.txt"
    start_app = r"C:\Users\santa\Desktop\MM\start_app.exe"

    # 端末ごとの設定
    devices = [
        ("1", "62025", "81", "Q", room_key1, settings_file),
        ("2", "62026", "87", "W", room_key1, settings_file),
        ("3", "62027", "69", "E", room_key1, settings_file),
        ("4", "62028", "82", "R", room_key1, settings_file), 
        ("5", "62029", "65", "A", room_key2, settings_file),
        ("6", "62030", "83", "S", room_key2, settings_file),
        ("7", "62031", "68", "D", room_key2, settings_file),
        ("8", "62032", "70", "F", room_key2, settings_file) 
    ]

    for window_name, port, code, key, room_key, settings_file in devices:
        # ファイル書き換え処理
        success = False
        retries = 3
        while not success and retries > 0:
            try:
                replace_multiple_lines_in_file(settings_file, {
                    24: f"tar_device=127.0.0.1:{port}",
                    25: f"output= -P 50037 -s 127.0.0.1:{port}",
                    27: f"main_key={code}",
                    28: f"main_keyF={key}",
                    33: f"room_key={room_key}"
                })
                success = True
            except Exception as e:
                print(f"[ERROR] ファイルの書き換えに失敗しました（{window_name}）：{e}")
                retries -= 1
                time.sleep(2)  # 失敗時にリトライ

        time.sleep(1)  # 書き換え後に少し待機

        # アプリ起動
        subprocess.run(start_app)
        time.sleep(2)  # アプリ起動を待つ

        load_image = "load09.png"

        # 画面のロード完了まで待機
        tap_until_found_on_windows("load.png", "macro", "macro.png", "macro")
        tap_until_found_on_windows(load_image, "macro", "load.png", "macro")
        pyautogui.press("down", presses=number - 1)
        time.sleep(0.5)
        pyautogui.press("enter")
        time.sleep(1.5)
        pyautogui.press("down")
        time.sleep(0.5)
        pyautogui.press("enter")
        time.sleep(1.5)
        pyautogui.write("1")
        pyautogui.press("enter")
        tap_until_found_on_windows("kaishi.png", "macro", "ok.png", "macro")
        tap_until_found_on_windows("nox.png", "macro", "kaishi.png", "macro")
        tap_if_found_on_windows("tap", "ok.png", "macro")

        time.sleep(2)  # 確実に次の処理へ移るため待機

        # ウィンドウをアクティブにして右クリック
        activate_window_and_right_click(window_name)

def continue_hasya_with_base_folder(base_folder: int):
    """
    覆者継続処理を指定フォルダベースで実行します（working version 完全準拠）
    
    Args:
        base_folder: 開始フォルダ番号
    """
    from app.operations import write_account_folders
    
    # フォルダベースからアカウント設定を更新
    write_account_folders(base_folder)
    
    settings_file_9 = r"C:\Users\santa\Desktop\MM\[周回マクロ設定]\【設定】(9)保存した設定.txt"
    settings_file_10 = r"C:\Users\santa\Desktop\MM\[周回マクロ設定]\【設定】(10)保存した設定.txt"
    start_app = r"C:\Users\santa\Desktop\MM\start_app.exe"

    # 端末ごとの設定
    devices = [
        ("1", "62025", "81", "Q", room_key1, settings_file_9),
        ("2", "62026", "87", "W", room_key1, settings_file_9),
        ("3", "62027", "69", "E", room_key1, settings_file_9),
        ("4", "62028", "82", "R", room_key1, settings_file_10),  # load10.png 使用
        ("5", "62029", "65", "A", room_key2, settings_file_9),
        ("6", "62030", "83", "S", room_key2, settings_file_9),
        ("7", "62031", "68", "D", room_key2, settings_file_9),
        ("8", "62032", "70", "F", room_key2, settings_file_10)  # load10.png 使用
    ]

    for window_name, port, code, key, room_key, settings_file in devices:
        # ファイル書き換え処理
        success = False
        retries = 3
        while not success and retries > 0:
            try:
                replace_multiple_lines_in_file(settings_file, {
                    24: f"tar_device=127.0.0.1:{port}",
                    25: f"output= -P 50037 -s 127.0.0.1:{port}",
                    27: f"main_key={code}",
                    28: f"main_keyF={key}",
                    33: f"room_key={room_key}"
                })
                success = True
            except Exception as e:
                print(f"[ERROR] ファイルの書き換えに失敗しました（{window_name}）：{e}")
                retries -= 1
                time.sleep(2)  # 失敗時にリトライ

        time.sleep(1)  # 書き換え後に少し待機

        # アプリ起動
        subprocess.run(start_app)
        time.sleep(8)  # アプリ起動を十分に待つ（4秒→8秒に延長）

        # **load09.png と load10.png を条件で切り替え**
        load_image = "load10.png" if window_name in ["4", "8"] else "load09.png"

        # 画面のロード完了まで待機
        while not tap_if_found_on_windows("tap", "load.png", "macro"):
            tap_if_found_on_windows("tap", "macro.png", "macro")
            # koushinまたはkoshinの両方をチェック（画像名の違いに対応）
            if (tap_if_found_on_windows("stay", "koushin.png", "macro") or 
                tap_if_found_on_windows("stay", "koshin.png", "macro")):
                tap_if_found_on_windows("tap", "close.png", "macro")
        tap_until_found_on_windows(load_image, "macro", "load.png", "macro")
        tap_until_found_on_windows("kaishi.png", "macro", load_image, "macro")
        tap_until_found_on_windows("nox.png", "macro", "kaishi.png", "macro")
        tap_if_found_on_windows("tap", "ok.png", "macro")

        time.sleep(2)  # 確実に次の処理へ移るため待機

        # ウィンドウをアクティブにして右クリック
        activate_window_and_right_click(window_name)