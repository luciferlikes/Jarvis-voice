"""主程序：喊「贾维斯」唤醒 → 说话 → 转文字 → Claude Code 执行 → 语音播报。

常驻后台运行：悬浮粒子 UI（pywebview，主线程）+ 系统托盘（独立线程，暂停/退出）。
JARVIS_UI=0 可退回纯托盘模式。
"""
import os
import queue
import re
import sys
import threading
import time
import wave
from collections import deque

import keyboard
import numpy as np
import sounddevice as sd

import config
from claude_code_bridge import ClaudeSession
from speech_to_text import SpeechToText
from text_to_speech import TextToSpeech, play_audio
from tray import run_tray, run_tray_detached
from ui import UiBridge, run_ui, toggle_ui_hidden, is_ui_hidden, close_ui
from wake_word import WakeWordDetector

# pythonw 静默启动时没有 stdout/stderr，print 会崩；改写入日志文件，方便排查
if sys.stdout is None or sys.stderr is None:
    _log = open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "console_log.txt"), "a", encoding="utf-8", buffering=1)
    if sys.stdout is None:
        sys.stdout = _log
    if sys.stderr is None:
        sys.stderr = _log
print(f"\n===== 启动 {time.strftime('%Y-%m-%d %H:%M:%S')} =====")

CHUNK = 1280   # 80ms @ 16kHz，唤醒识别器的输入帧长

# 流式回复的句子切分：从缓冲区开头匹配完整句（含句末标点/换行）
_SENTENCE_RE = re.compile(r"[^。！？!?；;.\n]*[。！？!?；;.\n]+")


_PS_FIND_INSTANCES = (
    "Get-CimInstance Win32_Process | "
    "Where-Object { ($_.Name -eq 'python.exe' -or $_.Name -eq 'pythonw.exe') -and "
    "($_.CommandLine -like '*jarvis-voice*' -or $_.CommandLine -like '*jarvis*main.py*') } | "
    "Select-Object -ExpandProperty ProcessId"
)

_TRAY_ICON = None   # 托盘句柄：退出流程必须 stop()，否则托盘线程拖住进程


def _stop_tray() -> None:
    """停止托盘图标线程（幂等）。所有退出路径统一调用。"""
    global _TRAY_ICON
    if _TRAY_ICON is not None:
        try:
            _TRAY_ICON.stop()
        except Exception:
            pass
        _TRAY_ICON = None


def _singleton() -> bool:
    """防止多开：启动时清掉所有残留实例再继续。

    教训：venv 双进程的命令行不一定含完整路径，之前按
    '*Python312*jarvis-voice*main.py*' 匹配会漏掉大部分实例，
    导致每重启一次就多一个僵尸窗口。现在模糊匹配 + 主动清理。
    """
    import subprocess

    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command", _PS_FIND_INSTANCES],
            capture_output=True, text=True, timeout=15,
        )
        pids = [int(x) for x in out.stdout.split() if x.strip().isdigit()]
    except Exception:
        pids = []
    # venv 双进程：排除自身 + 父进程（启动器），否则会把自己的本体进程杀掉
    exclude = {os.getpid(), os.getppid()}
    others = [p for p in pids if p not in exclude]
    if others:
        print(f"[!] 发现残留实例 {len(others)} 个（{others}），清理中 ...")
        subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "Stop-Process -Id " + ",".join(map(str, others)) +
             " -Force -ErrorAction SilentlyContinue"],
            capture_output=True, timeout=15,
        )
        time.sleep(1)
        print("[!] 残留实例已清理，继续启动。")
    return True


