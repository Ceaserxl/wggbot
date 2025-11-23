@echo off
setlocal EnableDelayedExpansion
pushd "%~dp0"

echo ===========================================
echo   WGGBot Bootstrapper
echo ===========================================
echo.

REM 1. Initialize portable python + venv
call python\initiate.bat
if errorlevel 1 (
    echo [!] Python initialization failed.
    pause
    exit /b 1
)

set "VENV_PY=appenv\Scripts\python.exe"

REM 2. Install global requirements
if exist "requirements.txt" (
    echo [*] Installing global requirements...
    "%VENV_PY%" -m pip install -r requirements.txt --no-warn-script-location
    echo [OK] Global requirements installed.
)

REM 3. Install each module's requirements.txt
echo [*] Installing module dependencies...
for /d %%D in ("app\modules\*") do (
    if exist "%%D\requirements.txt" (
        echo     - %%~nxD
        "%VENV_PY%" -m pip install -r "%%D\requirements.txt" --no-warn-script-location
    )
)
echo [OK] Modules processed.
echo.

REM 4. Start controller
echo [*] Launching controller...
"%VENV_PY%" app\controller.py
echo.
pause
exit /b 0
