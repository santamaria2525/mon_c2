import time
import os
import subprocess
from typing import Optional
from adb_utils import start_monster_strike_app, send_key_event, run_adb_command, pull_file_from_nox, perform_action, get_executable_path
from image_detection import tap_if_found, tap_until_found, type_folder_name, device_folder_mapping, read_orb_count, get_device_screenshot, find_image_count, mon_swipe, tap_if_found_on_windows ,tap_until_found_on_windows
from config import id1, id2, id3, id4, id5, id6, id7, id8, id9, id10, id11, id12, NOX_ADB_PATH, gacha_limit, auto_mode , on_save ,login_sleep , on_mission , on_que, on_check ,on_event ,on_medal, on_gacha , on_count, on_sell, on_name, name_prefix, on_initial , room_key1 , room_key2
from logging_util import logger, MultiDeviceLogger
import pytesseract
from login_operations import device_operation_login, handle_screens
from utils import get_base_path, get_resource_path, update_csv_data, send_notification_email ,replace_multiple_lines_in_file ,activate_window_and_right_click, multi_press
import pyautogui
import pygetwindow as gw
import threading
import concurrent.futures
import random

def device_operation_select(device_port: str, folder: str, multi_logger: Optional[MultiDeviceLogger] = None) -> bool:
    try:
        if not device_operation_login(device_port, folder, multi_logger):
            logger.error(f"ログイン失敗 (フォルダ：{folder})")
            if multi_logger:
                multi_logger.log_error(device_port, f"ログイン失敗 (フォルダ：{folder})")
            return False

        found_character = None  # 初期値を設定
        
        if on_check in [1, 2, 3]:
            icon_check(device_port, folder)
        if on_event == 1:
            event_do(device_port, folder)
        if on_medal == 1:
            medal_change(device_port, folder)
        if on_initial == 1:
            mon_initial(device_port, folder)
        if on_mission == 1:
            mission_get(device_port, folder)
        if on_name == 1:
            name_change(device_port, folder)
        if on_gacha == 1:
            found_character = mon_gacha_shinshun(device_port, folder, gacha_limit)
        if on_sell == 1:
            mon_sell(device_port, folder) 
        if on_count == 1:
            orb_count(device_port, folder, found_character=found_character) 
        if on_save == 1:
            pull_file_from_nox(device_port, folder)

        if multi_logger:
            multi_logger.log_success(device_port)
        return True

    except Exception as e:
        error_msg = f"{str(e)} (フォルダ：{folder})"
        logger.error(f"ガチャ操作中にエラーが発生しました: {error_msg}", exc_info=True)
        if multi_logger:
            multi_logger.log_error(device_port, error_msg)
        return False

def home(device_port: str, folder: str, multi_logger: Optional[MultiDeviceLogger] = None) -> bool:
    
    while not tap_if_found('stay', device_port, "room.png", "key"):
        handle_screens(device_port,"login")
        tap_if_found('tap', device_port, "zz_home.png", "key")
        tap_if_found('tap', device_port, "zz_home2.png", "key")
        perform_action(device_port, 'tap', 50, 170, duration=150)

def icon_check(device_port: str, folder: str, multi_logger: Optional[MultiDeviceLogger] = None) -> bool:

    home(device_port, folder)

    if on_check == 1: # ノマクエチェック
        while not tap_if_found('tap', device_port, "noma.png", "key"):
            tap_if_found('tap', device_port, "quest_c.png", "key")
            tap_if_found('tap', device_port, "quest.png", "key")
            tap_if_found('tap', device_port, "ichiran.png", "key")
            tap_if_found('tap', device_port, "ok.png", "key")
            tap_if_found('tap', device_port, "close.png", "key")
            time.sleep(1)
    
    if on_check == 2: # 覇者の塔クリアチェック
        timeout = 60  # タイムアウト時間（秒単位）
        start_time = time.time()  # 処理開始時間を記録

        while True:
            # "hasyafin1.png" を探す
            if tap_if_found('tap', device_port, "hasyafin1.png", "key"):
                break  # 見つかった場合、ループを終了

            # 2分間見つからなかった場合
            if time.time() - start_time > timeout:
                logger.info(f"覇者未完了。対象フォルダ: {folder}")
                break

            # 他のタップ処理を実行
            tap_if_found('tap', device_port, "quest_c.png", "key")
            tap_if_found('tap', device_port, "quest.png", "key")
            tap_if_found('tap', device_port, "ichiran.png", "key")
            tap_if_found('tap', device_port, "ok.png", "key")
            tap_if_found('tap', device_port, "close.png", "key")
            time.sleep(1)  # 次のチェックまで待機
    
    if on_check == 3: # 守護獣所持チェック
        tap_until_found(device_port, "monbox.png", "key", "monster.png", "key", "tap")
        tap_until_found(device_port, "shugo_box2.png", "key", "shugo_box.png", "key", "tap")
        tap_until_found(device_port, "shugo_ishi.png", "key", "ok.png", "key", "tap")
        if not tap_if_found('stay', device_port, "shugo1.png", "icon"):
            logger.info(f"守護１未所持　対象フォルダ: {folder}")
        if not tap_if_found('stay', device_port, "shugo2.png", "icon"):
            logger.info(f"守護２未所持　対象フォルダ: {folder}")
        if not tap_if_found('stay', device_port, "shugo3.png", "icon"):
            logger.info(f"守護３未所持　対象フォルダ: {folder}")
        if not tap_if_found('stay', device_port, "shugo4.png", "icon"):
            logger.info(f"守護４未所持　対象フォルダ: {folder}")

