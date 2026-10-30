@echo off
cd /d "%~dp0"
where py >nul 2>nul
if %ERRORLEVEL%==0 (
    py -3 launcher.py
) else (
    where python >nul 2>nul
    if %ERRORLEVEL%==0 (
        python launcher.py
    ) else (
        echo Game Grave needs Python 3.10 or newer installed from python.org.
        echo Check "Add Python to PATH" during installation.
        pause
    )
)
