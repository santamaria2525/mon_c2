"""
monst.image.core - Core computer vision functionality.

デバイススクリーンショット取得と基本的な画像検索機能を提供します。
"""

from __future__ import annotations

import gc
import subprocess
import threading
import time
from typing import Dict, Optional, Tuple

import cv2
import numpy as np

from config import NOX_ADB_PATH
from logging_util import logger
from .constants import MAX_SCREENSHOT_CACHE_AGE
from .device_management import mark_device_error, mark_device_recovered, is_device_in_error_state
from .utils import get_image_path

# テンプレート画像の簡易キャッシュ（プロセス内）
_template_cache: Dict[str, np.ndarray] = {}

def _get_template_gray(path: str) -> Optional[np.ndarray]:
    """グレースケールテンプレートを読み込み、プロセス内にキャッシュする。"""
    try:
        if not path:
            return None
        cached = _template_cache.get(path)
        if cached is not None:
            return cached
        tmpl = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
        if tmpl is not None:
            _template_cache[path] = tmpl
        else:
            logger.error(f"[ULTRATHINK] テンプレート読込失敗: {path}")
        return tmpl
    except Exception as e:
        logger.error(f"[ULTRATHINK] テンプレート読込エラー: {e}")
        return None

# スクリーンショットキャッシュ
_last_screenshot: Dict[str, np.ndarray] = {}
_last_screenshot_time: Dict[str, float] = {}
_screenshot_lock = threading.Lock()

# 連続失敗追跡
_consecutive_failures: Dict[str, int] = {}
_last_failure_time: Dict[str, float] = {}

# 回復チェック間隔
RECOVERY_CHECK_INTERVAL = 120

# メモリ管理
_memory_check_counter = 0
MEMORY_CHECK_INTERVAL = 50  # 50回に1回メモリチェック

