"""
tools.monitoring.task_monitor_v2 - 完全に新しいタスクモニター実装

メインスレッドで動作し、Windows APIを使用して確実に表示される
シンプルで堅牢なタスクモニターです。
"""

from __future__ import annotations

import threading
import time
import tkinter as tk
from tkinter import ttk
from typing import Dict, Optional, List
import sys
import os
import ctypes
import ctypes.wintypes
from logging_util import logger

class SuperTaskMonitor:
    """完全に新しい超確実なタスクモニター"""
    
    def __init__(self):
        self._window: Optional[tk.Tk] = None
        self._labels: Dict[str, tk.Label] = {}
        self._tasks: Dict[str, str] = {}  
        self._lock = threading.Lock()
        self._running = False
        self._device_ports: List[str] = []
        self._hwnd: Optional[int] = None
        
    def start_monitor(self, device_ports: List[str]) -> None:
        """タスクモニターを開始（メインスレッドで実行）"""
        if self._running:
            print("🖥️ タスクモニターは既に実行中です")
            return
            
        print(f"🖥️ SuperTaskMonitor開始: {len(device_ports)}端末")
        logger.info(f"🖥️ SuperTaskMonitor開始: {len(device_ports)}端末")
        
        self._running = True
        self._device_ports = device_ports.copy()
        
        # 初期化
        with self._lock:
            self._tasks = {port: "---:待機中" for port in device_ports}
        
        # メインスレッドで直接GUI作成
        try:
            self._create_window_now()
        except Exception as e:
            print(f"🖥️ GUI作成エラー: {e}")
            logger.error(f"🖥️ GUI作成エラー: {e}", exc_info=True)
    
    def _create_window_now(self) -> None:
        """今すぐメインスレッドでウィンドウを作成"""
        print("🖥️ ウィンドウ作成開始...")
        
        # tkinterウィンドウを作成
        self._window = tk.Tk()
        self._window.title("【実行中タスク】- SuperMonitor")
        
        # ウィンドウサイズ（非常に大きく）
        window_width = 600
        window_height = 200 + len(self._device_ports) * 50
        
        # 画面中央に配置
        screen_width = self._window.winfo_screenwidth()
        screen_height = self._window.winfo_screenheight()
        x = (screen_width - window_width) // 2
        y = (screen_height - window_height) // 2
        
        self._window.geometry(f"{window_width}x{window_height}+{x}+{y}")
        
        # ウィンドウを最前面に
        self._window.attributes('-topmost', True)
        self._window.resizable(True, True)  # リサイズ可能にして確実に表示
        
        # 背景色を目立つ色に
        self._window.configure(bg='lightblue')
        
        print(f"🖥️ ウィンドウサイズ: {window_width}x{window_height}")
        print(f"🖥️ ウィンドウ位置: {x}, {y}")
        
        # UI作成
        self._create_ui()
        
        # Windows APIで強制表示
        self._force_show_with_winapi()
        
        # 更新ループを開始
        self._window.after(1000, self._update_display)
        
        print("🖥️ ウィンドウ作成完了、表示中...")
        
        # メインループ開始（ブロックしない）
        self._window.update()
        
    def _create_ui(self) -> None:
        """UI要素を作成"""
        # メインフレーム
        main_frame = tk.Frame(self._window, bg='lightblue', padx=30, pady=30)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # 超大きなヘッダー
        header = tk.Label(main_frame, 
                         text="【実行中タスク】", 
                         font=("MS Gothic", 24, "bold"),
                         fg="red", bg="yellow",
                         relief=tk.RAISED, bd=5)
        header.pack(pady=(0, 30))
        
        # 端末情報フレーム
        self._info_frame = tk.Frame(main_frame, bg='lightblue')
        self._info_frame.pack(fill=tk.BOTH, expand=True)
        
        # 各端末のラベルを作成
        for i, device_port in enumerate(self._device_ports, 1):
            # 端末情報フレーム
            device_frame = tk.Frame(self._info_frame, bg='white', relief=tk.RAISED, bd=2)
            device_frame.pack(fill=tk.X, pady=5, padx=10)
            
            # 端末番号（左側）
            port_label = tk.Label(device_frame, 
                                text=f"端末{i}:", 
                                font=("MS Gothic", 16, "bold"),
                                fg="blue", bg="white")
            port_label.pack(side=tk.LEFT, padx=20, pady=10)
            
            # タスク情報（右側）
            task_info = self._tasks.get(device_port, "---:待機中")
            task_label = tk.Label(device_frame, 
                                text=task_info,
                                font=("MS Gothic", 14),
                                fg="black", bg="lightyellow",
                                relief=tk.SUNKEN, bd=2,
                                width=35)
            task_label.pack(side=tk.RIGHT, padx=20, pady=10)
            
            self._labels[device_port] = task_label
        
        # ボタンフレーム
        button_frame = tk.Frame(main_frame, bg='lightblue')
        button_frame.pack(pady=20)
        
        # 大きな閉じるボタン
        close_btn = tk.Button(button_frame,
                            text="最小化",
                            font=("MS Gothic", 14, "bold"),
                            bg="orange", fg="black",
                            width=15, height=2,
                            command=self._minimize_window)
        close_btn.pack(side=tk.LEFT, padx=10)
        
        # テストボタン
        test_btn = tk.Button(button_frame,
                           text="表示テスト",
                           font=("MS Gothic", 14, "bold"),
                           bg="green", fg="white",
                           width=15, height=2,
                           command=self._test_display)
        test_btn.pack(side=tk.LEFT, padx=10)
        
        # 状態表示
        self._status_label = tk.Label(main_frame,
                                    text="SuperTaskMonitor 正常動作中",
                                    font=("MS Gothic", 12),
                                    fg="green", bg="lightblue")
        self._status_label.pack(pady=10)
    
    def _force_show_with_winapi(self) -> None:
        """Windows APIを使ってウィンドウを強制表示"""
        try:
            # tkinterウィンドウのハンドルを取得
            self._window.update()
            hwnd_str = self._window.wm_frame()
            if hwnd_str:
                self._hwnd = int(hwnd_str, 16) if isinstance(hwnd_str, str) else hwnd_str
            else:
                # 代替方法でハンドルを取得
                self._hwnd = ctypes.windll.user32.FindWindowW(None, self._window.title())
            
            if self._hwnd:
                print(f"🖥️ ウィンドウハンドル取得: {self._hwnd}")
                
                # Windows APIで強制表示
                SW_RESTORE = 9
                SW_SHOW = 5 
                SW_SHOWNOACTIVATE = 4
                
                # 複数の方法で表示を試行
                ctypes.windll.user32.ShowWindow(self._hwnd, SW_RESTORE)
                ctypes.windll.user32.ShowWindow(self._hwnd, SW_SHOW)
                ctypes.windll.user32.SetForegroundWindow(self._hwnd)
                ctypes.windll.user32.BringWindowToTop(self._hwnd)
                
                # ウィンドウを最前面に設定
                HWND_TOPMOST = -1
                SWP_NOSIZE = 0x0001
                SWP_NOMOVE = 0x0002
                ctypes.windll.user32.SetWindowPos(
                    self._hwnd, HWND_TOPMOST, 0, 0, 0, 0, 
                    SWP_NOMOVE | SWP_NOSIZE
                )
                
                print("🖥️ Windows API強制表示完了")
            else:
                print("🖥️ ウィンドウハンドル取得失敗")
                
        except Exception as e:
            print(f"🖥️ Windows API表示エラー: {e}")
    
    def _test_display(self) -> None:
        """表示テスト"""
        print("🖥️ 表示テスト実行")
        self._force_show_with_winapi()
        
        # ウィンドウを点滅させる
        try:
            import time
            for _ in range(3):
                self._window.configure(bg='red')
                self._window.update()
                time.sleep(0.2)
                self._window.configure(bg='lightblue')
                self._window.update()
                time.sleep(0.2)
        except Exception as e:
            print(f"🖥️ 点滅テストエラー: {e}")
    
    def _minimize_window(self) -> None:
        """ウィンドウを最小化"""
        if self._window:
            self._window.iconify()
    
    def _update_display(self) -> None:
        """表示を更新"""
        if not self._running or not self._window:
            return
            
        try:
            # タスク情報を更新
            with self._lock:
                for device_port, task_info in self._tasks.items():
                    if device_port in self._labels:
                        current_text = self._labels[device_port].cget("text")
                        if current_text != task_info:
                            self._labels[device_port].config(text=task_info)
            
            # 状態表示を更新
            current_time = time.strftime("%H:%M:%S")
            self._status_label.config(text=f"SuperTaskMonitor 動作中 - {current_time}")
            
            # 次の更新をスケジュール
            self._window.after(1000, self._update_display)
            
        except Exception as e:
            print(f"🖥️ 更新エラー: {e}")
            if self._running:
                self._window.after(2000, self._update_display)
    
    def update_task(self, device_port: str, folder: str, operation: str) -> None:
        """タスク状況を更新"""
        with self._lock:
            self._tasks[device_port] = f"{folder}:{operation}"
        print(f"🖥️ 更新: {device_port} -> {folder}:{operation}")
    
    def stop_monitor(self) -> None:
        """モニターを停止"""
        self._running = False
        if self._window:
            try:
                self._window.destroy()
            except:
                pass
        print("🖥️ SuperTaskMonitor停止")

