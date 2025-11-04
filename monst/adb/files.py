"""
monst.adb.files - File management utilities for device storage.

デバイス上のファイル操作（プル、削除）のヘルパー関数を提供します。
"""

from __future__ import annotations

import os
from typing import Optional

from .core import run_adb_command, APP_PACKAGE

def remove_data10_bin_from_nox(device_port: str) -> None:
    """NOXデバイスからMonster Strikeのデータファイルを完全削除します。
    
    Args:
        device_port: 対象デバイスのポート
        
    Note:
        完全な初期化のために以下を実行:
        1. 主要データファイル削除 (data10.bin, data11.bin, data13.bin, data14.bin, data16.bin, data18.bin)
        2. 共有設定ファイル削除 (shared_prefs)
        3. データベースファイル削除 (databases)
        4. キャッシュディレクトリクリア (cache)
    """
    from logging_util import logger
    
    logger.info(f"🗑️ Monster Strike完全初期化開始 (ポート: {device_port})")
    
    # Step 1: 主要データファイル削除
    data_files = [
        f"/data/data/{APP_PACKAGE}/data10.bin",
        f"/data/data/{APP_PACKAGE}/data11.bin", 
        f"/data/data/{APP_PACKAGE}/data13.bin",
        f"/data/data/{APP_PACKAGE}/data14.bin",
        f"/data/data/{APP_PACKAGE}/data16.bin",
        f"/data/data/{APP_PACKAGE}/data18.bin",
    ]
    
    # logger.info("  • 主要データファイルを削除中...")
    for fp in data_files:
        run_adb_command(["shell", "rm", "-f", fp], device_port)
    
    # Step 2: 共有設定ファイル削除 (アカウント設定など)
    # logger.info("  • 共有設定ファイルを削除中...")
    run_adb_command([
        "shell", "rm", "-rf", 
        f"/data/data/{APP_PACKAGE}/shared_prefs"
    ], device_port)
    
    # Step 3: データベースファイル削除
    # logger.info("  • データベースファイルを削除中...")
    run_adb_command([
        "shell", "rm", "-rf", 
        f"/data/data/{APP_PACKAGE}/databases"
    ], device_port)
    
    # Step 4: キャッシュクリア
    # logger.info("  • キャッシュをクリア中...")
    run_adb_command([
        "shell", "rm", "-rf", 
        f"/data/data/{APP_PACKAGE}/cache"
    ], device_port)
    
    # Step 5: アプリ固有ファイル削除 (存在する場合)
    # logger.info("  • 追加ファイルをクリア中...")
    additional_files = [
        f"/data/data/{APP_PACKAGE}/files",
        f"/data/data/{APP_PACKAGE}/code_cache",
        f"/data/data/{APP_PACKAGE}/no_backup"
    ]
    
    for fp in additional_files:
        run_adb_command(["shell", "rm", "-rf", fp], device_port)
    
    logger.info("✅ Monster Strike完全初期化完了")

def pull_file_from_nox(device_port: str, folder_name: str) -> bool:
    """デバイスからdata10.binを指定フォルダにプルします。
    
    Args:
        device_port: 対象デバイスのポート
        folder_name: 保存先フォルダ名（bin_pull/<folder_name>/に保存）
        
    Returns:
        ファイルプル成功時はTrue
        
    Example:
        >>> pull_file_from_nox("127.0.0.1:62001", "backup_001")
        True  # bin_pull/backup_001/data10.bin に保存
    """
    from utils import get_base_path

    local_dir = os.path.join(get_base_path(), "bin_pull", folder_name)
    os.makedirs(local_dir, exist_ok=True)

    remote = f"/data/data/{APP_PACKAGE}/data10.bin"
    local_path = os.path.join(local_dir, "data10.bin")

    out = run_adb_command(["pull", remote, local_path], device_port)
    return bool(out and os.path.exists(local_path) and os.path.getsize(local_path))

