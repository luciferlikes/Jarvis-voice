# Capture a window's content including GPU-composited layers.
# Finds the window by command-line substring match (avoids Chinese title encoding issues).
# Usage: powershell -ExecutionPolicy Bypass -File scripts/print_window.ps1 "jarvis-voice" out.png
param([string]$Match, [string]$Out)
Add-Type @"
using System;
using System.Runtime.InteropServices;
public class W {
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out R r);
  [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr h, IntPtr dc, uint f);
  public struct R { public int L, T, Rt, B; }
}
"@
Add-Type -AssemblyName System.Drawing
$proc = $null
foreach ($c in (Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like "*$Match*" -and $_.Name -like 'python*' })) {
  $try = Get-Process -Id $c.ProcessId -ErrorAction SilentlyContinue
  if ($try -and $try.MainWindowHandle -ne 0) { $proc = $c; break }
}
if (-not $proc) { Write-Output "no windowed process found: $Match"; exit 1 }
$p = Get-Process -Id $proc.ProcessId -ErrorAction SilentlyContinue
if (-not $p -or $p.MainWindowHandle -eq 0) { Write-Output "no window for pid $($proc.ProcessId)"; exit 1 }
$r = New-Object W+R
[W]::GetWindowRect($p.MainWindowHandle, [ref]$r) | Out-Null
$w = $r.Rt - $r.L; $h = $r.B - $r.T
$bmp = New-Object System.Drawing.Bitmap $w, $h
$g = [System.Drawing.Graphics]::FromImage($bmp)
$hdc = $g.GetHdc()
# flag 2 = PW_RENDERFULLCONTENT: capture DirectComposition layers
[W]::PrintWindow($p.MainWindowHandle, $hdc, 2) | Out-Null
$g.ReleaseHdc($hdc)
$bmp.Save($Out)
Write-Output ("saved " + $Out + " " + $w + "x" + $h + " title=" + $p.MainWindowTitle)
