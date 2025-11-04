"""
monst.image.device_control - High-level device control operations.

高レベルのデバイス制御操作を提供します。
"""

from __future__ import annotations

import random
import time
from typing import Dict

from logging_util import logger
from monst.adb import perform_action, send_key_event
from .core import tap_if_found
# 安全のため自動回復機能のインポートを無効化
# from .device_management import is_device_in_error_state, recover_device, _device_in_error_state, clear_device_cache

# Import centralized device state management
from device_state import setup_device_folder_mapping as _setup_device_folder_mapping, get_folder_for_device

def setup_device_folder_mapping(device_ports: list[str], loaded_folders: list[str]) -> None:
    """デバイスとフォルダのマッピングを設定します。
    
    Args:
        device_ports: デバイスポートのリスト
        loaded_folders: 読み込まれたフォルダのリスト
    """
    _setup_device_folder_mapping(device_ports, loaded_folders)

def type_folder_name(device_port: str, prefix: str = "") -> None:
    """MON6互換フォルダ名入力 - 確実に動作する3段階シーケンス
    
    Args:
        device_port: デバイスポート
        prefix: フォルダ名の接頭辞
    """
    pass
    
    folder_name = get_folder_for_device(device_port)
    if not folder_name:
        pass
        return
    
    text_to_type = prefix + folder_name
    pass
    
    try:
        # === MON6互換 3段階シーケンス ===
        
        # Step 1: 既存テキストをクリア
        clear_result = send_key_event(device_port, key_event=67, times=8, delay=0.1)
        time.sleep(1.0)  # 十分な待機時間
        
        # Step 2: 新しいテキストを入力（MON6互換方式）
        input_result = send_key_event(device_port, text=text_to_type, delay=0.2)
        time.sleep(1.0)  # 入力が反映されるまで待機
        
        # Step 3: Enterで確定
        enter_result = send_key_event(device_port, key_event=66, delay=0.1)
        time.sleep(0.5)  # 確定処理の待機
        
        # === 結果確認 ===
        pass
            
    except Exception as e:
        pass

def tap_until_found(
    device_port: str, 
    target_image: str, 
    target_subfolder: str,
    action_image: str, 
    action_subfolder: str, 
    action: str = 'tap', 
    target_action: str = 'stay',
    timeout: int = 3600, 
    retry_interval: float = 2.0
) -> bool:
    """ターゲット画像が見つかるまでアクションを実行します。
    
    Args:
        device_port: デバイスポート
        target_image: 探す対象の画像ファイル名
        target_subfolder: 対象画像のサブフォルダ
        action_image: アクション実行時の画像ファイル名
        action_subfolder: アクション画像のサブフォルダ
        action: 実行するアクション
        target_action: ターゲット画像が見つかった時に実行するアクション
        timeout: タイムアウト秒数
        retry_interval: リトライ間隔（秒）
        
    Returns:
        成功/失敗
        
    Example:
        >>> # "ok.png"が見つかるまで"button.png"をタップし続ける
        >>> success = tap_until_found(
        ...     "127.0.0.1:62001", 
        ...     "ok.png", "result",
        ...     "button.png", "ui",
        ...     action="tap"
        ... )
    """
    start_time = time.time()
    last_action_time = 0
    
    # デバイス状態確認（自動回復機能は無効化）
    # 安全のため自動回復機能を無効化
    # if device_port in _device_in_error_state:
    #     # 自動回復を試みる
    #     reset_success = recover_device(device_port)
    #     if not reset_success:
    #         logger.warning(f"デバイス {device_port} の回復に失敗しました。操作をスキップします。")
    #         return False
    
    while True:
        # まずターゲットを探す
        if tap_if_found(target_action, device_port, target_image, target_subfolder, cache_time=0):
            return True
        
        # タイムアウトチェック
        current_time = time.time()
        if current_time - start_time > timeout:
            logger.warning(f"タイムアウト ({timeout}秒): {target_image}が見つかりません (デバイス: {device_port})")
            return False
        
        # アクション実行（一定間隔で）
        if current_time - last_action_time >= retry_interval:
            if action == 'tap':
                tap_if_found('tap', device_port, action_image, action_subfolder, cache_time=0)
            elif action == 'swipe_up':
                tap_if_found('swipe_up', device_port, action_image, action_subfolder, cache_time=0)
            elif action == 'swipe_down':
                tap_if_found('swipe_down', device_port, action_image, action_subfolder, cache_time=0)
            elif action == '100tap':
                perform_action(device_port, 'tap', 100, 100, duration=300)
            elif action == 'stay':
                time.sleep(0.5)
            
            last_action_time = current_time
            
            # デバイスエラーチェック（自動回復無効化）
            # 安全のため自動回復機能を無効化
            # if device_port in _device_in_error_state:
            #     logger.warning(f"デバイス {device_port} がエラー状態になりました。回復を試みます。")
            #     if recover_device(device_port):
            #         logger.info(f"デバイス {device_port} の回復に成功しました。操作を続行します。")
            #     else:
            #         logger.warning(f"デバイス {device_port} の回復に失敗しました。タイムアウトします。")
            #         return False
            
        # 負荷軽減のための待機
        time.sleep(min(0.5, retry_interval))  # 最大でも0.5秒待機

def mon_swipe(device_port: str) -> bool:
    """モンスト用のスワイプを実行します。
    
    Args:
        device_port: デバイスポート
        
    Returns:
        成功/失敗
        
    Example:
        >>> success = mon_swipe("127.0.0.1:62001")
        >>> if success:
        ...     print("スワイプしました")
    """
    # エラー状態のデバイスは処理をスキップ（チェック無効化）
    # 安全のため自動エラーチェックを無効化
    # if is_device_in_error_state(device_port):
    #     return False

    try:
        # 画面サイズを設定
        screen_width = 360  # 標準的なNOX画面幅
        screen_height = 640  # 標準的なNOX画面高さ

        # スワイプの開始位置 (右真ん中方向にランダム)
        start_x = random.randint(screen_width // 2 + 50, screen_width // 2 + 150)
        start_y = random.randint(screen_height // 2 - 50, screen_height // 2 + 50)

        # スワイプの終了位置 (左上方向にランダム、角度を浅く)
        end_x = random.randint(screen_width // 2 - 100, screen_width // 2 - 50)
        end_y = random.randint(screen_height // 2 - 100, screen_height // 2 - 50)

        # スワイプの時間（ランダム: 200～500ms）
        duration = random.randint(200, 500)

        # スワイプ実行
        perform_action(device_port, 'swipe', start_x, start_y, end_x, end_y, duration=duration)
        
        # キャッシュをクリア（自動回復機能は無効化）
        # clear_device_cache(device_port)
        
        return True
    except Exception as e:
        logger.error(f"スワイプ操作中にエラーが発生しました: {e} (デバイス: {device_port})")
        return False