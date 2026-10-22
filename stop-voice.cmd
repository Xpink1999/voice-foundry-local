@echo off
chcp 65001 >nul
"%~dp0.venv\Scripts\python.exe" -m voice_platform.cli stop