class AudioStream:
    """一个常开的麦克风流：唤醒监听和指令录音共用，避免反复开关设备。"""

    def __init__(self):
        self.queue = queue.Queue()

    def __enter__(self):
        self._stream = sd.InputStream(
            samplerate=config.SAMPLE_RATE,
            channels=config.CHANNELS,
            dtype="float32",
            device=config.INPUT_DEVICE,
            blocksize=CHUNK,
            callback=lambda indata, *_: self.queue.put(indata.copy()),
        )
        self._stream.start()
        return self

    def __exit__(self, *_):
        self._stream.stop()
        self._stream.close()

    def drain(self) -> None:
        """丢掉队列里残留的旧音频（上一轮的 TTS/录音尾巴）。"""
        while not self.queue.empty():
            self.queue.get()


def wait_for_trigger(stream, detector, stop_event, pause_event):
    """阻塞等待唤醒词或空格，返回 (触发方式, 触发前预录缓冲)；暂停/退出返回 None。

    预录缓冲保留触发前 0.64s 音频——用户常把指令紧跟在"贾维斯"后面说，
    丢掉会造成开头缺字，连唤醒词一起交给 Whisper，识别后再剥离唤醒词。
    """
    stream.drain()
    detector.reset()   # 清掉上一轮识别的残留，避免重复触发
    print(f"待机中 ... 喊「{config.WAKE_WORD}」或按空格触发")
    pre = deque(maxlen=8)   # 8 x 80ms = 0.64s
    while True:
        try:
            chunk = stream.queue.get(timeout=0.5)
        except queue.Empty:
            if stop_event.is_set() or pause_event.is_set():
                return None
            continue
        if stop_event.is_set() or pause_event.is_set():
            return None
        pre.append(chunk)
        if detector.detect(chunk):
            print("■ 检测到唤醒词！")
            return "wake", list(pre)
        if keyboard.is_pressed("space"):
            while keyboard.is_pressed("space"):   # 等松开，避免误入录音
                time.sleep(0.02)
            print("■ 空格触发")
            return "space", list(pre)


def record_command(stream, stop_event, bridge, preroll) -> np.ndarray | None:
    """录音直到静音超时或时长上限；太短/被退出返回 None。"""
    stream.drain()   # 丢掉提示音期间的声音，保留触发前的预录缓冲
    print("● 录音中 ...（说完停 1-2 秒自动结束）")
    chunks, silent = list(preroll), 0.0
    while True:
        try:
            chunk = stream.queue.get(timeout=0.5)
        except queue.Empty:
            if stop_event.is_set():
                return None
            continue
        if stop_event.is_set():
            return None
        chunks.append(chunk)
        rms = float(np.sqrt(np.mean(chunk ** 2)))
        bridge.push({"type": "level", "v": min(1.0, rms / 0.05)})   # 驱动粒子跳动
        silent = silent + CHUNK / config.SAMPLE_RATE if rms < config.SILENCE_RMS else 0.0
        total = len(chunks) * CHUNK / config.SAMPLE_RATE
        if silent >= config.SILENCE_SECONDS or total >= config.MAX_RECORD_SECONDS:
            break
    print("■ 录音结束")
    bridge.push({"type": "level", "v": 0.0})
    audio = np.concatenate(chunks).flatten()
    if len(audio) < config.SAMPLE_RATE * config.MIN_RECORD_SECONDS:
        print("[!] 录音太短，已忽略")
        return None
    return audio


def _strip_wake_words(text: str) -> str:
    """去掉转写结果开头的唤醒词（中文同音字 + 英文 jarvis 变体）。"""
    for w in config.WAKE_KEYWORDS + ["jarvis", "hey jarvis", "hi jarvis"]:
        text = re.sub(rf"^\s*{re.escape(w)}[\s，,。.]*", "", text, flags=re.IGNORECASE)
    return text.strip()


def save_wav(audio: np.ndarray) -> str:
    with wave.open(config.RECORD_FILE, "wb") as f:
        f.setnchannels(config.CHANNELS)
        f.setsampwidth(2)
        f.setframerate(config.SAMPLE_RATE)
        f.writeframes((audio * 32767).astype(np.int16).tobytes())
    return config.RECORD_FILE


