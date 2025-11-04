"""GUI dialog helpers."""

from __future__ import annotations
from .context import _tk_root
from .printing import _safe_print

from .common import (
    sys,
    time,
    threading,
    tk,
    simpledialog,
    ttk,
    messagebox,
    contextmanager,
    Dict,
    Callable,
    Optional,
    List,
    pyautogui,
    logger,
)

def display_message(title: str, message: str) -> None:
    """
    メッセージダイアログを表示
    
    Args:
        title: ダイアログのタイトル
        message: 表示するメッセージ
    """
    with _tk_root() as root:
        messagebox.showinfo(title, message)


def get_device_count() -> Optional[int]:
    """
    使用する端末台数を選択するダイアログを表示
    
    Returns:
        Optional[int]: 選択された端末台数、キャンセル時はNone
    """
    with _tk_root() as root:
        device_counts = ["3台", "4台", "5台", "6台", "7台", "8台"]
        
        # カスタムダイアログを作成
        dialog = tk.Toplevel(root)
        dialog.title("端末台数選択")
        dialog.geometry("300x250+400+300")
        dialog.resizable(False, False)
        dialog.grab_set()
        
        result = {"count": None}
        
        # ヘッダー
        header = tk.Label(dialog, text="何台の端末で実行しますか？", 
                         font=("MS Gothic", 12, "bold"))
        header.pack(pady=20)
        
        # ボタンフレーム
        button_frame = tk.Frame(dialog)
        button_frame.pack(pady=10)
        
        def select_count(count):
            result["count"] = count
            dialog.destroy()
        
        # 端末台数ボタン
        for i, count_text in enumerate(device_counts):
            count_num = i + 3  # 3台から8台
            btn = tk.Button(button_frame, text=count_text,
                           font=("MS Gothic", 10),
                           width=8, height=2,
                           command=lambda c=count_num: select_count(c))
            row = i // 3
            col = i % 3
            btn.grid(row=row, column=col, padx=5, pady=5)
        
        # キャンセルボタン
        cancel_btn = tk.Button(dialog, text="キャンセル",
                              command=dialog.destroy,
                              font=("MS Gothic", 10))
        cancel_btn.pack(pady=10)
        
        # ダイアログを中央に表示
        dialog.transient(root)
        dialog.focus_set()
        
        # モーダル処理
        dialog.wait_window()
        
        return result["count"]


def get_target_folder() -> Optional[str]:
    """
    ターゲットフォルダを入力するダイアログを表示
    
    Returns:
        Optional[str]: 入力されたフォルダ名、キャンセル時はNone
    """
    with _tk_root() as root:
        folder_name = simpledialog.askstring("Input", "対象のフォルダ名を入力してください:")
        if folder_name is None:
            return None
        return folder_name.zfill(3) if folder_name.isdigit() else folder_name


def get_name_prefix() -> str:
    """
    名前の接頭辞を入力するダイアログを表示
    
    Returns:
        str: 入力された接頭辞
    """
    with _tk_root() as root:
        prefix = simpledialog.askstring("Input", "名前の接頭辞を入力してください:")
        return prefix if prefix else ""


