@echo off
rem Double-click to run FinPulse on Windows. Needs Node.js 22 (https://nodejs.org).
cd /d "%~dp0"
where npm >nul 2>nul
if errorlevel 1 (
  echo.
  echo Node.js is not installed. Install the LTS version from https://nodejs.org, then double-click this file again.
  echo.
  pause
  exit /b 1
)
call npm start
pause