def _greet(tts, bridge: UiBridge, stream) -> None:
    """启动问候：英文开口（贾维斯人设），主动提问；说完清掉回声。

    注意问候语里不能出现唤醒词「贾维斯」，否则会被自己的麦克风误唤醒。
    """
    h = time.localtime().tm_hour
    period = "morning" if 6 <= h < 12 else "afternoon" if 12 <= h < 18 else "evening"
    text = (f"Good {period}, sir. All systems are operational. "
            "How may I be of assistance today?")
    print(f"[Greet] {text}")
    bridge.push({"type": "state", "state": "speaking"})
    bridge.push({"type": "message", "role": "assistant", "text": text})
    try:
        tts.speak(text)
    except Exception as e:
        print(f"[TTS] 启动问候失败（{e}）")
    bridge.push({"type": "state", "state": "idle"})
    stream.drain()   # 清掉问候声的麦克风回声，避免误触发


def voice_loop(stop_event, pause_event, bridge: UiBridge) -> None:
    """语音助手主循环，跑在后台线程里。"""
    stt = SpeechToText()
    session = ClaudeSession()      # 常驻会话：跨轮次/跨重启保持记忆

    def _step_aside():
        """打开文件/网页后界面自动让位（隐藏悬浮窗），喊唤醒词再叫回来。"""
        if not is_ui_hidden():
            print("[UI] 已打开目标，界面自动让位隐藏")
            toggle_ui_hidden()

    session.on_open_action = _step_aside
    tts = TextToSpeech()
    detector = WakeWordDetector()
    try:
        stt.warmup()   # 预加载 ASR 模型：首次识别零等待
        with AudioStream() as stream:
            _greet(tts, bridge, stream)
            while not stop_event.is_set():
                if pause_event.is_set():
                    stream.drain()   # 暂停期间持续清空音频，避免积压
                    time.sleep(0.5)
                    continue
                bridge.push({"type": "state", "state": "idle"})
                trigger = wait_for_trigger(stream, detector, stop_event, pause_event)
                if trigger is None:
                    continue
                _kind, preroll = trigger
                if is_ui_hidden():
                    toggle_ui_hidden()   # 界面隐藏时被唤醒 → 自动恢复
                bridge.push({"type": "state", "state": "listening"})   # 直接进聆听态，不再闪"回复中"
                play_audio(config.CHIME_PATH)   # 短提示音（0.3s），别吞用户开头的话
                audio = record_command(stream, stop_event, bridge, preroll)
                if audio is None:
                    continue
                bridge.push({"type": "state", "state": "thinking"})
                wav = save_wav(audio)
                t0 = time.time()
                text = stt.transcribe(wav)
                if not text:
                    tts.speak("抱歉，没听清，请再说一次")
                    continue
                text = _strip_wake_words(text)
                if not re.search(r"[A-Za-z0-9一-鿿]", text):   # 纯标点=没听清
                    tts.speak("抱歉，没听清，请再说一次")
                    continue
                print(f"识别结果（用时 {time.time() - t0:.1f}s）：{text}")
                bridge.push({"type": "message", "role": "user", "text": text})
                bridge.push({"type": "state", "state": "thinking"})

                # ---- 流式对话：逐块上屏（打字机），按句并行播报 ----
                tts_q: queue.Queue = queue.Queue()

                def _tts_worker():
                    while True:
                        sentence = tts_q.get()
                        if sentence is None:
                            return
                        bridge.push({"type": "state", "state": "speaking"})
                        if tts.speak(sentence, stop_check=lambda: keyboard.is_pressed("space")):
                            session.interrupt()   # 打断播报 → 同时掐断还在生成的回复
                            return

                worker = threading.Thread(target=_tts_worker, daemon=True)
                worker.start()
                pending = ""
                replied_first = False

                def _on_delta(dt: str):
                    nonlocal pending, replied_first
                    if not replied_first:
                        replied_first = True
                        bridge.push({"type": "state", "state": "speaking"})   # 首块回复 → 切「回复中」视觉
                    bridge.push({"type": "chunk", "text": dt})   # UI 打字机增量
                    pending += dt
                    m = _SENTENCE_RE.match(pending)
                    while m:                       # 完整句 → 交 TTS 线程播报
                        tts_q.put(m.group(0))
                        pending = pending[m.end():]
                        m = _SENTENCE_RE.match(pending)

                reply = session.run(
                    text, _on_delta,
                    stop_check=lambda: keyboard.is_pressed("space"),   # 空格打断生成
                )
                if not session.was_aborted and pending.strip():
                    tts_q.put(pending)             # 尾部不成句的文本也播
                tts_q.put(None)
                worker.join()   # 等 TTS 全部播完再回待机，避免把播报声录进下一轮
                print(f"JARVIS 回复：\n{reply}")
                bridge.push({"type": "state", "state": "idle"})
                if session.exit_requested:
                    print("[Exit] 用户要求退出，本轮播报已完成，正在退出 ...")
                    bridge.push({"type": "quit"})
                    stop_event.set()
                    _stop_tray()
                    close_ui()   # 原生关窗：JS window.close() 会被 WebView2 拦截
                elif session.hide_requested and not is_ui_hidden():
                    print("[UI] 用户要求隐藏界面，本轮播报已完成")
                    toggle_ui_hidden()
                print("-" * 40)
    finally:
        tts.stop()


