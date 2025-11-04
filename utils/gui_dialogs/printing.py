"""GUI dialog helpers."""

from __future__ import annotations

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

def _safe_print(message: str) -> None:
    try:
        print(message)
    except UnicodeEncodeError:
        encoding = getattr(sys.stdout, 'encoding', None) or 'utf-8'
        safe = message.encode(encoding, errors='replace').decode(encoding, errors='replace')
        print(safe)
