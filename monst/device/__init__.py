"""
monst.device - Device operation workflows and business logic.

Public API exports for backward compatibility.
"""

from __future__ import annotations

from .core import device_operation_select
from .navigation import home
from .checks import icon_check
from .events import event_do
from .gacha import mon_gacha_shinshun
from .quest import device_operation_quest, reset_quest_state, get_quest_state
from .operations import (
    medal_change,
    mon_initial,
    mission_get,
    name_change,
    mon_sell,
    orb_count,
    perform_monster_sell,
)
from .hasya import continue_hasya, load_macro
from .exceptions import (
    DeviceOperationError,
    LoginError,
    GachaOperationError,
    SellOperationError,
    ScreenshotError,
)

# Re-export all functions for backward compatibility
__all__ = [
    "device_operation_select",
    "home",
    "icon_check",
    "event_do",
    "mon_gacha_shinshun",
    "device_operation_quest",
    "reset_quest_state",
    "get_quest_state",
    "medal_change",
    "mon_initial",
    "mission_get",
    "name_change",
    "mon_sell",
    "orb_count",
    "perform_monster_sell",
    "DeviceOperationError",
    "LoginError",
    "GachaOperationError",
    "SellOperationError",
    "ScreenshotError",
]