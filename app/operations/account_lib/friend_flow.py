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

def _wait_for_room_via_login(self, port: str, device_num: int, sleep_time: float) -> bool:
    """ログイン処理（ROOMを見つけるまで）"""
    try:
        from monst.image import find_image_on_device
        from monst.adb import perform_action
        import random

        logger.debug(f"サブ端末{device_num}: ログイン処理（ROOM検索）を開始...")

        max_attempts = 50
        button_found = False

        # ログイン処理関数を呼び出してROOMを探す
        from login_operations import device_operation_login

        # 無限ループでROOMを見つけるまで継続
        attempt = 0
        while True:  # 成功するまで無限ループ
            try:
                # room.pngを直接チェック
                x, y = find_image_on_device(port, "room.png", "ui", threshold=0.8)
                if x is not None and y is not None:
                    logger.debug(f"サブ端末{device_num}: ROOM画面を初回検出 - 5秒後に再確認します")

                    # 5秒待機
                    time.sleep(5)

                    # 再度room.pngをチェック
                    x_retry, y_retry = find_image_on_device(port, "room.png", "ui", threshold=0.8)
                    if x_retry is not None and y_retry is not None:
                        logger.debug(f"サブ端末{device_num}: ? ROOM画面を再確認！全処理完了 (座標: {x_retry}, {y_retry})")
                        return True
                    else:
                        logger.warning(f"サブ端末{device_num}: ROOM画面再確認失敗 - ログイン処理継続")
                        # 再確認に失敗した場合は処理を継続

                # ログイン処理を実行（短時間）
                attempt += 1
                logger.debug(f"サブ端末{device_num}: ログイン処理実行中... (試行{attempt})")

                # 短時間のログイン動作
                for mini_attempt in range(10):
                    # 1. ログインボタンを探してクリック
                    button_found = False
                    for folder in ["login", "ui", "quest"]:
                        for image in ["doui.png", "ok.png", "start.png", "download.png", "gacha.png", "ok_queend.png", "zz_home2.png"]:
                            img_x, img_y = find_image_on_device(port, image, folder, threshold=0.75)
                            if img_x is not None and img_y is not None:
                                perform_action(port, 'tap', img_x, img_y)
                                time.sleep(sleep_time * 0.5)
                                button_found = True
                                break
                        if button_found:
                            break

                    # 2. ボタンが見つからない場合は画面左上当たりをタップ
                    if not button_found:
                        perform_action(port, 'tap', 150, 150)  # 画面左上当たり
                        time.sleep(sleep_time * 0.5)

                    # 3. 短時間待機
                    time.sleep(1)

                    # ROOMチェック
                    x, y = find_image_on_device(port, "room.png", "ui", threshold=0.8)
                    if x is not None and y is not None:
                        logger.debug(f"サブ端末{device_num}: ? ROOM画面検出！全処理完了 (座標: {x}, {y})")
                        return True

            except Exception as inner_e:
                logger.warning(f"サブ端末{device_num}: ログイン処理中エラー: {inner_e}")
                continue

    except Exception as e:
        logger.error(f"サブ端末{device_num}: room画面待機エラー: {e}")
        return False


