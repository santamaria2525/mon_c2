# -*- coding: utf-8 -*-
"""Standalone helpers for MMフォルダ関連のユーティリティ."""

from __future__ import annotations

import os
import tkinter as tk
from tkinter import filedialog
from typing import Dict

from logging_util import logger
from utils import (
    create_mm_folders,
    batch_rename_folders_csv,
    batch_rename_folders_excel,
    display_message,
)


def split_mm_folder() -> None:
    """Create MM folders under ``bin_push`` and report the result."""
    logger.info("MMフォルダ振り分けを開始します")
    try:
        stats: Dict[str, int] = create_mm_folders()
    except Exception as exc:  # pragma: no cover - legacy helper
        logger.error("MMフォルダの生成に失敗しました: %s", exc)
        display_message("エラー", f"MMフォルダの作成に失敗しました。\n\n詳細:\n{exc}")
        return

    total = sum(stats.values())
    if total <= 0:
        logger.warning("MMフォルダ生成対象が見つかりませんでした")
        display_message("MMフォルダ", "bin_push 配下に分割対象のフォルダが見つかりません。")
        return

    result_lines = [f"{mm_label}: {count} 件" for mm_label, count in stats.items() if count > 0]
    body = ["MMフォルダ作成結果", f"合計: {total} 件"]
    body.extend(result_lines)
    display_message("MMフォルダ", "\n".join(body))
    logger.info("MMフォルダ振り分け完了: %d 件", total)


def batch_rename_mm_folder() -> None:
    """Rename MM folders based on Excel/CSV mapping."""
    logger.info("MMフォルダ一括リネームを開始します")
    root = tk.Tk()
    root.withdraw()
    root.lift()
    root.attributes("-topmost", True)

    try:
        default_excel = os.path.join(os.getcwd(), "folder_change.xlsx")
        initial_dir = os.path.dirname(default_excel) if os.path.exists(default_excel) else os.getcwd()
        initial_file = "folder_change.xlsx" if os.path.exists(default_excel) else ""

        excel_path = filedialog.askopenfilename(
            title="MMフォルダ変更用のExcelまたはCSVを選択してください",
            filetypes=[
                ("Excel files", "*.xlsx"),
                ("Excel files (old)", "*.xls"),
                ("CSV files", "*.csv"),
                ("All files", "*.*"),
            ],
            defaultextension=".xlsx",
            initialdir=initial_dir,
            initialfile=initial_file,
        )
    finally:
        root.destroy()

    if not excel_path:
        logger.info("MMフォルダ一括リネーム: ファイル選択がキャンセルされました")
        return

    ext = os.path.splitext(excel_path)[1].lower()
    try:
        if ext in (".xlsx", ".xls"):
            results = batch_rename_folders_excel(excel_path)
            source_type = "Excel"
        elif ext == ".csv":
            results = batch_rename_folders_csv(excel_path)
            source_type = "CSV"
        else:
            display_message("エラー", f"未対応のファイル形式です: {ext}")
            return
    except Exception as exc:  # pragma: no cover - legacy helper
        logger.error("MMフォルダ一括リネームに失敗しました: %s", exc)
        display_message("エラー", f"フォルダ名の更新に失敗しました。\n\n詳細:\n{exc}")
        return

    if not results:
        display_message("MMフォルダ", f"{source_type} に有効な指示がありませんでした。")
        return

    success = [folder for folder, ok in results.items() if ok]
    failed = [folder for folder, ok in results.items() if not ok]
    body = [
        "MMフォルダ一括リネーム結果",
        f"対象: {len(results)} 件",
        f"成功: {len(success)} 件",
        f"失敗: {len(failed)} 件",
    ]
    if success:
        preview = ", ".join(success[:10])
        body.append(f"成功フォルダ例: {preview}")
    if failed:
        preview = ", ".join(failed[:5])
        body.append(f"失敗フォルダ例: {preview}")

    display_message("MMフォルダ", "\n".join(body))
    logger.info(
        "MMフォルダ一括リネーム完了: %d 件中 %d 件成功, %d 件失敗",
        len(results),
        len(success),
        len(failed),
    )
