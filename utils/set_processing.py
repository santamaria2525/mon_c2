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

# 循環インポート回避のため定数を直接定義
MAX_FOLDER_LIMIT = 3000

@contextmanager
def _tk_root(*, topmost: bool = True):
    """Context manager that creates a hidden Tk root and cleans up."""
    root = tk.Tk()
    root.withdraw()
    if topmost:
        root.attributes('-topmost', True)
    try:
        yield root
    finally:
        root.destroy()

def show_continue_dialog() -> bool:
    """
    続行確認ダイアログを表示
    
    Returns:
        bool: 続行する場合True、停止する場合False
    """
    with _tk_root() as root:
        result = messagebox.askyesno(
            "セット処理完了",
            "このセットの処理が完了しました。\n\n次のセットを処理しますか？",
            icon='question'
        )
        return result

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
    
    logger.info(f"🎯 セット処理開始: {operation_name} ({len(folders)}端末, フォルダ: {', '.join(folders)})")
    
    # 端末1から順次処理（タスクモニター対応）
    for i, (port, folder) in enumerate(zip(ports, folders), 1):
        try:
            logger.debug(f"端末{i} (ポート:{port}) - フォルダ{folder} 処理開始")
            
            # BINプッシュとアプリ準備
            if not _prepare_device_for_folder(port, folder):
                logger.error(f"端末{i} - フォルダ{folder} 準備失敗")
                continue
            
            # 操作実行
            try:
                if custom_args:
                    operation(port, folder, multi_logger, **custom_args)
                else:
                    operation(port, folder, multi_logger)
                    
                success_count += 1
                logger.info(f"✅ 端末{i} - フォルダ{folder} 処理完了")
                
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
    セット内の8端末を同時並列処理
    
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
    
    logger.info(f"🎯 8端末同時並列処理開始: {operation_name} ({len(folders)}端末, フォルダ: {', '.join(folders)})")
    
    def process_single_device(port: str, folder: str, device_num: int) -> bool:
        """単一端末の処理を実行"""
        try:
            logger.debug(f"端末{device_num} (ポート:{port}) - フォルダ{folder} 処理開始")
            
            # BINプッシュとアプリ準備
            if not _prepare_device_for_folder(port, folder):
                logger.error(f"端末{device_num} - フォルダ{folder} 準備失敗")
                return False
            
            # 操作実行
            try:
                if custom_args:
                    operation(port, folder, multi_logger, **custom_args)
                else:
                    operation(port, folder, multi_logger)
                    
                logger.info(f"✅ 端末{device_num} - フォルダ{folder} 処理完了")
                return True
                
            except Exception as e:
                logger.error(f"❌ 端末{device_num} - 操作実行エラー: {e}")
                return False
                
        except Exception as e:
            logger.error(f"❌ 端末{device_num} - 予期しないエラー: {e}")
            return False
    
    # 8端末を同時並列実行
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(ports)) as executor:
        # 全端末のタスクを同時実行
        futures = []
        for i, (port, folder) in enumerate(zip(ports, folders), 1):
            future = executor.submit(process_single_device, port, folder, i)
            futures.append(future)
        
        # すべてのタスクの完了を待機
        for future in concurrent.futures.as_completed(futures):
            try:
                if future.result():
                    success_count += 1
            except Exception as e:
                logger.error(f"❌ 並列処理中にエラー: {e}")
    
    logger.info(f"🎯 8端末同時並列処理完了: {success_count}/{len(folders)} 端末成功")
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
    8端末セット完了後の継続確認ダイアログを表示
    
    Returns:
        bool: 継続する場合True、停止する場合False
    """
    with _tk_root() as root:
        result = messagebox.askyesno(
            "8端末セット完了",
            "8端末でのログイン処理が完了しました。\n\n同じ8端末で継続してログイン処理を行いますか？",
            icon='question'
        )
        return result

def run_continuous_set_loop(
    base_folder: int,
    operation: Callable,
    ports: List[str],
    operation_name: str,
    custom_args: Optional[dict] = None
) -> None:
    """
    8端末セット継続ループ処理
    
    8端末でログイン処理完了後、確認ダイアログを表示し、
    OKが押されたら同じ8端末で次のフォルダセットを処理する。
    
    Args:
        base_folder: 開始フォルダ番号
        operation: 実行する操作関数
        ports: 使用する端末ポートリスト
        operation_name: 操作名
        custom_args: 追加引数
    """
    current_folder = base_folder
    round_number = 1
    num_devices = len(ports)
    
    logger.info(f"🔄 8端末継続ループ開始: {operation_name} ({num_devices}台)")
    
    while True:
        try:
            logger.info(f"\n🎯 === ラウンド{round_number} 処理開始 ===")
            
            # 8端末分のフォルダを検索
            next_folder, folders = find_next_set_folders(current_folder, num_devices)
            
            if not folders:
                logger.info("🏁 処理可能なフォルダが見つかりません。処理終了")
                break
            
            # 実際に使用する端末数を調整（8端末固定想定）
            actual_ports = ports[:len(folders)]
            
            logger.info(f"📂 処理フォルダ: {', '.join(folders)}")
            logger.info(f"📱 使用端末: {len(actual_ports)}台")
            
            # 8端末セットを同時並列処理
            success_count = process_set_parallel(
                folders, actual_ports, operation, operation_name, custom_args
            )
            
            logger.info(f"✅ ラウンド{round_number} 完了: {success_count}/{len(folders)} 端末成功")
            
            # 8端末セット完了後の継続確認ダイアログ
            if not show_loop_continue_dialog():
                logger.info("🛑 ユーザーにより8端末ループ停止")
                break
            
            # 次のラウンドに進む
            current_folder = next_folder
            round_number += 1
            
            if current_folder > MAX_FOLDER_LIMIT:
                logger.info(f"🏁 フォルダ上限 ({MAX_FOLDER_LIMIT}) に到達。処理終了")
                break
                
        except Exception as e:
            logger.error(f"❌ ラウンド{round_number} 処理エラー: {e}")
            if not show_loop_continue_dialog():
                break
            current_folder = next_folder if next_folder else current_folder + num_devices
            round_number += 1
    
    logger.info(f"🎉 8端末継続ループ完了: 合計{round_number-1}ラウンド処理")