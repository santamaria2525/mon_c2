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

def _wait_for_account_name_simple(self, port: str, device_num: int) -> bool:
    """ULTRATHINK版: account_name専用待機（単純で確実）"""
    try:
        from monst.image import find_image_on_device
        from monst.adb import perform_action

        # 高速設定
        from config import get_config
        config = get_config()
        base_sleep = max(getattr(config, 'login_sleep', 2), 1)  # 最低1秒

        # logger.debug(f"サブ端末{device_num}: ?? account_name.png専用待機開始")

        max_attempts = 100  # 十分な試行回数
        for attempt in range(max_attempts):

            # 毎回スクリーンショットを強制更新してaccount_nameをチェック
            account_x, account_y = find_image_on_device(port, "account_name.png", "ui", threshold=0.75)

            if account_x is not None and account_y is not None:
                logger.debug(f"サブ端末{device_num}: ?? account_name.png発見！ (座標: {account_x}, {account_y})")

                # account_nameをクリック
                perform_action(port, 'tap', account_x, account_y)
                logger.debug(f"サブ端末{device_num}: ? account_name.pngをクリック完了")
                time.sleep(1)
                return True

            # account_nameが見つからない場合は、ログイン進行のための最小限処理
            # ログインボタンをチェックしてクリック
            login_buttons = [
                ("doui.png", "login"),      # 同意ボタン（最優先）
                ("ok.png", "login"),        # OKボタン
                ("ok.png", "ui"),           # UI内のOKボタン  
                ("download.png", "login"),  # ダウンロードボタン
                ("start.png", "login")      # スタートボタン
            ]

            button_found = False
            for btn_name, folder in login_buttons:
                if not button_found:
                    btn_x, btn_y = find_image_on_device(port, btn_name, folder, threshold=0.75)
                    if btn_x is not None and btn_y is not None:
                        logger.debug(f"サブ端末{device_num}: ??? {btn_name}クリック (座標: {btn_x}, {btn_y})")
                        perform_action(port, 'tap', btn_x, btn_y)
                        time.sleep(base_sleep * 0.8)
                        button_found = True

            # 3. ボタンが見つからない場合は画面左上当たりをタップ
            if not button_found:
                perform_action(port, 'tap', 150, 150)  # 画面左上当たり
                time.sleep(base_sleep * 0.5)

                # たまにスワイプも実行
                if attempt % 5 == 0:
                    perform_action(port, 'swipe', 400, 600, 400, 400)
                    time.sleep(base_sleep * 0.5)

            # 進行状況を定期的に報告
            if attempt % 20 == 0:
                logger.debug(f"サブ端末{device_num}: account_name待機中... (試行 {attempt+1}/{max_attempts})")

            # 短い間隔で次の試行
            time.sleep(0.3)

        logger.error(f"サブ端末{device_num}: account_name.pngが{max_attempts}回の試行で見つかりませんでした")
        return False

    except Exception as e:
        logger.error(f"サブ端末{device_num}: account_name待機エラー: {e}")
        return False


def _execute_account_creation_steps(self, port: str, account_name: str, device_num: int) -> bool:
    """④～⑧のアカウント作成手順を実行（高速化版）"""
    try:
        from config import get_config
        config = get_config()
        base_sleep = max(getattr(config, 'login_sleep', 3), 1) * 0.7  # メイン端末より30%高速化

        # ⑤account_nameが出てきたらそれをクリックし、sub1～7という名前を付ける
        if not self._input_account_name_fast(port, account_name, device_num, base_sleep):
            return False

        # ⑥入力したら「ok」を押して「download」を押す
        if not self._confirm_account_creation_fast(port, device_num, base_sleep):
            return False

        # ⑦初期クエストが始まるのでクエスト完了まで実行
        if not self._complete_initial_quest_fast(port, device_num, base_sleep):
            return False

        # ⑧que_endが見つかったらログイン処理（ROOMを見つけるまで）
        if not self._wait_for_room_via_login(port, device_num, base_sleep):
            return False

        # ⑨ROOM画面まで到達完了（フレンド処理は後で順次実行）
        logger.debug(f"サブ端末{device_num}: ROOM画面到達完了 - フレンド処理は順次実行時に処理")

        return True

    except Exception as e:
        logger.error(f"サブ端末{device_num}: アカウント作成手順エラー: {e}")
        return False


