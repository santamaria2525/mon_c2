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

def _process_sub_devices(self, sub_ports: list[str]) -> bool:
    """サブ端末の初期化とアカウント作成を一括処理"""
    try:
        # logger.debug(f"サブ端末 {len(sub_ports)}台の一括処理を開始...")

        # ③サブ端末をすべて初期化
        if not self._initialize_sub_devices(sub_ports):
            logger.error("サブ端末の初期化に失敗")
            return False

        # ④～⑧各サブ端末でアカウント作成と初期クエスト
        if not self._setup_sub_accounts(sub_ports):
            logger.error("サブ端末のシングル初期化に失敗")
            return False

        logger.info("サブ端末の一括処理完了")
        return True

    except Exception as e:
        logger.error(f"サブ端末一括処理エラー: {e}")
        return False


def _initialize_sub_devices(self, sub_ports: list[str]) -> bool:
    """サブ端末をすべて初期化"""
    try:
        # logger.debug(f"サブ端末 {len(sub_ports)}台の初期化を開始...")

        from monst.adb.files import remove_data10_bin_from_nox

        success_count = 0
        for i, port in enumerate(sub_ports, 1):
            try:
                # logger.debug(f"サブ端末{i} ({port}) を初期化中...")
                remove_data10_bin_from_nox(port)
                success_count += 1
                # logger.debug(f"サブ端末{i} の初期化完了")
            except Exception as port_error:
                logger.error(f"サブ端末{i} ({port}) の初期化失敗: {port_error}")

        if success_count == len(sub_ports):
            # logger.info("すべてのサブ端末の初期化が完了しました")
            return True
        else:
            logger.warning(f"一部のサブ端末初期化に失敗: {success_count}/{len(sub_ports)}")
            return False

    except Exception as e:
        logger.error(f"サブ端末初期化エラー: {e}")
        return False


def _setup_sub_accounts(self, sub_ports: list[str]) -> bool:
    """各サブ端末でシングル初期化を並行実行"""
    try:
        logger.debug(f"サブ端末 {len(sub_ports)}台のシングル初期化を並行実行で開始...")

        with ThreadPoolExecutor(max_workers=len(sub_ports)) as executor:
            # 各サブ端末の処理を並行実行するためのFutureオブジェクトを作成
            futures = []
            for i, port in enumerate(sub_ports, 1):
                # SB + 3桁ランダム数字形式でアカウント名生成
                import random
                random_num = random.randint(100, 999)
                account_name = f"SB{random_num}"
                future = executor.submit(self._setup_single_sub_account, port, account_name, i)
                futures.append((future, i, port))

            # 全ての処理の完了を待機
            success_count = 0
            for future, device_num, port in futures:
                try:
                    result = future.result(timeout=300)  # 5分タイムアウト
                    if result:
                        success_count += 1
                        logger.debug(f"サブ端末{device_num} のシングル初期化完了")
                    else:
                        logger.error(f"サブ端末{device_num} のシングル初期化失敗")
                except Exception as e:
                    logger.error(f"サブ端末{device_num} ({port}) 並行処理エラー: {e}")

        if success_count == len(sub_ports):
            logger.info("すべてのサブ端末のシングル初期化が完了しました")

            # 全サブ端末完了後、サブ端末とメイン端末でフレンド処理を順次実行
            if not self._execute_sequential_friend_processing(sub_ports):
                logger.warning("フレンド処理に失敗しましたが、サブ端末初期化は完了")

            return True
        else:
            logger.warning(f"一部のサブ端末シングル初期化に失敗: {success_count}/{len(sub_ports)}")
            return success_count > 0  # 1台でも成功していれば継続

    except Exception as e:
        logger.error(f"サブ端末シングル初期化エラー: {e}")
        return False


def _setup_single_sub_account(self, port: str, account_name: str, device_num: int) -> bool:
    """単一サブ端末の完全処理（ULTRATHINK版）"""
    try:
        logger.debug(f"サブ端末{device_num} ({port}) の処理を開始...")

        from missing_functions import device_operation_nobin

        # ステップ1: シングル初期化処理を実行（アカウント初期化+アプリ起動のみ）
        # logger.debug(f"サブ端末{device_num}: ステップ1 - シングル初期化実行")
        from missing_functions import device_init_only
        success = device_init_only(port)

        if not success:
            logger.error(f"サブ端末{device_num} のシングル初期化失敗")
            return False

        logger.debug(f"サブ端末{device_num}: シングル初期化完了")

        # ステップ2: account_name.png専用待機（単純なループ）
        # logger.debug(f"サブ端末{device_num}: ステップ2 - account_name専用待機開始")
        try:
            if not self._wait_for_account_name_simple(port, device_num):
                logger.warning(f"サブ端末{device_num}: account_name待機でタイムアウト（処理は続行）")
                # account_name待機に失敗してもアカウント作成処理は試行する
        except Exception as e:
            logger.warning(f"サブ端末{device_num}: account_name待機でエラー発生（処理は続行）: {e}")
            # エラーが発生してもアカウント作成処理は試行する

        # ステップ3: account_name発見後のアカウント作成処理
        logger.debug(f"サブ端末{device_num}: ステップ3 - アカウント作成処理開始")
        try:
            if not self._execute_account_creation_steps(port, account_name, device_num):
                logger.warning(f"サブ端末{device_num}: アカウント作成処理に一部問題があったが、基本初期化は完了")
        except Exception as e:
            logger.warning(f"サブ端末{device_num}: アカウント作成処理エラー（基本初期化は完了）: {e}")

        logger.debug(f"サブ端末{device_num} の処理完了（初期化成功）")
        return True  # 基本的に成功とみなす（アプリ起動まで完了しているため）

    except Exception as e:
        logger.error(f"端末 {port} 処理エラー: {e}")
        return False
