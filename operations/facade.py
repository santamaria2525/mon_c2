# -*- coding: utf-8 -*-
"""High-level operations facade used by CLI/GUI layers."""

from __future__ import annotations

from functools import cached_property
from typing import Optional, TYPE_CHECKING, Any

from logging_util import logger

from domain import LoginWorkflow
from . import loops
from .macro import MacroRunner
from .single_executor import SingleDeviceExecutor
from .account_backup_executor import AccountBackupExecutor
from .friend_registration_executor import FriendRegistrationExecutor
from .shitei_click_executor import ShiteiClickExecutor
from services import ConfigService, MultiDeviceService
from .mm_tools import split_mm_folder as run_mm_split, batch_rename_mm_folder as run_mm_batch

if TYPE_CHECKING:  # pragma: no cover
    from app.operations.manager import OperationsManager as LegacyOperationsManager
else:
    LegacyOperationsManager = Any


class OperationsFacade:
    """Facade providing ergonomic access to all operations."""

    def __init__(self, core):
        self.core = core
        self.config_service = ConfigService()
        self.multi_device_service = MultiDeviceService()
        self.login_workflow = LoginWorkflow(core)

        self._device_count_logged = False

        self.login_loop_runner = loops.LoginLoopRunner(
            core,
            self.config_service,
            self.multi_device_service,
            self.login_workflow,
            on_ports_resolved=self._log_device_count_once,
        )
        self.one_set_runner = loops.OneSetRunner(
            core,
            self.config_service,
            self.multi_device_service,
            self.login_workflow,
            on_ports_resolved=self._log_device_count_once,
        )
        self.select_loop_runner = loops.SelectLoopRunner(
            core,
            self.config_service,
            self.multi_device_service,
            self.login_workflow,
            on_ports_resolved=self._log_device_count_once,
        )
        self.quest_loop_runner = loops.QuestLoopRunner(
            core,
            self.config_service,
            self.multi_device_service,
            self.login_workflow,
            on_ports_resolved=self._log_device_count_once,
        )
        self.hasya_runner = loops.HasyaTwoSetRunner(
            core,
            self.config_service,
            self.multi_device_service,
            on_ports_resolved=self._log_device_count_once,
        )
        self.macro_runner = MacroRunner(core)
        self.single_executor = SingleDeviceExecutor(core, self.config_service)
        self.account_backup_executor = AccountBackupExecutor(core, self.config_service, self.multi_device_service)
        self.friend_executor = FriendRegistrationExecutor(
            core,
            self.config_service,
            self.multi_device_service,
            self.login_workflow,
        )
        self.shitei_click_executor = ShiteiClickExecutor(core, self.config_service)

    # ------------------------------------------------------------------ #
    # Port logging helper
    # ------------------------------------------------------------------ #
    def _log_device_count_once(self, device_count: int, ports) -> None:
        if self._device_count_logged:
            return
        logger.debug("Device count configured: %d", device_count)
        if ports:
            preview = ", ".join(str(p) for p in list(ports)[:3])
            logger.debug("Using %d ports (e.g. %s...)", len(ports), preview)
        self._device_count_logged = True

    # ------------------------------------------------------------------ #
    # Public facade methods
    # ------------------------------------------------------------------ #
    def run_select_loop(self) -> None:
        self.select_loop_runner.run()

    def write_set(self) -> None:
        self.one_set_runner.run()

    def run_login_loop(self, start_folder: Optional[int] = None, *, auto_mode: bool = False) -> None:
        self.login_loop_runner.run(start_folder=start_folder, auto_mode=auto_mode)

    def run_continuous_login_loop(self) -> None:
        self.login_loop_runner.run_continuous()

    def run_hasya_loop(self) -> None:
        self.hasya_runner.run()

    def run_event_loop(self) -> None:
        self.quest_loop_runner.run()

    def write_single(self) -> None:
        self.single_executor.write()

    def reset_single(self) -> None:
        self.single_executor.initialize()

    def save_single(self) -> None:
        self.single_executor.save()

    def run_macro(self) -> None:
        self.macro_runner.run()

    def split_mm_folder(self) -> None:
        run_mm_split()

    def batch_rename_mm_folder(self) -> None:
        run_mm_batch()

    def run_friend_registration(self) -> None:
        self.friend_executor.run()

    def run_account_backup(self) -> None:
        self.account_backup_executor.run()

    def run_shitei_click(self) -> None:
        self.shitei_click_executor.run()

    def run_id_check(self) -> None:
        """Bridge to legacy IDチェック処理."""
        self.legacy.main_id_check()

    # ------------------------------------------------------------------ #
    # Legacy bridge
    # ------------------------------------------------------------------ #
    @cached_property
    def legacy(self) -> LegacyOperationsManager:
        """Instantiate the legacy manager on demand for unported operations."""
        try:
            from app.operations.manager import OperationsManager as _LegacyOperationsManager
        except Exception as exc:  # pragma: no cover - logged for user
            raise RuntimeError(
                "Legacy OperationsManager could not be imported. "
                "Please ensure app.operations.manager is syntactically valid."
            ) from exc
        return _LegacyOperationsManager(self.core)
