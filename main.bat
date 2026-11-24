@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title notice - daily alert launcher

rem ---- locate a Python 3 that actually has akshare + prompt_toolkit ----
rem The old hardcoded WindowsApps\python3.13.exe no longer exists. Prefer the
rem Store Python 3.13 (where the deps are installed), then fall back to PATH.
set "PYCMD="
set "STORE_PY=C:\Users\admin\AppData\Local\Microsoft\WindowsApps\PythonSoftwareFoundation.Python.3.13_qbz5n2kfra8p0\python.exe"
if exist "%STORE_PY%" (
    "%STORE_PY%" -c "import akshare, prompt_toolkit" >nul 2>&1
    if not errorlevel 1 set "PYCMD=%STORE_PY%"
)
if not defined PYCMD (
    where python >nul 2>nul
    if not errorlevel 1 set "PYCMD=python"
)
if not defined PYCMD (
    where py >nul 2>nul
    if not errorlevel 1 set "PYCMD=py -3"
)
if not defined PYCMD (
    echo [ERROR] Python 3 not found. Install Python 3 with akshare + prompt_toolkit.
    pause
    exit /b 1
)

echo [%DATE% %TIME%] launcher start, python=%PYCMD% >> "%~dp0notice_launch.log"

rem ---- 1) market brief: run ONCE right after this launcher starts (background) ----
echo [%DATE% %TIME%] launching market_brief\main.bat once >> "%~dp0notice_launch.log"
start "market_brief" /MIN /D "%~dp0market_brief" cmd /c "main.bat"

rem ---- 2) im1000: register a Windows daily task at 15:00 (idempotent) ----
set "TASKNAME=NoticeIm1000DailyUpdate"
set "IMUPDATE_BAT=%~dp0im1000\run_update.bat"
schtasks /create /tn "%TASKNAME%" /tr "\"%IMUPDATE_BAT%\" /auto" /sc daily /st 15:00 /f >nul 2>&1
if errorlevel 1 (
    echo [%DATE% %TIME%] WARN: failed to register daily task %TASKNAME% >> "%~dp0notice_launch.log"
) else (
    echo [%DATE% %TIME%] registered daily task %TASKNAME% at 15:00 >> "%~dp0notice_launch.log"
)

rem ---- 3) main alert process (stays in foreground) ----
echo [%DATE% %TIME%] starting main.py >> "%~dp0notice_launch.log"
%PYCMD% "%~dp0main.py"

endlocal
