"""
missing_functions.py - Temporary stubs for missing functions

リファクタリング中に削除された関数の一時的なスタブです。
"""

from __future__ import annotations

import time
from typing import Any, Optional

from logging_util import logger, MultiDeviceLogger

# 覇者関連の関数は monst.device.hasya から import
from monst.device.hasya import (
    device_operation_hasya,
    device_operation_hasya_wait, 
    device_operation_hasya_fin,
    device_operation_hasya_host_fin,
    continue_hasya,
    load_macro
)

def device_operation_excel_and_save(
    device_port: str, 
    workbook: Any, 
    start_row: int, 
    end_row: int, 
    completion_event: Any, 
    multi_logger: Optional[MultiDeviceLogger] = None
) -> bool:
    """mon6準拠のExcel引継ぎ保存フロー。"""
    from adb_utils import (
        close_monster_strike_app,
        start_monster_strike_app,
        pull_file_from_nox,
        remove_data10_bin_from_nox,
    )
    from login_operations import handle_screens
    from monst.adb import perform_action, send_key_event
    from monst.image import tap_if_found, tap_until_found
    from monst.device.operations import mon_initial

    MAX_ROW_DURATION = 15 * 60  # 15 minutes per row
    row_start_time: float = 0.0

    def _reset_row_timer() -> None:
        nonlocal row_start_time
        row_start_time = time.time()

    def _check_timeout() -> None:
        if row_start_time and (time.time() - row_start_time) > MAX_ROW_DURATION:
            raise RuntimeError("タイムアップのため失敗")

    def _ensure_home_visible() -> bool:
        for _ in range(8):
            _check_timeout()
            if tap_if_found('stay', device_port, "zz_home.png", "key") or tap_if_found('stay', device_port, "zz_home2.png", "key"):
                return True
            handle_screens(device_port, "login")
            tap_if_found('tap', device_port, "zz_home.png", "key")
            if tap_if_found('tap', device_port, "gacha_shu.png", "new"):
                tap_until_found(device_port, "zz_home.png", "key", "zz_home2.png", "key", "tap")
            tap_if_found('tap', device_port, "zz_home2.png", "key")
            perform_action(device_port, 'tap', 50, 170, duration=150)
            time.sleep(0.5)
        return tap_if_found('stay', device_port, "zz_home.png", "key") or tap_if_found('stay', device_port, "zz_home2.png", "key")

    def _focus_field(field_image: str, max_attempts: int = 12) -> bool:
        for _ in range(max_attempts):
            if tap_if_found('tap', device_port, field_image, "new", cache_time=0.0):
                time.sleep(0.3)
                return True
            time.sleep(0.2)
        logger.error("Excel引継ぎ: %s をフォーカスできませんでした。", field_image)
        return False

    def _input_text(field_image: str, value: str, *, ensure_focus: bool = True) -> None:
        """必要であればフォーカスを確保し、不要なら即座に入力する。"""
        if not ensure_focus:
            time.sleep(0.3)
            send_key_event(device_port, text=value, press_enter=False)
            return

        retries = 0
        while retries < 3:
            if _focus_field(field_image) and _focus_field(field_image):
                time.sleep(0.3)
                send_key_event(device_port, text=value, press_enter=False)
                return
            retries += 1
        raise RuntimeError(f"{field_image} への入力に失敗しました")

    def _tap_login_button() -> bool:
        if tap_if_found('tap', device_port, "login.png", "new"):
            time.sleep(0.3)
            return True
        return tap_until_found(device_port, "kyoka.png", "new", "login.png", "new", "tap")

    sheet = workbook.active
    success = False
    try:
        for current_row in range(start_row, end_row + 1):
            _reset_row_timer()
            cells = [cell.value for cell in sheet[current_row]]
            if not cells or len(cells) < 4:
                logger.warning("Excel引継ぎ: 行 %s のデータが不足しています。", current_row)
                continue

            xflag_id = str(cells[0]).strip() if cells[0] is not None else ""
            password = str(cells[1]).strip() if cells[1] is not None else ""
            account_id = str(cells[2]).strip() if cells[2] is not None else ""
            user_name = str(cells[3]).strip() if cells[3] is not None else f"{current_row:03d}"

            if not xflag_id or not password or not account_id:
                logger.error("Excel引継ぎ: 行 %s の必須項目が空です。", current_row)
                continue

            folder_label = user_name or account_id or f"{current_row:03d}"
            logger.info(
                "Excel引継ぎ開始 row=%s port=%s account=%s",
                current_row,
                device_port,
                account_id,
            )

            close_monster_strike_app(device_port)
            remove_data10_bin_from_nox(device_port)
            start_monster_strike_app(device_port)

            tap_retry = 0
            while not tap_if_found('tap', device_port, "hikitsugi.png", "new"):
                _check_timeout()
                tap_if_found('tap', device_port, "doui.png", "new")
                perform_action(device_port, 'tap', 50, 170, duration=150)
                time.sleep(0.5)
                tap_retry += 1
                if tap_retry > 80:
                    raise RuntimeError("hikitsugi.png の表示に失敗しました")

            tap_until_found(device_port, "yes.png", "new", "hikitsugi.png", "new", "tap")
            tap_until_found(device_port, "XFLAGID.png", "new", "yes.png", "new", "tap")
            tap_until_found(device_port, "kochira.png", "new", "XFLAGID.png", "new", "tap")
            tap_until_found(device_port, "XFLAGID.png", "new", "kochira.png", "new", "tap")

            attempts = 0
            while not tap_if_found('stay', device_port, "mail.png", "new"):
                _check_timeout()
                tap_if_found('tap', device_port, "XFLAGID.png", "new")
                tap_if_found('tap', device_port, "mail2.png", "new")
                time.sleep(0.5)
                attempts += 1
                if attempts > 30:
                    raise RuntimeError("mail.png の表示に失敗しました")

            _input_text("mail.png", xflag_id)
            _input_text("pass.png", password)
            if not _tap_login_button():
                raise RuntimeError("login.png をタップできませんでした")
            tap_until_found(device_port, "ID.png", "new", "kyoka.png", "new", "tap","stay")
            tap_if_found('tap', device_port, "ID.png", "new")
            _input_text("ID.png", account_id, ensure_focus=False)

            while True:
                _check_timeout()
                if tap_if_found('tap', device_port, "ok.png", "new"):
                    time.sleep(1.0)

                if tap_if_found('stay', device_port, "fri_x.png", "new"):
                    raise RuntimeError("IDの誤りを検出したため中断しました")

                if tap_if_found('stay', device_port, "yes2.png", "new"):
                    tap_if_found('tap', device_port, "yes2.png", "new")
                    time.sleep(1.5)
                    if tap_if_found('stay', device_port, "mukou.png", "new"):
                        raise RuntimeError("無効のデータのため中断しました")
                    break



            tap_until_found(device_port, "ok2.png", "new", "yes2.png", "new", "tap")
            tap_until_found(device_port, "download.png", "new", "ok2.png", "new", "tap")
            tap_if_found('tap', device_port, "download.png", "new")
            tap_if_found('tap', device_port, "download.png", "new")

            for _ in range(6):
                _check_timeout()
                if not _ensure_home_visible():
                    raise RuntimeError("ホーム画面への遷移に失敗しました")
                time.sleep(0.5)

            ##mon_initial(device_port, folder_label)一時除外
            pull_file_from_nox(device_port, folder_label)
            logger.info("Excel引継ぎ成功 port=%s folder=%s", device_port, folder_label)

        success = True
        if multi_logger:
            multi_logger.log_success(device_port)
        return True

    except Exception as exc:
        logger.error("Excel引継ぎ中にエラー: %s (port=%s)", exc, device_port)
        if multi_logger:
            multi_logger.log_error(device_port, str(exc))
        return False

    finally:
        if completion_event and not completion_event.is_set():
            completion_event.set()
        if not success and multi_logger:
            multi_logger.log_error(device_port, "Excel引継ぎ失敗")

