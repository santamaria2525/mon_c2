"""
monst.device.hasya - 覇者の塔関連の操作（mon6完全準拠版）

mon6フォルダの device_operations.py の覇者実装を完全移植
"""

from __future__ import annotations

import time
from typing import Optional

from logging_util import logger, MultiDeviceLogger
from login_operations import device_operation_login
from monst.adb import perform_action, send_key_event
from monst.image import tap_if_found, tap_until_found, tap_if_found_on_windows, tap_until_found_on_windows
from utils import send_notification_email, replace_multiple_lines_in_file, activate_window_and_right_click
from config import room_key1, room_key2

def device_operation_hasya(
    device_port: str, 
    folder: str, 
    multi_logger: Optional[MultiDeviceLogger] = None
) -> bool:
    """覇者の塔操作を実行します（mon6完全準拠）。
    
    Args:
        device_port: 対象デバイスのポート
        folder: フォルダ名
        multi_logger: マルチデバイスロガー（オプション）
        
    Returns:
        操作が成功したかどうか
    """
    try:
        if not device_operation_login(device_port, folder, multi_logger):
            logger.error(f"ログイン失敗 (フォルダ：{folder})")
            if multi_logger:
                multi_logger.log_error(device_port, f"ログイン失敗 (フォルダ：{folder})")
            return False

        while True:
            if tap_if_found('stay', device_port, "start.png", "quest"):
                if not tap_if_found('stay', device_port, "dekki_null2.png", "key"):
                    break
            if tap_if_found('stay', device_port, "event.png", "macro"):
                has_icon = tap_if_found('stay', device_port, "hasyatou_icon.png", "macro")
                if not has_icon:
                    logger.debug(f"覇者メニュー: hasyatou_icon.png 未検出のため端末 {device_port} で右→左スワイプを実行")
                    perform_action(device_port, 'swipe', 1100, 360, 200, 360, duration=3000)

            tap_if_found('tap', device_port, "quest_c.png", "key")
            tap_if_found('tap', device_port, "quest.png", "key")
            tap_if_found('tap', device_port, "ichiran.png", "key")
            tap_if_found('tap', device_port, "ok.png", "key")
            tap_if_found('tap', device_port, "close.png", "key")
            # 覇者の塔画像を複数チェック（セット1～6対応）
            hasya_images = ["hasyatou.png", "hasyatou2.png", "hasyatou3.png", "hasyatou4.png", "hasyatou5.png", "hasyatou6.png"]
            for hasya_img in hasya_images:
                tap_if_found('tap', device_port, hasya_img, "key")
            tap_if_found('tap', device_port, "shohi20.png", "key")
            tap_if_found('tap', device_port, "minnato.png", "key")
            tap_if_found('tap', device_port, "multi.png", "key")
            if tap_if_found('stay', device_port, "dekki_null2.png", "key"):
                tap_until_found(device_port, "go_tittle.png", "key", "sonota.png", "key", "tap")
                tap_until_found(device_port, "date_repear.png", "key", "go_tittle.png", "key", "tap")
                tap_until_found(device_port, "data_yes.png", "key", "date_repear.png", "key", "tap")
                tap_until_found(device_port, "zz_home.png", "key", "data_yes.png", "key", "tap")  
            time.sleep(2)

        suffixes = ('62025', '62026', '62027', '62029', '62030', '62031')
        if device_port.endswith(suffixes):
            tap_if_found('tap', device_port, "zz_home.png", "key")

        if multi_logger:
            multi_logger.log_success(device_port)
        return True

    except Exception as e:
        error_msg = f"{str(e)} (フォルダ：{folder})"
        logger.error(f"覇者の塔操作中にエラーが発生しました: {error_msg}", exc_info=True)
        if multi_logger:
            multi_logger.log_error(device_port, error_msg)
        return False

