@echo off
chcp 65001 >nul
cd /d "%~dp0"

rem ==== find git ====
set GITEXE=
where git >nul 2>nul && set GITEXE=git
if "%GITEXE%"=="" (
  for /d %%D in ("%USERPROFILE%\.workbuddy\binaries\PortableGit\versions\*") do (
    if exist "%%~D\cmd\git.exe" set GITEXE=%%~D\cmd\git.exe
  )
)
if "%GITEXE%"=="" (
  echo [X] git not found. Install Git for Windows first: https://git-scm.com/download/win
  pause
  exit /b 1
)
echo Using: %GITEXE%
echo.

echo === unpushed commits ===
"%GITEXE%" log --oneline origin/main..HEAD
echo.
echo === pushing to github.com/chuYI00/internhub (main) ===
"%GITEXE%" push origin main
if errorlevel 1 (
  echo.
  echo [X] push failed.
  echo     - if it asks for a password: GitHub no longer accepts account passwords.
  echo       Use a Personal Access Token as the password (repo scope), or sign in via Git Credential Manager.
  echo     - create token: https://github.com/settings/tokens
  echo.
  echo   offline fallback: patches are in backup\patches\ , bundle in backup\*.bundle
  pause
  exit /b 1
)
echo.
echo [OK] pushed.
"%GITEXE%" log --oneline -3
pause
