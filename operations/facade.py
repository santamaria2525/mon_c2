# -*- coding: utf-8 -*-
"""High-level operations facade used by CLI/GUI layers."""

from __future__ import annotations

from functools import cached_property
from typing import Optional

from logging_util import logger

from app.operations.manager import OperationsManager as LegacyOperationsManager

from mon_c2.domain import LoginWorkflow
from . import loops
from mon_c2.operations.macro import MacroRunner
from mon_c2.operations.single_executor import SingleDeviceExecutor
from mon_c2.operations.account_backup_executor import AccountBackupExecutor
from mon_c2.operations.friend_registration_executor import FriendRegistrationExecutor
from mon_c2.services import ConfigService, MultiDeviceService


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
        self.legacy.mm_folder_split()

    def batch_rename_mm_folder(self) -> None:
        self.legacy.mm_folder_batch_rename()

    def run_friend_registration(self) -> None:
        self.friend_executor.run()

    def run_account_backup(self) -> None:
        self.account_backup_executor.run()

    # ------------------------------------------------------------------ #
    # Legacy bridge
    # ------------------------------------------------------------------ #
    @cached_property
    def legacy(self) -> LegacyOperationsManager:
        """Instantiate the legacy manager on demand for unported operations."""
        return LegacyOperationsManager(self.core)
