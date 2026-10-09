@echo off
REM ============================================================
REM  MathModelAgent entry point (Windows)
REM
REM  This file must stay pure ASCII (no Chinese text) and keep
REM  NOTHING after the "python start.py" call but exit+EOF.
REM  cmd.exe reads batch files byte-wise; multibyte text can be
REM  split mid-character inside its read buffer and the stray
REM  fragment gets executed as a command (random "'xxx' is not
REM  recognized" errors). With only exit+EOF after the python
REM  call there is nothing left to misfire, and the exit code
REM  still equals python's.
REM
REM  All logic lives in start.py (install / start / stop).
REM  Usage: start.bat [start|install|stop] [--docker]
REM ============================================================
setlocal
chcp 65001 >nul
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 goto no_python
python -c "import sys;print(sys.version)" >nul 2>nul
if errorlevel 1 goto no_python
if not exist "%~dp0start.py" goto no_entry
goto run

:no_python
echo [ERROR] Python not found. Please install Python 3.11+ from:
echo         https://www.python.org/downloads/
echo         and check "Add python.exe to PATH" during setup.
set /p "=Press Enter to exit . . . "
exit /b 1

:no_entry
echo [ERROR] start.py is missing - the download is incomplete.
echo         Please re-download the full project and retry.
set /p "=Press Enter to exit . . . "
exit /b 1

:run
python "%~dp0start.py" %*
exit /b %errorlevel%
