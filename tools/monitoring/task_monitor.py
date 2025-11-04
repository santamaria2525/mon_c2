"""
tools.monitoring.task_monitor - 実行中タスク表示ウィンドウ

マルチデバイス処理中の各端末の現在の処理状況を表示する
Windows右下に常駐する小さなウィンドウを提供します。
"""

from __future__ import annotations

import threading
import time
import tkinter as tk
from tkinter import ttk
from typing import Dict, Optional, List
import sys
import os
import queue
from logging_util import logger

def get_safe_font(size: int = 12, weight: str = "normal") -> tuple:
    """他のPC環境でも動作する安全なフォントを取得"""
    fonts_to_try = [
        "MS Gothic",      # Windows標準（日本語）
        "Yu Gothic",      # Windows 10以降
        "Meiryo",         # Windows Vista以降
        "Arial",          # Windows標準（英語）
        "Helvetica",      # Mac/Linux
        "sans-serif",     # 汎用フォールバック
        "TkDefaultFont"   # tkinter デフォルト
    ]
    
    import tkinter.font as tkfont
    available_fonts = tkfont.families()
    
    for font_name in fonts_to_try:
        if font_name in available_fonts or font_name == "TkDefaultFont":
            return (font_name, size, weight)
    
    # 最終フォールバック
    return ("", size, weight)

