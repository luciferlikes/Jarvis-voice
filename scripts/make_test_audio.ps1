# Generate test WAVs with the Windows built-in TTS to verify the ASR chain
# without a real microphone. Chinese text is read from test_zh.txt because
# PowerShell 5.1 misreads UTF-8 source files without a BOM.
Add-Type -AssemblyName System.Speech
$outDir = Join-Path $PSScriptRoot "..\test_audio"
New-Item -ItemType Directory -Force -Path $outDir | Out-Null

$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
$s.Rate = 0

# English test - the default system voice (David/Zira) is always present
$s.SetOutputToWaveFile((Join-Path $outDir "test_en.wav"))
$s.Speak("Hello Jarvis, this is a voice recognition test.")
$s.SetOutputToNull()

# Chinese test - only if a Chinese voice (e.g. Huihui) is installed
$zh = $s.GetInstalledVoices() | Where-Object { $_.VoiceInfo.Culture.Name -match "^zh" } | Select-Object -First 1
if ($zh) {
    $text = (Get-Content -Raw -Encoding UTF8 (Join-Path $PSScriptRoot "test_zh.txt")).Trim()
    $s.SelectVoice($zh.VoiceInfo.Name)
    $s.SetOutputToWaveFile((Join-Path $outDir "test_zh.wav"))
    $s.Speak($text)
    $s.SetOutputToNull()
    Write-Output ("ZH voice: " + $zh.VoiceInfo.Name)
} else {
    Write-Output "No Chinese voice installed, skipping zh test"
}
$s.Dispose()
Write-Output "DONE"
