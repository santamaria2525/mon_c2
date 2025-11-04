"""
monst.adb - ADB utilities for Android device communication.

Public API exports for backward compatibility.
"""

from __future__ import annotations

from .core import (
    run_adb_command,
    perform_action,
    perform_action_enhanced,
    reset_adb_server,
    is_device_available,
    reconnect_device,
    check_adb_server,
)
from .shell import run_adb_shell_command
from .input import send_key_event, press_home_button, press_back_button  
from .files import remove_data10_bin_from_nox, pull_file_from_nox
from .app import (
    close_monster_strike_app,
    start_monster_strike_app, 
    restart_monster_strike_app,
)
from .utils import get_executable_path

# Re-export all functions for backward compatibility
__all__ = [
    "run_adb_command",
    "perform_action", 
    "perform_action_enhanced",
    "reset_adb_server",
    "is_device_available",
    "reconnect_device",
    "check_adb_server",
    "run_adb_shell_command",
    "send_key_event",
    "press_home_button",
    "press_back_button",
    "remove_data10_bin_from_nox",
    "pull_file_from_nox",
    "close_monster_strike_app",
    "start_monster_strike_app",
    "restart_monster_strike_app",
    "get_executable_path",
]