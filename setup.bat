@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo.
echo === SHADOW Windows setup ===
echo.

where python >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Python nav PATH. Uzliec Python 3.12 vai 3.13 no python.org
  echo         un atzime "Add python.exe to PATH".
  pause
  exit /b 1
)

python -c "import sys; raise SystemExit(0 if sys.version_info[:2] >= (3, 11) else 1)"
if errorlevel 1 (
  echo [ERROR] Nepieciesams Python 3.11+. Ieteicams 3.12 vai 3.13 ^(ne 3.14^).
  python --version
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo Veidoju virtualenv .venv ...
  python -m venv .venv
  if errorlevel 1 (
    echo [ERROR] venv neizdevas. Palaid CMD ka Administrator vai parbaudi Python instalaciju.
    pause
    exit /b 1
  )
)

echo Atjauninu pip ...
".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 (
  echo [ERROR] pip upgrade neizdevas.
  pause
  exit /b 1
)

echo Installuju atkaribas ^(bez pip cache, lai izvairitos no Permission denied^) ...
".venv\Scripts\python.exe" -m pip install --no-cache-dir -r requirements.txt
if errorlevel 1 (
  echo.
  echo [ERROR] Instalacija neizdevas.
  echo Megini: Python 3.12/3.13 + palaid so failu velreiz.
  pause
  exit /b 1
)

if not exist ".env" (
  if exist ".env.example" (
    copy /Y ".env.example" ".env" >nul
    echo Izveidots .env no .env.example — aizpildi API datus vai atstaj tuksu paper rezimam.
  )
)

echo.
echo === Gatavs ===
echo Palaid:  run.bat
echo Vai:     .venv\Scripts\python.exe start.py
echo Dashboard: http://127.0.0.1:8080
echo.
pause
endlocal