"""
monst.image.utils - Image path utilities and helper functions.

画像パス取得とヘルパー関数を提供します。
"""

from __future__ import annotations

import os
import sys

from logging_util import logger

LOG_IMAGE_DISCOVERY = False

def get_image_path(image_name: str, *subfolders: str) -> str:
    """画像ファイルのパスを取得します。
    
    Args:
        image_name: 画像ファイル名
        subfolders: サブフォルダ名（可変長引数）
        
    Returns:
        画像ファイルの絶対パス
        
    Example:
        >>> path = get_image_path("ok.png", "ui")
        >>> print(path)  # /path/to/gazo/ui/ok.png (新構造)
    """
    # パスマッピングを適用
    from gazo_path_mapping import get_mapped_path, get_legacy_folder_mapping
    
    if getattr(sys, 'frozen', False):
        # EXE 実行時: `gazo` フォルダは EXE と同じディレクトリにある
        base_path = os.path.dirname(sys.executable)
    else:
        # Python スクリプト実行時: `gazo` フォルダはスクリプトと同じディレクトリ
        base_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    # 旧パス形式を新パス形式にマッピング
    if subfolders:
        old_path = "/".join(subfolders) + "/" + image_name
        mapped_path = get_mapped_path(old_path)
        
        if mapped_path != old_path:
            # マッピングが見つかった場合、新しいパスを使用
            path_parts = mapped_path.split("/")
            image_path = os.path.join(base_path, "gazo", *path_parts)
        else:
            # マッピングが見つからない場合、フォルダ名のマッピングを試行
            mapped_folders = [get_legacy_folder_mapping(folder) for folder in subfolders]
            image_path = os.path.join(base_path, "gazo", *mapped_folders, image_name)
    else:
        # サブフォルダが指定されていない場合
        image_path = os.path.join(base_path, "gazo", image_name)

    # ファイルの存在確認と代替パス検索
    if not os.path.exists(image_path):
        # 新構造での検索を試行（売却フォルダを優先）
        alternative_folders = ["sell", "ui", "login", "gacha", "quest", "mission", "medal", "event", "macro", "icons"]
        for folder in alternative_folders:
            alt_path = os.path.join(base_path, "gazo", folder, image_name)
            if os.path.exists(alt_path):
                if LOG_IMAGE_DISCOVERY:
                    logger.debug(f"画像ファイルを新しい場所で発見: {alt_path}")
                return alt_path
        
        if image_name.lower() != "koshin.png":
            logger.error(f"[ERROR] 画像ファイルが見つかりません: {image_path}")

    return image_path

def get_image_path_for_windows(image_name: str, *subfolders: str) -> str:
    """Windows画面用の画像ファイルのパスを取得します。
    
    Args:
        image_name: 画像ファイル名
        subfolders: サブフォルダ名（可変長引数）
        
    Returns:
        画像ファイルの絶対パス
        
    Example:
        >>> path = get_image_path_for_windows("button.png", "ui", "main")
        >>> print(path)  # /path/to/gazo/ui/main/button.png
    """
    # パスマッピングを適用
    from gazo_path_mapping import get_mapped_path, get_legacy_folder_mapping
    
    if getattr(sys, 'frozen', False):
        base_path = os.path.dirname(sys.executable)
    else:
        base_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    # 旧パス形式を新パス形式にマッピング
    if subfolders:
        old_path = "/".join(subfolders) + "/" + image_name
        mapped_path = get_mapped_path(old_path)
        
        if mapped_path != old_path:
            # マッピングが見つかった場合、新しいパスを使用
            path_parts = mapped_path.split("/")
            image_path = os.path.join(base_path, "gazo", *path_parts)
        else:
            # マッピングが見つからない場合、フォルダ名のマッピングを試行
            mapped_folders = [get_legacy_folder_mapping(folder) for folder in subfolders]
            image_path = os.path.join(base_path, "gazo", *mapped_folders, image_name)
    else:
        # サブフォルダが指定されていない場合
        image_path = os.path.join(base_path, "gazo", image_name)

    # ファイルの存在確認と代替パス検索
    if not os.path.exists(image_path):
        # 新構造での検索を試行（売却フォルダを優先）
        alternative_folders = ["sell", "ui", "login", "gacha", "quest", "mission", "medal", "event", "macro", "icons"]
        for folder in alternative_folders:
            alt_path = os.path.join(base_path, "gazo", folder, image_name)
            if os.path.exists(alt_path):
                if LOG_IMAGE_DISCOVERY:
                    logger.debug(f"Windows画像ファイルを新しい場所で発見: {alt_path}")
                return alt_path
        
        if image_name.lower() != "koshin.png":
            logger.warning(f"[WARNING] 画像ファイルが存在しません: {image_path}")
    
    return image_path
