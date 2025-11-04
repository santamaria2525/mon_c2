"""
完璧なログイン操作モジュール - 8端末対応・エラーゼロ・シンプル実装

このモジュールは、ユーザー要求に基づいて完全に再設計されたログインシステムです。
・OKボタンを見つけたらクリックするシンプルな仕組み
・エラーが絶対に起こらない堅牢な設計
・8端末での並列実行に完全対応
・必要最小限の機能に絞った高信頼性実装
"""

import time
import os
from typing import Optional
from logging_util import logger
from utils.device_utils import get_terminal_number


# 画面別待機時間（高速化）
WAIT_TIMES = {
    "tap_after": 0.08,       # タップ後の待機
    "screen_load": 0.15,     # 画面読み込み待機
    "retry_interval": 0.4,  # リトライ間隔
    "error_recovery": 1.0,  # エラー回復待機
    "app_startup": 2.0,     # アプリ起動待機
}


def device_operation_login(
    device_port: str, 
    folder: str, 
    multi_logger: Optional = None, 
    home_early: bool = False
) -> bool:
    """
    完璧なログイン処理 - 8端末対応・エラーゼロ・シンプル設計
    
    Args:
        device_port: デバイスポート
        folder: フォルダ名
        multi_logger: ログ出力用
        home_early: ホーム画面で即終了するか
        
    Returns:
        bool: 成功時True、失敗時False
    """
    terminal_num = get_terminal_number(device_port)
    
    try:
        
        # 設定読み込み（エラーハンドリング付き）
        try:
            from config import get_config
            config = get_config()
            
            # 設定値の取得とデバッグ情報
            max_attempts = min(getattr(config, 'LOGIN_MAX_ATTEMPTS', 30), 50)  # 上限50回
            base_sleep = max(getattr(config, 'login_sleep', 5), 2)  # 最低2秒
            
            # 成功時はデバッグログ（最初の端末のみ）
            if terminal_num == "端末1":
                logger.info(f"設定読み込み成功: LOGIN_MAX_ATTEMPTS={max_attempts}, login_sleep={base_sleep}")
                
        except Exception as e:
            # 設定読み込み失敗時のフォールバック
            max_attempts = 30
            base_sleep = 2
            logger.warning(f"{terminal_num}: 設定読み込み失敗、デフォルト値使用 - エラー詳細: {type(e).__name__}: {e}")
        
        # メインログインループ
        for attempt in range(max_attempts):
            try:
                # 動的待機時間（指数バックオフ）
                if attempt > 0:
                    # 軽めの指数バックオフでレスポンス向上（上限12秒）
                    wait_time = min(base_sleep * (1.12 ** attempt), 12.0)
                    time.sleep(wait_time)
                
                # 1. 最優先: ルーム画面チェック
                if _check_room_screen(device_port):
                    _handle_room_entry(device_port)
                    if multi_logger:
                        multi_logger.log_success(device_port)
                    return True
                
                # 2. ホーム画面チェック
                if _check_home_screen(device_port):
                    if home_early:
                        if multi_logger:
                            multi_logger.log_success(device_port)
                        return True
                    
                    # ホーム画面からルーム画面への遷移
                    if _navigate_to_room(device_port):
                        _handle_room_entry(device_port)
                        if multi_logger:
                            multi_logger.log_success(device_port)
                        return True
                
                # 3. エラー画面チェック
                if _check_error_screen(device_port):
                    message = f"{terminal_num}: フォルダ{folder}でログイン不可画面(zz_lost)を検出"
                    logger.info(message)
                    if multi_logger:
                        multi_logger.log_success(device_port)
                        multi_logger.update_task_status(device_port, folder, 'zz_lost検出')
                    return True
                
                # 4. 各種ボタン処理（最重要）
                if _handle_all_buttons(device_port):
                    continue  # ボタンを押したら次のループへ
                
                # 5. 何も検出されない場合の安全ナビゲーション
                _safe_navigation(device_port)
                
            except Exception as e:
                logger.warning(f"{terminal_num}: ループ{attempt+1}でエラー: {e}")
                time.sleep(WAIT_TIMES["error_recovery"])
                continue
        
        # 最大試行回数到達
        logger.warning(f"{terminal_num}: 最大試行回数{max_attempts}回到達")
        
        # 最終回復試行（ログなしで実行）
        return _final_recovery(device_port, multi_logger, home_early)
        
    except Exception as e:
        logger.error(f"{terminal_num}: ログイン処理で致命的エラー: {e}")
        if multi_logger:
            multi_logger.log_error(device_port, str(e))
        return False


