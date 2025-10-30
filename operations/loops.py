# -*- coding: utf-8 -*-
"""Loop-oriented operations (select/login/quest) for the cleaned codebase."""

from __future__ import annotations

import concurrent.futures
import time
from typing import Callable, List, Optional, Sequence, Tuple

import config as legacy_config  # type: ignore

from adb_utils import reset_adb_server
from logging_util import MultiDeviceLogger, logger
from utils import close_nox_error_dialogs, display_message, get_target_folder

from mon_c2.config import MAX_FOLDER_LIMIT
from mon_c2.domain import LoginWorkflow
from mon_c2.operations.helpers import apply_select_configuration, cleanup_macro_windows
from mon_c2.operations.quest_executor import QuestExecutor
from mon_c2.services import ConfigService, ConfigSnapshot, MultiDeviceService

PortsResolvedCallback = Callable[[int, Sequence[str]], None]


class _BaseLoop:
    """Common helpers shared by the loop runners."""

    def __init__(
        self,
        core,
        config_service: ConfigService,
        multi_device_service: MultiDeviceService,
        *,
        on_ports_resolved: PortsResolvedCallback,
    ) -> None:
        self.core = core
        self.config_service = config_service
        self.multi_device_service = multi_device_service
        self._on_ports_resolved = on_ports_resolved

    def _load_config_and_ports(self) -> Tuple[Optional[ConfigSnapshot], Optional[List[str]]]:
        snapshot = self.config_service.load()
        if not self.config_service.validate_device_count(snapshot.device_count):
            logger.error("Invalid device count: %s", snapshot.device_count)
            logger.debug("Please set device_count in config.json between 3 and 8.")
            return None, None

        ports = self.config_service.get_ports_for_device_count(snapshot.device_count)
        self._on_ports_resolved(snapshot.device_count, ports)
        return snapshot, ports

    def _resolve_base_folder(self, start_folder: Optional[int]) -> Optional[int]:
        if start_folder is not None:
            return int(start_folder)

        folder_value = self.core.get_start_folder()
        if folder_value is None:
            return None
        return int(folder_value)

    def _guard_folder_limit(self, folder_value: int) -> bool:
        if folder_value > MAX_FOLDER_LIMIT:
            self._handle_folder_limit_exceeded(folder_value, reason=None)
            return False
        return True

    def _handle_folder_limit_exceeded(self, folder_value: int, reason: Optional[str]) -> None:
        if reason == "no_data":
            logger.info("BIN data missing; stopping at folder %03d", folder_value)
        else:
            logger.error("Folder limit exceeded (> %d): %d", MAX_FOLDER_LIMIT, folder_value)
        logger.info("Folder limit reached. Shutting down application.")
        try:
            self.core.stop_event.set()
        except Exception:
            pass
        raise SystemExit(0)


MAX_PARALLEL_DEVICE_TASKS = 4


class LoginLoopRunner(_BaseLoop):
    """Implements the primary login loop using the new service layout."""

    def __init__(
        self,
        core,
        config_service: ConfigService,
        multi_device_service: MultiDeviceService,
        login_workflow: LoginWorkflow,
        *,
        on_ports_resolved: PortsResolvedCallback,
    ) -> None:
        super().__init__(
            core,
            config_service,
            multi_device_service,
            on_ports_resolved=on_ports_resolved,
        )
        self.login_workflow = login_workflow

    def run(self, start_folder: Optional[int] = None, *, auto_mode: bool = False) -> None:
        snapshot, ports = self._load_config_and_ports()
        if not snapshot or not ports:
            return

        base_folder = self._resolve_base_folder(start_folder)
        if base_folder is None:
            logger.error("No folder was selected.")
            return

        if not self._guard_folder_limit(base_folder):
            return

        closed = cleanup_macro_windows()
        if closed:
            logger.debug("Closed %d leftover macro windows", closed)

        try:
            close_nox_error_dialogs()
        except Exception as exc:  # pragma: no cover - best effort cleanup
            logger.debug("Failed to close NOX error dialogs: %s", exc)

        logger.debug("Login loop start: folder %03d / ports %s", base_folder, ports)
        reset_adb_server()

        custom_args = {"home_early": True}
        if auto_mode:
            logger.debug("Auto mode active: home_early=True")

        next_folder, should_stop = self.multi_device_service.run_loop(
            base_folder,
            self.login_workflow.execute,
            ports,
            "Login",
            custom_args=custom_args,
            use_independent_processing=snapshot.use_independent_processing,
        )

        if should_stop:
            stop_reason = "no_data" if next_folder is None else None
            cutoff_folder = next_folder if next_folder is not None else max(base_folder, MAX_FOLDER_LIMIT)
            self._handle_folder_limit_exceeded(cutoff_folder, reason=stop_reason)

        if next_folder:
            logger.debug("Next folder candidate: %03d", next_folder)

    def run_continuous(self) -> None:
        snapshot, ports = self._load_config_and_ports()
        if not snapshot or not ports:
            return

        base_folder_raw = get_target_folder()
        if base_folder_raw is None:
            logger.error("No folder was selected.")
            return

        try:
            base_folder = int(base_folder_raw)
        except ValueError:
            logger.error("Invalid folder number: %s", base_folder_raw)
            return

        if not self._guard_folder_limit(base_folder):
            return

        logger.debug("Continuous login loop start: folder %03d / ports %s", base_folder, ports)
        reset_adb_server()

        try:
            self.multi_device_service.run_continuous_set_loop(
                base_folder=base_folder,
                operation=self.login_workflow.execute,
                ports=ports,
                operation_name="Login loop (8-device continuous)",
                custom_args=None,
            )
        except Exception as exc:
            logger.error("Eight-device loop error: %s", exc)
            display_message("Error", f"An error occurred:\n{exc}")


