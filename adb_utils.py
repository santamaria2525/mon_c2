"""
adb_utils.py - Backward compatibility layer for monst.adb package.

このファイルは既存コードとの互換性を保つためのエイリアスレイヤーです。
新しいコードでは monst.adb パッケージを直接使用することを推奨します。

Migration path:
  from adb_utils import run_adb_command
  ↓
  from monst.adb import run_adb_command
"""

from __future__ import annotations

import warnings

# 新しいパッケージから全ての公開関数をインポート
from monst.adb import (
    run_adb_command,
    perform_action,
    reset_adb_server,
    is_device_available,
    reconnect_device,
    check_adb_server,
    run_adb_shell_command,
    send_key_event,
    press_home_button,
    press_back_button,
    remove_data10_bin_from_nox,
    pull_file_from_nox,
    close_monster_strike_app,
    start_monster_strike_app,
    restart_monster_strike_app,
    get_executable_path,
)

# 定数も再エクスポート
from monst.adb.core import APP_PACKAGE, APP_ACTIVITY

# 廃止予定の警告（最初の呼び出し時のみ）
_deprecation_warned = False

def _warn_deprecation():
    global _deprecation_warned
    if not _deprecation_warned:
        warnings.warn(
            "adb_utils.py is deprecated. Use 'from monst.adb import ...' instead.",
            DeprecationWarning,
            stacklevel=3
        )
        _deprecation_warned = True

# 主要な関数にラッパーを追加（将来的な廃止準備）
_original_run_adb_command = run_adb_command

def run_adb_command(*args, **kwargs):
    _warn_deprecation()
    return _original_run_adb_command(*args, **kwargs)

# その他の主要関数も同様に
_original_perform_action = perform_action

def perform_action(*args, **kwargs):
    _warn_deprecation()
    return _original_perform_action(*args, **kwargs)