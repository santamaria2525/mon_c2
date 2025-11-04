"""
CLI and GUI front-ends for the cleaned Monster Strike Bot.

Both interfaces delegate business logic to ``mon_c2.operations`` so that
the presentation layer remains lightweight and easy to read.
"""

from __future__ import annotations

import sys
from typing import List

from logging_util import logger

from app.menu_map import build_menu
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from operations import OperationsFacade


class CLIInterface:
    """Command-line controller responsible for argument parsing and routing."""

    def __init__(self, core):
        self.core = core
        from operations import OperationsFacade  # Lazy import to avoid circular deps

        self.operations = OperationsFacade(core)

    # ------------------------------------------------------------------ #
    # Argument parsing
    # ------------------------------------------------------------------ #
    def parse_arguments(self) -> List[str]:
        """Return the command-line arguments (excluding the executable path)."""
        return sys.argv[1:] if len(sys.argv) > 1 else []

    def should_run_auto_mode(self, args: List[str]) -> bool:
        """True when the legacy ``1`` flag is present."""
        return "1" in args

    def handle_arguments(self, args: List[str]) -> bool:
        """
        Process CLI arguments.

        Returns True if the CLI fully handled the request (no GUI required).
        """
        self.core.handle_console_visibility(args)
        self._configure_monitor_preference(args)

        if self._handle_mm_folder_commands(args):
            return True

        if self.should_run_auto_mode(args):
            self.operations.run_login_loop(start_folder=1, auto_mode=True)
            return True

        return False

    def _configure_monitor_preference(self, args: List[str]) -> None:
        """Accept ``--monitor`` flag to select the task monitor backend."""
        monitor = None
        try:
            for i, arg in enumerate(args):
                if arg.startswith("--monitor="):
                    monitor = arg.split("=", 1)[1].strip().lower()
                    break
                if arg == "--monitor" and i + 1 < len(args):
                    monitor = args[i + 1].strip().lower()
                    break
        except Exception:
            monitor = None

        if monitor in ("compact", "process", "super"):
            self.core.set_monitor_preference(monitor)

    def _handle_mm_folder_commands(self, args: List[str]) -> bool:
        """Dispatch MM-folder CLI shortcuts."""
        if "mm-split" in args:
            logger.info("MMフォルダ切替を実行します (CLI)")
            self.operations.split_mm_folder()
            return True

        if "mm-help" in args:
            print(
                """
MMフォルダ関連コマンド:
  mm-split    : bin_pushフォルダをMMフォルダにコピー
  mm-help     : このヘルプを表示

使用例:
  python main.py mm-split
"""
            )
            return True

        return False

    # ------------------------------------------------------------------ #
    # Legacy compatibility helper
    # ------------------------------------------------------------------ #
    def run_auto_mode(self) -> None:
        """Legacy entry point for scripts that import this class directly."""
        logger.info("CLI auto mode requested via run_auto_mode().")
        self.operations.run_login_loop(auto_mode=True)


class GUIInterface:
    """GUI menu orchestrator."""

    def __init__(self, core):
        self.core = core
        from operations import OperationsFacade  # Lazy import to avoid circular deps

        self.operations = OperationsFacade(core)

    def show_main_menu(self) -> None:
        """Render the GUI menu using the shared menu map."""
        from utils import gui_run  # lazy import to avoid tkinter on CLI runs

        functions = build_menu(self.operations)
        gui_run(functions)
