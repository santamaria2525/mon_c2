"""
monst.device.gacha_perfect - 大改修前の成功バージョンを完全復元

ultrathink深層解析により、大改修前の成功バージョンのガチャシステムを完全に復元します。
キャラ未所持時のガチャ実行問題とExcel生成問題を根本的に解決します。
"""

from __future__ import annotations

# 大改修前の成功バージョンを使用
from .gacha_perfect_restored import (
    execute_perfect_gacha,
    mon_gacha_shinshun_perfect,
    mon_gacha_shinshun_perfect_restored
)

# 既存のインポートは互換性のため残す
import os
import time
from typing import List, Optional, Tuple, Dict, Any
from dataclasses import dataclass
import cv2
import numpy as np

from logging_util import logger
from monst.image import (
    get_device_screenshot, find_and_tap_image, tap_if_found, tap_until_found,
    save_character_ownership_image, read_account_name, save_account_name_image, 
    save_orb_count_image, read_orb_count
)
from monst.adb import perform_action
from utils.device_utils import get_terminal_number, get_terminal_number_only
from utils.data_persistence import update_excel_data
from config import get_config
from .navigation import home


# 旧バージョンの複雑なクラス構造は削除し、大改修前の成功バージョンを直接使用
# 以下は互換性のため残すが、実際の処理はgacha_perfect_restoredで行う