"""
設定管理システム - 循環インポート完全回避版

PyInstaller EXE環境での動作を保証するため、
外部モジュールへの依存を最小限に抑えた設計です。
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List

# ---------------------------------------------------------------------------
# 外部依存を排除したヘルパー関数
# ---------------------------------------------------------------------------

def _get_resource_path(relative_path: str) -> str:
    """リソースパスを取得（EXE環境で設定ファイルを正しく読み込み）"""
    try:
        # PyInstaller EXE環境 - EXEと同じディレクトリの設定ファイルを読み込み
        if getattr(sys, 'frozen', False):
            # EXEファイルと同じディレクトリを使用
            base_path = os.path.dirname(sys.executable)
        else:
            # 開発環境
            base_path = os.path.dirname(os.path.abspath(__file__))
        
        full_path = os.path.join(base_path, relative_path)
        # Quiet startup: suppress verbose path resolution log
        # _safe_print("DEBUG", f"設定パス解決: {relative_path} -> {full_path}")
        return full_path
    except Exception as e:
        _safe_print("ERROR", f"パス解決エラー: {e}")
        # フォールバック
        return relative_path

def _detect_nox_adb_path() -> str:
    """NOX ADBパスを自動検出（環境適応機能）"""
    possible_paths = [
        r"C:\Program Files (x86)\Nox\bin\adb.exe",
        r"C:\Program Files\Nox\bin\adb.exe",
        r"C:\Nox\bin\adb.exe",
        r"D:\Program Files (x86)\Nox\bin\adb.exe",
        r"D:\Program Files\Nox\bin\adb.exe",
        r"D:\Nox\bin\adb.exe",
        r"E:\Program Files (x86)\Nox\bin\adb.exe",
        r"E:\Program Files\Nox\bin\adb.exe",
        r"E:\Nox\bin\adb.exe"
    ]
    
    for path in possible_paths:
        if os.path.exists(path):
            _safe_print("INFO", f"NOX ADB検出: {path}")
            return path
    
    _safe_print("WARN", "NOX ADBが見つかりません。デフォルトパスを使用します")
    return r"C:\Program Files (x86)\Nox\bin\adb.exe"

def _safe_print(level: str, message: str) -> None:
    """安全なログ出力（logging_util依存を排除）"""
    try:
        print(f"[{level}] {message}")
    except:
        pass  # 出力エラーも無視

def get_ports_by_count(device_count: int) -> List[str]:
    """
    指定された台数分のポートリストを返す（完璧なバリデーション付き）
    
    Args:
        device_count: 端末台数（1-8台の範囲）
        
    Returns:
        List[str]: 指定台数分のポートリスト
        
    Raises:
        ValueError: 無効な台数指定時
    """
    all_ports = [
        "127.0.0.1:62025", "127.0.0.1:62026", "127.0.0.1:62027", "127.0.0.1:62028",
        "127.0.0.1:62029", "127.0.0.1:62030", "127.0.0.1:62031", "127.0.0.1:62032"
    ]
    
    # 厳密なバリデーション
    if not isinstance(device_count, int):
        _safe_print("ERROR", f"端末台数は整数で指定してください: {type(device_count).__name__}")
        device_count = 8  # デフォルト値にフォールバック
    
    if device_count < 1:
        _safe_print("WARN", f"端末台数が少なすぎます（{device_count}台）。最低1台に設定します。")
        return all_ports[:1]
    elif device_count > 8:
        _safe_print("WARN", f"端末台数が多すぎます（{device_count}台）。最大8台に設定します。")
        return all_ports
    else:
        # 端末台数設定ログは抑制（OperationsManagerで制御）
        return all_ports[:device_count]

def validate_device_count(device_count: int) -> bool:
    """端末台数設定の妥当性をチェック"""
    if not isinstance(device_count, int):
        return False
    return 3 <= device_count <= 8

def _coerce_ports(value) -> List[str]:
    """ポート設定値を統一フォーマットに変換"""
    if isinstance(value, int):
        # select_portsが整数の場合、その数だけのポートリストを生成
        return get_ports_by_count(value)
    elif isinstance(value, str):
        if ":" in value:
            return [value]
        else:
            return [f"127.0.0.1:{value}"]
    elif isinstance(value, list):
        result = []
        for item in value:
            if isinstance(item, int):
                result.append(f"127.0.0.1:{item}")
            elif isinstance(item, str):
                if ":" in item:
                    result.append(item)
                else:
                    result.append(f"127.0.0.1:{item}")
        return result
    else:
        return []

# ---------------------------------------------------------------------------
# 設定データクラス
# ---------------------------------------------------------------------------

@dataclass
class _Config:
    """設定データクラス（外部依存なし）"""
    
    # ADB設定
    NOX_ADB_PATH: str = r"C:\Program Files (x86)\Nox\bin\adb.exe"
    
    # デバイス設定
    common_ports: List[str] = field(default_factory=lambda: [
        "127.0.0.1:62025", "127.0.0.1:62026", "127.0.0.1:62027",
        "127.0.0.1:62028", "127.0.0.1:62029", "127.0.0.1:62030"
    ])
    host_ports: List[str] = field(default_factory=lambda: [
        "127.0.0.1:62025", "127.0.0.1:62026", "127.0.0.1:62027"
    ])
    sub_ports: List[str] = field(default_factory=lambda: [
        "127.0.0.1:62028", "127.0.0.1:62029", "127.0.0.1:62030"
    ])
    
    # バッチ設定
    folders_per_batch: int = 700
    select_ports: List[str] = field(default_factory=lambda: [
        "127.0.0.1:62025", "127.0.0.1:62026", "127.0.0.1:62027",
        "127.0.0.1:62028", "127.0.0.1:62029", "127.0.0.1:62030",
        "127.0.0.1:62031", "127.0.0.1:62032"
    ])
    device_count: int = 8
    gacha_limit: int = 0
    login_sleep: int = 5
    
    # ログイン・リトライ設定
    LOGIN_MAX_ATTEMPTS: int = 30
    LOGIN_CONSECUTIVE_SAME_SCREENS_THRESHOLD: int = 10
    
    # 名前設定
    name_prefix: str = "a"
    
    # ID設定
    id1: str = ""
    id2: str = ""
    id3: str = ""
    id4: str = ""
    id5: str = ""
    id6: str = ""
    id7: str = ""
    id8: str = ""
    id9: str = ""
    id10: str = ""
    id11: str = ""
    id12: str = ""
    
    # 機能フラグ
    on_que: int = 1
    on_event: int = 0
    on_medal: int = 0
    on_mission: int = 0
    on_sell: int = 0
    on_initial: int = 0
    on_name: int = 0
    on_gacha: int = 0
    on_gacha_kaisu: int = 30
    on_check: int = 0
    on_count: int = 0
    on_save: int = 0
    on_id_check: int = 0
    
    # ルームキー
    room_key1: str = "617"
    room_key2: str = "618"
    
    # 独立並行処理設定
    use_independent_processing: bool = True
    independent_worker_health_check_interval: int = 60
    independent_worker_timeout: int = 300
    independent_retry_failed_folders: bool = True
    
    # 追加設定用
    extra: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """辞書形式で設定を返す"""
        result = asdict(self)
        result.update(self.extra)
        return result

# ---------------------------------------------------------------------------
# 設定ローダー（完全に独立）
# ---------------------------------------------------------------------------

class _ConfigLoader:
    """設定ローダー（外部依存なし）"""
    
    _cfg: _Config = None
    _path: str = "config.json"
    
    @classmethod
    def _read(cls) -> _Config:
        """JSONファイルから設定を読み込み"""
        # ファイルパスの決定
        config_path = _get_resource_path(cls._path)
        
        try:
            with open(config_path, encoding="utf-8") as fp:
                raw: Dict[str, Any] = json.load(fp)
        except (OSError, json.JSONDecodeError) as exc:
            _safe_print("ERROR", f"Failed to read config.json: {exc}")
            # デフォルト設定で続行
            raw = {}
        
        data = dict(raw)
        
        # ポート設定の正規化
        common_ports = _coerce_ports(data.pop("common_ports", []))
        host_ports = _coerce_ports(data.pop("host_ports", []))
        sub_ports = _coerce_ports(data.pop("sub_ports", []))
        select_ports = _coerce_ports(data.pop("select_ports", 8))
        
        # device_countの完璧なバリデーション
        raw_device_count = data.pop("device_count", 8)
        if not isinstance(raw_device_count, int) or not (3 <= raw_device_count <= 8):
            _safe_print("WARN", f"無効なdevice_count設定: {raw_device_count}。デフォルト8台に設定します。")
            device_count = 8
        else:
            device_count = raw_device_count
            # Quiet startup: suppress device_count info
            # _safe_print("INFO", f"✅ device_count設定確認: {device_count}台")
        
        # NOX ADBパスの自動検出
        nox_adb_path = data.pop("NOX_ADB_PATH", None)
        if not nox_adb_path or not os.path.exists(nox_adb_path):
            nox_adb_path = _detect_nox_adb_path()
        
        # 設定オブジェクト作成
        cfg = _Config(
            NOX_ADB_PATH=nox_adb_path,
            common_ports=common_ports,
            host_ports=host_ports,
            sub_ports=sub_ports,
            select_ports=select_ports,
            folders_per_batch=data.pop("folders_per_batch", 700),
            device_count=device_count,
            gacha_limit=data.pop("gacha_limit", 0),
            login_sleep=data.pop("login_sleep", 5),
            LOGIN_MAX_ATTEMPTS=data.pop("LOGIN_MAX_ATTEMPTS", 30),
            LOGIN_CONSECUTIVE_SAME_SCREENS_THRESHOLD=data.pop("LOGIN_CONSECUTIVE_SAME_SCREENS_THRESHOLD", 10),
            name_prefix=data.pop("name_prefix", "a"),
            id1=data.pop("id1", ""),
            id2=data.pop("id2", ""),
            id3=data.pop("id3", ""),
            id4=data.pop("id4", ""),
            id5=data.pop("id5", ""),
            id6=data.pop("id6", ""),
            id7=data.pop("id7", ""),
            id8=data.pop("id8", ""),
            id9=data.pop("id9", ""),
            id10=data.pop("id10", ""),
            id11=data.pop("id11", ""),
            id12=data.pop("id12", ""),
            on_que=data.pop("on_que", 1),
            on_event=data.pop("on_event", 0),
            on_medal=data.pop("on_medal", 0),
            on_mission=data.pop("on_mission", 0),
            on_sell=data.pop("on_sell", 0),
            on_initial=data.pop("on_initial", 0),
            on_name=data.pop("on_name", 0),
            on_gacha=data.pop("on_gacha", 0),
            on_gacha_kaisu=data.pop("on_gacha_kaisu", 30),
            on_check=data.pop("on_check", 0),
            on_count=data.pop("on_count", 0),
            on_save=data.pop("on_save", 0),
            on_id_check=data.pop("on_id_check", 0),
            room_key1=data.pop("room_key1", "617"),
            room_key2=data.pop("room_key2", "618"),
            use_independent_processing=data.pop("use_independent_processing", True),
            independent_worker_health_check_interval=data.pop("independent_worker_health_check_interval", 60),
            independent_worker_timeout=data.pop("independent_worker_timeout", 300),
            independent_retry_failed_folders=data.pop("independent_retry_failed_folders", True),
            extra=data  # 残りのキーは全てextraに
        )
        
        return cfg
    
    @classmethod
    def load(cls, force: bool = False) -> _Config:
        """設定を読み込み（キャッシュ付き）"""
        if cls._cfg is None or force:
            cls._cfg = cls._read()
            # グローバル変数をエクスポート
            _export_globals(cls._cfg)
            # Quiet startup: suppress config loaded info
            # _safe_print("INFO", "設定を読み込みました")
        return cls._cfg
    
    @classmethod
    def reload(cls) -> _Config:
        """設定を再読み込み"""
        _safe_print("INFO", "設定を再読み込みします")
        return cls.load(force=True)

# ---------------------------------------------------------------------------
# グローバル変数エクスポート
# ---------------------------------------------------------------------------

def _export_globals(cfg: _Config) -> None:
    """設定値をグローバル変数としてエクスポート"""
    g = globals()
    for k, v in cfg.to_dict().items():
        g[k] = v

# ---------------------------------------------------------------------------
# 公開API（外部依存なし）
# ---------------------------------------------------------------------------

def get_config() -> _Config:
    """設定オブジェクトを取得"""
    return _ConfigLoader.load()

def load_config() -> _Config:
    """設定オブジェクトを取得（互換性のため）"""
    return get_config()

def get_config_value(key: str, default: Any = None) -> Any:
    """設定値を取得"""
    cfg = get_config()
    return getattr(cfg, key, cfg.extra.get(key, default))

def reload_config() -> _Config:
    """設定を再読み込み"""
    return _ConfigLoader.reload()

# ---------------------------------------------------------------------------
# モジュール初期化（安全な初期化）
# ---------------------------------------------------------------------------

def _safe_initialize():
    """安全な初期化（エラーを無視）"""
    try:
        get_config()  # 設定読み込みとグローバル変数エクスポート
    except Exception as e:
        _safe_print("WARN", f"設定初期化エラー（デフォルト値を使用）: {e}")
        # デフォルト設定でグローバル変数をエクスポート
        default_cfg = _Config()
        _export_globals(default_cfg)

# 初期化実行
_safe_initialize()

# ---------------------------------------------------------------------------
# 定数（互換性のため）
# ---------------------------------------------------------------------------

# フォルダ・処理制限
MAX_FOLDER_LIMIT = 3000
MAX_FOLDER_SEARCH_ATTEMPTS = 100
MAX_CONSECUTIVE_FAILURES = 50

# スレッド・ワーカー設定
MAX_WORKERS = 8
THREAD_START_DELAY = 2

# 安全性設定
SAFE_MODE = True
MAX_RESTART_DEVICES = 2
MAX_CONCURRENT_LOGIN_DEVICES = 2

# ログイン・リトライ設定
LOGIN_MAX_ATTEMPTS = 30
LOGIN_CONSECUTIVE_SAME_SCREENS_THRESHOLD = 10

# ADB・通信設定
ADB_MAX_CONCURRENT = 2
MIN_ADB_COMMAND_INTERVAL = 3.5

# タイムアウト設定
OPERATION_TIMEOUT = 300
WINDOW_ACTIVATION_RETRIES = 4
WINDOW_OPERATION_DELAY = 1.0

# 入力自動化タイミング
KEY_PRESS_DELAY = 0.2
MOUSE_CLICK_DELAY = 0.3
MOUSE_OPERATION_DELAY = 0.5

# 安定性制御設定
STABILITY_MODE = True
DEVICE_STARTUP_DELAY = 12
LOGIN_EXPONENTIAL_BACKOFF = True
ENABLE_RESOURCE_MONITORING = True
ENABLE_CIRCUIT_BREAKER = True
COOLDOWN_AFTER_FAILURE = 30
