"""
フォルダー進行システム - 安定した次フォルダー移行

フォルダー1014のような処理完了後、自動的に次のフォルダー（1015）を
検索・実行する機能を提供します。
"""

import os
import re
import sys
import time
from typing import List, Optional, Tuple
from logging_util import logger
from utils import get_base_path

class FolderProgressionSystem:
    """フォルダー進行システム"""
    
    @staticmethod
    def find_next_folder(current_folder, folder_path: str = None) -> Optional[str]:
        """次の利用可能なフォルダーを検索
        
        Args:
            current_folder: 現在のフォルダー名（str または int）
            folder_path: 検索対象のパス（bin_pushディレクトリ）
            
        Returns:
            Optional[str]: 次のフォルダー名、見つからない場合はNone
        """
        # フォルダー名を文字列に変換
        current_folder = str(current_folder)
        if folder_path is None:
            # 環境適応機能で複数パスを検索
            possible_paths = [
                os.path.join(get_base_path(), "bin_push"),
                r"C:\Users\santa\mon_c\bin_push",
                r"C:\Users\santa\Desktop\MM\py_base\bin_push",
                r"C:\Users\santa\Desktop\py\bin_push",
                r"C:\Users\santa\Desktop\bin_push",
                "./bin_push",  # EXEと同階層
                os.path.join(os.path.dirname(os.path.abspath(__file__)), "bin_push"),  # スクリプトと同階層
            ]
            
            # EXE実行時の特別なパス検索
            if getattr(sys, 'frozen', False):
                # PyInstallerでパッケージ化されている場合
                exe_dir = os.path.dirname(sys.executable)
                possible_paths.insert(0, os.path.join(exe_dir, "bin_push"))  # 最優先
                logger.info(f"🔍 EXE実行環境検出: {exe_dir}")
            
            logger.info(f"🔍 bin_push検索パス: {len(possible_paths)}個の候補")
            
            for i, path in enumerate(possible_paths):
                logger.info(f"🔍 検索中 [{i+1}/{len(possible_paths)}]: {path}")
                if os.path.exists(path):
                    folder_path = path
                    logger.info(f"✅ bin_pushフォルダ発見: {path}")
                    break
                else:
                    logger.info(f"❌ 存在しません: {path}")
            
            if not folder_path:
                logger.error("❌ bin_pushディレクトリが見つかりません")
                return None
        
        logger.info(f"🔍 次フォルダー検索開始: {current_folder} の次を検索中...")
        logger.info(f"📁 検索対象ディレクトリ: {folder_path}")
        
        try:
            # 現在のフォルダー番号を抽出
            current_num = int(current_folder)
            logger.info(f"📊 現在のフォルダー番号: {current_num}")
            
            # フォルダーリスト取得
            if not os.path.exists(folder_path):
                logger.error(f"❌ 指定されたパスが存在しません: {folder_path}")
                return None
            
            folders = [f for f in os.listdir(folder_path) 
                      if os.path.isdir(os.path.join(folder_path, f))]
            
            logger.info(f"📂 発見されたフォルダー数: {len(folders)}")
            
            # 数値フォルダーのみを抽出・ソート
            numeric_folders = []
            for folder in folders:
                if folder.isdigit():
                    num = int(folder)
                    numeric_folders.append((num, folder))
            
            numeric_folders.sort()  # 数値順でソート
            logger.info(f"📊 数値フォルダー数: {len(numeric_folders)}")
            
            # 現在のフォルダーより大きい最小の番号を検索
            next_candidates = [folder for num, folder in numeric_folders if num > current_num]
            
            if next_candidates:
                next_folder = next_candidates[0]
                
                # フォルダー内にdata10.binがあるか確認
                data_file = os.path.join(folder_path, next_folder, "data10.bin")
                if os.path.exists(data_file):
                    file_size = os.path.getsize(data_file)
                    logger.info(f"✅ 次フォルダー発見: {next_folder}")
                    logger.info(f"📄 data10.bin確認: {file_size:,} bytes")
                    return next_folder
                else:
                    logger.warning(f"⚠️ {next_folder}/data10.binが見つかりません")
            
            # 候補が見つからない場合の詳細ログ
            logger.warning("⚠️ 次のフォルダーが見つかりません")
            logger.info(f"📊 利用可能な数値フォルダー: {[folder for _, folder in numeric_folders]}")
            logger.info(f"📊 現在の番号より大きいフォルダー: {next_candidates}")
            
            return None
            
        except ValueError:
            logger.error(f"❌ フォルダー名が数値ではありません: {current_folder}")
            return None
        except Exception as e:
            logger.error(f"❌ 次フォルダー検索エラー: {e}")
            return None
    
    @staticmethod
    def find_available_folders(folder_path: str = None, start_from: int = None) -> List[str]:
        """利用可能な全フォルダーを検索
        
        Args:
            folder_path: 検索対象のパス
            start_from: 開始番号（指定番号以降のフォルダーを取得）
            
        Returns:
            List[str]: 利用可能なフォルダーのリスト
        """
        if folder_path is None:
            # EXE実行時の特別なパス検索
            if getattr(sys, 'frozen', False):
                exe_dir = os.path.dirname(sys.executable)
                folder_path = os.path.join(exe_dir, "bin_push")
                if os.path.exists(folder_path):
                    logger.info(f"✅ EXE同階層のbin_pushを使用: {folder_path}")
                else:
                    folder_path = None
            
            if folder_path is None:
                folder_path = os.path.join(get_base_path(), "bin_push")
        
        try:
            if not os.path.exists(folder_path):
                logger.error(f"❌ ディレクトリが存在しません: {folder_path}")
                return []
            
            folders = [f for f in os.listdir(folder_path) 
                      if os.path.isdir(os.path.join(folder_path, f))]
            
            # 数値フォルダーのみを抽出・ソート
            valid_folders = []
            for folder in folders:
                if folder.isdigit():
                    num = int(folder)
                    if start_from is None or num >= start_from:
                        # data10.binの存在確認
                        data_file = os.path.join(folder_path, folder, "data10.bin")
                        if os.path.exists(data_file) and os.path.getsize(data_file) > 0:
                            valid_folders.append((num, folder))
            
            valid_folders.sort()  # 数値順でソート
            result = [folder for _, folder in valid_folders]
            
            logger.info(f"📊 利用可能フォルダー数: {len(result)}")
            if result:
                logger.info(f"📁 範囲: {result[0]} - {result[-1]}")
            
            return result
            
        except Exception as e:
            logger.error(f"❌ フォルダー検索エラー: {e}")
            return []
    
    @staticmethod
    def validate_folder(folder_name, folder_path: str = None) -> bool:
        """フォルダーが処理可能か検証
        
        Args:
            folder_name: フォルダー名（str または int）
            folder_path: 検索対象のパス
            
        Returns:
            bool: 処理可能な場合True
        """
        # フォルダー名を文字列に変換
        folder_name = str(folder_name)
        
        if folder_path is None:
            # EXE実行時の特別なパス検索
            if getattr(sys, 'frozen', False):
                exe_dir = os.path.dirname(sys.executable)
                folder_path = os.path.join(exe_dir, "bin_push")
                if os.path.exists(folder_path):
                    logger.info(f"✅ EXE同階層のbin_pushを使用: {folder_path}")
                else:
                    folder_path = None
            
            if folder_path is None:
                folder_path = os.path.join(get_base_path(), "bin_push")
        
        try:
            folder_full_path = os.path.join(folder_path, folder_name)
            
            # フォルダー存在確認
            if not os.path.exists(folder_full_path):
                logger.error(f"❌ フォルダーが存在しません: {folder_full_path}")
                return False
            
            # data10.bin存在確認
            data_file = os.path.join(folder_full_path, "data10.bin")
            if not os.path.exists(data_file):
                logger.error(f"❌ data10.binが見つかりません: {data_file}")
                return False
            
            # ファイルサイズ確認
            file_size = os.path.getsize(data_file)
            if file_size == 0:
                logger.error(f"❌ data10.binが空ファイルです: {data_file}")
                return False
            
            # フォルダー検証成功ログは削除（処理完了時に出力する）
            return True
            
        except Exception as e:
            logger.error(f"❌ フォルダー検証エラー: {e}")
            return False
    
    @staticmethod
    def get_folder_status_summary(folder_path: str = None) -> dict:
        """フォルダー状況の概要を取得
        
        Args:
            folder_path: 検索対象のパス
            
        Returns:
            dict: フォルダー状況の詳細情報
        """
        if folder_path is None:
            # EXE実行時の特別なパス検索
            if getattr(sys, 'frozen', False):
                exe_dir = os.path.dirname(sys.executable)
                folder_path = os.path.join(exe_dir, "bin_push")
                if os.path.exists(folder_path):
                    logger.info(f"✅ EXE同階層のbin_pushを使用: {folder_path}")
                else:
                    folder_path = None
            
            if folder_path is None:
                folder_path = os.path.join(get_base_path(), "bin_push")
        
        try:
            all_folders = FolderProgressionSystem.find_available_folders(folder_path)
            
            summary = {
                "total_folders": len(all_folders),
                "first_folder": all_folders[0] if all_folders else None,
                "last_folder": all_folders[-1] if all_folders else None,
                "folder_list": all_folders[:10],  # 最初の10個
                "folder_path": folder_path,
                "has_more": len(all_folders) > 10
            }
            
            logger.info(f"📊 フォルダー状況概要:")
            logger.info(f"  - 総数: {summary['total_folders']}個")
            if summary['first_folder']:
                logger.info(f"  - 範囲: {summary['first_folder']} - {summary['last_folder']}")
            logger.info(f"  - パス: {summary['folder_path']}")
            
            return summary
            
        except Exception as e:
            logger.error(f"❌ フォルダー状況取得エラー: {e}")
            return {"error": str(e)}

