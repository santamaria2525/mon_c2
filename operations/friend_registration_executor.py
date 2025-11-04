# -*- coding: utf-8 -*-
"""Friend registration executor fully migrated from legacy flow."""

from __future__ import annotations

import concurrent.futures
import time
from typing import Optional, Tuple

from logging_util import logger
from app.operations.helpers import find_and_click_with_protection, log_folder_result
from app_crash_recovery import check_app_crash
from loop_protection import loop_protection  # type: ignore
from monst.adb import perform_action
from monst.image import find_image_on_device

from domain import LoginWorkflow
from .friend_flow import verify_friend_status
from services import ConfigService, MultiDeviceService
from services.folder import FolderProgressionService
from services.ports import PortAllocationService


class FriendRegistrationExecutor:
    """Clean implementation of the multi-device friend registration flow."""

    def __init__(
        self,
        core,
        config_service: ConfigService,
        multi_device_service: MultiDeviceService,
        login_workflow: LoginWorkflow,
    ) -> None:
        self.core = core
        self.config_service = config_service
        self.multi_device_service = multi_device_service
        self.login_workflow = login_workflow

        self._folder_service = FolderProgressionService(config_service)
        self._port_service = PortAllocationService(config_service)

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    def run(self) -> None:
        start_folder = self.core.get_start_folder()
        if start_folder is None:
            logger.info("フレンド登録: フォルダが選択されませんでした。")
            return

        if not self._folder_service.validate(start_folder):
            logger.warning("フレンド登録: 無効なフォルダ %s が指定されました。", start_folder)

        main_port, sub_ports = self._port_service.get_main_and_sub_ports()
        all_ports = [main_port, *sub_ports]
        logger.debug("フレンド登録: main=%s sub=%s", main_port, sub_ports)

        try:
            self.multi_device_service.run_push(start_folder, all_ports)
        except Exception as exc:
            logger.error("フレンド登録: BIN書き込みに失敗しました (%s)", exc)

        folder_str = f"{int(start_folder):03d}"
        for port in all_ports:
            try:
                success = self.login_workflow.execute(port, folder_str)
                if not success:
                    logger.warning("フレンド登録: ログイン処理に失敗 port=%s folder=%s", port, folder_str)
            except Exception as exc:
                logger.error("フレンド登録: ログイン処理で例外発生 port=%s (%s)", port, exc)

        for index, port in enumerate(all_ports, start=1):
            verify_friend_status(port, folder_str)

        summary = self._folder_service.summary()
        if summary:
            logger.debug("フレンド登録: フォルダ要約=%s", summary)

        success = self._run_friend_flows(main_port, sub_ports, folder_str)
        if success:
            logger.info("フレンド登録: 新実装で完了しました。")
        else:
            logger.error("フレンド登録: 新実装フローが途中で失敗しました。ログを確認してください。")

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #
    def _run_friend_flows(
        self,
        main_port: str,
        sub_ports: list[str],
        folder: str,
    ) -> bool:
        sleep_time = 0.6

        if sub_ports:
            for device_num, port in enumerate(sub_ports, start=1):
                if not self._execute_friend_registration(port, device_num, sleep_time):
                    return False
        else:
            logger.warning("フレンド登録: サブ端末が設定されていません。")

        if not self._execute_main_terminal_friend_processing(main_port, folder, sub_ports, sleep_time):
            return False

        if not self._execute_sub_terminal_friend_approvals(sub_ports, sleep_time):
            return False

        if not self._execute_main_terminal_final_confirmation(main_port, folder, sleep_time):
            return False

        return True

    def _execute_friend_registration(self, port: str, device_num: int, sleep_time: float) -> bool:
        """Sub device flow: friends → ok → search → copy."""
        try:
            if not find_and_click_with_protection(
                port,
                "friends.png",
                "ui",
                f"サブ端末{device_num}",
                max_attempts=100,
                sleep_time=sleep_time * 0.5,
            ):
                return False

            if not self._wait_for_image(
                port,
                "friends_ok.png",
                device_num,
                max_attempts=100,
                tap_recovery="friends.png",
                sleep_time=sleep_time,
                loop_key=f"friend_ok_{port}",
            ):
                return False

            if not self._wait_for_image(
                port,
                "friends_search.png",
                device_num,
                max_attempts=100,
                tap_recovery="friends.png",
                sleep_time=sleep_time,
                loop_key=f"friend_search_{port}",
            ):
                return False

            if not self._wait_for_image(
                port,
                "friends_copy.png",
                device_num,
                max_attempts=100,
                tap_recovery="friends.png",
                sleep_time=sleep_time,
                loop_key=f"friend_copy_{port}",
            ):
                return False

            logger.debug("サブ端末%s: friends_copy まで完了しました。", device_num)
            return True
        except Exception as exc:
            logger.error("サブ端末%s: フレンド登録中に例外発生 (%s)", device_num, exc)
            return False

    def _execute_main_terminal_friend_processing(
        self,
        main_port: str,
        folder: str,
        sub_ports: list[str],
        sleep_time: float,
    ) -> bool:
        """Handle host-side friend invitation for each sub device."""
        base_sleep = max(sleep_time, 1.0)

        if not sub_ports:
            logger.warning("メイン端末: サブ端末がないためフレンド処理をスキップします。")
            return False

        try:
            for device_index, sub_port in enumerate(sub_ports, start=1):
                if not self._open_friend_menu(main_port, device_index, base_sleep):
                    return False

                id_coordinates = self._locate_friend_id_field(main_port, device_index, base_sleep)
                if id_coordinates is None:
                    return False

                x, y = id_coordinates
                perform_action(main_port, "tap", x, y)
                time.sleep(base_sleep * 0.8)

                pasted = self._paste_friend_id_from_clipboard(main_port, device_index)
                if not pasted:
                    logger.warning(
                        "メイン端末: サブ端末%s(port=%s)向けID貼り付けでフォールバックを使用しました。",
                        device_index,
                        sub_port,
                    )

                if not self._wait_for_friend_end_state(main_port, device_index, base_sleep):
                    return False

                if not self._confirm_final_friend_ok(main_port, device_index, base_sleep):
                    return False

                logger.debug(
                    "メイン端末: サブ端末%s(port=%s)向けフレンド処理を完了しました。",
                    device_index,
                    sub_port,
                )
                time.sleep(base_sleep * 0.6)

            logger.info("メイン端末: フォルダ%sのサブ端末フレンド処理を完了しました。", folder)
            return True
        except Exception as exc:
            logger.error("メイン端末: フレンド処理中に例外が発生しました (%s)", exc)
            return False

    def _execute_sub_terminal_friend_approvals(
        self,
        sub_ports: list[str],
        sleep_time: float,
    ) -> bool:
        if not sub_ports:
            return True

        logger.info("サブ端末: フレンド承認処理を開始します。")
        all_success = True

        with concurrent.futures.ThreadPoolExecutor(max_workers=len(sub_ports)) as executor:
            future_map = {
                executor.submit(self._execute_sub_terminal_friend_approval, port, idx, sleep_time): (port, idx)
                for idx, port in enumerate(sub_ports, start=1)
            }

            for future in concurrent.futures.as_completed(future_map):
                port, device_num = future_map[future]
                try:
                    result = future.result()
                except Exception as exc:  # pragma: no cover - defensive
                    logger.error("サブ端末%s(port=%s): フレンド承認処理で例外発生 (%s)", device_num, port, exc)
                    all_success = False
                else:
                    if result:
                        logger.debug("サブ端末%s: フレンド承認処理を完了しました。", device_num)
                    else:
                        logger.warning("サブ端末%s: フレンド承認処理に失敗しました。", device_num)
                        all_success = False

        if all_success:
            logger.info("サブ端末: フレンド承認処理が完了しました。")
        return all_success

    def _execute_sub_terminal_friend_approval(
        self,
        port: str,
        device_num: int,
        sleep_time: float,
    ) -> bool:
        """Sub device flow: accept friend invitation."""
        base_sleep = max(sleep_time, 1.0)
        buttons = [
            ("modoru.png", "戻るボタン"),
            ("friends_syotai.png", "フレンド招待ボタン"),
            ("friends_ok.png", "フレンドOKボタン"),
            ("friends_syotai2.png", "フレンド招待2ボタン"),
            ("friends_kigen.png", "フレンド期限ボタン"),
            ("friends_syonin.png", "フレンド承認ボタン"),
        ]

        try:
            for image_name, description in buttons:
                attempt = 0
                while True:
                    x, y = find_image_on_device(port, image_name, "ui", threshold=0.8)
                    if x is not None and y is not None:
                        logger.debug(
                            "サブ端末%s: %sをクリックしました (座標: %s, %s)",
                            device_num,
                            description,
                            x,
                            y,
                        )
                        perform_action(port, "tap", x, y)
                        time.sleep(base_sleep * 2)
                        break

                    attempt += 1
                    if attempt % 10 == 0:
                        logger.debug(
                            "サブ端末%s: %sを探索中... (試行%d)",
                            device_num,
                            description,
                            attempt,
                        )
                    time.sleep(base_sleep * 0.5)

            attempt = 0
            while True:
                seiritu_x, seiritu_y = find_image_on_device(port, "friends_seiritu.png", "ui", threshold=0.8)
                if seiritu_x is not None and seiritu_y is not None:
                    logger.debug(
                        "サブ端末%s: friends_seirituを検出しました (座標: %s, %s)",
                        device_num,
                        seiritu_x,
                        seiritu_y,
                    )
                    break

                attempt += 1
                if attempt % 15 == 0:
                    logger.debug("サブ端末%s: friends_seirituを探索中... (試行%d)", device_num, attempt)
                time.sleep(base_sleep * 1.5)

            return True
        except Exception as exc:
            logger.error("サブ端末%s: フレンド承認処理で例外発生 (%s)", device_num, exc)
            return False

    def _execute_main_terminal_final_confirmation(
        self,
        main_port: str,
        folder: str,
        sleep_time: float,
    ) -> bool:
        base_sleep = max(sleep_time, 1.0)
        buttons = [
            ("modoru.png", "戻るボタン"),
            ("friends_syotai.png", "フレンド招待ボタン"),
        ]

        try:
            for image_name, description in buttons:
                attempt = 0
                while True:
                    x, y = find_image_on_device(main_port, image_name, "ui", threshold=0.8)
                    if x is not None and y is not None:
                        logger.debug(
                            "メイン端末: %sをクリックしました (座標: %s, %s)",
                            description,
                            x,
                            y,
                        )
                        perform_action(main_port, "tap", x, y)
                        time.sleep(base_sleep * 2)
                        break

                    attempt += 1
                    if attempt % 10 == 0:
                        logger.debug(
                            "メイン端末: %sを探索中... (試行%d)",
                            description,
                            attempt,
                        )
                    time.sleep(base_sleep * 0.5)

            attempt = 0
            while True:
                seiritu_x, seiritu_y = find_image_on_device(main_port, "friends_seiritu.png", "ui", threshold=0.8)
                if seiritu_x is not None and seiritu_y is not None:
                    logger.debug(
                        "メイン端末: friends_seirituを検出しました (座標: %s, %s)",
                        seiritu_x,
                        seiritu_y,
                    )
                    break

                attempt += 1
                if attempt % 15 == 0:
                    logger.debug("メイン端末: friends_seirituを探索中... (試行%d)", attempt)
                time.sleep(base_sleep * 1.5)

            attempt = 0
            while True:
                ok_x, ok_y = find_image_on_device(main_port, "friends_ok.png", "ui", threshold=0.8)
                if ok_x is not None and ok_y is not None:
                    perform_action(main_port, "tap", ok_x, ok_y)
                    log_folder_result(folder, "フレンド登録", "成功")
                    logger.info("メイン端末: フレンド登録最終確認が完了しました。")
                    time.sleep(base_sleep * 2)
                    return True

                attempt += 1
                if attempt % 10 == 0:
                    logger.debug("メイン端末: 最終friends_okを探索中... (試行%d)", attempt)
                time.sleep(base_sleep * 0.5)
        except Exception as exc:
            logger.error("メイン端末: 最終確認処理で例外発生 (%s)", exc)
            return False

    # ------------------------------------------------------------------ #
    # Low-level helpers
    # ------------------------------------------------------------------ #
    def _wait_for_image(
        self,
        port: str,
        image_name: str,
        device_num: int,
        *,
        max_attempts: int,
        tap_recovery: str,
        sleep_time: float,
        loop_key: str,
    ) -> bool:
        for attempt in range(1, max_attempts + 1):
            if check_app_crash(port):
                logger.warning("サブ端末%s: アプリクラッシュを検知 (%s)", device_num, image_name)
                return False

            x, y = find_image_on_device(port, image_name, "ui", threshold=0.8)
            if x is not None and y is not None:
                logger.debug(
                    "サブ端末%s: %s を検出しました (試行%d)",
                    device_num,
                    image_name,
                    attempt,
                )
                perform_action(port, "tap", x, y)
                time.sleep(sleep_time)
                return True

            if attempt % 5 == 0:
                rx, ry = find_image_on_device(port, tap_recovery, "ui", threshold=0.8)
                if rx is not None and ry is not None:
                    perform_action(port, "tap", rx, ry)

            time.sleep(sleep_time * 0.5)

        logger.warning("サブ端末%s: %s の検出に失敗しました (最大試行%d)", device_num, image_name, max_attempts)
        if loop_protection.should_backtrack(loop_key, device_num):
            backtrack = loop_protection.execute_backtrack(loop_key, device_num)
            if backtrack is not None:
                logger.warning("サブ端末%s: バックトラックを実施しました (%s)", device_num, loop_key)
        loop_protection.reset_operation(loop_key, device_num)
        return False

    def _open_friend_menu(self, port: str, device_index: int, sleep_time: float) -> bool:
        max_attempts = 60
        for attempt in range(1, max_attempts + 1):
            x, y = find_image_on_device(port, "friends.png", "ui", threshold=0.8)
            if x is not None and y is not None:
                logger.debug(
                    "メイン端末: サブ端末%s向けのfriends.pngを検出しました (試行%d)",
                    device_index,
                    attempt,
                )
                perform_action(port, "tap", x, y)
                time.sleep(sleep_time * 2)
                return True

            if attempt % 10 == 0:
                logger.debug(
                    "メイン端末: サブ端末%s向けfriends.pngを探索中... (試行%d)",
                    device_index,
                    attempt,
                )
            time.sleep(sleep_time * 0.5)

        logger.warning("メイン端末: サブ端末%s向けfriends.pngを見つけられませんでした。", device_index)
        return False

    def _locate_friend_id_field(
        self,
        port: str,
        device_index: int,
        sleep_time: float,
    ) -> Optional[Tuple[int, int]]:
        max_attempts = 160
        for attempt in range(1, max_attempts + 1):
            id_x, id_y = find_image_on_device(port, "friends_id.png", "ui", threshold=0.8)
            if id_x is not None and id_y is not None:
                logger.debug(
                    "メイン端末: サブ端末%s向けfriends_idを検出しました (試行%d)",
                    device_index,
                    attempt,
                )
                return int(id_x), int(id_y)

            for image_name in ("friends_syotai.png", "friends_ok.png", "friends_kensaku.png"):
                click_x, click_y = find_image_on_device(port, image_name, "ui", threshold=0.8)
                if click_x is not None and click_y is not None:
                    logger.debug(
                        "メイン端末: %sをクリックしてfriends_idを探索します (サブ端末%s, 試行%d)",
                        image_name,
                        device_index,
                        attempt,
                    )
                    perform_action(port, "tap", click_x, click_y)
                    time.sleep(sleep_time * 1.5)
                    break
            else:
                time.sleep(sleep_time * 0.5)

            if attempt % 20 == 0:
                logger.debug(
                    "メイン端末: サブ端末%s向けfriends_idを探索中... (試行%d)",
                    device_index,
                    attempt,
                )

        logger.warning("メイン端末: サブ端末%s向けfriends_idを特定できませんでした。", device_index)
        return None

    def _paste_friend_id_from_clipboard(self, port: str, device_index: int) -> bool:
        clipboard_text: Optional[str] = None
        try:
            import win32clipboard  # type: ignore

            win32clipboard.OpenClipboard()
            try:
                clipboard_text = win32clipboard.GetClipboardData(win32clipboard.CF_UNICODETEXT)  # type: ignore[attr-defined]
            except Exception:
                try:
                    raw = win32clipboard.GetClipboardData(win32clipboard.CF_TEXT)  # type: ignore[attr-defined]
                    if isinstance(raw, bytes):
                        clipboard_text = raw.decode("utf-8", errors="ignore")
                    else:
                        clipboard_text = str(raw)
                except Exception:
                    clipboard_text = None
            finally:
                win32clipboard.CloseClipboard()
        except ImportError:
            logger.warning("メイン端末: win32clipboardを利用できないためCtrl+Vにフォールバックします。")
        except Exception as exc:
            logger.warning("メイン端末: クリップボード取得に失敗しました (%s)", exc)

        text_to_paste = clipboard_text.strip() if clipboard_text else ""
        if text_to_paste:
            if self._send_text_via_keyevent(port, text_to_paste):
                logger.info("メイン端末: サブ端末%s向けIDをkeyeventで貼り付けました。", device_index)
                return True
            logger.warning("メイン端末: keyeventでの貼り付けに失敗したためCtrl+Vを試みます。")

        self._send_ctrl_v_keyevent(port)
        return False

    def _wait_for_friend_end_state(
        self,
        port: str,
        device_index: int,
        sleep_time: float,
    ) -> bool:
        max_attempts = 160
        friends_last_used = False

        for attempt in range(1, max_attempts + 1):
            end_x, end_y = find_image_on_device(port, "friends_end.png", "ui", threshold=0.8)
            if end_x is not None and end_y is not None:
                logger.debug(
                    "メイン端末: サブ端末%s向けfriends_endを検出しました (試行%d)",
                    device_index,
                    attempt,
                )
                return True

            yes_x, yes_y = find_image_on_device(port, "friends_yes.png", "ui", threshold=0.8)
            if yes_x is not None and yes_y is not None:
                logger.debug(
                    "メイン端末: friends_yesをクリックします (サブ端末%s, 試行%d)",
                    device_index,
                    attempt,
                )
                perform_action(port, "tap", yes_x, yes_y)
                time.sleep(sleep_time * 1.5)
                continue

            last_x, last_y = find_image_on_device(port, "friends_last.png", "ui", threshold=0.8)
            if last_x is not None and last_y is not None and not friends_last_used:
                logger.debug(
                    "メイン端末: friends_lastをクリックします (サブ端末%s, 試行%d)",
                    device_index,
                    attempt,
                )
                perform_action(port, "tap", last_x, last_y)
                friends_last_used = True
                time.sleep(sleep_time * 1.5)
                continue

            for image_name, wait_multiplier in (("friends_ok.png", 1.5), ("search.png", 2.5)):
                click_x, click_y = find_image_on_device(port, image_name, "ui", threshold=0.8)
                if click_x is not None and click_y is not None:
                    logger.debug(
                        "メイン端末: %sをクリックしてfriends_endを探索します (サブ端末%s, 試行%d)",
                        image_name,
                        device_index,
                        attempt,
                    )
                    perform_action(port, "tap", click_x, click_y)
                    time.sleep(sleep_time * wait_multiplier)
                    break
            else:
                time.sleep(sleep_time * 0.5)

            if attempt % 20 == 0:
                logger.debug(
                    "メイン端末: サブ端末%s向けfriends_endを探索中... (試行%d)",
                    device_index,
                    attempt,
                )

        logger.warning("メイン端末: サブ端末%s向けfriends_endを検出できませんでした。", device_index)
        return False

    def _confirm_final_friend_ok(
        self,
        port: str,
        device_index: int,
        sleep_time: float,
    ) -> bool:
        max_attempts = 100
        for attempt in range(1, max_attempts + 1):
            ok_x, ok_y = find_image_on_device(port, "friends_ok.png", "ui", threshold=0.8)
            if ok_x is not None and ok_y is not None:
                logger.debug(
                    "メイン端末: サブ端末%s向け最終friends_okを検出しました (試行%d)",
                    device_index,
                    attempt,
                )
                perform_action(port, "tap", ok_x, ok_y)
                time.sleep(sleep_time * 2)
                return True

            if attempt % 10 == 0:
                logger.debug(
                    "メイン端末: サブ端末%s向け最終friends_okを探索中... (試行%d)",
                    device_index,
                    attempt,
                )
            time.sleep(sleep_time * 0.5)

        logger.warning("メイン端末: サブ端末%s向け最終friends_okを検出できませんでした。", device_index)
        return False

    def _send_text_via_keyevent(self, port: str, text: str) -> bool:
        try:
            from monst.adb import run_adb_command
            from monst.adb.input import _send_text_keyevent_complete
        except ImportError as exc:
            logger.warning("メイン端末: keyeventモジュールの読み込みに失敗しました (%s)", exc)
            return False

        try:
            for _ in range(5):
                run_adb_command(["-s", port, "shell", "input", "keyevent", "67"])
                time.sleep(0.2)
            return bool(_send_text_keyevent_complete(port, text))
        except Exception as exc:
            logger.warning("メイン端末: keyeventによる貼り付けで例外発生 (%s)", exc)
            return False

    def _send_ctrl_v_keyevent(self, port: str) -> None:
        try:
            from monst.adb import run_adb_command

            run_adb_command(["-s", port, "shell", "input", "keyevent", "113"])
            run_adb_command(["-s", port, "shell", "input", "keyevent", "51"])
            logger.info("メイン端末: Ctrl+Vキーイベントを送信しました。")
        except Exception as exc:
            logger.error("メイン端末: Ctrl+Vキーイベントの送信に失敗しました (%s)", exc)


__all__ = ["FriendRegistrationExecutor"]
