@echo off
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"

set TMPF=%TEMP%\_ihub_clip.tsv

echo ============================================================
echo  Import job table from CLIPBOARD
echo.
echo  1. Select the table area in Feishu Base / Excel / WPS
echo     (including the header row; data rows only also work)
echo  2. Press Ctrl+C
echo  3. Double-click this file
echo  No export permission needed.
echo ============================================================
echo.

if exist "%TMPF%" del "%TMPF%" >nul 2>nul
powershell -NoProfile -Command "Get-Clipboard -Raw | Set-Content -Encoding UTF8 -NoNewline -LiteralPath '%TMPF%'"

if not exist "%TMPF%" (
  echo [FAILED] Clipboard is empty. Press Ctrl+C in the table first.
  goto :end
)

venv\Scripts\python.exe run_import.py "%TMPF%" --source "飞书粘贴"
set RC=%ERRORLEVEL%
del "%TMPF%" >nul 2>nul

echo.
if %RC%==0 (
  echo [DONE] Now open the web UI, see the job list.
) else (
  echo [ERROR] Import failed, see the message above.
)

:end
echo.
pause
