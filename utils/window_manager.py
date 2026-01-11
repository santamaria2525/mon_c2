"""
Window management utilities for Monster Strike Bot.

Provides helpers for:
- Window enumeration and activation
- Console window positioning
- Right-click automation for NOX instances
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes
import time
from collections import deque
from typing import Any, List, Optional, Tuple, Sequence
import threading

import pyautogui
import pygetwindow as gw

from logging_util import logger

# ---------------------------------------------------------------------------
# Tunable constants
# ---------------------------------------------------------------------------
WINDOW_ACTIVATION_RETRIES = 4
WINDOW_OPERATION_DELAY = 1.0
MOUSE_CLICK_DELAY = 0.3
MOUSE_OPERATION_DELAY = 0.5
SAFE_SCREEN_MARGIN = 50
RIGHT_CLICK_OFFSET = (150, 150)
RIGHT_CLICK_MOVE_DURATION_PRIMARY = 0.35
RIGHT_CLICK_MOVE_DURATION_SECONDARY = 0.25
RIGHT_CLICK_HOLD_PRIMARY = 0.12
RIGHT_CLICK_HOLD_SECONDARY = 0.18
RIGHT_CLICK_INTER_CLICK_DELAY = 0.55
_dialog_monitor_lock = threading.Lock()
_dialog_monitor_thread = None
_dialog_monitor_stop = threading.Event()
_NOX_WIDGET_KEYWORDS = ("noxウィジェット", "nox widget")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------
def _collect_windows(include_hidden: bool = True) -> List[Any]:
    """Return all top-level windows, optionally skipping hidden ones."""
    try:
        windows = gw.getAllWindows()
    except Exception as exc:
        logger.debug("Window enumeration failed: %s", exc)
        return []

    if include_hidden:
        return windows

    return [w for w in windows if getattr(w, "visible", True)]


def _matches_title(
    window_title: str,
    keyword: str,
    *,
    exact: bool,
    case_insensitive: bool,
) -> bool:
    """Check whether a window title matches the requested keyword."""
    if case_insensitive:
        window_title = window_title.lower()
        keyword = keyword.lower()
    return window_title == keyword if exact else keyword in window_title


def _post_wm_close(hwnd: int) -> bool:
    try:
        ctypes.windll.user32.PostMessageW(hwnd, 0x0010, 0, 0)  # WM_CLOSE
        return True
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug("Unable to post WM_CLOSE: %s", exc)
        return False


def _close_window(window: Any) -> bool:
    """Attempt to close a pygetwindow window instance."""
    title = window.title or ""
    try:
        window.close()
        return True
    except Exception as close_error:
        hwnd = getattr(window, "_hWnd", None)
        if hwnd:
            if _post_wm_close(hwnd):
                return True
            logger.debug("Unable to close window '%s' via WM_CLOSE", title)
        else:
            logger.debug("No HWND available for window '%s': %s", title, close_error)
    return False


def _is_nox_widget(title: str) -> bool:
    """Return True when the window title indicates the NOX widget popup."""
    if not title:
        return False
    lowered = title.lower()
    return any(keyword in lowered for keyword in _NOX_WIDGET_KEYWORDS)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def close_windows_by_title(
    title_keyword: str,
    *,
    exact: bool = False,
    include_hidden: bool = False,
    case_insensitive: bool = False,
    exclude_keywords: Optional[Sequence[str]] = None,
) -> int:
    """Close all windows whose title matches ``title_keyword``."""
    windows = _collect_windows(include_hidden=include_hidden)
    closed = 0
    excludes_lower = tuple((kw or "").lower() for kw in exclude_keywords or ())

    for window in windows:
        try:
            title = window.title or ""
            lowered_title = title.lower()

            if excludes_lower and any(ex_kw in lowered_title for ex_kw in excludes_lower):
                continue
            if not _matches_title(
                title,
                title_keyword,
                exact=exact,
                case_insensitive=case_insensitive,
            ):
                continue

            if not include_hidden and not getattr(window, "visible", True):
                continue

            if _close_window(window):
                closed += 1
                time.sleep(0.1)
            else:
                logger.debug("Failed to close window '%s'", title)
        except Exception as exc:
            logger.debug("Window close attempt failed: %s", exc)

    if closed:
        logger.debug("Closed %d window(s) matching '%s'", closed, title_keyword)

    return closed


def close_adb_error_dialogs() -> int:
    """Close adb.exe application error dialogs shown by Windows."""
    windows = _collect_windows(include_hidden=True)
    closed = 0
    now = time.time()
    if not hasattr(close_adb_error_dialogs, "_recent"):
        close_adb_error_dialogs._recent = deque()  # type: ignore[attr-defined]
        close_adb_error_dialogs._last_recovery = 0.0  # type: ignore[attr-defined]

    for window in windows:
        try:
            title = (window.title or "").strip()
            if not title:
                continue

            lower = title.lower()
            if "adb.exe" not in lower:
                continue

            if "application error" not in lower and "エラー" not in title:
                continue

            if _close_window(window):
                closed += 1
                time.sleep(0.1)
        except Exception as exc:
            logger.debug("ADB error window handling failed: %s", exc)

    if closed:
        logger.info("ADB エラーダイアログを %d 件閉じました", closed)
        recent = close_adb_error_dialogs._recent  # type: ignore[attr-defined]
        recent.append(now)
        while recent and now - recent[0] > 60.0:
            recent.popleft()
        if len(recent) >= 5:
            last_recovery = close_adb_error_dialogs._last_recovery  # type: ignore[attr-defined]
            if now - last_recovery > 120.0:
                close_adb_error_dialogs._last_recovery = now  # type: ignore[attr-defined]
                try:
                    from adb_utils import reset_adb_server
                    logger.warning("ADB エラーダイアログが連続発生したため ADB を再起動します")
                    reset_adb_server(force=True)
                except Exception as exc:
                    logger.debug("ADB reset from dialog monitor failed: %s", exc)

    return closed

def close_nox_error_dialogs() -> int:
    """Close common NOX crash/error dialogs on Windows."""
    error_keywords = [
        "nox",
        "noxplayer",
        "noxvm",
        "bignox",
        "noxpack",
        "ご注意",
    ]

    extra_terms = [
        "error",
        "stopped working",
        "not responding",
        "蜍穂ｽ懊ｒ蛛懈ｭ｢",
        "蠢懃ｭ斐＠縺ｦ縺・∪縺帙ｓ",
        "繧ｨ繝ｩ繝ｼ",
        "仮想マシン",
        "フィードバック",
        "1040",
    ]
    vm_failure_terms = {"仮想マシン", "フィードバック", "1040"}

    closed = 0

    # First pass: direct keyword match
    vm_failure_detected = False

    for keyword in error_keywords:
        closed += close_windows_by_title(
            keyword,
            include_hidden=True,
            case_insensitive=True,
            exclude_keywords=_NOX_WIDGET_KEYWORDS,
        )

    # Second pass: relaxed matching with additional error phrases
    keyword_lower = [kw.lower() for kw in error_keywords]
    extra_lower = [term.lower() for term in extra_terms]
    for window in _collect_windows(include_hidden=True):

        try:
            title = (window.title or "").strip()
            if not title:
                continue

            if _is_nox_widget(title):
                continue

            lower = title.lower()
            matches_base = any(base in lower for base in keyword_lower)
            if not matches_base and "ご注意" not in lower:
                continue
            matches_extra = any(term in lower for term in extra_lower)
            if not matches_extra:
                continue

            if _close_window(window):
                closed += 1
                if any(term in lower for term in vm_failure_terms):
                    vm_failure_detected = True
                time.sleep(0.1)
        except Exception as exc:
            logger.debug("NOX error window handling failed: %s", exc)

    if closed:
        logger.info("NOX 繧ｨ繝ｩ繝ｼ繝繧､繧｢繝ｭ繧ｰ繧・%d 莉ｶ髢峨§縺ｾ縺励◆", closed)
    if vm_failure_detected:
        try:
            from monst.image.device_management import notify_virtual_machine_failure
            notify_virtual_machine_failure()
        except Exception as exc:
            logger.debug("Failed to notify virtual machine failure: %s", exc)

    return closed


def close_adb_error_dialogs() -> int:
    """Close adb.exe application error dialogs shown by Windows."""
    windows = _collect_windows(include_hidden=True)
    closed = 0

    for window in windows:
        try:
            title = (window.title or "").strip()
            if not title:
                continue

            lower = title.lower()
            if "adb.exe" not in lower:
                continue

            if "application error" not in lower and "エラー" not in title:
                continue

            if _close_window(window):
                closed += 1
                time.sleep(0.1)
        except Exception as exc:
            logger.debug("ADB error window handling failed: %s", exc)

    if closed:
        logger.info("ADB エラーダイアログを %d 件閉じました", closed)

    return closed


def _dialog_monitor_loop(interval: float) -> None:
    while not _dialog_monitor_stop.wait(interval):
        try:
            closed = 0
            closed += close_adb_error_dialogs()
            closed += close_nox_error_dialogs()
            if not closed:
                close_windows_by_title(
                    "adb.exe - アプリケーション エラー", include_hidden=True, case_insensitive=True
                )
        except Exception as exc:
            logger.debug("Error dialog monitor loop failed: %s", exc)


def start_error_dialog_monitor(interval: float = 5.0) -> None:
    """Start a background thread that continuously dismisses error dialogs."""
    global _dialog_monitor_thread
    with _dialog_monitor_lock:
        if _dialog_monitor_thread and _dialog_monitor_thread.is_alive():
            return
        _dialog_monitor_stop.clear()
        _dialog_monitor_thread = threading.Thread(
            target=_dialog_monitor_loop,
            args=(max(1.0, interval),),
            name="ErrorDialogMonitor",
            daemon=True,
        )
        _dialog_monitor_thread.start()


def stop_error_dialog_monitor() -> None:
    global _dialog_monitor_thread
    with _dialog_monitor_lock:
        if not _dialog_monitor_thread:
            return
        _dialog_monitor_stop.set()
        _dialog_monitor_thread.join(timeout=2.0)
        _dialog_monitor_thread = None


def handle_windows(title: str = "monst_macro") -> bool:
    """Search windows by title and send an Enter key press."""
    for attempt in range(2):
        try:
            windows = gw.getWindowsWithTitle(title)
        except Exception as exc:
            logger.error("繧ｦ繧｣繝ｳ繝峨え讀懃ｴ｢縺ｫ螟ｱ謨励＠縺ｾ縺励◆: %s", exc)
            return False

        if not windows:
            logger.debug("蟇ｾ雎｡繧ｦ繧｣繝ｳ繝峨え縺瑚ｦ九▽縺九ｊ縺ｾ縺帙ｓ: %s", title)
            time.sleep(WINDOW_OPERATION_DELAY)
            continue

        success = False
        for window in windows:
            try:
                window.activate()
                time.sleep(WINDOW_OPERATION_DELAY)
                pyautogui.press("enter")
                time.sleep(WINDOW_OPERATION_DELAY)
                success = True
            except Exception as exc:
                logger.warning("繧ｦ繧｣繝ｳ繝峨え謫堺ｽ懊〒繧ｨ繝ｩ繝ｼ: %s", exc)

        if success:
            return True

        time.sleep(WINDOW_OPERATION_DELAY)

    return False


def set_console_window_size_and_position(width: int, height: int, x: int, y: int) -> bool:
    """Set console window size and position, keeping the window in the background."""
    try:
        hwnd = ctypes.windll.kernel32.GetConsoleWindow()
        if not hwnd:
            return False

        HWND_BOTTOM = 1
        SW_RESTORE = 9
        SWP_NOACTIVATE = 0x0010

        ctypes.windll.user32.ShowWindow(hwnd, SW_RESTORE)
        time.sleep(0.1)

        result = ctypes.windll.user32.SetWindowPos(
            hwnd,
            HWND_BOTTOM,
            x,
            y,
            width,
            height,
            SWP_NOACTIVATE,
        )

        if result:
            try:
                STD_OUTPUT_HANDLE = -11
                handle = ctypes.windll.kernel32.GetStdHandle(STD_OUTPUT_HANDLE)
                buffer_width = max(60, width // 10)
                buffer_height = max(20, height // 15)
                ctypes.windll.kernel32.SetConsoleScreenBufferSize(
                    handle,
                    ctypes.wintypes._COORD(buffer_width, buffer_height),
                )
            except Exception:
                pass

            logger.debug(
                "繧ｳ繝ｳ繧ｽ繝ｼ繝ｫ繧ｦ繧｣繝ｳ繝峨え險ｭ螳壼ｮ御ｺ・ %dx%d at (%d,%d)",
                width,
                height,
                x,
                y,
            )
            return True

        logger.warning("繧ｳ繝ｳ繧ｽ繝ｼ繝ｫ繧ｦ繧｣繝ｳ繝峨え縺ｮ菴咲ｽｮ險ｭ螳壹↓螟ｱ謨励＠縺ｾ縺励◆")
        return False

    except Exception as exc:
        logger.error("繧ｳ繝ｳ繧ｽ繝ｼ繝ｫ繧ｦ繧｣繝ｳ繝峨え險ｭ螳壹お繝ｩ繝ｼ: %s", exc)
        return False


# ---------------------------------------------------------------------------
# NOX window activation helpers
# ---------------------------------------------------------------------------
def _find_target_window(window_title: str) -> Optional[Any]:
    for window in _collect_windows(include_hidden=True):
        title = window.title or ""
        normalized_title = title.lstrip()
        if (
            normalized_title.startswith(window_title)
            and getattr(window, "visible", True)
            and window.width > 100
            and window.height > 100
        ):
            return window
    return None

def _bring_to_foreground(window: Any) -> None:
    title = window.title
    try:
        import win32con
        import win32gui

        hwnd = win32gui.FindWindow(None, title)
        if hwnd:
            win32gui.SetForegroundWindow(hwnd)
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            time.sleep(0.5)
            return
    except ImportError:
        pass
    except Exception:
        pass

    hwnd = getattr(window, "_hWnd", None) or ctypes.windll.user32.FindWindowW(None, title)
    if hwnd:
        ctypes.windll.user32.SetForegroundWindow(hwnd)
        ctypes.windll.user32.ShowWindow(hwnd, 9)  # SW_RESTORE
        time.sleep(0.5)


def _activate_window(window: Any, retries: int) -> bool:
    for attempt in range(retries):
        try:
            _bring_to_foreground(window)
            window.activate()
            time.sleep(1.0)

            active = gw.getActiveWindow()
            if (
                active
                and active.title == window.title
                and abs(window.left - active.left) < 10
            ):
                logger.info(
                    "NOX遶ｯ譛ｫ%s縺ｮ繧｢繧ｯ繝・ぅ繝門喧謌仙粥 (隧ｦ陦・%d)",
                    window.title,
                    attempt + 1,
                )
                return True

            logger.warning(
                "NOX遶ｯ譛ｫ%s縺ｮ繧｢繧ｯ繝・ぅ繝門喧遒ｺ隱榊､ｱ謨・(隧ｦ陦・%d)",
                window.title,
                attempt + 1,
            )
        except Exception as exc:
            logger.warning(
                "NOX遶ｯ譛ｫ%s繧｢繧ｯ繝・ぅ繝門喧繧ｨ繝ｩ繝ｼ: %s (隧ｦ陦・%d/%d)",
                window.title,
                exc,
                attempt + 1,
                retries,
            )

        time.sleep(1.0)

    return False


def _compute_safe_click_point(window: Any) -> Tuple[int, int]:
    click_x = window.left + RIGHT_CLICK_OFFSET[0]
    click_y = window.top + RIGHT_CLICK_OFFSET[1]
    screen_width, screen_height = pyautogui.size()

    safe_x = max(SAFE_SCREEN_MARGIN, min(click_x, screen_width - SAFE_SCREEN_MARGIN))
    safe_y = max(SAFE_SCREEN_MARGIN, min(click_y, screen_height - SAFE_SCREEN_MARGIN))
    return safe_x, safe_y


def _perform_context_click(x: int, y: int) -> None:
    pyautogui.moveTo(x, y, duration=RIGHT_CLICK_MOVE_DURATION_PRIMARY)
    time.sleep(MOUSE_OPERATION_DELAY)

    pyautogui.mouseDown(x=x, y=y, button='right')
    time.sleep(RIGHT_CLICK_HOLD_PRIMARY)
    pyautogui.mouseUp(x=x, y=y, button='right')
    logger.info("NOX繧ｦ繧｣繝ｳ繝峨え縺ｧ蜿ｳ繧ｯ繝ｪ繝・け螳溯｡・(荳谺｡)")

    time.sleep(RIGHT_CLICK_INTER_CLICK_DELAY)
    pyautogui.moveTo(x, y, duration=RIGHT_CLICK_MOVE_DURATION_SECONDARY)
    time.sleep(0.2)

    pyautogui.mouseDown(x=x, y=y, button='right')
    time.sleep(RIGHT_CLICK_HOLD_SECONDARY)
    pyautogui.mouseUp(x=x, y=y, button='right')
    logger.info("NOX繧ｦ繧｣繝ｳ繝峨え縺ｧ蜿ｳ繧ｯ繝ｪ繝・け螳溯｡・(遒ｺ隱・")
    time.sleep(MOUSE_CLICK_DELAY)


def activate_window_and_right_click(window_title: str, retries: Optional[int] = None) -> bool:
    """Activate a NOX window and perform two right clicks at a safe location."""
    retries = retries or WINDOW_ACTIVATION_RETRIES

    window = _find_target_window(window_title)
    if window is None:
        logger.error("NOX遶ｯ譛ｫ繧ｦ繧｣繝ｳ繝峨え縺瑚ｦ九▽縺九ｊ縺ｾ縺帙ｓ: %s", window_title)
        return False

    logger.info(
        "NOX遶ｯ譛ｫ%s縺ｮ繧｢繧ｯ繝・ぅ繝門喧髢句ｧ・ %dx%d (%dx%d)",
        window_title,
        window.left,
        window.top,
        window.width,
        window.height,
    )

    if not _activate_window(window, retries):
        logger.error("NOX遶ｯ譛ｫ%s縺ｮ繧｢繧ｯ繝・ぅ繝門喧縺ｫ螟ｱ謨励＠縺ｾ縺励◆", window_title)
        return False

    time.sleep(0.5)

    click_x, click_y = _compute_safe_click_point(window)
    logger.info(
        "蜿ｳ繧ｯ繝ｪ繝・け蠎ｧ讓呻ｼ医Ο繧ｰ繧､繝ｳ菴咲ｽｮ貅匁侠・・ (%d, %d)",
        click_x,
        click_y,
    )

    try:
        _perform_context_click(click_x, click_y)
        return True
    except Exception as exc:
        logger.error("NOX遶ｯ譛ｫ%s謫堺ｽ應ｸｭ縺ｫ繧ｨ繝ｩ繝ｼ: %s", window_title, exc)
        return False
