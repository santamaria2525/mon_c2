"""
utils.clipboard_manager - クリップボード操作の排他制御マネージャー

マルチ端末同時実行時のクリップボード競合を防ぐための
排他制御とタイミング調整機能を提供します。
"""

from __future__ import annotations

import threading
import time
import random
from typing import Optional, Dict
import pyperclip
from logging_util import logger

class ClipboardManager:
    """クリップボード操作の排他制御マネージャー"""
    
    def __init__(self):
        self._lock = threading.RLock()  # 再帰可能ロック
        self._device_delays: Dict[str, float] = {}  # 端末ごとの遅延時間
        
    def register_device(self, device_port: str, base_delay: float = 0.0) -> None:
        """端末を登録し、個別の遅延時間を設定
        
        Args:
            device_port: デバイスポート
            base_delay: 基本遅延時間（秒）
        """
        with self._lock:
            # 端末ごとに異なる遅延時間を設定（0.5～3.0秒の範囲でランダム）
            individual_delay = base_delay + random.uniform(0.5, 3.0)
            self._device_delays[device_port] = individual_delay
            logger.info(f"📋 クリップボード管理: {device_port} の遅延時間 {individual_delay:.1f}秒")
    
    def copy_with_exclusive_access(self, device_port: str, copy_action_func, 
                                 max_retries: int = 3) -> Optional[str]:
        """排他制御付きでクリップボードコピーを実行
        
        Args:
            device_port: デバイスポート
            copy_action_func: コピー操作を実行する関数
            max_retries: 最大リトライ回数
            
        Returns:
            コピーされたテキスト（失敗時はNone）
        """
        with self._lock:  # 全体を排他制御
            try:
                # 端末固有の遅延を適用
                delay = self._device_delays.get(device_port, 1.0)
                logger.info(f"📋 {device_port}: クリップボード操作開始 (遅延: {delay:.1f}秒)")
                time.sleep(delay)
                
                for attempt in range(max_retries):
                    try:
                        # クリップボードをクリア
                        pyperclip.copy("")
                        time.sleep(0.2)
                        
                        # コピー操作を実行
                        logger.info(f"📋 {device_port}: コピー操作実行 (試行 {attempt + 1}/{max_retries})")
                        success = copy_action_func()
                        
                        if not success:
                            logger.warning(f"📋 {device_port}: コピー操作が失敗しました")
                            if attempt < max_retries - 1:
                                time.sleep(1.0)  # リトライ前に待機
                            continue
                        
                        # コピー完了を待機
                        time.sleep(2.0)
                        
                        # クリップボードから内容を取得
                        copied_text = pyperclip.paste()
                        
                        # 内容を検証
                        if copied_text and copied_text.strip():
                            # 数字のみを抽出
                            extracted_id = ''.join(filter(str.isdigit, copied_text))
                            
                            if extracted_id and len(extracted_id) >= 8:  # 最低8桁の数字
                                logger.info(f"📋 {device_port}: ID取得成功 [{extracted_id}]")
                                return extracted_id
                            else:
                                logger.warning(f"📋 {device_port}: 無効なID形式 [{copied_text}]")
                        else:
                            logger.warning(f"📋 {device_port}: クリップボードが空です")
                        
                        if attempt < max_retries - 1:
                            logger.info(f"📋 {device_port}: リトライします ({attempt + 2}/{max_retries})")
                            time.sleep(2.0)  # リトライ前に待機
                            
                    except Exception as e:
                        logger.error(f"📋 {device_port}: クリップボード操作エラー (試行 {attempt + 1}): {e}")
                        if attempt < max_retries - 1:
                            time.sleep(2.0)
                
                logger.error(f"📋 {device_port}: 全ての試行が失敗しました")
                return None
                
            except Exception as e:
                logger.error(f"📋 {device_port}: 排他制御エラー: {e}")
                return None
            finally:
                # 処理完了後の待機（他の端末との干渉を防ぐ）
                time.sleep(0.5)
    
    def get_device_delay(self, device_port: str) -> float:
        """端末の遅延時間を取得"""
        return self._device_delays.get(device_port, 1.0)

# グローバルインスタンス
_clipboard_manager: Optional[ClipboardManager] = None

def get_clipboard_manager() -> ClipboardManager:
    """クリップボードマネージャーのシングルトンインスタンスを取得"""
    global _clipboard_manager
    if _clipboard_manager is None:
        _clipboard_manager = ClipboardManager()
    return _clipboard_manager

def register_device_for_clipboard(device_port: str, device_index: int = 0) -> None:
    """端末をクリップボードマネージャーに登録
    
    Args:
        device_port: デバイスポート
        device_index: 端末のインデックス（0から開始）
    """
    manager = get_clipboard_manager()
    # インデックスに基づいて基本遅延時間を設定（0秒、1秒、2秒...）
    base_delay = device_index * 1.0
    manager.register_device(device_port, base_delay)

def copy_id_with_exclusive_access(device_port: str, copy_action_func) -> Optional[str]:
    """排他制御付きでIDをコピー
    
    Args:
        device_port: デバイスポート
        copy_action_func: コピー操作を実行する関数
        
    Returns:
        コピーされたID（失敗時はNone）
    """
    manager = get_clipboard_manager()
    return manager.copy_with_exclusive_access(device_port, copy_action_func)