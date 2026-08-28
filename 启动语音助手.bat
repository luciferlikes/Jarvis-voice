@echo off
rem Start Jarvis voice assistant silently (tray icon only, no console window)
start "" "%~dp0.venv\Scripts\pythonw.exe" "%~dp0main.py"
