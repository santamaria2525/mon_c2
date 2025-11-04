"""
compact_task_monitor.py - EXE実行時専用のコンパクトタスクモニター

EXE実行環境で確実に表示される、最小限のUIを持つタスクモニターです。
無駄なスペースを削除し、必要な情報のみを表示します。
"""

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

class CompactTaskMonitor:
    """EXE実行時専用のコンパクトタスクモニター"""
    
    def __init__(self):
        self._window: Optional[tk.Tk] = None
        self._labels: Dict[str, tk.Label] = {}
        self._tasks: Dict[str, str] = {}  
        self._lock = threading.Lock()
        self._running = False
        self._device_ports: List[str] = []
        self._update_thread: Optional[threading.Thread] = None
        self._is_exe = getattr(sys, 'frozen', False)
        
    def start_monitor(self, device_ports: List[str]) -> None:
        """コンパクトタスクモニターを開始"""
        if self._running:
            return
            
        self._running = True
        self._device_ports = device_ports.copy()
        
        # 初期化
        with self._lock:
            self._tasks = {port: "待機中" for port in device_ports}
        
        # GUIウィンドウを作成（非ブロッキング、メインGUIとの競合回避）
        gui_thread = threading.Thread(target=self._create_window_nonblocking, daemon=True)
        gui_thread.start()
        time.sleep(1.5)  # GUI作成完了を待機（短縮）
    
    def _create_window_nonblocking(self) -> None:
        """非ブロッキング版ウィンドウ作成（メインGUIとの競合回避）"""
        try:
            # タスクモニター専用のTkinterインスタンスを作成
            self._window = tk.Tk()
            self._window.title("実行中タスク")
            
            # ウィンドウクラス名を設定してメインGUIと区別
            try:
                self._window.wm_class("TaskMonitor", "TaskMonitor")
            except:
                pass
            
            # コンパクトサイズ計算（1端末あたり25ピクセル）
            base_height = 80  # ヘッダー + マージン
            task_height = len(self._device_ports) * 25
            total_height = base_height + task_height
            window_width = 320
            
            # 画面右下に配置
            try:
                screen_width = self._window.winfo_screenwidth()
                screen_height = self._window.winfo_screenheight()
                x = screen_width - window_width - 20
                y = screen_height - total_height - 100
                self._window.geometry(f"{window_width}x{total_height}+{x}+{y}")
            except:
                # スクリーン情報取得失敗時のフォールバック
                self._window.geometry(f"{window_width}x{total_height}+1600+700")
            
            # ウィンドウ設定（メインGUIと競合しない設定）
            self._window.attributes('-topmost', True)
            self._window.resizable(False, False)
            self._window.configure(bg='#f0f0f0')
            
            # プロトコル設定（閉じるボタンで最小化）
            self._window.protocol("WM_DELETE_WINDOW", self._minimize_window)
            
            # コンパクトUI作成
            self._create_compact_ui()
            
            # 表示処理（軽量版）
            self._force_show_lightweight()
            
            # 非ブロッキング更新スケジューラー開始
            self._start_nonblocking_updates()
            
            # 非ブロッキングイベント処理ループ
            self._run_nonblocking_mainloop()
            
        except Exception as e:
            logger.error(f"タスクモニターウィンドウ作成エラー: {e}", exc_info=True)
    
    def _create_compact_ui(self) -> None:
        """コンパクトUI要素を作成"""
        # メインフレーム（余白最小）
        main_frame = tk.Frame(self._window, bg='#f0f0f0', padx=5, pady=5)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # コンパクトヘッダー
        header = tk.Label(main_frame, 
                         text="実行中タスク", 
                         font=("MS Gothic", 12, "bold"),
                         fg="white", bg="#4472C4",
                         relief=tk.FLAT, bd=1)
        header.pack(fill=tk.X, pady=(0, 3))
        
        # タスク表示エリア
        task_frame = tk.Frame(main_frame, bg='#f0f0f0')
        task_frame.pack(fill=tk.BOTH, expand=True)
        
        # 各端末のコンパクト表示
        for i, device_port in enumerate(self._device_ports, 1):
            # 1行のコンパクトフレーム
            row_frame = tk.Frame(task_frame, bg='white', relief=tk.RAISED, bd=1)
            row_frame.pack(fill=tk.X, pady=1)
            
            # 端末番号（左側、固定幅）
            port_label = tk.Label(row_frame, 
                                text=f"端末{i}:", 
                                font=("MS Gothic", 9),
                                fg="#2F5597", bg="white",
                                width=6, anchor='w')
            port_label.pack(side=tk.LEFT, padx=(3, 0))
            
            # タスク情報（右側）
            task_info = self._tasks.get(device_port, "待機中")
            task_label = tk.Label(row_frame, 
                                text=task_info,
                                font=("MS Gothic", 9),
                                fg="black", bg="#F2F2F2",
                                relief=tk.FLAT, bd=1,
                                anchor='w')
            task_label.pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=(0, 3))
            
            self._labels[device_port] = task_label
        
        # 最小化ボタン（コンパクト）
        btn_frame = tk.Frame(main_frame, bg='#f0f0f0')
        btn_frame.pack(fill=tk.X, pady=(3, 0))
        
        minimize_btn = tk.Button(btn_frame,
                                text="最小化",
                                font=("MS Gothic", 8),
                                bg="#E1ECFC", fg="black",
                                relief=tk.RAISED, bd=1,
                                height=1,
                                command=self._minimize_window)
        minimize_btn.pack(side=tk.RIGHT, padx=(0, 0))
        
        # ステータス表示（小さく）
        self._status_label = tk.Label(btn_frame,
                                    text="動作中",
                                    font=("MS Gothic", 8),
                                    fg="#666666", bg="#f0f0f0",
                                    anchor='w')
        self._status_label.pack(side=tk.LEFT)
    
    def _force_show_universal(self) -> None:
        """統一強制表示処理（全環境対応）"""
        try:
            print("ウィンドウ強制表示処理開始...")
            
            # tkinterウィンドウの更新を確実に実行
            for _ in range(3):
                self._window.update()
                time.sleep(0.1)
            
            # tkinter標準の表示処理
            self._window.deiconify()
            self._window.lift()
            self._window.attributes('-topmost', True)
            self._window.focus_force()
            
            # Windows API使用可能な場合の追加処理
            try:
                # ウィンドウハンドル取得
                hwnd = None
                for attempt in range(10):
                    try:
                        hwnd = ctypes.windll.user32.FindWindowW(None, "実行中タスク")
                        if hwnd:
                            break
                        time.sleep(0.1)
                    except:
                        pass
                
                if hwnd:
                    print(f"ウィンドウハンドル取得成功: {hwnd}")
                    
                    # Windows APIで表示処理
                    SW_RESTORE = 9
                    SW_SHOW = 5
                    
                    # 表示・復元
                    ctypes.windll.user32.ShowWindow(hwnd, SW_RESTORE)
                    time.sleep(0.1)
                    ctypes.windll.user32.ShowWindow(hwnd, SW_SHOW)
                    time.sleep(0.1)
                    
                    # 前面に持ってくる
                    ctypes.windll.user32.BringWindowToTop(hwnd)
                    ctypes.windll.user32.SetForegroundWindow(hwnd)
                    
                    # 最前面設定
                    HWND_TOPMOST = -1
                    SWP_NOSIZE = 0x0001
                    SWP_NOMOVE = 0x0002
                    SWP_SHOWWINDOW = 0x0040
                    
                    ctypes.windll.user32.SetWindowPos(
                        hwnd, HWND_TOPMOST, 0, 0, 0, 0, 
                        SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW
                    )
                    
                    print("Windows API表示処理完了")
                else:
                    print("ウィンドウハンドル取得失敗 - tkinter標準処理で継続")
                    
            except Exception as api_error:
                print(f"Windows API処理スキップ: {api_error}")
            
            print("ウィンドウ強制表示処理完了")
                
        except Exception as e:
            print(f"強制表示処理エラー: {e}")
            # エラー時の最低限処理
            try:
                self._window.attributes('-topmost', True)
                self._window.deiconify()
                self._window.lift()
            except:
                pass
    
    def _force_show_lightweight(self) -> None:
        """軽量版強制表示処理（メインGUIとの競合回避）"""
        try:
            # tkinter標準の表示処理のみ使用
            self._window.deiconify()
            self._window.lift()
            self._window.attributes('-topmost', True)
            
            # 最小限の更新処理
            self._window.update_idletasks()
                
        except Exception as e:
            logger.error(f"軽量版表示処理エラー: {e}")
    
    def _start_nonblocking_updates(self) -> None:
        """非ブロッキング更新スケジューラー開始"""
        def update_scheduler():
            if self._running and self._window:
                try:
                    self._update_display()
                except:
                    pass
                # 次の更新をスケジュール
                self._window.after(1000, update_scheduler)
        
        # 初回更新をスケジュール
        if self._window:
            self._window.after(1000, update_scheduler)
    
    def _run_nonblocking_mainloop(self) -> None:
        """非ブロッキングメインループ（短時間処理でメインGUIをブロックしない）"""
        try:
            while self._running and self._window:
                try:
                    # 短時間のイベント処理
                    self._window.update_idletasks()
                    self._window.update()
                    time.sleep(0.1)  # CPUリソースを他のプロセスに譲る
                except tk.TclError:
                    # ウィンドウが破棄された場合
                    break
                except Exception:
                    break
        except Exception as e:
            logger.error(f"非ブロッキングメインループエラー: {e}")
    
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
            
            # 時刻表示更新
            current_time = time.strftime("%H:%M")
            self._status_label.config(text=f"動作中 {current_time}")
            
            # 次の更新をスケジュール
            self._window.after(1000, self._update_display)
            
        except Exception as e:
            print(f"更新エラー: {e}")
            if self._running:
                self._window.after(2000, self._update_display)
    
    def update_task(self, device_port: str, folder: str, operation: str) -> None:
        """タスク状況を更新"""
        try:
            # ポート形式の正規化（127.0.0.1:62025 形式に統一）
            if device_port and ":" not in device_port:
                device_port = f"127.0.0.1:{device_port}"
            
            # コンパクト表示用にフォーマット
            compact_text = f"{folder}:{operation}"
            if len(compact_text) > 18:
                compact_text = compact_text[:15] + "..."
                
            with self._lock:
                # 該当するポートが登録されているかチェック
                if device_port in self._tasks:
                    self._tasks[device_port] = compact_text
                else:
                    # ポート番号のみでマッチングを試行
                    port_only = device_port.split(":")[-1] if ":" in device_port else device_port
                    for registered_port in self._tasks.keys():
                        if registered_port.endswith(f":{port_only}"):
                            self._tasks[registered_port] = compact_text
                            break
                        
        except Exception as e:
            # エラーのみログに出力（画面には表示しない）
            logger.error(f"タスクモニター更新エラー: {e}")
    
    def stop_monitor(self) -> None:
        """モニターを停止"""
        self._running = False
        if self._window:
            try:
                self._window.quit()
                self._window.destroy()
            except:
                pass
        print("CompactTaskMonitor停止")
    
    def _periodic_visibility_check(self) -> None:
        """定期的にウィンドウの表示状態をチェック（EXE環境用）"""
        if not self._running or not self._window:
            return
            
        try:
            # ウィンドウが最小化されていないかチェック
            window_state = self._window.state()
            if window_state == 'iconic':  # 最小化されている
                print("ウィンドウが最小化されているため復元します")
                self._window.deiconify()
                self._window.lift()
                self._window.attributes('-topmost', True)
                
            # Windows APIでも確認
            if self._is_exe:
                try:
                    hwnd = ctypes.windll.user32.FindWindowW(None, "実行中タスク")
                    if hwnd:
                        is_visible = ctypes.windll.user32.IsWindowVisible(hwnd)
                        if not is_visible:
                            print("ウィンドウが非表示のため再表示します")
                            ctypes.windll.user32.ShowWindow(hwnd, 5)  # SW_SHOW
                            ctypes.windll.user32.SetForegroundWindow(hwnd)
                except:
                    pass
            
            # 次のチェックをスケジュール（10秒後）
            self._window.after(10000, self._periodic_visibility_check)
            
        except Exception as e:
            print(f"表示状態チェックエラー: {e}")
            if self._running:
                self._window.after(15000, self._periodic_visibility_check)