def event_do(device_port: str, folder: str, multi_logger: Optional[MultiDeviceLogger] = None) -> bool:

    home(device_port, folder)

    ##mon_gacha_selection
    tap_until_found(device_port, "gacha_black.png", "key", "gacha.png", "key", "tap")
    if tap_if_found('stay', device_port, "sel_A.png", "event"):
        tap_until_found(device_port, "sel2.png", "event", "sel1.png", "event", "tap", "stay")
        if tap_if_found('tap', device_port, "el.png", "event"):
            tap_until_found(device_port, "check.png", "event", "el.png", "event", "tap", "stay")
        elif tap_if_found('tap', device_port, "geki.png", "event"):
            tap_until_found(device_port, "check.png", "event", "geki.png", "event", "tap", "stay")
        elif tap_if_found('tap', device_port, "masa.png", "event"):
            tap_until_found(device_port, "check.png", "event", "masa.png", "event", "tap", "stay")
        else:
            tap_until_found(device_port, "check.png", "event", "vani.png", "event", "tap", "stay")

    #各色クリック
        perform_action(device_port, 'tap', 100, 270, duration=150)
        time.sleep(2)
        perform_action(device_port, 'tap', 40, 390, duration=150)
        time.sleep(1)
        perform_action(device_port, 'tap', 160, 270, duration=150)
        time.sleep(2)
        perform_action(device_port, 'tap', 40, 390, duration=150)
        time.sleep(1)
        perform_action(device_port, 'tap', 210, 270, duration=150)
        time.sleep(2)
        perform_action(device_port, 'tap', 210, 270, duration=150)
        time.sleep(1)
        perform_action(device_port, 'tap', 270, 270, duration=150)
        time.sleep(2)
        perform_action(device_port, 'tap', 270, 270, duration=150)
        time.sleep(1)
        perform_action(device_port, 'tap', 320, 270, duration=150)
        time.sleep(2)
        perform_action(device_port, 'tap', 120, 330, duration=150)
        time.sleep(1)
        #ガチャ実行
        tap_until_found(device_port, "sel21.png", "event", "sel17.png", "event", "tap", "stay")
        tap_until_found(device_port, "sel22.png", "event", "sel21.png", "event", "tap", "stay")
        tap_if_found('tap', device_port, "sel22.png", "event")
        time.sleep(3)
        while not tap_if_found('tap', device_port, "gacha_back.png", "key"):
            tap_if_found('swipe_down', device_port, "tama.png", "key")
            tap_if_found('swipe_down', device_port, "tama2.png", "key")
            perform_action(device_port, 'tap', 50, 170, duration=150)

def medal_change(device_port: str, folder: str, multi_logger: Optional[MultiDeviceLogger] = None) -> bool:

    home(device_port, folder)

    tap_until_found(device_port, "monbox.png", "key", "monster.png", "key", "tap")
    while not tap_if_found('tap', device_port, "hikikae1.png", "key"):
        perform_action(device_port, 'swipe', 100, 500, 100, 400, duration=300)
    time.sleep(1)
    tap_if_found('tap', device_port, "hikikae1.png", "key")
    tap_until_found(device_port, "medal1.png", "key", "ok_2.png", "key", "tap", "tap")
    tap_until_found(device_port, "medal2.png", "key", "ok_2.png", "key", "tap", "tap")
    while not (tap_if_found('tap', device_port, "hikikae_p.png", "key") or tap_if_found('tap', device_port, "medal_fusoku.png", "key")):
        tap_if_found('tap', device_port, "hikikae_g.png", "key")        
    time.sleep(1)
    tap_if_found('tap', device_port, "hikikae_p.png", "key")
    tap_if_found('tap', device_port, "hikikae_p.png", "key")
    tap_if_found('tap', device_port, "hikikae_p.png", "key")
    tap_if_found('tap', device_port, "hikikae_p.png", "key")
    tap_if_found('tap', device_port, "hikikae_p.png", "key")
    tap_if_found('tap', device_port, "hikikae_p.png", "key")
    tap_if_found('tap', device_port, "yes.png", "key")
    time.sleep(1)
    tap_if_found('tap', device_port, "ok_2.png", "key")

