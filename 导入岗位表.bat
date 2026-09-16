@echo off
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"

echo ============================================================
echo  Import job table
echo  Usage: drag a .csv file onto this window, then press Enter
echo ============================================================
echo.
if "%~1"=="" (
  set /p FILE=Drag the CSV file here, then press Enter:
) else (
  set FILE=%~1
)
set FILE=%FILE:"=%
echo.
venv\Scripts\python.exe run_import.py "%FILE%" --source "我找的岗位表"
echo.
echo Tip: custom source name:
echo   venv\Scripts\python.exe run_import.py "file.csv" --source feishu-1
pause
