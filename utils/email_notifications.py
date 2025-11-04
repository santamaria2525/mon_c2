"""
Email notification utilities for Monster Strike Bot

This module handles email notification operations including:
- SMTP email sending
- Error notification
- Status reporting
- Email rate limiting (1 email per PC per hour)
"""

import smtplib
from email.mime.text import MIMEText
import platform
from datetime import datetime, timedelta
from logging_util import logger
import threading
import time

# メール送信履歴管理（PC単位で1時間1本制限）
class EmailRateLimiter:
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if not self._initialized:
            self.last_send_time = None
            self.cooldown_hours = 1  # 1時間のクールダウン
            self._initialized = True
    
    def can_send_email(self) -> bool:
        """メール送信が可能かどうかを判定"""
        if self.last_send_time is None:
            return True
        
        elapsed_time = datetime.now() - self.last_send_time
        return elapsed_time >= timedelta(hours=self.cooldown_hours)
    
    def record_email_sent(self):
        """メール送信を記録"""
        self.last_send_time = datetime.now()
    
    def get_remaining_cooldown(self) -> str:
        """残りクールダウン時間を文字列で返す"""
        if self.last_send_time is None:
            return "制限なし"
        
        elapsed_time = datetime.now() - self.last_send_time
        remaining = timedelta(hours=self.cooldown_hours) - elapsed_time
        
        if remaining <= timedelta(0):
            return "送信可能"
        
        minutes = int(remaining.total_seconds() / 60)
        return f"{minutes}分後に送信可能"
    
    def reset(self):
        """クールダウンをリセット（ツール再実行時）"""
        self.last_send_time = None

# グローバルなレート制限インスタンス
_rate_limiter = EmailRateLimiter()

def send_notification_email(subject: str, message: str, to_email: str = "naka1986222@gmail.com") -> bool:
    """
    通知メールを送信（1PC1時間1本制限付き）
    
    Args:
        subject: メールの件名
        message: メール本文
        to_email: 送信先メールアドレス
        
    Returns:
        bool: 送信成功かどうか
    """
    # レート制限チェック
    if not _rate_limiter.can_send_email():
        remaining_time = _rate_limiter.get_remaining_cooldown()
        logger.warning(f"メール送信制限中: {remaining_time}")
        logger.warning(f"スキップされたメール - 件名: {subject}")
        return False
    
    # メール設定
    from_email = "naka1986222@gmail.com"  # 送信元メールアドレス
    password = "bbgm bglv zvie wqqm"      # アプリパスワード
    smtp_server = "smtp.gmail.com"        # SMTPサーバー
    smtp_port = 587                       # SMTPポート
    
    try:
        # デバイス情報とタイムスタンプを追加
        device_name = platform.node()
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        message = f"{message}\n\n送信元デバイス: {device_name}\n送信時刻: {timestamp}"

        # メール作成
        msg = MIMEText(message)
        msg["Subject"] = subject
        msg["From"] = from_email
        msg["To"] = to_email

        # 送信
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()  # TLS暗号化
            server.login(from_email, password)
            server.sendmail(from_email, to_email, msg.as_string())
            
        # 送信成功時にレート制限を記録
        _rate_limiter.record_email_sent()
        logger.info(f"通知メールを送信しました: {subject}")
        logger.info(f"次回メール送信可能時刻: {datetime.now() + timedelta(hours=1)}")
        return True
    except Exception as e:
        logger.error(f"通知メールの送信に失敗しました: {e}")
        return False

def reset_email_rate_limit():
    """
    メール送信制限をリセット（ツール再実行時に呼び出し）
    """
    _rate_limiter.reset()

def get_email_status() -> dict:
    """
    現在のメール送信状態を取得
    
    Returns:
        dict: 送信状態情報
    """
    return {
        "can_send": _rate_limiter.can_send_email(),
        "remaining_cooldown": _rate_limiter.get_remaining_cooldown(),
        "last_send_time": _rate_limiter.last_send_time
    }