# グローバルインスタンス
_compact_monitor: Optional[CompactTaskMonitor] = None

def start_compact_task_monitor(device_ports: List[str]) -> None:
    """CompactTaskMonitorを開始"""
    global _compact_monitor
    try:
        if _compact_monitor is None:
            _compact_monitor = CompactTaskMonitor()
        
        _compact_monitor.start_monitor(device_ports)
        
    except Exception as e:
        logger.error(f"CompactTaskMonitor起動エラー: {e}", exc_info=True)

def update_compact_task(device_port: str, folder: str, operation: str) -> None:
    """CompactTaskMonitorのタスク状況を更新"""
    global _compact_monitor
    try:
        if _compact_monitor:
            _compact_monitor.update_task(device_port, folder, operation)
        # EXE実行時は静音モード
    except Exception as e:
        # エラーのみ表示
        import logging
        logging.error(f"タスクモニター更新エラー: {e}")

def test_compact_monitor() -> None:
    """CompactTaskMonitorをテスト"""
    try:
        print("CompactTaskMonitorテスト開始")
        test_ports = ["62001", "62025", "62026", "62027", "62028", "62029", "62030", "62031"]
        
        start_compact_task_monitor(test_ports)
        
        # テストデータ更新
        for i, port in enumerate(test_ports):
            folder = f"{i+1:03d}"
            status = ["ID_check中", "login中", "待機中", "処理中", "完了"][i % 5]
            update_compact_task(port, folder, status)
            time.sleep(0.5)
        
        print("CompactTaskMonitorテスト完了")
        
    except Exception as e:
        print(f"CompactTaskMonitorテストエラー: {e}")

if __name__ == "__main__":
    test_compact_monitor()


def is_compact_task_monitor_running() -> bool:
    """Return True if CompactTaskMonitor is active."""
    try:
        return bool(_compact_monitor and _compact_monitor._running)
    except Exception:
        return False
