"""Operations package facade."""

from __future__ import annotations

import importlib
from types import MappingProxyType
from typing import Any, Iterable, Tuple

_EXPORT_MAP = {
    'OperationsManager': ('app.operations.manager', 'OperationsManager'),
    'run_push': ('app.operations.helpers', 'run_push'),
    'run_loop': ('app.operations.helpers', 'run_loop'),
    'run_loop_enhanced': ('app.operations.helpers', 'run_loop_enhanced'),
    'remove_all_nox': ('app.operations.helpers', 'remove_all_nox'),
    'run_in_threads': ('app.operations.helpers', 'run_in_threads'),
    'log_folder_result': ('app.operations.helpers', 'log_folder_result'),
    'debug_log': ('app.operations.helpers', 'debug_log'),
    'find_and_click_with_protection': ('app.operations.helpers', 'find_and_click_with_protection'),
    'write_account_folders': ('app.operations.helpers', 'write_account_folders'),
}

__all__ = tuple(_EXPORT_MAP.keys())
_EXPORT_MAP = MappingProxyType(_EXPORT_MAP)


def __getattr__(name: str) -> Any:
    if name not in _EXPORT_MAP:
        raise AttributeError(f"module 'app.operations' has no attribute '{name}'")
    module_name, attr_name = _EXPORT_MAP[name]
    module = importlib.import_module(module_name)
    value = getattr(module, attr_name)
    globals()[name] = value
    return value


def __dir__() -> Iterable[str]:
    return sorted(set(globals().keys()) | set(__all__))
