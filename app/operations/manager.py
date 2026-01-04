# -*- coding: utf-8 -*-
"""
Business logic operations for Monster Strike Bot

This module handles:
- Device operations and workflows
- Multi-device coordination
- File operations and data management
- Core business logic functions
"""

import os
import sys
import time
import threading
import openpyxl
import pyautogui
import concurrent.futures
from typing import List, Callable, Optional, Dict, Any

from config import select_ports, host_ports, sub_ports, get_config, get_ports_by_count, MAX_FOLDER_LIMIT
from utils import (
    get_resource_path,
    display_message,
    get_target_folder,
    create_mm_folders,
    get_mm_folder_status,
    clean_mm_folders,
    batch_rename_folders_csv,
    batch_rename_folders_excel,
    close_windows_by_title,
    close_nox_error_dialogs,
)



def _try_stop_task_monitor() -> None:
    """Attempt to stop the external task monitor if available."""
    try:
        from utils.process_task_monitor import stop_process_task_monitor as _stop
    except Exception:
        return
    try:
        _stop()
    except Exception:
        pass

from adb_utils import (
    close_monster_strike_app, start_monster_strike_app,
    remove_data10_bin_from_nox, pull_file_from_nox, run_adb_command,
    reset_adb_server
)
from device_operations import device_operation_select
from login_operations import device_operation_login
from logging_util import MultiDeviceLogger
from monst.device import device_operation_quest
from missing_functions import (
    device_operation_excel_and_save, device_operation_nobin,
    continue_hasya, load_macro
)
from monst.device.hasya import (
    device_operation_hasya, device_operation_hasya_wait, device_operation_hasya_fin,
    device_operation_hasya_host_fin, continue_hasya_parallel, continue_hasya,
    continue_hasya_with_base_folder
)
from utils import find_next_set_folders
from logging_util import logger
from .helpers import (
    run_push,
    run_loop,
    run_loop_enhanced,
    remove_all_nox,
    run_in_threads,
    log_folder_result,
    debug_log,
    find_and_click_with_protection,
    write_account_folders,
)

MAX_PARALLEL_DEVICE_TASKS = 8  # 端末8台を同時進行

MACRO_MENU_WINDOW_TITLES = (
    "NOX自動化ツール - 機能選択",
    "MSTools Dialog",
)

from . import account as account_ops
from image_detection import tap_if_found_on_windows
from app.core import ApplicationCore
from app_crash_recovery import ensure_app_running, check_app_crash

