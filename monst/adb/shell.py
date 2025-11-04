"""
monst.adb.shell - ADB shell command utilities.

シェルコマンド実行のヘルパー関数を提供します。
"""

from __future__ import annotations

from typing import Optional

from .core import run_adb_command, _DEFAULT_TIMEOUT

def run_adb_shell_command(
    command: str, 
    device_port: str, 
    timeout: int = _DEFAULT_TIMEOUT
) -> Optional[str]:
    """ADBシェルコマンドを実行し、結果を返します。
    
    Args:
        command: 実行するシェルコマンド文字列
        device_port: 対象デバイスのポート
        timeout: タイムアウト秒数
        
    Returns:
        成功時は標準出力、失敗時はNone
        
    Example:
        >>> run_adb_shell_command("ls /data/data", "127.0.0.1:62001")
        "com.android.providers.settings\\ncom.android.shell\\n..."
    """
    # 文字列を分割してコマンド引数リストに変換
    if isinstance(command, str):
        cmd = command.split()
    else:
        cmd = list(command)
    return run_adb_command(["shell", *cmd], device_port, timeout)