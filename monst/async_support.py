"""
monst.async_support - Asyncio support utilities.

既存の同期コードを将来的にasyncioに移行するための基盤を提供します。
"""

from __future__ import annotations

import asyncio
import functools
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Awaitable, Callable, TypeVar

T = TypeVar('T')
P = TypeVar('P')

class AsyncAdapter:
    """同期関数を非同期で実行するためのアダプター。
    
    Example:
        >>> adapter = AsyncAdapter()
        >>> async def main():
        ...     result = await adapter.run_in_thread(sync_function, arg1, arg2)
        ...     print(result)
    """
    
    def __init__(self, max_workers: int | None = None) -> None:
        """初期化。
        
        Args:
            max_workers: 最大ワーカー数（Noneの場合は自動設定）
        """
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._loop = None
    
    async def run_in_thread(self, func: Callable[..., T], *args: Any, **kwargs: Any) -> T:
        """同期関数をスレッドプールで非同期実行します。
        
        Args:
            func: 実行する同期関数
            *args: 関数の位置引数
            **kwargs: 関数のキーワード引数
            
        Returns:
            関数の実行結果
            
        Example:
            >>> result = await adapter.run_in_thread(blocking_operation, param1, param2)
        """
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            self._executor, 
            functools.partial(func, *args, **kwargs)
        )
    
    def close(self) -> None:
        """エグゼキューターを終了します。"""
        self._executor.shutdown(wait=True)
    
    async def __aenter__(self):
        """非同期コンテキストマネージャー対応。"""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """非同期コンテキストマネージャー対応。"""
        self.close()

def async_wrapper(func: Callable[..., T]) -> Callable[..., Awaitable[T]]:
    """同期関数を非同期関数に変換するデコレーター。
    
    Args:
        func: 変換する同期関数
        
    Returns:
        非同期版の関数
        
    Example:
        >>> @async_wrapper
        ... def sync_function(x, y):
        ...     return x + y
        >>> 
        >>> async def main():
        ...     result = await sync_function(1, 2)
        ...     print(result)  # 3
    """
    @functools.wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> T:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None, 
            functools.partial(func, *args, **kwargs)
        )
    return wrapper

class AsyncBatch:
    """複数の非同期操作をバッチ実行するためのユーティリティ。
    
    Example:
        >>> async with AsyncBatch() as batch:
        ...     batch.add(async_func1, arg1)
        ...     batch.add(async_func2, arg2)
        ...     results = await batch.execute()
    """
    
    def __init__(self, max_concurrent: int = 10) -> None:
        """初期化。
        
        Args:
            max_concurrent: 同時実行数の上限
        """
        self.max_concurrent = max_concurrent
        self._tasks: list[tuple[Callable[..., Awaitable[Any]], tuple, dict]] = []
        self._semaphore: asyncio.Semaphore | None = None
    
    def add(self, coro_func: Callable[..., Awaitable[T]], *args: Any, **kwargs: Any) -> None:
        """バッチに非同期関数を追加します。
        
        Args:
            coro_func: 実行する非同期関数
            *args: 関数の位置引数
            **kwargs: 関数のキーワード引数
        """
        self._tasks.append((coro_func, args, kwargs))
    
    async def execute(self) -> list[Any]:
        """バッチ内の全タスクを実行します。
        
        Returns:
            各タスクの実行結果のリスト
            
        Raises:
            Exception: いずれかのタスクが失敗した場合
        """
        if self._semaphore is None:
            self._semaphore = asyncio.Semaphore(self.max_concurrent)
        
        async def _execute_task(func, args, kwargs):
            async with self._semaphore:
                return await func(*args, **kwargs)
        
        tasks = [
            _execute_task(func, args, kwargs) 
            for func, args, kwargs in self._tasks
        ]
        
        return await asyncio.gather(*tasks)
    
    async def execute_with_timeout(self, timeout: float) -> list[Any]:
        """タイムアウト付きでバッチを実行します。
        
        Args:
            timeout: タイムアウト秒数
            
        Returns:
            各タスクの実行結果のリスト
            
        Raises:
            asyncio.TimeoutError: タイムアウトした場合
        """
        return await asyncio.wait_for(self.execute(), timeout=timeout)
    
    def clear(self) -> None:
        """バッチをクリアします。"""
        self._tasks.clear()
    
    async def __aenter__(self):
        """非同期コンテキストマネージャー対応。"""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """非同期コンテキストマネージャー対応。"""
        self.clear()

# Future async versions of core functions (準備段階)
class AsyncAdbClient:
    """将来的なAsyncio ADB クライアントのプロトタイプ。
    
    Note:
        現在はプレースホルダーです。将来の実装で詳細を追加予定。
    """
    
    def __init__(self, adapter: AsyncAdapter | None = None) -> None:
        self._adapter = adapter or AsyncAdapter()
    
    async def run_command(self, args: list[str], device_port: str | None = None) -> str | None:
        """非同期でADBコマンドを実行します（将来実装予定）。
        
        Args:
            args: ADBコマンド引数
            device_port: デバイスポート
            
        Returns:
            コマンド実行結果
        """
        # 現在は同期版をラップ
        from monst.adb import run_adb_command
        return await self._adapter.run_in_thread(run_adb_command, args, device_port)
    
    async def perform_action(
        self, 
        device_port: str, 
        action: str, 
        x: int, 
        y: int, 
        **kwargs: Any
    ) -> bool:
        """非同期でデバイス操作を実行します（将来実装予定）。
        
        Args:
            device_port: デバイスポート
            action: アクション種類
            x, y: 座標
            **kwargs: その他のオプション
            
        Returns:
            操作成功したかどうか
        """
        # 現在は同期版をラップ
        from monst.adb import perform_action
        return await self._adapter.run_in_thread(perform_action, device_port, action, x, y, **kwargs)

# Example usage patterns for future migration
async def example_async_device_operations():
    """将来の非同期デバイス操作のサンプル実装。
    
    Note:
        これは将来のAPIデザインのサンプルです。
    """
    async with AsyncAdapter() as adapter:
        # 複数デバイスで並列操作
        async with AsyncBatch(max_concurrent=5) as batch:
            for device_port in ["127.0.0.1:62001", "127.0.0.1:62002"]:
                batch.add(adapter.run_in_thread, _mock_device_operation, device_port)
            
            results = await batch.execute_with_timeout(timeout=300.0)
            return results

def _mock_device_operation(device_port: str) -> str:
    """モックデバイス操作（サンプル用）。"""
    return f"Operation completed on {device_port}"