def _input_account_name_fast(self, port: str, account_name: str, device_num: int, sleep_time: float) -> bool:
    """高速化版アカウント名入力"""
    try:
        from monst.image import find_image_on_device
        from monst.adb import perform_action
        from monst.adb.input import send_text_robust

        logger.debug(f"サブ端末{device_num}: アカウント名「{account_name}」を入力中...")

        # アカウント名を入力
        logger.debug(f"サブ端末{device_num}: ? アカウント名「{account_name}」の入力を開始します")
        send_text_robust(port, account_name)
        time.sleep(sleep_time)

        logger.debug(f"サブ端末{device_num}: ? アカウント名入力完了")
        return True

    except Exception as e:
        logger.error(f"サブ端末{device_num}: アカウント名入力エラー: {e}")
        return False


def _confirm_account_creation_fast(self, port: str, device_num: int, sleep_time: float) -> bool:
    """高速化版アカウント作成確定"""
    try:
        from monst.image import find_image_on_device
        from monst.adb import perform_action

        logger.debug(f"サブ端末{device_num}: アカウント作成を確定中...")

        # OKボタンを押す
        for attempt in range(10):
            x, y = find_image_on_device(port, "ok.png", "ui", threshold=0.8)
            if x is not None and y is not None:
                perform_action(port, 'tap', x, y)
                time.sleep(sleep_time)
                logger.debug(f"サブ端末{device_num}: ? OKボタンをクリック (座標: {x}, {y})")
                break
            time.sleep(sleep_time * 0.5)

        # downloadボタンを待機してクリック
        for attempt in range(20):
            x, y = find_image_on_device(port, "download.png", "login", threshold=0.8)
            if x is not None and y is not None:
                perform_action(port, 'tap', x, y)
                time.sleep(sleep_time)
                logger.debug(f"サブ端末{device_num}: ? downloadボタンをクリック (座標: {x}, {y})")
                return True
            time.sleep(sleep_time * 0.3)

        logger.warning(f"サブ端末{device_num}: downloadボタンが見つかりませんでした")
        return False

    except Exception as e:
        logger.error(f"サブ端末{device_num}: アカウント作成確定エラー: {e}")
        return False


def _complete_initial_quest_fast(self, port: str, device_num: int, sleep_time: float) -> bool:
    """高速化版初期クエスト完了"""
    try:
        from monst.image import find_image_on_device
        from monst.image.device_control import mon_swipe
        from monst.adb import perform_action
        import random

        logger.debug(f"サブ端末{device_num}: 初期クエスト実行中...")

        # que_endが見つかるまで無限ループ
        attempt = 0
        while True:
            # que_endを探す
            x, y = find_image_on_device(port, "que_end.png", "quest", threshold=0.8)
            if x is not None and y is not None:
                logger.debug(f"サブ端末{device_num}: ? que_end検出！初期クエスト完了 (座標: {x}, {y})")
                return True

            # questフォルダ内のok.pngをチェックしてクリック
            ok_x, ok_y = find_image_on_device(port, "ok.png", "quest", threshold=0.75)
            if ok_x is not None and ok_y is not None:
                logger.debug(f"サブ端末{device_num}: questフォルダのok.pngクリック (座標: {ok_x}, {ok_y})")
                perform_action(port, 'tap', ok_x, ok_y)
                time.sleep(sleep_time * 0.5)
                continue

            # 戦闘中のシュート（モンスト特有のスワイプ）
            mon_swipe(port)
            time.sleep(sleep_time * 0.3)

            # クエスト進行のためのランダムタップ・スワイプ
            tap_x = random.randint(350, 450)  # 400 ± 50
            tap_y = random.randint(550, 650)  # 600 ± 50
            perform_action(port, 'tap', tap_x, tap_y)
            time.sleep(sleep_time * 0.5)  # 高速化

            if attempt % 5 == 0:
                # ランダムスワイプ座標
                start_x = random.randint(350, 450)  # 400 ± 50
                start_y = random.randint(650, 750)  # 700 ± 50
                end_x = random.randint(350, 450)    # 400 ± 50  
                end_y = random.randint(250, 350)    # 300 ± 50
                perform_action(port, 'swipe', start_x, start_y, end_x, end_y)
                time.sleep(sleep_time * 0.3)

            attempt += 1
            if attempt % 20 == 0:
                logger.debug(f"サブ端末{device_num}: クエスト進行中... (試行{attempt})")

    except Exception as e:
        logger.error(f"サブ端末{device_num}: 初期クエスト実行エラー: {e}")
        return False


