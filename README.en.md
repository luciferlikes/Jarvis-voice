# JARVIS — Jarvis Voice Assistant

> 中文版本：[README.md](README.md)

Say the wake word → speak → on-device transcription → LLM reply → spoken answer, with a holographic particle overlay straight out of Iron Man. Wake word and speech recognition run fully offline; only the conversational brain lives in the cloud.

## Features

- **Wake word**: Chinese "贾维斯" (homophones included) via Vosk, English "Hey Jarvis" via openWakeWord; spacebar as a fallback trigger
- **Speech recognition**: SenseVoice (sherpa-onnx, local CPU real-time, automatic Chinese/English detection)
- **Conversation**: Anthropic-compatible gateway (DeepSeek by default), streaming replies, session memory across restarts
- **Speech output**: edge-tts neural voices (Chinese Yunjian / English British male), pyttsx3 offline fallback; playback via miniaudio + sounddevice
- **Action tools**: open webpages/files/folders, search the web, hide the UI, exit itself
- **UI**: pywebview transparent always-on-top overlay (click-through, draggable), Matrix digital rain + particles + arc reactor ring, four-state machine (idle / listening / thinking / replying)
- **System tray**: pause/resume, hide UI, quit; auto-start script

## Requirements

- Windows 10/11 (requires pywebview WebView2, pystray, keyboard)
- Python 3.12
- Microphone + audio output device
- Environment variables (required for conversation):
  - `ANTHROPIC_BASE_URL`: Anthropic-compatible gateway address (e.g. `https://api.deepseek.com/anthropic`)
  - `ANTHROPIC_AUTH_TOKEN`: gateway API key (`sk-` prefix optional, added automatically)
  - `ANTHROPIC_MODEL` (optional, defaults to `deepseek-v4-pro[1m]`)

## Installation

```bat
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt

:: Download models (SenseVoice transcription + Vosk Chinese wake word, ~300MB total)
.venv\Scripts\python scripts\download_sensevoice.py
.venv\Scripts\python scripts\download_vosk_model.py
```

> openWakeWord must be pinned to `0.5.1` (0.6+ no longer bundles models and has a preprocessing bug); its English wake-word feature models must be placed inside the package's own `resources/models/` directory.

## Usage

- Launch: `启动语音助手.bat` (silent) or `.venv\Scripts\pythonw.exe main.py`
- Wake: say "贾维斯" or press the spacebar → stop speaking and pause ~1 second to end the turn
- Hotkeys:
  - `Ctrl+Alt+Q` graceful exit (`Ctrl+Alt+Shift+Q` force exit)
  - `Ctrl+Alt+M` hide/show the UI (saying the wake word while hidden brings it back)
- Tray: double-click = pause/resume; right-click = hide UI / quit
- Example voice commands: "open Baidu", "open the resume folder on my desktop", "what's on drive E", "minimize yourself", "quit"

All settings live in `config.py` (overridable via `JARVIS_*` environment variables).

## Security notes

**This program is designed for personal use and works out of the box; read this section and tighten the configuration before running it in shared or untrusted environments.**

### Inherent risk model

| Risk | Description | Mitigation |
|---|---|---|
| Always-on microphone | The wake word is always listening; anyone nearby (or "Jarvis" on TV/video) can trigger it | Tray "pause" mutes instantly; `SILENCE_RMS`/wake thresholds are adjustable |
| Voice-executed local actions | After waking, files/folders/webpages can be opened by voice (restricted by allowlist) | `run_command` allowlist + executable blacklist; tools can be disabled in sensitive environments |
| Prompt injection | Audio content (e.g. voices from a playing video) is transcribed into context; malicious audio could coax the model into calling tools | Avoid playing instruction-bearing audio near JARVIS |
| Data exfiltration | Directory structure read by `list_dir` could theoretically be written into a `web_search` query and leave the machine | `list_dir` returns only directory names (max 50 entries); disable if concerned |
| Plaintext session storage | `session_history.json` stores conversation history in plaintext (may contain personal info) | Already in `.gitignore`; delete periodically or change the `SESSION_HISTORY` path |
| Key handling | API keys come only from environment variables, never code; but run logs print the endpoint and the first 6 characters of the key | Log files are in `.gitignore`; never share logs |

### Pre-open-source checklist

- [ ] Confirm no hardcoded keys/personal paths (`scripts/make_shortcuts.ps1` contains machine-specific paths — delete or parameterize before committing)
- [ ] `.gitignore` covers: `.venv/`, `models/`, audio, logs, session history, `.claude/`
- [ ] Model files are not committed (large + individual licenses; use the download scripts instead)
- [ ] README states: the API gateway is a third-party service (DeepSeek etc.) — conversation content is sent to the configured gateway

### Project structure

```
main.py               Main loop: wake → record → transcribe → chat → speak
wake_word.py          Wake word detection (Vosk Chinese + openWakeWord English)
speech_to_text.py     SenseVoice transcription (sherpa-onnx)
claude_code_bridge.py Persistent session + tools (web_search/run_command/list_dir/hide_self/exit_self)
text_to_speech.py     edge-tts synthesis + miniaudio/sounddevice playback
ui.py / ui/face.html  Holographic overlay (pywebview + particle UI)
tray.py               System tray
config.py             All tunable parameters
scripts/              Model downloads, smoke tests, helper scripts
```

## License

Code: MIT (see [LICENSE](LICENSE)). Model files are downloaded from official sources under their respective licenses (SenseVoice / Vosk / openWakeWord) and are not distributed with this repository.
