"""
Crash detection and recovery helpers for the automation flow.

Monster Strike がホーム画面に戻ってしまった場合に、再起動と復旧を試みる。
"""

from __future__ import annotations

import time
from typing import Any, Callable, Sequence, Tuple

from logging_util import logger
from image_detection import tap_if_found
from monst.image import find_image_on_device
from adb_utils import start_monster_strike_app
from utils import close_nox_error_dialogs

HOME_SCREEN_ICONS: Sequence[Tuple[str, str]] = (
    ("icon.png", "login"),
    ("icon12.png", "login"),
)

MAX_ICON_ATTEMPTS = 3
ICON_TAP_DELAY = 5.0
ICON_RETRY_SLEEP = 2.0
FORCED_LAUNCH_SLEEP = 8.0
POST_RESTART_WAIT = 10.0
MAX_VERIFICATION_ATTEMPTS = 3
VERIFICATION_EXTRA_SLEEP = 3.0


class AppCrashRecovery:
    """クラッシュ検知と自動復旧をまとめるオーケストレーター。"""

    def __init__(self) -> None:
        self.crash_detection_enabled = True
        self.max_recovery_attempts = 5
        self.recovery_timeout = 45  # 互換性のため保持（現状では使用しない）

    # ------------------------------------------------------------------
    # クラッシュ検知
    # ------------------------------------------------------------------
    def is_app_crashed(self, device_port: str) -> bool:
        """ホーム画面のアイコンが見つかったらクラッシュとみなす。"""
        if not self.crash_detection_enabled:
            return False

        try:
            for image_name, category in HOME_SCREEN_ICONS:
                x, y = find_image_on_device(device_port, image_name, category)
                if x is not None and y is not None:
                    return True
        except Exception as exc:
            logger.debug("クラッシュ検知エラー (ポート %s): %s", device_port, exc)

        return False

    # ------------------------------------------------------------------
    # 復旧フロー
    # ------------------------------------------------------------------
    def recover_from_crash(self, device_port: str) -> bool:
        """クラッシュを検知した端末で Monster Strike を再起動する。"""
        try:
            close_nox_error_dialogs()

            if not self._restart_app_from_home(device_port):
                logger.error("アプリ起動に失敗しました (ポート %s)", device_port)
                return False

            time.sleep(POST_RESTART_WAIT)

            if not self._verify_app_recovery(device_port):
                logger.error("復旧失敗: 依然としてホーム画面です (ポート %s)", device_port)
                return False

            logger.info("%s: 再起動完了", device_port)
            return True

        except Exception as exc:
            logger.error("復旧処理でエラーが発生しました (ポート %s): %s", device_port, exc)
            return False

    def _restart_app_from_home(self, device_port: str) -> bool:
        """ホーム画面からアイコンをタップしてアプリを再起動する。"""
        for attempt in range(MAX_ICON_ATTEMPTS):
            try:
                for image_name, category in HOME_SCREEN_ICONS:
                    if tap_if_found('tap', device_port, image_name, category):
                        time.sleep(ICON_TAP_DELAY)
                        return True

                time.sleep(ICON_RETRY_SLEEP)
            except Exception as exc:
                logger.warning(
                    "アプリ起動試行に失敗しました (ポート %s, 試行 %d): %s",
                    device_port,
                    attempt + 1,
                    exc,
                )
                time.sleep(ICON_RETRY_SLEEP)

        logger.info("強制起動を実行します (ポート %s)", device_port)
        try:
            start_monster_strike_app(device_port)
            time.sleep(FORCED_LAUNCH_SLEEP)
            return True
        except Exception as exc:
            logger.error("強制起動に失敗しました (ポート %s): %s", device_port, exc)
            return False

    def _verify_app_recovery(self, device_port: str) -> bool:
        """段階的にホーム画面から復帰できたかを確認する。"""
        for attempt in range(MAX_VERIFICATION_ATTEMPTS):
            try:
                wait_time = 3 + (attempt * 2)
                time.sleep(wait_time)

                if not self.is_app_crashed(device_port):
                    return True

                if attempt < MAX_VERIFICATION_ATTEMPTS - 1:
                    time.sleep(VERIFICATION_EXTRA_SLEEP)
            except Exception:
                time.sleep(2)

        return False

    # ------------------------------------------------------------------
    # 外部向けヘルパー
    # ------------------------------------------------------------------
    def check_and_recover(self, device_port: str) -> bool:
        """クラッシュしていれば復旧、通常時は True を返す。"""
        close_nox_error_dialogs()
        if not self.is_app_crashed(device_port):
            return True
        return self.recover_from_crash(device_port)

    def wrap_operation_with_recovery(
        self,
        operation: Callable[..., Any],
        device_port: str,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        """操作実行時にクラッシュ検知と復旧を組み込む。"""
        for attempt in range(self.max_recovery_attempts + 1):
            if attempt > 0:
                if not self.check_and_recover(device_port):
                    logger.error("復旧試行が上限に達しました (ポート %s)", device_port)
                    return None

            try:
                result = operation(*args, **kwargs)
            except Exception as exc:
                logger.error("操作実行エラー (ポート %s): %s", device_port, exc)
                if self.is_app_crashed(device_port):
                    logger.warning("エラー後にクラッシュを検知しました (ポート %s)", device_port)
                    continue
                raise

            if self.is_app_crashed(device_port):
                logger.warning("操作後にクラッシュを検知しました (ポート %s)", device_port)
                continue

            return result

        logger.error("最大復旧試行回数を超過しました (ポート %s)", device_port)
        return None


# グローバルインスタンス
crash_recovery = AppCrashRecovery()


def check_app_crash(device_port: str) -> bool:
    """外部向けクラッシュ検知ヘルパー。"""
    return crash_recovery.is_app_crashed(device_port)


def recover_app_crash(device_port: str) -> bool:
    """外部向けクラッシュ復旧ヘルパー。"""
    return crash_recovery.recover_from_crash(device_port)


def ensure_app_running(device_port: str) -> bool:
    """アプリが動作中か確認し、必要であれば復旧する。"""
    return crash_recovery.check_and_recover(device_port)


def with_crash_recovery(operation: Callable[..., Any]):
    """装飾子として操作にクラッシュ復旧フローを付与する。"""

    def wrapper(*args: Any, **kwargs: Any):
        if args:
            device_port = args[0]
            return crash_recovery.wrap_operation_with_recovery(
                operation,
                device_port,
                *args,
                **kwargs,
            )
        return operation(*args, **kwargs)

    return wrapper


def integrate_crash_detection_in_loop(
    operation: Callable[..., Any],
    device_port: str,
    folder: str,
    multi_logger: Any,
    **kwargs: Any,
) -> tuple[bool, bool]:
    """ループ内でクラッシュ検知と復旧を組み合わせる。"""
    is_crash = False

    try:
        if check_app_crash(device_port):
            is_crash = True
            if not crash_recovery.recover_from_crash(device_port):
                logger.error(
                    "クラッシュ復旧に失敗したためフォルダを再試行キューへ追加 (ポート %s, フォルダ %s)",
                    device_port,
                    folder,
                )
                return False, True

            logger.info(
                "クラッシュ復旧成功。処理を継続します (ポート %s, フォルダ %s)",
                device_port,
                folder,
            )

        result = operation(device_port, folder, multi_logger, **kwargs)

        if check_app_crash(device_port):
            logger.warning(
                "操作後にクラッシュを検知したためフォルダを再試行キューへ追加 (ポート %s, フォルダ %s)",
                device_port,
                folder,
            )
            return False, True

        return result, is_crash

    except Exception as exc:
        logger.error(
            "操作実行エラー (ポート %s, フォルダ %s): %s",
            device_port,
            folder,
            exc,
        )
        crash_detected = check_app_crash(device_port)
        if crash_detected:
            logger.warning(
                "エラー後にクラッシュを検知したためフォルダを再試行キューへ追加 (ポート %s, フォルダ %s)",
                device_port,
                folder,
            )
        return False, crash_detected or is_crash


def set_crash_detection_enabled(enabled: bool) -> None:
    """クラッシュ検知の有効/無効を切り替える。"""
    crash_recovery.crash_detection_enabled = enabled
    logger.info("クラッシュ検知: %s", "有効" if enabled else "無効")


def set_max_recovery_attempts(attempts: int) -> None:
    """最大復旧試行回数を設定する。"""
    crash_recovery.max_recovery_attempts = attempts
    logger.info("最大復旧試行回数: %d 回", attempts)
