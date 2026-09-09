@echo off
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"
echo [InternHub] starting web UI at http://localhost:8501 ...
venv\Scripts\python.exe -m streamlit run app.py
pause
