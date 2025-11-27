@echo off
setlocal

:: Activate venv (relative)
call python\win-x64\wvenv\Scripts\activate.bat

:: Run scraper (relative)
python app\modules\scraper\scraper_base.py %*
