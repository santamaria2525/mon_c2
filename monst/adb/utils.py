"""
monst.adb.utils - Miscellaneous utilities.

その他のユーティリティ関数を提供します。
"""

from __future__ import annotations

import os
import sys

def get_executable_path() -> str:
    """実行ファイルまたはスクリプトのディレクトリパスを返します。
    
    Returns:
        実行中のファイルが存在するディレクトリの絶対パス
        
    Note:
        PyInstallerでパッケージ化された場合とPythonスクリプトとして
        実行された場合の両方に対応します。
    """
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))