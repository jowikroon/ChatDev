@echo off
title ChatDev skill install
cd /d "%~dp0"
where py >nul 2>nul && (py -3 install.py) || (python install.py)
echo.
pause
