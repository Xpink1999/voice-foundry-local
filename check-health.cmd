@echo off
chcp 65001 >nul
call "%~dp0bin\voice.cmd" health
if errorlevel 1 pause
