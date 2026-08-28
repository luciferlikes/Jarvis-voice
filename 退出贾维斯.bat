@echo off
chcp 65001 >nul
rem Force-exit all Jarvis instances (last resort when hotkey/tray fail)
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { ($_.Name -eq 'python.exe' -or $_.Name -eq 'pythonw.exe') -and ($_.CommandLine -like '*jarvis-voice*' -or $_.CommandLine -like '*jarvis*main.py*') } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"
echo 贾维斯已退出。
pause
