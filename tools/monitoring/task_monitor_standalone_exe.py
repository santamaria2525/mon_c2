"""
task_monitor_standalone_exe.py - Python依存完全排除版タスクモニター

別PC環境でもPythonインストール不要で動作する
完全独立型タスクモニターです。
"""

import json
import os
import sys
import time
import threading
from datetime import datetime
from typing import Dict, Any, Optional

# tkinter環境設定（exe環境対応）
try:
    import tkinter as tk
    from tkinter import ttk
    TKINTER_AVAILABLE = True
except ImportError:
    TKINTER_AVAILABLE = False
    print("[ERROR] tkinter利用不可 - GUI無効モード")

class ExeTaskMonitor:
    """Python依存なし・exe専用タスクモニター"""
    
    def __init__(self, data_file: str):
        self.data_file = data_file
        self.devices = {}
        self.running = True
        self.root = None
        self.status_labels = {}
        self.folder_labels = {}
        
        # データファイル初期化
        self._ensure_data_file()
        
    def _ensure_data_file(self):
        """データファイルの存在確認・初期化"""
        try:
            if not os.path.exists(self.data_file):
                initial_data = {
                    "devices": {},
                    "last_update": time.time(),
                    "status": "初期化中"
                }
                with open(self.data_file, 'w', encoding='utf-8') as f:
                    json.dump(initial_data, f, ensure_ascii=False, indent=2)
                print(f"[INFO] データファイル初期化: {self.data_file}")
        except Exception as e:
            print(f"[ERROR] データファイル初期化失敗: {e}")
    
    def _load_data(self) -> Dict[str, Any]:
        """データファイルから状態を読み込み"""
        try:
            if os.path.exists(self.data_file):
                with open(self.data_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            print(f"[WARN] データ読み込みエラー: {e}")
        
        return {"devices": {}, "last_update": time.time(), "status": "エラー"}
    
    def create_gui(self):
        """GUI作成（exe環境完全対応）"""
        if not TKINTER_AVAILABLE:
            print("[ERROR] GUI作成不可 - tkinter利用不可")
            return False
            
        try:
            # メインウィンドウ作成
            self.root = tk.Tk()
            self.root.title("📊 タスクモニター (EXE版)")
            
            # exe環境でのtkinter設定
            if getattr(sys, 'frozen', False):
                # EXE環境での特別設定
                try:
                    self.root.wm_state('normal')
                except:
                    pass
            
            # ウィンドウサイズと位置
            window_width = 320
            window_height = 200
            
            # 画面右下に配置
            screen_width = self.root.winfo_screenwidth()
            screen_height = self.root.winfo_screenheight()
            x = screen_width - window_width - 20
            y = screen_height - window_height - 100
            
            self.root.geometry(f"{window_width}x{window_height}+{x}+{y}")
            self.root.resizable(False, False)
            self.root.attributes('-topmost', True)
            
            # フレーム作成
            main_frame = ttk.Frame(self.root, padding="5")
            main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
            
            # ヘッダー
            header_label = ttk.Label(main_frame, text="📊 端末状態監視", 
                                   font=("Arial", 10, "bold"))
            header_label.grid(row=0, column=0, columnspan=2, pady=(0, 5))
            
            # デバイス状態表示エリア
            self.device_frame = ttk.Frame(main_frame)
            self.device_frame.grid(row=1, column=0, columnspan=2, sticky=(tk.W, tk.E))
            
            # 更新時刻表示
            self.time_label = ttk.Label(main_frame, text="起動中...", 
                                      font=("Arial", 8))
            self.time_label.grid(row=2, column=0, columnspan=2, pady=(5, 0))
            
            print("[SUCCESS] GUI作成完了")
            return True
            
        except Exception as e:
            print(f"[ERROR] GUI作成失敗: {e}")
            return False
    
    def update_device_display(self, data: Dict[str, Any]):
        """デバイス表示を更新"""
        if not self.root:
            return
            
        try:
            devices = data.get("devices", {})
            
            # 既存のウィジェットをクリア
            for widget in self.device_frame.winfo_children():
                widget.destroy()
            
            # デバイス情報を表示
            row = 0
            for device_id, device_info in devices.items():
                # デバイス名
                device_label = ttk.Label(self.device_frame, 
                                       text=f"端末{device_id[-2:]}:",
                                       font=("Arial", 8, "bold"))
                device_label.grid(row=row, column=0, sticky=tk.W, padx=(0, 5))
                
                # ステータス
                status = device_info.get("status", "不明")
                folder = device_info.get("folder", "---")
                
                # ステータスに応じた色分け
                if "成功" in status or "完了" in status:
                    fg_color = "green"
                elif "エラー" in status or "失敗" in status:
                    fg_color = "red"
                elif "実行中" in status or "処理中" in status:
                    fg_color = "blue"
                else:
                    fg_color = "black"
                
                status_text = f"{folder} | {status}"
                status_label = ttk.Label(self.device_frame, 
                                       text=status_text,
                                       font=("Arial", 8),
                                       foreground=fg_color)
                status_label.grid(row=row, column=1, sticky=tk.W)
                
                row += 1
            
            # 更新時刻
            current_time = datetime.now().strftime("%H:%M:%S")
            self.time_label.config(text=f"更新: {current_time}")
            
        except Exception as e:
            print(f"[ERROR] 表示更新エラー: {e}")
    
    def monitor_loop(self):
        """メインモニタリングループ"""
        print("[INFO] モニタリングループ開始")
        
        while self.running:
            try:
                # データ読み込み
                data = self._load_data()
                
                # GUI更新
                if self.root:
                    self.root.after(0, lambda: self.update_device_display(data))
                
                # 5秒間隔で更新
                time.sleep(5)
                
            except Exception as e:
                print(f"[ERROR] モニタリングエラー: {e}")
                time.sleep(5)
    
    def start(self):
        """タスクモニター開始"""
        print("[INFO] EXE版タスクモニター開始")
        
        # GUI作成
        if not self.create_gui():
            print("[ERROR] GUI作成失敗 - 終了")
            return
        
        # モニタリングスレッド開始
        monitor_thread = threading.Thread(target=self.monitor_loop, daemon=True)
        monitor_thread.start()
        
        # 終了ハンドラー設定
        def on_closing():
            print("[INFO] タスクモニター終了")
            self.running = False
            self.root.destroy()
        
        self.root.protocol("WM_DELETE_WINDOW", on_closing)
        
        # GUIメインループ
        try:
            self.root.mainloop()
        except Exception as e:
            print(f"[ERROR] GUIループエラー: {e}")

def main():
    """メイン実行関数"""
    if len(sys.argv) < 2:
        print("[ERROR] 使用方法: python task_monitor_standalone_exe.py <data_file>")
        sys.exit(1)
    
    data_file = sys.argv[1]
    print(f"[INFO] データファイル: {data_file}")
    
    # タスクモニター起動
    monitor = ExeTaskMonitor(data_file)
    monitor.start()

if __name__ == "__main__":
    main()