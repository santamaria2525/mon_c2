@echo off
setlocal
cd /d "%~dp0"

set "PYTHON=python"
where py >nul 2>nul && set "PYTHON=py -3"

%PYTHON% build_exe.py
echo.
echo Build finished. Press any key to close...
pause >nul
