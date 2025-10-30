"""Multi-device orchestration helpers for the cleaned codebase."""

from __future__ import annotations

from typing import Any, Callable, Iterable, Mapping, Optional, Sequence, Tuple

from logging_util import logger
from multi_device import (
    remove_all_nox,
    run_loop,
    run_loop_enhanced,
    run_push,
)
from utils.set_processing import run_continuous_set_loop


Operation = Callable[..., Any]


class MultiDeviceService:
    """
    Thin wrapper around the proven multi-device helpers.

    Centralising these calls simplifies testing and lets us layer additional
    safeguards or logging in a single place as the refactor progresses.
    """

    def run_push(self, base_folder: int, ports: Sequence[str]) -> Tuple[Optional[int], Sequence[str]]:
        logger.debug("Running run_push for folder %03d on ports %s", base_folder, ports)
        return run_push(int(base_folder), list(ports))

    def run_loop(
        self,
        base_folder: int,
        operation: Operation,
        ports: Sequence[str],
        operation_name: str,
        *,
        custom_args: Optional[Mapping[str, Any]] = None,
        use_independent_processing: bool = True,
        additional_operation: Optional[Operation] = None,
        save_data_files: bool = False,
    ) -> Tuple[Optional[int], bool]:
        return run_loop_enhanced(
            int(base_folder),
            operation,
            list(ports),
            operation_name,
            additional_operation=additional_operation,
            custom_args=custom_args,
            save_data_files=save_data_files,
            use_independent_processing=use_independent_processing,
        )

    def run_simple_loop(
        self,
        base_folder: int,
        operation: Operation,
        ports: Sequence[str],
        operation_name: str,
    ) -> None:
        run_loop(int(base_folder), operation, list(ports), operation_name)  # legacy helper

    def run_continuous_set_loop(
        self,
        base_folder: int,
        operation: Operation,
        ports: Sequence[str],
        operation_name: str,
        *,
        custom_args: Optional[Mapping[str, Any]] = None,
    ) -> None:
        run_continuous_set_loop(
            base_folder=int(base_folder),
            operation=operation,
            ports=list(ports),
            operation_name=operation_name,
            custom_args=custom_args,
        )

    def remove_all_nox(self) -> None:
        remove_all_nox()