def device_operation_hasya_wait(
    device_port: str, 
    multi_logger: Optional[MultiDeviceLogger] = None
) -> bool:
    """覇者の塔待機処理を実行します（ホスト端末用・mon6完全準拠）。
    
    Args:
        device_port: 対象デバイスのポート
        multi_logger: マルチデバイスロガー（オプション）
        
    Returns:
        処理が成功したかどうか
    """
    start_time = time.time()
    timeout = 6 * 60 * 60  # 6時間（秒単位）
    
    logger.info(f"ホスト端末 {device_port}: アイコン待機処理を開始（最大6時間）")

    try:
        while True:
            # 6時間経過したか確認
            if time.time() - start_time > timeout:
                send_notification_email(
                    subject="ホスト端末停滞通知",
                    message=f"ホスト端末 {device_port} で6時間以内に覇者作業が完了しませんでした。",
                    to_email="naka1986222@gmail.com"
                )
                logger.warning(f"ホスト端末 {device_port}: 6時間タイムアウト")
                break

            # icon.png の検出処理（mon6元バージョン完全準拠・シンプル）
            if tap_if_found('tap', device_port, "icon.png", "key"):
                logger.info(f"ホスト端末 {device_port}: icon.png検出→8端末マクロ実行へ")
                break
            
            # デバッグ用：定期的にアイコン検索状況をログ出力
            if int(time.time() - start_time) % 600 == 0:  # 10分ごと
                logger.info(f"ホスト端末 {device_port}: アイコン検索中...({int((time.time() - start_time)/60)}分経過)")
            
            time.sleep(120)  # 2分間隔で再チェック

        if multi_logger:
            multi_logger.log_success(device_port)
        return True

    except Exception as e:
        error_msg = f"ホスト端末待機エラー: {str(e)}"
        logger.error(error_msg, exc_info=True)
        if multi_logger:
            multi_logger.log_error(device_port, error_msg)
        return False

def device_operation_hasya_fin(
    device_port: str, 
    multi_logger: Optional[MultiDeviceLogger] = None
) -> bool:
    """覇者の塔完了処理を実行します（サブ端末用・mon6完全準拠）。
    
    Args:
        device_port: 対象デバイスのポート
        multi_logger: マルチデバイスロガー（オプション）
        
    Returns:
        処理が成功したかどうか
    """
    start_time = time.time()
    timeout = 3 * 60  # 3分（秒単位）

    try:
        logger.info(f"サブ端末 {device_port}: 覇者完了検知を開始（最大3分）")
        
        while True:
            # 3分経過したか確認
            if time.time() - start_time > timeout:
                send_notification_email(
                    subject="タイムアウト通知",
                    message=f"サブ端末 {device_port} で3分以内に覇者finが見つかりませんでした。",
                    to_email="naka1986222@gmail.com"
                )
                logger.warning(f"サブ端末 {device_port}: 3分タイムアウト")
                break

            tap_if_found('tap', device_port, "icon.png", "key")
            tap_if_found('tap', device_port, "zz_home.png", "key")
            time.sleep(1)
            tap_if_found('tap', device_port, "quest_c.png", "key")
            tap_if_found('tap', device_port, "quest.png", "key")
            time.sleep(1)
            for _ in range(10):
                tap_if_found('tap', device_port, "a_ok1.png", "key")
                tap_if_found('tap', device_port, "a_ok2.png", "key")
                tap_if_found('tap', device_port, "close.png", "key")
            if (tap_if_found('tap', device_port, "hasyafin1.png", "key") or 
                tap_if_found('tap', device_port, "hasyafin2.png", "key") or 
                tap_if_found('tap', device_port, "hasyafin3.png", "key")):
                logger.info(f"サブ端末 {device_port}: 覇者完了検知成功")
                break
            time.sleep(1)

        if multi_logger:
            multi_logger.log_success(device_port)
        return True

    except Exception as e:
        error_msg = f"サブ端末覇者完了検知エラー: {str(e)}"
        logger.error(error_msg, exc_info=True)
        if multi_logger:
            multi_logger.log_error(device_port, error_msg)
        return False