def mission_get(device_port: str, folder: str, multi_logger: Optional[MultiDeviceLogger] = None) -> bool:

    home(device_port, folder)

    tap_until_found(device_port, "m_mission_b.png", "key", "m_mission.png", "key", "tap")
    tap_if_found('tap', device_port, "m_tujo.png", "key")
    time.sleep(1)
    while not find_image_count(device_port, "m_mitatsu.png", 4, 0.75, "key"):
        handle_screens(device_port,"mission")
        if tap_if_found('stay', device_port, "m_5tai.png", "key"):
            tap_if_found('tap', device_port, "m_uke5.png", "mission")
        if tap_if_found('stay', device_port, "m_3tai.png", "key") or tap_if_found('stay', device_port, "m_4tai.png", "key") or tap_if_found('stay', device_port, "m_6tai.png", "key") or tap_if_found('stay', device_port, "m_7tai.png", "key") or tap_if_found('stay', device_port, "m_8tai.png", "key") or tap_if_found('stay', device_port, "m_10tai.png", "key"):
            tap_if_found('tap', device_port, "m_close.png", "key")
        if tap_if_found('stay', device_port, "m_stjoho.png", "key"):
            tap_until_found(device_port, "m_mission_b.png", "key", "back.png", "key", "tap")
        if tap_if_found('stay', device_port, "m_tokugacha.png", "key"):
            tap_until_found(device_port, "m_mission.png", "key", "zz_home2.png", "key", "tap")
            tap_until_found(device_port, "m_mission_b.png", "key", "m_mission.png", "key", "tap")
        perform_action(device_port, 'swipe', 100, 400, 100, 500, duration=300)

def name_change(device_port: str, folder: str, multi_logger: Optional[MultiDeviceLogger] = None) -> bool:

    home(device_port, folder)

    tap_until_found(device_port, "option.png", "key", "sonota.png", "key", "tap")
    tap_until_found(device_port, "waku.png", "key", "option.png", "key", "tap")
    time.sleep(1)
    tap_if_found('tap', device_port, "name.png", "key")
    time.sleep(1)
    send_key_event(device_port, key_event=67, times=8)
    type_folder_name(device_port, name_prefix)
    send_key_event(device_port, key_event=66)
    tap_if_found('tap', device_port, "name_ok.png", "key")
    time.sleep(1)
    tap_if_found('tap', device_port, "name_ok2.png", "key")

def mon_gacha_shinshun(device_port: str, folder: str, gacha_limit: int = 16 , multi_logger: Optional[MultiDeviceLogger] = None) -> bool:

    home(device_port, folder)

    gacha_count = 0
    found_character = False

    tap_until_found(device_port, "gacha_black.png", "key", "gacha.png", "key", "tap")
    time.sleep(2)

    while True:
        # キャラクター獲得判定
        if tap_if_found('stay', device_port, "01_hoshi_sentaku.png", "hoshi"):
            time.sleep(6)
            while not tap_if_found('stay', device_port, "shinshun_zenshin.png", "end"):
                for img_file in sorted(os.listdir(get_resource_path("hoshi", "gazo"))):
                    tap_if_found('tap', device_port, img_file, "hoshi")
                    time.sleep(1)
            found_character = True

        elif tap_if_found('stay', device_port, "shinshun_icon.png", "end") or tap_if_found('stay', device_port, "shinshun_zenshin.png", "end") or tap_if_found('stay', device_port, "syoji1.png", "end") or tap_if_found('stay', device_port, "syoji2.png", "end"):
            found_character = True

        elif tap_if_found('stay', device_port, "empty.png", "end"):
            logger.warning(f"オーブ切れ - ポート: {device_port}")
            break

        # ガチャを引く
        if gacha_count < gacha_limit:  # 16回目までは通常タップ
            if tap_if_found('tap', device_port, "gacharu.png", "end"):
                gacha_count += 1
        elif gacha_count == gacha_limit:  # 17回目はタップせず検出のみ
            if tap_if_found('stay', device_port, "gacharu.png", "end"):
                logger.info(f"17回目のガチャるを検出しましたが、タップはしません - ポート: {device_port}")
                break  # キャラ獲得画面または17回目のガチャる検出で終了

        # 他の画像をタップ
        for img_file in sorted(os.listdir(get_resource_path("gacha", "gazo"))):
            if img_file.endswith('.png'):
                tap_if_found('tap', device_port, img_file, "gacha")
        
        if tap_if_found('tap', device_port, "sell2.png", "key"):
            sell_operations = [("l4check.png", "pre.png"), ("l5check.png", "sonota.png")]
            for level_check_img, category_img in sell_operations:
                if not perform_monster_sell(device_port, level_check_img, category_img):
                    raise Exception(f"売却処理失敗: {level_check_img}")
            tap_until_found(device_port, "gacharu.png", "end", "back.png", "key", "tap")

        # スクロール操作
        tap_if_found('swipe_down', device_port, "tama.png", "key")
        tap_if_found('swipe_down', device_port, "tama2.png", "key")
        tap_if_found('swipe_down', device_port, "hoshi_tama.png", "key")
        tap_if_found('swipe_down', device_port, "hoshi_tama2.png", "key")


        if found_character == True and tap_if_found('stay', device_port, "gacharu.png", "end"):
            break

    return found_character

def mon_sell(device_port: str, folder: str, multi_logger: Optional[MultiDeviceLogger] = None) -> bool:
    
    home(device_port, folder)

    tap_until_found(device_port, "monbox.png", "key", "monster.png", "key", "tap")
    tap_until_found(device_port, "sell.png", "key", "monbox.png", "key", "swipe_up", "tap", timeout=30)

    sell_operations = [("l4check.png", "pre.png"), ("l5check.png", "sonota.png")]
    for level_check_img, category_img in sell_operations:
        if not perform_monster_sell(device_port, level_check_img, category_img):
            raise Exception(f"売却処理失敗: {level_check_img}")

    if multi_logger:
        multi_logger.log_success(device_port)
    return True

