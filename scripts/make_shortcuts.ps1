# Create launcher shortcuts: direct pythonw target + custom ico icon.
# The lnk in the project dir is the canonical launcher: right-click it
# and "Send to Desktop" will keep the icon. The bat is legacy.
# Paths are derived at runtime (no hardcoded user paths).
$base = Split-Path -Parent $PSScriptRoot      # project root (scripts/..)
$desktop = [Environment]::GetFolderPath("Desktop")
$ws = New-Object -ComObject WScript.Shell
foreach ($lnk in @((Join-Path $base "Jarvis.lnk"), (Join-Path $desktop "Jarvis.lnk"))) {
    $s = $ws.CreateShortcut($lnk)
    $s.TargetPath = Join-Path $base ".venv\Scripts\pythonw.exe"
    $s.Arguments = '"' + (Join-Path $base "main.py") + '"'
    $s.WorkingDirectory = $base
    $s.IconLocation = (Join-Path $base "icon.ico") + ",0"
    $s.Description = "Launch Jarvis voice assistant"
    $s.Save()
    Write-Output ("Created: " + $lnk)
}
