@echo off
setlocal
cd /d "%~dp0"
wsl -- bash ./Build.sh %*
exit /b %errorlevel%
