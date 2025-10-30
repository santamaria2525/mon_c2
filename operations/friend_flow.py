"""Friend-registration helpers for the cleaned codebase."""

from __future__ import annotations

from logging_util import logger
from monst.device.friends import friend_status_check


def verify_friend_status(device_port: str, folder: str) -> bool:
    """
    Check friend status on the specified device using the proven legacy helper.

    Returns:
        bool: True when friend registration status is confirmed.
    """

    try:
        result = friend_status_check(device_port, folder, None)
        if result:
            logger.info("フレンド状態確認成功: port=%s folder=%s", device_port, folder)
        else:
            logger.warning("フレンド状態確認失敗: port=%s folder=%s", device_port, folder)
        return bool(result)
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.error("フレンド状態確認中に例外発生 port=%s folder=%s error=%s", device_port, folder, exc)
        return False


__all__ = ["verify_friend_status"]