class OperationsManager:
    """Manager for all bot operations"""
    
    def __init__(self, core: ApplicationCore):
        self.core = core
        # 設定ファイルから独立並行処理モード設定を読み込み
        config = get_config()
        self.use_independent_processing = config.use_independent_processing
        
        # タスクモニター初期化
        self._task_monitor_started = False
        # 端末台数設定ログの初回フラグ
        self._device_count_logged = False
        self._port_last_started: Dict[str, float] = {}
        self._port_throttle_seconds = 4.0
    
    def set_processing_mode(self, independent: bool = True) -> None:
        """
        処理モードを設定
        
        Args:
            independent: True=独立並行処理, False=従来同期処理
        """
        self.use_independent_processing = independent
        mode_name = "独立並行処理" if independent else "従来同期処理"
        logger.debug(f"?? 処理モード変更: {mode_name}")
    
    def get_processing_mode(self) -> bool:
        """現在の処理モードを取得"""
        return self.use_independent_processing

    def _handle_folder_limit_exceeded(self, folder_value: int, *, reason: str | None = None) -> None:
        """Stop the application when folder processing should cease."""
        if reason == "no_data":
            logger.info(f"BIN data missing; stopping at folder {folder_value:03d}")
        else:
            logger.error(f"Folder limit exceeded (> {MAX_FOLDER_LIMIT}): {folder_value}")
        logger.info("Folder limit reached. Shutting down application.")
        try:
            _try_stop_task_monitor()
        except Exception:
            pass
        try:
            self.core.stop_event.set()
        except Exception:
            pass
        raise SystemExit(0)

    def _cleanup_macro_windows(self) -> int:
        """Close any lingering macro selection windows."""

        closed = 0
        for title in MACRO_MENU_WINDOW_TITLES:
            closed += close_windows_by_title(title)
        return closed

    def _get_validated_ports(self) -> Optional[List[str]]:
        """
        設定ファイルから端末数を取得し、バリデーション済みのポートリストを返す
        
        Returns:
            Optional[List[str]]: バリデーション済みポートリスト（エラー時はNone） 
        """
        try:
            # config.jsonから端末台数を取得（完璧なエラーハンドリング）
            config = get_config()
            device_count = config.device_count
            
            # バリデーション
            from config import validate_device_count
            if not validate_device_count(device_count):
                logger.error(f"? 無効な端末台数設定: {device_count}")
                logger.debug("?? config.json の device_count を3-8の範囲で設定してください")
                return None
            
            selected_ports = get_ports_by_count(device_count)
            # 端末台数設定ログは初回のみ表示
            if not self._device_count_logged:
                logger.debug(f"? 端末台数設定確認: {device_count}台")
                logger.debug(f"??? 使用ポート: {len(selected_ports)}個 {selected_ports[:3]}...")
                self._device_count_logged = True
            
            return selected_ports
            
        except Exception as e:
            logger.error(f"? 端末数設定取得エラー: {e}")
            logger.debug("?? config.json の device_count 設定を確認してください")
            return None
    
    def _get_dynamic_host_sub_ports(self, all_ports: List[str]) -> tuple[List[str], List[str]]:
        """
        端末リストを主端末(host)と副端末(sub)に動的分割（mon6準拠：端末4,8がホスト）
        
        Args:
            all_ports: 全端末のポートリスト
            
        Returns:
            tuple[List[str], List[str]]: (主端末リスト, 副端末リスト)
        """
        # mon6準拠：端末4(62028)と端末8(62032)がホスト端末
        host_port_numbers = ['62028', '62032']  # 端末4と8
        
        host_ports = []
        sub_ports = []
        
        for port in all_ports:
            port_number = port.split(':')[-1]  # 127.0.0.1:62028 -> 62028
            if port_number in host_port_numbers:
                host_ports.append(port)
            else:
                sub_ports.append(port)
        
        logger.debug(f"?? 覇者用端末分割（mon6準拠）: ホスト端末{len(host_ports)}台 / サブ端末{len(sub_ports)}台")
        logger.debug(f"   ホスト端末: {[p.split(':')[-1] for p in host_ports]} (端末4,8)")
        logger.debug(f"   サブ端末: {[p.split(':')[-1] for p in sub_ports]} (端末1,2,3,5,6,7)")
        
        return host_ports, sub_ports
    
    def _run_multi_device_operation_mon6(self, op: Callable, ports: List[str], name: str) -> None:
        """mon6準拠のマルチデバイス操作実行"""
        from logging_util import MultiDeviceLogger
        ml = MultiDeviceLogger(ports)
        worker_count = min(len(ports), MAX_PARALLEL_DEVICE_TASKS)
        with concurrent.futures.ThreadPoolExecutor(max_workers=worker_count) as exe:
            fs = [exe.submit(op, p, ml) for p in ports]
            
            # 完全完了待機（重要！）
            done, _ = concurrent.futures.wait(fs, return_when=concurrent.futures.ALL_COMPLETED)
            
            # 失敗した処理があるかチェック
            for future in done:
                try:
                    result = future.result()
                    logger.debug(f"? {name}処理完了: {result}")
                except Exception as e:
                    logger.error(f"? {name}処理失敗: {e}")
        
        ml.summarize_results(name)
    
    def _run_loop_wrapper(
        self,
        operation: Callable[..., Any],
        operation_name: str,
        ports: List[str],
        *,
        additional_operation: Optional[Callable[[int], Any]] = None,
        custom_args: Optional[Dict[str, Any]] = None,
        save_data_files: bool = False,
        use_independent_processing: Optional[bool] = None,
        base_folder: Optional[int] = None,
    ) -> None:
        """Common wrapper for run_loop operations with throttling."""
        if base_folder is None:
            base_folder = self.core.get_start_folder()
            if base_folder is None:
                return
        closed = self._cleanup_macro_windows()
        if closed:
            logger.debug("Closed %d leftover macro windows", closed)
        close_nox_error_dialogs()
        reset_adb_server()

        if use_independent_processing is None:
            use_independent_processing = self.use_independent_processing

        ports = [port for port in ports if port]
        if not ports:
            logger.warning("%s: no available device ports", operation_name)
            return

        now = time.time()
        wait_time = 0.0
        for port in ports:
            last = self._port_last_started.get(port, 0.0)
            if last:
                cooldown = self._port_throttle_seconds - (now - last)
                if cooldown > wait_time:
                    wait_time = cooldown
        if wait_time > 0.5:
            wait_time = min(wait_time, self._port_throttle_seconds)
            logger.debug("%s: waiting %.1fs to stagger device start", operation_name, wait_time)
            time.sleep(wait_time)

        ordered_ports = sorted(ports, key=lambda p: self._port_last_started.get(p, 0.0))
        logger.debug(
            "%s: starting loop (mode=%s) on ports %s",
            operation_name,
            'independent' if use_independent_processing else 'cooperative',
            ordered_ports,
        )

        next_base, should_stop = run_loop_enhanced(
            base_folder,
            operation,
            ordered_ports,
            operation_name,
            additional_operation=additional_operation,
            custom_args=custom_args,
            save_data_files=save_data_files,
            use_independent_processing=use_independent_processing,
        )

        stamp = time.time()
        for idx, port in enumerate(ordered_ports):
            self._port_last_started[port] = stamp + idx * 0.5

        if should_stop:
            stop_reason = "no_data" if next_base is None else None
            cutoff_folder = next_base if next_base is not None else max(base_folder, MAX_FOLDER_LIMIT)
            self._handle_folder_limit_exceeded(cutoff_folder, reason=stop_reason)


    def run_multi_device_operation(self, op: Callable, ports: List[str], name: str, folder: str = None) -> None:
        """Execute operation on multiple devices"""
        # タスクモニターを開始
        self._start_task_monitor(ports)
        
        ml = MultiDeviceLogger(ports)
        
        # 各デバイスの初期状態をタスクモニターに設定
        for port in ports:
            folder_str = folder if folder else "---"
            ml.update_task_status(port, folder_str, f"{name}準備中")
        
        worker_count = min(len(ports), MAX_PARALLEL_DEVICE_TASKS)
        with concurrent.futures.ThreadPoolExecutor(max_workers=worker_count) as exe:
            if folder is not None:
                # folderパラメータが必要な操作用
                fs = [exe.submit(self._execute_with_monitoring, op, p, folder, ml, name) for p in ports]
            else:
                # folderパラメータが不要な操作用
                fs = [exe.submit(self._execute_with_monitoring, op, p, None, ml, name) for p in ports]
            
            # 完全完了待機（重要！）
            done, _ = concurrent.futures.wait(fs, return_when=concurrent.futures.ALL_COMPLETED)
            
            # 失敗した処理があるかチェック  
            for future in done:
                try:
                    result = future.result()
                    logger.debug(f"? {name}処理完了: {result}")
                except Exception as e:
                    logger.error(f"? {name}処理失敗: {e}")
        
        # 完了状態をタスクモニターに設定
        for port in ports:
            folder_str = folder if folder else "---"
            ml.update_task_status(port, folder_str, f"{name}完了")
        
        ml.summarize_results(name)
    
    # ================== Main Operations ==================
    
    def main_loop_select(self) -> None:
        """Execute select operation loop"""
        try:
            # config.jsonから端末台数を取得（完璧なエラーハンドリング）
            config = get_config()
            device_count = config.device_count
            
            # バリデーション
            from config import validate_device_count
            if not validate_device_count(device_count):
                logger.error(f"? 無効な端末台数設定: {device_count}")
                logger.debug("?? config.json の device_count を3-8の範囲で設定してください")
                return
            
            selected_ports = get_ports_by_count(device_count)
            # 端末台数設定ログは初回のみ表示
            if not self._device_count_logged:
                logger.debug(f"? 端末台数設定確認: {device_count}台")
                logger.debug(f"??? 使用ポート: {len(selected_ports)}個 {selected_ports[:3]}...")
                self._device_count_logged = True
            
            # タスクモニターを開始
            self._start_task_monitor(selected_ports)
            self._run_loop_wrapper(
                device_operation_select,
                "セレクト",
                selected_ports,
                custom_args={"home_early": True},
            )
            
        except Exception as e:
            logger.error(f"? セレクト操作初期化エラー: {e}")
            logger.debug("?? config.json の device_count 設定を確認してください")
    
    def main_1set(self) -> None:
        """Execute 1set write operation"""
        # 端末数設定を取得
        selected_ports = self._get_validated_ports()
        if selected_ports is None:
            return
            
        # タスクモニターを開始（すべての操作で表示）
        self._start_task_monitor(selected_ports)
        
        # フォルダ選択ダイアログを表示
        base_folder = get_target_folder()
        if base_folder is None:
            logger.error("フォルダが選択されませんでした。")
            return
        
        try:
            base_int = int(base_folder)
        except ValueError:
            logger.error(f"無効なフォルダ番号: {base_folder}")
            return
        
        if base_int > MAX_FOLDER_LIMIT:
            self._handle_folder_limit_exceeded(base_int)
        
        logger.debug(f"1set書き込み処理開始: フォルダ{base_int:03d}から")
        reset_adb_server()
        run_push(base_int, selected_ports)
        
        # 1set書き込み用にlogin操作を実行（folderパラメータを正しく渡す）
        ml = MultiDeviceLogger(selected_ports)
        worker_count = min(len(selected_ports), MAX_PARALLEL_DEVICE_TASKS)
        with concurrent.futures.ThreadPoolExecutor(max_workers=worker_count) as exe:
            fs = [exe.submit(device_operation_login, p, str(base_int), ml) for p in selected_ports]
            
            # 完全完了待機（重要！）
            done, _ = concurrent.futures.wait(fs, return_when=concurrent.futures.ALL_COMPLETED)
            
            # 失敗した処理があるかチェック  
            for future in done:
                try:
                    result = future.result()
                    logger.debug(f"? 1set書き込みログイン処理完了: {result}")
                except Exception as e:
                    logger.error(f"? 1set書き込みログイン処理失敗: {e}")
        
        ml.summarize_results("1set書き込み")
        logger.debug("? 1set書き込み用ログイン処理完全完了")
        time.sleep(5)  # 完了確認時間
    
    def main_loop(self, start_folder: Optional[int] = None) -> None:
        """Execute main login loop"""
        try:
            # config.jsonから端末台数を取得（完璧なエラーハンドリング）
            config = get_config()
            device_count = config.device_count
            
            # バリデーション
            from config import validate_device_count
            if not validate_device_count(device_count):
                logger.error(f"? 無効な端末台数設定: {device_count}")
                logger.debug("?? config.json の device_count を3-8の範囲で設定してください")
                return
            
            selected_ports = get_ports_by_count(device_count)
            # 端末台数設定ログは初回のみ表示
            if not self._device_count_logged:
                logger.debug(f"? 端末台数設定確認: {device_count}台")
                logger.debug(f"??? 使用ポート: {len(selected_ports)}個 {selected_ports[:3]}...")
                self._device_count_logged = True
            
            # タスクモニターを開始
            self._start_task_monitor(selected_ports)
            
            base_folder = start_folder or get_target_folder()
            if base_folder is None:
                logger.error("フォルダが見つかりません。")
                return
            
            try:
                base_int = int(base_folder)
            except ValueError:
                logger.error(f"無効なフォルダ番号: {base_folder}")
                return
            
            if base_int > MAX_FOLDER_LIMIT:
                self._handle_folder_limit_exceeded(base_int)
            
            logger.debug(f"ログインループ開始: フォルダ {base_int:03d} から")
            reset_adb_server()
            custom_args = {'home_early': True}
            
            # 独立並行処理システムを使用
            logger.debug(f"?? 処理モード: {'独立並行処理' if self.use_independent_processing else '従来同期処理'}")
            
            next_folder, should_stop = run_loop_enhanced(
                base_int, device_operation_login, selected_ports, "ログイン操作",
                custom_args=custom_args,
                use_independent_processing=self.use_independent_processing
            )

            # BIN data exhaustion or upper limit triggers a controlled shutdown
            if should_stop:
                stop_reason = "no_data" if next_folder is None else None
                cutoff_folder = next_folder if next_folder is not None else max(base_int, MAX_FOLDER_LIMIT)
                self._handle_folder_limit_exceeded(cutoff_folder, reason=stop_reason)

            if next_folder:
                logger.debug(f"次の開始フォルダ: {next_folder:03d}")
                
        except Exception as e:
            logger.error(f"? ログインループ初期化エラー: {e}")
            logger.debug("?? config.json の device_count 設定を確認してください")
    
    def main_loop_stop(self) -> None:
        """Execute continuous login loop with 8-terminal set processing and stop dialogs"""
        # 端末数設定を取得
        selected_ports = self._get_validated_ports()
        if selected_ports is None:
            return
            
        # タスクモニターを開始（すべての操作で表示）
        self._start_task_monitor(selected_ports)
        
        # フォルダ選択ダイアログを表示
        base_folder = get_target_folder()
        if base_folder is None:
            logger.error("フォルダが選択されませんでした。")
            return
        
        try:
            base_int = int(base_folder)
        except ValueError:
            logger.error(f"無効なフォルダ番号: {base_folder}")
            return
        
        if base_int > MAX_FOLDER_LIMIT:
            self._handle_folder_limit_exceeded(base_int)
        
        logger.debug(f"8端末ループ処理開始: フォルダ{base_int:03d}から")
        
        # 8端末セット継続ループ処理を実行
        from utils.set_processing import run_continuous_set_loop
        from adb_utils import reset_adb_server
        
        reset_adb_server()
        
        try:
            run_continuous_set_loop(
                base_folder=base_int,
                operation=device_operation_login,
                ports=selected_ports,
                operation_name="ログイン操作(8端末継続ループ)",
                custom_args=None
            )
        except Exception as e:
            logger.error(f"8端末ループ処理エラー: {e}")
            display_message("エラー", f"処理中にエラーが発生しました: {e}")
    
    def main_loop_hasya(self) -> None:
        """Execute hasya (overlord) operation - 覇者2セット完全準拠版（メモリ不足対応）"""
        # 覇者2セット処理: 旧バージョン完全準拠 + メモリ監視強化
        
        # フォルダ管理変数（ダブり処理防止強化）
        current_folder_base = None
        processed_folders = set()  # 処理済みフォルダ記録（ダブり防止）
        
        def add_ops(current_folder: int):
            nonlocal current_folder_base, processed_folders
            current_folder_base = current_folder
            processed_folders.clear()
            block_start = current_folder_base
            
            # 初期フォルダ範囲をprocessed_foldersに記録（ダブり防止）
            initial_range = set(range(current_folder, current_folder + 8))
            logger.debug(f"?? 初期処理対象フォルダ: {sorted(initial_range)}")
            
            # メモリ監視を強化モードで開始
            from memory_monitor import memory_monitor, force_cleanup
            memory_monitor.cleanup_aggressive_mode = True
            memory_monitor.consecutive_critical_count = 0
            memory_monitor.check_interval = 30  # 30秒間隔で監視強化
            logger.debug("?? 覇者2セット開始: メモリ監視強化モード有効")
            
            # 事前メモリクリーンアップ
            force_cleanup()
            
            # 処理継続保証のための追加設定
            import psutil
            memory_percent = psutil.virtual_memory().percent
            logger.debug(f"?? 覇者2セット開始時メモリ: {memory_percent:.1f}%")
            
            # ===========================================
            # 【重要】覇者処理開始前の初期binファイル書き込み処理
            # ===========================================
            logger.debug(f"?? 覇者処理開始前: 初期binファイル書き込み開始（フォルダ{current_folder_base}から8端末分）")
            
            # 端末リスト取得
            selected_ports = self._get_validated_ports()
            if selected_ports is None:
                logger.error("? �[���ݒ肪�擾�ł��܂���")
                return
            device_count = len(selected_ports)
            
            # 初期binファイル書き込み実行（最重要）
            from multi_device import run_push
            try:
                run_push(current_folder_base, selected_ports)
                logger.debug(f"? 初期binファイル書き込み完了: フォルダ{current_folder_base}~{current_folder_base+7}")
            except Exception as e:
                logger.error(f"? 初期binファイル書き込み失敗: {e}")
                raise
            
            # bin書き込み完了後の待機時間
            time.sleep(3)
            logger.debug("? アカウント切り替え完了 → 覇者2セット処理開始")
            
            # 覇者2セット = 2回の処理実行
            for set_number in range(1, 3):  # 1セット目、2セット目
                logger.debug(f"{time.strftime('%Y-%m-%d %H:%M:%S')} - 覇者{set_number}セット目開始")
                
                # 各セット開始前にメモリ状況確認と継続保証
                import psutil
                memory_percent = psutil.virtual_memory().percent
                available_mb = psutil.virtual_memory().available / (1024 * 1024)
                
                logger.debug(f"?? セット{set_number}開始前メモリ状況: {memory_percent:.1f}% (利用可能: {available_mb:.0f}MB)")
                
                if memory_percent >= 98.0:
                    logger.error(f"?? セット{set_number}: 極限メモリ不足 {memory_percent:.1f}% - 緊急継続処理")
                    # 緊急継続処理
                    force_cleanup()
                    memory_monitor._extreme_cleanup()
                    time.sleep(3)
                elif memory_percent >= 95.0:
                    logger.warning(f"?? セット{set_number}: メモリ不足 {memory_percent:.1f}% - 予防処理実行")
                    force_cleanup()
                    time.sleep(2)
                
                # 処理継続保証の確認
                new_memory_percent = psutil.virtual_memory().percent
                if new_memory_percent >= 97.0:
                    logger.warning(f"? セット{set_number}: メモリ不足継続 {new_memory_percent:.1f}% - 継続強化モード")
                    memory_monitor.consecutive_critical_count += 1
                
                # ===========================================
                # 【重要】各セット開始前の事前準備処理（ログイン + 覇者準備）
                # ===========================================
                
                if set_number == 1:
                    # 1セット目用事前準備処理
                    set1_folders = set(range(current_folder_base, current_folder_base + 8))
                    logger.debug(f"覇者1セット目開始: フォルダ{sorted(set1_folders)}でログイン処理を開始...")
                    
                    # 処理済みフォルダに記録（ダブり防止）
                    processed_folders.update(set1_folders)
                    logger.debug(f"?? 処理済みフォルダ更新: {sorted(processed_folders)}")
                    selected_ports = self._get_validated_ports()
                    if selected_ports is None:
                        logger.error("? 端末設定が取得できません")
                        return
                    
                    # 1セット目用のログイン処理を並行実行（完全完了待機）
                    import concurrent.futures
                    from login_operations import device_operation_login
                    from monst.logging import MultiDeviceLogger
                    
                    ml = MultiDeviceLogger(selected_ports)
                    worker_count = min(len(selected_ports), MAX_PARALLEL_DEVICE_TASKS)
                    with concurrent.futures.ThreadPoolExecutor(max_workers=worker_count) as exe:
                        fs = [exe.submit(device_operation_login, p, str(current_folder_base + i), ml) 
                              for i, p in enumerate(selected_ports)]
                        
                        # 完全完了待機（重要！）
                        done, _ = concurrent.futures.wait(fs, return_when=concurrent.futures.ALL_COMPLETED)
                        
                        # 失敗した処理があるかチェック
                        for future in done:
                            try:
                                result = future.result()
                                logger.debug(f"? 1セット目ログイン処理完了: {result}")
                            except Exception as e:
                                logger.error(f"? 1セット目ログイン処理失敗: {e}")
                    
                    ml.summarize_results("覇者1セット目8端末ログイン")
                    logger.debug("? 覇者1セット目: 8端末ログイン処理完全完了 → 覇者初期処理開始")
                    time.sleep(5)  # ログイン完了確認時間
                    
                    # 1セット目用覇者初期処理（クエスト表示など）を8端末で実行
                    logger.info("覇者1セット目: 覇者初期処理（クエスト表示・覇者の塔選択）開始...")
                    
                    # 覇者初期処理のクエスト選択部分のみを8端末で並行実行（完全完了待機）
                    ml2 = MultiDeviceLogger(selected_ports)
                    worker_count = min(len(selected_ports), MAX_PARALLEL_DEVICE_TASKS)
                    with concurrent.futures.ThreadPoolExecutor(max_workers=worker_count) as exe:
                        # 各端末で覇者初期処理を実行
                        fs = [exe.submit(self._execute_hasya_quest_preparation, p, str(current_folder_base + i), ml2) 
                              for i, p in enumerate(selected_ports)]
                        
                        # 完全完了待機（重要！）
                        done, _ = concurrent.futures.wait(fs, return_when=concurrent.futures.ALL_COMPLETED)
                        
                        # 失敗した処理があるかチェック
                        for future in done:
                            try:
                                result = future.result()
                                logger.debug(f"? 1セット目覇者準備処理完了: {result}")
                            except Exception as e:
                                logger.error(f"? 1セット目覇者準備処理失敗: {e}")
                    
                    ml2.summarize_results("覇者1セット目クエスト準備")
                    logger.debug("? 覇者1セット目: 覇者初期処理完全完了 → app実行開始")
                    time.sleep(8)  # 覇者初期処理完了確認時間を大幅延長
                    
                elif set_number == 2:
                    # 2セット目は次の8フォルダに進む（ダブり処理防止強化）
                    previous_base = current_folder_base
                    current_folder_base = current_folder_base + 8
                    
                    # 重複チェック（ダブり処理防止）
                    set2_folders = set(range(current_folder_base, current_folder_base + 8))
                    duplicate_check = set2_folders.intersection(processed_folders)
                    if duplicate_check:
                        logger.error(f"?? 重複フォルダ検出: {sorted(duplicate_check)} - ダブり処理防止システム発動")
                        raise ValueError(f"フォルダ重複エラー: {sorted(duplicate_check)}")
                    
                    logger.debug(f"?? 覇者フォルダベース更新: {previous_base} → {current_folder_base}（ダブり処理防止）")
                    logger.debug(f"覇者2セット目: フォルダ{sorted(set2_folders)}で処理開始（1セット目：{previous_base}~{previous_base+7}完了済み）")
                    
                    # 処理済みフォルダに記録（ダブり防止）
                    processed_folders.update(set2_folders)
                    logger.debug(f"?? 処理済みフォルダ更新: {sorted(processed_folders)}")
                    
                    # ===========================================
                    # 【重要】2セット目開始前の新フォルダbinファイル書き込み処理
                    # ===========================================
                    logger.debug(f"?? 覇者2セット目開始前: 新フォルダbinファイル書き込み開始（フォルダ{current_folder_base}から8端末分）")
                    
                    selected_ports = self._get_validated_ports()
                    if selected_ports is None:
                        logger.error("? 端末設定が取得できません")
                        return
                    
                    # 2セット目用のbinファイル書き込み実行（最重要）
                    from multi_device import run_push
                    try:
                        run_push(current_folder_base, selected_ports)
                        logger.debug(f"? 2セット目binファイル書き込み完了: フォルダ{current_folder_base}~{current_folder_base+7}")
                    except Exception as e:
                        logger.error(f"? 2セット目binファイル書き込み失敗: {e}")
                        raise
                    
                    # bin書き込み完了後の待機時間
                    time.sleep(3)
                    logger.debug("? 2セット目アカウント切り替え完了 → ログイン処理開始")
                    
                    # 2セット目開始前に8端末のログイン処理を実行（重要！）
                    logger.info("覇者2セット目開始: 8端末ログイン処理を開始...")
                    selected_ports = self._get_validated_ports()
                    
                    # 8端末のログイン処理を並行実行（完全完了待機）
                    import concurrent.futures
                    from login_operations import device_operation_login
                    from monst.logging import MultiDeviceLogger
                    
                    ml = MultiDeviceLogger(selected_ports)
                    worker_count = min(len(selected_ports), MAX_PARALLEL_DEVICE_TASKS)
                    with concurrent.futures.ThreadPoolExecutor(max_workers=worker_count) as exe:
                        fs = [exe.submit(device_operation_login, p, str(current_folder_base + i), ml) 
                              for i, p in enumerate(selected_ports)]
                        
                        # 完全完了待機（重要！）
                        done, _ = concurrent.futures.wait(fs, return_when=concurrent.futures.ALL_COMPLETED)
                        
                        # 失敗した処理があるかチェック
                        for future in done:
                            try:
                                result = future.result()
                                logger.debug(f"? ログイン処理完了: {result}")
                            except Exception as e:
                                logger.error(f"? ログイン処理失敗: {e}")
                    
                    ml.summarize_results("覇者2セット目8端末ログイン")
                    logger.debug("? 覇者2セット目: 8端末ログイン処理完全完了 → 覇者初期処理開始")
                    time.sleep(5)  # ログイン完了確認時間を延長
                    
                    # 覇者初期処理（クエスト表示など）を8端末で実行
                    logger.info("覇者2セット目: 覇者初期処理（クエスト表示・覇者の塔選択）開始...")
                    from monst.device.hasya import device_operation_hasya
                    
                    # 覇者初期処理のクエスト選択部分のみを8端末で並行実行（完全完了待機）
                    ml2 = MultiDeviceLogger(selected_ports)
                    worker_count = min(len(selected_ports), MAX_PARALLEL_DEVICE_TASKS)
                    with concurrent.futures.ThreadPoolExecutor(max_workers=worker_count) as exe:
                        # 各端末で覇者初期処理を実行（ログインは既に完了しているのでクエスト選択のみ）
                        fs = [exe.submit(self._execute_hasya_quest_preparation, p, str(current_folder_base + i), ml2) 
                              for i, p in enumerate(selected_ports)]
                        
                        # 完全完了待機（重要！）
                        done, _ = concurrent.futures.wait(fs, return_when=concurrent.futures.ALL_COMPLETED)
                        
                        # 失敗した処理があるかチェック
                        for future in done:
                            try:
                                result = future.result()
                                logger.debug(f"? 覇者準備処理完了: {result}")
                            except Exception as e:
                                logger.error(f"? 覇者準備処理失敗: {e}")
                    
                    ml2.summarize_results("覇者2セット目クエスト準備")
                    logger.debug("? 覇者2セット目: 覇者初期処理完全完了 → app実行開始")
                    time.sleep(8)  # 覇者初期処理完了確認時間を大幅延長
                
                # 各セットでマクロ起動（フォルダベース指定）
                # 注意: 覇者準備処理が完全に完了してからマクロ起動
                logger.debug(f"覇者{set_number}セット: 全準備処理完了確認後、マクロ起動開始...")
                time.sleep(3)  # 準備処理の完全完了確認時間
                continue_hasya_with_base_folder(current_folder_base)
                
                # mon6のhost_ports/sub_ports再現
                from config import select_ports
                selected_ports = self._get_validated_ports()
                device_count = len(selected_ports)
                dynamic_host_ports, dynamic_sub_ports = self._get_dynamic_host_sub_ports(selected_ports)
                
                # mon6完全準拠の処理フロー（元バージョンと完全同一）：
                # ホスト端末でアイコン確認後は即座に次工程へ進む
                logger.debug(f"覇者{set_number}セット: ホスト端末（4,8）でアイコン待機開始...")
                self._run_multi_device_operation_mon6(device_operation_hasya_wait, dynamic_host_ports, f"覇者{set_number}セットホスト待機")
                logger.debug(f"覇者{set_number}セット: ホストアイコン確認完了。サブ終了検知をスキップして次工程へ進行")
                
                # アイコン検出完了→8端末マクロ操作開始（mon6準拠・タイミング調整）
                logger.debug(f"覇者{set_number}セット: アイコン検出完了→8端末マクロ操作開始")
                
                # OKボタン処理（間隔調整）
                for i in range(3):
                    tap_if_found_on_windows("tap", "ok.png", "macro")
                    time.sleep(2)  # 1秒→2秒に延長
                    
                # 8端末マクロ処理（間隔調整）
                from utils.gui_dialogs import multi_press_enhanced
                multi_press_enhanced()
                
                # マクロ終了確認（間隔調整）
                for i in range(8):
                    tap_if_found_on_windows("tap", "macro_fin.png", "macro")
                    time.sleep(2)  # 1秒→2秒に延長
                
                set_start_folder = int(current_folder_base)
                set_end_folder = set_start_folder + device_count - 1
                logger.info(f"フォルダ{set_start_folder:03d}-{set_end_folder:03d} の処理が完了")
                
                logger.debug(f"覇者{set_number}セット目完了")
                
                # 1セット完了後の待機（bin書き替えは2セット目開始前に実行済み）
                if set_number == 1:
                    logger.debug("覇者1セット完了 → 2セット目準備開始")
                    time.sleep(2)  # セット間の待機時間
            
            # 全2セット完了後のQWERASDFキー処理（mon6完全準拠）
            block_end = block_start + device_count * 2 - 1
            logger.info(f"フォルダ{block_start:03d}-{block_end:03d} の2セットが完了")
            logger.debug("覇者2セット完了: QWERASDF終了処理開始...")
            time.sleep(2)  # 処理確実化のための待機
            
            from utils.gui_dialogs import multi_press_enhanced
            multi_press_enhanced()
            
            # monst_macroウィンドウ有効化＋エンター処理（拡張タイミング）
            logger.debug("覇者2セット完了: monst_macroウィンドウ終了処理...")
            for i in range(8):
                tap_if_found_on_windows("tap", "macro_fin.png", "macro")
                time.sleep(2)  # 1秒→2秒に延長（ウィンドウ処理時間確保）
            
            # 処理完了後にメモリ監視を通常モードに戻す
            memory_monitor.cleanup_aggressive_mode = False
            memory_monitor.consecutive_critical_count = 0
            memory_monitor.check_interval = 60  # 通常間隔に戻す
            
            # 完了時メモリ状況確認
            final_memory_percent = psutil.virtual_memory().percent
            final_available_mb = psutil.virtual_memory().available / (1024 * 1024)
            logger.debug(f"?? 覇者2セット処理完了: メモリ監視を通常モードに復帰")
            logger.debug(f"?? 完了時メモリ状況: {final_memory_percent:.1f}% (利用可能: {final_available_mb:.0f}MB)")
            
            # 最終クリーンアップ（完了後のメモリ最適化）
            if final_memory_percent >= 85.0:
                logger.debug("?? 完了後クリーンアップ実行")
                force_cleanup()
            
            next_base_candidate = current_folder_base + 8
            _, next_folders = find_next_set_folders(next_base_candidate, device_count)
            if next_folders and len(next_folders) == device_count:
                next_start = int(next_folders[0])
                next_end = int(next_folders[-1])
                logger.info(f"次ブロック継続予定: フォルダ{next_start:03d}-{next_end:03d}")
                add_ops(next_start)
                return
            logger.info("覇者2セット処理完全終了")
        
        # ===================
        # フォルダ選択ダイアログを表示して処理を開始
        # ===================
        
        # 端末数設定を取得
        selected_ports = self._get_validated_ports()
        if selected_ports is None:
            return
            
        # タスクモニターを開始
        self._start_task_monitor(selected_ports)
        
        # フォルダ選択ダイアログを表示
        base_folder = get_target_folder()
        if base_folder is None:
            logger.error("フォルダが選択されませんでした。")
            return
        
        try:
            base_int = int(base_folder)
        except ValueError:
            logger.error(f"無効なフォルダ番号: {base_folder}")
            return
        
        if base_int > MAX_FOLDER_LIMIT:
            self._handle_folder_limit_exceeded(base_int)
        
        logger.debug(f"覇者2セット処理開始: フォルダ{base_int:03d}から")
        
        from adb_utils import reset_adb_server
        reset_adb_server()
        
        # 覇者2セット処理を実行
        add_ops(base_int)
    
    def _execute_hasya_quest_preparation(self, device_port: str, folder: str, multi_logger: Optional[MultiDeviceLogger] = None) -> bool:
        """覇者のクエスト準備処理のみを実行（ログイン済み端末用）。

        Args:
            device_port: 対象デバイスのポート
            folder: フォルダ名
            multi_logger: マルチデバイスロガー（オプション）

        Returns:
            bool: 操作が成功したかどうか
        """
        try:
            from monst.image import tap_if_found, tap_until_found

            logger.debug(f"覇者クエスト準備開始: {device_port} (フォルダ{folder})")

            while True:
                if tap_if_found('stay', device_port, "start.png", "quest"):
                    if not tap_if_found('stay', device_port, "dekki_null2.png", "key"):
                        break
                tap_if_found('tap', device_port, "quest_c.png", "key")
                tap_if_found('tap', device_port, "quest.png", "key")
                tap_if_found('tap', device_port, "ichiran.png", "key")
                tap_if_found('tap', device_port, "ok.png", "key")
                tap_if_found('tap', device_port, "close.png", "key")

                hasya_images = [
                    "hasyatou.png",
                    "hasyatou2.png",
                    "hasyatou3.png",
                    "hasyatou4.png",
                    "hasyatou5.png",
                    "hasyatou6.png",
                ]
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

            logger.debug(f"覇者クエスト準備完了: {device_port} (フォルダ{folder})")
            if multi_logger:
                multi_logger.log_success(device_port)
            return True

        except Exception as e:
            error_msg = f"覇者クエスト準備エラー: {str(e)} (フォルダ：{folder})"
            logger.error(error_msg, exc_info=True)
            if multi_logger:
                multi_logger.log_error(device_port, error_msg)
            return False
    def main_single(self) -> None:
        """Execute single device write operation (Single write)"""
        logger.info("シングル書き込みを開始します")
        
        try:
            # デバイスポート選択
            available_ports = [
                '127.0.0.1:62025', '127.0.0.1:62026', '127.0.0.1:62027',
                '127.0.0.1:62028', '127.0.0.1:62029', '127.0.0.1:62030',
                '127.0.0.1:62031', '127.0.0.1:62032'
            ]
            
            port = None
            try:
                port = self.core.select_device_port()
            except Exception:
                pass
            
            # GUIが失敗した場合、コンソール選択を使用
            if port is None:
                print("\n?? シングル書き込み - デバイスポート選択")
                print("利用可能なデバイスポート:")
                for i, available_port in enumerate(available_ports, 1):
                    print(f"  {i}. {available_port}")
                
                while True:
                    try:
                        choice = input(f"\nポート番号を選択してください (1-{len(available_ports)}, 0=キャンセル): ").strip()
                        
                        if choice == "0":
                            return
                        
                        if choice == "":
                            port = available_ports[0]
                            break
                            
                        choice_num = int(choice)
                        if 1 <= choice_num <= len(available_ports):
                            port = available_ports[choice_num - 1]
                            break
                        else:
                            print(f"無効な番号です。1-{len(available_ports)}の範囲で選択してください。")
                            
                    except (ValueError, KeyboardInterrupt):
                        print("無効な入力です。数字を入力してください。")
                        continue
            
            if port is None:
                return
            
            # フォルダ番号選択
            base = self.core.get_start_folder()
            if base is None:
                return
            
            # ソースファイル存在確認
            src = get_resource_path(f"{str(base).zfill(3)}/data10.bin", "bin_push")
            if src is None or not os.path.exists(src):
                error_msg = f"フォルダ{base:03d}にdata10.binファイルが見つかりません"
                logger.error(error_msg)
                display_message("エラー", error_msg)
                return
            
            # 処理実行
            reset_adb_server()
            close_monster_strike_app(port)
            run_adb_command(['push', src, "/data/data/jp.co.mixi.monsterstrike/data10.bin"], port)
            start_monster_strike_app(port)
            
            # アプリクラッシュ検出・復旧
            if not ensure_app_running(port):
                logger.error(f"アプリクラッシュ復旧失敗 (ポート: {port})")
                display_message("エラー", "アプリクラッシュが検出されました。\n手動でアプリを確認してください。")
                return
            
            # ログイン操作実行
            device_operation_login(port, str(base).zfill(3))
            
            # 操作後クラッシュチェック
            if check_app_crash(port):
                logger.warning(f"操作後にクラッシュ検出 (ポート: {port})")
            
            # 完了
            logger.info("シングル書き込みが完了しました")
                
        except Exception as e:
            error_msg = f"シングル書き込み中にエラーが発生しました: {e}"
            logger.error(error_msg)
            display_message("エラー", f"{error_msg}\n\n詳細はログを確認してください。")
            return
    
    def main_single_del(self) -> None:
        """Execute single device delete operation (Single initialization)"""
        logger.info("シングル初期化を開始します")
        
        try:
            # デバイスポート選択
            available_ports = [
                '127.0.0.1:62025', '127.0.0.1:62026', '127.0.0.1:62027',
                '127.0.0.1:62028', '127.0.0.1:62029', '127.0.0.1:62030',
                '127.0.0.1:62031', '127.0.0.1:62032'
            ]
            
            port = None
            try:
                port = self.core.select_device_port()
            except Exception:
                pass
            
            # GUIが失敗した場合、コンソール選択を使用
            if port is None:
                print("\n?? シングル初期化 - デバイスポート選択")
                print("利用可能なデバイスポート:")
                for i, available_port in enumerate(available_ports, 1):
                    print(f"  {i}. {available_port}")
                
                while True:
                    try:
                        choice = input(f"\nポート番号を選択してください (1-{len(available_ports)}, 0=キャンセル): ").strip()
                        
                        if choice == "0":
                            return
                        
                        if choice == "":
                            port = available_ports[0]
                            break
                            
                        choice_num = int(choice)
                        if 1 <= choice_num <= len(available_ports):
                            port = available_ports[choice_num - 1]
                            break
                        else:
                            print(f"無効な番号です。1-{len(available_ports)}の範囲で選択してください。")
                            
                    except (ValueError, KeyboardInterrupt):
                        print("無効な入力です。数字を入力してください。")
                        continue
            
            if port is None:
                return
            
            # 処理実行
            reset_adb_server()
            close_monster_strike_app(port)
            remove_data10_bin_from_nox(port)
            start_monster_strike_app(port)
            
            # 完了
            logger.info("シングル初期化が完了しました")
            
        except Exception as e:
            error_msg = f"シングル初期化中にエラーが発生しました: {e}"
            logger.error(error_msg)
            display_message("エラー", f"{error_msg}\n\n詳細はログを確認してください。")
            return
    
    def main_single_save(self) -> None:
        """Execute single device save operation (Single save)"""
        logger.info("シングル保存を開始します...")
        
        try:
            # デバイスポート選択
            available_ports = [
                '127.0.0.1:62025', '127.0.0.1:62026', '127.0.0.1:62027',
                '127.0.0.1:62028', '127.0.0.1:62029', '127.0.0.1:62030',
                '127.0.0.1:62031', '127.0.0.1:62032'
            ]
            
            port = None
            try:
                port = self.core.select_device_port()
            except Exception as gui_error:
                logger.warning(f"GUI選択エラー: {gui_error}")
            
            if port is None:
                print("\n=== シングル保存 - デバイスポート選択 ===")
                print("利用可能なデバイスポート:")
                for i, available_port in enumerate(available_ports, 1):
                    print(f"  {i}. {available_port}")
                
                while True:
                    try:
                        choice = input(f"\nポート番号を選択してください (1-{len(available_ports)}, 0=キャンセル): ").strip()
                        
                        if choice == "0":
                            print("処理をキャンセルしました。")
                            return
                        
                        if choice == "":
                            port = available_ports[0]
                            break
                            
                        choice_num = int(choice)
                        if 1 <= choice_num <= len(available_ports):
                            port = available_ports[choice_num - 1]
                            break
                        else:
                            print(f"無効な番号です。1-{len(available_ports)}の範囲で選択してください。")
                            
                    except (ValueError, KeyboardInterrupt):
                        print("無効な入力です。数字を入力してください。")
                        continue
            
            if port is None:
                logger.error("デバイスポートが選択されませんでした")
                return
            
            # 保存フォルダ名選択
            save_folder = None
            try:
                save_folder = get_target_folder()
                if save_folder:
                    save_folder = save_folder.strip()
            except Exception:
                pass
            
            if not save_folder:
                print("\n保存先フォルダ名を入力してください:")
                while True:
                    try:
                        save_folder = input("フォルダ名 (空白=single, 0=キャンセル): ").strip()
                        
                        if save_folder == "0":
                            return
                        
                        if save_folder == "":
                            save_folder = "single"
                            break
                        
                        if any(char in save_folder for char in '<>:"/\\|?*'):
                            print("無効な文字が含まれています。")
                            continue
                        
                        break
                        
                    except KeyboardInterrupt:
                        return
            
            if not save_folder:
                save_folder = "single"
            
            # ADBサーバーリセット
            reset_adb_server()
            
            # データファイルをプル（保存）
            success = pull_file_from_nox(port, save_folder)
            
            # 保存先確認
            from utils import get_base_path
            import os
            
            save_dir = os.path.join(get_base_path(), "bin_pull", save_folder)
            save_file = os.path.join(save_dir, "data10.bin")
            
            if os.path.exists(save_file) and os.path.getsize(save_file) > 0:
                logger.debug(f"シングル保存完了: {port} -> {save_folder}")
            else:
                logger.error("データファイルの保存に失敗しました")
                
        except Exception as e:
            error_msg = f"シングル保存中にエラーが発生しました: {e}"
            logger.error(error_msg)
            display_message("エラー", f"{error_msg}\n\n詳細はログを確認してください。")
            return
    
    
    
    
    
    
    
    
    
    
    
    
    
    
            
            
    
    
    
    
    
    
    
    
    

    
    def main_no_bin(self) -> None:
        """Execute no bin operation"""
        # 端末数設定を取得
        selected_ports = self._get_validated_ports()
        if selected_ports is None:
            return
            
        # タスクモニターを開始（すべての操作で表示）
        self._start_task_monitor(selected_ports)
        self._run_loop_wrapper(device_operation_nobin, "no bin", selected_ports)
    
    def main_id_check(self) -> None:
        """Execute ID check operation"""
        from monst.device.operations import id_check
        from utils.clipboard_manager import register_device_for_clipboard
        
        # 端末数設定を取得
        ports = self._get_validated_ports()
        if ports is None:
            return
        
        # 各端末をクリップボードマネージャーに登録（タイミングをずらすため）
        for i, device_port in enumerate(ports):
            register_device_for_clipboard(device_port, i)
        
        # タスクモニターを開始
        self._start_task_monitor(ports)
        
        logger.info("ID_Check処理を開始します")
        
        ml = MultiDeviceLogger(ports)
        
        # 並列処理でID確認を実行
        worker_count = min(len(ports), MAX_PARALLEL_DEVICE_TASKS)
        with concurrent.futures.ThreadPoolExecutor(max_workers=worker_count) as exe:
            futures = []
            for i, device_port in enumerate(ports):
                if self.core.is_stopping():
                    break
                    
                folder = f"{i+1:03d}"  # フォルダ番号を3桁で生成
                
                # 初期状態をタスクモニターに設定
                ml.update_task_status(device_port, folder, "ID_check準備中")
                
                # ID確認タスクを投入
                future = exe.submit(self._execute_id_check_with_monitoring, 
                                  device_port, folder, ml)
                futures.append(future)
            
            # 全てのタスク完了を待機
            concurrent.futures.wait(futures)
        
        # 完了状態をタスクモニターに設定
        for i, device_port in enumerate(ports):
            folder = f"{i+1:03d}"
            ml.update_task_status(device_port, folder, "ID_check完了")
        
        ml.summarize_results("ID_Check")
        logger.info("ID_Check処理完了")
    
    def _execute_id_check_with_monitoring(self, device_port: str, folder: str, 
                                        multi_logger: MultiDeviceLogger) -> None:
        """モニタリング付きでID確認を実行"""
        try:
            from monst.device.operations import id_check
            
            multi_logger.update_task_status(device_port, folder, "ID_check中")
            
            player_id = id_check(device_port, folder, multi_logger)
            
            if player_id and "COMPLETED" in player_id:
                multi_logger.log_success(device_port)
                multi_logger.update_task_status(device_port, folder, "ID_check成功")
            else:
                multi_logger.log_error(device_port, "ID確認失敗")
                multi_logger.update_task_status(device_port, folder, "ID_check失敗")
                
        except Exception as e:
            multi_logger.log_error(device_port, str(e))
            multi_logger.update_task_status(device_port, folder, "ID_checkエラー")
    
    def main_macro(self) -> None:
        """Execute macro operation"""
        base = get_target_folder()
        if base is None:
            logger.warning("フォルダが未指定。")
            return

        try:
            macro_number = int(base)
        except ValueError:
            logger.error(f"無効フォルダ: {base}")
            display_message("エラー", "数字を入力")
            return

        self._cleanup_macro_windows()

        try:
            load_macro(macro_number)
        finally:
            closed = self._cleanup_macro_windows()
            if closed:
                logger.info("Closed %s stray macro menu window(s)", closed)

    def main_loop_event(self) -> None:
        """Execute event quest operation"""
        # 端末数設定を取得
        selected_ports = self._get_validated_ports()
        if selected_ports is None:
            return
            
        # タスクモニターを開始（すべての操作で表示）
        self._start_task_monitor(selected_ports)
        self._run_loop_wrapper(device_operation_quest, "クエスト", selected_ports)
    
    def monitor_check(self) -> None:
        """Execute monitor check (disabled for safety)"""
        logger.info("デバイス監視テストは安全のため無効化されています。")
        logger.info("NOXの安定性を優先し、自動再起動機能を停止しました。")
    
    # ================== MM Folder Operations ==================
    
    def mm_folder_split(self) -> None:
        """MMフォルダ分割処理"""
        logger.info("● MMフォルダ分割開始")
        try:
            stats = create_mm_folders()
            total = sum(stats.values())
            if total > 0:
                # 結果詳細を作成
                result_details = []
                for mm_number, count in stats.items():
                    if count > 0:
                        result_details.append(f"{mm_number}: {count}フォルダ")
                
                result_text = f"MMフォルダ分割完了\n\n総処理数: {total}フォルダ\n\n" + "\n".join(result_details)
                display_message("完了", result_text)
            else:
                display_message("情報", "bin_pushフォルダに処理対象のデータが見つかりませんでした")
                logger.warning("● MMフォルダ分割: 処理対象なし")
        except Exception as e:
            logger.error(f"MMフォルダ分割エラー: {e}")
            display_message("エラー", f"MMフォルダ分割に失敗しました\n\nエラー内容:\n{e}")
    
    def mm_folder_batch_rename(self) -> None:
        """MMフォルダ一括リネーム処理"""
        import tkinter as tk
        from tkinter import filedialog
        
        logger.info("● フォルダ一括リネーム開始")
        
        try:
            # Excelファイル選択ダイアログ
            root = tk.Tk()
            root.withdraw()  # メインウィンドウを隠す
            root.lift()
            root.attributes('-topmost', True)
            
            # デフォルトでfolder_change.xlsxを指定
            default_excel = os.path.join(os.getcwd(), "folder_change.xlsx")
            initial_dir = os.path.dirname(default_excel) if os.path.exists(default_excel) else os.getcwd()
            initial_file = "folder_change.xlsx" if os.path.exists(default_excel) else ""
            
            excel_path = filedialog.askopenfilename(
                title="リネーム用Excelファイルを選択してください",
                filetypes=[("Excel files", "*.xlsx"), ("Excel files (old)", "*.xls"), ("CSV files", "*.csv"), ("All files", "*.*")],
                defaultextension=".xlsx",
                initialdir=initial_dir,
                initialfile=initial_file
            )
            
            root.destroy()
            
            if not excel_path:
                logger.info("Excelファイル選択がキャンセルされました")
                return
            
            # ファイル拡張子に応じて適切な関数を選択
            file_extension = os.path.splitext(excel_path)[1].lower()
            if file_extension in ['.xlsx', '.xls']:
                # Excelファイルの場合
                results = batch_rename_folders_excel(excel_path)
                file_type = "Excel"
            elif file_extension == '.csv':
                # CSVファイルの場合（互換性維持）
                results = batch_rename_folders_csv(excel_path)
                file_type = "CSV"
            else:
                display_message("エラー", f"サポートされていないファイル形式です: {file_extension}")
                return
            
            if not results:
                display_message("エラー", f"{file_type}ファイルの読み込みに失敗しました")
                return
            
            # 結果集計
            success_count = sum(1 for success in results.values() if success)
            fail_count = len(results) - success_count
            
            if success_count > 0:
                # 成功詳細を作成
                success_list = [folder for folder, success in results.items() if success]
                fail_list = [folder for folder, success in results.items() if not success]
                
                result_text = f"フォルダ一括リネーム完了\n\n"
                result_text += f"総処理数: {len(results)}フォルダ\n"
                result_text += f"成功: {success_count}フォルダ\n"
                result_text += f"失敗: {fail_count}フォルダ\n\n"
                
                if success_count > 0:
                    result_text += "成功したフォルダ:\n" + "\n".join(success_list[:10])
                    if len(success_list) > 10:
                        result_text += f"\n...他{len(success_list) - 10}個"
                
                if fail_count > 0:
                    result_text += "\n\n失敗したフォルダ:\n" + "\n".join(fail_list[:5])
                    if len(fail_list) > 5:
                        result_text += f"\n...他{len(fail_list) - 5}個"
                
                result_text += "\n\nリネーム結果は 'rename_result' フォルダに保存されました"
                
                display_message("完了", result_text)
            else:
                display_message("情報", "リネーム処理対象のフォルダが見つかりませんでした")
                logger.warning("● フォルダ一括リネーム: 処理対象なし")
                
        except Exception as e:
            logger.error(f"フォルダ一括リネームエラー: {e}")
            display_message("エラー", f"フォルダ一括リネームに失敗しました\n\nエラー内容:\n{e}")
    
    def _start_task_monitor(self, ports: list[str]) -> None:
        """Task monitor is disabled to reduce overhead."""
        logger.debug('Task monitor disabled; skipping startup.')


    def _execute_with_monitoring(self, operation: Callable, device_port: str, folder: str, 
                                multi_logger: MultiDeviceLogger, operation_name: str) -> None:
        """モニタリング付きで操作を実行"""
        try:
            folder_str = folder if folder else "---"
            multi_logger.update_task_status(device_port, folder_str, f"{operation_name}中")
            
            if folder is not None:
                operation(device_port, folder, multi_logger)
            else:
                operation(device_port, multi_logger)
                
            multi_logger.log_success(device_port)
        except Exception as e:
            multi_logger.log_error(device_port, str(e))
            folder_str = folder if folder else "---"
            multi_logger.update_task_status(device_port, folder_str, f"{operation_name}エラー")






