@echo off
REM AutoShorts AI — Windows Autonomous Operator Background Runner
REM Starts the Gradio UI and autonomous channel watcher quietly on system startup.

title AutoShorts AI Autonomous Operator

set "PROJECT_DIR=%~dp0.."
cd /d "%PROJECT_DIR%"

REM Create logs directory if not present
if not exist "logs" mkdir logs

REM Locate Python 3.11 executable
set "PYTHON_EXE="
if exist "%LOCALAPPDATA%\Programs\Python\Python311\python.exe" (
    set "PYTHON_EXE=%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
) else (
    where python >nul 2>&1
    if not errorlevel 1 (
        set "PYTHON_EXE=python"
    ) else (
        echo [ERROR] Python not found in PATH or standard install directory. >> logs\autonomous_operator.log
        exit /b 1
    )
)

echo [%DATE% %TIME%] Starting AutoShorts AI Autonomous Daemon... >> logs\autonomous_operator.log

REM Run daemon cycle and startup catch-up sync
"%PYTHON_EXE%" -c "from src.core.autonomous_daemon import AutonomousDaemon; d = AutonomousDaemon(); rep = d.run_cycle(); print('Cycle completed:', rep.get('timestamp_iso'), 'Jobs executed:', rep.get('jobs_executed'))" >> logs\autonomous_operator.log 2>&1

echo [%DATE% %TIME%] Autonomous cycle executed successfully. >> logs\autonomous_operator.log
exit /b 0