def _execute_friend_registration(self, port: str, device_num: int, sleep_time: float) -> bool:
    """サブ端末でのフレンド登録処理"""
    try:
        from monst.image import find_image_on_device
        from monst.adb import perform_action

        logger.debug(f"サブ端末{device_num}: フレンド登録処理を開始...")

        # ⑨ friends.pngをクリック（ループ保護付き）
        if not find_and_click_with_protection(port, "friends.png", "ui", f"サブ端末{device_num}", 
                                            max_attempts=100, sleep_time=sleep_time * 0.5):
            logger.warning(f"サブ端末{device_num}: friends.png検索失敗")
            from loop_protection import loop_protection
            # バックステップ実行: フレンド処理を前の動作に戻す
            if loop_protection.should_backtrack(f"friend_init_{port}", device_num):
                backtrack_device = loop_protection.execute_backtrack(f"friend_init_{port}", device_num)
                if backtrack_device is not None:
                    logger.warning(f"?? バックステップ: サブ端末{device_num} → 前の処理に戻って再実行")
                    # フレンド処理を最初からやり直し
                    return self._execute_friend_registration(port, device_num, sleep_time)
            logger.error(f"? サブ端末{device_num}: バックステップ限界到達 - 処理中断")
            # 手動介入のため状態をリセットして継続可能にする
            from loop_protection import loop_protection
            logger.warning(f"?? 手動介入想定: サブ端末{device_num} ループ保護状態をリセット")
            loop_protection.reset_operation(f"friend_init_{port}", device_num)
            return False
        time.sleep(sleep_time * 2)

        # ⑩ friends_ok.png → friends_searchの順で押していく
        # まずfriends_ok.pngを探してクリック（ループ保護付き）
        ok_attempt = 0
        max_ok_attempts = 100  # 最大100回試行
        while ok_attempt < max_ok_attempts:
            # アプリ落ち検知
            from app_crash_recovery import check_app_crash
            if check_app_crash(port):
                logger.warning(f"サブ端末{device_num}: アプリ落ち検知 - 最初からやり直し")
                return self._execute_friend_registration(port, device_num, sleep_time)

            ok_x, ok_y = find_image_on_device(port, "friends_ok.png", "ui", threshold=0.8)
            if ok_x is not None and ok_y is not None:
                logger.debug(f"サブ端末{device_num}: ? friends_ok.pngクリック (座標: {ok_x}, {ok_y})")
                perform_action(port, 'tap', ok_x, ok_y)
                time.sleep(sleep_time * 2)
                break
            else:
                # friends_ok.pngが見つからない場合、friendsを再度クリック
                ok_attempt += 1
                if ok_attempt % 5 == 0:
                    logger.debug(f"サブ端末{device_num}: friends_ok.png未発見、friendsを再クリック (試行{ok_attempt})")
                    friends_x, friends_y = find_image_on_device(port, "friends.png", "ui", threshold=0.8)
                    if friends_x is not None and friends_y is not None:
                        perform_action(port, 'tap', friends_x, friends_y)
                        time.sleep(sleep_time * 2)

                # 上限チェック - バックステップ実行
                if ok_attempt >= max_ok_attempts:
                    logger.warning(f"サブ端末{device_num}: friends_ok.png検索上限到達 ({max_ok_attempts}回)")
                    from loop_protection import loop_protection
                    # バックステップ実行: 端末処理を前のステップに戻す
                    if loop_protection.should_backtrack(f"friend_register_{port}", device_num):
                        backtrack_device = loop_protection.execute_backtrack(f"friend_register_{port}", device_num)
                        if backtrack_device is not None:
                            logger.warning(f"?? バックステップ: サブ端末{device_num} → 前の処理に戻って再実行")
                            # フレンド処理を最初からやり直し
                            return self._execute_friend_registration(port, device_num, sleep_time)
                    logger.error(f"? サブ端末{device_num}: バックステップ限界到達 - 処理中断")
                    # 手動介入のため状態をリセットして継続可能にする
                    logger.warning(f"?? 手動介入想定: サブ端末{device_num} ループ保護状態をリセット")
                    loop_protection.reset_operation(f"friend_register_{port}", device_num)
                    return False

            time.sleep(sleep_time * 0.5)

        # 次にfriends_searchを探してクリック（ループ保護付き）
        search_found = False
        search_attempt = 0
        max_search_attempts = 100  # 最大100回試行
        while not search_found and search_attempt < max_search_attempts:
            # アプリ落ち検知
            from app_crash_recovery import check_app_crash
            if check_app_crash(port):
                logger.warning(f"サブ端末{device_num}: アプリ落ち検知 - 最初からやり直し")
                return self._execute_friend_registration(port, device_num, sleep_time)

            search_x, search_y = find_image_on_device(port, "friends_search.png", "ui", threshold=0.8)
            if search_x is not None and search_y is not None:
                logger.debug(f"サブ端末{device_num}: ? friends_searchクリック (座標: {search_x}, {search_y})")
                perform_action(port, 'tap', search_x, search_y)
                time.sleep(sleep_time * 2)
                search_found = True
                break
            else:
                # friends_searchが見つからない場合、friendsを再度クリック
                search_attempt += 1
                if search_attempt % 5 == 0:
                    logger.debug(f"サブ端末{device_num}: friends_search未発見、friendsを再クリック (試行{search_attempt})")
                    friends_x, friends_y = find_image_on_device(port, "friends.png", "ui", threshold=0.8)
                    if friends_x is not None and friends_y is not None:
                        perform_action(port, 'tap', friends_x, friends_y)
                        time.sleep(sleep_time * 2)

                # 上限チェック - バックステップ実行
                if search_attempt >= max_search_attempts:
                    logger.warning(f"サブ端末{device_num}: friends_search検索上限到達 ({max_search_attempts}回)")
                    from loop_protection import loop_protection
                    # バックステップ実行: 端末処理を前のステップに戻す
                    if loop_protection.should_backtrack(f"friend_search_{port}", device_num):
                        backtrack_device = loop_protection.execute_backtrack(f"friend_search_{port}", device_num)
                        if backtrack_device is not None:
                            logger.warning(f"?? バックステップ: サブ端末{device_num} → 前の処理に戻って再実行")
                            # フレンド処理を最初からやり直し
                            return self._execute_friend_registration(port, device_num, sleep_time)
                    logger.error(f"? サブ端末{device_num}: バックステップ限界到達 - 処理中断")
                    # 手動介入のため状態をリセットして継続可能にする
                    logger.warning(f"?? 手動介入想定: サブ端末{device_num} ループ保護状態をリセット")
                    loop_protection.reset_operation(f"friend_search_{port}", device_num)
                    return False

            time.sleep(sleep_time * 0.5)

        # ⑪ friends_copyを押してIDをコピー（ループ保護付き）
        copy_attempt = 0
        max_copy_attempts = 100  # 最大100回試行
        while copy_attempt < max_copy_attempts:
            # アプリ落ち検知
            from app_crash_recovery import check_app_crash
            if check_app_crash(port):
                logger.warning(f"サブ端末{device_num}: アプリ落ち検知 - 最初からやり直し")
                return self._execute_friend_registration(port, device_num, sleep_time)

            copy_x, copy_y = find_image_on_device(port, "friends_copy.png", "ui", threshold=0.8)
            if copy_x is not None and copy_y is not None:
                logger.debug(f"サブ端末{device_num}: ? friends_copyクリック、IDコピー実行 (座標: {copy_x}, {copy_y})")
                perform_action(port, 'tap', copy_x, copy_y)
                time.sleep(sleep_time * 2)
                break
            copy_attempt += 1
            if copy_attempt % 10 == 0:
                logger.debug(f"サブ端末{device_num}: friends_copy検索中... (試行{copy_attempt})")

            # 上限チェック - バックステップ実行
            if copy_attempt >= max_copy_attempts:
                logger.warning(f"サブ端末{device_num}: friends_copy検索上限到達 ({max_copy_attempts}回)")
                from loop_protection import loop_protection
                # バックステップ実行: 端末処理を前のステップに戻す
                if loop_protection.should_backtrack(f"friend_copy_{port}", device_num):
                    backtrack_device = loop_protection.execute_backtrack(f"friend_copy_{port}", device_num)
                    if backtrack_device is not None:
                        logger.warning(f"?? バックステップ: サブ端末{device_num} → 前の処理に戻って再実行")
                        # フレンド処理を最初からやり直し
                        return self._execute_friend_registration(port, device_num, sleep_time)
                logger.error(f"? サブ端末{device_num}: バックステップ限界到達 - 処理中断")
                # 手動介入のため状態をリセットして継続可能にする
                logger.warning(f"?? 手動介入想定: サブ端末{device_num} ループ保護状態をリセット")
                loop_protection.reset_operation(f"friend_copy_{port}", device_num)
                return False

            time.sleep(sleep_time * 0.5)

        logger.debug(f"サブ端末{device_num}: ? フレンド登録処理完了（IDコピー済み）")
        return True

    except Exception as e:
        logger.error(f"サブ端末{device_num}: フレンド登録処理エラー: {e}")
        return False