# Bind account-related helpers to OperationsManager
OperationsManager._get_main_and_sub_ports = account_ops._get_main_and_sub_ports
OperationsManager._load_main_device_data = account_ops._load_main_device_data
OperationsManager._perform_main_device_login = account_ops._perform_main_device_login
OperationsManager._process_sub_devices = account_ops._process_sub_devices
OperationsManager._initialize_sub_devices = account_ops._initialize_sub_devices
OperationsManager._setup_sub_accounts = account_ops._setup_sub_accounts
OperationsManager._setup_single_sub_account = account_ops._setup_single_sub_account
OperationsManager._wait_for_account_name_simple = account_ops._wait_for_account_name_simple
OperationsManager._execute_account_creation_steps = account_ops._execute_account_creation_steps
OperationsManager._input_account_name_fast = account_ops._input_account_name_fast
OperationsManager._confirm_account_creation_fast = account_ops._confirm_account_creation_fast
OperationsManager._complete_initial_quest_fast = account_ops._complete_initial_quest_fast
OperationsManager._wait_for_room_via_login = account_ops._wait_for_room_via_login
OperationsManager._execute_friend_registration = account_ops._execute_friend_registration
OperationsManager._execute_main_terminal_friend_processing = account_ops._execute_main_terminal_friend_processing
OperationsManager._execute_sequential_friend_processing = account_ops._execute_sequential_friend_processing
OperationsManager._execute_single_sub_friend_processing = account_ops._execute_single_sub_friend_processing
OperationsManager._wait_for_account_name_screen = account_ops._wait_for_account_name_screen
OperationsManager._input_account_name = account_ops._input_account_name
OperationsManager._execute_sub_terminal_friend_approval = account_ops._execute_sub_terminal_friend_approval
OperationsManager._execute_main_terminal_final_confirmation = account_ops._execute_main_terminal_final_confirmation
OperationsManager._confirm_account_creation = account_ops._confirm_account_creation
OperationsManager._complete_initial_quest = account_ops._complete_initial_quest
OperationsManager._wait_for_room_screen = account_ops._wait_for_room_screen
OperationsManager.main_friend_registration = account_ops.main_friend_registration
OperationsManager.main_new_save = account_ops.main_new_save