class ContinuousProcessingController:
    """連続処理制御システム"""
    
    def __init__(self):
        self.current_folder = None
        self.completed_folders = []
        self.processing_active = False
    
    def start_continuous_processing(self, start_folder: str = None) -> bool:
        """連続処理を開始
        
        Args:
            start_folder: 開始フォルダー（未指定の場合は最小番号から）
            
        Returns:
            bool: 開始成功かどうか
        """
        try:
            logger.info("🚀 連続処理制御システム開始")
            
            # 開始フォルダーの決定
            if start_folder is None:
                available_folders = FolderProgressionSystem.find_available_folders()
                if not available_folders:
                    logger.error("❌ 処理可能なフォルダーがありません")
                    return False
                start_folder = available_folders[0]
            
            # フォルダー検証
            if not FolderProgressionSystem.validate_folder(start_folder):
                logger.error(f"❌ 開始フォルダーが無効です: {start_folder}")
                return False
            
            self.current_folder = start_folder
            self.processing_active = True
            
            logger.info(f"✅ 連続処理開始: フォルダー {start_folder} から")
            return True
            
        except Exception as e:
            logger.error(f"❌ 連続処理開始エラー: {e}")
            return False
    
    def complete_current_folder(self) -> Optional[str]:
        """現在のフォルダーを完了し、次のフォルダーを取得
        
        Returns:
            Optional[str]: 次のフォルダー名、なければNone
        """
        try:
            if not self.current_folder:
                logger.error("❌ 現在のフォルダーが設定されていません")
                return None
            
            logger.info(f"✅ フォルダー完了: {self.current_folder}")
            self.completed_folders.append(self.current_folder)
            
            # 次のフォルダーを検索
            next_folder = FolderProgressionSystem.find_next_folder(self.current_folder)
            
            if next_folder:
                if FolderProgressionSystem.validate_folder(next_folder):
                    self.current_folder = next_folder
                    logger.info(f"🔄 次のフォルダーに移行: {next_folder}")
                    return next_folder
                else:
                    logger.error(f"❌ 次のフォルダーが無効: {next_folder}")
            
            # 次のフォルダーがない場合
            logger.info("🏁 全ての処理が完了しました")
            self.processing_active = False
            return None
            
        except Exception as e:
            logger.error(f"❌ フォルダー完了処理エラー: {e}")
            return None
    
    def get_progress_status(self) -> dict:
        """進行状況を取得
        
        Returns:
            dict: 進行状況の詳細
        """
        return {
            "current_folder": self.current_folder,
            "completed_count": len(self.completed_folders),
            "completed_folders": self.completed_folders[-5:],  # 最新5個
            "is_active": self.processing_active
        }

