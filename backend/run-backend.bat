@echo off
cd /d "%~dp0"

if not exist venv (
    echo First run detected - setting up the Python environment...
    echo This only happens once and may take a few minutes.
    echo.
    python -m venv venv
    if errorlevel 1 (
        echo.
        echo ERROR: Could not create a Python virtual environment.
        echo Make sure Python 3.11 or newer is installed and on your PATH:
        echo   https://www.python.org/downloads/
        echo.
        pause
        exit /b 1
    )
    echo Installing backend dependencies...
    venv\Scripts\pip.exe install -r requirements.txt
    if errorlevel 1 (
        echo.
        echo ERROR: Failed to install backend dependencies - see the error above.
        echo.
        pause
        exit /b 1
    )
    echo Backend setup complete.
    echo.
)

venv\Scripts\python.exe main.py
