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

def _load_main_device_data(self, main_port: str, folder_num) -> bool:
    """メイン端末にフォルダデータを読み込み"""
    try:
        # フォルダー番号を整数に変換
        folder_num = int(str(folder_num))
        # logger.debug(f"メイン端末 {main_port} にフォルダ {folder_num:03d} のデータを読み込み中...")

        from monst.adb.core import reset_adb_server
        from monst.adb.files import push_file_to_nox
        from monst.adb.app import restart_monster_strike_app

        # ADBサーバーをリセット
        reset_adb_server()

        # データファイルを端末にプッシュ
        folder_name = f"{folder_num:03d}"
        success = push_file_to_nox(main_port, folder_name)

        if success:
            # logger.debug(f"メイン端末のデータ読み込み完了: フォルダ {folder_num:03d}")

            # データ読み込み後にアプリを再起動
            logger.debug(f"メイン端末 {main_port} のアプリを再起動中...")
            restart_monster_strike_app(main_port)
            # logger.debug(f"メイン端末のアプリ再起動完了")

            # メイン端末のログイン処理を実行してホーム画面まで進行
            if self._perform_main_device_login(main_port, folder_num):
                # logger.debug(f"メイン端末のログイン処理完了")
                return True
            else:
                logger.error(f"メイン端末のログイン処理失敗")
                return False
        else:
            logger.error(f"メイン端末のデータ読み込み失敗: フォルダ {folder_num:03d}")
            return False

    except Exception as e:
        logger.error(f"メイン端末データ読み込みエラー: {e}")
        return False


def _perform_main_device_login(self, main_port: str, folder_num) -> bool:
    """メイン端末のログイン処理実行"""
    try:
        # フォルダー番号を整数に変換
        folder_num = int(str(folder_num))
        logger.debug(f"メイン端末 {main_port} のログイン処理を開始...")

        # フォルダ名を3桁形式に変換
        folder_name = f"{folder_num:03d}"

        # フレンド登録専用のログイン処理（room再確認機能付き）
        from monst.device.friends import _login_with_room_verification
        success = _login_with_room_verification(main_port, folder_name)

        if success:
            logger.debug(f"メイン端末のログイン完了: フォルダ {folder_name}")
            return True
        else:
            logger.error(f"メイン端末のログイン失敗: フォルダ {folder_name}")
            return False

    except Exception as e:
        logger.error(f"メイン端末ログインエラー: {e}")
        return False