def perform_monster_sell(device_port: str, level_check_img: str, category_img: str) -> bool:
    max_attempts = 8
    for _ in range(max_attempts):
        while not tap_if_found('stay', device_port, "sentaku.png", "del"):
            tap_if_found('tap', device_port, "ikkatsu.png", "del")
            tap_if_found('tap', device_port, "ok2.png", "del")
            time.sleep(1)

        while not tap_if_found('stay', device_port, level_check_img, "del"):
            tap_if_found('tap', device_port, "l4.png" if level_check_img == "l4check.png" else "l5.png", "del")
            tap_if_found('tap', device_port, category_img, "del")

        if tap_until_found(device_port, "kakunin.png", "del", "kakunin.png", "del", "stay", "tap", timeout=10):
            time.sleep(1)
            if tap_if_found('stay', device_port, "jogen.png", "del"):
                tap_if_found('tap', device_port, "ok2.png", "del")
            tap_until_found(device_port, "ok.png", "del", "ok.png", "del", "stay", "tap", timeout=10)
            
            while not tap_if_found('stay', device_port, "off.png", "del"):
                for img in ["yes.png", "yes2.png", "yes3.png"]:
                    tap_if_found('tap', device_port, img, "del")
                time.sleep(2)

        if tap_if_found('stay', device_port, "end.png", "del"):
            tap_if_found('tap', device_port, "ok2.png", "del")
            return True

    return False

def friends(device_port: str, folder: str, multi_logger: Optional[MultiDeviceLogger] = None) -> bool:

    home(device_port, folder)

    tap_until_found(device_port, "friends_search.png", "key", "friends.png", "key", "tap")
    if id1:
        mon_friends(device_port, id1)
    if id2:
        mon_friends(device_port, id2)
    if id3:
        mon_friends(device_port, id3)
    if id4:
        mon_friends(device_port, id4)
    if id5:
        mon_friends(device_port, id5)
    if id6:
        mon_friends(device_port, id6)
    if id7:
        mon_friends(device_port, id7)
    if id8:
        mon_friends(device_port, id8)
    if id9:
        mon_friends(device_port, id9)
    if id10:
        mon_friends(device_port, id10)
    if id11:
        mon_friends(device_port, id11)
    if id12:
        mon_friends(device_port, id12)

    if multi_logger:
        multi_logger.log_success(device_port)
    return True

def mon_friends(device_port: str, id_f: str) -> None:
    tap_until_found(device_port, "friends_no.png", "key", "friends_search.png", "key", "tap")
    tap_if_found('tap', device_port, "friends_no.png", "key")
    send_key_event(device_port, text=id_f)
    send_key_event(device_port, key_event=66)
    tap_until_found(device_port, "last.png", "key", "search.png", "key", "tap")
    tap_until_found(device_port, "yes_f.png", "key", "last.png", "key", "tap")
    tap_until_found(device_port, "ok_f.png", "key", "yes_f.png", "key", "tap")

    # 最後の処理を修正
    while True:
        if tap_if_found('stay', device_port, "friends_no.png", "key"):
            tap_if_found('tap', device_port, "ok_f.png", "key")
            logger.info(f"フレンド申請完了 (ID: {id_f})")
            break
        elif tap_if_found('stay', device_port, "friendzumi.png", "key"):
            while not tap_if_found('stay', device_port, "friends_search.png", "key"):
                tap_if_found('tap', device_port, "ok_f2.png", "key")
                tap_if_found('tap', device_port, "back.png", "key")
            tap_until_found(device_port, "friends_no.png", "key", "friends_search.png", "key", "tap")
            logger.info(f"既にフレンド済み (ID: {id_f})")
            break
        else:
            tap_if_found('tap', device_port, "ok_f.png", "key")

def orb_count(device_port: str, folder: str, found_character, multi_logger: Optional[MultiDeviceLogger] = None) -> bool:

    home(device_port, folder)

    start_time = time.time()
    timeout = 300  # 5分のタイムアウト
    max_retries = 5

    while time.time() - start_time < timeout:
        for _ in range(max_retries):
            try:
                orbs = read_orb_count(device_port, folder)
                if orbs is not None:
                    if 1 <= orbs <= 5000:
                        # キャラ獲得状況とオーブ数をCSVに記録
                        if update_csv_data("orb_data.csv", folder, orbs, found_character):
                            if multi_logger:
                                multi_logger.log_success(device_port)
                            logger.info(f"フォルダ {folder} のオーブ数を確定: {orbs}, キャラ獲得: {found_character}")
                            return True
                        else:
                            logger.error(f"フォルダ {folder} のデータ保存に失敗しました: オーブ数 {orbs}, キャラ獲得 {found_character}")
                    else:
                        logger.warning(f"無効なオーブ数が検出されました: {orbs} (デバイス {device_port}, フォルダ {folder})")
            except pytesseract.TesseractNotFoundError:
                logger.error("Tesseract OCRが見つかりません。インストールと設定を確認してください。")
                return False
            
            time.sleep(2)  # 各試行間の待機時間

        # スクリーンの更新
        logger.warning(f"フォルダ {folder} のオーブ数読み取りに失敗。画面を更新します。")
        tap_if_found('tap', device_port, "zz_home.png", "key")
        tap_if_found('tap', device_port, "zz_home2.png", "key")
        perform_action(device_port, 'tap', 50, 170, duration=150)
        time.sleep(2)

    logger.error(f"フォルダ {folder} のオーブ数の読み取りがタイムアウトしました")
    return False

