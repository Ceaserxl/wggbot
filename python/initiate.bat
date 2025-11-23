@echo off
setlocal EnableDelayedExpansion
pushd "%~dp0"

REM --------------------------------------------
REM CONFIG
REM --------------------------------------------
set "WINPY=cpython-3.13.7windows.tar.gz"
set "PYROOT=%CD%"
set "WINX64=%PYROOT%\win-x64"
set "VENV_DIR=%~dp0..\appenv"
set "VENV_PY=%VENV_DIR%\Scripts\python.exe"

echo.
echo ===========================================
echo   Portable Python Initializer
echo ===========================================
echo.

REM --------------------------------------------
REM Ensure win-x64 folder exists
REM --------------------------------------------
if not exist "%WINX64%" (
    mkdir "%WINX64%" >nul 2>&1
)

REM --------------------------------------------
REM Locate python.exe
REM --------------------------------------------
for /r "%WINX64%" %%F in (python.exe) do (
    set "PYPATH=%%F"
    goto FOUND_PY
)

REM --------------------------------------------
REM Extract archive if python.exe not found
REM --------------------------------------------
echo [*] Extracting portable Python...
tar -xf "%WINPY%" -C "%WINX64%"

REM Try searching again
for /r "%WINX64%" %%F in (python.exe) do (
    set "PYPATH=%%F"
    goto FOUND_PY
)

echo [!] ERROR: python.exe not found after extraction.
pause
exit /b 1

:FOUND_PY
echo [OK] Python located: %PYPATH%
echo.

REM --------------------------------------------
REM Create virtual environment if needed
REM --------------------------------------------
if not exist "%VENV_PY%" (
    echo [*] Creating project virtual environment...
    "%PYPATH%" -m venv "%VENV_DIR%"
)

if not exist "%VENV_PY%" (
    echo [!] Failed to create virtual environment.
    pause
    exit /b 1
)

echo [OK] Virtual environment ready: %VENV_DIR%
echo.

exit /b 0
