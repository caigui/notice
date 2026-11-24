@echo off
setlocal

rem Move to the directory where this .bat file lives
cd /d "%~dp0"

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
echo Command    : %PYCMD% risk_premium_panel.py --update
echo.

if /i "%~1"=="/auto" (
    %PYCMD% risk_premium_panel.py --update >> "%~dp0risk_premium_update.log" 2>&1
) else (
    %PYCMD% risk_premium_panel.py --update
)
set "RC=%ERRORLEVEL%"

echo.
if "%RC%"=="0" (
    echo [OK] risk_premium_panel.py --update finished successfully.
) else (
    echo [ERROR] risk_premium_panel.py --update failed with exit code %RC%.
)

:end
echo.
if /i "%~1"=="/auto" goto no_pause
if defined NOTICE_NO_PAUSE goto no_pause
pause
:no_pause
endlocal
