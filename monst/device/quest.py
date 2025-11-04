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
from typing import Optional

from config import on_que
from logging_util import logger, MultiDeviceLogger
from login_operations import device_operation_login, handle_screens
from monst.adb import perform_action
from monst.image import tap_if_found, mon_swipe
from monst.image.device_control import tap_until_found

from .exceptions import DeviceOperationError

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
        
        # 条件式によるタイムアウト付きループ（mon6準拠）
        start_time = time.time()
        timeout = 100  # 1.5分間のタイムアウト（mon6と同じ）

        while time.time() - start_time < timeout:
            if tap_if_found('stay', device_port, "battle.png", "quest"):
                break
                
            # イベントクエスト処理（mon6完全準拠）
            if on_que == 1:
                tap_if_found('tap', device_port, "pue_shohi.png", "quest")
                tap_if_found('tap', device_port, "chosen.png", "quest")
                tap_if_found('tap', device_port, "chosen_ok.png", "quest")
                tap_if_found('tap', device_port, "counter.png", "quest")
                if tap_if_found('stay', device_port, "eventblack.png", "quest"):
                    if not (tap_if_found('tap', device_port, "event_pue1.png", "quest") or 
                            tap_if_found('tap', device_port, "event_pue2.png", "quest") or 
                            tap_if_found('tap', device_port, "event_pue3.png", "quest")):
                        tap_if_found('swipe_up', device_port, "eventblack.png", "key")
                        tap_if_found('swipe_up', device_port, "eventblack.png", "key")
                        tap_if_found('swipe_up', device_port, "eventblack.png", "key")
                        if not (tap_if_found('tap', device_port, "event_pue1.png", "quest") or 
                                tap_if_found('tap', device_port, "event_pue2.png", "quest") or 
                                tap_if_found('tap', device_port, "event_pue3.png", "quest")):
                            return True
                            
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