# グローバルインスタンス
_super_monitor: Optional[SuperTaskMonitor] = None

def start_super_task_monitor(device_ports: List[str]) -> None:
    """SuperTaskMonitorを開始"""
    global _super_monitor
    try:
        if _super_monitor is None:
            _super_monitor = SuperTaskMonitor()
        
        print(f"🖥️ SuperTaskMonitor起動要求: {len(device_ports)}端末")
        _super_monitor.start_monitor(device_ports)
        
    except Exception as e:
        print(f"🖥️ SuperTaskMonitor起動エラー: {e}")
        logger.error(f"🖥️ SuperTaskMonitor起動エラー: {e}", exc_info=True)

def update_super_task(device_port: str, folder: str, operation: str) -> None:
    """SuperTaskMonitorのタスク状況を更新"""
    global _super_monitor
    if _super_monitor:
        _super_monitor.update_task(device_port, folder, operation)

def is_super_task_monitor_running() -> bool:
    """Return True if SuperTaskMonitor (embedded Tk) is active."""
    try:
        return bool(_super_monitor and _super_monitor._running)
    except Exception:
        return False

def test_super_monitor() -> None:
    """SuperTaskMonitorをテスト"""
    try:
        print("🖥️ SuperTaskMonitorテスト開始")
        test_ports = ["62001", "62025", "62026", "62027", "62028", "62029", "62030", "62031"]
        
        start_super_task_monitor(test_ports)
        
        # テストデータ更新
        for i, port in enumerate(test_ports):
            folder = f"{i+1:03d}"
            status = ["ID_check中", "login中", "待機中", "処理中", "完了"][i % 5]
            update_super_task(port, folder, status)
            time.sleep(0.3)
        
        print("🖥️ SuperTaskMonitorテスト完了")
        
    except Exception as e:
        print(f"🖥️ SuperTaskMonitorテストエラー: {e}")