def push_file_to_nox(device_port: str, folder_name: str) -> bool:
    """指定フォルダのdata10.binをデバイスにプッシュします（診断機能付き）。
    
    Args:
        device_port: 対象デバイスのポート
        folder_name: 読み込み元フォルダ名（bin_push/<folder_name>/から読み込み）
        
    Returns:
        ファイルプッシュ成功時はTrue
        
    Example:
        >>> push_file_to_nox("127.0.0.1:62025", "001")
        True  # bin_push/001/data10.bin をデバイスにプッシュ
    """
    from utils import get_base_path
    from logging_util import logger
    import stat
    
    try:
        local_dir = os.path.join(get_base_path(), "bin_push", folder_name)
        local_path = os.path.join(local_dir, "data10.bin")
        
        # ステップ1: 詳細なローカルファイル診断
        logger.info(f"🔍 ファイルプッシュ診断開始: {folder_name} -> {device_port}")
        logger.info(f"📁 ローカルディレクトリ: {local_dir}")
        logger.info(f"📄 ローカルファイル: {local_path}")
        
        if not os.path.exists(local_dir):
            logger.error(f"❌ ディレクトリが存在しません: {local_dir}")
            return False
            
        if not os.path.exists(local_path):
            logger.error(f"❌ ローカルファイルが見つかりません: {local_path}")
            # フォルダ内容を確認
            try:
                files = os.listdir(local_dir)
                logger.info(f"📂 フォルダ内容: {files}")
            except:
                logger.error("📂 フォルダ内容の取得に失敗")
            return False
        
        # ファイル詳細情報
        file_size = os.path.getsize(local_path)
        file_stat = os.stat(local_path)
        file_mode = stat.filemode(file_stat.st_mode)
        
        logger.info(f"📊 ファイル情報:")
        logger.info(f"  - サイズ: {file_size:,} bytes")
        logger.info(f"  - 権限: {file_mode}")
        logger.info(f"  - 修正日時: {file_stat.st_mtime}")
        
        if file_size == 0:
            logger.error(f"❌ ローカルファイルが空です: {local_path}")
            return False
        
        if file_size > 100 * 1024 * 1024:  # 100MB制限
            logger.warning(f"⚠️ ファイルが大きすぎます: {file_size:,} bytes")
        
        # ステップ2: デバイス状態確認（復旧システム付き）
        logger.info(f"📱 デバイス状態確認: {device_port}")
        
        # デバイス接続確認
        device_check = run_adb_command(["shell", "echo", "device_test"], device_port)
        if not device_check or "device_test" not in device_check:
            logger.error(f"❌ デバイス応答なし: {device_port}")
            
            # メイン端末の場合は復旧システムを起動
            if device_port == "127.0.0.1:62025":
                logger.warning("🤖 メイン端末復旧システムを起動します...")
                try:
                    from device_recovery_system import ensure_main_terminal_available
                    recovered_port = ensure_main_terminal_available(device_port)
                    if recovered_port and recovered_port != device_port:
                        logger.warning(f"🔄 代替メイン端末を使用: {device_port} -> {recovered_port}")
                        # 代替端末で再試行
                        return push_file_to_nox(recovered_port, folder_name)
                    elif recovered_port == device_port:
                        logger.info(f"🔧 メイン端末復旧成功: {device_port}")
                        # 復旧後に再試行
                        device_check = run_adb_command(["shell", "echo", "device_test"], device_port)
                        if not device_check or "device_test" not in device_check:
                            logger.error(f"❌ 復旧後も応答なし: {device_port}")
                            return False
                    else:
                        logger.error("❌ メイン端末復旧システムも失敗しました")
                        return False
                except ImportError:
                    logger.error("復旧システムがインポートできません")
                    return False
                except Exception as e:
                    logger.error(f"復旧システム実行エラー: {e}")
                    return False
            else:
                return False
        
        # デバイス容量確認
        df_check = run_adb_command(["shell", "df", "/data"], device_port, timeout=10)
        if df_check:
            logger.info(f"💾 デバイス容量: {df_check.strip()}")
        
        # ステップ3: 対象ディレクトリの権限確認・修正
        remote_dir = f"/data/data/{APP_PACKAGE}"
        remote = f"{remote_dir}/data10.bin"
        
        logger.info(f"🔧 デバイス権限設定確認: {remote_dir}")
        
        # ディレクトリ作成と権限設定
        run_adb_command(["shell", "mkdir", "-p", remote_dir], device_port)
        run_adb_command(["shell", "chmod", "755", remote_dir], device_port)
        
        # 既存ファイル削除
        run_adb_command(["shell", "rm", "-f", remote], device_port)
        
        # ステップ4: ファイルプッシュ実行（詳細診断付きリトライ）
        for attempt in range(3):  # 最大3回リトライ
            logger.info(f"📤 ファイルプッシュ試行 {attempt + 1}/3: {local_path} -> {remote}")
            
            # 詳細診断版のADBコマンドを使用
            from .core import run_adb_command_detailed
            
            stdout, stderr, returncode = run_adb_command_detailed(
                ["push", local_path, remote], device_port, timeout=60
            )
            
            # 詳細なエラー診断
            if returncode == 0 and stdout:
                logger.info(f"📤 プッシュ出力: {stdout.strip()}")
                
                # プッシュ後検証
                verify_cmd = run_adb_command(["shell", "ls", "-la", remote], device_port)
                if verify_cmd and "data10.bin" in verify_cmd:
                    # ファイルサイズ確認
                    size_cmd = run_adb_command(["shell", "stat", "-c", "%s", remote], device_port)
                    if size_cmd:
                        try:
                            remote_size = int(size_cmd.strip())
                            logger.info(f"✅ プッシュ検証: ローカル{file_size} -> リモート{remote_size}")
                            
                            if remote_size == file_size:
                                logger.info(f"✅ ファイルプッシュ成功: {folder_name} -> {device_port}")
                                return True
                            else:
                                logger.warning(f"⚠️ サイズ不一致: ローカル{file_size} != リモート{remote_size}")
                        except ValueError:
                            logger.warning(f"⚠️ リモートサイズ取得失敗: {size_cmd}")
                
                logger.info(f"✅ ファイルプッシュ成功（検証スキップ）: {folder_name} -> {device_port}")
                return True
            else:
                # 詳細なエラー情報をログ出力
                logger.error(f"❌ プッシュ失敗（試行 {attempt + 1}/3）:")
                logger.error(f"  - リターンコード: {returncode}")
                logger.error(f"  - 標準出力: {stdout}")
                logger.error(f"  - 標準エラー: {stderr}")
                
                # エラー原因を分析
                if stderr:
                    error_lower = stderr.lower()
                    if "permission denied" in error_lower:
                        logger.error("🔒 権限エラー検出 - デバイス権限を確認してください")
                        # 権限修正を試行
                        run_adb_command(["shell", "su", "-c", f"chmod 777 {remote_dir}"], device_port)
                    elif "no space" in error_lower or "space left" in error_lower:
                        logger.error("💾 容量不足エラー検出 - デバイスの空き容量を確認してください")
                    elif "device not found" in error_lower or "device offline" in error_lower:
                        logger.error("📱 デバイス接続エラー検出 - ADB接続を確認してください")
                        # デバイス再接続を試行
                        from .core import reconnect_device
                        if reconnect_device(device_port):
                            logger.info("🔗 デバイス再接続成功、次の試行を続行")
                        else:
                            logger.error("🔗 デバイス再接続失敗")
                    elif "read-only" in error_lower:
                        logger.error("📝 読み取り専用エラー検出 - ファイルシステムの状態を確認してください")
                    else:
                        logger.error(f"❓ 不明なエラー: {stderr}")
            
            if attempt < 2:  # 最後の試行でなければ待機
                import time
                wait_time = 2 ** attempt  # 指数バックオフ（1秒、2秒、4秒）
                logger.info(f"⏳ {wait_time}秒待機後、再試行します...")
                time.sleep(wait_time)
        
        logger.error(f"❌ ファイルプッシュ失敗: {folder_name} -> {device_port} (全試行失敗)")
        return False
            
    except Exception as e:
        logger.error(f"❌ ファイルプッシュエラー: {e}")
        import traceback
        logger.error(f"📋 スタックトレース: {traceback.format_exc()}")
        return False