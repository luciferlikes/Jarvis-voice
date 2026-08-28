"""全局配置：录音参数、模型参数，以及后续步骤的预留项。"""
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ---- 录音参数 ----
SAMPLE_RATE = 16000          # Whisper 要求的采样率
CHANNELS = 1
MAX_RECORD_SECONDS = 20      # 单次录音上限，防误触一直录
MIN_RECORD_SECONDS = 0.3     # 低于此时长视为误触，忽略

# 录音临时文件
RECORD_FILE = os.path.join(BASE_DIR, "last_record.wav")

# 托盘图标（scripts/make_icon.py 生成）
ICON_PATH = os.path.join(BASE_DIR, "icon.png")

# ---- 悬浮 UI（第六步启用）----
UI_ENABLED = os.getenv("JARVIS_UI", "1") != "0"     # 置 0 可退回纯托盘模式
UI_WIDTH = 420
UI_HEIGHT = 660

# 输入设备：None 表示系统默认麦克风，可用设备名覆盖（见 main.py 启动时打印的麦克风名）
INPUT_DEVICE = os.getenv("JARVIS_INPUT_DEVICE")

# ---- 语音识别（SenseVoice via sherpa-onnx，已替换 faster-whisper）----
# 中文 CER 7.8%（Whisper small 约 22%），CPU 上 ~17 倍实时；语种自动检测
SENSEVOICE_MODEL_DIR = os.path.join(BASE_DIR, "models", "sense-voice")   # 模型解压目录
SENSEVOICE_LANGUAGE = os.getenv("JARVIS_SENSEVOICE_LANGUAGE", "auto")    # auto/zh/en/ja/ko/yue

# 旧 faster-whisper 配置（scripts/download_model.py 仍引用，保留备用）
WHISPER_MODEL = os.getenv("JARVIS_WHISPER_MODEL", "small")
WHISPER_DEVICE = os.getenv("JARVIS_WHISPER_DEVICE", "cpu")
WHISPER_COMPUTE = os.getenv("JARVIS_WHISPER_COMPUTE", "int8")
MODEL_DIR = os.path.join(BASE_DIR, "models")   # 模型缓存目录

# ---- 语音播报（edge-tts 在线为主，pyttsx3 离线兜底）----
TTS_MAX_CHARS = int(os.getenv("JARVIS_TTS_MAX_CHARS", "300"))      # 超长回复只念前 N 字
TTS_EDGE_RATE = os.getenv("JARVIS_TTS_EDGE_RATE", "-10%")          # 语速微调（贾维斯要沉稳点）
TTS_VOICE_EN = os.getenv("JARVIS_TTS_VOICE_EN", "en-GB-RyanNeural")    # 英文：英伦男声
TTS_VOICE_ZH = os.getenv("JARVIS_TTS_VOICE_ZH", "zh-CN-YunjianNeural")  # 中文：云健（浑厚男声）
TTS_RATE = int(os.getenv("JARVIS_TTS_RATE", "180"))                # 离线兜底（pyttsx3）语速

# ---- 唤醒词（第四步启用）----
WAKE_WORD = "贾维斯"
# 中文唤醒：Vosk 模型目录（scripts/download_vosk_model.py 下载），匹配关键词（含同音字）
WAKE_MODEL_PATH = os.path.join(BASE_DIR, "models", "vosk-model-small-cn-0.22")
WAKE_KEYWORDS = ["贾维斯", "假维斯", "佳维斯", "贾维思", "贾维丝", "假维思"]
# 英文唤醒：openWakeWord 0.5.1 内置的 hey_jarvis 模型（喊 "Jarvis" / "Hey Jarvis"）
# 注意：0.6 起包不内置模型且预处理有 vstack bug，故固定用 0.5.1
WAKE_MODEL_EN = os.getenv("JARVIS_WAKE_MODEL_EN", "hey_jarvis")
WAKE_THRESHOLD_EN = float(os.getenv("JARVIS_WAKE_THRESHOLD_EN", "0.5"))   # 越低越灵敏

# ---- 录音结束判定（第四步启用）----
SILENCE_SECONDS = float(os.getenv("JARVIS_SILENCE_SECONDS", "1.0"))   # 连续静音多少秒自动结束录音
SILENCE_RMS = float(os.getenv("JARVIS_SILENCE_RMS", "0.006"))         # 静音 RMS 阈值，视麦克风环境调节

# 唤醒提示音（scripts/make_chime.py 生成）
CHIME_PATH = os.path.join(BASE_DIR, "chime.wav")

# ---- 常驻会话（anthropic SDK 流式，第七步启用）----
# 会话历史文件：跨重启保持对话记忆；删掉此文件即可重置记忆
SESSION_HISTORY = os.path.join(BASE_DIR, "session_history.json")
SESSION_MAX_TURNS = int(os.getenv("JARVIS_SESSION_MAX_TURNS", "8"))   # 保留最近 N 轮对话（历史太长会拖慢 API）
# web_search 工具委托给 claude -p 执行（CLI 自带 WebSearch 工具，权限见 .claude/settings.json）
CLAUDE_BIN = os.getenv("JARVIS_CLAUDE_BIN", "claude")
CLAUDE_FLAGS = ["-p"]      # -p：print 模式，非交互执行并直接返回结果
CLAUDE_TIMEOUT = int(os.getenv("JARVIS_CLAUDE_TIMEOUT", "300"))   # 单次执行超时（秒）
TOOL_TIMEOUT = int(os.getenv("JARVIS_TOOL_TIMEOUT", "60"))        # 工具委托超时（秒）
