@echo off
REM dbot.bat — Windows manager for your Discord bot (wvenv + menu)
REM Portable Python is extracted only during Install (option 8).
setlocal EnableExtensions EnableDelayedExpansion

REM --- Move to script directory ---
pushd "%~dp0"

REM --- Config (auto) ---
for %%I in ("%cd%.") do set "SESSION=%%~nI"
set "LOG=%SESSION%.log"
set "MAIN=main.py"
set "WVENV_DIR=wvenv"
set "WVENV_PY=%WVENV_DIR%\Scripts\python.exe"
set "ACTIVATOR=%WVENV_DIR%\Scripts\activate.bat"
set "REPO_URL=https://github.com/Ceaserxl/wggbot.git"

REM Choose a Python for running (prefer venv if present; no extraction here)
if exist "%WVENV_PY%" (
  set "PYEXE=%WVENV_PY%"
) else (
  where py >nul 2>&1 && (set "PYEXE=py -3") || (set "PYEXE=python")
)

:menu
cls
echo ===========================================
echo   DBOT for "%SESSION%"  (Windows)
echo ===========================================
echo [1] Start
echo [2] Start ^(headless^)  - background, logs to "%LOG%"
echo [3] Stop ^(headless session only^)
echo [4] Restart  ^(headless session only^)
echo [5] Log ^(tail^)  - opens separate window; close it to exit
echo [6] Shell ^(activate wvenv^)
echo [7] Export requirements.txt
echo [8] Install / Reinstall wvenv + deps  ^(extract on demand^)
echo [9] Wipe  ^(delete wvenv + resources\python313\win-x64^)
echo [0] Check for updates ^(then Install^)
echo [Q] Quit
echo.
set "choice="
set /p "choice=Select an option: "

if /i "%choice%"=="1" goto start_foreground
if /i "%choice%"=="2" goto start_headless
if /i "%choice%"=="3" goto stop
if /i "%choice%"=="4" goto restart
if /i "%choice%"=="5" goto log
if /i "%choice%"=="6" goto shell
if /i "%choice%"=="7" goto export
if /i "%choice%"=="8" goto install
if /i "%choice%"=="9" goto wipe_only
if /i "%choice%"=="0" goto update_check
if /i "%choice%"=="q" goto :eof
goto menu

REM ---------- helpers ----------
:brief_pause
timeout /t 2 /nobreak >nul
exit /b 0

:start_precheck_fn
if not exist "%ACTIVATOR%" (
  echo Missing: %ACTIVATOR%
  echo Run Install ^(option 8^) first.
  call :brief_pause
  exit /b 1
)
if not exist "%WVENV_PY%" (
  echo Missing: %WVENV_PY%
  echo Run Install ^(option 8^) first.
  call :brief_pause
  exit /b 1
)
if exist ".dbot.pid" (
  for /f %%p in (.dbot.pid) do (
    tasklist /FI "PID eq %%p" | find "%%p" >nul && (
      echo Already running headless ^(PID %%p^). Stop it first ^(option 3^).
      call :brief_pause
      exit /b 1
    )
  )
)
exit /b 0

REM ---------- actions ----------
:start_foreground
call :start_precheck_fn
if errorlevel 1 goto menu
echo Launching in a new window...
start "dbot - %SESSION%" cmd /k call "%ACTIVATOR%" ^&^& python "%MAIN%"
timeout /t 1 >nul
goto menu

:start_headless
call :start_headless_fn
goto menu

:start_headless_fn
call :start_precheck_fn
if errorlevel 1 exit /b 1

echo Starting %MAIN% headless...
set "RUNLINE=""%MAIN%"" >> ""%LOG%"" 2^>^&1"
for /f "usebackq delims=" %%P in (`
  powershell -NoProfile -Command ^
    "$p = Start-Process -FilePath 'cmd.exe' -ArgumentList @('/c','""%WVENV_PY%"" %RUNLINE%') -WindowStyle Hidden -PassThru; $p.Id"
`) do (
  >.dbot.pid echo %%P
  echo Started ^(PID %%P^) - logging to "%LOG%"
)
timeout /t 1 >nul
exit /b 0

:stop
call :stop_fn
goto menu

:stop_fn
if not exist ".dbot.pid" (
  echo No headless PID file; nothing to stop. If you used Start, close that window.
  call :brief_pause
  exit /b 1
)
for /f %%p in (.dbot.pid) do (
  echo Stopping PID %%p ...
  taskkill /PID %%p /T /F >nul 2>&1
)
del /f /q .dbot.pid >nul 2>&1
echo Stopped.
timeout /t 1 >nul
exit /b 0

:restart
call :stop_fn
call :start_headless_fn
goto menu

:log
if not exist "%LOG%" (
  echo No log yet: %LOG%
  call :brief_pause
  goto menu
)
start "dbot log - %SESSION%" powershell -NoProfile -NoLogo -Command ^
  "Write-Host 'Tailing %LOG% (close this window to exit)...'; Get-Content -Path '%LOG%' -Wait -Tail 50"
goto menu

:shell
if exist "%ACTIVATOR%" (
  start "wvenv - %SESSION%" cmd /k call "%ACTIVATOR%" ^&^& cd /d "%cd%"
) else (
  echo %ACTIVATOR% not found. Run Install ^(option 8^) to create wvenv.
  call :brief_pause
)
goto menu

:export
if not exist "%WVENV_PY%" (
  echo %WVENV_PY% not found. Run Install ^(option 8^) first.
  call :brief_pause
  goto menu
)
echo Exporting requirements to requirements.txt ...
"%WVENV_PY%" -m pip freeze > requirements.txt
if errorlevel 1 (
  echo Export failed.
) else (
  echo Saved: requirements.txt
)
call :brief_pause
goto menu

