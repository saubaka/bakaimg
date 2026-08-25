@echo off
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0"

set "CLOUDNEST_PYTHON=.venv\Scripts\python.exe"

if not exist "%CLOUDNEST_PYTHON%" (
  echo [bakaimg] 请先运行 start.bat --check-only 创建本地环境。
  exit /b 1
)

if not defined CLOUDNEST_SECRET_KEY (
  echo [bakaimg] 生产启动前必须设置 CLOUDNEST_SECRET_KEY。
  exit /b 1
)
if not defined CLOUDNEST_SITE_URL (
  echo [bakaimg] 生产启动前必须设置使用 HTTPS 的 CLOUDNEST_SITE_URL。
  exit /b 1
)

set "CLOUDNEST_ENV=production"
if not defined CLOUDNEST_HOST set "CLOUDNEST_HOST=127.0.0.1"
if not defined CLOUDNEST_PORT set "CLOUDNEST_PORT=5200"
if not defined CLOUDNEST_THREADS set "CLOUDNEST_THREADS=8"

"%CLOUDNEST_PYTHON%" -m pip install --disable-pip-version-check --no-index --find-links wheelhouse -r requirements.txt
if errorlevel 1 exit /b 1

"%CLOUDNEST_PYTHON%" -m flask --app wsgi:app db upgrade
if errorlevel 1 exit /b 1
"%CLOUDNEST_PYTHON%" -m flask --app wsgi:app init-site
if errorlevel 1 exit /b 1
"%CLOUDNEST_PYTHON%" -m flask --app wsgi:app system-check
if errorlevel 1 exit /b 1
"%CLOUDNEST_PYTHON%" -m flask --app wsgi:app media-check
if errorlevel 1 exit /b 1

if /I "%~1"=="--check-only" (
  echo [bakaimg] 生产预检完成。
  exit /b 0
)

echo [bakaimg] 正在启动生产服务：http://%CLOUDNEST_HOST%:%CLOUDNEST_PORT%
"%CLOUDNEST_PYTHON%" serve.py
exit /b %errorlevel%