def device_operation_hasya(device_port: str, folder: str, multi_logger: Optional[MultiDeviceLogger] = None) -> bool:
    try:
        if not device_operation_login(device_port, folder, multi_logger):
            logger.error(f"ログイン失敗 (フォルダ：{folder})")
            if multi_logger:
                multi_logger.log_error(device_port, f"ログイン失敗 (フォルダ：{folder})")
            return False

        while True:
            if tap_if_found('stay', device_port, "start.png", "quest"):
                if not tap_if_found('stay', device_port, "dekki_null2.png", "key"):
                    break
            tap_if_found('tap', device_port, "quest_c.png", "key")
            tap_if_found('tap', device_port, "quest.png", "key")
            tap_if_found('tap', device_port, "ichiran.png", "key")
            tap_if_found('tap', device_port, "ok.png", "key")
            tap_if_found('tap', device_port, "close.png", "key")
            tap_if_found('tap', device_port, "hasyatou.png", "key")
            tap_if_found('tap', device_port, "shohi20.png", "key")
            tap_if_found('tap', device_port, "minnato.png", "key")
            tap_if_found('tap', device_port, "multi.png", "key")
            if tap_if_found('stay', device_port, "dekki_null2.png", "key"):
                tap_until_found(device_port, "go_tittle.png", "key", "sonota.png", "key", "tap")
                tap_until_found(device_port, "date_repear.png", "key", "go_tittle.png", "key", "tap")
                tap_until_found(device_port, "data_yes.png", "key", "date_repear.png", "key", "tap")
                tap_until_found(device_port, "zz_home.png", "key", "data_yes.png", "key", "tap")  
            time.sleep(2)

        suffixes = ('62025', '62026', '62027', '62029', '62030', '62031')
        if device_port.endswith(suffixes):
            tap_if_found('tap', device_port, "zz_home.png", "key")

        if multi_logger:
            multi_logger.log_success(device_port)
        return True

    except Exception as e:
        error_msg = f"{str(e)} (フォルダ：{folder})"
        logger.error(f"覇者の塔操作中にエラーが発生しました: {error_msg}", exc_info=True)
        if multi_logger:
            multi_logger.log_error(device_port, error_msg)
        return False

def device_operation_hasya_wait(device_port: str, multi_logger: Optional[MultiDeviceLogger] = None) -> bool:
    start_time = time.time()
    timeout = 6 * 60 * 60  # 6時間（秒単位）

    try:
        while True:
            # 4時間経過したか確認
            if time.time() - start_time > timeout:
                # タイムアウト時に通知を送信
                send_notification_email(
                    subject="停滞通知",
                    message=f"{device_port} で6時間以内に覇者作業が完了しませんでした。",
                    to_email="naka1986222@gmail.com"  # 通知を受け取るメールアドレス
                )
                break  # ループを抜ける

            if tap_if_found('tap', device_port, "icon.png", "key"):
                break  # アイコンが見つかったらループを抜ける
            
            time.sleep(120)  # 2分間隔で再チェック

        if multi_logger:
            multi_logger.log_success(device_port)
        return True

    except Exception as e:
        if multi_logger:
            multi_logger.log_error(device_port, str(e))
        return False

def device_operation_hasya_fin(device_port: str, multi_logger: Optional[MultiDeviceLogger] = None) -> bool:
    start_time = time.time()
    timeout = 3 * 60  # 3分（秒単位）

    try:
        while True:
            # 10分経過したか確認
            if time.time() - start_time > timeout:
                send_notification_email(
                    subject="タイムアウト通知",
                    message=f"{device_port} で3分以内に覇者finが見つかりませんでした。",
                    to_email="naka1986222@gmail.com"  # 通知を受け取るメールアドレス
                )
                break  # タイムアウト後はループを抜ける

            tap_if_found('tap', device_port, "icon.png", "key")
            tap_if_found('tap', device_port, "zz_home.png", "key")
            time.sleep(1)
            tap_if_found('tap', device_port, "quest_c.png", "key")
            tap_if_found('tap', device_port, "quest.png", "key")
            time.sleep(1)
            for _ in range(10):
                tap_if_found('tap', device_port, "a_ok1.png", "key")
                tap_if_found('tap', device_port, "a_ok2.png", "key")
                tap_if_found('tap', device_port, "close.png", "key")
            if (tap_if_found('tap', device_port, "hasyafin1.png", "key") or 
                tap_if_found('tap', device_port, "hasyafin2.png", "key") or 
                tap_if_found('tap', device_port, "hasyafin3.png", "key")):
                break
            time.sleep(1)

        if multi_logger:
            multi_logger.log_success(device_port)
        return True

    except Exception as e:
        if multi_logger:
            multi_logger.log_error(device_port, str(e))
        return False

