@echo off
REM AutoShorts AI — Windows Startup Autostart Uninstaller

title Remove AutoShorts AI Startup

set "TASK_NAME=AutoShortsAutonomousOperator"
set "STARTUP_FOLDER=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"

echo [*] Removing AutoShorts AI Task Scheduler entry...
schtasks /delete /tn "%TASK_NAME%" /f >nul 2>&1

echo [*] Removing AutoShorts AI User Startup script...
if exist "%STARTUP_FOLDER%\AutoShorts_Startup.bat" (
    del /f /q "%STARTUP_FOLDER%\AutoShorts_Startup.bat" >nul 2>&1
)

echo [SUCCESS] AutoShorts AI Windows startup entries removed.
exit /b 0
