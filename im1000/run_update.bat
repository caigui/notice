@echo off
setlocal

rem Move to the directory where this .bat file lives
cd /d "%~dp0"

rem Pick an available Python launcher: prefer "python", fall back to "py -3"
set "PYCMD=python"
where python >nul 2>nul
if errorlevel 1 (
    where py >nul 2>nul
    if errorlevel 1 (
        echo [ERROR] Python not found. Please install Python 3 and add it to PATH.
        goto end
    )
    set "PYCMD=py -3"
)

echo Working dir: %CD%
echo Command    : %PYCMD% im1000_panel.py --update
echo.

if /i "%~1"=="/auto" (
    %PYCMD% im1000_panel.py --update >> "%~dp0im1000_update.log" 2>&1
) else (
    %PYCMD% im1000_panel.py --update
)
set "RC=%ERRORLEVEL%"

echo.
if "%RC%"=="0" (
    echo [OK] im1000_panel.py --update finished successfully.
) else (
    echo [ERROR] im1000_panel.py --update failed with exit code %RC%.
)

:end
echo.
rem Scheduled task calls this with /auto - never pause in that case.
if /i "%~1"=="/auto" goto no_pause
if defined NOTICE_NO_PAUSE goto no_pause
pause
:no_pause
endlocal
