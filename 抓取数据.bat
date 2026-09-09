@echo off
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"
echo [InternHub] crawling jobs into SQLite ...
venv\Scripts\python.exe run_crawl.py
echo.
echo Done. Now start the web UI bat file to view.
pause
