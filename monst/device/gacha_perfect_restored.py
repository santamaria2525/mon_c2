"""
monst.device.gacha_perfect_restored
===================================

Restored implementation of the pre-refactor "perfect" gacha workflow that the
ultrathink path expects.  The public surface mirrors the historical module and
is intentionally defensive so we never crash while processing a folder.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Optional, Tuple

from config import get_config
from logging_util import logger
from utils.device_utils import get_terminal_number
from utils.path_manager import get_base_path

# Lazy import helper to avoid circular imports at module import time.


def _get_gacha_module():
    from . import gacha as gacha_module  # Local import to avoid cycles

    return gacha_module


@dataclass
class _PerfectGachaContext:
    device_port: str
    folder: str
    gacha_limit: int
    continue_until_character: bool
    wait_after_pull: float = 3.0
    wait_between_retries: float = 1.5
    interface_reset_interval: int = 2
    max_recoverable_failures: int = 6
    target_folder: str = "gacha_target"
    target_images: Tuple[str, ...] = tuple()

    @property
    def terminal_label(self) -> str:
        return get_terminal_number(self.device_port)

    @classmethod
    def build(
        cls,
        device_port: str,
        folder: str,
        gacha_limit: int,
        continue_until_character: bool,
    ) -> _PerfectGachaContext:
        cfg = get_config()

        fallback_limit = getattr(cfg, "on_gacha_kaisu", 16)
        limit = gacha_limit if isinstance(gacha_limit, int) and gacha_limit > 0 else fallback_limit
        limit = max(1, limit)

        # Allow optional per-install tuning via config.extra
        extra = getattr(cfg, "extra", {}) or {}
        wait_after_pull = float(extra.get("gacha_wait_after_pull", 3.0))
        wait_between_retries = float(extra.get("gacha_wait_between_retries", 1.5))
        target_folder = str(extra.get("gacha_target_folder", "gacha_target")).strip() or "gacha_target"
        target_images = _discover_target_images(target_folder)

        return cls(
            device_port=device_port,
            folder=folder,
            gacha_limit=limit,
            continue_until_character=bool(continue_until_character),
            wait_after_pull=wait_after_pull,
            wait_between_retries=wait_between_retries,
            target_folder=target_folder,
            target_images=target_images,
        )


class _PerfectGachaRunner:
    def __init__(self, context: _PerfectGachaContext):
        self.ctx = context
        self._gacha_module = _get_gacha_module()

    # ------------------------------------------------------------------ API --

    def run(self) -> bool:
        terminal = self.ctx.terminal_label
        logger.info(
            "%s: 完全復元ガチャ開始 (limit=%d continue=%s)",
            terminal,
            self.ctx.gacha_limit,
            self.ctx.continue_until_character,
        )
        if self.ctx.target_images:
            logger.info("%s: カスタムターゲット画像数=%d フォルダ=%s", terminal, len(self.ctx.target_images), self.ctx.target_folder)

        target_position = None if self.ctx.target_images else self._find_target_region()
        needs_pull = True
        if target_position and not self.ctx.continue_until_character:
            needs_pull = self._gacha_module.check_character_ownership_at_position(
                self.ctx.device_port,
                target_position,
            )

        if not needs_pull and not self.ctx.continue_until_character:
            logger.info("%s: target領域は全て所持済みのためガチャをスキップ", terminal)
            return False

        found_character = self._perform_pulls(target_position)

        if found_character:
            self._persist_results(bool(target_position))

        logger.info(
            "%s: 完全復元ガチャ終了 -> %s",
            terminal,
            "キャラ獲得" if found_character else "未獲得",
        )
        return found_character

    # ------------------------------------------------------------- internals --

    def _find_target_region(self) -> Optional[tuple]:
        try:
            return self._gacha_module._search_target_with_swipe(self.ctx.device_port)
        except Exception as exc:  # pragma: no cover - safety net
            logger.error("%s: target検索に失敗しました: %s", self.ctx.terminal_label, exc)
            return None

    def _perform_pulls(self, target_position: Optional[tuple]) -> bool:
        pulls = 0
        consecutive_failures = 0
        found_character = False

        if self._custom_target_detected():
            logger.info("%s: カスタムガチャターゲットを検出したため即終了します", self.ctx.terminal_label)
            return True

        while self._should_continue(pulls):
            if self._custom_target_detected():
                found_character = True
                break

            if target_position and not self.ctx.continue_until_character:
                needs_pull = self._gacha_module.check_character_ownership_at_position(
                    self.ctx.device_port,
                    target_position,
                )
                if not needs_pull:
                    logger.info("%s: target領域が緑文字になったため終了", self.ctx.terminal_label)
                    break

            try:
                result = self._gacha_module._execute_simple_gacha_action(self.ctx.device_port)
            except Exception as exc:
                logger.error("%s: ガチャ操作で例外が発生: %s", self.ctx.terminal_label, exc)
                consecutive_failures += 1
                if self._abort_due_to_failures(consecutive_failures):
                    break
                time.sleep(self.ctx.wait_between_retries)
                continue

            if result == "character_found":
                pulls += 1
                found_character = True
                break

            if result is True:
                pulls += 1
                consecutive_failures = 0
                time.sleep(self.ctx.wait_after_pull)
                continue

            consecutive_failures += 1
            if self._abort_due_to_failures(consecutive_failures):
                break

            if consecutive_failures % self.ctx.interface_reset_interval == 0:
                try:
                    self._gacha_module._handle_gacha_interface(self.ctx.device_port)
                except Exception as exc:  # pragma: no cover - defensive
                    logger.debug("%s: ガチャ画面復旧に失敗: %s", self.ctx.terminal_label, exc)

            time.sleep(self.ctx.wait_between_retries)

        return found_character

    def _should_continue(self, pulls: int) -> bool:
        if self.ctx.continue_until_character:
            return pulls < self.ctx.gacha_limit
        return pulls < self.ctx.gacha_limit

    def _abort_due_to_failures(self, consecutive_failures: int) -> bool:
        if consecutive_failures < self.ctx.max_recoverable_failures:
            return False
        logger.error(
            "%s: ガチャ操作失敗が連続しすぎたため中断 (%d回)",
            self.ctx.terminal_label,
            consecutive_failures,
        )
        return True

    def _persist_results(self, has_target_snapshot: bool) -> None:
        saver = (
            self._gacha_module._save_gacha_completion_data_with_target_image
            if has_target_snapshot
            else self._gacha_module._save_gacha_completion_data
        )
        if not saver(self.ctx.device_port, self.ctx.folder):
            logger.warning("%s: ガチャ結果データの保存に失敗しました", self.ctx.terminal_label)

    # --------------------------------------------------------- custom targets --
    def _custom_target_detected(self) -> bool:
        if not self.ctx.target_images:
            return False
        for image_name in self.ctx.target_images:
            try:
                if self._gacha_module.tap_if_found(
                    "stay",
                    self.ctx.device_port,
                    image_name,
                    self.ctx.target_folder,
                ):
                    logger.info(
                        "%s: ガチャターゲット画像(%s)を検出しました",
                        self.ctx.terminal_label,
                        image_name,
                    )
                    return True
            except Exception:
                continue
        return False


def execute_perfect_gacha(
    device_port: str,
    folder: str,
    gacha_limit: int,
    *,
    continue_until_character: bool = False,
) -> bool:
    """
    Public entry point used by monst.device.gacha.mon_gacha_shinshun.
    """
    context = _PerfectGachaContext.build(
        device_port=device_port,
        folder=folder,
        gacha_limit=gacha_limit,
        continue_until_character=continue_until_character,
    )
    runner = _PerfectGachaRunner(context)

    try:
        return runner.run()
    except Exception as exc:  # pragma: no cover - safety guard
        logger.error("%s: 完全復元ガチャ中に致命的なエラー: %s", context.terminal_label, exc)
        return False


def mon_gacha_shinshun_perfect(
    device_port: str,
    folder: str,
    gacha_limit: int,
    *,
    continue_until_character: bool = False,
) -> bool:
    """Backward compatible alias for external callers."""
    return execute_perfect_gacha(
        device_port,
        folder,
        gacha_limit,
        continue_until_character=continue_until_character,
    )


def mon_gacha_shinshun_perfect_restored(
    device_port: str,
    folder: str,
    gacha_limit: int,
    *,
    continue_until_character: bool = False,
) -> bool:
    """Alias retained for legacy imports."""
    return mon_gacha_shinshun_perfect(
        device_port,
        folder,
        gacha_limit,
        continue_until_character=continue_until_character,
    )


def _discover_target_images(folder_name: str) -> Tuple[str, ...]:
    try:
        base_path = get_base_path()
        target_dir = os.path.join(base_path, "gazo", folder_name)
        if not os.path.isdir(target_dir):
            return tuple()
        images = [
            name
            for name in os.listdir(target_dir)
            if name.lower().endswith(".png")
        ]
        return tuple(sorted(images))
    except Exception as exc:
        logger.debug("カスタムガチャターゲット検索に失敗: %s", exc)
        return tuple()