:install
set "recreate="
if exist "%WVENV_DIR%" (
  set /p "recreate=wvenv exists. Reinstall (delete and recreate venv + portable Python)? [y/N]: "
  if /i "!recreate!"=="y" (
    echo Removing %WVENV_DIR% ...
    rmdir /s /q "%WVENV_DIR%"
    echo Removing portable Python folder win-x64 ...
    rmdir /s /q "resources\python313\win-x64" 2>nul
  ) else (
    echo Keeping existing wvenv; skipping venv creation and deps.
    goto install_done
  )
)

set "EMBED_BASE=resources\python313"
set "EMBED_DIR=%EMBED_BASE%\win-x64"
set "EMBED_PY="
set "ARCHIVE=%EMBED_BASE%\cpython-3.13.7windows.tar.gz"

if not exist "%EMBED_DIR%" mkdir "%EMBED_DIR%"

if not exist "%ARCHIVE%" (
  echo Missing archive: %ARCHIVE%
  echo Place your Windows build as exactly this filename, then run Install again.
  call :brief_pause
  goto install_done
)

echo Extracting cpython-3.13.7windows.tar.gz to %EMBED_DIR% ...
tar -xf "%ARCHIVE%" -C "%EMBED_DIR%"

if exist "%EMBED_DIR%\python\python.exe" (
  set "EMBED_PY=%EMBED_DIR%\python\python.exe"
) else if exist "%EMBED_DIR%\python.exe" (
  set "EMBED_PY=%EMBED_DIR%\python.exe"
) else (
  for /d %%D in ("%EMBED_DIR%\*") do (
    if exist "%%~fD\python\python.exe" set "EMBED_PY=%%~fD\python\python.exe"
    if exist "%%~fD\python.exe" set "EMBED_PY=%%~fD\python.exe"
  )
)

if not defined EMBED_PY (
  echo Extraction finished but python.exe was not found in %EMBED_DIR%.
  echo Check the archive contents or adjust the detection paths.
  call :brief_pause
  goto install_done
)

echo Embedded Python ready: %EMBED_PY%

:after_extract
if defined EMBED_PY (
  set "CREATOR=%EMBED_PY%"
) else (
  where py >nul 2>&1 && (set "CREATOR=py -3") || (set "CREATOR=python")
)

echo Creating virtual environment: %WVENV_DIR% ...
%CREATOR% -m ensurepip -U
%CREATOR% -m pip install -U pip --no-warn-script-location
%CREATOR% -m venv "%WVENV_DIR%"
if errorlevel 1 (
  echo Failed to create venv.
  call :brief_pause
  goto menu
)

echo Upgrading pip in wvenv ...
"%WVENV_PY%" -m pip install --upgrade pip --no-warn-script-location

if exist "requirements.txt" (
  echo Installing requirements.txt ...
  "%WVENV_PY%" -m pip install -r requirements.txt --no-warn-script-location
) else (
  echo No requirements.txt found; skipping dependency install.
)

:install_done
echo Install complete.
call :brief_pause
goto menu

:wipe_only
echo This will delete the venv and portable Python. No reinstall will be performed.
set /p "ans=Proceed? [y/N]: "
if /i not "%ans%"=="y" goto menu

if exist ".dbot.pid" call :stop_fn

echo Deleting wvenv ...
rmdir /s /q "wvenv" 2>nul

echo Deleting portable Python (resources\python313\win-x64) ...
rmdir /s /q "resources\python313\win-x64" 2>nul

echo Wipe complete.
call :brief_pause
goto menu

:update_check
set "GIT_TERMINAL_PROMPT=0"
where git >nul 2>nul || (
  echo git is not installed. Get Git for Windows: https://git-scm.com/download/win
  call :brief_pause
  goto menu
)

echo Checking remote HEAD for %REPO_URL% ...
set "REMOTE_HASH="
for /f "usebackq tokens=1" %%H in (`git ls-remote -h "%REPO_URL%" HEAD 2^>nul`) do set "REMOTE_HASH=%%H"

if not defined REMOTE_HASH (
  for /f "usebackq delims=" %%J in (`
    powershell -NoProfile -Command "(Invoke-RestMethod -UseBasicParsing https://api.github.com/repos/Ceaserxl/wggbot/commits/HEAD).sha"
  `) do set "REMOTE_HASH=%%J"
)

if not defined REMOTE_HASH (
  echo Failed to query remote hash. Check network/auth.
  call :brief_pause
  goto menu
)

set "LOCAL_HASH=(none)"
if exist ".git" (
  for /f "usebackq delims=" %%L in (`git rev-parse HEAD 2^>nul`) do set "LOCAL_HASH=%%L"
)

echo Local : %LOCAL_HASH%
echo Remote: %REMOTE_HASH%

if /i "%LOCAL_HASH%"=="%REMOTE_HASH%" (
  echo Already up-to-date.
  call :brief_pause
  goto menu
)

echo.
set "ans="
set /p "ans=Stop bot, update to newest, then run Install? [y/N]: "
if /i not "%ans%"=="y" goto menu

if exist ".dbot.pid" call :stop_fn

if exist ".git" (
  echo Resetting to remote and cleaning untracked ^(ignored files preserved by .gitignore^)...
  git fetch --all --prune
  git reset --hard %REMOTE_HASH%
  git clean -df
) else (
  echo Bootstrapping git in current folder...
  git init
  git remote add origin "%REPO_URL%" 2>nul
  git fetch --depth=1 origin
  git reset --hard %REMOTE_HASH%
  git clean -df
)

echo Code updated. Running Install...
call :install

echo Update + Install complete.
call :brief_pause
goto menu

