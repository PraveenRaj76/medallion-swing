@echo off
REM Double-click this file to start Medallion Swing locally.
REM First run installs dependencies automatically (can take a few minutes);
REM after that it starts in seconds. Opens the backend and frontend each in
REM their own window, then opens the app in your browser once both are
REM actually ready. Close both windows (or just close this one) to stop.

cd /d "%~dp0"

echo Starting backend (window: "Medallion Swing - Backend")...
start "Medallion Swing - Backend" cmd /k "backend\run-backend.bat"

echo Waiting for the backend to come up (first run can take a few minutes)...
powershell -NoProfile -Command "$deadline = (Get-Date).AddMinutes(5); while ((Get-Date) -lt $deadline) { try { Invoke-RestMethod -Uri 'http://localhost:8000/health' -TimeoutSec 2 | Out-Null; exit 0 } catch { Start-Sleep -Seconds 2 } }; exit 1"
if errorlevel 1 (
    echo.
    echo Backend did not come up within 5 minutes - check the "Medallion Swing - Backend" window for errors.
    echo.
) else (
    echo Backend is up.
)

echo Starting frontend (window: "Medallion Swing - Frontend")...
start "Medallion Swing - Frontend" cmd /k "frontend\run-frontend.bat"

echo Waiting for the frontend to come up (first run can take a minute or two)...
powershell -NoProfile -Command "$deadline = (Get-Date).AddMinutes(3); while ((Get-Date) -lt $deadline) { try { Invoke-WebRequest -Uri 'http://localhost:5173' -TimeoutSec 2 -UseBasicParsing | Out-Null; exit 0 } catch { Start-Sleep -Seconds 2 } }; exit 1"
if errorlevel 1 (
    echo.
    echo Frontend did not come up within 3 minutes - check the "Medallion Swing - Frontend" window for errors.
    echo.
) else (
    echo Frontend is up. Opening in your browser...
    start http://localhost:5173
)

echo.
echo Medallion Swing:
echo   Backend:  http://localhost:8000/health
echo   Frontend: http://localhost:5173
echo.
echo Close this window any time - it's just the launcher. The two app windows will keep running.
pause
