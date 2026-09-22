@echo off
cd /d "%~dp0"

if not exist node_modules (
    echo First run detected - installing frontend dependencies...
    echo This only happens once and may take a minute or two.
    echo.
    call npm install
    if errorlevel 1 (
        echo.
        echo ERROR: npm install failed - see the error above.
        echo Make sure Node.js 18 or newer is installed:
        echo   https://nodejs.org/
        echo.
        pause
        exit /b 1
    )
    echo Frontend setup complete.
    echo.
)

call npm run dev
