# Check waveOut master volume (the channel MCI playback uses): 0% = muted
Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
public class Vol {
    [DllImport("winmm.dll")]
    public static extern int waveOutGetVolume(IntPtr hwo, out uint v);
}
"@
[uint32]$v = 0
[Vol]::waveOutGetVolume([IntPtr]::Zero, [ref]$v) | Out-Null
$L = $v -band 0xFFFF
$R = ($v -shr 16) -band 0xFFFF
Write-Output ("waveOut volume - L: {0}%  R: {1}%" -f [int](100*$L/65535), [int](100*$R/65535))
