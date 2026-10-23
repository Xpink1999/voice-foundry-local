@echo off
chcp 65001 >nul
call "%~dp0bin\voice.cmd" ui
if errorlevel 1 pause