class TaskMonitor:
    """実行中タスク表示ウィンドウのマネージャー"""
    
    def __init__(self):
        self._window: Optional[tk.Toplevel] = None
        self._labels: Dict[str, tk.Label] = {}
        self._tasks: Dict[str, str] = {}  # device_port -> "folder:operation"
        self._lock = threading.Lock()
        self._running = False
        self._update_thread: Optional[threading.Thread] = None
        self._root_window: Optional[tk.Tk] = None
        self._update_queue: queue.Queue = queue.Queue()
        self._gui_ready = threading.Event()
        self._device_ports: List[str] = []
        
    def start_monitor(self, device_ports: List[str]) -> None:
        """モニター表示を開始"""
        if self._running:
            logger.info("🖥️ タスクモニターは既に実行中です")
            return
            
        logger.info(f"🖥️ タスクモニター開始: {len(device_ports)}端末")
        self._running = True
        self._device_ports = device_ports.copy()
        
        # 初期化
        with self._lock:
            self._tasks = {port: "---:待機中" for port in device_ports}
        
        # GUI作成を別スレッドで開始（exe環境対応）
        gui_thread = threading.Thread(target=self._create_gui_safe, daemon=True)
        gui_thread.start()
        
        # GUIの準備完了を少し待つ
        if self._gui_ready.wait(timeout=5.0):
            logger.info("🖥️ タスクモニターGUIが準備完了")
        else:
            logger.warning("🖥️ タスクモニターGUIの準備がタイムアウト")
    
    def stop_monitor(self) -> None:
        """モニター表示を停止"""
        self._running = False
        
        if self._window:
            try:
                self._window.after(0, self._window.destroy)
            except:
                pass
                
        if self._root_window:
            try:
                self._root_window.after(0, self._root_window.quit)
            except:
                pass
    
    def update_task(self, device_port: str, folder: str, operation: str) -> None:
        """端末の処理状況を更新"""
        with self._lock:
            self._tasks[device_port] = f"{folder}:{operation}"
    
    def _create_gui_safe(self) -> None:
        """安全なGUI作成（exe環境対応）"""
        try:
            logger.info("🖥️ タスクモニターGUI作成開始")
            
            # tkinterの初期化（exe環境対応）
            self._setup_tkinter_for_exe()
            
            # 隠しrootウィンドウを作成
            self._root_window = tk.Tk()
            self._root_window.withdraw()  # 隠す
            self._root_window.title("TaskMonitor Root")
            
            # メインウィンドウを作成
            self._window = tk.Toplevel(self._root_window)
            self._window.title("実行中タスク")
            self._window.attributes('-topmost', True)
            self._window.resizable(False, False)
            
            # ウィンドウサイズを大きく設定（視認性重視）
            window_width = 500
            window_height = 150 + len(self._device_ports) * 40
            self._window.geometry(f"{window_width}x{window_height}")
            
            # ウィンドウを画面中央に配置（確実に見えるように）
            self._position_window_center()
            
            # スタイル設定（安全なフォント使用）
            try:
                style = ttk.Style()
                safe_font = get_safe_font(9)
                style.configure("TaskMonitor.TLabel", font=safe_font)
                logger.info(f"🖥️ 使用フォント: {safe_font[0]}")
            except Exception as e:
                logger.warning(f"スタイル設定失敗: {e}")
            
            # フレーム作成（パディングを大きく）
            main_frame = ttk.Frame(self._window, padding="20")
            main_frame.grid(row=0, column=0, sticky="nsew")
            
            # 大きなヘッダー（目立つように）
            header_font = get_safe_font(16, "bold")
            header_label = ttk.Label(main_frame, text="【実行中タスク】", 
                                   font=header_font,
                                   foreground="red")
            header_label.grid(row=0, column=0, columnspan=2, pady=(0, 20))
            
            # 各端末のラベルを作成（大きく見やすく）
            row = 1
            with self._lock:
                for i, device_port in enumerate(self._device_ports, 1):
                    task_info = self._tasks.get(device_port, "---:待機中")
                    
                    # 端末番号ラベル（大きなフォント）
                    port_font = get_safe_font(14, "bold")
                    port_label = ttk.Label(main_frame, text=f"端末{i}：", 
                                         font=port_font)
                    port_label.grid(row=row, column=0, sticky="w", padx=(0, 20), pady=5)
                    
                    # タスク情報ラベル（大きなフォント）
                    task_font = get_safe_font(14)
                    task_label = ttk.Label(main_frame, text=task_info, 
                                         font=task_font, width=30,
                                         background="lightyellow")
                    task_label.grid(row=row, column=1, sticky="w", pady=5)
                    
                    self._labels[device_port] = task_label
                    row += 1
            
            # 大きな閉じるボタン
            close_button = ttk.Button(main_frame, text="最小化", 
                                    command=self._minimize_window, width=20)
            close_button.grid(row=row, column=0, columnspan=2, pady=(20, 0))
            
            # テスト用の状態表示
            status_font = get_safe_font(12)
            status_label = ttk.Label(main_frame, text="タスクモニター起動中...", 
                                   font=status_font, foreground="blue")
            status_label.grid(row=row+1, column=0, columnspan=2, pady=(10, 0))
            
            # ウィンドウの閉じるボタンの動作を変更
            self._window.protocol("WM_DELETE_WINDOW", self._minimize_window)
            
            # ウィンドウを強制表示（複数回実行で確実に）
            for _ in range(3):
                self._window.deiconify()
                self._window.lift()
                self._window.focus_force()
                self._window.tkraise()
                self._window.attributes('-topmost', True)
                self._window.update_idletasks()
                time.sleep(0.1)
            
            # GUI準備完了を通知
            self._gui_ready.set()
            
            # 確認メッセージをコンソールにも出力
            print("🖥️ タスクモニターが画面中央に表示されました！")
            print(f"🖥️ ウィンドウサイズ: {500}x{150 + len(self._device_ports) * 40}")
            print("🖥️ 見えない場合は Alt+Tab でウィンドウを切り替えてください")
            
            # GUI更新ループを開始
            self._window.after(100, self._gui_update_loop)
            
            logger.info("🖥️ タスクモニターGUI作成完了")
            
            # メインループを開始
            self._root_window.mainloop()
            
        except Exception as e:
            logger.error(f"🖥️ GUI作成エラー: {e}", exc_info=True)
            self._gui_ready.set()  # エラーでも通知
    
    def _position_window_center(self) -> None:
        """ウィンドウを画面中央に配置（確実に見えるように）"""
        try:
            # 画面サイズを取得
            screen_width = self._window.winfo_screenwidth()
            screen_height = self._window.winfo_screenheight()
            
            # ウィンドウサイズ（大きく設定）
            window_width = 500
            window_height = 150 + len(self._device_ports) * 40
            
            # 画面中央に配置
            x = (screen_width - window_width) // 2
            y = (screen_height - window_height) // 2
            
            self._window.geometry(f"{window_width}x{window_height}+{x}+{y}")
            logger.info(f"🖥️ ウィンドウ中央配置: {window_width}x{window_height}+{x}+{y}")
            
        except Exception as e:
            logger.error(f"🖥️ ウィンドウ配置エラー: {e}")
            # エラー時はデフォルト位置
            self._window.geometry("500x400+100+100")
    
    def _position_window(self) -> None:
        """レガシー関数（互換性維持）"""
        self._position_window_center()
    
    def _minimize_window(self) -> None:
        """ウィンドウを最小化"""
        if self._window:
            self._window.iconify()
    
    def _gui_update_loop(self) -> None:
        """GUI更新ループ（GUIスレッドで実行）"""
        if not self._running or not self._window:
            return
            
        try:
            # タスク情報を更新
            updated = False
            with self._lock:
                for device_port, task_info in self._tasks.items():
                    if device_port in self._labels:
                        current_text = self._labels[device_port].cget("text")
                        if current_text != task_info:
                            self._labels[device_port].config(text=task_info)
                            updated = True
            
            if updated:
                self._window.update_idletasks()
            
            # 500ms後に再実行（負荷軽減）
            self._window.after(500, self._gui_update_loop)
            
        except Exception as e:
            logger.error(f"🖥️ GUI更新エラー: {e}")
            if self._running:
                self._window.after(1000, self._gui_update_loop)
    
    def _setup_tkinter_for_exe(self) -> None:
        """exe環境でのtkinter設定"""
        try:
            if is_exe_environment():
                # exe環境でのtkinter設定（安全な方法）
                import sys
                if hasattr(sys, '_MEIPASS'):
                    # PyInstallerで作成されたexeの場合、適切なパスを設定
                    tcl_path = os.path.join(sys._MEIPASS, 'tcl')
                    tk_path = os.path.join(sys._MEIPASS, 'tk') 
                    
                    if os.path.exists(tcl_path):
                        os.environ['TCL_LIBRARY'] = tcl_path
                        logger.info(f"🖥️ TCL_LIBRARY設定: {tcl_path}")
                    
                    if os.path.exists(tk_path):
                        os.environ['TK_LIBRARY'] = tk_path
                        logger.info(f"🖥️ TK_LIBRARY設定: {tk_path}")
                        
                    logger.info("🖥️ exe環境用tkinter設定完了")
                else:
                    logger.info("🖥️ 標準exe環境、デフォルト設定を使用")
        except Exception as e:
            logger.warning(f"🖥️ exe環境設定エラー: {e}")
            # エラー時はシステムデフォルトを使用

