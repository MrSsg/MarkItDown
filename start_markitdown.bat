@echo off
cd /d "%~dp0markitdown-desktop"
python main.py
if errorlevel 1 (
    echo.
    echo App exited with error. Press any key to close.
    pause >nul
)