def device_operation_hasya_host_fin(
    device_port: str, 
    multi_logger: Optional[MultiDeviceLogger] = None
) -> bool:
    """ホスト端末用の覇者の塔完了処理（終了検知機能付き）。
    
    旧バージョンの終了検知機構を再現：
    - ホスト端末での長時間待機と終了検知の組み合わせ
    - 6時間のタイムアウトまたはhasyafin画像の検出で終了
    
    Args:
        device_port: 対象デバイスのポート
        multi_logger: マルチデバイスロガー（オプション）
        
    Returns:
        処理が成功したかどうか
    """
    start_time = time.time()
    timeout = 6 * 60 * 60  # 6時間（秒単位）- ホスト端末用の長時間タイムアウト
    check_interval = 120  # 2分間隔でチェック

    try:
        logger.info(f"ホスト端末 {device_port}: 終了検知処理を開始（最大6時間）")
        
        while True:
            # 6時間経過したか確認
            if time.time() - start_time > timeout:
                send_notification_email(
                    subject="ホスト端末停滞通知", 
                    message=f"ホスト端末 {device_port} で6時間以内に覇者作業が完了しませんでした。",
                    to_email="naka1986222@gmail.com"
                )
                logger.warning(f"ホスト端末 {device_port}: 6時間タイムアウト")
                break

            # 基本的なUI操作（icon.pngチェック）
            if tap_if_found('tap', device_port, "icon.png", "key"):
                logger.info(f"ホスト端末 {device_port}: icon.png検出 - 基本処理継続")
                
            # ホーム画面への移動
            tap_if_found('tap', device_port, "zz_home.png", "key")
            time.sleep(1)
            
            # クエスト画面へのアクセス
            tap_if_found('tap', device_port, "quest_c.png", "key")
            tap_if_found('tap', device_port, "quest.png", "key")
            time.sleep(1)
            
            # OK/Closeボタンのクリア処理
            for _ in range(5):  # ホスト端末用に回数調整
                tap_if_found('tap', device_port, "a_ok1.png", "key")
                tap_if_found('tap', device_port, "a_ok2.png", "key")
                tap_if_found('tap', device_port, "close.png", "key")
            
            # **核心的な終了検知：hasyafin画像の検出**
            if (tap_if_found('tap', device_port, "hasyafin1.png", "key") or 
                tap_if_found('tap', device_port, "hasyafin2.png", "key") or 
                tap_if_found('tap', device_port, "hasyafin3.png", "key")):
                logger.info(f"ホスト端末 {device_port}: 覇者完了検知 - 処理終了")
                break
                
            # 次のチェックまで待機
            time.sleep(check_interval)

        if multi_logger:
            multi_logger.log_success(device_port)
        logger.info(f"ホスト端末 {device_port}: 終了検知処理完了")
        return True

    except Exception as e:
        error_msg = f"ホスト端末終了検知エラー: {str(e)}"
        logger.error(error_msg, exc_info=True)
        if multi_logger:
            multi_logger.log_error(device_port, error_msg)
        return False