# システム統合用の便利関数
def ensure_continuous_processing(current_folder: str) -> Optional[str]:
    """連続処理の継続を保証
    
    Args:
        current_folder: 完了したフォルダー名
        
    Returns:
        Optional[str]: 次のフォルダー名
    """
    try:
        logger.info(f"🔄 連続処理継続チェック: {current_folder} 完了後")
        
        # 次のフォルダーを検索
        next_folder = FolderProgressionSystem.find_next_folder(current_folder)
        
        if next_folder:
            if FolderProgressionSystem.validate_folder(next_folder):
                logger.info(f"✅ 次フォルダー確定: {current_folder} -> {next_folder}")
                return next_folder
            else:
                logger.error(f"❌ 次フォルダーが無効: {next_folder}")
        else:
            logger.info("🏁 全フォルダー処理完了")
        
        return None
        
    except Exception as e:
        logger.error(f"❌ 連続処理継続エラー: {e}")
        return None

if __name__ == "__main__":
    # テスト実行
    print("=== フォルダー進行システム テスト ===")
    
    # 現在のフォルダー状況を確認
    summary = FolderProgressionSystem.get_folder_status_summary()
    print(f"フォルダー総数: {summary.get('total_folders', 0)}")
    
    # 次フォルダー検索テスト
    test_folder = "1014"
    next_folder = FolderProgressionSystem.find_next_folder(test_folder)
    if next_folder:
        print(f"✅ {test_folder} の次: {next_folder}")
    else:
        print(f"❌ {test_folder} の次のフォルダーが見つかりません")