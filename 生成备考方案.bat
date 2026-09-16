@echo off
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"
echo ============================================
echo  生成备考方案（选目标单位 - 自动出方案）
echo  不填参数 = 云南中烟 冲刺模板
echo ============================================
echo.
venv\Scripts\python.exe run_studyplan.py --target 云南中烟 --date 2026-12-06 --hours 6
echo.
echo  想换成别的单位？命令行里这样写：
echo     venv\Scripts\python.exe run_studyplan.py --list
echo     venv\Scripts\python.exe run_studyplan.py --target 云南省烟草专卖局 --role 信息技术 --hours 4
echo.
echo  产物目录：%~dp0备考冲刺资料
pause