def _execute_main_terminal_friend_processing(self, main_port: str, sub_ports: list) -> bool:
    """メイン端末でのフレンド処理（各サブ端末のIDを検索・追加）"""
    try:
        from monst.image import find_image_on_device
        from monst.adb import perform_action

        logger.info("メイン端末: フレンド処理を開始...")
        base_sleep = 1.0

        # 各サブ端末に対してフレンド処理を実行
        for i, sub_port in enumerate(sub_ports, 1):
            logger.debug(f"メイン端末: サブ端末{i}のフレンド追加処理を開始...")

            # ⑫ メイン端末でfriends.pngを押す
            friends_found = False
            attempt = 0
            while not friends_found:  # friends.pngが見つかるまで無限ループ
                friends_x, friends_y = find_image_on_device(main_port, "friends.png", "ui", threshold=0.8)
                if friends_x is not None and friends_y is not None:
                    logger.debug(f"メイン端末: ? friends.pngクリック (座標: {friends_x}, {friends_y})")
                    perform_action(main_port, 'tap', friends_x, friends_y)
                    time.sleep(base_sleep * 2)
                    friends_found = True
                    break
                attempt += 1
                if attempt % 10 == 0:
                    logger.debug(f"メイン端末: friends.png検索中... (試行{attempt})")
                time.sleep(base_sleep * 0.5)

            # ⑬ friends_idが見つかるまで、friends_syotai、friends_ok、friends_kensakuを探して押し続ける
            logger.info("メイン端末: friends_id到達まで必要なボタンを順次押下...")
            id_x = None
            id_y = None
            navigation_attempt = 0

            while True:  # friends_idが見つかるまで無限ループ
                # まずfriends_idが見つかるかチェック
                id_x, id_y = find_image_on_device(main_port, "friends_id.png", "ui", threshold=0.8)
                if id_x is not None and id_y is not None:
                    logger.debug(f"メイン端末: ? friends_id発見！ナビゲーション完了 (座標: {id_x}, {id_y})")
                    break

                navigation_attempt += 1
                if navigation_attempt % 20 == 0:
                    logger.debug(f"メイン端末: friends_idナビゲーション中... (試行{navigation_attempt})")

                # friends_syotaiを探してクリック
                syotai_x, syotai_y = find_image_on_device(main_port, "friends_syotai.png", "ui", threshold=0.8)
                if syotai_x is not None and syotai_y is not None:
                    logger.debug(f"メイン端末: ? friends_syotaiクリック (座標: {syotai_x}, {syotai_y})")
                    perform_action(main_port, 'tap', syotai_x, syotai_y)
                    time.sleep(base_sleep * 1.5)
                    continue

                # friends_okを探してクリック
                ok_x, ok_y = find_image_on_device(main_port, "friends_ok.png", "ui", threshold=0.8)
                if ok_x is not None and ok_y is not None:
                    logger.debug(f"メイン端末: ? friends_okクリック (座標: {ok_x}, {ok_y})")
                    perform_action(main_port, 'tap', ok_x, ok_y)
                    time.sleep(base_sleep * 1.5)
                    continue

                # friends_kensakuを探してクリック
                kensaku_x, kensaku_y = find_image_on_device(main_port, "friends_kensaku.png", "ui", threshold=0.8)
                if kensaku_x is not None and kensaku_y is not None:
                    logger.debug(f"メイン端末: ? friends_kensakuクリック (座標: {kensaku_x}, {kensaku_y})")
                    perform_action(main_port, 'tap', kensaku_x, kensaku_y)
                    time.sleep(base_sleep * 1.5)
                    continue

                # どのボタンも見つからない場合は少し待機
                time.sleep(base_sleep * 0.5)

            # ⑯ サブ端末からコピーされたIDをペーストする（テスト確認済みkeyevent方式を使用）
            logger.info("メイン端末: IDペースト実行...")
            # まずテキスト入力欄をクリックしてフォーカス
            perform_action(main_port, 'tap', id_x, id_y)
            time.sleep(base_sleep * 1)

            # 確実性の高いkeyevent方式でIDをペースト
            paste_success = False
            try:
                import win32clipboard
                from monst.adb.input import _send_text_keyevent_complete
                from monst.adb import run_adb_command

                # Windowsクリップボードからテキストを取得
                logger.info("メイン端末: Windowsクリップボードからテキスト取得...")
                win32clipboard.OpenClipboard()

                # 確実な取得方法（テスト済み）
                clipboard_text = None
                try:
                    raw_data = win32clipboard.GetClipboardData(win32clipboard.CF_UNICODETEXT)
                    clipboard_text = str(raw_data).strip() if raw_data else None
                except:
                    try:
                        raw_data = win32clipboard.GetClipboardData(win32clipboard.CF_TEXT)
                        if isinstance(raw_data, bytes):
                            clipboard_text = raw_data.decode('utf-8').strip()
                        else:
                            clipboard_text = str(raw_data).strip()
                    except:
                        clipboard_text = None

                win32clipboard.CloseClipboard()

                if clipboard_text:
                    logger.debug(f"メイン端末: クリップボードテキスト取得成功: {clipboard_text}")

                    # アカウント名入力と同じkeyevent完全方式を使用（テスト確認済み）
                    logger.info("メイン端末: keyevent方式でID入力開始...")

                    # まず入力欄をクリア（バックスペース5回）
                    for i in range(5):
                        run_adb_command(["-s", main_port, "shell", "input", "keyevent", "67"])  # BACKSPACE
                        time.sleep(0.2)

                    # アカウント名入力と完全同一の方法で確実に入力
                    result = _send_text_keyevent_complete(main_port, clipboard_text)
                    if result:
                        logger.info("メイン端末: ? keyevent方式でID入力完了（成功率: 高い）")
                        paste_success = True
                    else:
                        logger.warning("メイン端末: keyevent方式で問題が発生した可能性があります")

                else:
                    logger.warning("メイン端末: クリップボードが空またはテキストでない")

            except ImportError:
                logger.warning("メイン端末: win32clipboard モジュールが利用できません")
            except Exception as paste_error:
                logger.warning(f"メイン端末: keyevent方式エラー: {paste_error}")

            # フォールバック: Ctrl+V キーイベント送信
            if not paste_success:
                try:
                    from monst.adb import run_adb_command
                    logger.info("メイン端末: フォールバック - Ctrl+V キーイベント送信...")
                    # Ctrl+V を送信 (KEYCODE_CTRL_LEFT + KEYCODE_V)
                    run_adb_command(["-s", main_port, "shell", "input", "keyevent", "113", "51"])
                    logger.info("メイン端末: ? Ctrl+V キーイベント送信完了")
                except Exception as fallback_error:
                    logger.error(f"メイン端末: Ctrl+V キーイベントエラー: {fallback_error}")

            time.sleep(base_sleep * 1.5)

            # ⑰ friends_endが見つかるまでfriends_ok、friends_last、searchを押す
            logger.info("メイン端末: friends_end到達まで検索処理実行...")
            search_attempt = 0

            while True:  # friends_endが見つかるまで無限ループ
                # まずfriends_endが見つかるかチェック
                end_x, end_y = find_image_on_device(main_port, "friends_end.png", "ui", threshold=0.8)
                if end_x is not None and end_y is not None:
                    logger.debug(f"メイン端末: ? friends_end発見！検索処理完了 (座標: {end_x}, {end_y})")
                    break

                search_attempt += 1
                if search_attempt % 20 == 0:
                    logger.debug(f"メイン端末: friends_end検索処理中... (試行{search_attempt})")

                # friends_okを優先してクリック（friends_lastより優先）
                ok_x, ok_y = find_image_on_device(main_port, "friends_ok.png", "ui", threshold=0.8)
                if ok_x is not None and ok_y is not None:
                    logger.debug(f"メイン端末: ? friends_okクリック（最優先） (座標: {ok_x}, {ok_y})")
                    perform_action(main_port, 'tap', ok_x, ok_y)
                    time.sleep(base_sleep * 1.5)
                    continue

                # searchを探してクリック（2番目の優先順位）
                search_x, search_y = find_image_on_device(main_port, "search.png", "ui", threshold=0.8)
                if search_x is not None and search_y is not None:
                    logger.debug(f"メイン端末: ? searchクリック（検索処理） (座標: {search_x}, {search_y})")
                    perform_action(main_port, 'tap', search_x, search_y)
                    time.sleep(base_sleep * 2.5)  # 検索完了待機
                    continue

                # friends_lastを探してクリック（最後の選択肢）
                last_x, last_y = find_image_on_device(main_port, "friends_last.png", "ui", threshold=0.8)
                if last_x is not None and last_y is not None:
                    logger.debug(f"メイン端末: ? friends_lastクリック（検索処理） (座標: {last_x}, {last_y})")
                    perform_action(main_port, 'tap', last_x, last_y)
                    time.sleep(base_sleep * 1.5)
                    continue

                # どのボタンも見つからない場合は少し待機
                time.sleep(base_sleep * 0.5)

            # ⑱ friends_okを押す（最終確認）
            final_attempt = 0
            while True:  # 最終friends_okが見つかるまで無限ループ
                final_ok_x, final_ok_y = find_image_on_device(main_port, "friends_ok.png", "ui", threshold=0.8)
                if final_ok_x is not None and final_ok_y is not None:
                    logger.debug(f"メイン端末: ? 最終friends_okクリック (座標: {final_ok_x}, {final_ok_y})")
                    perform_action(main_port, 'tap', final_ok_x, final_ok_y)
                    time.sleep(base_sleep * 2)
                    break
                final_attempt += 1
                if final_attempt % 10 == 0:
                    logger.debug(f"メイン端末: 最終friends_ok検索中... (試行{final_attempt})")
                time.sleep(base_sleep * 0.5)

            logger.debug(f"メイン端末: ? サブ端末{i}のフレンド追加処理完全完了")
            time.sleep(base_sleep)  # 次のサブ端末処理前に待機

        logger.info("メイン端末: ? 全サブ端末のフレンド処理完了")
        return True

    except Exception as e:
        logger.error(f"メイン端末: フレンド処理エラー: {e}")
        return False


