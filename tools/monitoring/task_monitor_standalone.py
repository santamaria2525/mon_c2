"""
独立実行型タスクモニター - exe環境完全対応版

このスクリプトは完全に独立してタスクモニターを表示します。
メインアプリケーションとは一切tkinterを共有しません。
"""

import sys
import os
import json
import time
import threading
import subprocess
from pathlib import Path
from typing import Dict, List, Optional

# tkinterの安全なインポート
try:
    import tkinter as tk
    from tkinter import ttk
    TKINTER_AVAILABLE = True
except ImportError:
    TKINTER_AVAILABLE = False
    print("❌ tkinter not available")

class IndependentTaskMonitor:
    """完全独立型タスクモニター"""
    
    def __init__(self, data_file: str):
        self.data_file = data_file
        self.window = None
        self.labels = {}
        self.running = False
        self.device_ports = []
        self.tasks = {}
        self.last_modified = 0
        
    def start(self):
        """タスクモニター開始"""
        if not TKINTER_AVAILABLE:
            print("❌ tkinter使用不可 - コンソール出力モードで動作")
            self._console_mode()
            return
            
        try:
            print("🖥️ 独立タスクモニター開始...")
            
            # データファイルの初期読み込み
            if not self._load_data():
                print("❌ データファイル読み込み失敗")
                return
                
            self.running = True
            
            # GUI作成
            self._create_gui()
            
            # データ監視スレッド開始
            monitor_thread = threading.Thread(target=self._monitor_data, daemon=True)
            monitor_thread.start()
            
            print("✅ タスクモニター表示開始")
            
            # メインループ
            if self.window:
                self.window.mainloop()
                
        except Exception as e:
            print(f"❌ タスクモニターエラー: {e}")
            import traceback
            traceback.print_exc()
            
    def _console_mode(self):
        """軽量バックグラウンドモード（表示なし）"""
        print("🔇 バックグラウンドモード開始（表示なし）")
        self.running = True
        
        # 軽量な無表示監視（データファイルの整合性確認のみ）
        while self.running:
            try:
                if os.path.exists(self.data_file):
                    with open(self.data_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    # データ確認のみ、出力なし
                
                time.sleep(5.0)  # 軽量化のため間隔を長く
                    
            except KeyboardInterrupt:
                break
            except Exception:
                time.sleep(10.0)  # エラー時はさらに長く待機
        
    def _create_gui(self):
        """GUI作成"""
        try:
            # tkinter環境設定
            self._setup_tkinter()
            
            # メインウィンドウ作成
            self.window = tk.Tk()
            self.window.title("📊 実行中タスク")
            
            # 軽量コンパクトウィンドウ設定
            window_width = 320
            window_height = 60 + len(self.device_ports) * 22
            
            # 画面右下に配置
            screen_width = self.window.winfo_screenwidth()
            screen_height = self.window.winfo_screenheight()
            x = screen_width - window_width - 10
            y = screen_height - window_height - 50
            
            self.window.geometry(f"{window_width}x{window_height}+{x}+{y}")
            
            # 軽量ウィンドウ属性
            self.window.attributes('-topmost', False)  # 最前面無効化で負荷軽減
            self.window.resizable(False, False)
            self.window.configure(bg='#34495e')
            
            # 透明度設定（軽量化）
            try:
                self.window.attributes('-alpha', 0.9)  # 少し透明に
            except:
                pass
            
            # 閉じるボタンの動作
            self.window.protocol("WM_DELETE_WINDOW", self._minimize)
            
            # UI要素作成
            self._create_ui()
            
            # 強制表示
            self._force_show()
            
            # 定期更新
            self.window.after(1000, self._update_gui)
            
        except Exception as e:
            print(f"❌ GUI作成エラー: {e}")
            raise
            
    def _setup_tkinter(self):
        """tkinter環境設定"""
        try:
            # exe環境でのTCL/TKライブラリ設定
            if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
                tcl_path = os.path.join(sys._MEIPASS, 'tcl')
                tk_path = os.path.join(sys._MEIPASS, 'tk')
                
                if os.path.exists(tcl_path):
                    os.environ['TCL_LIBRARY'] = tcl_path
                    
                if os.path.exists(tk_path):
                    os.environ['TK_LIBRARY'] = tk_path
                    
            print("✅ tkinter環境設定完了")
            
        except Exception as e:
            print(f"⚠️ tkinter設定エラー: {e}")
            
    def _create_ui(self):
        """軽量UI要素作成"""
        # コンパクトメインフレーム
        main_frame = tk.Frame(self.window, bg='#34495e', padx=5, pady=5)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # コンパクトヘッダー
        header = tk.Label(main_frame,
                         text="⚡ タスク状況",
                         font=('Arial', 10, 'bold'),
                         fg='white', bg='#34495e')
        header.pack(anchor='w')
        
        # 軽量タスク表示エリア
        self.task_frame = tk.Frame(main_frame, bg='#34495e')
        self.task_frame.pack(fill=tk.BOTH, expand=True)
        
        # 各端末の軽量表示
        for i, port in enumerate(self.device_ports, 1):
            # 軽量端末行
            task_text = self.tasks.get(port, "待機")
            
            # 1行表示（端末番号:状況）
            task_label = tk.Label(self.task_frame,
                                 text=f"{i:2d}: {task_text}",
                                 font=('Arial', 8),
                                 fg='#ecf0f1', bg='#34495e',
                                 anchor='w', pady=1)
            task_label.pack(fill=tk.X, padx=2)
            
            self.labels[port] = task_label
            
        # 最小限のコントロール
        ctrl_frame = tk.Frame(main_frame, bg='#34495e')
        ctrl_frame.pack(fill=tk.X, pady=(3, 0))
        
        # 時刻表示のみ
        self.status_label = tk.Label(ctrl_frame,
                                    text=time.strftime("%H:%M"),
                                    font=('Arial', 7),
                                    fg='#bdc3c7', bg='#34495e')
        self.status_label.pack(side=tk.RIGHT)
        
    def _force_show(self):
        """軽量ウィンドウ表示"""
        try:
            # 最小限の表示処理
            self.window.deiconify()
            self.window.update_idletasks()
            print("✅ 軽量タスクモニター表示完了")
            
        except Exception as e:
            print(f"⚠️ 表示エラー: {e}")
            
    def _minimize(self):
        """最小化"""
        if self.window:
            self.window.iconify()
            
    def _load_data(self):
        """データ読み込み"""
        try:
            if not os.path.exists(self.data_file):
                print(f"⚠️ データファイル未発見: {self.data_file}")
                return False
                
            with open(self.data_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
            self.device_ports = data.get("device_ports", [])
            self.tasks = data.get("tasks", {})
            self.last_modified = os.path.getmtime(self.data_file)
            
            print(f"✅ データ読み込み完了: {len(self.device_ports)}端末")
            return True
            
        except Exception as e:
            print(f"❌ データ読み込みエラー: {e}")
            return False
            
    def _monitor_data(self):
        """データファイル監視"""
        while self.running:
            try:
                if os.path.exists(self.data_file):
                    current_time = os.path.getmtime(self.data_file)
                    if current_time > self.last_modified:
                        self.last_modified = current_time
                        self._update_data()
                        
                time.sleep(0.5)
                
            except Exception as e:
                print(f"⚠️ データ監視エラー: {e}")
                time.sleep(2.0)
                
    def _update_data(self):
        """データ更新"""
        try:
            with open(self.data_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
            new_tasks = data.get("tasks", {})
            if new_tasks != self.tasks:
                self.tasks = new_tasks
                
        except Exception as e:
            print(f"⚠️ データ更新エラー: {e}")
            
    def _update_gui(self):
        """軽量GUI更新"""
        if not self.running or not self.window:
            return
            
        try:
            # 軽量タスク表示更新
            for i, (port, task_info) in enumerate(self.tasks.items(), 1):
                if port in self.labels:
                    new_text = f"{i:2d}: {task_info}"
                    current = self.labels[port].cget("text")
                    if current != new_text:
                        self.labels[port].config(text=new_text)
                        
            # 時刻のみ更新（軽量化）
            current_time = time.strftime("%H:%M")
            self.status_label.config(text=current_time)
            
            # 軽量更新間隔（2秒）
            self.window.after(2000, self._update_gui)
            
        except Exception as e:
            if self.running:
                self.window.after(5000, self._update_gui)  # エラー時は5秒待機

def main():
    """メイン関数"""
    if len(sys.argv) != 2:
        print("使用方法: python task_monitor_standalone.py <データファイルパス>")
        input("Enterで終了...")
        return
        
    data_file = sys.argv[1]
    print(f"🚀 独立タスクモニター起動: {data_file}")
    
    try:
        monitor = IndependentTaskMonitor(data_file)
        monitor.start()
    except KeyboardInterrupt:
        print("\n👋 ユーザーにより中断されました")
    except Exception as e:
        print(f"❌ 致命的エラー: {e}")
        import traceback
        traceback.print_exc()
        input("Enterで終了...")

if __name__ == "__main__":
    main()