"""
Utils package facade with lazy attribute loading.

Only the symbols defined in ``__all__`` are exposed, and each symbol is
imported on first use to avoid circular-import issues and reduce import cost.
"""

from __future__ import annotations

import importlib
from types import MappingProxyType
from typing import Any, Dict, Iterable, Tuple

_EXPORT_MAP: Dict[str, Tuple[str, str]] = {
    'get_base_path': ('utils.path_manager', 'get_base_path'),
    'set_working_directory': ('utils.path_manager', 'set_working_directory'),
    'get_resource_path': ('utils.path_manager', 'get_resource_path'),
    'get_log_file_path': ('utils.path_manager', 'get_log_file_path'),
    'update_csv_data': ('utils.data_persistence', 'update_csv_data'),
    'read_csv_data': ('utils.data_persistence', 'read_csv_data'),
    'update_excel_data': ('utils.data_persistence', 'update_excel_data'),
    'display_message': ('utils.gui_dialogs', 'display_message'),
    'get_target_folder': ('utils.gui_dialogs', 'get_target_folder'),
    'get_name_prefix': ('utils.gui_dialogs', 'get_name_prefix'),
    'select_device_port': ('utils.gui_dialogs', 'select_device_port'),
    'gui_run': ('utils.gui_dialogs', 'gui_run'),
    'handle_windows': ('utils.window_manager', 'handle_windows'),
    'set_console_window_size_and_position': ('utils.window_manager', 'set_console_window_size_and_position'),
    'activate_window_and_right_click': ('utils.window_manager', 'activate_window_and_right_click'),
    'close_windows_by_title': ('utils.window_manager', 'close_windows_by_title'),
    'close_nox_error_dialogs': ('utils.window_manager', 'close_nox_error_dialogs'),
    'close_adb_error_dialogs': ('utils.window_manager', 'close_adb_error_dialogs'),
    'start_error_dialog_monitor': ('utils.window_manager', 'start_error_dialog_monitor'),
    'stop_error_dialog_monitor': ('utils.window_manager', 'stop_error_dialog_monitor'),
    'start_watchdog_heartbeat': ('utils.watchdog', 'start_watchdog_heartbeat'),
    'stop_watchdog_heartbeat': ('utils.watchdog', 'stop_watchdog_heartbeat'),
    'multi_press': ('utils.input_automation', 'multi_press'),
    'send_notification_email': ('utils.email_notifications', 'send_notification_email'),
    'reset_email_rate_limit': ('utils.email_notifications', 'reset_email_rate_limit'),
    'get_email_status': ('utils.email_notifications', 'get_email_status'),
    'detect_encoding': ('utils.file_operations', 'detect_encoding'),
    'replace_multiple_lines_in_file': ('utils.file_operations', 'replace_multiple_lines_in_file'),
    'create_mm_folders': ('utils.mm_folder_manager', 'create_mm_folders'),
    'get_mm_folder_status': ('utils.mm_folder_manager', 'get_mm_folder_status'),
    'clean_mm_folders': ('utils.mm_folder_manager', 'clean_mm_folders'),
    'batch_rename_folders_csv': ('utils.mm_folder_manager', 'batch_rename_folders_csv'),
    'batch_rename_folders_excel': ('utils.mm_folder_manager', 'batch_rename_folders_excel'),
    'MMFolderManager': ('utils.mm_folder_manager', 'MMFolderManager'),
    'run_set_based_loop': ('utils.set_processing', 'run_set_based_loop'),
    'show_continue_dialog': ('utils.set_processing', 'show_continue_dialog'),
    'find_next_set_folders': ('utils.set_processing', 'find_next_set_folders'),
    'process_set_sequential': ('utils.set_processing', 'process_set_sequential'),
    'check_circular_imports': ('utils.circular_import_checker', 'check_circular_imports'),
    'CircularImportChecker': ('utils.circular_import_checker', 'CircularImportChecker'),
}

__all__ = tuple(_EXPORT_MAP.keys())
_EXPORT_MAP = MappingProxyType(_EXPORT_MAP)


def _load_attribute(name: str) -> Any:
    module_name, attr_name = _EXPORT_MAP[name]
    module = importlib.import_module(module_name)
    value = getattr(module, attr_name)
    globals()[name] = value
    return value


def __getattr__(name: str) -> Any:
    if name not in _EXPORT_MAP:
        raise AttributeError(f"module 'utils' has no attribute '{name}'")
    return _load_attribute(name)


def __dir__() -> Iterable[str]:
    return sorted(set(globals().keys()) | set(__all__))