def _execute_sequential_friend_processing(self, sub_ports: list) -> bool:
    """サブ端末1から順次フレンド処理を実行"""
    try:
        from config import get_config
        config = get_config()
        base_sleep = max(getattr(config, 'login_sleep', 2), 1)

        logger.info("=== 順次フレンド処理開始 ===")
        logger.debug(f"対象サブ端末: {len(sub_ports)}台")

        # サブ端末1から順次処理
        for i, port in enumerate(sub_ports, 1):
            logger.debug(f"サブ端末{i}: フレンド処理を開始...")
            try:
                # サブ端末でフレンド登録処理（IDコピー）
                if self._execute_friend_registration(port, i, base_sleep):
                    logger.debug(f"サブ端末{i}: ? フレンド登録処理完了")

                    # メイン端末でそのサブ端末のIDを検索・追加
                    main_port = "127.0.0.1:62025"  # メイン端末ポート
                    if self._execute_single_sub_friend_processing(main_port, port, i):
                        logger.debug(f"サブ端末{i}: ? メイン端末でのフレンド追加完了")
                    else:
                        logger.warning(f"サブ端末{i}: メイン端末でのフレンド追加に失敗")
                else:
                    logger.warning(f"サブ端末{i}: フレンド登録処理に失敗")

            except Exception as e:
                logger.error(f"サブ端末{i}: フレンド処理エラー: {e}")
                continue

        logger.info("=== 順次フレンド処理完了 ===")

        # ⑲ すべてのサブ端末で作業が完了したら、各サブ端末にてフレンド承認処理（同時進行）
        logger.info("=== サブ端末フレンド承認処理開始（同時進行） ===")
        from concurrent.futures import ThreadPoolExecutor, as_completed

        # 各サブ端末のフレンド承認処理を並列実行
        with ThreadPoolExecutor(max_workers=len(sub_ports)) as executor:
            # 各サブ端末に対してタスクを投入
            future_to_device = {}
            for i, port in enumerate(sub_ports, 1):
                logger.debug(f"サブ端末{i}: フレンド承認処理を並列開始...")
                future = executor.submit(self._execute_sub_terminal_friend_approval, port, i)
                future_to_device[future] = (port, i)

            # 各タスクの完了を待機
            for future in as_completed(future_to_device):
                port, device_num = future_to_device[future]
                try:
                    result = future.result()
                    if result:
                        logger.debug(f"サブ端末{device_num}: ? フレンド承認処理完了（並列）")
                    else:
                        logger.warning(f"サブ端末{device_num}: フレンド承認処理に失敗（並列）")
                except Exception as e:
                    logger.error(f"サブ端末{device_num}: フレンド承認処理エラー（並列）: {e}")

        logger.info("=== 全サブ端末フレンド承認処理完了 ===")

        # ⑳ 全サブ端末でその処理が終わったらメイン端末にて最終確認処理
        logger.info("=== メイン端末最終確認処理開始 ===")
        try:
            main_port = "127.0.0.1:62025"  # メイン端末ポート
            if self._execute_main_terminal_final_confirmation(main_port):
                logger.info("メイン端末: ? 最終確認処理完了")
            else:
                logger.warning("メイン端末: 最終確認処理に失敗")
        except Exception as e:
            logger.error(f"メイン端末: 最終確認処理エラー: {e}")

        # 最終的な完了ログのみ出力
        pass
        return True

    except Exception as e:
        logger.error(f"順次フレンド処理エラー: {e}")
        return False


