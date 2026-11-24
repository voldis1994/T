@echo off
setlocal EnableExtensions
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo Vispirms palaid setup.bat
  pause
  exit /b 1
)

echo Startēju SHADOW...
echo Dashboard: http://127.0.0.1:8080
echo.
".venv\Scripts\python.exe" start.py
set EXITCODE=%ERRORLEVEL%
if not "%EXITCODE%"=="0" (
  echo.
  echo [ERROR] Robots apturejas ar kodu %EXITCODE%
  pause
)
endlocal & exit /b %EXITCODE%