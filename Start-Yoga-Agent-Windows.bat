@echo off
title Daily Yoga AI Agent
cd /d "%~dp0"

where python >nul 2>nul
if %errorlevel%==0 (
    python app.py
    goto :end
)

where py >nul 2>nul
if %errorlevel%==0 (
    py -3 app.py
    goto :end
)

echo ============================================================
echo  Python 3 is needed to run Daily Yoga AI Agent.
echo  Opening the official Python download page for you...
echo  Tip: During installation, check "Add Python to PATH".
echo ============================================================
start https://www.python.org/downloads/
pause

:end