def device_operation_excel_and_save(device_port: str, workbook, start_row: int, end_row: int, completion_event, multi_logger: Optional[MultiDeviceLogger] = None) -> bool:
    try:
        for current_row in range(start_row, end_row + 1):
            row_data = [cell.value for cell in workbook.active[current_row]]

            if row_data is None:
                break

            xflag_id, password, account_id, user_name = row_data
            start_monster_strike_app(device_port)
            while not tap_if_found('tap', device_port, "hikitsugi.png", "new"):
                tap_if_found('tap', device_port, "doui.png", "new")
                perform_action(device_port, 'tap', 50, 170, duration=150)
            tap_until_found(device_port, "yes.png", "new", "hikitsugi.png", "new", "tap")
            tap_until_found(device_port, "XFLAGID.png", "new", "yes.png", "new", "tap")
            tap_until_found(device_port, "kochira.png", "new", "XFLAGID.png", "new", "tap")
            tap_until_found(device_port, "XFLAGID.png", "new", "kochira.png", "new", "tap")
            while not tap_if_found('tap', device_port, "mail.png", "new"):
                tap_if_found('tap', device_port, "XFLAGID.png", "new")
                tap_if_found('tap', device_port, "mail2.png", "new")
            time.sleep(1)
            send_key_event(device_port, text=xflag_id)
            tap_if_found('tap', device_port, "pass.png", "new")
            tap_if_found('tap', device_port, "pass.png", "new")
            time.sleep(1)
            send_key_event(device_port, text=password)
            tap_until_found(device_port, "kyoka.png", "new", "login.png", "new", "tap")
            tap_until_found(device_port, "ID.png", "new", "kyoka.png", "new", "tap")
            
            tap_if_found('tap', device_port, "ID.png", "new")
            time.sleep(1)
            send_key_event(device_port, text=account_id)
            while True:
                # "ok.png" を探して押す
                if tap_if_found('tap', device_port, "ok.png", "new"):
                    time.sleep(2)  # "yes2.png" または "fri_x.png" が表示されるまでの待機

                # "yes2.png" を探す
                if tap_if_found('stay', device_port, "yes2.png", "new"):
                    # "yes2.png" が見つかった場合のみ次の処理に進む
                    break  # 次の処理に進むためループを抜ける

                # "fri_x.png" を探す
                if tap_if_found('stay', device_port, "fri_x.png", "new"):
                    # "fri_x.png" が見つかった場合のみログを記録し作業を終了
                    logger.error(f"端末 {device_port}: 'fri_x.png' が見つかったため作業を終了します。失敗としてログに記録します。")
                    if multi_logger:
                        multi_logger.log_error(device_port, "fri_x.png detected. Marked as failed.")
                    completion_event.set()  # 次のタスクが進行できるようにする
                    return False  # 作業失敗として終了

            tap_until_found(device_port, "ok2.png", "new", "yes2.png", "new", "tap")
            tap_until_found(device_port, "download.png", "new", "ok2.png", "new", "tap")
            tap_if_found('tap', device_port, "download.png", "new")
            tap_if_found('tap', device_port, "download.png", "new")
            for _ in range(6):
                while not tap_if_found('stay', device_port, "room.png", "key"):
                    handle_screens(device_port,"login")
                    tap_if_found('tap', device_port, "zz_home.png", "key")
                    if tap_if_found('tap', device_port, "gacha_shu.png", "new"):
                        tap_until_found(device_port, "zz_home.png", "key", "zz_home2.png", "key", "tap")
                    perform_action(device_port, 'tap', 50, 170, duration=150)
                time.sleep(0.5)
            mon_initial(device_port, user_name)
            pull_file_from_nox(device_port, user_name)

        completion_event.set()
        if multi_logger:
            multi_logger.log_success(device_port)
        return True

    except Exception as e:
        if multi_logger:
            multi_logger.log_error(device_port, str(e))
        completion_event.set()
        return False

def device_operation_nobin(device_port: str, multi_logger: Optional[MultiDeviceLogger] = None) -> bool:
    try:
        def find_and_tap_parallel(device_port):
            with concurrent.futures.ThreadPoolExecutor() as executor:
                futures = [
                    executor.submit(tap_if_found, 'tap', device_port, f"m{i}.png", "mon")
                    for i in range(1, 16)
                ]
                
                for future in concurrent.futures.as_completed(futures):
                    result = future.result()
                    if result:
                        # 画像が見つかりタップが成功した時点で全スレッドを停止
                        executor.shutdown(wait=False)
                        break

        while True:
            find_and_tap_parallel(device_port)
    
    except Exception as e:
        logger.error(f"device_operation_nobin 中にエラーが発生しました: {e}")
        if multi_logger:
            multi_logger.log_error(device_port, f"エラー: {e}")
        return False