def select_device_port() -> Optional[str]:
    """
    デバイスポートを選択するダイアログを表示
    
    Returns:
        Optional[str]: 選択されたデバイスポート、キャンセル時はNone
    """
    try:
        import sys
        
        # デバイスポートオプション
        device_ports_options = [
            '127.0.0.1:62025', '127.0.0.1:62026', '127.0.0.1:62027',
            '127.0.0.1:62028', '127.0.0.1:62029', '127.0.0.1:62030',
            '127.0.0.1:62031', '127.0.0.1:62032'
        ]
        
        # EXE環境での特別対応
        if hasattr(sys, 'frozen'):
            try:
                # Non-interactive console fallback to avoid blocking
                try:
                    if not (getattr(sys, 'stdin', None) and sys.stdin.isatty()):
                        logger.info("Console non-interactive; defaulting to 127.0.0.1:62025")
                        return device_ports_options[0]
                except Exception:
                    return device_ports_options[0]
                # EXE環境での簡易コンソール選択
                _safe_print("\n=== シングル初期化 - デバイスポート選択 ===")
                _safe_print("利用可能なデバイスポート:")
                for i, port in enumerate(device_ports_options, 1):
                    _safe_print(f"{i}. {port}")
                
                while True:
                    try:
                        choice = input("\nポート番号を選択してください (1-8, 0=キャンセル): ").strip()
                        if choice == "0":
                            _safe_print("キャンセルされました。")
                            return None
                        
                        choice_num = int(choice)
                        if 1 <= choice_num <= len(device_ports_options):
                            selected = device_ports_options[choice_num - 1]
                            _safe_print(f"選択されたポート: {selected}")
                            return selected
                        else:
                            _safe_print("無効な番号です。1-8の範囲で選択してください。")
                    except (ValueError, KeyboardInterrupt):
                        _safe_print("無効な入力です。数字を入力してください。")
                        
            except Exception as console_error:
                logger.warning(f"コンソール選択エラー: {console_error}")
                # デフォルトポートを返す
                return device_ports_options[0]
        
        # 通常のGUI環境での処理
        result = [None]
        
        # Tkinterルートウィンドウを作成
        root = tk.Tk()
        try:
            # ウィンドウを最前面に強制表示
            root.withdraw()  # 一度隠す
            root.update()
            
            # ウィンドウ設定
            root.title('シングル初期化 - デバイス選択')
            root.geometry("450x280+200+200")
            root.resizable(False, False)
            root.configure(bg='#f0f0f0')
            
            # 最前面に表示
            root.attributes('-topmost', True)
            root.lift()
            root.focus_force()
            root.deiconify()  # ウィンドウを表示
            
            # メインフレーム
            main_frame = tk.Frame(root, bg='#f0f0f0', padx=30, pady=20)
            main_frame.pack(fill=tk.BOTH, expand=True)
            
            # タイトル
            title_label = tk.Label(
                main_frame,
                text="🔧 シングル初期化",
                font=('MS Gothic', 16, 'bold'),
                bg='#f0f0f0',
                fg='#2E7D32'
            )
            title_label.pack(pady=(0, 15))
            
            # 説明
            desc_label = tk.Label(
                main_frame,
                text="対象デバイスのポートを選択してください:",
                font=('MS Gothic', 12),
                bg='#f0f0f0',
                fg='#424242'
            )
            desc_label.pack(pady=(0, 20))
            
            # ポート選択フレーム
            port_frame = tk.Frame(main_frame, bg='#f0f0f0')
            port_frame.pack(pady=(0, 25))
            
            selected_port = tk.StringVar(value=device_ports_options[0])
            
            port_label = tk.Label(port_frame, text="ポート:", font=('MS Gothic', 11), bg='#f0f0f0')
            port_label.pack(side=tk.LEFT, padx=(0, 10))
            
            dropdown = ttk.Combobox(
                port_frame,
                textvariable=selected_port,
                values=device_ports_options,
                width=20,
                state='readonly',
                font=('MS Gothic', 11)
            )
            dropdown.pack(side=tk.LEFT)
            
            # ボタンフレーム
            button_frame = tk.Frame(main_frame, bg='#f0f0f0')
            button_frame.pack()
            
            def on_ok():
                result[0] = selected_port.get()
                root.quit()
                
            def on_cancel():
                result[0] = None
                root.quit()
            
            # OKボタン
            ok_button = tk.Button(
                button_frame,
                text="OK",
                command=on_ok,
                width=12,
                height=2,
                font=('MS Gothic', 11, 'bold'),
                bg='#4CAF50',
                fg='white',
                relief='raised',
                bd=2
            )
            ok_button.pack(side=tk.LEFT, padx=(0, 15))
            
            # キャンセルボタン
            cancel_button = tk.Button(
                button_frame,
                text="キャンセル",
                command=on_cancel,
                width=12,
                height=2,
                font=('MS Gothic', 11),
                bg='#FF5722',
                fg='white',
                relief='raised',
                bd=2
            )
            cancel_button.pack(side=tk.LEFT)
            
            # キーバインド
            root.bind('<Return>', lambda e: on_ok())
            root.bind('<Escape>', lambda e: on_cancel())
            
            # フォーカス設定と表示強制
            dropdown.focus_set()
            root.update()
            root.focus_force()
            
            # モーダル実行
            root.mainloop()
            
        finally:
            try:
                root.destroy()
            except:
                pass
                
        return result[0]
        
    except Exception as e:
        logger.error(f"デバイスポート選択エラー: {e}")
        import traceback
        logger.error(f"詳細: {traceback.format_exc()}")
        
        # フォールバック: デフォルトポートを返す
        logger.info("フォールバック: デフォルトポート 127.0.0.1:62025 を使用します")
        return '127.0.0.1:62025'