def continue_hasya_parallel() -> None:
    """覇者継続処理を８端末並列実行します（８端末セット対応版）。"""
    import concurrent.futures
    import threading
    
    settings_file_9 = r"C:\Users\santa\Desktop\MM\[周回マクロ設定]\【設定】(9)保存した設定.txt"
    settings_file_10 = r"C:\Users\santa\Desktop\MM\[周回マクロ設定]\【設定】(10)保存した設定.txt"
    start_app = r"C:\Users\santa\Desktop\MM\start_app.exe"

    # 端末ごとの設定（８端末すべて）
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
    
    def process_device(device_config):
        """1端末の処理を実行（並列実行用）"""
        window_name, port, code, key, room_key, settings_file = device_config
        
        try:
            # ファイル書き換え処理
            success = False
            retries = 3

            for attempt in range(retries):
                try:
                    # mon6準拠の設定ファイル書き換え - 行番号を直接指定
                    changes = {
                        24: f"tar_device=127.0.0.1:{port}",
                        25: f"output= -P 50037 -s 127.0.0.1:{port}",  # 正しいADBポート
                        27: f"main_key={code}",
                        28: f"main_keyF={key}",
                        33: f"room_key={room_key}"
                    }
                    
                    # 端末4と8（ホスト処理）の場合の追加ログ
                    if window_name in ["4", "8"]:
                        logger.info(f"覇者並列：端末{window_name}はホスト処理モード（設定ファイル10使用）")
                    
                    result = replace_multiple_lines_in_file(settings_file, changes)
                    if result:
                        success = True
                        logger.info(f"覇者並列：設定ファイル更新成功: {window_name} (試行 {attempt + 1})")
                        break
                    else:
                        logger.warning(f"覇者並列：設定ファイル更新失敗: {window_name} (試行 {attempt + 1}): replace_multiple_lines_in_file returned False")
                except Exception as e:
                    logger.warning(f"覇者並列：設定ファイル更新失敗: {window_name} (試行 {attempt + 1}): {e}")
                    time.sleep(1)  # リトライ前に少し待機

            if not success:
                logger.error(f"覇者並列：設定ファイル更新に失敗しました: {window_name}")
                return False
                
            time.sleep(1)  # 書き換え後に少し待機

            # mon6と同じくアプリ起動
            try:
                import subprocess
                subprocess.run([start_app], check=False)  # mon6ではcheck=Falseを使用
                time.sleep(4)  # アプリ起動を待つ
            except Exception as e:
                logger.error(f"覇者並列：start_app.exe 実行エラー ({window_name}): {e}")
                return False

            # **load09.png と load10.png を条件で切り替え（mon6準拠）**
            load_image = "load10.png" if window_name in ["4", "8"] else "load09.png"

            # Windows画面上でのマクロ操作（mon6準拠）
            try:
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

                # ウィンドウをアクティブにして右クリック（mon6準拠）
                activate_window_and_right_click(window_name)
                logger.info(f"覇者並列：端末{window_name}の処理完了")
                return True
                
            except Exception as e:
                logger.error(f"覇者並列：Windows画面操作エラー ({window_name}): {e}")
                return False
                
        except Exception as e:
            logger.error(f"覇者並列：端末{window_name}処理中にエラー: {e}")
            return False
    
    # ８端末を並列で処理
    logger.info("覇者継続処理を８端末並列実行で開始")
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(process_device, device_config) for device_config in devices]
        results = [future.result() for future in concurrent.futures.as_completed(futures)]
    
    successful_count = sum(1 for result in results if result)
    logger.info(f"覇者継続処理完了：成功{successful_count}台 / 合計{len(devices)}台")

def continue_hasya_with_base_folder(base_folder: int) -> None:
    """覇者継続処理を1端末ずつ順次実行（フォルダベース指定版）"""
    logger.info(f"覇者継続処理を開始（フォルダ{base_folder}ベース）")
    
    # フォルダ書き換え処理（2セット目で+8フォルダ）
    from app.operations import write_account_folders
    write_account_folders(base_folder)
    logger.info(f"フォルダ書き換え完了: {base_folder}から8フォルダ")
    
    # start_app.exeの起動
    start_app = r"C:\Users\santa\Desktop\MM\start_app.exe"
    
    # ルームキー設定（config.jsonから読み込み済み）
    
    # 設定ファイルパス（端末4と8はホスト処理用に設定10を使用）
    settings_file_9 = r"C:\Users\santa\Desktop\MM\[周回マクロ設定]\【設定】(9)保存した設定.txt"
    settings_file_10 = r"C:\Users\santa\Desktop\MM\[周回マクロ設定]\【設定】(10)保存した設定.txt"
    
    # 8端末の設定情報（端末4,8はホスト処理対応）
    devices = [
        ("1", "62025", "81", "Q", room_key1, settings_file_9),
        ("2", "62026", "87", "W", room_key1, settings_file_9),
        ("3", "62027", "69", "E", room_key1, settings_file_9),
        ("4", "62028", "82", "R", room_key1, settings_file_10),  # ホスト処理用
        ("5", "62029", "65", "A", room_key2, settings_file_9),
        ("6", "62030", "83", "S", room_key2, settings_file_9),
        ("7", "62031", "68", "D", room_key2, settings_file_9),
        ("8", "62032", "70", "F", room_key2, settings_file_10)   # ホスト処理用
    ]

    # 1端末ずつ順次実行（mon6完全準拠）
    for number, (window_name, port, code, key, room_key, settings_file) in enumerate(devices, 1):
        logger.info(f"端末{number}の処理開始: フォルダ{base_folder + (number-1)} ({window_name})")
        
        # 1. 設定ファイル更新（この端末用）
        success = False
        retries = 3
        while not success and retries > 0:
            try:
                # ホスト処理用の特別設定を考慮
                changes = {
                    24: f"tar_device=127.0.0.1:{port}",
                    25: f"output= -P 50037 -s 127.0.0.1:{port}",  # 正しいADBポート
                    27: f"main_key={code}",
                    28: f"main_keyF={key}",
                    33: f"room_key={room_key}"
                }
                
                # 端末4と8（ホスト処理）の場合の追加設定
                if window_name in ["4", "8"]:
                    logger.info(f"端末{number}: ホスト処理モード（設定ファイル10使用）")
                
                replace_multiple_lines_in_file(settings_file, changes)
                success = True
                logger.info(f"端末{number}: 設定ファイル更新成功")
            except Exception as e:
                logger.error(f"端末{number}: 設定ファイル更新失敗: {e}")
                retries -= 1
                time.sleep(1)

        time.sleep(1)  # 設定更新後の待機

        # 2. start_app.exe実行
        try:
            import subprocess
            subprocess.run(start_app, check=True)
            logger.info(f"端末{number}: start_app.exe実行成功")
            time.sleep(3)  # start_app.exe実行完了まで待機
        except Exception as e:
            logger.error(f"端末{number}: start_app.exe実行失敗: {e}")
            
        # 3. 覇者用画面操作（mon6完全準拠）
        try:
            # **load09.png と load10.png を条件で切り替え（mon6準拠）**
            load_image = "load10.png" if window_name in ["4", "8"] else "load09.png"
            
            # 画面のロード完了まで待機（mon6完全準拠）
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
            
            # ウィンドウをアクティブにして右クリック（mon6準拠）
            activate_window_and_right_click(window_name)
            
            logger.info(f"端末{number}の処理完了")
            
        except Exception as e:
            logger.error(f"端末{number}: 覇者操作失敗: {e}")
        
        # 次の端末処理前の待機
        if number < len(devices):
            time.sleep(2)
            logger.info(f"端末{number+1}の処理に進みます")
    
    logger.info(f"全8端末の覇者継続処理が完了しました（フォルダ{base_folder}ベース）")

