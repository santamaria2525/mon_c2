"""
セット単位処理ユーティリティ

端末数を1セットとして順次処理し、セット完了後に確認ダイアログを表示する機能を提供します。
"""

import time
import os
from typing import List, Callable, Optional, Tuple
import tkinter as tk
from tkinter import messagebox
import concurrent.futures

from utils import get_resource_path
from adb_utils import (
    close_monster_strike_app, start_monster_strike_app,
    run_adb_command
)
from logging_util import logger, MultiDeviceLogger
from contextlib import contextmanager
from monst.image.device_management import (
    pause_auto_restart,
    resume_auto_restart,
    force_restart_nox_device,
    get_device_idle_time,
    record_device_progress,
)

# 循環インポート回避のため定数を直接定義
MAX_FOLDER_LIMIT = 4000


def _format_folder_range(folders: List[str]) -> str:
    """Return human readable folder range like '001-008'."""
    if not folders:
        return "-"
    try:
        ordered = sorted(folders, key=lambda x: int(x))
    except Exception:
        ordered = folders
    start = ordered[0]
    end = ordered[-1]
    return f"{start}-{end}" if start != end else start

@contextmanager
def _tk_root(*, topmost: bool = True):
    """Context manager that creates a hidden Tk root and cleans up."""
    root = tk.Tk()
    root.withdraw()
    if topmost:
        root.attributes('-topmost', True)
    try:
        root.option_add("*Font", "Meiryo UI 9")
    except Exception:
        pass
    try:
        yield root
    finally:
        root.destroy()

@contextmanager
def _auto_restart_pause_scope(reason: str):
    """Ensure NOX auto-restart is paused while waiting for user input."""
    pause_auto_restart(reason)
    try:
        yield
    finally:
        resume_auto_restart()

def show_continue_dialog() -> bool:
    """
    Continue dialog.

    Returns:
        bool: True to continue, False to stop.
    """
    with _auto_restart_pause_scope("wait_user_continue"), _tk_root() as root:
        return messagebox.askyesno(
            "\u30bb\u30c3\u30c8\u51e6\u7406\u5b8c\u4e86",
            "\u3053\u306e\u30bb\u30c3\u30c8\u306e\u51e6\u7406\u304c\u5b8c\u4e86\u3057\u307e\u3057\u305f\u3002\n\u6b21\u306e\u30bb\u30c3\u30c8\u3092\u51e6\u7406\u3057\u307e\u3059\u304b\uff1f",
            icon='question',
        )


def find_next_set_folders(base_folder: int, num_devices: int) -> Tuple[Optional[int], List[str]]:
    """
    次のセット分のフォルダを順次検索
    
    Args:
        base_folder: 開始フォルダ番号
        num_devices: 端末数（セットサイズ）
        
    Returns:
        tuple: (次の開始フォルダ番号, 見つかったフォルダリスト)
    """
    bin_folder = get_resource_path("bin_push")
    candidates: List[str] = []
    idx = base_folder
    
    # 端末数分のフォルダを順次検索
    while len(candidates) < num_devices and idx <= MAX_FOLDER_LIMIT:
        fld = str(idx).zfill(3)
        path = os.path.join(bin_folder, fld, "data10.bin")
        if os.path.exists(path):
            candidates.append(fld)
        idx += 1
    
    if not candidates:
        logger.error(f"フォルダ {base_folder:03d} から {MAX_FOLDER_LIMIT:03d} までBINが見つかりません")
        return None, []
    
    # 見つかったフォルダ数が端末数より少ない場合
    if len(candidates) < num_devices:
        logger.warning(f"必要な{num_devices}端末分のフォルダが見つからず、{len(candidates)}個のみ処理")
    
    return idx, candidates

def process_set_sequential(
    folders: List[str],
    ports: List[str],
    operation: Callable,
    operation_name: str,
    custom_args: Optional[dict] = None
) -> int:
    """
    セット内のフォルダを端末1→2→3→8の順番で順次処理
    
    Args:
        folders: 処理するフォルダリスト
        ports: 使用する端末ポートリスト
        operation: 実行する操作関数
        operation_name: 操作名
        custom_args: 追加引数
        
    Returns:
        int: 成功した端末数
    """
    success_count = 0
    multi_logger = MultiDeviceLogger(ports, folders)
    
    logger.info(f"🎯 セット処理開始: {operation_name} (フォルダ: {', '.join(folders)})")
    
    for i, (port, folder) in enumerate(zip(ports, folders), 1):
        try:
            if not _prepare_device_for_folder(port, folder):
                logger.error(f"端末{i} - フォルダ{folder} 準備失敗")
                continue
            
            try:
                if custom_args:
                    operation(port, folder, multi_logger, **custom_args)
                else:
                    operation(port, folder, multi_logger)

                success_count += 1
            except Exception as e:
                logger.error(f"❌ 端末{i} - 操作実行エラー: {e}")
                
        except Exception as e:
            logger.error(f"❌ 端末{i} - 予期しないエラー: {e}")
    
    logger.info(f"🎯 セット処理完了: {success_count}/{len(folders)} 端末成功")
    return success_count

