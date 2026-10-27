@echo off
REM AutoShorts AI — Windows Startup Autostart Installer
REM Registers AutoShorts AI in Windows Task Scheduler or the user's Startup folder.

title AutoShorts AI Startup Setup

set "SCRIPT_DIR=%~dp0"
set "BAT_PATH=%SCRIPT_DIR%start_autonomous_operator.bat"
set "TASK_NAME=AutoShortsAutonomousOperator"

echo ============================================================
echo   AutoShorts AI - Windows Startup Autostart Configuration
echo ============================================================
echo.

if "%1"=="/uninstall" goto UNINSTALL
if "%1"=="--uninstall" goto UNINSTALL

REM Try registering via Windows Task Scheduler (runs on user logon with highest available privileges)
echo [*] Registering Task Scheduler task: %TASK_NAME%...
schtasks /create /tn "%TASK_NAME%" /tr "\"%BAT_PATH%\"" /sc onlogon /rl highest /f >nul 2>&1
if not errorlevel 1 (
    echo [SUCCESS] Task Scheduler registration completed successfully.
    echo           AutoShorts AI will now automatically check your watch folder
    echo           and sync YouTube channel metrics each time you log in to Windows.
    goto DONE
)

REM Fallback: Create shortcut / launcher in user's Startup directory
echo [!] Task Scheduler required administrative privileges.
echo [*] Falling back to Windows User Startup folder...
set "STARTUP_FOLDER=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"

if exist "%STARTUP_FOLDER%" (
    echo @echo off > "%STARTUP_FOLDER%\AutoShorts_Startup.bat"
    echo start /B "" "%BAT_PATH%" >> "%STARTUP_FOLDER%\AutoShorts_Startup.bat"
    echo [SUCCESS] Startup launcher created in:
    echo           %STARTUP_FOLDER%\AutoShorts_Startup.bat
    goto DONE
) else (
    echo [ERROR] Could not locate Windows Startup folder: %STARTUP_FOLDER%
    exit /b 1
)

:UNINSTALL
echo [*] Removing AutoShorts AI from startup...
schtasks /delete /tn "%TASK_NAME%" /f >nul 2>&1
set "STARTUP_FOLDER=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
if exist "%STARTUP_FOLDER%\AutoShorts_Startup.bat" (
    del /f /q "%STARTUP_FOLDER%\AutoShorts_Startup.bat" >nul 2>&1
)
echo [SUCCESS] AutoShorts AI startup autostart removed cleanly.
goto END

:DONE
echo.
echo Setup finished. To remove startup autostart at any time, run:
echo setup_windows_startup.bat /uninstall
echo.

:END
exit /b 0