def continue_hasya() -> None:
    """覇者継続処理を1端末ずつ順次実行（mon6完全準拠）"""
    logger.info("覇者継続処理を開始（1端末ずつ順次実行）")
    
    # start_app.exeの起動
    start_app = r"C:\Users\santa\Desktop\MM\start_app.exe"
    
    # ルームキー設定（config.jsonから読み込み済み）
    
    # 設定ファイルパス（端末4と8はホスト処理用に設定10を使用）
    settings_file_9 = r"C:\Users\santa\Desktop\MM\[周回マクロ設定]\【設定】(9)保存した設定.txt"
    settings_file_10 = r"C:\Users\santa\Desktop\MM\[周回マクロ設定]\【設定】(10)保存した設定.txt"
    
    # 8端末の設定情報（端末4,8はホスト処理対応）
    devices = [
        ("1", "62025", "81", "Q", room_key1, settings_file_9),
        ("2", "62026", "87", "W", room_key1, settings_file_9),
        ("3", "62027", "69", "E", room_key1, settings_file_9),
        ("4", "62028", "82", "R", room_key1, settings_file_10),  # ホスト処理用
        ("5", "62029", "65", "A", room_key2, settings_file_9),
        ("6", "62030", "83", "S", room_key2, settings_file_9),
        ("7", "62031", "68", "D", room_key2, settings_file_9),
        ("8", "62032", "70", "F", room_key2, settings_file_10)   # ホスト処理用
    ]

    # 1端末ずつ順次実行（mon6完全準拠）
    for number, (window_name, port, code, key, room_key, settings_file) in enumerate(devices, 1):
        logger.info(f"端末{number}の処理開始: {window_name}")
        
        # 1. 設定ファイル更新（この端末用）
        success = False
        retries = 3
        while not success and retries > 0:
            try:
                # ホスト処理用の特別設定を考慮
                changes = {
                    24: f"tar_device=127.0.0.1:{port}",
                    25: f"output= -P 50037 -s 127.0.0.1:{port}",  # 正しいADBポート
                    27: f"main_key={code}",
                    28: f"main_keyF={key}",
                    33: f"room_key={room_key}"
                }
                
                # 端末4と8（ホスト処理）の場合の追加設定
                if window_name in ["4", "8"]:
                    logger.info(f"端末{number}: ホスト処理モード（設定ファイル10使用）")
                
                replace_multiple_lines_in_file(settings_file, changes)
                success = True
                logger.info(f"端末{number}: 設定ファイル更新成功")
            except Exception as e:
                logger.error(f"端末{number}: 設定ファイル更新失敗: {e}")
                retries -= 1
                time.sleep(1)

        time.sleep(1)  # 設定更新後の待機

        # 2. start_app.exe実行
        try:
            import subprocess
            subprocess.run(start_app, check=True)
            logger.info(f"端末{number}: start_app.exe実行成功")
            time.sleep(3)  # start_app.exe実行完了まで待機
        except Exception as e:
            logger.error(f"端末{number}: start_app.exe実行失敗: {e}")
            
        # 3. 覇者用画面操作（mon6完全準拠）
        try:
            # **load09.png と load10.png を条件で切り替え（mon6準拠）**
            load_image = "load10.png" if window_name in ["4", "8"] else "load09.png"
            
            # 画面のロード完了まで待機（mon6完全準拠）
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
            
            # ウィンドウをアクティブにして右クリック（mon6準拠）
            activate_window_and_right_click(window_name)
            
            logger.info(f"端末{number}の処理完了")
            
        except Exception as e:
            logger.error(f"端末{number}: 覇者操作失敗: {e}")
        
        # 次の端末処理前の待機
        if number < len(devices):
            time.sleep(2)
            logger.info(f"端末{number+1}の処理に進みます")
    
    logger.info("全8端末の覇者継続処理が完了しました")

