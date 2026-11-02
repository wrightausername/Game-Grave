@echo off
cd /d "%~dp0"
py -3 -m pip install --upgrade pyinstaller "psutil>=6.1,<8"
if errorlevel 1 goto fail
py -3 -m PyInstaller --clean --onefile --windowed --hidden-import activity_history --hidden-import shader_cache --hidden-import save_discovery --hidden-import scan_progress --hidden-import graveyard --hidden-import mod_sources --hidden-import ecosystems --hidden-import launchers --hidden-import recovery --hidden-import file_detective --hidden-import space_planner --hidden-import insights --hidden-import save_vault --name GameGrave launcher.py
if errorlevel 1 goto fail
echo.
echo Standalone Windows app: dist\GameGrave.exe
echo To produce an INSTALLER, use build_installer.ps1 on Windows with Inno Setup 6 installed.
echo This unsigned preview build is for local testing, not retail distribution.
pause
exit /b 0
:fail
echo Build failed. Confirm Python 3.10+ is installed.
pause
exit /b 1
