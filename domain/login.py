"""Modern wrapper around the login operation."""

from __future__ import annotations

from typing import Optional

from login_operations import device_operation_login
from logging_util import MultiDeviceLogger, logger


class LoginWorkflow:
    """Encapsulates the login operation used in multi-device loops."""

    def __init__(self, core):
        self.core = core

    def execute(
        self,
        device_port: str,
        folder: str,
        multi_logger: Optional[MultiDeviceLogger] = None,
        *,
        home_early: bool = False,
    ) -> bool:
        logger.debug("Executing login workflow on %s (folder %s)", device_port, folder)
        return bool(device_operation_login(device_port, folder, multi_logger, home_early))