def load_macro(number: int) -> None:
    """
    マクロ読み込み処理を実行します（working version 完全準拠）
    
    Args:
        number: マクロ番号
    """
    settings_file_base = fr"C:\Users\santa\Desktop\MM\[周回マクロ設定]\【設定】({number})保存した設定.txt"
    start_app = r"C:\Users\santa\Desktop\MM\start_app.exe"

    # 端末ごとの設定（マクロメニューでは8端末すべて同じ設定ファイルを使用）
    devices = [
        ("1", "62025", "81", "Q", room_key1, settings_file_base),
        ("2", "62026", "87", "W", room_key1, settings_file_base),
        ("3", "62027", "69", "E", room_key1, settings_file_base),
        ("4", "62028", "82", "R", room_key1, settings_file_base),  # マクロメニューでは同じファイル使用
        ("5", "62029", "65", "A", room_key2, settings_file_base),
        ("6", "62030", "83", "S", room_key2, settings_file_base),
        ("7", "62031", "68", "D", room_key2, settings_file_base),
        ("8", "62032", "70", "F", room_key2, settings_file_base)   # マクロメニューでは同じファイル使用
    ]

    for window_name, port, code, key, room_key, settings_file in devices:
        # ファイル書き換え処理
        success = False
        retries = 3
        while not success and retries > 0:
            try:
                changes = {
                    24: f"tar_device=127.0.0.1:{port}",
                    25: f"output= -P 50037 -s 127.0.0.1:{port}",  # 正しいADBポート
                    27: f"main_key={code}",
                    28: f"main_keyF={key}",
                    33: f"room_key={room_key}"
                }
                
                # マクロメニューでは全端末が同じ設定ファイルを使用
                logger.info(f"load_macro: 端末{window_name}（設定ファイル{number}使用）")
                
                replace_multiple_lines_in_file(settings_file, changes)
                success = True
            except Exception as e:
                logger.error(f"[エラー] ファイルの書き換えに失敗しました（{window_name}）：{e}")
                retries -= 1
                time.sleep(2)  # 失敗時にリトライ

        time.sleep(1)  # 書き換え後に少し待機

        # アプリ起動
        import subprocess
        subprocess.run(start_app)
        time.sleep(2)  # アプリ起動を待つ

        load_image = "load09.png"

        # 画面のロード完了まで待機（mon6完全準拠・マクロ用）
        tap_until_found_on_windows("load.png", "macro", "macro.png", "macro")
        tap_until_found_on_windows(load_image, "macro", "load.png", "macro")
        
        # キー操作による設定選択（マクロメニュー用）
        import pyautogui
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