def emergency_test_window() -> None:
    """緊急用の確実に表示されるテストウィンドウ"""
    try:
        print("🚨 緊急テストウィンドウ起動")
        
        root = tk.Tk()
        root.title("🚨緊急テストウィンドウ🚨")
        root.geometry("800x600+100+100")
        root.configure(bg='red')
        root.attributes('-topmost', True)
        
        # 巨大なテキスト
        label = tk.Label(root, 
                        text="🚨緊急テストウィンドウ🚨\n\nこれが見えますか？", 
                        font=("MS Gothic", 30, "bold"),
                        fg="white", bg="red")
        label.pack(expand=True)
        
        # Windows APIで強制表示
        root.update()
        hwnd = ctypes.windll.user32.FindWindowW(None, root.title())
        if hwnd:
            ctypes.windll.user32.SetForegroundWindow(hwnd)
            ctypes.windll.user32.BringWindowToTop(hwnd)
            print(f"🚨 緊急ウィンドウハンドル: {hwnd}")
        
        # 閉じるボタン
        close_btn = tk.Button(root, text="閉じる", command=root.destroy,
                             font=("MS Gothic", 20), bg="yellow", fg="black",
                             width=20, height=3)
        close_btn.pack(pady=20)
        
        print("🚨 緊急テストウィンドウ表示完了")
        root.mainloop()
        
    except Exception as e:
        print(f"🚨 緊急テストウィンドウエラー: {e}")

if __name__ == "__main__":
    # 直接実行時のテスト
    emergency_test_window()
