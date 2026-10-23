@echo off
setlocal
if not exist "%~dp0..\.venv\Scripts\python.exe" (
  echo Voice Foundry is not installed in this folder.
  echo Run install-voice.cmd, or: powershell -ExecutionPolicy Bypass -File scripts\install.ps1
  exit /b 2
)
set "PYTHONPATH="
set "PYTHONHOME="
set "PYTHONNOUSERSITE=1"
"%~dp0..\.venv\Scripts\python.exe" -m voice_platform.cli %*
exit /b %errorlevel%