def get_device_screenshot(
    device_port: str, 
    cache_time: float = 5.0,  # 2.0秒から5.0秒に延長（8端末対応）
    force_refresh: bool = False
) -> Optional[np.ndarray]:
    """デバイスからスクリーンショットを取得します。
    
    Args:
        device_port: 対象デバイスのポート
        cache_time: キャッシュの有効期間（秒）
        force_refresh: 強制的に新しいスクリーンショットを取得するか
        
    Returns:
        スクリーンショットの画像データ、取得失敗時はNone
        
    Example:
        >>> screenshot = get_device_screenshot("127.0.0.1:62001")
        >>> if screenshot is not None:
        ...     print(f"Screenshot size: {screenshot.shape}")
    """
    current_time = time.time()
    
    # エラー状態のデバイスの処理
    if is_device_in_error_state(device_port) and not force_refresh:
        # エラー状態からの回復を一定時間後に試みる
        # RECOVERY_CHECK_INTERVAL時間経過後は強制的にリフレッシュ
        if True:  # 簡略化：常に回復を試みる
            # 強制的にリフレッシュ
            force_refresh = True
        else:
            # 回復試行までは前回のキャッシュを使用（存在する場合）
            if device_port in _last_screenshot:
                return _last_screenshot[device_port]
            return None
    
    # キャッシュの有効期限チェック
    cache_valid = (
        not force_refresh and 
        device_port in _last_screenshot and 
        current_time - _last_screenshot_time.get(device_port, 0) < min(cache_time, MAX_SCREENSHOT_CACHE_AGE)
    )
    
    if cache_valid:
        return _last_screenshot[device_port]
    
    # 新しいスクリーンショットの取得を試みる
    try:
        # デバイス接続確認（改良版）
        devices_cmd = [NOX_ADB_PATH, "devices"]
        try:
            devices_output = subprocess.check_output(devices_cmd, stderr=subprocess.PIPE, timeout=8)
            if device_port.encode() not in devices_output:
                # デバイス再接続試行
                reconnect_cmd = [NOX_ADB_PATH, "connect", device_port]
                subprocess.run(reconnect_cmd, capture_output=True, timeout=5)
                time.sleep(1)
                # 再確認
                devices_output = subprocess.check_output(devices_cmd, stderr=subprocess.PIPE, timeout=5)
                if device_port.encode() not in devices_output:
                    raise subprocess.SubprocessError(f"Device {device_port} not found after reconnect")
        except subprocess.TimeoutExpired:
            # ADBサーバーリセット
            subprocess.run([NOX_ADB_PATH, "kill-server"], capture_output=True, timeout=3)
            time.sleep(1)
            subprocess.run([NOX_ADB_PATH, "start-server"], capture_output=True, timeout=5)
            time.sleep(2)
            devices_output = subprocess.check_output(devices_cmd, stderr=subprocess.PIPE, timeout=8)
            if device_port.encode() not in devices_output:
                raise subprocess.SubprocessError(f"Device {device_port} not found after ADB reset")
        
        # スクリーンショット取得（リトライ機能付き）
        max_retries = 3
        for attempt in range(max_retries):
            try:
                cmd = [NOX_ADB_PATH, "-s", device_port, "exec-out", "screencap", "-p"]
                screenshot_data = subprocess.check_output(cmd, stderr=subprocess.PIPE, timeout=30)
                
                if not screenshot_data:
                    if attempt < max_retries - 1:
                        time.sleep(0.5)
                        continue
                    raise subprocess.SubprocessError("Empty screenshot data after retries")
                
                img_array = np.frombuffer(screenshot_data, np.uint8)
                img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
                
                if img is None or img.size == 0:
                    if attempt < max_retries - 1:
                        time.sleep(0.5)
                        continue
                    raise subprocess.SubprocessError("Failed to decode screenshot after retries")
                
                break  # 成功したらループを抜ける
                
            except subprocess.CalledProcessError as e:
                if attempt < max_retries - 1:
                    time.sleep(0.5)
                    continue
                raise subprocess.SubprocessError(f"Screenshot command failed: {e}")
            except subprocess.TimeoutExpired:
                if attempt < max_retries - 1:
                    time.sleep(1)
                    continue
                raise subprocess.SubprocessError("Screenshot timeout after retries")

        # キャッシュ更新
        with _screenshot_lock:
            _last_screenshot[device_port] = img
            _last_screenshot_time[device_port] = current_time

        # 正常に取得できたら連続失敗カウンターをリセット
        _consecutive_failures[device_port] = 0
        
        # メモリ管理: 定期的にガベージコレクションを実行
        global _memory_check_counter
        _memory_check_counter += 1
        if _memory_check_counter >= MEMORY_CHECK_INTERVAL:
            _memory_check_counter = 0
            # 古いキャッシュを削除
            with _screenshot_lock:
                current_time_check = time.time()
                expired_devices = []
                for device, last_time in _last_screenshot_time.items():
                    if current_time_check - last_time > MAX_SCREENSHOT_CACHE_AGE * 2:  # 2倍の時間が経過
                        expired_devices.append(device)
                
                for device in expired_devices:
                    if device in _last_screenshot:
                        del _last_screenshot[device]
                    if device in _last_screenshot_time:
                        del _last_screenshot_time[device]
                        
            # ガベージコレクション実行
            gc.collect()
        
        # 正常に取得できたら回復とマーク
        if is_device_in_error_state(device_port):
            mark_device_recovered(device_port)
            
        return img

    except (subprocess.TimeoutExpired, subprocess.CalledProcessError, subprocess.SubprocessError, FileNotFoundError, MemoryError, OSError) as e:
        # 連続失敗カウンターを更新
        _consecutive_failures[device_port] = _consecutive_failures.get(device_port, 0) + 1
        _last_failure_time[device_port] = current_time
        
        # エラーメッセージの改善（頻繁なログを抑制）
        if "not found" in str(e).lower() or "after reconnect" in str(e).lower():
            # デバイス接続失敗時はDEBUGレベルでログ出力（完全に抑制）
            logger.debug(f"デバイス {device_port} への接続に失敗: {e}")
        elif "timeout" in str(e).lower():
            # タイムアウトエラーは20回に1回だけログ出力（さらに抑制）
            if _consecutive_failures.get(device_port, 0) % 20 == 0:
                logger.warning(f"スクリーンショット取得タイムアウト ({device_port}): 連続{_consecutive_failures.get(device_port, 0)}回")
        elif "memory" in str(e).lower() or isinstance(e, MemoryError):
            # メモリエラーは即座にログ出力し、緊急メモリ清理を実行
            logger.error(f"メモリ不足エラー ({device_port}): {e}")
            # 緊急メモリ清理
            with _screenshot_lock:
                _last_screenshot.clear()
                _last_screenshot_time.clear()
            gc.collect()
        elif "empty" in str(e).lower() or "decode" in str(e).lower():
            # データエラーは10回に1回だけログ出力（さらに抑制）
            if _consecutive_failures.get(device_port, 0) % 10 == 0:
                logger.warning(f"スクリーンショット取得エラー ({device_port}): {e}")
        else:
            # その他のエラーは5回に1回だけログ出力（抑制）
            if _consecutive_failures.get(device_port, 0) % 5 == 0:
                logger.warning(f"スクリーンショット取得エラー ({device_port}): {e}")
        
        consecutive_count = _consecutive_failures[device_port]
        
        # 連続失敗が7回以上の場合は確実にエラーとして扱う
        if consecutive_count >= 7:
            error_msg = f"連続失敗{consecutive_count}回: {str(e)}"
            mark_device_error(device_port, error_msg)
        # 3分以内に5回失敗した場合もエラーとして扱う
        elif consecutive_count >= 5:
            first_failure_time = _last_failure_time.get(device_port, current_time)
            if current_time - first_failure_time <= 180:  # 3分以内
                error_msg = f"短時間内連続失敗{consecutive_count}回: {str(e)}"
                mark_device_error(device_port, error_msg)
        
        # 前回のキャッシュがあれば使用
        if device_port in _last_screenshot:
            return _last_screenshot[device_port]
        return None