# グローバルインスタンス
_task_monitor: Optional[TaskMonitor] = None

def get_task_monitor() -> TaskMonitor:
    """タスクモニターのシングルトンインスタンスを取得"""
    global _task_monitor
    if _task_monitor is None:
        _task_monitor = TaskMonitor()
    return _task_monitor

def start_task_monitor(device_ports: List[str]) -> None:
    """タスクモニターを開始"""
    monitor = get_task_monitor()
    monitor.start_monitor(device_ports)

def stop_task_monitor() -> None:
    """タスクモニターを停止"""
    global _task_monitor
    if _task_monitor:
        _task_monitor.stop_monitor()
        _task_monitor = None

def update_device_task(device_port: str, folder: str, operation: str) -> None:
    """デバイスのタスク状況を更新
    
    Args:
        device_port: デバイスポート
        folder: フォルダ番号（例：001）  
        operation: 操作名（例：ID_check中）
    """
    global _task_monitor
    if _task_monitor:
        _task_monitor.update_task(device_port, folder, operation)

def test_task_monitor() -> None:
    """タスクモニターのテスト起動"""
    try:
        print("🖥️ タスクモニターテスト開始")
        logger.info("🖥️ タスクモニターテスト開始")
        
        test_ports = ["62001", "62025", "62026", "62027", "62028", "62029", "62030", "62031"]
        
        print(f"🖥️ {len(test_ports)}端末でタスクモニターを起動します...")
        start_task_monitor(test_ports)
        
        print("🖥️ 3秒後にテストデータを更新します...")
        time.sleep(3.0)
        
        # テストデータを更新
        for i, port in enumerate(test_ports):
            folder = f"{i+1:03d}"
            status = ["ID_check中", "login中", "待機中", "処理中", "完了"][i % 5]
            update_device_task(port, folder, status)
            print(f"🖥️ 端末{i+1}: {folder}:{status}")
            time.sleep(0.5)
        
        print("🖥️ タスクモニターテスト完了")
        logger.info("🖥️ タスクモニターテスト完了")
    except Exception as e:
        print(f"🖥️ タスクモニターテストエラー: {e}")
        logger.error(f"🖥️ タスクモニターテストエラー: {e}", exc_info=True)