def _wait_for_account_name_screen(self, port: str, device_num: int, max_attempts: int = 100) -> bool:
    """account_name.pngが出るまでログイン動作を実施"""
    try:
        from monst.image import get_device_screenshot, find_image_on_device
        from monst.adb import perform_action

        logger.debug(f"サブ端末{device_num}: アカウント名入力画面を待機中...")

        attempt = 0
        while True:  # 成功するまで無限ループ
            # account_name.pngを探す（find_image_on_device内でスクリーンショット取得）
            x, y = find_image_on_device(port, "account_name.png", "ui", threshold=0.8)
            if x is not None and y is not None:
                logger.debug(f"サブ端末{device_num}: アカウント名入力画面を発見")
                return True

            # まだ見つからない場合は適当にタップして進める
            # 画面中央をタップ
            perform_action(port, 'tap', 400, 600)
            time.sleep(1)

            # スワイプも試行（チュートリアル進行用）
            perform_action(port, 'swipe', 400, 600, 400, 400)
            time.sleep(2)

            attempt += 1
            if attempt % 5 == 0:
                logger.debug(f"サブ端末{device_num}: アカウント名画面待機中... (試行{attempt})")

    except Exception as e:
        logger.error(f"サブ端末{device_num}: アカウント名画面待機エラー: {e}")
        return False


def _input_account_name(self, port: str, account_name: str, device_num: int) -> bool:
    """アカウント名を入力"""
    try:
        from monst.image import get_device_screenshot, find_image_on_device
        from monst.adb import perform_action
        from monst.adb.input import send_text_robust

        logger.debug(f"サブ端末{device_num}: アカウント名「{account_name}」を入力中...")

        # account_name.pngをクリック
        x, y = find_image_on_device(port, "account_name.png", "ui", threshold=0.8)
        if x is not None and y is not None:
            perform_action(port, 'tap', x, y)
            time.sleep(1)

            # アカウント名を入力
            send_text_robust(port, account_name)
            time.sleep(1)

            logger.debug(f"サブ端末{device_num}: アカウント名入力完了")
            return True
        else:
            logger.error(f"サブ端末{device_num}: アカウント名入力フィールドが見つかりません")
            return False

    except Exception as e:
        logger.error(f"サブ端末{device_num}: アカウント名入力エラー: {e}")
        return False