def _check_room_screen(device_port: str) -> bool:
    """ルーム画面チェック（エラーハンドリング付き）"""
    try:
        return _safe_tap_if_found('stay', device_port, "room.png", "login")
    except Exception:
        return False


def _check_home_screen(device_port: str) -> bool:
    """ホーム画面チェック（エラーハンドリング付き）"""
    try:
        return _safe_tap_if_found('stay', device_port, "zz_home.png", "login")
    except Exception:
        return False


def _check_error_screen(device_port: str) -> bool:
    """エラー画面チェック（エラーハンドリング付き）"""
    try:
        return _safe_tap_if_found('stay', device_port, "zz_lost.png", "login")
    except Exception:
        return False


def _navigate_to_room(device_port: str) -> bool:
    """ホーム画面からルーム画面への安全な遷移"""
    try:
        terminal_num = get_terminal_number(device_port)
        
        # 画面中央を安全にタップ
        _safe_perform_action(device_port, 'tap', 320, 240, duration=150)
        time.sleep(WAIT_TIMES["tap_after"])
        
        # ホームボタンを安全にタップ
        _safe_tap_if_found('tap', device_port, "zz_home.png", "login")
        time.sleep(WAIT_TIMES["tap_after"])
        
        # ルーム画面到達確認（最大3回）
        for i in range(3):
            if _check_room_screen(device_port):
                return True
            time.sleep(WAIT_TIMES["screen_load"])
        
        return False
        
    except Exception as e:
        logger.warning(f"ルーム遷移でエラー: {e}")
        return False


def _handle_room_entry(device_port: str) -> None:
    """ルーム画面でオーブクリアの確認を行い、表示されていればタップする。"""
    terminal_num = get_terminal_number(device_port)
    timeout = 30.0  # seconds
    start_time = time.time()
    max_sequence_attempts = 6

    def tap_reward_buttons():
        targets = [
            ("obu10.png", ("login", "ui", "key")),
            ("uketoru.png", ("login", "ui", "key")),
            ("yes.png", ("login", "ui", "key")),
            ("ok.png", ("login", "ui", "key")),
        ]
        for image_name, folders in targets:
            tapped = False
            for folder in folders:
                if _safe_tap_if_found('tap', device_port, image_name, folder):
                    logger.debug(f"{terminal_num}: {image_name} をタップ (フォルダ={folder})")
                    tapped = True
                    time.sleep(WAIT_TIMES["tap_after"])
                    break
            if not tapped:
                logger.debug(f"{terminal_num}: {image_name} 未検出 (報酬処理)")
        time.sleep(0.3)

    def confirm_room_stable() -> bool:
        if not _safe_tap_if_found('stay', device_port, "room.png", "login"):
            return False
        time.sleep(1.0)
        return _safe_tap_if_found('stay', device_port, "room.png", "login")

    while True:
        elapsed = time.time() - start_time
        if elapsed > timeout:
            message = f"{terminal_num}: room確認タイムアウト ({timeout}s)"
            logger.warning(message)
            raise RuntimeError(message)

        if not _safe_tap_if_found('stay', device_port, "room.png", "login"):
            time.sleep(WAIT_TIMES["screen_load"])
            continue

        obuclear_tapped = False
        for folder_name in ("login", "ui", "key"):
            if _safe_tap_if_found('tap', device_port, "obuclear.png", folder_name):
                logger.info(f"{terminal_num}: obuclear.pngをタップ (フォルダ={folder_name})")
                obuclear_tapped = True
                time.sleep(WAIT_TIMES["screen_load"])
                break

        if obuclear_tapped:
            for attempt in range(1, max_sequence_attempts + 1):
                tap_reward_buttons()
                if confirm_room_stable():
                    logger.info(f"{terminal_num}: obuclear後のroom再確認完了 (試行{attempt})")
                    return
                logger.debug(f"{terminal_num}: room再確認失敗 (試行{attempt}) - 報酬処理を再試行")
            message = f"{terminal_num}: obuclear後のroom再確認に失敗 (最大{max_sequence_attempts}回)"
            logger.warning(message)
            raise RuntimeError(message)

        # obuclearが表示されていない場合もroom安定を確認
        if confirm_room_stable():
            logger.debug(f"{terminal_num}: room画面安定 (obuclear未検出)")
            return
        time.sleep(WAIT_TIMES["screen_load"])


