# -*- coding: utf-8 -*-
"""
New entry point for the cleaned Monster Strike Bot.

This script mirrors the existing behaviour exposed by ``main.py`` but delegates
to the reorganised packages under ``mon_c2``. It can be invoked directly
or via ``python -m mon_c2`` while we migrate functionality.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure the package root is importable even when running as a script.
_PACKAGE_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _PACKAGE_DIR.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

def main() -> None:
    """Run the automation application."""
    try:
        from mon_c2.app import ApplicationCore, CLIInterface, GUIInterface
    except Exception as exc:  # noqa: BLE001
        _handle_startup_failure(exc)
        raise

    core = ApplicationCore()
    core.setup_console_title()

    cli = CLIInterface(core)
    args = cli.parse_arguments()

    if not cli.handle_arguments(args):
        gui = GUIInterface(core)
        gui.show_main_menu()


def _handle_startup_failure(exc: Exception) -> None:
    import traceback
    from datetime import datetime

    is_frozen = getattr(sys, "frozen", False)
    base_dir = (
        Path(sys.executable).resolve().parent
        if is_frozen
        else _PACKAGE_DIR
    )
    log_dir = base_dir / "logs"
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    fallback_log = log_dir / f"fatal_{timestamp}.log"
    error_text = traceback.format_exc()
    try:
        fallback_log.write_text(error_text, encoding="utf-8")
    except Exception:
        pass

    try:
        from logging_util import logger

        logger.exception("Fatal error during application startup")
    except Exception:
        pass

    message = (
        "致命的なエラーが発生しました。\n"
        f"詳細はログファイルをご確認ください:\n{fallback_log}"
    )

    if is_frozen:
        try:
            import ctypes

            ctypes.windll.user32.MessageBoxW(None, message, "MS Tools C2", 0x10)
        except Exception:
            pass

    print(message)
    print(error_text)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001
        _handle_startup_failure(exc)
        raise SystemExit(1) from exc