def _execute_sub_terminal_friend_approval(self, port: str, device_num: int) -> bool:
    """サブ端末でのフレンド承認処理（⑲）"""
    try:
        from monst.image import find_image_on_device
        from monst.adb import perform_action

        logger.debug(f"サブ端末{device_num}: フレンド承認処理を開始...")
        base_sleep = 1.0

        # 必要な画像の順序: modoru.png→friends_syotai.png→friends_ok→friends_syotai2.png→friends_kigen.png→friends_syonin.png
        button_sequence = [
            ("modoru.png", "戻るボタン"),
            ("friends_syotai.png", "フレンド招待ボタン"),
            ("friends_ok.png", "フレンドOKボタン"),
            ("friends_syotai2.png", "フレンド招待2ボタン"),
            ("friends_kigen.png", "フレンド期限ボタン"),
            ("friends_syonin.png", "フレンド承認ボタン")
        ]

        # 各ボタンを順番に押していく
        for button_name, button_desc in button_sequence:
            attempt = 0
            while True:  # 各ボタンが見つかるまで無限ループ
                x, y = find_image_on_device(port, button_name, "ui", threshold=0.8)
                if x is not None and y is not None:
                    logger.debug(f"サブ端末{device_num}: ? {button_desc}クリック (座標: {x}, {y})")
                    perform_action(port, 'tap', x, y)
                    time.sleep(base_sleep * 2)
                    break

                attempt += 1
                if attempt % 10 == 0:
                    logger.debug(f"サブ端末{device_num}: {button_desc}検索中... (試行{attempt})")
                time.sleep(base_sleep * 0.5)

        # friends_seiritu.pngが表示されるまで待機
        logger.debug(f"サブ端末{device_num}: フレンド成立確認待機中...")
        seiritu_attempt = 0
        while True:  # friends_seiritu.pngが見つかるまで無限ループ
            seiritu_x, seiritu_y = find_image_on_device(port, "friends_seiritu.png", "ui", threshold=0.8)
            if seiritu_x is not None and seiritu_y is not None:
                logger.debug(f"サブ端末{device_num}: ? フレンド成立確認！ (座標: {seiritu_x}, {seiritu_y})")
                break

            seiritu_attempt += 1
            if seiritu_attempt % 15 == 0:
                logger.debug(f"サブ端末{device_num}: フレンド成立確認中... (試行{seiritu_attempt})")
            time.sleep(base_sleep * 1.5)

        logger.debug(f"サブ端末{device_num}: ? フレンド承認処理完了")
        return True

    except Exception as e:
        logger.error(f"サブ端末{device_num}: フレンド承認処理エラー: {e}")
        return False


def _execute_main_terminal_final_confirmation(self, main_port: str) -> bool:
    """メイン端末での最終確認処理（⑳）"""
    try:
        from monst.image import find_image_on_device
        from monst.adb import perform_action

        logger.info("メイン端末: 最終確認処理を開始...")
        base_sleep = 1.0

        # modoru.png → friends_syotai.png と押していく
        button_sequence = [
            ("modoru.png", "戻るボタン"),
            ("friends_syotai.png", "フレンド招待ボタン")
        ]

        # 各ボタンを順番に押していく
        for button_name, button_desc in button_sequence:
            attempt = 0
            while True:  # 各ボタンが見つかるまで無限ループ
                x, y = find_image_on_device(main_port, button_name, "ui", threshold=0.8)
                if x is not None and y is not None:
                    logger.debug(f"メイン端末: ? {button_desc}クリック (座標: {x}, {y})")
                    perform_action(main_port, 'tap', x, y)
                    time.sleep(base_sleep * 2)
                    break

                attempt += 1
                if attempt % 10 == 0:
                    logger.debug(f"メイン端末: {button_desc}検索中... (試行{attempt})")
                time.sleep(base_sleep * 0.5)

        # friends_seirituが表示されるまで待機
        logger.info("メイン端末: フレンド成立確認待機中...")
        seiritu_attempt = 0
        while True:  # friends_seiritu.pngが見つかるまで無限ループ
            seiritu_x, seiritu_y = find_image_on_device(main_port, "friends_seiritu.png", "ui", threshold=0.8)
            if seiritu_x is not None and seiritu_y is not None:
                logger.debug(f"メイン端末: ? フレンド成立確認！ (座標: {seiritu_x}, {seiritu_y})")
                break

            seiritu_attempt += 1
            if seiritu_attempt % 15 == 0:
                logger.debug(f"メイン端末: フレンド成立確認中... (試行{seiritu_attempt})")
            time.sleep(base_sleep * 1.5)

        # friends_seiritu表示後、friends_okを押す
        logger.info("メイン端末: friends_seiritu表示後のfriends_ok検索中...")
        final_ok_attempt = 0
        while True:  # friends_okが見つかるまで無限ループ
            final_ok_x, final_ok_y = find_image_on_device(main_port, "friends_ok.png", "ui", threshold=0.8)
            if final_ok_x is not None and final_ok_y is not None:
                log_folder_result(current_folder, "フレンド登録", "成功")
                perform_action(main_port, 'tap', final_ok_x, final_ok_y)
                time.sleep(base_sleep * 2)
                break

            final_ok_attempt += 1
            if final_ok_attempt % 10 == 0:
                logger.debug(f"メイン端末: 最終friends_ok検索中... (試行{final_ok_attempt})")
            time.sleep(base_sleep * 0.5)

        logger.info("メイン端末: ? 最終確認処理完了")
        return True

    except Exception as e:
        logger.error(f"メイン端末: 最終確認処理エラー: {e}")
        return False


