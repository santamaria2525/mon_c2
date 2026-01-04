"""
monst.device.quest - クエスト操作機能（mon6完全準拠版）

参考バージョン（mon6 - 20250628）のdevice_operation_quest関数をベースに、
現在のプロジェクト構造に合わせて最適化した安定版です。

主な特徴:
- シンプルで確実な順次処理
- 複雑な状態管理を排除
- 早期returnやexceptionを最小化
- mon6と同じフロー制御

主な機能:
- 通常クエストの実行
- イベントクエストの実行（mon6準拠）
- 守護獣クエストの実行（mon6準拠）
- バトル終了待機処理
- データ復旧処理
"""

from __future__ import annotations

import time
from functools import lru_cache
from typing import Dict, Optional, Tuple

import cv2
import numpy as np

from config import on_que
from logging_util import logger, MultiDeviceLogger
from login_operations import device_operation_login, handle_screens
from monst.adb import perform_action
from monst.image import tap_if_found, mon_swipe, get_device_screenshot
from monst.image.device_control import tap_until_found
from monst.image.utils import get_image_path

from .exceptions import DeviceOperationError

_COUNTER_EVENT_IMAGES = (
    "event_pue1.png",
    "event_pue2.png",
    "event_pue3.png",
)
_COUNTER_QUE_IMAGES = (
    "event_que1.png",
    "event_que2.png",
    "event_que3.png",
)
_COUNTER_MAX_SWIPE = 6
_COUNTER_TAP_RETRIES = 3
_COUNTER_MATCH_THRESHOLD = 0.68
_COUNTER_FRAME_WAIT = 0.15
_COUNTER_ROI = (120, 720)  # (top, bottom) in pixels
_COUNTER_SWIPE_LIMIT = 6
_COUNTER_SWIPE_DURATION = 2000
_COUNTER_STATE_TIMEOUT = 20 * 60


def _tap_counter_event_targets(device_port: str) -> bool:
    """オーブカウンター対象の3画像だけを確実にタップする。"""
    for attempt in range(_COUNTER_TAP_RETRIES):
        capture = _capture_counter_frame(device_port)
        if capture is None:
            logger.debug("[COUNTER] screenshot unavailable on attempt %s", attempt + 1)
            time.sleep(_COUNTER_FRAME_WAIT)
            continue
        frame, offset_y = capture

        image_name, coords, confidence = _match_counter_target(frame, offset_y)
        if coords and confidence >= _COUNTER_MATCH_THRESHOLD:
            if perform_action(device_port, "tap", coords[0], coords[1], duration=200):
                logger.debug(
                    "[COUNTER] tapped %s at %s (confidence=%.3f)",
                    image_name,
                    coords,
                    confidence,
                )
                return True
            logger.warning("[COUNTER] tap failed (%s) confidence=%.3f", image_name, confidence)
        else:
            logger.debug(
                "[COUNTER] no target (attempt=%s, confidence=%.3f)",
                attempt + 1,
                confidence,
            )
        time.sleep(_COUNTER_FRAME_WAIT)
    return False


def _capture_counter_frame(device_port: str) -> Optional[Tuple[np.ndarray, int]]:
    """最新スクリーンショットのROIを取得する。"""
    frame = get_device_screenshot(device_port, cache_time=0.0, force_refresh=True)
    if frame is None:
        return None
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    top, bottom = _COUNTER_ROI
    top = max(0, min(top, gray.shape[0]))
    bottom = max(top + 1, min(bottom, gray.shape[0]))
    return gray[top:bottom, :].copy(), top


