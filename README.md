# 贾维斯语音助手（JARVIS）

喊一声「贾维斯」唤醒 → 说话 → 本地转写 → 大模型回复 → 语音播报，配一个全息粒子悬浮窗（钢铁侠风格）。完全离线的唤醒词与语音识别，云端只负责对话大脑。

## 特性

- **唤醒词**：中文「贾维斯」（含同音字）via Vosk，英文 "Hey Jarvis" via openWakeWord；空格键兜底触发
- **语音识别**：SenseVoice（sherpa-onnx，本地 CPU 实时，中英自动检测）
- **对话**：Anthropic 兼容网关（默认 DeepSeek），流式回复、跨重启会话记忆
- **播报**：edge-tts 神经语音（中文云健 / 英文英伦男声），pyttsx3 离线兜底；miniaudio + sounddevice 播放
- **动作工具**：打开网页/文件/文件夹、搜索联网信息、隐藏界面、退出自己
- **UI**：pywebview 全屏透明悬浮窗（鼠标穿透、置顶），Matrix 数字雨 + 粒子 + 弧反应堆圆环，四态状态机（待机/聆听/思考/回复）
- **托盘**：暂停/继续、隐藏界面、退出；开机自启脚本

## 环境要求

- Windows 10/11（依赖 pywebview WebView2、pystray、keyboard）
- Python 3.12
- 麦克风 + 音频输出设备
- 环境变量（对话必需）：
  - `ANTHROPIC_BASE_URL`：Anthropic 兼容网关地址（如 `https://api.deepseek.com/anthropic`）
  - `ANTHROPIC_AUTH_TOKEN`：网关密钥（`sk-` 前缀可省略，程序自动补全）
  - `ANTHROPIC_MODEL`（可选，默认 `deepseek-v4-pro[1m]`）

## 安装

```bat
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt

:: 下载模型（SenseVoice 转写 + Vosk 中文唤醒，共约 300MB）
.venv\Scripts\python scripts\download_sensevoice.py
.venv\Scripts\python scripts\download_vosk_model.py
```

> openWakeWord 必须钉在 `0.5.1`（0.6 起不内置模型且预处理有 bug），其英文唤醒特征模型需放入包自身的 `resources/models/` 目录。

## 使用

- 启动：`启动语音助手.bat`（静默）或 `.venv\Scripts\pythonw.exe main.py`
- 唤醒：喊「贾维斯」或按空格 → 说完停顿 1 秒自动结束
- 热键：
  - `Ctrl+Alt+Q` 优雅退出（`Ctrl+Alt+Shift+Q` 强制退出）
  - `Ctrl+Alt+M` 隐藏/显示界面（隐藏后喊唤醒词自动恢复）
- 托盘：双击 = 暂停/继续；右键 = 隐藏界面 / 退出
- 语音指令示例：「打开百度」「打开桌面上的简历文件夹」「看看 E 盘有什么」「最小化自己」「退出吧」

配置项见 `config.py`（均可通过 `JARVIS_*` 环境变量覆盖）。

## 安全说明

**本程序为个人使用设计，默认开箱即用；在共享/不受控环境中请阅读本节并自行收紧配置。**

### 固有风险模型

| 风险 | 说明 | 缓解 |
|---|---|---|
| 麦克风常开 | 唤醒词始终监听；旁人靠近（或电视/视频里出现"贾维斯"）即可触发 | 托盘"暂停"可随时关麦；`SILENCE_RMS`/唤醒阈值可调 |
| 语音执行本地操作 | 唤醒后可语音打开文件/文件夹/网页（受允许列表限制） | `run_command` 白名单 + 可执行文件黑名单；敏感环境可禁用工具 |
| 提示词注入 | 音频内容（如播放的视频人声）会被转写进入上下文，恶意音频可能诱导模型调用工具 | 避免在贾维斯附近播放含指令的音频 |
| 数据外带 | `list_dir` 读到的目录结构理论上可被模型写入 `web_search` 查询而流出本机 | `list_dir` 仅返回目录名（上限 50 项）；介意可禁用 |
| 会话明文存储 | `session_history.json` 明文保存对话历史（含个人信息） | 已加入 `.gitignore`；定期删除或改 `SESSION_HISTORY` 路径 |
| 密钥处理 | 密钥仅从环境变量读取、不进代码；但运行日志会打印端点与密钥前 6 位 | 日志文件已在 `.gitignore`，勿将日志外发 |

### 开源前检查清单

- [ ] 确认无硬编码密钥/个人路径（`scripts/make_shortcuts.ps1` 含本机路径，提交前删除或参数化）
- [ ] `.gitignore` 已覆盖：`.venv/`、`models/`、音频、日志、会话历史、`.claude/`
- [ ] 模型文件不提交仓库（体积大 + 各自许可证，用下载脚本代替）
- [ ] README 声明：API 网关为第三方服务（DeepSeek 等），对话内容会发送至所配置的网关

### 项目结构

```
main.py               主循环：唤醒 → 录音 → 转写 → 对话 → 播报
wake_word.py          唤醒词检测（Vosk 中文 + openWakeWord 英文）
speech_to_text.py     SenseVoice 转写（sherpa-onnx）
claude_code_bridge.py 常驻会话 + 工具（web_search/run_command/list_dir/hide_self/exit_self）
text_to_speech.py     edge-tts 合成 + miniaudio/sounddevice 播放
ui.py / ui/face.html  全息悬浮窗（pywebview + 粒子 UI）
tray.py               系统托盘
config.py             全部可调参数
scripts/              模型下载、冒烟测试、辅助脚本
```

## 许可

代码：MIT（待定）。模型文件按其各自许可证（SenseVoice / Vosk / openWakeWord）从官方源下载。
