"""
loop_protection.py - 無限ループ防止と段階的バックステップ機能

30回以上の繰り返し防止と、段階的な処理後退機能を提供します。
"""

from __future__ import annotations

import time
from typing import Dict, List, Optional, Callable, Any, Tuple
from dataclasses import dataclass
from logging_util import logger

@dataclass
class ProcessingState:
    """処理状態の追跡情報"""
    operation_name: str
    current_folder: int
    attempt_count: int
    last_attempt_time: float
    failure_reasons: List[str]
    backtrack_level: int  # バックトラック レベル（何段階戻ったか）

class LoopProtectionManager:
    """無限ループ防止と段階的バックステップ管理"""
    
    def __init__(self, max_attempts: int = 100, backtrack_limit: int = 3):
        self.max_attempts = max_attempts
        self.backtrack_limit = backtrack_limit
        self.processing_states: Dict[str, ProcessingState] = {}
        self.operation_history: List[Tuple[str, int, float]] = []  # (operation, folder, timestamp)
        
    def register_attempt(self, operation_name: str, folder: int, failure_reason: str = None) -> bool:
        """
        処理試行を登録し、継続可能かを判定
        
        Returns:
            True: 継続可能, False: 停止すべき
        """
        current_time = time.time()
        state_key = f"{operation_name}_{folder}"
        
        # 履歴に追加
        self.operation_history.append((operation_name, folder, current_time))
        
        # 状態の取得または作成
        if state_key not in self.processing_states:
            self.processing_states[state_key] = ProcessingState(
                operation_name=operation_name,
                current_folder=folder,
                attempt_count=1,
                last_attempt_time=current_time,
                failure_reasons=[],
                backtrack_level=0
            )
        else:
            state = self.processing_states[state_key]
            state.attempt_count += 1
            state.last_attempt_time = current_time
            if failure_reason:
                state.failure_reasons.append(failure_reason)
        
        state = self.processing_states[state_key]
        
        # 最大試行回数チェック
        if state.attempt_count >= self.max_attempts:
            logger.warning(f"🚨 {operation_name} フォルダ{folder}: {self.max_attempts}回試行 → バックステップ実行")
            return False
            
        # 警告レベル（50回以上）
        if state.attempt_count >= 50:
            logger.warning(f"⚠️ {operation_name} フォルダ{folder}: {state.attempt_count}回試行中")
            
        return True
    
    def should_backtrack(self, operation_name: str, folder: int) -> bool:
        """バックトラックが必要かチェック"""
        state_key = f"{operation_name}_{folder}"
        if state_key in self.processing_states:
            state = self.processing_states[state_key]
            return state.attempt_count >= self.max_attempts and state.backtrack_level < self.backtrack_limit
        return False
    
    def execute_backtrack(self, operation_name: str, current_folder: int) -> Optional[int]:
        """
        段階的バックステップを実行
        
        Returns:
            バックトラック後のフォルダ番号（None = バックトラック不可）
        """
        state_key = f"{operation_name}_{current_folder}"
        if state_key not in self.processing_states:
            return None
            
        state = self.processing_states[state_key]
        if state.backtrack_level >= self.backtrack_limit:
            logger.error(f"❌ {operation_name}: バックトラック限界到達（{self.backtrack_limit}段階）")
            return None
            
        # バックトラック実行
        state.backtrack_level += 1
        backtrack_folder = max(1, current_folder - state.backtrack_level)
        
        logger.warning(f"🔄 バックステップ実行: {operation_name}")
        logger.warning(f"   フォルダ {current_folder} → {backtrack_folder} (第{state.backtrack_level}段階)")
        logger.warning(f"   失敗回数: {state.attempt_count}回")
        if state.failure_reasons:
            logger.warning(f"   失敗理由: {', '.join(state.failure_reasons[-3:])}")  # 最新3件
            
        # 新しいフォルダの状態をリセット
        new_state_key = f"{operation_name}_{backtrack_folder}"
        if new_state_key in self.processing_states:
            del self.processing_states[new_state_key]
            
        return backtrack_folder
    
    def reset_operation(self, operation_name: str, folder: int):
        """特定の操作・フォルダの状態をリセット"""
        state_key = f"{operation_name}_{folder}"
        if state_key in self.processing_states:
            del self.processing_states[state_key]
            logger.info(f"🔄 {operation_name} フォルダ{folder}: 状態リセット")
    
    def get_stats(self) -> Dict[str, Any]:
        """統計情報を取得"""
        total_attempts = sum(state.attempt_count for state in self.processing_states.values())
        problem_operations = [
            (key, state.attempt_count) 
            for key, state in self.processing_states.items() 
            if state.attempt_count >= 10
        ]
        
        return {
            "total_operations": len(self.processing_states),
            "total_attempts": total_attempts,
            "problem_operations": problem_operations,
            "history_size": len(self.operation_history)
        }
    
    def cleanup_old_states(self, max_age_hours: int = 24):
        """古い状態をクリーンアップ"""
        current_time = time.time()
        cutoff_time = current_time - (max_age_hours * 3600)
        
        # 古い履歴を削除
        self.operation_history = [
            (op, folder, ts) for op, folder, ts in self.operation_history 
            if ts > cutoff_time
        ]
        
        # 古い状態を削除
        old_keys = [
            key for key, state in self.processing_states.items()
            if state.last_attempt_time < cutoff_time
        ]
        
        for key in old_keys:
            del self.processing_states[key]
            
        if old_keys:
            logger.info(f"🧹 古い処理状態をクリーンアップ: {len(old_keys)}件")

# グローバルインスタンス
loop_protection = LoopProtectionManager()

def protected_operation_wrapper(
    operation: Callable,
    operation_name: str, 
    folder: int,
    *args,
    **kwargs
) -> Tuple[Any, bool]:
    """
    保護された操作ラッパー
    
    Returns:
        (operation_result, should_continue)
    """
    try:
        # 試行回数チェック
        if not loop_protection.register_attempt(operation_name, folder):
            # バックトラックが必要
            if loop_protection.should_backtrack(operation_name, folder):
                new_folder = loop_protection.execute_backtrack(operation_name, folder)
                if new_folder is not None:
                    logger.info(f"🔄 バックステップ後に再試行: フォルダ{new_folder}")
                    return protected_operation_wrapper(operation, operation_name, new_folder, *args, **kwargs)
            
            logger.error(f"❌ {operation_name}: 処理限界到達 - 停止します")
            return None, False
        
        # 実際の操作実行
        result = operation(folder, *args, **kwargs)
        
        # 成功時は状態リセット
        loop_protection.reset_operation(operation_name, folder)
        return result, True
        
    except Exception as e:
        # 失敗を記録
        failure_reason = str(e)
        loop_protection.register_attempt(operation_name, folder, failure_reason)
        logger.error(f"❌ {operation_name} フォルダ{folder}: {failure_reason}")
        raise