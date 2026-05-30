@echo off
setlocal

chcp 65001 >nul
cd /d "%~dp0"

where py >nul 2>nul
if errorlevel 1 (
  echo [ERROR] 未检测到 py 启动器。请安装 Python 3.11+ 并勾选 Add to PATH。
  echo 下载: https://www.python.org/downloads/windows/
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  py -3 -m venv .venv
  if errorlevel 1 (
    echo [ERROR] 创建虚拟环境失败。
    exit /b 1
  )
)

call ".venv\Scripts\activate.bat"
python -m pip install --upgrade pip
if errorlevel 1 (
  echo [ERROR] pip 升级失败。若在受限网络，请先设置 HTTPS_PROXY。
  echo 例如: set HTTPS_PROXY=http://127.0.0.1:7890
  exit /b 1
)

pip install -r requirements.txt
if errorlevel 1 (
  echo [ERROR] 依赖安装失败。请检查网络/代理设置。
  echo 提示: set HTTPS_PROXY=http://127.0.0.1:7890
  exit /b 1
)

if /I "%1"=="daily" (
  python scripts\precompute_daily.py
  if errorlevel 1 exit /b %errorlevel%
  exit /b 0
)

if /I "%1"=="breadth" (
  python scripts\sync_breadth.py
  exit /b %errorlevel%
)

for /f "tokens=5" %%a in ('netstat -ano ^| findstr /R /C:":8080 .*LISTENING"') do (
  echo [WARN] 端口 8080 已被进程 %%a 占用。若页面打不开，可先结束该进程：
  echo        taskkill /PID %%a /F
  goto :start_server
)

:start_server
if exist "frontend\package.json" (
  where npm >nul 2>nul
  if not errorlevel 1 (
    echo Building frontend...
    pushd frontend
    call npm install --no-audit --no-fund
    if errorlevel 1 (
      echo [WARN] npm install failed — serving legacy web/ if no web\dist
    ) else (
      call npm run build
      if errorlevel 1 echo [WARN] frontend build failed
    )
    popd
  ) else (
    echo [WARN] npm not found — skip frontend build
  )
)

python -m uvicorn src.server:app --host 127.0.0.1 --port 8080
