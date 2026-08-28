# Find the Jarvis UI window and print its rectangle.
# Usage: powershell -ExecutionPolicy Bypass -File scripts/find_window.ps1
Add-Type @"
using System;
using System.Runtime.InteropServices;
public class Win32 {
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr hWnd, out RECT r);
  public struct RECT { public int Left, Top, Right, Bottom; }
}
"@
$procs = Get-Process python -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowTitle -match 'voice|jarvis' -or $_.MainWindowTitle -ne '' }
foreach ($p in Get-Process -ErrorAction SilentlyContinue) {
  if ($p.MainWindowTitle -eq '') { continue }
  $r = New-Object Win32+RECT
  [Win32]::GetWindowRect($p.MainWindowHandle, [ref]$r) | Out-Null
  Write-Output ("PID=" + $p.Id + " name=" + $p.ProcessName + " title=" + $p.MainWindowTitle + " rect=" + $r.Left + "," + $r.Top + "," + $r.Right + "," + $r.Bottom)
}