def _confirm_account_creation(self, port: str, device_num: int) -> bool:
    """OKを押してdownloadを押す"""
    try:
        from monst.image import get_device_screenshot, find_image_on_device
        from monst.adb.input import tap_on_screen

        logger.debug(f"サブ端末{device_num}: アカウント作成を確定中...")

        # OKボタンを押す
        x, y = find_image_on_device(port, "ok.png", "ui", threshold=0.8)
        if x is not None and y is not None:
            perform_action(port, 'tap', x, y)
            time.sleep(2)
            logger.debug(f"サブ端末{device_num}: OKボタンをクリック")
        else:
            logger.warning(f"サブ端末{device_num}: OKボタンが見つかりません")

        # downloadボタンを待機してクリック
        for attempt in range(10):
            x, y = find_image_on_device(port, "download.png", "login", threshold=0.8)
            if x is not None and y is not None:
                perform_action(port, 'tap', x, y)
                logger.debug(f"サブ端末{device_num}: downloadボタンをクリック")
                time.sleep(3)
                return True

            time.sleep(1)

        logger.error(f"サブ端末{device_num}: downloadボタンが見つかりませんでした")
        return False

    except Exception as e:
        logger.error(f"サブ端末{device_num}: アカウント作成確定エラー: {e}")
        return False


def _complete_initial_quest(self, port: str, device_num: int, max_attempts: int = 60) -> bool:
    """初期クエストを完了"""
    try:
        from monst.image import get_device_screenshot, find_image_on_device
        from monst.adb.input import tap_on_screen, swipe_on_screen

        logger.debug(f"サブ端末{device_num}: 初期クエスト開始...")

        for attempt in range(max_attempts):
            # que_end.pngをチェック（クエスト完了の確認）
            x, y = find_image_on_device(port, "que_end.png", "quest", threshold=0.8)
            if x is not None and y is not None:
                logger.debug(f"サブ端末{device_num}: 初期クエスト完了を検出")
                return True

            # クエスト進行のための基本操作
            # 画面中央をタップ
            tap_on_screen(port, 400, 600)
            time.sleep(1)

            # 右スワイプ（次へ進む）
            swipe_on_screen(port, 300, 600, 500, 600)
            time.sleep(1)

            # OKボタンがあればクリック
            ok_x, ok_y = find_image_on_device(port, "ok.png", "ui", threshold=0.8)
            if ok_x is not None and ok_y is not None:
                tap_on_screen(port, ok_x, ok_y)
                time.sleep(1)

            if attempt % 10 == 0:
                logger.debug(f"サブ端末{device_num}: 初期クエスト実行中... (試行{attempt+1}/{max_attempts})")

        logger.error(f"サブ端末{device_num}: 初期クエスト完了に失敗")
        return False

    except Exception as e:
        logger.error(f"サブ端末{device_num}: 初期クエスト実行エラー: {e}")
        return False