def find_image_on_device_enhanced(
    device_port: str, 
    image_name: str, 
    *subfolders: str,
    force_refresh: bool = True,
    multi_threshold: bool = True
) -> Tuple[Optional[int], Optional[int]]:
    """ULTRATHINK版: 強化された画像検索関数
    
    Args:
        device_port: デバイスポート
        image_name: 探す画像ファイル名
        subfolders: 画像のサブフォルダ（可変長）
        force_refresh: 強制的にスクリーンショットを更新
        multi_threshold: 複数閾値で検索を試行
        
    Returns:
        見つかった座標のタプル、見つからない場合は(None, None)
    """
    try:
        # 強制的に最新のスクリーンショットを取得（エラー状態無視）
        screenshot = get_device_screenshot(device_port, cache_time=0, force_refresh=force_refresh)
        if screenshot is None:
            # エラー状態でも再試行
            logger.debug(f"[ULTRATHINK] スクリーンショット取得失敗、再試行中... ({device_port})")
            time.sleep(0.5)
            screenshot = get_device_screenshot(device_port, cache_time=0, force_refresh=True)
            if screenshot is None:
                return None, None

        # グレースケール変換
        gray_screenshot = cv2.cvtColor(screenshot, cv2.COLOR_BGR2GRAY)
        
        # テンプレート画像読み込み
        target_image_path = get_image_path(image_name, *subfolders)
        template = _get_template_gray(target_image_path)
        
        if template is None:
            logger.error(f"[ULTRATHINK] テンプレート画像が見つかりません: {target_image_path}")
            return None, None
        
        # マルチ閾値検索
        thresholds_to_try = [0.9, 0.8, 0.75, 0.7, 0.65] if multi_threshold else [0.8]
        
        max_confidence_found = 0.0
        best_coords = None
        
        for threshold in thresholds_to_try:
            # テンプレートマッチング実行
            res = cv2.matchTemplate(gray_screenshot, template, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, max_loc = cv2.minMaxLoc(res)
            
            # 最高信頼度を記録
            if max_val > max_confidence_found:
                max_confidence_found = max_val
                best_coords = (max_loc[0] + (template.shape[1] // 2), max_loc[1] + (template.shape[0] // 2))
            
            if max_val >= threshold:
                # より精密な座標計算
                center_x = max_loc[0] + (template.shape[1] // 2)
                center_y = max_loc[1] + (template.shape[0] // 2)
                
                return center_x, center_y
        
        logger.debug(f"[ULTRATHINK] {image_name}が見つかりませんでした (最高信頼度: {max_confidence_found:.3f})")
        return None, None
        
    except Exception as e:
        logger.error(f"[ULTRATHINK] 強化画像検索エラー ({image_name}): {e}")
        return None, None

def find_image_on_device(
    device_port: str, 
    image_name: str, 
    *subfolders: str,
    cache_time: float = 2.0, 
    threshold: float = 0.8
) -> Tuple[Optional[int], Optional[int]]:
    """デバイス画面で画像を探します（従来版）
    
    Args:
        device_port: デバイスポート
        image_name: 探す画像ファイル名
        subfolders: 画像のサブフォルダ（可変長）
        cache_time: キャッシュ有効期間（秒）
        threshold: マッチング閾値
        
    Returns:
        見つかった座標のタプル、見つからない場合は(None, None)
        
    Example:
        >>> x, y = find_image_on_device("127.0.0.1:62001", "ok.png", "ui")
        >>> if x is not None and y is not None:
        ...     print(f"Found at ({x}, {y})")
    """
    # スクリーンショット取得
    eff_cache = cache_time
    try:
        if any(str(sf).lower() == 'login' for sf in subfolders):
            eff_cache = min(cache_time, 0.5)
    except Exception:
        pass
    screenshot = get_device_screenshot(device_port, eff_cache)
    if screenshot is None:
        return None, None

    # 画像認識処理
    try:
        # グレースケール変換
        gray_screenshot = cv2.cvtColor(screenshot, cv2.COLOR_BGR2GRAY)
        
        # テンプレート画像読み込み
        target_image_path = get_image_path(image_name, *subfolders)
        template = _get_template_gray(target_image_path)
        
        if template is None:
            logger.error(f"テンプレート画像が見つかりません: {target_image_path}")
            return None, None
        
        # テンプレートマッチング実行
        res = cv2.matchTemplate(gray_screenshot, template, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(res)
        
        # 閾値以上のマッチがあれば座標を返す
        if max_val >= threshold:
            center_x = max_loc[0] + (template.shape[1] // 2)
            center_y = max_loc[1] + (template.shape[0] // 2)
            return center_x, center_y
            
    except (MemoryError, OSError) as e:
        # メモリ不足エラーの場合は特別処理
        if "memory" in str(e).lower() or isinstance(e, MemoryError):
            logger.error(f"画像検索中にメモリ不足エラーが発生しました: {e}")
            # 緊急メモリ清理
            with _screenshot_lock:
                _last_screenshot.clear()
                _last_screenshot_time.clear()
            gc.collect()
        else:
            logger.error(f"画像検索中にシステムエラーが発生しました: {e}")
            
        # NOXフリーズの可能性があるエラーを自動復旧システムに報告
        from .device_management import mark_device_error
        mark_device_error(device_port, f"画像検索システムエラー: {e} (画像: {image_name})")
        
    except Exception as e:
        error_msg = f"画像検索エラー: {e} (画像: {image_name})"
        logger.error(f"画像検索中にエラーが発生しました: {e} (画像: {image_name})")
        
        # NOXフリーズの可能性があるエラーを自動復旧システムに報告
        from .device_management import mark_device_error
        mark_device_error(device_port, error_msg)
    
    return None, None

def find_and_tap_image(
    device_port: str, 
    image_name: str, 
    *subfolders: str,
    cache_time: float = 2.0, 
    threshold: float = 0.8
) -> Tuple[Optional[int], Optional[int]]:
    """画像を探し、見つかれば座標を返します。
    
    Args:
        device_port: デバイスポート
        image_name: 検索する画像のファイル名
        subfolders: 画像を検索するサブフォルダパス
        cache_time: キャッシュの有効期間（秒）
        threshold: マッチングの閾値
        
    Returns:
        座標タプル、見つからなければ(None, None)
        
    Example:
        >>> x, y = find_and_tap_image("127.0.0.1:62001", "button.png", "ui")
        >>> if x is not None and y is not None:
        ...     # perform_action でタップ実行
        ...     pass
    """
    try:
        # スクリーンショット取得 - force_refreshフラグを追加
        force_refresh = is_device_in_error_state(device_port)
        eff_cache = cache_time
        try:
            if any(str(sf).lower() == 'login' for sf in subfolders):
                eff_cache = min(cache_time, 0.5)
        except Exception:
            pass
        screenshot = get_device_screenshot(device_port, eff_cache, force_refresh=force_refresh)
        
        if screenshot is None:
            # エラーログを削除してDEBUGレベルに変更
            logger.debug(f"スクリーンショット取得失敗: {device_port}")
            return None, None

        # グレースケール変換
        gray_screenshot = cv2.cvtColor(screenshot, cv2.COLOR_BGR2GRAY)
        
        # テンプレート画像読み込み
        target_image_path = get_image_path(image_name, *subfolders)
        template = _get_template_gray(target_image_path)

        if template is None:
            logger.error(f"テンプレート画像が見つかりません: {target_image_path}")
            return None, None

        # テンプレートマッチング実行
        try:
            res = cv2.matchTemplate(gray_screenshot, template, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, max_loc = cv2.minMaxLoc(res)

            # マッチング閾値チェック
            if max_val >= threshold:
                # 中心座標を計算
                center_x = max_loc[0] + (template.shape[1] // 2)
                center_y = max_loc[1] + (template.shape[0] // 2)
                return center_x, center_y
        except Exception as match_err:
            return None, None

    except Exception as e:
        logger.error(f"画像検索中にエラーが発生しました: {e}")
        return None, None
    
    # 明示的にデフォルトの戻り値を返す
    return None, None

def find_image_count(
    device_port: str, 
    image_name: str, 
    required_count: int,
    threshold: float = 0.75, 
    folder: str = ""
) -> bool:
    """指定された画像が画面上に指定回数以上見つかるかを確認します。
    
    Args:
        device_port: デバイスポート
        image_name: 検索する画像ファイル名
        required_count: 必要な検出回数
        threshold: マッチング閾値
        folder: 画像フォルダ
        
    Returns:
        指定回数以上見つかったかどうか
        
    Example:
        >>> # 画面上に"ok.png"が3個以上あるかチェック
        >>> found = find_image_count("127.0.0.1:62001", "ok.png", 3)
        >>> if found:
        ...     print("3個以上見つかりました")
    """
    try:
        # スクリーンショットを取得
        screenshot = get_device_screenshot(device_port, cache_time=1.0, force_refresh=True)
        if screenshot is None:
            return False
            
        gray_screenshot = cv2.cvtColor(screenshot, cv2.COLOR_BGR2GRAY)
        
        # テンプレート画像読み込み
        target_image_path = get_image_path(image_name, folder)
        template = _get_template_gray(target_image_path)
        
        if template is None:
            logger.error(f"テンプレート画像が見つかりません: {target_image_path}")
            return False
        
        # テンプレートマッチング実行
        res = cv2.matchTemplate(gray_screenshot, template, cv2.TM_CCOEFF_NORMED)
        
        # 閾値以上のマッチング位置を特定
        locations = np.where(res >= threshold)
        
        # 近接マッチを統合（重複排除）
        matches = set()
        min_distance = max(template.shape[0], template.shape[1]) // 2
        
        for pt in zip(*locations[::-1]):  # (x, y) 形式に変換
            # 既存のマッチと十分離れているか確認
            is_new = True
            for existing_pt in matches:
                dist = np.sqrt((pt[0] - existing_pt[0])**2 + (pt[1] - existing_pt[1])**2)
                if dist < min_distance:
                    is_new = False
                    break
            
            if is_new:
                matches.add(pt)
        
        # 一致数が必要数以上あるか確認
        return len(matches) >= required_count
        
    except Exception as e:
        logger.error(f"画像検出カウント中にエラーが発生しました: {e}")
        return False

def tap_if_found(
    action: str, 
    device_port: str, 
    image_name: str, 
    *subfolders: str,
    cache_time: float = 2.0, 
    threshold: float = 0.8,
    max_y: Optional[int] = None
) -> bool:
    """画像が見つかった場合にタップします。
    
    Args:
        action: 実行するアクション ('tap', 'swipe_down', 'swipe_up', 'stay')
        device_port: デバイスポート
        image_name: 検索する画像のファイル名
        subfolders: 画像を検索するサブフォルダパス
        cache_time: キャッシュの有効期間（秒）
        threshold: マッチングの閾値
        
    Returns:
        アクション実行の成功/失敗
        
    Example:
        >>> # "ok.png"が見つかったらタップ
        >>> success = tap_if_found('tap', "127.0.0.1:62001", "ok.png", "key")
        >>> if success:
        ...     print("タップしました")
    """
    from monst.adb import perform_action
    from .device_management import recover_device
    
    time.sleep(0.1)
    
    # エラー状態のデバイスで特別処理
    if is_device_in_error_state(device_port):
        # 回復試行回数の上限チェック
        from .device_management import _recovery_attempts, MAX_RECOVERY_ATTEMPTS
        
        # 回復試行回数が上限に達している場合は処理をスキップ
        if _recovery_attempts.get(device_port, 0) >= MAX_RECOVERY_ATTEMPTS:
            return False
        
        # エラー状態が長く続いている場合は自動回復を試みる
        try:
            reset_success = recover_device(device_port)
            # recover_device内で既に2行ログを出力するので、ここでは追加ログ不要
            if not reset_success:
                return False
        except Exception as e:
            logger.error(f"自動回復中にエラー: {e}")
            return False
    
    # 画像検索 - 安全なタプルアンパック
    try:
        result = find_and_tap_image(device_port, image_name, *subfolders, cache_time=cache_time, threshold=threshold)
        # 確実にタプルを取得
        if result is not None and len(result) == 2:
            x, y = result
        else:
            x, y = None, None
    except Exception as unpack_error:
        logger.error(f"画像検索結果のアンパックエラー: {unpack_error}")
        x, y = None, None
    
    # 見つからなかった場合、キャッシュを使わずに再試行
    if x is None and y is None and cache_time > 0:
        try:
            result = find_and_tap_image(device_port, image_name, *subfolders, cache_time=0, threshold=threshold)
            if result is not None and len(result) == 2:
                x, y = result
            else:
                x, y = None, None
        except Exception as unpack_error:
            logger.error(f"再試行時のアンパックエラー: {unpack_error}")
            x, y = None, None
    
    if x is not None and y is not None:
        # Y座標制限チェック（キャラアイコンクリック防止）
        if max_y is not None and y > max_y:
            return False  # 指定Y座標より下の場合はスキップ
        
        try:
            # タップアクションごとの処理
            if action == 'tap':
                result = perform_action(device_port, action, x, y, duration=150)
            elif action == 'swipe_down':
                result = perform_action(device_port, 'swipe', x, y, x, y+100, duration=300)
            elif action == 'swipe_up':
                result = perform_action(device_port, 'swipe', x, y, x, y-100, duration=1500)
            elif action == 'stay':
                time.sleep(0.5)
                result = True
            else:
                logger.error(f"無効なアクション: {action}")
                return False
            
            # アクション成功時はキャッシュを削除
            if result:
                if device_port in _last_screenshot:
                    del _last_screenshot[device_port]
                return True
            else:
                logger.warning(f"アクション '{action}' の実行に失敗: デバイス {device_port}")
                return False
                
        except Exception as e:
            logger.error(f"アクション実行中にエラー: {e}")
            return False

    return False