def device_operation_quest(device_port: str, folder: str, multi_logger: Optional[MultiDeviceLogger] = None) -> bool:
    try:
        if not device_operation_login(device_port, folder, multi_logger):
            logger.error(f"ログイン失敗 (フォルダ：{folder})")
            if multi_logger:
                multi_logger.log_error(device_port, f"ログイン失敗 (フォルダ：{folder})")
            return False
        
        # 条件式によるタイムアウト付きループ
        start_time = time.time()
        timeout = 100  # 1.5分間のタイムアウト

        while time.time() - start_time < timeout:
            if tap_if_found('stay', device_port, "battle.png", "quest"):
                break
            if on_que == 1: # イベントクエスト
                tap_if_found('tap', device_port, "pue_shohi.png", "quest")
                tap_if_found('tap', device_port, "chosen.png", "quest")
                tap_if_found('tap', device_port, "chosen_ok.png", "quest")
                tap_if_found('tap', device_port, "counter.png", "quest")
                if tap_if_found('stay', device_port, "eventblack.png", "quest"):
                    if not (tap_if_found('tap', device_port, "event_pue1.png", "quest") or tap_if_found('tap', device_port, "event_pue2.png", "quest") or tap_if_found('tap', device_port, "event_pue3.png", "quest")):
                        tap_if_found('swipe_up', device_port, "eventblack.png", "key")
                        tap_if_found('swipe_up', device_port, "eventblack.png", "key")
                        tap_if_found('swipe_up', device_port, "eventblack.png", "key")
                        if not (tap_if_found('tap', device_port, "event_pue1.png", "quest") or tap_if_found('tap', device_port, "event_pue2.png", "quest") or tap_if_found('tap', device_port, "event_pue3.png", "quest")):
                            return True
            if on_que == 2: # 守護獣
                tap_if_found('tap', device_port, "quest_c.png", "key")
                tap_if_found('tap', device_port, "quest.png", "key")
                tap_if_found('tap', device_port, "ichiran.png", "key")
                tap_if_found('tap', device_port, "shugo_que.png", "quest")
                tap_if_found('tap', device_port, "kyukyoku.png", "key")
                tap_if_found('tap', device_port, "shugo.png", "quest")
            if tap_if_found('tap', device_port, "solo.png", "key"):
                while not tap_if_found('tap', device_port, "start.png", "quest"):
                    perform_action(device_port, 'tap', 200, 575, duration=200) 
            if tap_if_found('stay', device_port, "dekki_null.png", "key"):
                timeout = timeout + 300
                tap_until_found(device_port, "go_tittle.png", "key", "sonota.png", "key", "tap")
                while not tap_if_found('tap', device_port, "date_repear.png", "key"):
                    tap_if_found('tap', device_port, "go_tittle.png", "key")
                    tap_if_found('tap', device_port, "sonota.png", "key")
                tap_until_found(device_port, "data_yes.png", "key", "date_repear.png", "key", "tap")
                tap_until_found(device_port, "zz_home.png", "key", "data_yes.png", "key", "tap")   
            tap_if_found('tap', device_port, "close.png", "key")
            tap_if_found('tap', device_port, "start.png", "quest")
            tap_if_found('tap', device_port, "kaifuku.png", "quest")
            tap_if_found('tap', device_port, "ok.png", "key")
            if tap_if_found('stay', device_port, "uketsuke.png", "key"):
                tap_if_found('tap', device_port, "zz_home.png", "key")
            time.sleep(1)  # 次のループまでの短い待機時間
        else:
            print(f"デバイス {device_port}: 1.5分間 'battle.png' が見つかりませんでした。タイムアウトします。")

        for _ in range(300):  # 300回のループ（約10分間）
            time.sleep(2)
            if tap_if_found('stay', device_port, "que_end.png", "quest"):
                break
            tap_if_found('tap', device_port, "que_ok.png", "quest")
            tap_if_found('tap', device_port, "que_yes.png", "quest")
            mon_swipe(device_port)
        else:
            # タイムアウト時にフォルダ番号をログに記録
            logger.error(f"タイムアウト: 10分間画像が見つかりませんでした (フォルダ: {folder})")

        if multi_logger:
            multi_logger.log_success(device_port)
        return True
    
    except Exception as e:
        logger.error(f"device_operation_quest 中にエラーが発生しました: {e}")
        if multi_logger:
            multi_logger.log_error(device_port, f"エラー: {e}")
        return False


def mon_initial(device_port: str, folder: str, multi_logger: Optional[MultiDeviceLogger] = None) -> bool:

    home(device_port, folder)

    tap_until_found(device_port, "option.png", "key", "sonota.png", "key", "tap")
    tap_until_found(device_port, "waku.png", "key", "option.png", "key", "tap")
    time.sleep(1)
    while not tap_if_found('stay', device_port, "op_end.png", "key"):
        tap_if_found('swipe_up', device_port, "waku.png", "key") 
        time.sleep(1)
        for _ in range(3):
            tap_if_found('tap', device_port, "off.png", "key") 
    
    while not tap_if_found('stay', device_port, "nicname.png", "key"):
        tap_if_found('swipe_down', device_port, "waku.png", "key") 
        for _ in range(3):
            tap_if_found('tap', device_port, "off.png", "key") 
    tap_until_found(device_port, "name_hen.png", "key", "name_ok.png", "key", "tap")
    tap_until_found(device_port, "name_ok.png", "key", "name_ok2.png", "key", "tap")
    tap_until_found(device_port, "zz_home.png", "key", "zz_home2.png", "key", "tap")



