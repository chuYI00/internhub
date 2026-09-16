@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ============================================
echo  重新生成简历材料（万能版 + 8 个方向）
echo ============================================
venv\Scripts\python.exe gen_resume_kit.py
echo.
echo  顺手把网申助手脚本也刷新一次...
venv\Scripts\python.exe -m ihub.autofill
echo.
echo  材料目录：%~dp0简历材料
pause
