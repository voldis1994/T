@echo off
setlocal EnableExtensions
cd /d "%~dp0"

REM === SHADOW one-click start (Windows) ===
set PORT=8080
if exist ".env" (
  for /f "usebackq tokens=1,* delims==" %%A in (".env") do (
    if /I "%%A"=="SHADOW_PORT" set PORT=%%B
  )
)

if exist ".venv\Scripts\python.exe" (
  set "PY=.venv\Scripts\python.exe"
) else (
  set "PY=python"
)

echo.
echo ========================================
echo   SHADOW start
echo   Dashboard: http://127.0.0.1:%PORT%
echo ========================================
echo.
echo NEKOPE mekletaja — adrese atversies pati.
echo Ja ne, Edge/Chrome adreses josla ieraksti EXACTI:
echo   http://127.0.0.1:%PORT%
echo   (http — ne htpp)
echo.
echo CMD logu NEAIZVER — robots strada te.
echo Apturet: Ctrl+C
echo.

REM Atver parlukprogramma pec 2 sekundem (pareiza URL, bez mekletaja)
start "SHADOW-browser" /MIN cmd /c "timeout /t 2 /nobreak >nul & start \"\" http://127.0.0.1:%PORT%/"

"%PY%" start.py
set EXITCODE=%ERRORLEVEL%

if not "%EXITCODE%"=="0" (
  echo.
  echo [ERROR] Robots apturejas ar kodu %EXITCODE%
  echo Ja teica "Address already in use" — aizver ieprieksejo CMD (Ctrl+C) un megini velreiz.
  pause
)
endlocal & exit /b %EXITCODE%