def _match_counter_target(frame: np.ndarray, offset_y: int) -> Tuple[Optional[str], Optional[Tuple[int, int]], float]:
    """ROI内から最も信頼度の高いevent_pue画像を探す。"""
    best_conf = 0.0
    best_coords: Optional[Tuple[int, int]] = None
    best_image: Optional[str] = None
    for image in _COUNTER_EVENT_IMAGES:
        template = _load_quest_template(image)
        if template is None:
            continue
        h, w = template.shape[:2]
        if frame.shape[0] < h or frame.shape[1] < w:
            continue
        res = cv2.matchTemplate(frame, template, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(res)
        if max_val > best_conf:
            best_conf = max_val
            best_image = image
            best_coords = (
                max_loc[0] + w // 2,
                offset_y + max_loc[1] + h // 2,
            )

    return best_image, best_coords, best_conf


@lru_cache(maxsize=None)
def _load_quest_template(image_name: str) -> Optional[np.ndarray]:
    """テンプレート画像を読み込みキャッシュする。"""
    try:
        path = get_image_path(image_name, "quest")
        template = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
        if template is None:
            logger.error("[COUNTER] template not found: %s", path)
        return template
    except Exception as exc:  # noqa: BLE001
        logger.error("[COUNTER] template load failed (%s): %s", image_name, exc)
        return None


def _run_counter_state_machine(device_port: str) -> bool:
    """on_que=1用のホーム/バトル/その他ループを実行する。"""
    _wait_for_room_ready(device_port)
    context: Dict[str, int] = {"swipe_miss": 0, "folder_done": 0}
    start_time = time.time()

    while time.time() - start_time < _COUNTER_STATE_TIMEOUT:
        if context.get("folder_done"):
            logger.info("[COUNTER] swipe limit reached, folder completed")
            return True

        if _detect_counter_completion(device_port):
            return True

        if _handle_dekki_null_state(device_port):
            context["swipe_miss"] = 0
            continue

        state = _get_counter_state(device_port)
        if state == "home":
            if _process_counter_home_state(device_port, context):
                continue
        elif state == "battle":
            _process_counter_battle_state(device_port)
            continue
        else:
            _process_counter_other_state(device_port)
            continue

        time.sleep(0.3)

    logger.warning("[COUNTER] state machine timeout reached")
    return False


def _wait_for_room_ready(device_port: str, timeout: float = 45.0) -> None:
    """room.pngが検出されるまで待機する。"""
    start = time.time()
    while time.time() - start < timeout:
        if tap_if_found('stay', device_port, "room.png", "login"):
            logger.debug("[COUNTER] room detected, starting quest routine")
            return
        time.sleep(0.5)
    logger.warning("[COUNTER] room.png not confirmed before timeout")


def _detect_counter_completion(device_port: str) -> bool:
    """クエスト終了表示を検知する。"""
    for image in ("que_end1.png", "que_end2.png", "que_end.png"):
        if tap_if_found('tap', device_port, image, "quest"):
            return True
    return False


def _get_counter_state(device_port: str) -> str:
    """現在の状態を判定する。"""
    if tap_if_found('stay', device_port, "sutamina.png", "quest"):
        return "home"
    if tap_if_found('stay', device_port, "battle.png", "quest"):
        return "battle"
    return "other"


def _process_counter_home_state(device_port: str, context: Dict[str, int]) -> bool:
    """ホーム状態の処理を実行する。"""
    action_taken = False
    if tap_if_found('tap', device_port, "counter.png", "quest"):
        action_taken = True
        context["swipe_miss"] = 0
        _ensure_counter_list_visible(device_port)

    event_clicked = _tap_event_que_images(device_port)
    if event_clicked:
        context["swipe_miss"] = 0
        return True

    for image, folder in (
        ("chosen.png", "quest"),
        ("close.png", "quest"),
        ("que_shohi.png", "quest"),
        ("solo.png", "key"),
        ("start.png", "quest"),
    ):
        if tap_if_found('tap', device_port, image, folder):
            return True

    if tap_if_found('stay', device_port, "suketto.png", "quest"):
        perform_action(device_port, 'tap', 150, 480, duration=150)
        return True

    if tap_if_found('stay', device_port, "stnabi.png", "quest") and not event_clicked:
        perform_action(
            device_port,
            'swipe',
            150,
            500,
            150,
            100,
            duration=_COUNTER_SWIPE_DURATION,
        )
        context["swipe_miss"] = context.get("swipe_miss", 0) + 1
        logger.debug(
            "[COUNTER] swipe %s/%s without targets",
            context["swipe_miss"],
            _COUNTER_SWIPE_LIMIT,
        )
        if context["swipe_miss"] >= _COUNTER_SWIPE_LIMIT:
            context["folder_done"] = 1
        return True

    return action_taken


def _tap_event_que_images(device_port: str) -> bool:
    """event_que画像を順番にクリックする。"""
    for image in _COUNTER_QUE_IMAGES:
        if tap_if_found('tap', device_port, image, "quest", cache_time=0.0):
            logger.debug("[COUNTER] tapped %s", image)
            return True
    return False


def _handle_dekki_null_state(device_port: str) -> bool:
    """デッキ切れ状態を復旧する。"""
    if not (
        tap_if_found('stay', device_port, "dekki_null.png", "key")
        or tap_if_found('stay', device_port, "dekki_null2.png", "key")
    ):
        return False

    tap_until_found(device_port, "go_tittle.png", "key", "sonota.png", "key", "tap")
    while not tap_if_found('tap', device_port, "date_repear.png", "key"):
        tap_if_found('tap', device_port, "go_tittle.png", "key")
        tap_if_found('tap', device_port, "sonota.png", "key")
    tap_until_found(device_port, "data_yes.png", "key", "date_repear.png", "key", "tap")
    tap_until_found(device_port, "zz_home.png", "key", "data_yes.png", "key", "tap")
    return True


def _process_counter_battle_state(device_port: str) -> None:
    """バトル状態時の処理。"""
    mon_swipe(device_port)
    for image in ("que_ok.png", "que_yes.png", "que_yes_re.png"):
        tap_if_found('tap', device_port, image, "quest")


def _process_counter_other_state(device_port: str) -> None:
    """その他状態時の処理。"""
    if tap_if_found('tap', device_port, "que_end_ok.png", "quest"):
        return
    _tap_login_home(device_port)


def _tap_login_home(device_port: str) -> None:
    """ホームボタンをタップしてログイン画面に戻す。"""
    tap_if_found('tap', device_port, "zz_home.png", "login")
    tap_if_found('tap', device_port, "zz_home2.png", "login")
    perform_action(device_port, 'tap', 40, 180, duration=150)


def _ensure_counter_list_visible(device_port: str) -> bool:
    """イベントリストが表示されるまで短時間待機する。"""
    if tap_if_found('stay', device_port, "eventblack.png", "quest"):
        return True
    time.sleep(0.2)
    return tap_if_found('stay', device_port, "eventblack.png", "quest")


def _scroll_counter_list(device_port: str) -> None:
    """イベントリストを下方向にスクロールする。"""
    if tap_if_found('swipe_down', device_port, "eventblack.png", "quest"):
        return
    perform_action(device_port, 'swipe', 350, 620, 350, 260, duration=400)
    mon_swipe(device_port)


def _select_counter_event(device_port: str) -> bool:
    """オーブカウンターイベントを選択し、クエスト開始を試みる。"""
    tap_if_found('tap', device_port, "pue_shohi.png", "quest")
    tap_if_found('tap', device_port, "chosen.png", "quest")
    tap_if_found('tap', device_port, "chosen_ok.png", "quest")
    tap_if_found('tap', device_port, "counter.png", "quest")

    if not tap_if_found('stay', device_port, "eventblack.png", "quest"):
        logger.debug("[COUNTER] event list not visible")
        return False

    if _tap_counter_event_targets(device_port):
        return True

    for attempt in range(_COUNTER_MAX_SWIPE):
        _scroll_counter_list(device_port)
        if _tap_counter_event_targets(device_port):
            return True

    logger.info("[COUNTER] targets not found after swiping")
    return False

def device_operation_quest(
    device_port: str, 
    folder: str, 
    multi_logger: Optional[MultiDeviceLogger] = None
) -> bool:
    """
    クエスト操作を実行します（mon6完全準拠版）。
    
    参考バージョン（mon6 - 20250628）と同様のシンプルで確実な動作を提供します。
    複雑な状態管理や早期returnを避け、順次処理によって安定した動作を実現します。
    
    Args:
        device_port: 対象デバイスのポート番号
        folder: 処理対象のフォルダ名
        multi_logger: マルチデバイス用ロガー（オプション）
        
    Returns:
        bool: クエスト処理が成功した場合True
    """
    try:
        # ログイン処理（mon6と同じ）
        if not device_operation_login(device_port, folder, multi_logger):
            return False

        if on_que == 1:
            success = _run_counter_state_machine(device_port)
            if success and multi_logger:
                multi_logger.log_success(device_port)
            if success:
                logger.info(f"{folder} 完了")
            return success
        
        counter_engaged = False
        if on_que == 1:
            if not _select_counter_event(device_port):
                return True
            counter_engaged = True

        # 条件式によるタイムアウト付きループ（mon6準拠）
        start_time = time.time()
        timeout = 100  # 1.5分間のタイムアウト（mon6と同じ）

        while time.time() - start_time < timeout:
            if on_que == 1 and tap_if_found('stay', device_port, "zz_home.png", "key"):
                if not counter_engaged:
                    if not _select_counter_event(device_port):
                        return True
                    counter_engaged = True

            if tap_if_found('stay', device_port, "battle.png", "quest"):
                counter_engaged = False
                break
                
            # イベントクエスト処理（mon6完全準拠）
            if on_que == 1:
                if not counter_engaged:
                    if not _select_counter_event(device_port):
                        return True
                    counter_engaged = True
                            
            # 守護獣クエスト処理（mon6完全準拠）
            if on_que == 2:
                tap_if_found('tap', device_port, "quest_c.png", "key")
                tap_if_found('tap', device_port, "quest.png", "key")
                tap_if_found('tap', device_port, "ichiran.png", "key")
                tap_if_found('tap', device_port, "shugo_que.png", "quest")
                tap_if_found('tap', device_port, "kyukyoku.png", "key")
                tap_if_found('tap', device_port, "shugo.png", "quest")
                
            # solo.png特別処理（mon6と同じ）
            if tap_if_found('tap', device_port, "solo.png", "key"):
                while not tap_if_found('tap', device_port, "start.png", "quest"):
                    perform_action(device_port, 'tap', 200, 575, duration=200)
                    
            # デッキ切れ処理（mon6準拠）
            if tap_if_found('stay', device_port, "dekki_null.png", "key"):
                timeout = timeout + 300
                tap_until_found(device_port, "go_tittle.png", "key", "sonota.png", "key", "tap")
                while not tap_if_found('tap', device_port, "date_repear.png", "key"):
                    tap_if_found('tap', device_port, "go_tittle.png", "key")
                    tap_if_found('tap', device_port, "sonota.png", "key")
                tap_until_found(device_port, "data_yes.png", "key", "date_repear.png", "key", "tap")
                tap_until_found(device_port, "zz_home.png", "key", "data_yes.png", "key", "tap")
                
            # 基本的な画面遷移（mon6と完全に同じ）
            tap_if_found('tap', device_port, "close.png", "key")
            tap_if_found('tap', device_port, "start.png", "quest")
            tap_if_found('tap', device_port, "kaifuku.png", "quest")
            tap_if_found('tap', device_port, "ok.png", "key")
            
            # 受付時間外処理（mon6と同じ）
            if tap_if_found('stay', device_port, "uketsuke.png", "key"):
                tap_if_found('tap', device_port, "zz_home.png", "key")
                
            time.sleep(1)  # 次のループまでの短い待機時間
        else:
            pass

        # バトル終了待機処理（mon6準拠：300回のループ = 約10分間）
        for _ in range(300):
            time.sleep(2)
            if tap_if_found('stay', device_port, "que_end.png", "quest"):
                break
            tap_if_found('tap', device_port, "que_ok.png", "quest")
            tap_if_found('tap', device_port, "que_yes.png", "quest")
            # スワイプ実行中の追加クリック処理
            tap_if_found('tap', device_port, "que_yes_re.png", "quest")
            tap_if_found('tap', device_port, "icon.png", "quest")
            mon_swipe(device_port)
        else:
            pass

        if multi_logger:
            multi_logger.log_success(device_port)
        logger.info(f"{folder} 完了")
        return True
    
    except Exception:
        return False

# mon6準拠：簡潔なユーティリティ関数のみ保持

def reset_quest_state(device_port: str) -> None:
    """指定デバイスのクエスト処理状態をリセットします（mon6準拠）"""
    pass

def get_quest_state(device_port: str) -> dict:
    """指定デバイスのクエスト処理状態を取得します（mon6準拠）"""
    return {"status": "ready"}
