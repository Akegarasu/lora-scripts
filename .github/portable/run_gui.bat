@echo off
setlocal
cd /d "%~dp0"
set "PYTHONHOME=%~dp0python"
set "PYTHONPATH="
set "PYTHONSAFEPATH="
set "PYTHONUTF8=1"
set "PYTHONUNBUFFERED=1"
set "HF_HOME=%~dp0huggingface"
set "PATH=%~dp0python;%~dp0python\Scripts;%PATH%"
"%~dp0python\python.exe" -s gui.py %*
set "GUI_EXIT_CODE=%ERRORLEVEL%"
pause
exit /b %GUI_EXIT_CODE%