def process_set_parallel(
    folders: List[str],
    ports: List[str],
    operation: Callable,
    operation_name: str,
    custom_args: Optional[dict] = None
) -> int:
    """
    ??????8?????????

    Args:
        folders: ???????????
        ports: ????????????
        operation: ????????
        operation_name: ???
        custom_args: ????

    Returns:
        int: ???????
    """
    success_count = 0
    multi_logger = MultiDeviceLogger(ports, folders)

    resend_interval = 600
    max_resend_attempts = 0
    try:
        from config import get_config

        cfg = get_config()
        resend_interval = int(getattr(cfg, "login_resend_interval_seconds", resend_interval) or resend_interval)
        resend_interval = max(60, resend_interval)
        max_resend_attempts = int(getattr(cfg, "login_resend_max_attempts", 0) or 0)
    except Exception:
        pass

    logger.info(f"?? 8?????????? {operation_name} (????: {', '.join(folders)})")

    def process_single_device(port: str, folder: str, device_num: int) -> bool:
        """????????? (10????????????)"""
        attempts = 0
        next_check = time.time() + resend_interval
        while True:
            attempts += 1
            record_device_progress(port)
            try:
                if not _prepare_device_for_folder(port, folder):
                    logger.error(f"??{device_num} - ????{folder} ????")
                    success = False
                else:
                    try:
                        if custom_args:
                            operation(port, folder, multi_logger, **custom_args)
                        else:
                            operation(port, folder, multi_logger)
                        logger.debug(f"??{device_num} - ????{folder} ????")
                        success = True
                    except Exception as e:
                        logger.error(f"? ??{device_num} - ???????: {e}")
                        success = False
            except Exception as e:
                logger.error(f"? ??{device_num} - ????????: {e}")
                success = False

            if success:
                record_device_progress(port)
                return True

            if max_resend_attempts and attempts >= max_resend_attempts:
                logger.error(f"??{device_num} - ?????? ({attempts}?)")
                return False

            idle_time = int(get_device_idle_time(port))
            logger.warning(
                f"[RESEND] ??{device_num} ????{folder} ???????: idle={idle_time}s (??{attempts})"
            )

            # ????NOX??????
            try:
                force_restart_nox_device(port, emergency=True)
            except Exception as e:
                logger.error(f"??{device_num} - ?????????: {e}")

            now = time.time()
            if now < next_check:
                time.sleep(max(1, next_check - now))
            next_check = time.time() + resend_interval

    # 8?????????
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(ports)) as executor:
        futures = []
        for i, (port, folder) in enumerate(zip(ports, folders), 1):
            futures.append(executor.submit(process_single_device, port, folder, i))

        for future in concurrent.futures.as_completed(futures):
            try:
                if future.result():
                    success_count += 1
            except Exception as e:
                logger.error(f"? ?????????: {e}")

    logger.info(f"?? 8?????????? {success_count}/{len(folders)} ????")
    return success_count

def _prepare_device_for_folder(port: str, folder: str) -> bool:
    """
    端末にフォルダのBINを準備
    
    Args:
        port: 端末ポート
        folder: フォルダ番号
        
    Returns:
        bool: 準備成功時True
    """
    try:
        bin_folder = get_resource_path("bin_push")
        # フォルダ番号を整数に変換してからフォーマット
        folder_num = int(folder) if isinstance(folder, str) else folder
        src = os.path.join(bin_folder, f"{folder_num:03d}", "data10.bin")
        
        if not os.path.exists(src):
            logger.error(f"BINファイルが存在しません: {src}")
            return False
        
        # アプリ終了
        close_monster_strike_app(port)
        time.sleep(1.5)
        
        # BINプッシュ
        dest_path = '/data/data/jp.co.mixi.monsterstrike/data10.bin'
        push_cmd = ['push', src, dest_path]
        
        logger.debug(f"BINプッシュ実行: adb -s {port} {' '.join(push_cmd)}")
        result = run_adb_command(push_cmd, port)
        
        if result is None:
            logger.error(f"BINプッシュ失敗: フォルダ{folder} ポート{port}")
            logger.error(f"  送信元: {src}")
            logger.error(f"  送信先: {dest_path}")  
            logger.error(f"  コマンド: adb -s {port} push \"{src}\" \"{dest_path}\"")
            
            # 追加デバッグ情報
            logger.error(f"  デバッグ情報:")
            logger.error(f"    フォルダタイプ: {type(folder)} 値: '{folder}'")
            logger.error(f"    ファイルサイズ: {os.path.getsize(src) if os.path.exists(src) else 'N/A'} bytes")
            return False
        
        logger.debug(f"BINプッシュ成功: フォルダ{folder} -> {port}")
        
        time.sleep(1)
        
        # アプリ起動
        start_monster_strike_app(port)
        time.sleep(5)  # 起動待機
        
        return True
        
    except Exception as e:
        logger.error(f"端末準備エラー {folder}: {e}")
        return False

