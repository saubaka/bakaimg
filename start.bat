@echo off
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0"

set "CLOUDNEST_PYTHON=.venv\Scripts\python.exe"
set "CLOUDNEST_PIP=.venv\Scripts\pip.exe"

if not exist "%CLOUDNEST_PYTHON%" (
  where py >nul 2>nul
  if errorlevel 1 (
    echo [bakaimg] 未找到Python启动器。请先安装Python 3.12至3.14。
    exit /b 1
  )
  echo [bakaimg] 正在创建独立虚拟环境...
  py -3 -m venv .venv
  if errorlevel 1 exit /b 1
)

"%CLOUDNEST_PYTHON%" -c "import sys; raise SystemExit(0 if (3,12) <= sys.version_info[:2] <= (3,14) else 1)"
if errorlevel 1 (
  echo [bakaimg] 需要Python 3.12、3.13或3.14。
  exit /b 1
)

"%CLOUDNEST_PYTHON%" -m pip install --disable-pip-version-check --no-index --find-links wheelhouse -r requirements-dev.txt
if errorlevel 1 (
  echo [bakaimg] 本地依赖安装失败。
  exit /b 1
)

if not defined CLOUDNEST_ENV set "CLOUDNEST_ENV=development"
if not defined CLOUDNEST_HOST set "CLOUDNEST_HOST=127.0.0.1"
if not defined CLOUDNEST_PORT set "CLOUDNEST_PORT=5200"

"%CLOUDNEST_PYTHON%" -m flask --app wsgi:app db upgrade
if errorlevel 1 exit /b 1

"%CLOUDNEST_PYTHON%" -m flask --app wsgi:app init-site
if errorlevel 1 exit /b 1

"%CLOUDNEST_PYTHON%" -m flask --app wsgi:app system-check
if errorlevel 1 exit /b 1

"%CLOUDNEST_PYTHON%" -m flask --app wsgi:app media-check
if errorlevel 1 exit /b 1

if /I "%~1"=="--check-only" (
  echo [bakaimg] 检查完成。
  exit /b 0
)

echo [bakaimg] 本地测试地址：http://%CLOUDNEST_HOST%:%CLOUDNEST_PORT%
"%CLOUDNEST_PYTHON%" -m flask --app wsgi:app run --host "%CLOUDNEST_HOST%" --port "%CLOUDNEST_PORT%" --no-debugger --no-reload
exit /b %errorlevel%
