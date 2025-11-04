"""
Declarative mapping between GUI menu labels and operation entry points.

Keeping this mapping in a dedicated module allows both GUI and future shortcut
providers to reuse the same configuration without duplicating strings.
"""

from __future__ import annotations

from typing import Callable, Dict, Optional


MenuCallback = Optional[Callable[[], None]]


def build_menu(operations) -> Dict[str, MenuCallback]:
    """Return the GUI menu definition backed by the operations facade."""
    return {
        "セレクト": operations.run_select_loop,
        "マクロ": operations.run_macro,
        "1set書き込み": operations.write_set,
        "ログインループ": operations.run_login_loop,
        "ループ(STOP)": operations.run_continuous_login_loop,
        "覇者": operations.run_hasya_loop,
        "クエスト": operations.run_event_loop,
        "シングル書き込み": operations.write_single,
        "シングル初期化": operations.reset_single,
        "シングル保存": operations.save_single,
        "フレンド登録システム": operations.run_friend_registration,
        "エクセルから引継ぎ保存": operations.run_account_backup,
        "指定画像クリック": operations.run_shitei_click,
        "---": None,
        "MMフォルダ切替": operations.split_mm_folder,
        "フォルダ一括リネーム": operations.batch_rename_mm_folder,
    }
