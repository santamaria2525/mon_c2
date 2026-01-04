"""
monst.image - Computer vision and device screenshot utilities.

Public API exports for backward compatibility.
"""

from __future__ import annotations

from .core import (
    get_device_screenshot,
    find_image_on_device,
    find_image_on_device_enhanced,
    find_and_tap_image,
    tap_if_found,
    find_image_count,
)
from .recognition import read_orb_count, read_account_name, save_account_name_image, save_orb_count_image, is_ocr_available
from .gacha_capture import save_character_ownership_image, save_full_gacha_screen_image
from .device_control import (
    tap_until_found,
    mon_swipe,
    setup_device_folder_mapping,
    type_folder_name,
)
from .device_management import (
    is_device_in_error_state,
    mark_device_error,
    mark_device_recovered,
    clear_device_cache,
    force_restart_nox_device,
    recover_device,
    monitor_nox_health,
)
from .windows_ui import (
    find_image_on_windows,
    find_and_tap_image_on_windows,
    tap_if_found_on_windows,
    tap_until_found_on_windows,
)
from .utils import get_image_path, get_image_path_for_windows
from ..device.navigation import home

# Re-export all functions for backward compatibility
__all__ = [
    "get_device_screenshot",
    "find_image_on_device", 
    "find_image_on_device_enhanced",
    "find_and_tap_image",
    "tap_if_found",
    "find_image_count",
    "read_orb_count",
    "read_account_name",
    "save_account_name_image",
    "save_orb_count_image",
    "is_ocr_available",
    "save_character_ownership_image",
    "save_full_gacha_screen_image",
    "tap_until_found",
    "mon_swipe",
    "setup_device_folder_mapping",
    "type_folder_name",
    "is_device_in_error_state",
    "mark_device_error",
    "mark_device_recovered",
    "clear_device_cache",
    "force_restart_nox_device",
    "recover_device",
    "monitor_nox_health",
    "find_image_on_windows",
    "find_and_tap_image_on_windows", 
    "tap_if_found_on_windows",
    "tap_until_found_on_windows",
    "get_image_path",
    "get_image_path_for_windows",
    "home",
]
