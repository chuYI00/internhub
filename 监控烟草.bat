@echo off
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"
echo ============================================================
echo  Tobacco recruitment monitor
echo  Only NEW announcements are reported. Windows are 7-10 days.
echo ============================================================
echo.
venv\Scripts\python.exe run_tobacco_watch.py --pages 3 --detail 8
echo.
echo Tip: see all announcements too:
echo     venv\Scripts\python.exe run_tobacco_watch.py --all
pause
