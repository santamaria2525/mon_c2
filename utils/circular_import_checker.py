"""
循環インポートチェックユーティリティ

EXE作成前に循環インポートがないかを事前チェックし、
PyInstallerでのビルドエラーを防ぎます。
"""

import ast
import os
import sys
from typing import Dict, List, Set, Tuple
from pathlib import Path

class CircularImportChecker:
    """循環インポートを検出するチェッカー"""
    
    def __init__(self, base_path: str):
        self.base_path = Path(base_path)
        self.imports: Dict[str, Set[str]] = {}
        self.errors: List[str] = []
    
    def check_all_files(self) -> bool:
        """
        プロジェクト内のすべてのPythonファイルをチェック
        
        Returns:
            bool: 循環インポートがない場合True
        """
        print("[CHECK] 循環インポートチェック開始...")
        
        # 全Pythonファイルを収集
        python_files = list(self.base_path.rglob("*.py"))
        print(f"[INFO] チェック対象: {len(python_files)}ファイル")
        
        # 各ファイルのインポートを解析
        for py_file in python_files:
            if self._should_skip_file(py_file):
                continue
            
            try:
                self._analyze_file(py_file)
            except Exception as e:
                print(f"[WARN] {py_file.name}: 解析エラー ({e})")
        
        # 循環インポート検出
        cycles = self._detect_cycles()
        
        if cycles:
            print(f"\n[ERROR] 循環インポートを {len(cycles)} 箇所で検出:")
            for i, cycle in enumerate(cycles, 1):
                print(f"  {i}. {' -> '.join(cycle + [cycle[0]])}")
                self.errors.append(f"循環インポート: {' -> '.join(cycle)}")
            return False
        else:
            print("[OK] 循環インポートは検出されませんでした")
            return True
    
    def _should_skip_file(self, file_path: Path) -> bool:
        """スキップすべきファイルかチェック"""
        skip_patterns = [
            "__pycache__",
            ".git", 
            "dist",
            "build",
            ".spec",
            "old",
            "test_",
            "tmp_"
        ]
        
        file_str = str(file_path)
        return any(pattern in file_str for pattern in skip_patterns)
    
    def _analyze_file(self, file_path: Path) -> None:
        """ファイルのインポート文を解析"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
        except UnicodeDecodeError:
            try:
                with open(file_path, 'r', encoding='cp932') as f:
                    content = f.read()
            except:
                return
        
        try:
            tree = ast.parse(content)
        except SyntaxError:
            return
        
        # モジュール名を取得
        relative_path = file_path.relative_to(self.base_path)
        module_parts = list(relative_path.parts[:-1]) + [relative_path.stem]
        if module_parts[-1] == "__init__":
            module_parts = module_parts[:-1]
        module_name = ".".join(module_parts) if module_parts != ['.'] else "__main__"
        
        if module_name not in self.imports:
            self.imports[module_name] = set()
        
        # インポート文を解析
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imported_module = alias.name.split('.')[0]
                    if self._is_local_module(imported_module):
                        self.imports[module_name].add(imported_module)
            
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imported_module = node.module.split('.')[0]
                    if self._is_local_module(imported_module):
                        self.imports[module_name].add(imported_module)
    
    def _is_local_module(self, module_name: str) -> bool:
        """ローカルモジュールかチェック"""
        # プロジェクト内のモジュールかチェック
        local_modules = [
            "config", "utils", "app", "monst", "adb_utils", 
            "logging_util", "multi_device", "login_operations",
            "device_operations", "missing_functions", "image_detection",
            "app_crash_recovery", "memory_monitor", "independent_worker_system",
            "threading_system", "safety_system"
        ]
        return module_name in local_modules
    
    def _detect_cycles(self) -> List[List[str]]:
        """循環インポートを検出"""
        cycles = []
        visited = set()
        rec_stack = set()
        
        def dfs(node: str, path: List[str]) -> None:
            if node in rec_stack:
                # 循環を発見
                cycle_start = path.index(node)
                cycle = path[cycle_start:]
                cycles.append(cycle)
                return
            
            if node in visited:
                return
            
            visited.add(node)
            rec_stack.add(node)
            
            for neighbor in self.imports.get(node, set()):
                dfs(neighbor, path + [neighbor])
            
            rec_stack.remove(node)
        
        for module in self.imports:
            if module not in visited:
                dfs(module, [module])
        
        return cycles
    
    def get_error_report(self) -> str:
        """エラーレポートを生成"""
        if not self.errors:
            return "[OK] 循環インポートエラーはありません"
        
        report = "[ERROR] 循環インポートエラー:\n"
        for i, error in enumerate(self.errors, 1):
            report += f"  {i}. {error}\n"
        
        report += "\n[FIX] 修正方法:\n"
        report += "  - 遅延インポート（関数内でimport）を使用\n"
        report += "  - 共通の依存関係を別モジュールに移動\n"
        report += "  - インポート順序を見直し\n"
        
        return report

def check_circular_imports(base_path: str = ".") -> bool:
    """
    循環インポートをチェック
    
    Args:
        base_path: プロジェクトのベースパス
        
    Returns:
        bool: 問題がない場合True
    """
    checker = CircularImportChecker(base_path)
    is_clean = checker.check_all_files()
    
    if not is_clean:
        print("\n" + checker.get_error_report())
    
    return is_clean

if __name__ == "__main__":
    # カレントディレクトリをチェック
    result = check_circular_imports(".")
    
    if not result:
        print("\n[WARN] EXE作成前に循環インポートを修正してください")
        sys.exit(1)
    else:
        print("\n[SUCCESS] 循環インポートチェック完了 - EXE作成可能です")