class OneSetRunner(_BaseLoop):
    """Replicates the legacy 1set write behaviour with clearer structure."""

    def __init__(
        self,
        core,
        config_service: ConfigService,
        multi_device_service: MultiDeviceService,
        login_workflow: LoginWorkflow,
        *,
        on_ports_resolved: PortsResolvedCallback,
    ) -> None:
        super().__init__(
            core,
            config_service,
            multi_device_service,
            on_ports_resolved=on_ports_resolved,
        )
        self.login_workflow = login_workflow

    def run(self) -> None:
        snapshot, ports = self._load_config_and_ports()
        if not snapshot or not ports:
            return

        base_folder = self._resolve_base_folder(None)
        if base_folder is None:
            logger.error("フォルダが選択されませんでした。")
            return

        if not self._guard_folder_limit(base_folder):
            return

        closed = cleanup_macro_windows()
        if closed:
            logger.debug("Closed %d leftover macro windows", closed)

        logger.debug("1set書き込み処理開始: フォルダ%03d / ポート%s", base_folder, ports)
        reset_adb_server()

        try:
            next_base, pushed_folders = self.multi_device_service.run_push(base_folder, ports)
        except Exception as exc:  # pragma: no cover - defensive bridge
            logger.error("run_push 実行中にエラー: %s", exc)
            display_message("エラー", f"bin書き込み中にエラーが発生しました:\n{exc}")
            return

        if pushed_folders:
            logger.debug("bin書き込み完了: 次の開始候補 %03d / 使用フォルダ %s", next_base, pushed_folders)
        else:
            logger.warning("bin書き込み結果が空でした。configとbin_pushフォルダを確認してください。")

        folder_label = str(base_folder)
        multi_logger = MultiDeviceLogger(list(ports), [folder_label] * len(ports))
        worker_count = min(len(ports), MAX_PARALLEL_DEVICE_TASKS)

        with concurrent.futures.ThreadPoolExecutor(max_workers=worker_count) as executor:
            futures = {
                executor.submit(
                    self.login_workflow.execute,
                    port,
                    folder_label,
                    multi_logger,
                ): port
                for port in ports
            }
            for future, port in futures.items():
                try:
                    result = future.result()
                    logger.debug("1setログイン完了: %s => %s", port, result)
                except Exception as exc:
                    logger.error("1setログイン失敗: %s => %s", port, exc)

        multi_logger.summarize_results("1set書き込み")
        logger.debug("1set書き込み用ログイン処理が完了しました")
        time.sleep(5)  # legacy互換の待機時間


class HasyaTwoSetRunner(_BaseLoop):
    """Bridge to the legacy hasya two-set workflow while we refactor progressively."""

    def __init__(
        self,
        core,
        config_service: ConfigService,
        multi_device_service: MultiDeviceService,
        *,
        on_ports_resolved: PortsResolvedCallback,
    ) -> None:
        super().__init__(
            core,
            config_service,
            multi_device_service,
            on_ports_resolved=on_ports_resolved,
        )
        from mon_c2.operations.hasya_executor import HasyaExecutor

        self._executor = HasyaExecutor(multi_device_service)

    def run(self) -> None:
        import config as legacy_config  # type: ignore

        snapshot, ports = self._load_config_and_ports()
        if not snapshot or not ports:
            return

        apply_select_configuration(
            snapshot.select_flags,
            name_prefix=snapshot.name_prefix,
            gacha_attempts=snapshot.gacha_attempts,
            gacha_limit=snapshot.gacha_limit,
            continue_until_character=snapshot.continue_until_character,
            room_key1=snapshot.room_key1,
            room_key2=snapshot.room_key2,
        )
        try:
            cfg = legacy_config.get_config()  # type: ignore[attr-defined]
            cfg.device_count = snapshot.device_count
        except Exception:
            pass
        legacy_config.device_count = snapshot.device_count
        legacy_config.select_ports = list(ports)  # legacy helpers expect this global list

        base_folder = self._resolve_base_folder(None)
        if base_folder is None:
            logger.error("No folder was selected.")
            return

        if not self._guard_folder_limit(base_folder):
            return

        closed = cleanup_macro_windows()
        if closed:
            logger.debug("Closed %d leftover macro windows", closed)

        try:
            close_nox_error_dialogs()
        except Exception as exc:
            logger.debug("Failed to close NOX error dialogs: %s", exc)

        reset_adb_server()

        self._executor.run(base_folder, ports)


