"""
monst.device.exceptions - Device operation exception hierarchy.

デバイス操作関連の例外クラス階層を定義します。
"""

from __future__ import annotations

class DeviceOperationError(Exception):
    """デバイス操作全般のエラーの基底クラス。
    
    Args:
        message: エラーメッセージ
        
    Example:
        >>> raise DeviceOperationError("Device operation failed")
    """
    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(self.message)

class LoginError(DeviceOperationError):
    """ログイン関連のエラー。
    
    デバイスへのログインやアプリの初期化に失敗した場合に発生します。
    
    Example:
        >>> raise LoginError("Failed to login to device")
    """
    pass

class GachaOperationError(DeviceOperationError):
    """ガチャ操作関連のエラー。
    
    ガチャの実行や結果処理に失敗した場合に発生します。
    
    Example:
        >>> raise GachaOperationError("Gacha operation timed out")
    """
    pass

class SellOperationError(DeviceOperationError):
    """売却操作関連のエラー。
    
    キャラクターやアイテムの売却処理に失敗した場合に発生します。
    
    Example:
        >>> raise SellOperationError("Failed to sell items")
    """
    pass

class ScreenshotError(DeviceOperationError):
    """スクリーンショット取得関連のエラー。
    
    デバイスからのスクリーンショット取得に失敗した場合に発生します。
    
    Example:
        >>> raise ScreenshotError("Screenshot capture failed")
    """
    pass