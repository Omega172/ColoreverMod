@echo off
setlocal
cd /d "%~dp0"
set "strInput=%~1"
if defined strInput set "strInput=%strInput:\=/%"
wsl -- bash ./Package.sh "%strInput%"
exit /b %errorlevel%