def _execute_single_sub_friend_processing(self, main_port: str, sub_port: str, sub_device_num: int) -> bool:
    """メイン端末で単一サブ端末のフレンド処理を実行"""
    try:
        from monst.image import find_image_on_device
        from monst.adb import perform_action

        logger.debug(f"メイン端末: サブ端末{sub_device_num}のフレンド追加処理を開始...")
        base_sleep = 1.0

        # ⑫ メイン端末でfriends.pngを押す（サブ端末1の場合のみ）
        if sub_device_num == 1:
            attempt = 0
            while True:  # friends.pngが見つかるまで無限ループ
                friends_x, friends_y = find_image_on_device(main_port, "friends.png", "ui", threshold=0.8)
                if friends_x is not None and friends_y is not None:
                    logger.debug(f"メイン端末: ? friends.pngクリック (座標: {friends_x}, {friends_y})")
                    perform_action(main_port, 'tap', friends_x, friends_y)
                    time.sleep(base_sleep * 2)
                    break
                attempt += 1
                if attempt % 10 == 0:
                    logger.debug(f"メイン端末: friends.png検索中... (試行{attempt})")
                time.sleep(base_sleep * 0.5)
        else:
            logger.debug(f"メイン端末: サブ端末{sub_device_num}はfriends.png検索をスキップ（既に開いている状態）")

        # ⑬ friends_idが見つかるまで、friends_syotai、friends_ok、friends_kensakuを探して押し続ける
        logger.debug(f"メイン端末: friends_id到達まで必要なボタンを順次押下...")
        id_x = None
        id_y = None
        navigation_attempt = 0

        while True:  # friends_idが見つかるまで無限ループ
            # まずfriends_idが見つかるかチェック
            id_x, id_y = find_image_on_device(main_port, "friends_id.png", "ui", threshold=0.8)
            if id_x is not None and id_y is not None:
                logger.debug(f"メイン端末: ? friends_id発見！ナビゲーション完了 (座標: {id_x}, {id_y})")
                break

            navigation_attempt += 1
            if navigation_attempt % 20 == 0:
                logger.debug(f"メイン端末: friends_idナビゲーション中... (試行{navigation_attempt})")

            # friends_syotaiを探してクリック
            syotai_x, syotai_y = find_image_on_device(main_port, "friends_syotai.png", "ui", threshold=0.8)
            if syotai_x is not None and syotai_y is not None:
                logger.debug(f"メイン端末: ? friends_syotaiクリック (座標: {syotai_x}, {syotai_y})")
                perform_action(main_port, 'tap', syotai_x, syotai_y)
                time.sleep(base_sleep * 1.5)
                continue

            # friends_okを探してクリック
            ok_x, ok_y = find_image_on_device(main_port, "friends_ok.png", "ui", threshold=0.8)
            if ok_x is not None and ok_y is not None:
                logger.debug(f"メイン端末: ? friends_okクリック (座標: {ok_x}, {ok_y})")
                perform_action(main_port, 'tap', ok_x, ok_y)
                time.sleep(base_sleep * 1.5)
                continue

            # friends_kensakuを探してクリック
            kensaku_x, kensaku_y = find_image_on_device(main_port, "friends_kensaku.png", "ui", threshold=0.8)
            if kensaku_x is not None and kensaku_y is not None:
                logger.debug(f"メイン端末: ? friends_kensakuクリック (座標: {kensaku_x}, {kensaku_y})")
                perform_action(main_port, 'tap', kensaku_x, kensaku_y)
                time.sleep(base_sleep * 1.5)
                continue

            # どのボタンも見つからない場合は少し待機
            time.sleep(base_sleep * 0.5)

        # ⑯ IDペーストを実行（テスト確認済みkeyevent方式を使用）
        logger.debug(f"メイン端末: IDペースト実行...")
        # まずテキスト入力欄をクリックしてフォーカス
        perform_action(main_port, 'tap', id_x, id_y)
        time.sleep(base_sleep * 1)

        # 確実性の高いkeyevent方式でIDをペースト
        paste_success = False
        try:
            import win32clipboard
            from monst.adb.input import _send_text_keyevent_complete
            from monst.adb import run_adb_command

            # Windowsクリップボードからテキストを取得
            logger.debug(f"メイン端末: Windowsクリップボードからテキスト取得...")
            win32clipboard.OpenClipboard()

            # 確実な取得方法（テスト済み）
            clipboard_text = None
            try:
                raw_data = win32clipboard.GetClipboardData(win32clipboard.CF_UNICODETEXT)
                clipboard_text = str(raw_data).strip() if raw_data else None
            except:
                try:
                    raw_data = win32clipboard.GetClipboardData(win32clipboard.CF_TEXT)
                    if isinstance(raw_data, bytes):
                        clipboard_text = raw_data.decode('utf-8').strip()
                    else:
                        clipboard_text = str(raw_data).strip()
                except:
                    clipboard_text = None

            win32clipboard.CloseClipboard()

            if clipboard_text:
                logger.debug(f"メイン端末: クリップボードテキスト取得成功: {clipboard_text}")

                # アカウント名入力と同じkeyevent完全方式を使用（テスト確認済み）
                logger.debug(f"メイン端末: keyevent方式でID入力開始...")

                # まず入力欄をクリア（バックスペース5回）
                for i in range(5):
                    run_adb_command(["-s", main_port, "shell", "input", "keyevent", "67"])  # BACKSPACE
                    time.sleep(0.2)

                # アカウント名入力と完全同一の方法で確実に入力
                result = _send_text_keyevent_complete(main_port, clipboard_text)
                if result:
                    logger.debug(f"メイン端末: ? keyevent方式でID入力完了（成功率: 高い）")
                    paste_success = True
                else:
                    logger.warning(f"メイン端末: keyevent方式で問題が発生した可能性があります")

            else:
                logger.warning(f"メイン端末: クリップボードが空またはテキストでない")

        except ImportError:
            logger.warning(f"メイン端末: win32clipboard モジュールが利用できません")
        except Exception as paste_error:
            logger.warning(f"メイン端末: keyevent方式エラー: {paste_error}")

        # フォールバック: Ctrl+V キーイベント送信
        if not paste_success:
            try:
                from monst.adb import run_adb_command
                logger.debug(f"メイン端末: フォールバック - Ctrl+V キーイベント送信...")
                # Ctrl+V を送信 (KEYCODE_CTRL_LEFT + KEYCODE_V)
                run_adb_command(["-s", main_port, "shell", "input", "keyevent", "113", "51"])
                logger.debug(f"メイン端末: ? Ctrl+V キーイベント送信完了")
            except Exception as fallback_error:
                logger.error(f"メイン端末: Ctrl+V キーイベントエラー: {fallback_error}")

        time.sleep(base_sleep * 1.5)

        # ⑰ friends_endが見つかるまでfriends_yes、friends_last、searchを押す
        logger.debug(f"メイン端末: friends_end到達まで検索処理実行...")
        search_attempt = 0
        friends_last_used = False  # friends_lastを1度だけ使うためのフラグ

        while True:  # friends_endが見つかるまで無限ループ
            # まずfriends_endが見つかるかチェック
            end_x, end_y = find_image_on_device(main_port, "friends_end.png", "ui", threshold=0.8)
            if end_x is not None and end_y is not None:
                logger.debug(f"メイン端末: ? friends_end発見！検索処理完了 (座標: {end_x}, {end_y})")
                break

            search_attempt += 1
            if search_attempt % 20 == 0:
                logger.debug(f"メイン端末: friends_end検索処理中... (試行{search_attempt})")

            # friends_yesとfriends_lastを同時チェックして、yesを優先
            yes_x, yes_y = find_image_on_device(main_port, "friends_yes.png", "ui", threshold=0.8)
            last_x, last_y = find_image_on_device(main_port, "friends_last.png", "ui", threshold=0.8)

            if yes_x is not None and yes_y is not None:
                logger.debug(f"メイン端末: ? friends_yesクリック（優先・検索処理） (座標: {yes_x}, {yes_y})")
                perform_action(main_port, 'tap', yes_x, yes_y)
                time.sleep(base_sleep * 1.5)
                continue
            elif last_x is not None and last_y is not None and not friends_last_used:
                logger.debug(f"メイン端末: ? friends_lastクリック（1度のみ・検索処理） (座標: {last_x}, {last_y})")
                perform_action(main_port, 'tap', last_x, last_y)
                friends_last_used = True  # フラグを立てて1度だけに制限
                time.sleep(base_sleep * 1.5)
                continue

            # searchを探してクリック
            search_x, search_y = find_image_on_device(main_port, "search.png", "ui", threshold=0.8)
            if search_x is not None and search_y is not None:
                logger.debug(f"メイン端末: ? searchクリック（検索処理） (座標: {search_x}, {search_y})")
                perform_action(main_port, 'tap', search_x, search_y)
                time.sleep(base_sleep * 2.5)  # 検索完了待機
                continue

            # どのボタンも見つからない場合は少し待機
            time.sleep(base_sleep * 0.5)

        # ⑱ friends_okを押す（最終確認）
        final_attempt = 0
        while True:  # 最終friends_okが見つかるまで無限ループ
            final_ok_x, final_ok_y = find_image_on_device(main_port, "friends_ok.png", "ui", threshold=0.8)
            if final_ok_x is not None and final_ok_y is not None:
                logger.debug(f"メイン端末: ? 最終friends_okクリック (座標: {final_ok_x}, {final_ok_y})")
                perform_action(main_port, 'tap', final_ok_x, final_ok_y)
                time.sleep(base_sleep * 2)
                break
            final_attempt += 1
            if final_attempt % 10 == 0:
                logger.debug(f"メイン端末: 最終friends_ok検索中... (試行{final_attempt})")
            time.sleep(base_sleep * 0.5)

        logger.debug(f"メイン端末: ? サブ端末{sub_device_num}のフレンド追加処理完全完了")
        time.sleep(base_sleep)  # 次の処理前に待機
        return True

    except Exception as e:
        logger.error(f"メイン端末: サブ端末{sub_device_num}のフレンド処理エラー: {e}")
        return False


