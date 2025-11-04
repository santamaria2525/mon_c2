"""
monst.exceptions - Common exception hierarchy for all monst modules.

monst パッケージ全体で使用する共通の例外階層を定義します。
"""

from __future__ import annotations

class MonstError(Exception):
    """monst パッケージの基底例外クラス。
    
    Args:
        message: エラーメッセージ
        code: エラーコード（オプション）
        
    Example:
        >>> raise MonstError("Something went wrong", code="E001")
    """
    def __init__(self, message: str, code: str | None = None) -> None:
        self.message = message
        self.code = code
        super().__init__(self.message)

class ConfigurationError(MonstError):
    """設定関連のエラー。
    
    設定ファイルの読み込みや設定値の検証に失敗した場合に発生します。
    
    Example:
        >>> raise ConfigurationError("Invalid config value", code="C001")
    """
    pass

class NetworkError(MonstError):
    """ネットワーク関連のエラー。
    
    ADB接続やHTTP通信に失敗した場合に発生します。
    
    Example:
        >>> raise NetworkError("Connection timeout", code="N001")
    """
    pass

class ImageProcessingError(MonstError):
    """画像処理関連のエラー。
    
    画像認識やOCR処理に失敗した場合に発生します。
    
    Example:
        >>> raise ImageProcessingError("Template not found", code="I001")
    """
    pass

class DeviceError(MonstError):
    """デバイス操作関連のエラー。
    
    デバイスの操作や状態管理に失敗した場合に発生します。
    
    Example:
        >>> raise DeviceError("Device not responding", code="D001")
    """
    pass

class ADBError(NetworkError):
    """ADB関連のエラー。
    
    ADBコマンドの実行に失敗した場合に発生します。
    
    Example:
        >>> raise ADBError("ADB command failed", code="A001")
    """
    pass