"""
monst.image.constants - Constants for image processing.

画像処理で使用する共有定数をまとめています。
"""

from __future__ import annotations

import os

# ---- NOX制御関連 ---------------------------------------------------------

RESTART_VERBOSE = False
ERROR_LOG_INTERVAL = 3600
ERROR_MAIL_INTERVAL = 21600
MAX_ERRORS_BEFORE_RESTART = 100
MIN_CONSECUTIVE_ERRORS = 25
ERROR_COOLDOWN_PERIOD = 600
RECOVERY_CHECK_INTERVAL = 120
MAX_SCREENSHOT_CACHE_AGE = 60.0

DEVICE_RESTART_QUEUE_DELAY = 120
MAX_CONCURRENT_RESTARTS = 1

NOX_FRIENDLY_MODE = True
ENABLE_AUTO_RESTART = False
ENABLE_AUTO_RECOVERY = True

EMAIL_NOTIFICATION_DELAY = 10

NOX_EXE_PATH = r"C:\Program Files (x86)\Nox\bin\Nox.exe"

# ---- OCR/Tesseract -------------------------------------------------------

_DEFAULT_TESSERACT_PATH = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
# 環境変数 TESSERACT_CMD_PATH が設定されていれば最優先で採用
TESSERACT_CMD_PATH = os.getenv("TESSERACT_CMD_PATH", _DEFAULT_TESSERACT_PATH)
