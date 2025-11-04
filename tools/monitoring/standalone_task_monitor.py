"""
standalone_task_monitor.py - 独立プロセス用タスクモニター

メインアプリから独立したプロセスとして動作するタスクモニターです。
JSONファイルを監視してタスク状況を表示します。
"""

import sys
import os
import json
import time
import tkinter as tk
from tkinter import ttk
import threading
try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False
    print("[WARNING] psutil未インストール - 親プロセス監視無効")

from typing import Dict, List, Optional

class StandaloneTaskMonitor:
    """独立プロセス用タスクモニター"""
    
    def __init__(self, data_file: str):
        self._data_file = data_file
        self._window: Optional[tk.Tk] = None
        self._labels: Dict[str, tk.Label] = {}
        self._tasks: Dict[str, str] = {}
        self._device_ports: List[str] = []
        self._running = False
        self._last_modified = 0
        self._parent_pid = os.getppid()  # 親プロセスPIDを保存
        
    def start(self) -> None:
        """タスクモニターを開始"""
        # 独立タスクモニター開始
        
        # 初期データを読み込み
        if not self._load_initial_data():
            return
        
        self._running = True
        
        # GUI作成
        self._create_window()
        
        # データ監視スレッド開始
        monitor_thread = threading.Thread(target=self._monitor_data_file, daemon=True)
        monitor_thread.start()
        
        # 親プロセス監視スレッド開始（psutilが使用可能な場合のみ）
        if PSUTIL_AVAILABLE:
            parent_monitor_thread = threading.Thread(target=self._monitor_parent_process, daemon=True)
            parent_monitor_thread.start()
        else:
            pass
        
        # メインループ開始
        # 独立タスクモニター表示開始
        self._window.mainloop()
    
    def _load_initial_data(self) -> bool:
        """初期データを読み込み"""
        try:
            if not os.path.exists(self._data_file):
                print(f"データファイルが存在しません: {self._data_file}")
                return False
                
            with open(self._data_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            self._device_ports = data.get("device_ports", [])
            self._tasks = data.get("tasks", {})
            self._last_modified = os.path.getmtime(self._data_file)
            
            # 初期データ読み込み完了
            return True
            
        except Exception as e:
            print(f"初期データ読み込みエラー: {e}")
            return False
    
    def _create_window(self) -> None:
        """ウィンドウを作成"""
        try:
            # ウィンドウ作成開始
            
            # tkinterルートウィンドウを作成
            self._window = tk.Tk()
            self._window.title("実行中タスク")
            
            # コンパクトサイズ計算
            base_height = 80
            task_height = len(self._device_ports) * 25
            total_height = base_height + task_height
            window_width = 320
            
            # 画面右下に配置
            screen_width = self._window.winfo_screenwidth()
            screen_height = self._window.winfo_screenheight()
            x = screen_width - window_width - 20
            y = screen_height - total_height - 100
            
            self._window.geometry(f"{window_width}x{total_height}+{x}+{y}")
            
            # ウィンドウ設定
            self._window.attributes('-topmost', True)
            self._window.resizable(False, False)
            self._window.configure(bg='#f0f0f0')
            self._window.protocol("WM_DELETE_WINDOW", self._minimize_window)
            
            # ウィンドウサイズと位置設定完了
            
            # UI作成
            self._create_ui()
            
            # 強制表示
            self._force_show()
            
            # 定期更新開始
            self._window.after(1000, self._update_display)
            
            # ウィンドウ作成完了
            
        except Exception as e:
            print(f"ウィンドウ作成エラー: {e}")
            raise
    
    def _create_ui(self) -> None:
        """UI要素を作成"""
        # メインフレーム
        main_frame = tk.Frame(self._window, bg='#f0f0f0', padx=5, pady=5)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # ヘッダー
        header = tk.Label(main_frame, 
                         text="実行中タスク", 
                         font=("MS Gothic", 12, "bold"),
                         fg="white", bg="#4472C4",
                         relief=tk.FLAT, bd=1)
        header.pack(fill=tk.X, pady=(0, 3))
        
        # タスク表示エリア
        task_frame = tk.Frame(main_frame, bg='#f0f0f0')
        task_frame.pack(fill=tk.BOTH, expand=True)
        
        # 各端末の表示
        for i, device_port in enumerate(self._device_ports, 1):
            # 1行のフレーム
            row_frame = tk.Frame(task_frame, bg='white', relief=tk.RAISED, bd=1)
            row_frame.pack(fill=tk.X, pady=1)
            
            # 端末番号
            port_label = tk.Label(row_frame, 
                                text=f"端末{i}:", 
                                font=("MS Gothic", 9),
                                fg="#2F5597", bg="white",
                                width=6, anchor='w')
            port_label.pack(side=tk.LEFT, padx=(3, 0))
            
            # タスク情報
            task_info = self._tasks.get(device_port, "待機中")
            task_label = tk.Label(row_frame, 
                                text=task_info,
                                font=("MS Gothic", 9),
                                fg="black", bg="#F2F2F2",
                                relief=tk.FLAT, bd=1,
                                anchor='w')
            task_label.pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=(0, 3))
            
            self._labels[device_port] = task_label
        
        # 最小化ボタン
        btn_frame = tk.Frame(main_frame, bg='#f0f0f0')
        btn_frame.pack(fill=tk.X, pady=(3, 0))
        
        minimize_btn = tk.Button(btn_frame,
                                text="最小化",
                                font=("MS Gothic", 8),
                                bg="#E1ECFC", fg="black",
                                relief=tk.RAISED, bd=1,
                                height=1,
                                command=self._minimize_window)
        minimize_btn.pack(side=tk.RIGHT)
        
        # ステータス
        self._status_label = tk.Label(btn_frame,
                                    text="動作中",
                                    font=("MS Gothic", 8),
                                    fg="#666666", bg="#f0f0f0",
                                    anchor='w')
        self._status_label.pack(side=tk.LEFT)
    
    def _force_show(self) -> None:
        """ウィンドウを強制表示"""
        try:
            # tkinter標準の表示処理
            for _ in range(3):
                self._window.update()
                self._window.deiconify()
                self._window.lift()
                self._window.focus_force()
                self._window.attributes('-topmost', True)
                time.sleep(0.1)
            
            # Windows API使用（可能な場合）
            try:
                import ctypes
                hwnd = ctypes.windll.user32.FindWindowW(None, "実行中タスク")
                if hwnd:
                    ctypes.windll.user32.ShowWindow(hwnd, 5)  # SW_SHOW
                    ctypes.windll.user32.SetForegroundWindow(hwnd)
                    ctypes.windll.user32.BringWindowToTop(hwnd)
                    
                    # 最前面設定
                    HWND_TOPMOST = -1
                    SWP_NOSIZE = 0x0001
                    SWP_NOMOVE = 0x0002
                    ctypes.windll.user32.SetWindowPos(
                        hwnd, HWND_TOPMOST, 0, 0, 0, 0, 
                        SWP_NOMOVE | SWP_NOSIZE
                    )
            except Exception as e:
                print(f"Windows API表示エラー: {e}")
                
        except Exception as e:
            print(f"強制表示エラー: {e}")
    
    def _minimize_window(self) -> None:
        """ウィンドウを最小化"""
        if self._window:
            self._window.iconify()
    
    def _monitor_data_file(self) -> None:
        """データファイルを監視"""
        while self._running:
            try:
                if os.path.exists(self._data_file):
                    current_modified = os.path.getmtime(self._data_file)
                    if current_modified > self._last_modified:
                        self._last_modified = current_modified
                        self._load_data_update()
                        
                time.sleep(0.5)  # 0.5秒間隔で監視
                
            except Exception as e:
                print(f"データファイル監視エラー: {e}")
                time.sleep(1.0)
    
    def _load_data_update(self) -> None:
        """データファイルから更新を読み込み"""
        try:
            with open(self._data_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            new_tasks = data.get("tasks", {})
            
            # タスク情報が変更された場合のみ更新
            if new_tasks != self._tasks:
                self._tasks = new_tasks
                # GUI更新はメインスレッドで実行
                if self._window:
                    self._window.after(0, self._update_gui)
                    
        except Exception as e:
            print(f"データ更新エラー: {e}")
            import traceback
            traceback.print_exc()
    
    def _update_display(self) -> None:
        """表示を定期更新"""
        if not self._running or not self._window:
            return
            
        try:
            # 時刻表示更新
            current_time = time.strftime("%H:%M")
            self._status_label.config(text=f"動作中 {current_time}")
            
            # 次の更新をスケジュール
            self._window.after(1000, self._update_display)
            
        except Exception as e:
            print(f"表示更新エラー: {e}")
            if self._running:
                self._window.after(2000, self._update_display)
    
    def _update_gui(self) -> None:
        """GUI要素を更新"""
        try:
            for device_port, task_info in self._tasks.items():
                if device_port in self._labels:
                    current_text = self._labels[device_port].cget("text")
                    if current_text != task_info:
                        self._labels[device_port].config(text=task_info)
                        
        except Exception as e:
            print(f"GUI更新エラー: {e}")
            import traceback
            traceback.print_exc()
    
    def _monitor_parent_process(self) -> None:
        """親プロセスを監視し、終了時に自動終了"""
        if not PSUTIL_AVAILABLE:
            return
            
        # 親プロセス監視開始
        
        while self._running:
            try:
                # 親プロセスが存在するかチェック
                if not psutil.pid_exists(self._parent_pid):
                    self._shutdown_monitor()
                    break
                    
                # より確実なチェック: プロセス情報を取得
                try:
                    parent_process = psutil.Process(self._parent_pid)
                    if not parent_process.is_running():
                        self._shutdown_monitor()
                        break
                except psutil.NoSuchProcess:
                    self._shutdown_monitor()
                    break
                    
                time.sleep(2.0)  # 2秒間隔で監視
                
            except Exception as e:
                print(f"親プロセス監視エラー: {e}")
                time.sleep(5.0)
    
    def _shutdown_monitor(self) -> None:
        """タスクモニターを安全に終了"""
        # タスクモニター自動終了
        self._running = False
        
        if self._window:
            try:
                # メインスレッドでウィンドウを閉じる
                self._window.after(0, self._close_window)
            except Exception as e:
                print(f"ウィンドウ終了エラー: {e}")
    
    def _close_window(self) -> None:
        """ウィンドウを閉じる（メインスレッドで実行）"""
        try:
            if self._window:
                self._window.quit()
                self._window.destroy()
                pass
        except Exception as e:
            print(f"ウィンドウ閉じエラー: {e}")

def main():
    """メイン関数"""
    if len(sys.argv) != 2:
        print("使用方法: python standalone_task_monitor.py <データファイルパス>")
        sys.exit(1)
    
    data_file = sys.argv[1]
    
    # 独立タスクモニター起動
    
    try:
        monitor = StandaloneTaskMonitor(data_file)
        monitor.start()
    except Exception as e:
        print(f"独立タスクモニターエラー: {e}")
        import traceback
        traceback.print_exc()
        input("Enterキーを押して終了...")

if __name__ == "__main__":
    main()