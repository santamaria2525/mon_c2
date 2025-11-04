"""
デバイス復旧システム - メイン端末特化版

別PC環境でメイン端末（127.0.0.1:62025）が応答しない問題を
自動的に診断・復旧するシステムです。
"""

import time
from typing import List, Optional, Tuple
from logging_util import logger
from monst.adb.core import run_adb_command, reconnect_device, is_device_available

class DeviceRecoverySystem:
    """デバイス復旧システム"""
    
    # 代替ポートの優先順位（メイン端末の代替として使用）
    FALLBACK_PORTS = [
        "127.0.0.1:62028",  # 第1候補
        "127.0.0.1:62029",  # 第2候補
        "127.0.0.1:62030",  # 第3候補
        "127.0.0.1:62031",  # 第4候補
        "127.0.0.1:62032",  # 第5候補
    ]
    
    @staticmethod
    def diagnose_main_terminal(main_port: str = "127.0.0.1:62025") -> Tuple[bool, str]:
        """メイン端末の詳細診断
        
        Args:
            main_port: メイン端末のポート
            
        Returns:
            Tuple[bool, str]: (診断結果, 詳細メッセージ)
        """
        logger.info(f"🔍 メイン端末診断開始: {main_port}")
        
        # 1. ADBデバイスリストでの確認
        devices_output = run_adb_command(["devices"], None, timeout=5)
        if not devices_output or main_port not in devices_output:
            return False, f"ADBデバイスリストに{main_port}が見つかりません"
        
        # 2. 基本的な応答テスト
        echo_result = run_adb_command(["shell", "echo", "test"], main_port, timeout=5)
        if not echo_result or "test" not in echo_result:
            return False, "デバイスからの基本応答がありません"
        
        # 3. ファイルシステムアクセステスト
        ls_result = run_adb_command(["shell", "ls", "/data"], main_port, timeout=10)
        if not ls_result:
            return False, "ファイルシステムへのアクセスができません"
        
        # 4. Monster Strikeディレクトリアクセステスト
        ms_dir = "/data/data/jp.co.mixi.monsterstrike"
        ms_result = run_adb_command(["shell", "ls", ms_dir], main_port, timeout=10)
        if not ms_result:
            return False, f"Monster Strikeディレクトリ({ms_dir})にアクセスできません"
        
        logger.info(f"✅ メイン端末診断完了: {main_port} - 正常")
        return True, "正常"
    
    @staticmethod
    def recover_main_terminal(main_port: str = "127.0.0.1:62025") -> bool:
        """メイン端末の復旧試行
        
        Args:
            main_port: メイン端末のポート
            
        Returns:
            bool: 復旧成功かどうか
        """
        logger.info(f"🔧 メイン端末復旧開始: {main_port}")
        
        # 1. 標準再接続を試行
        if reconnect_device(main_port):
            if is_device_available(main_port):
                logger.info(f"✅ 標準再接続で復旧成功: {main_port}")
                return True
        
        # 2. ADBサーバー全体のリセット
        logger.info("🔄 ADBサーバー全体をリセットします...")
        from monst.adb.core import reset_adb_server
        if reset_adb_server():
            time.sleep(3)
            if is_device_available(main_port):
                logger.info(f"✅ ADBサーバーリセットで復旧成功: {main_port}")
                return True
        
        # 3. NOXエミュレータの再起動（可能な場合）
        logger.info("🔄 NOXエミュレータの再起動を試行...")
        try:
            # NOX再起動コマンド（環境に依存）
            import subprocess
            nox_paths = [
                r"C:\Program Files (x86)\Nox\bin\nox_adb.exe",
                r"C:\Program Files\Nox\bin\nox_adb.exe",
            ]
            
            for nox_path in nox_paths:
                import os
                if os.path.exists(nox_path):
                    # デバイスの切断と再接続
                    subprocess.run([nox_path, "disconnect", main_port], 
                                 capture_output=True, timeout=10)
                    time.sleep(2)
                    result = subprocess.run([nox_path, "connect", main_port], 
                                          capture_output=True, timeout=10)
                    if result.returncode == 0:
                        time.sleep(3)
                        if is_device_available(main_port):
                            logger.info(f"✅ NOX再接続で復旧成功: {main_port}")
                            return True
                    break
        except Exception as e:
            logger.warning(f"NOX再起動中にエラー: {e}")
        
        logger.error(f"❌ メイン端末の復旧に失敗: {main_port}")
        return False
    
    @staticmethod
    def find_alternative_port(excluded_ports: List[str] = None) -> Optional[str]:
        """代替メイン端末を検索
        
        Args:
            excluded_ports: 除外するポートのリスト
            
        Returns:
            Optional[str]: 利用可能な代替ポート、見つからない場合はNone
        """
        if excluded_ports is None:
            excluded_ports = []
        
        logger.info("🔍 代替メイン端末を検索中...")
        
        for port in DeviceRecoverySystem.FALLBACK_PORTS:
            if port in excluded_ports:
                continue
                
            logger.info(f"📱 代替ポート確認中: {port}")
            
            # 基本的な可用性チェック
            if is_device_available(port):
                # より詳細なテスト
                success, message = DeviceRecoverySystem.diagnose_main_terminal(port)
                if success:
                    logger.info(f"✅ 代替メイン端末発見: {port}")
                    return port
                else:
                    logger.warning(f"⚠️ {port}: {message}")
            else:
                logger.debug(f"❌ {port}: 利用不可")
        
        logger.error("❌ 利用可能な代替メイン端末が見つかりません")
        return None
    
    @staticmethod
    def smart_recovery(main_port: str = "127.0.0.1:62025") -> Optional[str]:
        """スマート復旧システム
        
        メイン端末の問題を診断し、復旧または代替端末を提供
        
        Args:
            main_port: メイン端末のポート
            
        Returns:
            Optional[str]: 使用可能なポート（復旧後のメイン端末または代替端末）
        """
        logger.info("🤖 スマート復旧システム開始")
        
        # 1. 現状診断
        is_healthy, diagnosis = DeviceRecoverySystem.diagnose_main_terminal(main_port)
        
        if is_healthy:
            logger.info(f"✅ メイン端末は正常です: {main_port}")
            return main_port
        
        logger.warning(f"⚠️ メイン端末に問題があります: {diagnosis}")
        
        # 2. 復旧試行
        if DeviceRecoverySystem.recover_main_terminal(main_port):
            logger.info(f"🔧 メイン端末を復旧しました: {main_port}")
            return main_port
        
        # 3. 代替端末検索
        alternative = DeviceRecoverySystem.find_alternative_port([main_port])
        if alternative:
            logger.warning(f"🔄 代替メイン端末を使用します: {alternative}")
            return alternative
        
        # 4. 最終手段：利用可能な任意のデバイス
        logger.error("🆘 最終手段：任意の利用可能デバイスを検索...")
        devices_output = run_adb_command(["devices"], None, timeout=5)
        if devices_output:
            import re
            device_pattern = r'(\d+\.\d+\.\d+\.\d+:\d+)\s+device'
            devices = re.findall(device_pattern, devices_output)
            
            for device in devices:
                if device != main_port and is_device_available(device):
                    logger.warning(f"🆘 緊急代替端末として使用: {device}")
                    return device
        
        logger.critical("💥 利用可能なデバイスが見つかりません")
        return None

# システム統合用の便利関数
def ensure_main_terminal_available(main_port: str = "127.0.0.1:62025") -> Optional[str]:
    """メイン端末の可用性を保証
    
    Args:
        main_port: メイン端末のポート
        
    Returns:
        Optional[str]: 使用可能なポート
    """
    return DeviceRecoverySystem.smart_recovery(main_port)

if __name__ == "__main__":
    # テスト実行
    print("=== デバイス復旧システム テスト ===")
    
    result = ensure_main_terminal_available()
    if result:
        print(f"✅ 利用可能なメイン端末: {result}")
    else:
        print("❌ メイン端末の確保に失敗")