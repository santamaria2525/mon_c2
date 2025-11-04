# -*- coding: utf-8 -*-
"""
PyInstaller helper for the cleaned ``mon_c2`` codebase.

The script mirrors the legacy builder but keeps the workflow concise:
    1. Sanity-check key files/modules
    2. Invoke PyInstaller in one-file mode
    3. Collect the runtime resources required alongside the executable
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

# Ensure project root is importable while running this script.
if str(Path(__file__).resolve().parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

PROJECT_ROOT = Path(__file__).resolve().parent
REPO_ROOT = PROJECT_ROOT.parent
ENTRYPOINT = PROJECT_ROOT / "main.py"

BUILD_DIR = PROJECT_ROOT / "build"
DIST_DIR = PROJECT_ROOT / "dist"
RELEASE_DIR = PROJECT_ROOT / "release"
EXECUTABLE_NAME = "MS_Tools_C2"
PYINSTALLER_CMD = [sys.executable, "-m", "PyInstaller"]

# EXE のみを出力するため追加リソースはコピーしない
RESOURCE_DIRS: list[str] = []
RESOURCE_FILES: list[str] = []

HIDDEN_IMPORTS = [
    "logging_util",
    "adb_utils",
    "device_operations",
    "login_operations",
    "multi_device",
    "missing_functions",
    "memory_monitor",
    "loop_protection",
    "app_crash_recovery",
    "image_detection",
    "monst.device",
    "monst.device.hasya",
    "monst.image",
    "monst.image.utils",
    "monst.image.core",
    "monst.image.gacha_capture",
    "monst.device.gacha",
    "app.operations",
    "app.operations.manager",
    "app.operations.helpers",
    "utils",
    "utils.process_task_monitor",
    "tools.monitoring.task_monitor",
    "tools.monitoring.task_monitor_v2",
    "tools.monitoring.compact_task_monitor",
    "tools.monitoring.standalone_task_monitor",
    "tools.monitoring.task_monitor_standalone",
    "tools.monitoring.task_monitor_standalone_exe",
    "mon_c2",
    "mon_c2.app",
    "mon_c2.domain",
    "mon_c2.operations",
    "mon_c2.services",
    "mon_c2.config",
]

COLLECT_ALL_MODULES = [
    "utils",
    "app.operations",
    "app.operations.account_lib",
    "monst.device",
    "monst.image",
    "tools.monitoring",
    "mon_c2",
]

def _collect_utils_hidden_imports() -> list[str]:
    modules: list[str] = []
    try:
        import importlib

        utils_pkg = importlib.import_module("utils")
        export_map = getattr(utils_pkg, "_EXPORT_MAP", {})
        for module_name, _attr in export_map.values():
            modules.append(module_name)
    except Exception as exc:
        print(f"[WARN] utils hidden import discovery failed: {exc}")
    return modules


def _print_stage(message: str) -> None:
    print(f"[BUILD] {message}")


def check_environment() -> None:
    _print_stage("Checking prerequisites")
    if not ENTRYPOINT.exists():
        raise SystemExit(f"Entry point not found: {ENTRYPOINT}")
    try:
        import PyInstaller  # noqa: F401
    except ImportError as exc:
        raise SystemExit("PyInstaller is not installed. Please run 'pip install pyinstaller'.") from exc


def run_compile_checks() -> None:
    _print_stage("Running compileall sanity checks")
    targets = [
        PROJECT_ROOT / "app",
        PROJECT_ROOT / "operations",
        PROJECT_ROOT / "services",
        PROJECT_ROOT / "domain",
        PROJECT_ROOT / "config.py",
    ]
    cmd = [sys.executable, "-m", "compileall"] + [str(path) for path in targets]
    subprocess.run(cmd, check=True)


def build_executable() -> Path:
    _print_stage("Invoking PyInstaller")
    if DIST_DIR.exists():
        shutil.rmtree(DIST_DIR)
    if BUILD_DIR.exists():
        shutil.rmtree(BUILD_DIR)
    for spec in PROJECT_ROOT.glob("*.spec"):
        spec.unlink()

    cmd = (
        PYINSTALLER_CMD
        + [
            "--noconfirm",
            "--clean",
            "--onefile",
            "--name",
            EXECUTABLE_NAME,
            "--paths",
            str(PROJECT_ROOT),
            "--paths",
            str(REPO_ROOT),
        ]
    )
    utils_hidden = _collect_utils_hidden_imports()
    hidden_imports = list(dict.fromkeys(HIDDEN_IMPORTS + utils_hidden))
    for hidden in hidden_imports:
        cmd.append(f"--hidden-import={hidden}")

    for module_name in COLLECT_ALL_MODULES:
        cmd.extend(["--collect-all", module_name])

    icon_candidates = [
        PROJECT_ROOT / "gazo" / "ms_icon.ico",
        REPO_ROOT / "gazo" / "ms_icon.ico",
    ]
    for icon_path in icon_candidates:
        if icon_path.exists():
            cmd.extend(["--icon", str(icon_path)])
            break

    cmd.append(str(ENTRYPOINT))

    subprocess.run(cmd, check=True, cwd=PROJECT_ROOT)
    built_exe = DIST_DIR / f"{EXECUTABLE_NAME}.exe"
    if not built_exe.exists():
        raise SystemExit("PyInstaller did not produce the expected executable.")
    return built_exe


def copy_resources(built_exe: Path) -> Path:
    _print_stage("Preparing release directory (exe only)")
    if RELEASE_DIR.exists():
        shutil.rmtree(RELEASE_DIR)
    RELEASE_DIR.mkdir(parents=True, exist_ok=True)

    target_exe = RELEASE_DIR / built_exe.name
    shutil.copy2(built_exe, target_exe)

    return target_exe


def main() -> None:
    _print_stage("Mon_C2 EXE Build Start")
    check_environment()
    run_compile_checks()
    built_exe = build_executable()
    target_path = copy_resources(built_exe)
    _print_stage("Build complete")
    print(f"Executable ready: {target_path}")
    print("Release directory contents:")
    for path in sorted(RELEASE_DIR.iterdir()):
        print("  -", path.name)
    print("\nrelease フォルダには exe のみを配置しています。追加リソースは含まれていません。")


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as exc:
        raise SystemExit(f"Command failed with exit code {exc.returncode}") from exc