def run_set_based_loop(
    base_folder: int,
    operation: Callable,
    ports: List[str],
    operation_name: str,
    custom_args: Optional[dict] = None
) -> None:
    """
    セット単位での処理ループ
    
    Args:
        base_folder: 開始フォルダ番号
        operation: 実行する操作関数
        ports: 使用する端末ポートリスト
        operation_name: 操作名
        custom_args: 追加引数
    """
    current_folder = base_folder
    set_number = 1
    num_devices = len(ports)
    
    logger.info(f"🔄 セット単位処理開始: {operation_name} ({num_devices}台, フォルダ{current_folder:03d}～)")
    
    while True:
        try:
            logger.info(f"\n🎯 === セット{set_number} 処理開始 ===")
            
            # 次のセット分のフォルダを検索
            next_folder, folders = find_next_set_folders(current_folder, num_devices)
            
            if not folders:
                logger.info("🏁 処理可能なフォルダが見つかりません。処理終了")
                break
            
            # 実際に使用する端末数を調整
            actual_ports = ports[:len(folders)]
            
            logger.info(f"📂 処理フォルダ: {', '.join(folders)}")
            logger.info(f"📱 使用端末: {len(actual_ports)}台")
            
            # セット内を順次処理
            success_count = process_set_sequential(
                folders, actual_ports, operation, operation_name, custom_args
            )
            
            logger.info(f"✅ セット{set_number} 完了: {success_count}/{len(folders)} 成功")
            
            # 続行確認ダイアログ
            if not show_continue_dialog():
                logger.info("🛑 ユーザーにより処理停止")
                break
            
            # 次のセットに進む
            current_folder = next_folder
            set_number += 1
            
            if current_folder > MAX_FOLDER_LIMIT:
                logger.info(f"🏁 フォルダ上限 ({MAX_FOLDER_LIMIT}) に到達。処理終了")
                break
                
        except Exception as e:
            logger.error(f"❌ セット{set_number} 処理エラー: {e}")
            if not show_continue_dialog():
                break
            current_folder = next_folder if next_folder else current_folder + num_devices
            set_number += 1
    
    logger.info(f"🎉 セット単位処理完了: 合計{set_number-1}セット処理")

def show_loop_continue_dialog() -> bool:
    """
    8-device loop continue dialog.

    Returns:
        bool: True to continue, False to stop.
    """
    with _auto_restart_pause_scope("wait_loop_continue"), _tk_root() as root:
        return messagebox.askyesno(
            "\u0038\u7aef\u672b\u30bb\u30c3\u30c8\u5b8c\u4e86",
            "\u0038\u7aef\u672b\u3067\u306e\u30ed\u30b0\u30a4\u30f3\u51e6\u7406\u304c\u5b8c\u4e86\u3057\u307e\u3057\u305f\u3002\n\u540c\u3058\u0038\u7aef\u672b\u3067\u7d99\u7d9a\u3057\u3066\u30ed\u30b0\u30a4\u30f3\u51e6\u7406\u3092\u884c\u3044\u307e\u3059\u304b\uff1f",
            icon='question',
        )


def run_continuous_set_loop(
    base_folder: int,
    operation: Callable,
    ports: List[str],
    operation_name: str,
    custom_args: Optional[dict] = None,
    summary_label: Optional[str] = None,
) -> None:
    """8??????????????????"""
    current_folder = base_folder
    round_number = 1
    num_devices = len(ports)

    logger.info("[Loop] 8???????: %s (???=%d)", operation_name, num_devices)

    while True:
        try:
            logger.info("[Loop] === ???%02d ?? ===", round_number)
            next_folder, folders = find_next_set_folders(current_folder, num_devices)
            if not folders:
                logger.info("[Loop] ?????????????????")
                break

            actual_ports = ports[:len(folders)]
            range_label = _format_folder_range(folders)
            suffix = summary_label or operation_name
            logger.info("%s %s ????", range_label, suffix)

            success_count = process_set_parallel(
                folders, actual_ports, operation, operation_name, custom_args
            )

            label = (f"{range_label} {suffix}").strip()
            if success_count == len(folders):
                logger.info("%s ???? (%d/%d)", label, success_count, len(folders))
            else:
                logger.warning("%s ????? (%d/%d)", label, success_count, len(folders))
            logger.info("%s ?????? (??=??, ???=??)", label)

            if not show_loop_continue_dialog():
                logger.info("[Loop] ???????????")
                break

            logger.info("[Loop] ???%02d ??: %d/%d ??", round_number, success_count, len(folders))

            current_folder = next_folder
            round_number += 1

            if current_folder > MAX_FOLDER_LIMIT:
                logger.info("[Loop] ?????? (%d) ???", MAX_FOLDER_LIMIT)
                break

        except Exception as exc:
            logger.error("[Loop] ???%02d ???: %s", round_number, exc)
            if not show_loop_continue_dialog():
                break
            current_folder = next_folder if next_folder else current_folder + num_devices
            round_number += 1

    logger.info("[Loop] 8?????????: ?%d???", round_number - 1)

