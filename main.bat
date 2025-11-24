@echo off
setlocal EnableDelayedExpansion
pushd "%~dp0"

echo ===========================================
echo   WGGBot Bootstrapper
echo ===========================================

:: ------------------------------------------
:: CONFIG
:: ------------------------------------------
set "PYBASE=python"
set "PYREPO=https://github.com/Ceaserxl/ppython.git"
set "PYHASHFILE=%PYBASE%\version.txt"
set "PYMAIN=%PYBASE%\win-x64\python\python.exe"
set "VENV_PY=%PYBASE%\win-x64\wvenv\Scripts\python.exe"

:: ------------------------------------------
:: 0. ENSURE PORTABLE PYTHON EXISTS
:: ------------------------------------------
if not exist "%PYMAIN%" (
    echo [*] Portable Python missing — downloading...
    if exist "%PYBASE%" rmdir /s /q "%PYBASE%"
    git clone --depth 1 "%PYREPO%" "%PYBASE%"
    if errorlevel 1 (
        echo [!] ERROR: Failed to clone %PYREPO%
        pause
        exit /b 1
    )
    for /f "delims=" %%H in ('git -C "%PYBASE%" rev-parse HEAD') do echo %%H> "%PYHASHFILE%"
    echo [OK] Portable Python downloaded.
) else (
    :: ------------------------------------------
    :: CHECK FOR UPDATES
    :: ------------------------------------------
    if exist "%PYHASHFILE%" (
        for /f "delims=" %%L in (%PYHASHFILE%) do set "LOCAL_HASH=%%L"
        for /f "tokens=1" %%R in ('git ls-remote "%PYREPO%" HEAD') do set "REMOTE_HASH=%%R"

        if /I "!LOCAL_HASH!" neq "!REMOTE_HASH!" (
            echo [*] Update detected — refreshing portable python...
            rmdir /s /q "%PYBASE%"
            git clone --depth 1 "%PYREPO%" "%PYBASE%"
            for /f "delims=" %%H in ('git -C "%PYBASE%" rev-parse HEAD') do echo %%H> "%PYHASHFILE%"
            echo [OK] Updated portable Python.
        ) else (
            echo [OK] Portable Python up-to-date.
        )
    )
)

:: ------------------------------------------
:: 1. RUN python\initiate.bat
:: ------------------------------------------
echo [*] Initializing portable Python...
call python\initiate.bat
if errorlevel 1 (
    echo [!] Python initialization failed.
    pause
    exit /b 1
)

:: ------------------------------------------
:: 2. RUN CONTROLLER USING WVENV PYTHON
:: ------------------------------------------
if not exist "%VENV_PY%" (
    echo [!] ERROR: venv python missing:
    echo     %VENV_PY%
    pause
    exit /b 1
)

echo [*] Starting WGGBot controller...
"%VENV_PY%" app\controller.py
exit /b 0
