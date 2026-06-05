@echo off
setlocal
set "HERE=%~dp0"
type "%HERE%..\assets\ascii.txt"
echo.
set "PYEXE=%HERE%..\python\python.exe"
set "SCRIPT=%HERE%opeternal_listener.py"
if not exist "%PYEXE%" (
    echo Python not found. Run setup.bat first.
    pause & exit /b 1
)

set "BIND_IP=%~1"
if "%BIND_IP%"=="" set "BIND_IP=0.0.0.0"
set "HTTP_PORT=%~2"
if "%HTTP_PORT%"=="" set "HTTP_PORT=80"
set "HTTPS_PORT=%~3"
if "%HTTPS_PORT%"=="" set "HTTPS_PORT=443"

cd /d "%HERE%"
"%PYEXE%" opeternal_listener.py --bind-ip %BIND_IP% --http-port %HTTP_PORT% --https-port %HTTPS_PORT%
pause
