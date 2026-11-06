@echo off
if not exist "%~dp0GameGrave-Crimson-Preview.exe" (
    echo Extract the entire Windows build ZIP before opening this launcher.
    pause
    exit /b 1
)
start "" "%~dp0GameGrave-Crimson-Preview.exe" --ready-room-reference
