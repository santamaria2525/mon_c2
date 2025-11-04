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


def _create_root(topmost: bool = True) -> tk.Tk:
    """Create a Tk root window configured for dialogs."""
    root = tk.Tk()
    root.withdraw()

    try:
        root.wm_class("MSToolsDialog", "MSToolsDialog")
    except (AttributeError, tk.TclError):
        try:
            root.title("MSTools Dialog")
        except Exception:
            pass

    if topmost:
        try:
            root.attributes('-topmost', True)
        except (AttributeError, tk.TclError):
            pass

    try:
        root.tk.call('wm', 'group', root._w, '')
    except (AttributeError, tk.TclError):
        pass

    return root


@contextmanager
def _tk_root(*, topmost: bool = True):
    """Context manager that creates a hidden Tk root and cleans up."""
    root = _create_root(topmost=topmost)
    try:
        yield root
    finally:
        try:
            root.quit()
            root.destroy()
        except (AttributeError, tk.TclError):
            pass
