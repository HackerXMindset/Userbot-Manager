@echo off
REM DAIC command to toggle between Discussion and Implementation modes (Windows CMD version)

REM Get the project root (where .claude directory is)
set PROJECT_ROOT=%cd%

:find_claude
if exist "%PROJECT_ROOT%\.claude" goto found_claude
for %%I in ("%PROJECT_ROOT%") do set PARENT=%%~dpI
if "%PARENT%"=="%PROJECT_ROOT%" goto not_found
set PROJECT_ROOT=%PARENT:~0,-1%
goto find_claude

:not_found
echo [DAIC Error] Could not find .claude directory in current path or parent directories
exit /b 1

:found_claude
REM Find the hooks directory
set HOOKS_DIR=%PROJECT_ROOT%\.claude\hooks

REM Check if Python is available as python or python3
where python >nul 2>nul
if %errorlevel% equ 0 (
    set PYTHON_CMD=python
) else (
    where python3 >nul 2>nul
    if %errorlevel% equ 0 (
        set PYTHON_CMD=python3
    ) else (
        echo [DAIC Error] Python not found. Please ensure Python is installed and in your PATH
        exit /b 1
    )
)

REM Run Python inline to toggle mode
%PYTHON_CMD% -c "import sys; sys.path.insert(0, r'%HOOKS_DIR%'); from shared_state import toggle_daic_mode; mode = toggle_daic_mode(); print('[DAIC] ' + mode)"