class SelectLoopRunner(_BaseLoop):
    """Execute the select workflow using the cleaned configuration."""

    def __init__(
        self,
        core,
        config_service: ConfigService,
        multi_device_service: MultiDeviceService,
        login_workflow: LoginWorkflow,
        *,
        on_ports_resolved: PortsResolvedCallback,
    ) -> None:
        super().__init__(
            core,
            config_service,
            multi_device_service,
            on_ports_resolved=on_ports_resolved,
        )
        from mon_c2.operations.select_executor import SelectExecutor

        self._executor = SelectExecutor(login_workflow)

    def run(self) -> None:
        snapshot, ports = self._load_config_and_ports()
        if not snapshot or not ports:
            return
        legacy_config.device_count = snapshot.device_count
        legacy_config.select_ports = list(ports)

        base_folder = self._resolve_base_folder(None)
        if base_folder is None:
            logger.error("No folder was selected.")
            return

        if not self._guard_folder_limit(base_folder):
            return

        apply_select_configuration(
            snapshot.select_flags,
            name_prefix=snapshot.name_prefix,
            gacha_attempts=snapshot.gacha_attempts,
            gacha_limit=snapshot.gacha_limit,
            continue_until_character=snapshot.continue_until_character,
            room_key1=snapshot.room_key1,
            room_key2=snapshot.room_key2,
        )
        logger.debug("Select flags: %s", snapshot.select_flags)

        closed = cleanup_macro_windows()
        if closed:
            logger.debug("Closed %d leftover macro windows", closed)

        try:
            close_nox_error_dialogs()
        except Exception as exc:  # pragma: no cover
            logger.debug("Failed to close NOX error dialogs: %s", exc)

        reset_adb_server()

        operation = self._executor.create_operation(
            flags=snapshot.select_flags,
            quest_preset=snapshot.quest_preset,
            quest_parameters=snapshot.quest_parameters,
            gacha_attempts=snapshot.gacha_attempts,
            gacha_limit=snapshot.gacha_limit,
            continue_until_character=snapshot.continue_until_character,
        )

        next_folder, should_stop = self.multi_device_service.run_loop(
            base_folder,
            operation,
            ports,
            "Select",
            custom_args={"home_early": True},
            use_independent_processing=snapshot.use_independent_processing,
        )

        if should_stop:
            stop_reason = "no_data" if next_folder is None else None
            cutoff_folder = next_folder if next_folder is not None else max(base_folder, MAX_FOLDER_LIMIT)
            self._handle_folder_limit_exceeded(cutoff_folder, reason=stop_reason)

        if next_folder:
            logger.debug("Next folder candidate: %03d", next_folder)


class QuestLoopRunner(_BaseLoop):
    """Execute the quest workflow using the cleaned configuration."""

    def __init__(
        self,
        core,
        config_service: ConfigService,
        multi_device_service: MultiDeviceService,
        login_workflow: LoginWorkflow,
        *,
        on_ports_resolved: PortsResolvedCallback,
    ) -> None:
        super().__init__(
            core,
            config_service,
            multi_device_service,
            on_ports_resolved=on_ports_resolved,
        )
        self._executor = QuestExecutor(login_workflow)

    def run(self) -> None:
        snapshot, ports = self._load_config_and_ports()
        if not snapshot or not ports:
            return
        legacy_config.device_count = snapshot.device_count
        legacy_config.select_ports = list(ports)

        base_folder = self._resolve_base_folder(None)
        if base_folder is None:
            logger.error("No folder was selected.")
            return

        if not self._guard_folder_limit(base_folder):
            return

        apply_select_configuration(
            snapshot.select_flags,
            name_prefix=snapshot.name_prefix,
            gacha_attempts=snapshot.gacha_attempts,
            gacha_limit=snapshot.gacha_limit,
            continue_until_character=snapshot.continue_until_character,
            room_key1=snapshot.room_key1,
            room_key2=snapshot.room_key2,
        )
        logger.debug(
            "Quest configuration: flags=%s preset=%s parameters=%s",
            snapshot.select_flags,
            snapshot.quest_preset,
            snapshot.quest_parameters,
        )

        try:
            close_nox_error_dialogs()
        except Exception as exc:  # pragma: no cover
            logger.debug("Failed to close NOX error dialogs: %s", exc)

        reset_adb_server()

        operation = self._executor.create_operation(
            flags=snapshot.select_flags,
            quest_parameters=snapshot.quest_parameters,
        )

        next_folder, should_stop = self.multi_device_service.run_loop(
            base_folder,
            operation,
            ports,
            "Quest",
            custom_args=None,
            use_independent_processing=snapshot.use_independent_processing,
        )

        if should_stop:
            stop_reason = "no_data" if next_folder is None else None
            cutoff_folder = next_folder if next_folder is not None else max(base_folder, MAX_FOLDER_LIMIT)
            from app.operations.manager import OperationsManager  # legacy helper

            legacy = OperationsManager(self.core)
            legacy._handle_folder_limit_exceeded(cutoff_folder, reason=stop_reason)  # type: ignore[attr-defined]

        if next_folder:
            logger.debug("Next folder candidate: %03d", next_folder)
