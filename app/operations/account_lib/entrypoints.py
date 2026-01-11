"""Account operation helpers."""

from __future__ import annotations

from .common import (
    pyautogui,
    time,
    openpyxl,
    ThreadPoolExecutor,
    as_completed,
    logger,
    display_message,
    get_target_folder,
    create_mm_folders,
    get_mm_folder_status,
    clean_mm_folders,
    batch_rename_folders_csv,
    batch_rename_folders_excel,
)

def main_friend_registration(self) -> None:
    """Execute friend registration system (Main + Sub devices)"""
    logger.info("フレンド登録システムを開始します...")

    try:
        # ①実行後まずは開始フォルダをダイヤログで指定
        start_folder = self.core.get_start_folder()
        if start_folder is None:
            logger.info("フォルダが指定されませんでした")
            return

        logger.debug(f"開始フォルダ: {start_folder}")

        # フォルダー進行システムで開始フォルダーを検証
        try:
            from folder_progression_system import FolderProgressionSystem
            if not FolderProgressionSystem.validate_folder(start_folder):
                logger.warning(f"?? 開始フォルダーが無効です: {start_folder} - 次の有効フォルダを検索します")

                # 無効フォルダの場合は次の有効フォルダを自動検索（ダイアログなし）
                try:
                    from folder_progression_system import ensure_continuous_processing
                    next_valid_folder = ensure_continuous_processing(start_folder)
                    if next_valid_folder:
                        start_folder = next_valid_folder
                        logger.debug(f"? 自動検索で有効フォルダ発見: {start_folder}")
                    else:
                        logger.error(f"? 有効フォルダが見つかりません - 処理を終了します")
                        return
                except Exception as e:
                    logger.error(f"? 有効フォルダ検索エラー: {e}")
                    return

            # フォルダー状況の概要を表示
            summary = FolderProgressionSystem.get_folder_status_summary()
            logger.debug(f"?? フォルダー状況: 総数{summary.get('total_folders', 0)}個")

        except Exception as validation_error:
            logger.warning(f"?? フォルダー検証エラー（処理継続）: {validation_error}")

        # メイン/サブ端末のポート設定を取得
        main_port, sub_ports = self._get_main_and_sub_ports()
        if not main_port or not sub_ports:
            logger.error("ポート設定の取得に失敗しました")
            return

        logger.debug(f"メイン端末: {main_port}")
        logger.debug(f"サブ端末: {len(sub_ports)}台 - {', '.join(sub_ports)}")

        current_folder = start_folder
        max_consecutive_folders = 9999  # 最大連続処理数制限（実質無制限：存在するフォルダまで継続）
        processed_count = 0

        # 【重要】初期フォルダのアカウント切り替え処理（最初のフォルダで必須）
        logger.debug(f"?? 初期アカウント切り替え開始: フォルダ{current_folder}")
        try:
            selected_ports = self._get_validated_ports()
            if selected_ports is not None:
                # デバイス接続確認（安全なアプローチ）
                from adb_utils import is_device_available
                available_ports = []
                for port in selected_ports:
                    if is_device_available(port):
                        available_ports.append(port)
                        logger.debug(f"? デバイス接続確認: {port}")
                    else:
                        logger.warning(f"?? デバイス接続確認失敗: {port}")

                if available_ports:
                    from mon_c2.multi_device import run_push
                    run_push(int(current_folder), available_ports)
                    logger.debug(f"? 初期アカウント切り替え完了: フォルダ{current_folder} (対象: {len(available_ports)}台)")
                    time.sleep(2)  # 初期切り替え完了待機
                else:
                    logger.error("? 利用可能なデバイスがありません")
            else:
                logger.error("? 初期アカウント切り替え失敗: 端末設定取得不可")
        except Exception as init_push_error:
            logger.error(f"? 初期アカウント切り替えエラー: {init_push_error}")
            # エラーでも処理継続

        while not self.core.is_stopping() and processed_count < max_consecutive_folders:
            # logger.debug(f"=== フォルダ {current_folder:03d} の処理開始 ===")
            processed_count += 1
            logger.debug(f"?? フォルダ処理進捗: {processed_count}/{max_consecutive_folders}")

            try:
                # ②メイン端末とサブ端末を同時並行処理で実行
                with ThreadPoolExecutor(max_workers=2) as executor:
                    # メイン端末のデータ読み込み処理
                    main_future = executor.submit(self._load_main_device_data, main_port, current_folder)

                    # サブ端末の初期化とアカウント作成処理
                    sub_future = executor.submit(self._process_sub_devices, sub_ports)

                    # 両方の処理結果を待機
                    try:
                        main_success = main_future.result(timeout=300)  # 5分タイムアウト
                        sub_success = sub_future.result(timeout=600)    # 10分タイムアウト

                        if not main_success:
                            logger.error(f"フォルダ {current_folder:03d} のメイン端末処理に失敗")
                            break

                        if not sub_success:
                            logger.error("サブ端末処理に失敗")
                            break

                    except TimeoutError:
                        logger.error("並行処理がタイムアウトしました")
                        break

                logger.debug(f"フォルダ {current_folder} の処理完了")

                # 自動継続の確認（連続処理制限に近づいたら警告）
                # 連続処理制限の警告は実質無制限なのでスキップ
                if processed_count > 0 and processed_count % 100 == 0:
                    logger.debug(f"?? 継続処理中: {processed_count}フォルダ処理済み")

                # フレンド登録用：存在するフォルダを絶対にスキップしないシステム
                try:
                    from folder_progression_system import ensure_continuous_processing, FolderProgressionSystem
                    next_folder = ensure_continuous_processing(current_folder)

                    if next_folder:
                        current_folder = next_folder
                        logger.debug(f"?? 次のフォルダーに移行: {next_folder}")

                        # 【重要】次のフォルダーのアカウント切り替え処理（data10.bin push）
                        logger.debug(f"?? アカウント切り替え開始: フォルダ{current_folder}のdata10.binをpush")
                        try:
                            # 端末設定取得
                            selected_ports = self._get_validated_ports()
                            if selected_ports is None:
                                logger.error("? アカウント切り替え失敗: 端末設定取得不可")
                            else:
                                # デバイス接続確認（安全なアプローチ）
                                from adb_utils import is_device_available
                                available_ports = []
                                for port in selected_ports:
                                    if is_device_available(port):
                                        available_ports.append(port)
                                    else:
                                        logger.warning(f"?? フォルダ移行時デバイス接続確認失敗: {port}")

                                if available_ports:
                                    from mon_c2.multi_device import run_push
                                    run_push(int(current_folder), available_ports)
                                    logger.debug(f"? アカウント切り替え完了: フォルダ{current_folder} (対象: {len(available_ports)}台)")
                                    time.sleep(2)  # 切り替え完了待機
                                else:
                                    logger.error("? フォルダ移行時: 利用可能なデバイスがありません")
                        except Exception as push_error:
                            logger.error(f"? アカウント切り替えエラー: {push_error}")
                            # エラーでも処理継続（旧アカウントでも処理可能）
                    else:
                        # ensure_continuous_processingで見つからない場合の強化検索
                        logger.warning(f"?? 標準検索でフォルダが見つかりません。強化検索を実行...")

                        # 手動で次のフォルダーを検索（絶対にスキップしない）
                        current_num = int(current_folder)
                        found_next = False

                        # 次の100フォルダまで徹底検索
                        for search_num in range(current_num + 1, current_num + 101):
                            search_folder = str(search_num)
                            if FolderProgressionSystem.validate_folder(search_folder):
                                current_folder = search_folder
                                logger.debug(f"? 強化検索で発見: {search_folder}（存在するフォルダを絶対実行）")

                                # 【重要】強化検索で見つかったフォルダーのアカウント切り替え処理
                                logger.debug(f"?? 強化検索後アカウント切り替え開始: フォルダ{current_folder}")
                                try:
                                    selected_ports = self._get_validated_ports()
                                    if selected_ports is not None:
                                        # デバイス接続確認（安全なアプローチ）
                                        from adb_utils import is_device_available
                                        available_ports = []
                                        for port in selected_ports:
                                            if is_device_available(port):
                                                available_ports.append(port)
                                            else:
                                                logger.warning(f"?? 強化検索時デバイス接続確認失敗: {port}")

                                        if available_ports:
                                            from mon_c2.multi_device import run_push
                                            run_push(int(current_folder), available_ports)
                                            logger.debug(f"? 強化検索後アカウント切り替え完了: フォルダ{current_folder} (対象: {len(available_ports)}台)")
                                            time.sleep(2)
                                        else:
                                            logger.error("? 強化検索時: 利用可能なデバイスがありません")
                                except Exception as push_error:
                                    logger.error(f"? 強化検索後アカウント切り替えエラー: {push_error}")

                                found_next = True
                                break
                            else:
                                # 存在しないフォルダのログは最小化（スパム防止）
                                if search_num <= current_num + 10:  # 最初の10個のみログ出力
                                    logger.debug(f"?? フォルダ{search_folder}: 存在しないためスキップ")

                        if not found_next:
                            logger.info("?? 全てのフォルダー検索完了（100フォルダ先まで検索済み）")
                            break

                    # EXE実行時は一定間隔で自動停止オプション
                    if getattr(sys, 'frozen', False) and processed_count % 10 == 0:
                        logger.debug(f"?? {processed_count}フォルダ処理完了 - 継続中...")
                        time.sleep(1)  # CPU負荷軽減

                except Exception as progression_error:
                    logger.error(f"? フォルダー進行システムエラー: {progression_error}")
                    # 最終フォールバック: loop_protection活用の強制継続
                    from loop_protection import loop_protection

                    operation_key = f"friend_folder_progression_{current_folder}"
                    if not loop_protection.register_attempt(operation_key, int(current_folder), str(progression_error)):
                        logger.warning(f"?? フォルダ{current_folder}: 最大試行回数到達も強制継続")

                    try:
                        current_num = int(current_folder) + 1
                        current_folder = str(current_num)
                        logger.warning(f"?? 最終フォールバック実行: {current_folder}（絶対にスキップしない）")
                    except ValueError:
                        # 番号解析失敗でも時刻ベースで継続
                        current_folder = str(max(1, int(time.time()) % 1000))
                        logger.error(f"? フォルダー番号解析失敗も強制継続: {current_folder}")
                        continue

            except Exception as folder_error:
                logger.error(f"フォルダ {current_folder} 処理中エラー: {folder_error}")

                # フォルダエラー時は自動的に次のフォルダに移行（ダイアログなし）
                logger.warning(f"?? フォルダ {current_folder} でエラー発生 - 自動的に次のフォルダに移行します")

                # エラー発生時の処理改善：スキップ防止＋loop_protection活用
                from loop_protection import loop_protection

                # loop_protectionでリトライ管理（スキップ絶対防止）
                operation_key = f"folder_processing_{current_folder}"

                # バックステップが必要かチェック
                if loop_protection.should_backtrack(operation_key, int(current_folder)):
                    backtrack_folder_num = loop_protection.execute_backtrack(operation_key, int(current_folder))
                    if backtrack_folder_num is not None:
                        current_folder = str(backtrack_folder_num)
                        logger.warning(f"?? バックステップ実行: フォルダ{current_folder}に戻って再実行")
                        # バックステップ後は確実に実行（スキップしない）
                        continue
                    else:
                        logger.error(f"? バックステップ限界到達: フォルダ{current_folder}")

                # リトライ回数を管理してスキップ防止
                if not loop_protection.register_attempt(operation_key, int(current_folder), "processing_error"):
                    logger.warning(f"?? フォルダ{current_folder}: 最大試行回数到達も強制継続")

                # フレンド登録エラー時フォルダー進行（必ず実行・絶対にスキップしない）
                try:
                    from folder_progression_system import ensure_continuous_processing, FolderProgressionSystem
                    next_folder = ensure_continuous_processing(current_folder)

                    if next_folder:
                        current_folder = next_folder
                        logger.debug(f"?? エラー後の次フォルダーに移行（強制実行）: {next_folder}")

                        # 【重要】エラー後の次のフォルダーアカウント切り替え処理
                        logger.debug(f"?? エラー後アカウント切り替え開始: フォルダ{current_folder}")
                        try:
                            selected_ports = self._get_validated_ports()
                            if selected_ports is not None:
                                # デバイス接続確認（安全なアプローチ）
                                from adb_utils import is_device_available
                                available_ports = []
                                for port in selected_ports:
                                    if is_device_available(port):
                                        available_ports.append(port)
                                    else:
                                        logger.warning(f"?? エラー後デバイス接続確認失敗: {port}")

                                if available_ports:
                                    from mon_c2.multi_device import run_push
                                    run_push(int(current_folder), available_ports)
                                    logger.debug(f"? エラー後アカウント切り替え完了: フォルダ{current_folder} (対象: {len(available_ports)}台)")
                                    time.sleep(2)
                                else:
                                    logger.error("? エラー後: 利用可能なデバイスがありません")
                        except Exception as push_error:
                            logger.error(f"? エラー後アカウント切り替えエラー: {push_error}")

                        continue
                    else:
                        # エラー後も強化検索で絶対にスキップしない
                        logger.warning(f"?? エラー後標準検索でフォルダが見つかりません。強化検索を実行...")
                        current_num = int(current_folder)
                        found_next = False

                        for search_num in range(current_num + 1, current_num + 101):
                            search_folder = str(search_num)
                            if FolderProgressionSystem.validate_folder(search_folder):
                                current_folder = search_folder
                                logger.debug(f"? エラー後強化検索で発見: {search_folder}（存在するフォルダを絶対実行）")

                                # 【重要】エラー後強化検索で見つかったフォルダーのアカウント切り替え処理
                                logger.debug(f"?? エラー後強化検索アカウント切り替え開始: フォルダ{current_folder}")
                                try:
                                    selected_ports = self._get_validated_ports()
                                    if selected_ports is not None:
                                        # デバイス接続確認（安全なアプローチ）
                                        from adb_utils import is_device_available
                                        available_ports = []
                                        for port in selected_ports:
                                            if is_device_available(port):
                                                available_ports.append(port)
                                            else:
                                                logger.warning(f"?? エラー後強化検索時デバイス接続確認失敗: {port}")

                                        if available_ports:
                                            from mon_c2.multi_device import run_push
                                            run_push(int(current_folder), available_ports)
                                            logger.debug(f"? エラー後強化検索アカウント切り替え完了: フォルダ{current_folder} (対象: {len(available_ports)}台)")
                                            time.sleep(2)
                                        else:
                                            logger.error("? エラー後強化検索時: 利用可能なデバイスがありません")
                                except Exception as push_error:
                                    logger.error(f"? エラー後強化検索アカウント切り替えエラー: {push_error}")

                                found_next = True
                                break

                        if not found_next:
                            logger.info("?? エラー後全てのフォルダー検索完了（100フォルダ先まで検索済み）")
                            break
                except Exception as progression_error:
                    logger.error(f"? エラー後のフォルダー進行失敗（フォールバック実行）: {progression_error}")
                    # フォールバック：どんなことがあっても次のフォルダを実行
                    try:
                        current_num = int(current_folder) + 1
                        current_folder = str(current_num)
                        logger.warning(f"?? 強制フォールバック実行: {current_folder}（絶対にスキップしない）")
                        continue
                    except ValueError:
                        # 番号解析失敗でも強制的に次を実行
                        current_folder = str(max(1, int(time.time()) % 100))  # 時刻ベースで適当なフォルダ番号
                        logger.error(f"? フォルダー番号解析失敗も強制実行: {current_folder}")
                        continue

        # 処理終了ログ
        # フォルダが存在する限り継続処理（実質無制限）
        logger.debug(f"? フレンド登録処理完了: {processed_count}フォルダ処理済み")
        logger.debug(f"?? 存在するフォルダをすべて処理しました（制限撤廃）")

        # フレンド処理完了後は継続実行可能状態を維持
        logger.info("?? フレンド登録システムは継続実行可能状態を維持します")
        logger.info("?? 新しいフォルダを追加すれば自動的に処理が継続されます")

        # 自動終了は行わず、GUIメニューに戻る
        # EXE実行時でも手動で終了するまで継続実行

    except Exception as e:
        error_msg = f"フレンド登録システム中にエラーが発生しました: {e}"
        logger.error(error_msg)
        from utils import display_message
        display_message("エラー", f"{error_msg}\n\n詳細はログを確認してください。")
        return


def main_new_save(self) -> None:
    """Execute Excel-based save operation"""
    # 端末数設定を取得
    selected_ports = self._get_validated_ports()
    if selected_ports is None:
        return

    try:
        wb = openpyxl.load_workbook('mon_aco.xlsx')
    except Exception as e:
        logger.error(f"Excelロード失敗: {e}")
        display_message("エラー", "mon_aco.xlsxを開けません")
        return

    total = wb.active.max_row
    row = get_target_folder()
    if row is not None:
        try: 
            row = int(row)
        except ValueError:
            logger.error(f"無効な行: {row}")
            display_message("エラー", "数字を入力")
            return
    else:
        return

    reset_adb_server()
    while row <= total and not self.core.is_stopping():
        remove_all_nox(selected_ports)
        events, args = [], []
        for p in selected_ports:
            if row > total: 
                break
            ev = threading.Event()
            events.append(ev)
            args.append((p, wb, row, row, ev))
            row += 1
        run_in_threads(device_operation_excel_and_save, args)
        for ev in events: 
            ev.wait()
        if row > total: 
            break
