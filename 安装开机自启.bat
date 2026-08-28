@echo off
rem Create a startup shortcut so Jarvis starts with Windows
set SHORTCUT=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\JarvisVoice.lnk
powershell -Command "$ws = New-Object -ComObject WScript.Shell; $s = $ws.CreateShortcut('%SHORTCUT%'); $s.TargetPath = '%~dp0.venv\Scripts\pythonw.exe'; $s.Arguments = '\"%~dp0main.py\"'; $s.WorkingDirectory = '%~dp0'; $s.Save()"
if %errorlevel%==0 (echo Installed. Jarvis will start with Windows.) else (echo Failed.)
pause
