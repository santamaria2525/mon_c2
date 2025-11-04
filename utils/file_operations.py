"""
File operation utilities for Monster Strike Bot

This module handles file operations including:
- File encoding detection
- Multi-line file modifications
- File validation and error handling
"""

import os
from typing import Dict
from logging_util import logger

def detect_encoding(file_path: str) -> str:
    """
    ファイルのエンコーディングを検出（mon6準拠）
    
    Args:
        file_path: ファイルパス
        
    Returns:
        str: 検出されたエンコーディング
    """
    try:
        # まずchardetを使用
        import chardet
        with open(file_path, "rb") as f:
            result = chardet.detect(f.read())
            
        encoding = result.get("encoding")
        
        # None または認識できないエンコーディングの場合はデフォルト値を使用
        if not encoding or encoding.lower() == 'ascii':
            return "utf-8"
            
        return encoding
    except ImportError:
        # chardetが利用できない場合のフォールバック
        encodings_to_try = ['utf-8', 'shift_jis', 'cp932', 'euc-jp', 'iso-2022-jp']
        
        for encoding in encodings_to_try:
            try:
                with open(file_path, "r", encoding=encoding) as f:
                    f.read()
                return encoding
            except UnicodeDecodeError:
                continue
            except Exception:
                continue
    except Exception as e:
        logger.error(f"エンコーディング検出中にエラー: {e}")
    
    return "utf-8"  # デフォルトはUTF-8

def replace_multiple_lines_in_file(file_path: str, changes: Dict[int, str]) -> bool:
    """
    ファイルの複数行を一度に置換（エンコーディングエラー対応版）
    
    Args:
        file_path: ファイルパス
        changes: 行番号と新しいテキストのディクショナリ
        
    Returns:
        bool: 置換成功かどうか
    """
    if not os.path.exists(file_path):
        logger.error(f"ファイルが見つかりません: {file_path}")
        return False

    # 複数回の読み込み・書き込み試行
    max_retries = 3
    for attempt in range(max_retries):
        try:
            # ファイルのエンコーディングを検出
            encoding = detect_encoding(file_path)
            logger.debug(f"試行 {attempt + 1}: エンコーディング {encoding} を使用 (ファイル: {file_path})")
            
            # ファイル読み込み
            with open(file_path, "r", encoding=encoding) as file:
                lines = file.readlines()
                
            if not lines:
                logger.error(f"ファイルが空です: {file_path}")
                return False
                
            # 最大行番号の検証
            max_line = max(changes.keys()) if changes else 0
            if max_line > len(lines):
                logger.error(f"指定した行番号 {max_line} がファイルの行数 {len(lines)} を超えています")
                return False

            # 行を置き換え（行番号は1始まり）
            for line_number, new_text in changes.items():
                if 1 <= line_number <= len(lines):
                    lines[line_number - 1] = new_text + "\n"
                else:
                    logger.error(f"指定した行番号 {line_number} が範囲外です（全 {len(lines)} 行）")
                    return False

            # 変更内容を書き戻し
            with open(file_path, "w", encoding=encoding) as file:
                file.writelines(lines)
                
            return True
            
        except UnicodeDecodeError as e:
            logger.warning(f"エンコーディングエラー (試行 {attempt + 1}): {e}")
            if attempt == max_retries - 1:
                logger.error(f"全ての試行でエンコーディングエラーが発生しました: {file_path}")
                return False
            continue
        except Exception as e:
            logger.error(f"ファイルの書き換え中にエラー (試行 {attempt + 1}): {e}")
            if attempt == max_retries - 1:
                return False
            continue
    
    return False
