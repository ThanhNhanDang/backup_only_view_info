@echo off
set SCRIPT_DIR=%~dp0

echo Checking for existing flask_server.py process...

REM Tìm và kill process
tasklist | findstr /R "python.*flask_server.py" > nul
if %ERRORLEVEL% equ 0 (
    echo Flask server is running, killing process...
    taskkill /IM python.exe /F
) else (
    echo No existing Flask server process found.
)

set VENV_PATH=%SCRIPT_DIR%venv
set PYTHON=%VENV_PATH%\Scripts\python.exe

if exist "%PYTHON%" (
    echo Using virtual environment Python: %PYTHON%
) else (
    echo Virtual environment not found at %VENV_PATH%
    exit /b 1
)

echo Starting Flask server...
cd /d "%SCRIPT_DIR%"
start "" "%PYTHON%" -u "%SCRIPT_DIR%flask_server.py" > "%SCRIPT_DIR%flask.log" 2>&1

echo Flask server restarted at port 8080 and running in background.