def create_simple_test_window() -> None:
    """最もシンプルなテスト用ウィンドウを作成"""
    try:
        import tkinter as tk
        print("🖥️ シンプルテストウィンドウ作成中...")
        
        root = tk.Tk()
        root.title("タスクモニターテスト")
        root.geometry("600x400+200+200")
        root.attributes('-topmost', True)
        
        # 大きなテキスト
        test_font = get_safe_font(20, "bold")
        label = tk.Label(root, text="タスクモニターテスト画面", 
                        font=test_font, 
                        fg="red", bg="yellow")
        label.pack(expand=True)
        
        # 閉じるボタン
        button_font = get_safe_font(14)
        close_btn = tk.Button(root, text="閉じる", command=root.destroy,
                             font=button_font, width=20, height=2)
        close_btn.pack(pady=20)
        
        print("🖥️ シンプルテストウィンドウを表示しました！")
        root.mainloop()
        
    except Exception as e:
        print(f"🖥️ シンプルテストウィンドウエラー: {e}")

def force_show_task_monitor() -> None:
    """強制的にタスクモニターを表示"""
    global _task_monitor
    if _task_monitor and _task_monitor._window:
        try:
            _task_monitor._window.deiconify()
            _task_monitor._window.lift()
            _task_monitor._window.focus_force()
            logger.info("🖥️ タスクモニターを強制表示しました")
        except Exception as e:
            logger.error(f"🖥️ タスクモニター強制表示エラー: {e}")

def test_exe_gui_compatibility() -> bool:
    """exe環境でのGUI動作テスト"""
    try:
        print("🖥️ exe環境GUI互換性テスト開始...")
        logger.info("🖥️ exe環境GUI互換性テスト開始")
        
        # 1. exe環境の確認
        is_exe = is_exe_environment()
        print(f"🖥️ exe環境: {'Yes' if is_exe else 'No'}")
        
        # 2. tkinterの基本動作テスト
        import tkinter as tk
        test_root = tk.Tk()
        test_root.withdraw()  # 隠す
        
        # 3. フォント可用性テスト
        import tkinter.font as tkfont
        available_fonts = tkfont.families()
        safe_font = get_safe_font(12)
        print(f"🖥️ 利用可能フォント数: {len(available_fonts)}")
        print(f"🖥️ 選択されたフォント: {safe_font[0]}")
        
        # 4. 簡単なテストウィンドウ作成
        test_window = tk.Toplevel(test_root)
        test_window.title("GUI互換性テスト")
        test_window.geometry("300x200+100+100")
        
        # 5. ラベル作成テスト
        test_label = tk.Label(test_window, text="GUI動作テスト", font=safe_font)
        test_label.pack(pady=20)
        
        # 6. 短時間表示して閉じる
        test_window.update()
        time.sleep(1.0)  # 1秒表示
        
        test_window.destroy()
        test_root.destroy()
        
        print("🖥️ ✅ GUI互換性テスト成功！")
        logger.info("🖥️ GUI互換性テスト成功")
        return True
        
    except Exception as e:
        print(f"🖥️ ❌ GUI互換性テスト失敗: {e}")
        logger.error(f"🖥️ GUI互換性テスト失敗: {e}", exc_info=True)
        return False

# exe実行時の対応
def is_exe_environment() -> bool:
    """exe実行環境かどうかを判定"""
    return getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS')

def setup_exe_gui() -> None:
    """exe環境でのGUI設定（コンソール最小化を無効化）"""
    if is_exe_environment():
        logger.info("🖥️ exe環境を検出しました")
        # タスクモニター表示のため、コンソール最小化を無効化
        logger.info("🖥️ タスクモニター表示のためコンソール制御をスキップ")
        # 旧処理は無効化
        # import ctypes
        # try:
        #     hwnd = ctypes.windll.kernel32.GetConsoleWindow()
        #     if hwnd:
        #         ctypes.windll.user32.ShowWindow(hwnd, 6)  # SW_MINIMIZE
        #         logger.info("🖥️ コンソールウィンドウを最小化")
        # except Exception as e:
        #     logger.warning(f"🖥️ コンソール制御エラー: {e}")
