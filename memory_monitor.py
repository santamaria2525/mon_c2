"""
memory_monitor.py - システムメモリ監視機能

ログ分析に基づく、メモリ枯渇エラー防止システム
"""

import gc
import psutil
import threading
import time
from typing import Dict, Optional

from logging_util import logger

class MemoryMonitor:
    """システムメモリ監視クラス"""
    
    def __init__(self, check_interval: int = 300):  # 5分間隔に変更
        self.check_interval = check_interval
        self.is_running = False
        self.monitor_thread: Optional[threading.Thread] = None
        self.memory_history: Dict[str, float] = {}
        self.warning_threshold = 92.0  # 92%使用で警告（緩和）
        self.critical_threshold = 97.0  # 97%使用で緊急処理（緩和）
        self.extreme_threshold = 99.0  # 99%使用で極限モード（緩和）
        self.consecutive_critical_count = 0  # 連続クリティカル回数
        self.cleanup_aggressive_mode = False  # 積極的クリーンアップモード
        self.silent_mode = True  # メモリ警告ログを抑制
        
    def start_monitoring(self):
        """メモリ監視を開始"""
        if self.is_running:
            return
            
        self.is_running = True
        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()
        
    def stop_monitoring(self):
        """メモリ監視を停止"""
        self.is_running = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=5)
        logger.info("メモリ監視を停止しました")
        
    def _monitor_loop(self):
        """メモリ監視メインループ"""
        while self.is_running:
            try:
                # メモリ使用率チェック
                memory_percent = psutil.virtual_memory().percent
                available_mb = psutil.virtual_memory().available / (1024 * 1024)
                
                # 履歴記録
                current_time = time.strftime("%H:%M:%S")
                self.memory_history[current_time] = memory_percent
                
                # 警告レベルチェック（サイレントモード）
                if memory_percent >= self.extreme_threshold:
                    if not self.silent_mode:
                        logger.error(f"🔥 極限: メモリ使用率 {memory_percent:.1f}% (利用可能: {available_mb:.0f}MB)")
                    self._extreme_cleanup()
                    self.consecutive_critical_count += 1
                elif memory_percent >= self.critical_threshold:
                    if not self.silent_mode:
                        logger.error(f"⚠️ 緊急: メモリ使用率 {memory_percent:.1f}% (利用可能: {available_mb:.0f}MB)")
                    self._emergency_cleanup()
                    self.consecutive_critical_count += 1
                elif memory_percent >= self.warning_threshold:
                    self._proactive_cleanup()
                    self.consecutive_critical_count = 0
                else:
                    self.consecutive_critical_count = 0
                    self.cleanup_aggressive_mode = False
                
                # 連続クリティカル状態の対応（サイレント）
                if self.consecutive_critical_count >= 3:
                    self.cleanup_aggressive_mode = True
                    # 積極モード有効時もログを抑制
                
                # 古い履歴を削除（最新10件のみ保持）
                if len(self.memory_history) > 10:
                    oldest_key = min(self.memory_history.keys())
                    del self.memory_history[oldest_key]
                    
            except Exception as e:
                logger.error(f"メモリ監視エラー: {e}")
                
            time.sleep(self.check_interval)
            
    def _proactive_cleanup(self):
        """予防的メモリクリーンアップ"""
        try:
            # ガベージコレクション実行
            collected = gc.collect()
            
            # 積極モードの場合はより強力なクリーンアップ
            cache_threshold = 5 if self.cleanup_aggressive_mode else 10
            
            # 画像キャッシュクリア（必要に応じて）
            from monst.image.core import _last_screenshot, _last_screenshot_time, _screenshot_lock
            with _screenshot_lock:
                # 古いキャッシュのみクリア
                current_time = time.time()
                expired_devices = []
                for device, last_time in _last_screenshot_time.items():
                    if current_time - last_time > cache_threshold:
                        expired_devices.append(device)
                
                for device in expired_devices:
                    if device in _last_screenshot:
                        del _last_screenshot[device]
                    if device in _last_screenshot_time:
                        del _last_screenshot_time[device]
                    
        except Exception as e:
            logger.error(f"予防的メモリクリーンアップエラー: {e}")
            
    def _emergency_cleanup(self):
        """緊急メモリクリーンアップ（サイレント）"""
        try:
            # ログ出力を抑制
            
            # 画像キャッシュ全クリア
            from monst.image.core import _last_screenshot, _last_screenshot_time, _screenshot_lock
            with _screenshot_lock:
                cache_count = len(_last_screenshot)
                _last_screenshot.clear()
                _last_screenshot_time.clear()
                logger.info(f"画像キャッシュ全削除: {cache_count}エントリ")
            
            # 強制ガベージコレクション（全世代）
            collected = 0
            for generation in range(3):
                collected += gc.collect(generation)
            logger.info(f"強制ガベージコレクション実行: {collected}オブジェクト回収")
            
            # メモリ使用量再確認
            time.sleep(2)
            new_memory_percent = psutil.virtual_memory().percent
            logger.info(f"クリーンアップ後メモリ使用率: {new_memory_percent:.1f}%")
            
        except Exception as e:
            logger.error(f"緊急メモリクリーンアップエラー: {e}")
            
    def _extreme_cleanup(self):
        """極限メモリクリーンアップ - 処理継続を最優先（サイレント）"""
        try:
            # ログ出力を抑制
            
            # 即座に画像キャッシュ全クリア
            from monst.image.core import _last_screenshot, _last_screenshot_time, _screenshot_lock
            with _screenshot_lock:
                cache_count = len(_last_screenshot)
                _last_screenshot.clear()
                _last_screenshot_time.clear()
                logger.info(f"🧹 全画像キャッシュ強制削除: {cache_count}エントリ")
            
            # 全世代ガベージコレクション（複数回実行）
            total_collected = 0
            for i in range(3):  # 3回実行
                for generation in range(3):
                    total_collected += gc.collect(generation)
                time.sleep(0.1)  # 短い待機
            
            logger.info(f"🔄 極限ガベージコレクション: {total_collected}オブジェクト回収")
            
            # 強制メモリ圧縮（可能な限り）
            import ctypes
            if hasattr(ctypes, 'windll'):
                try:
                    ctypes.windll.kernel32.SetProcessWorkingSetSize(-1, -1, -1)
                    logger.info("💾 Windows メモリ圧縮実行")
                except:
                    pass
            
            # 短時間待機後にメモリ状況確認
            time.sleep(1)
            new_memory_percent = psutil.virtual_memory().percent
            # クリーンアップ後ログを抑制
            
            # まだ高い場合は監視間隔を短縮（ログ抑制）
            if new_memory_percent >= 97.0:  # 閾値を緩和
                self.check_interval = 120  # 2分間隔
            else:
                self.check_interval = 300  # 通常に戻す（5分）
                
        except Exception as e:
            logger.error(f"極限メモリクリーンアップエラー: {e}")
            
    def get_memory_status(self) -> Dict:
        """現在のメモリ状況を取得"""
        try:
            memory = psutil.virtual_memory()
            return {
                "percent": memory.percent,
                "available_mb": memory.available / (1024 * 1024),
                "total_mb": memory.total / (1024 * 1024),
                "used_mb": memory.used / (1024 * 1024),
                "history": self.memory_history.copy()
            }
        except Exception as e:
            logger.error(f"メモリ状況取得エラー: {e}")
            return {}

# グローバルインスタンス
memory_monitor = MemoryMonitor()

def start_memory_monitoring():
    """メモリ監視開始"""
    memory_monitor.start_monitoring()

def stop_memory_monitoring():
    """メモリ監視停止"""
    memory_monitor.stop_monitoring()

def get_memory_status():
    """メモリ状況取得"""
    return memory_monitor.get_memory_status()

def force_cleanup():
    """強制メモリクリーンアップ"""
    memory_monitor._emergency_cleanup()