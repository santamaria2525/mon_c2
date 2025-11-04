"""
image_detection.py - Backward compatibility layer for monst.image package.

このファイルは既存コードとの互換性を保つためのエイリアスレイヤーです。
新しいコードでは monst.image パッケージを直接使用することを推奨します。

Migration path:
  from image_detection import get_device_screenshot
  ↓
  from monst.image import get_device_screenshot
"""

from __future__ import annotations

import warnings

# 新しいパッケージから全ての公開関数をインポート
from monst.image import (
    get_device_screenshot,
    find_image_on_device,
    find_and_tap_image,
    tap_if_found,
    find_image_count,
    read_orb_count,
    tap_until_found,
    mon_swipe,
    setup_device_folder_mapping,
    type_folder_name,
    is_device_in_error_state,
    mark_device_error,
    mark_device_recovered,
    clear_device_cache,
    force_restart_nox_device,
    recover_device,
    monitor_nox_health,
    find_image_on_windows,
    find_and_tap_image_on_windows,
    tap_if_found_on_windows,
    tap_until_found_on_windows,
    get_image_path,
    get_image_path_for_windows,
)

# 互換性のためのエイリアス関数
def find_image_exact_range(device_port, image_name, subfolder=None):
    """find_image_on_deviceのエイリアス（互換性保持用）"""
    _warn_deprecation()
    if subfolder:
        return find_image_on_device(device_port, image_name, subfolder)
    else:
        return find_image_on_device(device_port, image_name)

# 廃止予定の警告（最初の呼び出し時のみ）
_deprecation_warned = False

def _warn_deprecation():
    global _deprecation_warned
    if not _deprecation_warned:
        warnings.warn(
            "image_detection.py is deprecated. Use 'from monst.image import ...' instead.",
            DeprecationWarning,
            stacklevel=3
        )
        _deprecation_warned = True

# 主要な関数にラッパーを追加（将来的な廃止準備）
_original_get_device_screenshot = get_device_screenshot

def get_device_screenshot(*args, **kwargs):
    _warn_deprecation()
    return _original_get_device_screenshot(*args, **kwargs)

_original_tap_if_found = tap_if_found

def tap_if_found(*args, **kwargs):
    _warn_deprecation()
    return _original_tap_if_found(*args, **kwargs)