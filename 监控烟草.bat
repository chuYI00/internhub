@echo off
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"
echo ============================================================
echo  烟草招聘监控  --  国家烟草专卖局 人才招聘专栏
echo  只报告「新增」公告；报名窗口只有 7-10 天，别错过
echo ============================================================
echo.
venv\Scripts\python.exe run_tobacco_watch.py --pages 3 --detail 8
echo.
echo 提示：想连全部公告一起看，跑：
echo     venv\Scripts\python.exe run_tobacco_watch.py --all
pause