def _wait_for_room_screen(self, port: str, device_num: int, max_attempts: int = 30) -> bool:
    """room.pngが見つかるまでログイン動作を繰り返す"""
    try:
        from monst.image import get_device_screenshot, find_image_on_device
        from monst.adb.input import tap_on_screen, swipe_on_screen

        logger.debug(f"サブ端末{device_num}: ルーム画面を待機中...")

        for attempt in range(max_attempts):
            # room.pngをチェック（ルートディレクトリ）
            x, y = find_image_on_device(port, "room.png", threshold=0.8)
            if x is not None and y is not None:
                logger.debug(f"サブ端末{device_num}: ルーム画面を初回検出 - 5秒後に再確認します")

                # 5秒待機
                time.sleep(5)

                # 再度room.pngをチェック
                x_retry, y_retry = find_image_on_device(port, "room.png", threshold=0.8)
                if x_retry is not None and y_retry is not None:
                    logger.debug(f"サブ端末{device_num}: ? ルーム画面を再確認 - ログイン完了")
                    return True
                else:
                    logger.warning(f"サブ端末{device_num}: ルーム画面再確認失敗 - ログイン処理継続")
                    # 再確認に失敗した場合は処理を継続

            # まだルームに到達していない場合の基本操作
            tap_on_screen(port, 400, 600)
            time.sleep(1)

            swipe_on_screen(port, 400, 600, 400, 400)
            time.sleep(2)

            if attempt % 5 == 0:
                logger.debug(f"サブ端末{device_num}: ルーム画面待機中... (試行{attempt+1}/{max_attempts})")

        logger.error(f"サブ端末{device_num}: ルーム画面が見つかりませんでした")
        return False

    except Exception as e:
        logger.error(f"サブ端末{device_num}: ルーム画面待機エラー: {e}")
        return False
