@echo off
title Daily Yoga AI Agent
cd /d "%~dp0"

if not exist "app.py" (
    echo ============================================================
    echo  ERROR: app.py was not found in this folder!
    echo  Please right-click the downloaded ZIP file and select
    echo  "Extract All..." before double-clicking this launcher.
    echo ============================================================
    pause
    goto :end
)

python --version >nul 2>nul
if %errorlevel%==0 (
    python app.py
    if not %errorlevel%==0 pause
    goto :end
)

py -3 --version >nul 2>nul
if %errorlevel%==0 (
    py -3 app.py
    if not %errorlevel%==0 pause
    goto :end
)

echo ============================================================
echo  Python 3 is needed to run Daily Yoga AI Agent.
echo  Opening the official Python download page for you...
echo  IMPORTANT: Check "Add python.exe to PATH" during setup!
echo ============================================================
start https://www.python.org/downloads/
pause

:end
