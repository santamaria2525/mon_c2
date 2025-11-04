"""
monst.image.constants - Constants for image processing.

画像処理に関する定数定義
"""

from __future__ import annotations

# エラー管理用の定数 - NOX再起動制御
RESTART_VERBOSE = False 
ERROR_LOG_INTERVAL = 3600  # エラーログの出力間隔（秒）
ERROR_MAIL_INTERVAL = 21600  # エラーメール通知の間隔（秒）
MAX_ERRORS_BEFORE_RESTART = 100  # 再起動するまでのエラー回数閾値（大幅増加）
MIN_CONSECUTIVE_ERRORS = 25  # 連続エラーの最小数（大幅増加）
ERROR_COOLDOWN_PERIOD = 600  # 再起動のクールダウン期間（秒）- 10分に延長
RECOVERY_CHECK_INTERVAL = 120  # 回復確認の間隔（秒）- 2分に延長（安定性重視）
MAX_SCREENSHOT_CACHE_AGE = 60.0  # スクリーンショットキャッシュの最大有効期間（秒）- 8端末対応で延長

# デバイス再起動制御
DEVICE_RESTART_QUEUE_DELAY = 120  # デバイス間再起動の最小間隔（秒）- 大幅延長
MAX_CONCURRENT_RESTARTS = 1  # 同時再起動可能デバイス数を1に制限（安定性重視）

# NOX安定性重視設定
NOX_FRIENDLY_MODE = True  # NOX優先モード
ENABLE_AUTO_RESTART = False  # 自動再起動機能を無効化（安定性重視）
ENABLE_AUTO_RECOVERY = True  # 自動回復機能は維持（軽微な回復のみ）

# 通知遅延
EMAIL_NOTIFICATION_DELAY = 10  # 10秒間はメール送信を遅らせる

# NOXのパス
NOX_EXE_PATH = r"C:\Program Files (x86)\Nox\bin\Nox.exe"

# Tesseractのパス
TESSERACT_CMD_PATH = r'C:\Program Files\Tesseract-OCR\tesseract.exe'