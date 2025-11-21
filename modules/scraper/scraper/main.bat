@echo off
title 🔷 Scraper Menu
chcp 65001 >nul

:: ==========================================================
::  Window Setup
:: ==========================================================
mode con: cols=140 lines=45

:: ==========================================================
::  Virtual Environment Check
:: ==========================================================
if not exist "C:\venvs\tg\Scripts\activate.bat" (
    echo ❌ Virtual environment not found.
    echo Create one:
    echo     python -m venv C:\venvs\tg
    exit /b
)

call C:\venvs\tg\Scripts\activate.bat
cd /d "%~dp0"

:MENU
cls
echo.
echo  🔷==================== SCRAPER MENU ====================🔷
echo.
echo   1. Run scraper (normal)
echo   2. Run scraper with custom arguments
echo   3. Update a setting (set key value)
echo   4. Export requirements.txt
echo   5. Exit
echo.
set /p choice="👉 Select an option: "

if "%choice%"=="1" goto RUN_BASIC
if "%choice%"=="2" goto RUN_ARGS
if "%choice%"=="3" goto SETTING
if "%choice%"=="4" goto EXPORT_REQ
if "%choice%"=="5" exit /b

echo ❌ Invalid choice!
pause
goto MENU


:: ==========================================================
::  OPTION 1 — RUN SCRAPER (BASIC)
:: ==========================================================
:RUN_BASIC
cls
echo.
echo 🔷 Enter tags (space-separated):
set /p tags="Tags: "

if "%tags%"=="" (
    echo ❌ No tags provided.
    pause
    goto MENU
)

echo.
echo 🚀 Running scraper...
python main.py run %tags%

pause
goto MENU


:: ==========================================================
::  OPTION 2 — RUN SCRAPER WITH CUSTOM ARGUMENTS
:: ==========================================================
:RUN_ARGS
cls
echo.
echo 🔷 Enter full arguments for scraper:
echo Example:   ponyxoxo -i
echo Example:   -g https://thefap.net/some-gallery/
echo.
set /p custom="Args: "

if "%custom%"=="" (
    echo ❌ No arguments entered.
    pause
    goto MENU
)

echo.
echo 🚀 Running scraper...
python main.py run %custom%

pause
goto MENU


:: ==========================================================
::  OPTION 3 — UPDATE A SETTING
:: ==========================================================
:SETTING
cls
echo.
echo 🔧 Update a setting
echo Format: <key> <value>
echo Example keys:
echo   images   videos   galleries
echo   scan_tags   scan_galleries
echo   reverse   simulate   summary
echo.
set /p key="Setting key: "
set /p val="Setting value: "

if "%key%"=="" (
    echo ❌ Missing key.
    pause
    goto MENU
)
if "%val%"=="" (
    echo ❌ Missing value.
    pause
    goto MENU
)

python main.py set %key% %val%

pause
goto MENU


:: ==========================================================
::  OPTION 4 — EXPORT REQUIREMENTS.TXT
:: ==========================================================
:EXPORT_REQ
cls
echo.
echo 📦 Exporting requirements.txt...
pip freeze > requirements.txt

if exist requirements.txt (
    echo ✔ requirements.txt exported successfully!
) else (
    echo ❌ Failed to export requirements.txt
)

pause
goto MENU
