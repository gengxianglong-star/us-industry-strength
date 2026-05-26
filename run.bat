@echo off
setlocal

cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  py -3 -m venv .venv
)

call ".venv\Scripts\activate.bat"
python -m pip install --upgrade pip
pip install -r requirements.txt

if /I "%1"=="daily" (
  python scripts\precompute_daily.py
  if errorlevel 1 exit /b %errorlevel%
  exit /b 0
)

if /I "%1"=="breadth" (
  python scripts\sync_breadth.py
  exit /b %errorlevel%
)

python -m uvicorn src.server:app --host 127.0.0.1 --port 8080