def device_init_only(device_port: str) -> bool:
    """サブ端末専用：アカウント初期化+アプリ起動のみ（ログイン処理なし）"""
    from adb_utils import close_monster_strike_app, start_monster_strike_app, remove_data10_bin_from_nox
    import time
    
    try:
        logger.info(f"シングル初期化開始: {device_port}")
        
        # アプリを閉じる
        close_monster_strike_app(device_port)
        time.sleep(1)
        
        # data10.binを削除（アカウント初期化）
        remove_data10_bin_from_nox(device_port)
        time.sleep(1)
        
        # アプリを起動
        start_monster_strike_app(device_port)
        time.sleep(3)  # アプリ起動待機
        
        logger.info(f"シングル初期化完了: {device_port}")
        return True
        
    except Exception as e:
        logger.error(f"シングル初期化エラー ({device_port}): {e}")
        return False

def device_operation_nobin(
    device_port: str, 
    folder: str, 
    multi_logger: Optional[MultiDeviceLogger] = None
) -> bool:
    """No bin操作の実装（mon6準拠）- フルバージョン。"""
    from adb_utils import close_monster_strike_app, start_monster_strike_app, remove_data10_bin_from_nox
    from login_operations import device_operation_login
    from image_detection import tap_if_found
    
    try:
        # アプリを閉じる
        close_monster_strike_app(device_port)
        
        # data10.binを削除
        remove_data10_bin_from_nox(device_port)
        
        # アプリを起動
        start_monster_strike_app(device_port)
        
        # ログイン処理
        if not device_operation_login(device_port, folder, multi_logger):
            error_msg = f"ログイン失敗 (フォルダ：{folder})"
            logger.error(error_msg)
            if multi_logger:
                multi_logger.log_error(device_port, error_msg)
            return False
        
        # ガチャボタン誤作動防止
        if tap_if_found('tap', device_port, "gacha_shu.png", "login"):
            logger.warning(f"no bin処理中にガチャボタンを検出しました。ホーム画面に戻ります。")
            tap_if_found('tap', device_port, "zz_home.png", "login")
            tap_if_found('tap', device_port, "zz_home2.png", "login")
            time.sleep(1)
        
        if multi_logger:
            multi_logger.log_success(device_port)
        
        logger.info(f"no bin処理完了: {device_port}, フォルダ {folder}")
        return True
        
    except Exception as e:
        error_msg = f"no bin処理中にエラーが発生しました: {str(e)}"
        logger.error(error_msg)
        if multi_logger:
            multi_logger.log_error(device_port, error_msg)
        return False

# device_operation_quest は monst.device.quest で実装済み

# continue_hasya と load_macro は上記でインポート済み
