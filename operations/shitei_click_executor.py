# -*- coding: utf-8 -*-
"""
Executor that continuously searches for images in ``gazo/shitei`` and taps them.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Sequence

import cv2  # type: ignore
import numpy as np

from logging_util import logger
from monst.adb import perform_action
from monst.image import get_device_screenshot
from utils import display_message, get_base_path
from config import get_config_value


@dataclass(slots=True)
class _TemplateEntry:
    mtime: float
    image: np.ndarray


class ShiteiClickExecutor:
    """Continuously searches for images inside ``gazo/shitei`` and taps them."""

    IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp"}
    SCAN_INTERVAL_SECONDS = 0.0
    POST_TAP_DELAY_SECONDS = 0.0
    TAP_THRESHOLD = 0.75
    NO_MATCH_LOG_INTERVAL = 15

    def __init__(self, core, config_service) -> None:
        self.core = core
        self.config_service = config_service
        self._warned_no_images = False
        self._last_image_snapshot: tuple[str, ...] = ()
        self._no_match_counter = 0
        self._template_cache: dict[str, _TemplateEntry] = {}
        self._roi = self._load_roi()

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    def run(self) -> None:
        """Entry point for the menu command."""
        snapshot = self.config_service.load()
        ports = self.config_service.get_ports_for_device_count(snapshot.device_count)
        if not ports:
            logger.error("指定画像クリック: ポート設定が取得できません。config.json を確認してください。")
            return

        catalog_dir = self._ensure_catalog()
        if catalog_dir is None:
            return

        logger.info("指定画像クリック: 監視フォルダ=%s", catalog_dir)
        logger.info("指定画像クリック: 対象ポート=%s", ports)

        try:
            self._run_loop(ports, catalog_dir)
        except KeyboardInterrupt:
            logger.info("指定画像クリック: ユーザー操作により停止しました。")

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #
    def _ensure_catalog(self) -> Path | None:
        image_dir = Path(get_base_path()) / "gazo" / "shitei"
        try:
            image_dir.mkdir(parents=True, exist_ok=True)
        except Exception as exc:
            logger.error("指定画像クリック: フォルダ作成に失敗しました (%s)", exc)
            display_message("エラー", f"gazo/shitei フォルダを作成できませんでした。\n詳細: {exc}")
            return None

        if not any(file.suffix.lower() in self.IMAGE_EXTENSIONS for file in image_dir.glob("*")):
            logger.warning("指定画像クリック: gazo/shitei に検索対象の画像がありません。")
            display_message("情報", "gazo/shitei フォルダに検索したい画像 (png/jpg) を配置してください。")
        return image_dir

    def _load_roi(self) -> tuple[int, int, int, int] | None:
        raw = get_config_value("shitei_roi", None)
        if not isinstance(raw, dict):
            return None

        try:
            x = int(raw.get("x", 0))
            y = int(raw.get("y", 0))
            width = int(raw.get("width", 0))
            height = int(raw.get("height", 0))
        except (TypeError, ValueError):
            logger.warning("指定画像クリック: shitei_roi 設定に無効な値が含まれています。")
            return None

        if width <= 0 or height <= 0:
            logger.warning("指定画像クリック: shitei_roi の幅・高さは正の値で指定してください。")
            return None

        logger.info("指定画像クリック: ROI 設定を適用します (x=%d y=%d width=%d height=%d)", x, y, width, height)
        return (x, y, width, height)

    def _collect_images(self, directory: Path) -> List[str]:
        return sorted(
            file.name
            for file in directory.iterdir()
            if file.is_file() and file.suffix.lower() in self.IMAGE_EXTENSIONS
        )

    def _run_loop(self, ports: Sequence[str], image_dir: Path) -> None:
        while not self.core.is_stopping():
            cycle_start = time.monotonic()
            image_names = self._collect_images(image_dir)

            if not image_names:
                if not self._warned_no_images:
                    logger.warning("指定画像クリック: 監視フォルダに画像が存在しません。")
                    self._warned_no_images = True
                time.sleep(self.SCAN_INTERVAL_SECONDS)
                continue

            if self._warned_no_images:
                logger.info("指定画像クリック: 監視対象の画像を検出しました (件数=%d)。", len(image_names))
                self._warned_no_images = False

            snapshot = tuple(image_names)
            if snapshot != self._last_image_snapshot:
                self._last_image_snapshot = snapshot
                logger.info("指定画像クリック: 現在の監視対象 => %s", ", ".join(image_names))

            any_tapped = False
            worker_count = min(len(ports), 4) or 1
            from concurrent.futures import ThreadPoolExecutor, as_completed

            with ThreadPoolExecutor(max_workers=worker_count) as executor:
                future_map = {
                    executor.submit(self._process_port, port, image_dir, image_names): port
                    for port in ports
                }

                for future in as_completed(future_map):
                    if self.core.is_stopping():
                        break
                    try:
                        if future.result():
                            any_tapped = True
                    except Exception as exc:
                        logger.exception("指定画像クリック: ポート処理中に例外が発生しました (port=%s): %s", future_map[future], exc)

            if any_tapped:
                self._no_match_counter = 0
            else:
                self._no_match_counter += 1
                if self._no_match_counter % self.NO_MATCH_LOG_INTERVAL == 0:
                    logger.info(
                        "指定画像クリック: 直近の %d サイクルで一致がありませんでした。",
                        self.NO_MATCH_LOG_INTERVAL,
                    )

            elapsed = time.monotonic() - cycle_start
            remaining = self.SCAN_INTERVAL_SECONDS - elapsed
            if remaining > 0:
                time.sleep(remaining)

        logger.info("指定画像クリック: 停止要求を受け取り終了します。")

    def _process_port(self, port: str, directory: Path, image_names: Iterable[str]) -> bool:
        screenshot = get_device_screenshot(port, cache_time=0.0, force_refresh=True)
        if screenshot is None or screenshot.size == 0:
            logger.debug("指定画像クリック: スクリーンショット取得に失敗しました (port=%s)", port)
            return False

        try:
            gray_screenshot = cv2.cvtColor(screenshot, cv2.COLOR_BGR2GRAY)
        except Exception as exc:
            logger.exception("指定画像クリック: 画像変換に失敗しました (port=%s): %s", port, exc)
            return False

        roi_offset_x = roi_offset_y = 0
        if self._roi:
            rx, ry, rw, rh = self._roi
            h, w = gray_screenshot.shape[:2]
            rx = max(0, min(rx, w - 1))
            ry = max(0, min(ry, h - 1))
            rw = max(1, min(rw, w - rx))
            rh = max(1, min(rh, h - ry))
            gray_screenshot = gray_screenshot[ry : ry + rh, rx : rx + rw]
            roi_offset_x, roi_offset_y = rx, ry

        for image_name in image_names:
            template = self._load_template(directory, image_name)
            if template is None:
                continue

            try:
                res = cv2.matchTemplate(gray_screenshot, template, cv2.TM_CCOEFF_NORMED)
                _, max_val, _, max_loc = cv2.minMaxLoc(res)
            except Exception as exc:
                logger.exception("指定画像クリック: テンプレートマッチで例外 (port=%s image=%s): %s", port, image_name, exc)
                continue

            if max_val < self.TAP_THRESHOLD:
                continue

            center_x = int(max_loc[0] + template.shape[1] / 2) + roi_offset_x
            center_y = int(max_loc[1] + template.shape[0] / 2) + roi_offset_y

            try:
                if perform_action(port, "tap", center_x, center_y, duration=120):
                    logger.debug(
                        "指定画像クリック: port=%s image=%s をタップしました (score=%.3f)",
                        port,
                        image_name,
                        max_val,
                    )
                    if self.POST_TAP_DELAY_SECONDS > 0:
                        time.sleep(self.POST_TAP_DELAY_SECONDS)
                    return True
                else:
                    logger.warning("指定画像クリック: port=%s でタップに失敗しました (image=%s)", port, image_name)
            except Exception as exc:
                logger.exception("指定画像クリック: タップ送信で例外 (port=%s image=%s): %s", port, image_name, exc)

        return False

    def _load_template(self, directory: Path, image_name: str) -> np.ndarray | None:
        path = directory / image_name
        try:
            mtime = path.stat().st_mtime
        except FileNotFoundError:
            return None

        cache_key = str(path)
        entry = self._template_cache.get(cache_key)
        if entry and entry.mtime == mtime:
            return entry.image

        template = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
        if template is None:
            logger.error("指定画像クリック: テンプレート画像を読み込めませんでした (%s)", path)
            return None

        self._template_cache[cache_key] = _TemplateEntry(mtime=mtime, image=template)
        return template