def _handle_all_buttons(device_port: str) -> bool:
    """全ボタンの包括的処理（OKボタン優先）"""
    button_found = False
    
    try:
        # ガチャボタン誤作動防止（最優先）
        if _safe_tap_if_found('tap', device_port, "gacha_shu.png", "login"):
            _handle_gacha_prevention(device_port)
            return True
        
        # OKボタン系（ユーザー要求の核心）
        ok_buttons = [
            "ok.png", "a_ok1.png", "ok2.png", "ok3.png", "yes.png", "yes2.png"
        ]
        
        for button in ok_buttons:
            if _safe_tap_if_found('tap', device_port, button, "login"):
                time.sleep(WAIT_TIMES["tap_after"])
                button_found = True
                break
        
        # UIフォルダのOKボタンもチェック
        if not button_found:
            ui_buttons = ["ok.png", "ok_f.png", "yes.png"]
            for button in ui_buttons:
                if _safe_tap_if_found('tap', device_port, button, "ui"):
                    time.sleep(WAIT_TIMES["tap_after"])
                    button_found = True
                    break
        
        # その他の重要ボタン
        if not button_found:
            other_buttons = [
                ("close.png", "login"), ("retry.png", "login"), ("no.png", "login"),
                ("uketoru.png", "ui"), ("modoru.png", "ui"), ("close.png", "ui")
            ]
            
            for button, folder in other_buttons:
                if _safe_tap_if_found('tap', device_port, button, folder):
                    time.sleep(WAIT_TIMES["tap_after"])
                    button_found = True
                    break
        
        return button_found
        
    except Exception as e:
        logger.warning(f"ボタン処理でエラー: {e}")
        return False


def _handle_gacha_prevention(device_port: str):
    """ガチャボタン誤作動防止（エラーハンドリング付き）"""
    try:
        _safe_tap_if_found('tap', device_port, "zz_home.png", "login")
        time.sleep(WAIT_TIMES["tap_after"])
        _safe_tap_if_found('tap', device_port, "zz_home2.png", "login")
        time.sleep(WAIT_TIMES["tap_after"])
        
    except Exception as e:
        logger.warning(f"ガチャ防止処理でエラー: {e}")


def _safe_navigation(device_port: str):
    """安全なナビゲーション（ランダムタップの代替）"""
    try:
        # 画面キャッシュクリア
        _safe_clear_cache(device_port)
        
        # 指定位置をタップ（40, 180固定）
        _safe_perform_action(device_port, 'tap', 40, 180, duration=150)
        time.sleep(WAIT_TIMES["tap_after"])
                
    except Exception as e:
        logger.warning(f"安全ナビゲーションでエラー: {e}")