def _register_hotkeys(bridge: UiBridge, stop_event: threading.Event) -> None:
    """全局退出热键（注册在 main：UI 挂掉也生效）。

    Ctrl+Alt+Q        优雅退出（发 quit 事件让窗口关闭，正常收尾）
    Ctrl+Alt+Shift+Q  强制退出（os._exit 立即终止进程，兜底用）
    注意：不能用 Ctrl+Shift 开头——中文 Windows 会被输入法切换拦截。
    """
    try:
        def _graceful():
            bridge.push({"type": "quit"})
            stop_event.set()
            _stop_tray()
            close_ui()   # 原生关窗：JS window.close() 会被 WebView2 拦截

        keyboard.add_hotkey("ctrl+alt+q", _graceful)
        keyboard.add_hotkey("ctrl+alt+m", lambda: toggle_ui_hidden())
        keyboard.add_hotkey("ctrl+alt+shift+q", lambda: os._exit(0))
        print("[Hotkey] Ctrl+Alt+Q 退出 / Ctrl+Alt+M 隐藏界面 / Ctrl+Alt+Shift+Q 强制退出")
        keyboard.wait()
    except Exception as e:
        print(f"[Hotkey] 全局热键注册失败（{e}），可用托盘退出")


def main() -> None:
    if not _singleton():
        return
    device = sd.query_devices(kind="input")
    print(f"当前麦克风: {device['name']}")
    print(f"=== {config.WAKE_WORD}语音助手 ===")
    print("喊「贾维斯」或按空格唤醒；托盘图标可暂停/退出。\n")
    stop_event = threading.Event()
    pause_event = threading.Event()
    bridge = UiBridge()
    threading.Thread(target=_register_hotkeys, args=(bridge, stop_event), daemon=True).start()
    worker = threading.Thread(target=voice_loop, args=(stop_event, pause_event, bridge), daemon=True)
    worker.start()
    if config.UI_ENABLED:
        global _TRAY_ICON
        _TRAY_ICON = run_tray_detached(stop_event, pause_event, bridge)
        try:
            run_ui(bridge, stop_event)   # 阻塞主线程，窗口关闭后返回
        except Exception as e:
            if stop_event.is_set():
                return   # 正在退出流程中（窗口被 close_ui 关掉），不要复活
            print(f"[UI] 悬浮窗启动失败（{e}），退回纯托盘模式")
            stop_event.clear()
            run_tray(stop_event, pause_event, bridge)   # 阻塞
    else:
        run_tray(stop_event, pause_event, bridge)   # 阻塞
    worker.join(timeout=5)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n已退出")
