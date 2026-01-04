"""
Quest workflow executor tailored for the refactored codebase.

Legacy のロジックを丹念に移植し、デバイス制御ヘルパーとの互換性を維持する。
"""

from __future__ import annotations

import time
from typing import Dict, Optional

from logging_util import MultiDeviceLogger, logger
from monst.adb import perform_action
from monst.device.exceptions import LoginError
from monst.image import mon_swipe, tap_if_found, find_image_on_device
from monst.image.device_control import tap_until_found
from monst.image.device_management import monitor_device_health
from utils.device_utils import get_terminal_number

from domain import LoginWorkflow


class QuestExecutor:
    """Execute quest scenarios based on configuration flags."""

    def __init__(self, login_workflow: LoginWorkflow) -> None:
        self.login_workflow = login_workflow

    def create_operation(
        self,
        *,
        flags: Dict[str, int],
        quest_parameters: Dict[str, str],
    ):
        """Return a callable compatible with ``MultiDeviceService.run_loop``."""

        def _operation(
            device_port: str,
            folder: str,
            multi_logger: Optional[MultiDeviceLogger] = None,
            **login_kwargs,
        ) -> bool:
            return self._execute(
                device_port=device_port,
                folder=folder,
                multi_logger=multi_logger,
                flags=flags,
                quest_parameters=quest_parameters,
                login_kwargs=login_kwargs,
            )

        return _operation

    # ------------------------------------------------------------------ #
    # Core execution
    # ------------------------------------------------------------------ #
    def _execute(
        self,
        *,
        device_port: str,
        folder: str,
        multi_logger: Optional[MultiDeviceLogger],
        flags: Dict[str, int],
        quest_parameters: Dict[str, str],
        login_kwargs: Dict[str, object],
    ) -> bool:
        flag_on_que = int(flags.get("on_que", 0))

        try:
            monitor_device_health([device_port])
            if not self.login_workflow.execute(
                device_port,
                folder,
                multi_logger,
                **login_kwargs,
            ):
                raise LoginError(f"ログイン失敗 (folder={folder})")

            if flag_on_que == 3:
                if not self._run_quest_three(device_port):
                    raise RuntimeError("クエスト3処理が完了しませんでした")
                if multi_logger:
                    multi_logger.log_success(device_port)
                logger.info("%s: %s [QUEST_DONE]", get_terminal_number(device_port), folder)
                return True

            self._prepare_battle(device_port, flag_on_que)
            self._wait_for_completion(device_port)

            if multi_logger:
                multi_logger.log_success(device_port)
            logger.info("%s: %s [QUEST_DONE]", get_terminal_number(device_port), folder)
            return True

        except Exception as exc:  # noqa: BLE001
            logger.error(
                "%s: %s [QUEST_ERROR] %s",
                get_terminal_number(device_port),
                folder,
                exc,
            )
            if multi_logger:
                multi_logger.log_error(device_port, str(exc))
            return False

    # ------------------------------------------------------------------ #
    # Workflow steps
    # ------------------------------------------------------------------ #
    def _prepare_battle(self, device_port: str, flag_on_que: int) -> None:
        """Handle the pre-battle setup with timeouts and branch logic."""
        start_time = time.time()
        timeout = 100  # matches legacy behaviour

        while time.time() - start_time < timeout:
            if tap_if_found("stay", device_port, "battle.png", "quest"):
                break

            if flag_on_que == 1:
                self._handle_event_quest(device_port)
            elif flag_on_que == 2:
                self._handle_guardian_quest(device_port)

            if tap_if_found("tap", device_port, "solo.png", "key"):
                while not tap_if_found("tap", device_port, "start.png", "quest"):
                    perform_action(device_port, "tap", 200, 575, duration=200)

            if tap_if_found("stay", device_port, "dekki_null.png", "key"):
                timeout += 300
                tap_until_found(device_port, "go_tittle.png", "key", "sonota.png", "key", "tap")
                while not tap_if_found("tap", device_port, "date_repear.png", "key"):
                    tap_if_found("tap", device_port, "go_tittle.png", "key")
                    tap_if_found("tap", device_port, "sonota.png", "key")
                tap_until_found(device_port, "data_yes.png", "key", "date_repear.png", "key", "tap")
                tap_until_found(device_port, "zz_home.png", "key", "data_yes.png", "key", "tap")

            tap_if_found("tap", device_port, "close.png", "key")
            tap_if_found("tap", device_port, "start.png", "quest")
            tap_if_found("tap", device_port, "kaifuku.png", "quest")
            tap_if_found("tap", device_port, "ok.png", "key")

            if tap_if_found("stay", device_port, "uketsuke.png", "key"):
                tap_if_found("tap", device_port, "zz_home.png", "key")

            time.sleep(1)

    def _handle_event_quest(self, device_port: str) -> None:
        tap_if_found("tap", device_port, "pue_shohi.png", "quest")
        tap_if_found("tap", device_port, "chosen.png", "quest")
        tap_if_found("tap", device_port, "chosen_ok.png", "quest")
        tap_if_found("tap", device_port, "counter.png", "quest")

        if tap_if_found("stay", device_port, "eventblack.png", "quest"):
            if not self._tap_event_choices(device_port):
                tap_if_found("swipe_up", device_port, "eventblack.png", "key")
                tap_if_found("swipe_up", device_port, "eventblack.png", "key")
                tap_if_found("swipe_up", device_port, "eventblack.png", "key")
                self._tap_event_choices(device_port)

    def _tap_event_choices(self, device_port: str) -> bool:
        choices = [
            tap_if_found("tap", device_port, "event_pue1.png", "quest"),
            tap_if_found("tap", device_port, "event_pue2.png", "quest"),
            tap_if_found("tap", device_port, "event_pue3.png", "quest"),
        ]
        return any(choices)

    def _handle_guardian_quest(self, device_port: str) -> None:
        tap_if_found("tap", device_port, "quest_c.png", "key")
        tap_if_found("tap", device_port, "quest.png", "key")
        tap_if_found("tap", device_port, "ichiran.png", "key")
        tap_if_found("tap", device_port, "shugo_que.png", "quest")
        tap_if_found("tap", device_port, "kyukyoku.png", "key")
        tap_if_found("tap", device_port, "shugo.png", "quest")

    def _wait_for_completion(self, device_port: str) -> None:
        """Poll quest completion indicators with retries."""
        for _ in range(300):
            time.sleep(2)
            if tap_if_found("stay", device_port, "que_end.png", "quest"):
                break
            tap_if_found("tap", device_port, "que_ok.png", "quest")
            tap_if_found("tap", device_port, "que_yes.png", "quest")
            tap_if_found("tap", device_port, "que_yes_re.png", "quest")
            tap_if_found("tap", device_port, "icon.png", "quest")
            mon_swipe(device_port)

    # ------------------------------------------------------------------ #
    # Quest type 3 (home/battle/free state machine)
    # ------------------------------------------------------------------ #
    def _run_quest_three(self, device_port: str) -> bool:
        """Execute the stabilised quest-3 workflow."""
        start_time = time.time()
        timeout = 20 * 60  # generous safety margin

        while time.time() - start_time < timeout:
            if self._detect_quest_three_completion(device_port):
                return True

            state = self._get_quest_three_state(device_port)
            if state == "home":
                self._process_quest_three_home_state(device_port)
            elif state == "battle":
                self._process_quest_three_battle_state(device_port)
            else:
                self._process_quest_three_free_state(device_port)

            time.sleep(0.3)

        return False

    def _detect_quest_three_completion(self, device_port: str) -> bool:
        """Return True once any of the completion indicators are found."""
        for image in ("que_end1.png", "que_end2.png", "que_end.png"):
            if tap_if_found("tap", device_port, image, "quest"):
                return True
        return False

    def _get_quest_three_state(self, device_port: str) -> str:
        if tap_if_found("stay", device_port, "sutamina.png", "quest"):
            return "home"
        if tap_if_found("stay", device_port, "battle.png", "quest"):
            return "battle"
        return "free"

    def _process_quest_three_home_state(self, device_port: str) -> None:
        if tap_if_found("tap", device_port, "retry.png", "quest"):
            return

        if self._tap_home_priority_sequence(device_port):
            return

        if self._handle_event_entry(device_port):
            return

        if self._handle_event_black_scroll(device_port):
            return

        if self._handle_pgacha(device_port):
            return

        if self._handle_nabitoha_or_jogai(device_port):
            return

        if self._handle_suketto(device_port):
            return

        self._click_login_home(device_port)

    def _process_quest_three_battle_state(self, device_port: str) -> None:
        mon_swipe(device_port)
        for image in ("que_ok.png", "que_yes.png", "que_yes_re.png"):
            tap_if_found("tap", device_port, image, "quest")

    def _process_quest_three_free_state(self, device_port: str) -> None:
        if tap_if_found("tap", device_port, "que_end_ok.png", "quest"):
            time.sleep(0.3)
            return
        self._click_login_home(device_port)

    def _tap_home_priority_sequence(self, device_port: str) -> bool:
        if tap_if_found("tap", device_port, "pue_shohi.png", "quest"):
            return True

        if self._tap_event_pue_images(device_port):
            return True

        targets = [
            ("event_s.png", "quest"),
            ("event_top.png", "quest"),
            ("chosen.png", "quest"),
            ("close.png", "quest"),
            ("solo.png", "quest"),
            ("kyara-waku.png", "quest"),
            ("start.png", "quest"),
            ("quest.png", "quest"),
            ("quest_c.png", "quest"),
            ("ok.png", "quest"),
        ]
        for image, folder in targets:
            if tap_if_found("tap", device_port, image, folder):
                return True
        return False

    def _handle_event_entry(self, device_port: str) -> bool:
        if tap_if_found("tap", device_port, "event.png", "quest"):
            return True

        if tap_if_found("stay", device_port, "event_l.png", "quest"):
            for _ in range(20):
                perform_action(device_port, "swipe", 300, 320, 220, 320, duration=2000)
                time.sleep(0.4)
                if tap_if_found("tap", device_port, "event.png", "quest"):
                    return True
                if not tap_if_found("stay", device_port, "event_l.png", "quest"):
                    break
        return False

    def _handle_event_black_scroll(self, device_port: str) -> bool:
        if not tap_if_found("stay", device_port, "eventblack.png", "quest"):
            return False

        for _ in range(10):
            perform_action(device_port, "swipe", 150, 500, 150, 300, duration=2000)
            time.sleep(0.4)
            if self._tap_event_pue_images(device_port):
                return True
        return False

    def _tap_event_pue_images(self, device_port: str) -> bool:
        if tap_if_found("tap", device_port, "pue_shohi.png", "quest"):
            return True

        for image in ("event_pue1.png", "event_pue2.png", "event_pue3.png", "event_pue.png"):
            if tap_if_found("tap", device_port, image, "quest"):
                return True
        return False

    def _handle_pgacha(self, device_port: str) -> bool:
        try:
            coords = find_image_on_device(device_port, "pgacha.png", "quest", threshold=0.8)
        except Exception:
            return False

        if not coords or coords[0] is None or coords[1] is None:
            return False

        x, y = coords
        perform_action(device_port, "tap", int(x), int(y) + 50, duration=150)
        return True

    def _handle_nabitoha_or_jogai(self, device_port: str) -> bool:
        found = False
        if tap_if_found("stay", device_port, "nabitoha.png", "puest"):
            found = True
        if tap_if_found("stay", device_port, "jogai.png", "puest"):
            found = True
        if not found:
            return False

        self._click_login_home(device_port)
        return True

    def _handle_suketto(self, device_port: str) -> bool:
        if not tap_if_found("stay", device_port, "suketto.png", "quest"):
            return False
        perform_action(device_port, "tap", 200, 550, duration=200)
        return True

    def _click_login_home(self, device_port: str) -> None:
        tap_if_found("tap", device_port, "zz_home.png", "login")
        tap_if_found("tap", device_port, "zz_home2.png", "login")
        perform_action(device_port, "tap", 40, 180, duration=150)


__all__ = ["QuestExecutor"]
