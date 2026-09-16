@echo off
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"
echo ============================================================
echo  导入岗位表  --  飞书多维表格 / Excel / 其他来源导出的 CSV
echo  用法：把 CSV 文件拖到本窗口上，然后回车
echo ============================================================
echo.
if "%~1"=="" (
  set /p FILE=请把 CSV 文件拖进来（或直接粘贴完整路径）然后回车：
) else (
  set FILE=%~1
)
set FILE=%FILE:"=%
echo.
venv\Scripts\python.exe run_import.py "%FILE%" --source "我找的岗位表"
echo.
echo 提示：想标成别的来源名，用命令行：
echo     venv\Scripts\python.exe run_import.py "文件.csv" --source 飞书表1
pause
