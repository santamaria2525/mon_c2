"""
Path management utilities for Monster Strike Bot

This module handles all path-related operations including:
- Base path resolution
- Resource path discovery
- Working directory management
- Log file path generation
"""

import os
import sys
from datetime import datetime
from typing import Optional
from logging_util import logger

def get_base_path() -> str:
    """
    実行ファイルがあるベースパスを取得
    
    Returns:
        str: ベースパス
    """
    if getattr(sys, 'frozen', False):
        # Exeファイルとして実行されている場合
        return os.path.dirname(sys.executable)
    else:
        # スクリプトとして実行されている場合
        return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def set_working_directory() -> None:
    """作業ディレクトリをアプリケーションの基本パスに設定する"""
    base_path = get_base_path()
    os.chdir(base_path)
    logger.debug(f"作業ディレクトリを設定: {base_path}")

def get_resource_path(relative_path: str, *subfolders: str) -> Optional[str]:
    """
    リソースファイルのパスを取得
    
    Args:
        relative_path: リソースの相対パス
        subfolders: サブフォルダ名（可変長引数）
        
    Returns:
        Optional[str]: リソースの絶対パス、見つからない場合はNone
    """
    # 検索するパスのリスト（Windows/Linux両対応）
    search_paths = []
    
    # 1. exeファイルと同じディレクトリ
    base_path = get_base_path()
    if subfolders:
        search_paths.append(os.path.join(base_path, *subfolders, relative_path))
    else:
        search_paths.append(os.path.join(base_path, relative_path))
    
    # 2. PyInstallerでバンドルされたリソース（EXE実行時のみ）
    if hasattr(sys, '_MEIPASS'):
        meipass_path = getattr(sys, '_MEIPASS', '')
        if subfolders:
            search_paths.append(os.path.join(meipass_path, *subfolders, relative_path))
        else:
            search_paths.append(os.path.join(meipass_path, relative_path))
    
    # 3. カレントディレクトリ
    cwd = os.getcwd()
    if subfolders:
        search_paths.append(os.path.join(cwd, *subfolders, relative_path))
    else:
        search_paths.append(os.path.join(cwd, relative_path))
    
    # 4. 親ディレクトリ
    parent_path = os.path.dirname(base_path)
    if subfolders:
        search_paths.append(os.path.join(parent_path, *subfolders, relative_path))
    else:
        search_paths.append(os.path.join(parent_path, relative_path))
    
    # 5. EXE実行時の追加検索パス
    if getattr(sys, 'frozen', False):
        exe_dir = os.path.dirname(sys.executable)
        if subfolders:
            search_paths.append(os.path.join(exe_dir, *subfolders, relative_path))
        else:
            search_paths.append(os.path.join(exe_dir, relative_path))
    
    # 6. 様々なPC環境での可能性のあるパスを検索
    potential_paths = [
        r"C:\Users\santa\mon_c",           # 元の開発環境
        r"C:\Users\santa\Desktop\MM\py_base",  # 別PC環境1
        r"C:\Users\santa\Desktop\py",       # 別PC環境2
        r"C:\Users\santa\Desktop",          # デスクトップ
        r"D:\monster_strike",               # 別ドライブ
        r"E:\monster_strike",               # 別ドライブ
    ]
    
    for potential_path in potential_paths:
        if os.path.exists(potential_path):
            if subfolders:
                search_paths.append(os.path.join(potential_path, *subfolders, relative_path))
            else:
                search_paths.append(os.path.join(potential_path, relative_path))
    
    # 7. 現在の実行ディレクトリの親ディレクトリも検索
    current_exe_dir = get_base_path()
    parent_dirs = []
    temp_path = current_exe_dir
    for _ in range(3):  # 3階層上まで検索
        temp_path = os.path.dirname(temp_path)
        if temp_path and temp_path != os.path.dirname(temp_path):  # ルートに到達しない限り
            parent_dirs.append(temp_path)
    
    for parent_dir in parent_dirs:
        if subfolders:
            search_paths.append(os.path.join(parent_dir, *subfolders, relative_path))
        else:
            search_paths.append(os.path.join(parent_dir, relative_path))
    
    # Noneを除去
    search_paths = [path for path in search_paths if path is not None]
    
    # 存在するパスを返す
    for path in search_paths:
        if path and os.path.exists(path):
            return path
    
    # 見つからない場合はログを出力（重要ファイルのみ）
    if relative_path not in {'config.json', 'log.txt'}:
        logger.warning(f"リソースが見つかりません: {relative_path}")
    
    return None

def get_log_file_path(base_dir: Optional[str] = None, prefix: str = 'log') -> str:
    """
    ログファイルのパスを取得
    
    Args:
        base_dir: ベースディレクトリ
        prefix: ファイル名の接頭辞
        
    Returns:
        str: ログファイルのパス
    """
    if base_dir is None:
        base_dir = get_base_path()
    
    # ログディレクトリの作成
    log_dir = os.path.join(base_dir, 'logs')
    os.makedirs(log_dir, exist_ok=True)
    
    # 日付を含むファイル名の作成
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{prefix}_{timestamp}.txt"
    
    return os.path.join(log_dir, filename)