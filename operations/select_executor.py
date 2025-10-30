"""
High-level select menu executor implemented on the cleaned codebase.

既存のデバイス操作ライブラリを利用しつつ、オーケストレーション部分のみを軽量化する。
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Dict, Optional

from image_detection import tap_if_found
from logging_util import MultiDeviceLogger, logger
from monst.adb import pull_file_from_nox
from monst.device.checks import icon_check
from monst.device.events import bakuage_roulette_do, event_do
from monst.device.exceptions import GachaOperationError, LoginError, SellOperationError
from monst.device.friends import friend_status_check
from monst.device.gacha import mon_gacha_shinshun
from monst.device.operations import medal_change, mission_get, mon_initial, mon_sell, name_change, orb_count
from monst.image.device_management import monitor_device_health
from utils.device_utils import get_terminal_number

from mon_c2.domain import LoginWorkflow
from mon_c2.operations.select_flow import SelectResult, build_default_workflow


@dataclass
class _SelectState:
    device_port: str
    folder: str
    multi_logger: Optional[MultiDeviceLogger]
    quest_preset: str
    quest_parameters: Dict[str, str]
    gacha_attempts: int
    gacha_limit: int
    continue_until_character: bool
    found_character: Optional[bool] = None
    results: Optional[list[SelectResult]] = None


class SelectExecutor:
    """Execute the select workflow for a single device."""

    def __init__(self, login_workflow: LoginWorkflow):
        self.login_workflow = login_workflow

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    def create_operation(
        self,
        *,
        flags: Dict[str, int],
        quest_preset: str,
        quest_parameters: Dict[str, str],
        gacha_attempts: int,
        gacha_limit: int,
        continue_until_character: bool,
    ):
        """Return a callable suitable for MultiDeviceService.run_loop."""

        def _operation(
            device_port: str,
            folder: str,
            multi_logger: Optional[MultiDeviceLogger] = None,
            **login_kwargs,
        ) -> bool:
            return self._execute(
                device_port,
                folder,
                multi_logger,
                flags=flags,
                quest_preset=quest_preset,
                quest_parameters=quest_parameters,
                gacha_attempts=gacha_attempts,
                gacha_limit=gacha_limit,
                continue_until_character=continue_until_character,
                login_kwargs=login_kwargs,
            )

        return _operation

    # ------------------------------------------------------------------ #
    # Internal execution pipeline
    # ------------------------------------------------------------------ #
    def _execute(
        self,
        device_port: str,
        folder: str,
        multi_logger: Optional[MultiDeviceLogger],
        *,
        flags: Dict[str, int],
        quest_preset: str,
        quest_parameters: Dict[str, str],
        gacha_attempts: int,
        gacha_limit: int,
        continue_until_character: bool,
        login_kwargs: Dict[str, object],
    ) -> bool:
        state = _SelectState(
            device_port=device_port,
            folder=folder,
            multi_logger=multi_logger,
            quest_preset=quest_preset,
            quest_parameters=dict(quest_parameters),
            gacha_attempts=gacha_attempts,
            gacha_limit=gacha_limit,
            continue_until_character=continue_until_character,
            results=[],
        )
        operations_completed: list[str] = []

        try:
            monitor_device_health([device_port])

            login_success = self.login_workflow.execute(
                device_port,
                folder,
                multi_logger,
                **login_kwargs,
            )
            if not login_success:
                raise LoginError(f"ログインに失敗しました (folder={folder})")

            self._clear_gacha_dialogs(device_port)

            workflow = build_default_workflow(
                lambda key: self._make_handler(key, state)
            )
            workflow_results = workflow.execute(flags)
            state.results = workflow_results

            for result in workflow_results:
                if result.details:
                    operations_completed.append(result.details)

            summary = " ".join(operations_completed) if operations_completed else "NONE"
            logger.info("%s: %s [%s]", get_terminal_number(device_port), folder, summary)
            if multi_logger:
                multi_logger.log_success(device_port)
            return True

        except LoginError as exc:
            logger.error("%s: %s [LOGIN_ERROR]", get_terminal_number(device_port), folder)
            if multi_logger:
                multi_logger.log_error(device_port, str(exc))
            if flags.get("on_save", 0) == 1:
                self._attempt_save(device_port, folder)
            return False
        except (GachaOperationError, SellOperationError) as exc:
            logger.error("%s: %s [OPERATION_ERROR]", get_terminal_number(device_port), folder)
            if multi_logger:
                multi_logger.log_error(device_port, str(exc))
            if flags.get("on_save", 0) == 1:
                self._attempt_save(device_port, folder)
            return False
        except Exception as exc:  # noqa: BLE001
            logger.error("%s: %s [ERROR] %s", get_terminal_number(device_port), folder, exc)
            if multi_logger:
                multi_logger.log_error(device_port, str(exc))
            if flags.get("on_save", 0) == 1:
                self._attempt_save(device_port, folder)
            return False

    # ------------------------------------------------------------------ #
    # Handlers
    # ------------------------------------------------------------------ #
    def _make_handler(self, key: str, state: _SelectState):
        mapping = {
            "on_check": lambda flags: self._handle_check(state, flags),
            "on_event": lambda flags: self._handle_event(state, flags),
            "on_que": lambda flags: self._handle_que(state, flags),
            "on_medal": lambda flags: self._handle_simple(
                state, flags, key, medal_change, "MEDAL"
            ),
            "on_initial": lambda flags: self._handle_simple(
                state, flags, key, mon_initial, "INITIAL"
            ),
            "on_mission": lambda flags: self._handle_simple(
                state, flags, key, mission_get, "MISSION"
            ),
            "on_name": lambda flags: self._handle_simple(
                state, flags, key, name_change, "NAME"
            ),
            "on_gacha": lambda flags: self._handle_gacha(state, flags),
            "on_sell": lambda flags: self._handle_simple(
                state, flags, key, mon_sell, "SELL"
            ),
            "on_count": lambda flags: self._handle_count(state, flags),
            "on_save": lambda flags: self._handle_save(state, flags),
        }
        handler = mapping.get(key)
        if not handler:
            return lambda _flags: SelectResult(key, True, "")
        return handler

    def _handle_check(self, state: _SelectState, flags: Dict[str, int]) -> SelectResult:
        try:
            icon_check(state.device_port, state.folder)
            return SelectResult("on_check", True, "CHECK")
        except Exception as exc:  # noqa: BLE001
            logger.warning("CHECK失敗: %s", exc)
            return SelectResult("on_check", False, "CHECK_FAIL")

    def _handle_event(self, state: _SelectState, flags: Dict[str, int]) -> SelectResult:
        mode = int(flags.get("on_event", 0))
        try:
            if mode == 1:
                success = bool(event_do(state.device_port, state.folder))
                return SelectResult("on_event", success, "EVENT" if success else "EVENT_FAIL")
            if mode == 2:
                success = bool(
                    bakuage_roulette_do(state.device_port, state.folder, state.multi_logger)
                )
                return SelectResult(
                    "on_event", success, "BAKUAGE_ROULETTE" if success else "BAKUAGE_ROULETTE_FAIL"
                )
            if mode == 3:
                success = bool(
                    friend_status_check(state.device_port, state.folder, state.multi_logger)
                )
                return SelectResult(
                    "on_event",
                    success,
                    "FRIEND_STATUS_CHECK" if success else "FRIEND_STATUS_CHECK_FAIL",
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning("イベント処理失敗: %s", exc)
            return SelectResult("on_event", False, "EVENT_ERROR")
        return SelectResult("on_event", True, "")

    def _handle_que(self, state: _SelectState, flags: Dict[str, int]) -> SelectResult:
        # 旧実装では on_que==1 の場合に別処理へ委譲していたため現状はスキップ
        return SelectResult("on_que", True, "")

    def _handle_simple(
        self,
        state: _SelectState,
        flags: Dict[str, int],
        key: str,
        func,
        label: str,
    ) -> SelectResult:
        try:
            try:
                func(state.device_port, state.folder, state.multi_logger)
            except TypeError:
                func(state.device_port, state.folder)
            return SelectResult(key, True, label)
        except Exception as exc:  # noqa: BLE001
            logger.warning("%s 処理失敗: %s", label, exc)
            return SelectResult(key, False, f"{label}_FAIL")

    def _handle_gacha(self, state: _SelectState, flags: Dict[str, int]) -> SelectResult:
        try:
            gacha_limit = max(0, int(state.gacha_limit))
            continue_until_character = bool(state.continue_until_character)
            if gacha_limit <= 0:
                gacha_limit = max(1, int(state.gacha_attempts))
            state.found_character = mon_gacha_shinshun(
                state.device_port,
                state.folder,
                gacha_limit,
                state.multi_logger,
                continue_until_character=continue_until_character,
            )
            label = f"GACHA({state.found_character})"
            return SelectResult("on_gacha", True, label)
        except Exception as exc:  # noqa: BLE001
            logger.warning("ガチャ処理失敗: %s", exc)
            state.found_character = False
            return SelectResult("on_gacha", False, "GACHA_FAIL")

    def _handle_count(self, state: _SelectState, flags: Dict[str, int]) -> SelectResult:
        max_retries = 10
        for attempt in range(max_retries):
            try:
                if orb_count(
                    state.device_port,
                    state.folder,
                    found_character=state.found_character,
                    multi_logger=state.multi_logger,
                ):
                    return SelectResult("on_count", True, "COUNT")
            except Exception:
                pass
            if attempt < max_retries - 1:
                time.sleep(2)
        return SelectResult("on_count", False, "COUNT_FAIL")

    def _handle_save(self, state: _SelectState, flags: Dict[str, int]) -> SelectResult:
        try:
            pull_file_from_nox(state.device_port, state.folder)
            return SelectResult("on_save", True, "SAVE")
        except Exception as exc:  # noqa: BLE001
            logger.warning("SAVE失敗: %s", exc)
            return SelectResult("on_save", False, "SAVE_FAIL")

    # ------------------------------------------------------------------ #
    # Utility helpers
    # ------------------------------------------------------------------ #
    def _clear_gacha_dialogs(self, device_port: str) -> None:
        if tap_if_found("tap", device_port, "gacha_shu.png", "login"):
            tap_if_found("tap", device_port, "zz_home.png", "login")
            tap_if_found("tap", device_port, "zz_home2.png", "login")
            time.sleep(1)

    def _attempt_save(self, device_port: str, folder: str) -> None:
        try:
            pull_file_from_nox(device_port, folder)
        except Exception:
            pass


__all__ = ["SelectExecutor"]