def continue_hasya():
    settings_file_9 = r"C:\Users\santa\Desktop\MM\[周回マクロ設定]\【設定】(9)保存した設定.txt"
    settings_file_10 = r"C:\Users\santa\Desktop\MM\[周回マクロ設定]\【設定】(10)保存した設定.txt"
    start_app = r"C:\Users\santa\Desktop\MM\start_app.exe"

    # 端末ごとの設定
    devices = [
        ("1", "62025", "81", "Q", room_key1, settings_file_9),
        ("2", "62026", "87", "W", room_key1, settings_file_9),
        ("3", "62027", "69", "E", room_key1, settings_file_9),
        ("4", "62028", "82", "R", room_key1, settings_file_10),  # load10.png 使用
        ("5", "62029", "65", "A", room_key2, settings_file_9),
        ("6", "62030", "83", "S", room_key2, settings_file_9),
        ("7", "62031", "68", "D", room_key2, settings_file_9),
        ("8", "62032", "70", "F", room_key2, settings_file_10)  # load10.png 使用
    ]

    for window_name, port, code, key, room_key, settings_file in devices:
        # ファイル書き換え処理
        success = False
        retries = 3
        while not success and retries > 0:
            try:
                replace_multiple_lines_in_file(settings_file, {
                    24: f"tar_device=127.0.0.1:{port}",
                    25: f"output= -P 50037 -s 127.0.0.1:{port}",
                    27: f"main_key={code}",
                    28: f"main_keyF={key}",
                    33: f"room_key={room_key}"
                })
                success = True
            except Exception as e:
                print(f"[ERROR] ファイルの書き換えに失敗しました（{window_name}）：{e}")
                retries -= 1
                time.sleep(2)  # 失敗時にリトライ

        time.sleep(1)  # 書き換え後に少し待機

        # アプリ起動
        subprocess.run(start_app)
        time.sleep(4)  # アプリ起動を待つ

        # **load09.png と load10.png を条件で切り替え**
        load_image = "load10.png" if window_name in ["4", "8"] else "load09.png"

        # 画面のロード完了まで待機
        while not tap_if_found_on_windows("tap", "load.png", "macro"):
            tap_if_found_on_windows("tap", "macro.png", "macro")
            if tap_if_found_on_windows("stay", "koshin.png", "macro"):
                tap_if_found_on_windows("tap", "close.png", "macro")
        tap_until_found_on_windows(load_image, "macro", "load.png", "macro")
        tap_until_found_on_windows("kaishi.png", "macro", load_image, "macro")
        tap_until_found_on_windows("nox.png", "macro", "kaishi.png", "macro")
        tap_if_found_on_windows("tap", "ok.png", "macro")

        time.sleep(2)  # 確実に次の処理へ移るため待機

        # ウィンドウをアクティブにして右クリック
        activate_window_and_right_click(window_name)




def load_macro(number: int):
    settings_file = fr"C:\Users\santa\Desktop\MM\[周回マクロ設定]\【設定】({number})保存した設定.txt"
    start_app = r"C:\Users\santa\Desktop\MM\start_app.exe"

    # 端末ごとの設定
    devices = [
        ("1", "62025", "81", "Q", room_key1, settings_file),
        ("2", "62026", "87", "W", room_key1, settings_file),
        ("3", "62027", "69", "E", room_key1, settings_file),
        ("4", "62028", "82", "R", room_key1, settings_file), 
        ("5", "62029", "65", "A", room_key2, settings_file),
        ("6", "62030", "83", "S", room_key2, settings_file),
        ("7", "62031", "68", "D", room_key2, settings_file),
        ("8", "62032", "70", "F", room_key2, settings_file) 
    ]

    for window_name, port, code, key, room_key, settings_file in devices:
        # ファイル書き換え処理
        success = False
        retries = 3
        while not success and retries > 0:
            try:
                replace_multiple_lines_in_file(settings_file, {
                    24: f"tar_device=127.0.0.1:{port}",
                    25: f"output= -P 50037 -s 127.0.0.1:{port}",
                    27: f"main_key={code}",
                    28: f"main_keyF={key}",
                    33: f"room_key={room_key}"
                })
                success = True
            except Exception as e:
                print(f"[ERROR] ファイルの書き換えに失敗しました（{window_name}）：{e}")
                retries -= 1
                time.sleep(2)  # 失敗時にリトライ

        time.sleep(1)  # 書き換え後に少し待機

        # アプリ起動
        subprocess.run(start_app)
        time.sleep(2)  # アプリ起動を待つ

        load_image = "load09.png"

        # 画面のロード完了まで待機
        tap_until_found_on_windows("load.png", "macro", "macro.png", "macro")
        tap_until_found_on_windows(load_image, "macro", "load.png", "macro")
        pyautogui.press("down", presses=number - 1)
        time.sleep(0.5)
        pyautogui.press("enter")
        time.sleep(1.5)
        pyautogui.press("down")
        time.sleep(0.5)
        pyautogui.press("enter")
        time.sleep(1.5)
        pyautogui.write("1")
        pyautogui.press("enter")
        tap_until_found_on_windows("kaishi.png", "macro", "ok.png", "macro")
        tap_until_found_on_windows("nox.png", "macro", "kaishi.png", "macro")
        tap_if_found_on_windows("tap", "ok.png", "macro")

        time.sleep(2)  # 確実に次の処理へ移るため待機

        # ウィンドウをアクティブにして右クリック
        activate_window_and_right_click(window_name)

