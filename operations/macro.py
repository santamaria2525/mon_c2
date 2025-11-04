# -*- coding: utf-8 -*-
"""
Macro execution workflow for the cleaned codebase.
"""

from __future__ import annotations

from logging_util import logger
from missing_functions import load_macro
from utils import display_message, get_target_folder

from .helpers import cleanup_macro_windows


class MacroRunner:
    """Handle macro selection and execution."""

    def __init__(self, core):
        self.core = core

    def run(self) -> None:
        """Prompt for a macro number and launch it."""
        base = get_target_folder()
        if base is None:
            logger.warning("フォルダが選択されませんでした。")
            return

        try:
            macro_number = int(base)
        except ValueError:
            logger.error("無効なフォルダ番号: %s", base)
            display_message("エラー", "有効なフォルダ番号を入力してください。")
            return

        closed = cleanup_macro_windows()
        if closed:
            logger.debug("Closed %d leftover macro windows before launch.", closed)

        try:
            load_macro(macro_number)
            logger.info("マクロ %d を実行しました。", macro_number)
        except Exception as exc:
            logger.error("マクロの読み込みに失敗しました: %s", exc)
            display_message("エラー", f"マクロの読み込みに失敗しました。\n\n詳細: {exc}")
        finally:
            closed_after = cleanup_macro_windows()
            if closed_after:
                logger.info("Closed %d stray macro menu window(s) after launch.", closed_after)
