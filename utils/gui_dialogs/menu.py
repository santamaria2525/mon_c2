"""GUI dialog helpers."""

from __future__ import annotations
from .context import _tk_root
from .printing import _safe_print
from .dialogs import select_device_port

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

def gui_run(main_functions: Dict[str, Callable]) -> None:
    """
    機能選択GUIを表示して実行（ボタン形式）
    
    Args:
        main_functions: 関数名と実行関数のディクショナリ
    """
    result = {"selection": None}
    
    def show_dialog():
        nonlocal result
        
        # タスクモニターとの競合を回避するため、少し待機
        time.sleep(0.5)
        
        root = tk.Tk()
        root.title("NOX自動化ツール - 機能選択")
        
        # ウィンドウクラス名を設定してタスクモニターと区別
        try:
            root.wm_class("MainGUI", "MainGUI")
        except:
            pass
        
        # 関数数に応じてウィンドウサイズを調整
        functions_list = list(main_functions.keys())
        num_functions = len(functions_list)
        
        # 3列で配置、適切な高さを計算
        cols = 3
        rows = (num_functions + cols - 1) // cols  # 切り上げ計算
        
        button_width = 180
        button_height = 50
        padding = 15
        header_height = 80
        
        window_width = cols * button_width + (cols + 1) * padding
        window_height = header_height + rows * (button_height + padding) + padding
        
        # 画面中央に配置
        screen_width = root.winfo_screenwidth()
        screen_height = root.winfo_screenheight()
        x = (screen_width - window_width) // 2
        y = (screen_height - window_height) // 2
        root.geometry(f"{window_width}x{window_height}+{x}+{y}")
        
        # ウィンドウを最前面に
        root.attributes('-topmost', True)
        root.resizable(False, False)
        
        # メインフレーム
        main_frame = tk.Frame(root, bg='#f0f0f0')
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # ヘッダー
        header_frame = tk.Frame(main_frame, bg='#f0f0f0')
        header_frame.pack(fill=tk.X, pady=(0, 15))
        
        title_label = tk.Label(
            header_frame,
            text="実行する機能を選択してください",
            font=("Arial", 14, "bold"),
            bg='#f0f0f0',
            fg='#333333'
        )
        title_label.pack()
        
        subtitle_label = tk.Label(
            header_frame,
            text="ボタンをクリックして機能を実行",
            font=("Arial", 10),
            bg='#f0f0f0',
            fg='#666666'
        )
        subtitle_label.pack(pady=(5, 0))

        # ボタンフレーム
        buttons_frame = tk.Frame(main_frame, bg='#f0f0f0')
        buttons_frame.pack(expand=True)

        # ボタン作成関数
        def create_function_button(parent, text, command, row, col):
            btn = tk.Button(
                parent,
                text=text,
                command=command,
                width=18,
                height=2,
                font=("Arial", 10, "bold"),
                bg='#4CAF50',
                fg='white',
                relief='raised',
                bd=2,
                cursor='hand2'
            )
            btn.grid(row=row, column=col, padx=8, pady=8, sticky='nsew')
            
            # ホバーエフェクト
            def on_enter(e):
                btn.config(bg='#45a049')
            def on_leave(e):
                btn.config(bg='#4CAF50')
                
            btn.bind("<Enter>", on_enter)
            btn.bind("<Leave>", on_leave)
            
            return btn

        # 各機能のボタンを作成
        def execute_function(func_name):
            def wrapper():
                result["selection"] = func_name
                root.destroy()
            return wrapper

        # ボタンを配置
        for i, func_name in enumerate(functions_list):
            row = i // cols
            col = i % cols
            create_function_button(
                buttons_frame, 
                func_name, 
                execute_function(func_name),
                row, 
                col
            )

        # グリッドの列の重みを設定（均等に配置）
        for col in range(cols):
            buttons_frame.grid_columnconfigure(col, weight=1)

        # 終了ボタンフレーム
        exit_frame = tk.Frame(main_frame, bg='#f0f0f0')
        exit_frame.pack(fill=tk.X, pady=(15, 0))
        
        def cancel():
            root.destroy()

        exit_btn = tk.Button(
            exit_frame,
            text="終了",
            command=cancel,
            width=12,
            height=1,
            font=("Arial", 10),
            bg='#f44336',
            fg='white',
            relief='raised',
            bd=2,
            cursor='hand2'
        )
        exit_btn.pack()
        
        # ホバーエフェクト
        def on_exit_enter(e):
            exit_btn.config(bg='#da190b')
        def on_exit_leave(e):
            exit_btn.config(bg='#f44336')
            
        exit_btn.bind("<Enter>", on_exit_enter)
        exit_btn.bind("<Leave>", on_exit_leave)

        # キーボードショートカット
        root.bind('<Escape>', lambda event: cancel())
        
        # 最初のボタンにフォーカス
        root.focus_set()
        
        root.mainloop()

    # UIスレッドで実行（タスクモニターとの競合を避けるため）
    try:
        dialog_thread = threading.Thread(target=show_dialog, daemon=True)
        dialog_thread.start()
        dialog_thread.join(timeout=300)  # 5分でタイムアウト
        
        if dialog_thread.is_alive():
            _safe_print("⚠️ GUI応答なし - 強制終了")
            import sys
            import ctypes
            if hasattr(sys, 'frozen'):
                # exe環境では強制的にダイアログを閉じる
                try:
                    ctypes.windll.user32.SendMessageW(0xFFFF, 0x0010, 0, 0)  # WM_CLOSE
                except:
                    pass
    except Exception as e:
        _safe_print(f"⚠️ GUI起動エラー: {e}")
        # フォールバック: コンソール入力
        if 'functions' in locals():
            _safe_print("\n📋 利用可能な機能:")
            for i, name in enumerate(functions.keys(), 1):
                _safe_print(f"{i}. {name}")
            
            try:
                choice = input("\n機能を選択してください (番号): ")
                if choice.isdigit():
                    func_list = list(functions.keys())
                    idx = int(choice) - 1
                    if 0 <= idx < len(func_list):
                        selected_func = func_list[idx]
                        _safe_print(f"実行: {selected_func}")
                        functions[selected_func]()
            except KeyboardInterrupt:
                _safe_print("\n操作がキャンセルされました")
            except Exception as console_error:
                _safe_print(f"コンソール操作エラー: {console_error}")
    
    # 選択された関数を実行
    if result["selection"] in main_functions:
        main_functions[result["selection"]]()