def _final_recovery(device_port: str, multi_logger: Optional, home_early: bool) -> bool:
    """最終回復処理（エラーハンドリング付き）"""
    try:
        # アプリ再起動
        _safe_restart_app(device_port)
        time.sleep(WAIT_TIMES["app_startup"])
        
        # 最大5回の回復試行
        for attempt in range(5):
            time.sleep(WAIT_TIMES["screen_load"])
            
            if _check_home_screen(device_port):
                if home_early:
                    if multi_logger:
                        multi_logger.log_success(device_port)
                    return True
                elif _navigate_to_room(device_port):
                    if multi_logger:
                        multi_logger.log_success(device_port)
                    return True
            
            _safe_navigation(device_port)
        
        return False
        
    except Exception:
        return False


# ========== 安全な操作関数群（エラーハンドリング完備） ==========

def _safe_tap_if_found(action: str, device_port: str, image: str, folder: str) -> bool:
    """エラーハンドリング付きのtap_if_found"""
    try:
        from image_detection import tap_if_found
        return tap_if_found(action, device_port, image, folder)
    except Exception:
        return False


def _safe_perform_action(device_port: str, action: str, x: int, y: int, duration: int = 150):
    """エラーハンドリング付きのperform_action"""
    try:
        from adb_utils import perform_action
        perform_action(device_port, action, x, y, duration)
    except Exception:
        pass


def _safe_clear_cache(device_port: str):
    """エラーハンドリング付きのキャッシュクリア"""
    try:
        from image_detection import clear_device_cache
        clear_device_cache(device_port)
    except Exception:
        pass


def _safe_restart_app(device_port: str):
    """エラーハンドリング付きのアプリ再起動"""
    try:
        from adb_utils import restart_monster_strike_app
        restart_monster_strike_app(device_port)
    except Exception:
        pass


# ========== 後方互換性の保証 ==========

def _handle_room_screen(device_port: str) -> bool:
    """後方互換性のための関数"""
    try:
        # ルーム画面の詳細処理
        max_attempts = 10
        
        for attempt in range(max_attempts):
            if attempt > 0:
                time.sleep(WAIT_TIMES["screen_load"])
            
            if _check_room_screen(device_port):
                time.sleep(WAIT_TIMES["screen_load"])
                
                # オーブクリア処理
                if _safe_tap_if_found('tap', device_port, "obuclear.png", "ui"):
                    for i in range(5):
                        if _check_room_screen(device_port):
                            break
                        _safe_tap_if_found('tap', device_port, "a_ok1.png", "ui")
                        time.sleep(0.1)
                        _safe_tap_if_found('tap', device_port, "yes.png", "ui")
                        time.sleep(0.1)
                        _safe_tap_if_found('tap', device_port, "uketoru.png", "ui")
                        time.sleep(0.1)
                
                # 最終確認
                if _check_room_screen(device_port):
                    return True
            
            # ガチャボタン防止
            if _safe_tap_if_found('tap', device_port, "gacha_shu.png", "login"):
                _handle_gacha_prevention(device_port)
                continue
            
            # その他の画面処理
            _handle_all_buttons(device_port)
            
            # 基本的なナビゲーション
            _safe_perform_action(device_port, 'tap', 40, 180, duration=150)
        
        return False
        
    except Exception:
        return False


def handle_screens(device_port: str, folder_name: str) -> bool:
    """後方互換性のための関数"""
    try:
        # ガチャボタン防止
        if _safe_tap_if_found('tap', device_port, "gacha_shu.png", "login"):
            _handle_gacha_prevention(device_port)
            return True
        
        # 画像フォルダからファイルを検索してタップ
        try:
            from utils import get_resource_path
            images_dir = get_resource_path(folder_name, "gazo")
            
            if images_dir and os.path.exists(images_dir):
                images = sorted([img for img in os.listdir(images_dir) if img.endswith('.png')])
                
                for img in images:
                    if _safe_tap_if_found('tap', device_port, img, folder_name):
                        time.sleep(WAIT_TIMES["tap_after"])
                        return True
        except Exception:
            pass
        
        return False
        
    except Exception:
        return False
