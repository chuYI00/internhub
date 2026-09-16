@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
cd /d "%~dp0"

rem ---- find git ----
set GITEXE=
where git >nul 2>nul && set GITEXE=git
if "%GITEXE%"=="" (
  for /d %%D in ("%USERPROFILE%\.workbuddy\binaries\PortableGit\versions\*") do (
    if exist "%%~D\cmd\git.exe" set GITEXE=%%~D\cmd\git.exe
  )
)
if "%GITEXE%"=="" (
  echo [X] git not found. Install Git for Windows: https://git-scm.com/download/win
  pause
  exit /b 1
)
echo git: %GITEXE%
echo.

rem ---- token: %1 > token.txt > ask ----
set TOKEN=%~1
if "%TOKEN%"=="" if exist "token.txt" (
  set /p TOKEN=<token.txt
)
if "%TOKEN%"=="" (
  echo GitHub no longer accepts your account password. Paste a Personal Access Token.
  echo   create one: https://github.com/settings/tokens  ^(classic, tick "repo"^)
  echo   tip: save it into token.txt next to this file, then just double-click this bat.
  echo.
  set /p TOKEN=Token: 
)
if "%TOKEN%"=="" (
  echo [X] no token, aborted.
  pause
  exit /b 1
)

rem ---- token sanity check: classic PAT is ghp_ + 36 chars = 40 total ----
set TLEN=0
for /l %%i in (1,1,200) do if not "!TOKEN:~%%i,1!"=="" set TLEN=%%i
echo token length: %TLEN%
if %TLEN% LSS 40 (
  echo.
  echo [X] token looks TRUNCATED: got %TLEN% chars, a classic PAT has 40 ^(ghp_ + 36^).
  echo     Re-copy it from https://github.com/settings/tokens - make sure the whole string
  echo     is selected ^(it is easy to miss the tail^).
  echo.
  pause
  exit /b 1
)

set REMOTEURL=https://github.com/chuYI00/internhub.git

echo === refresh remote info ===
"%GITEXE%" fetch %REMOTEURL% main 2>nul
"%GITEXE%" rev-parse --verify FETCH_HEAD >nul 2>nul
if not errorlevel 1 (
  "%GITEXE%" update-ref refs/remotes/origin/main FETCH_HEAD 2>nul
  for /f %%N in ('"%GITEXE%" rev-list --count FETCH_HEAD..HEAD') do echo unpushed commits: %%N
)
echo.

echo === pushing to github.com/chuYI00/internhub (main) ===
"%GITEXE%" push "%REMOTEURL%" HEAD:main
if errorlevel 1 (
  echo.
  echo [X] push failed. common causes:
  echo     1. token expired / revoked / wrong scope - regenerate with "repo" scope
  echo     2. token truncated - it must be 40 chars ^(ghp_ + 36^)
  echo     3. no network / proxy blocking github.com
  echo.
  echo   offline fallback: backup\patches\ ^(all commits as .patch^)
  echo                     backup\internhub_未推送.bundle
  pause
  exit /b 1
)
echo.
echo [OK] pushed.
"%GITEXE%" log --oneline -3
pause
