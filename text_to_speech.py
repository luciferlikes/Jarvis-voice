"""语音播报：edge-tts 在线神经语音，按文本自动挑中文/英文声线。

中文用云健、英文用英伦男声（气质接近贾维斯）；edge-tts 失败时回退 pyttsx3 离线语音。
支持打断：stop_check() 返回 True 时立即停止当前播报（空格打断）。
按句合成+播报：第一句合成完就开始念，边念边合成后续句子，缩短等待。
"""
import asyncio
import ctypes
import os
import re
import threading
import time

import edge_tts
import pyttsx3

import config


_alias_seq = 0


def play_audio(path: str, stop_check=None) -> bool:
    """播放音频（wav/mp3）：miniaudio 解码 + sounddevice（WASAPI）播放。

    与浏览器/播放器走同一音频栈。MCI 老通道在麦克风流活跃时会被
    Nahimic 镜像吞掉（返回码正常但不发声），仅作 ImportError 兜底。
    stop_check 返回 True 立即中断；返回 True=被中断，False=播完。
    """
    t0 = time.time()
    try:
        import miniaudio
        import numpy as np
        import sounddevice as sd

        audio = miniaudio.decode_file(path, output_format=miniaudio.SampleFormat.FLOAT32)
        pcm = np.array(audio.samples, dtype=np.float32)
        if audio.nchannels > 1:
            pcm = pcm.reshape(-1, audio.nchannels)
        # 显式 OutputStream + 分块写入：比 sd.play 在后台线程更可靠，且块间可打断
        stream = sd.OutputStream(samplerate=audio.sample_rate,
                                 channels=audio.nchannels, dtype="float32")
        stream.start()
        try:
            chunk = max(1, int(audio.sample_rate * 0.2))
            pos = 0
            while pos < len(pcm):
                if stop_check and stop_check():
                    print(f"[TTS] 播放被打断（{time.time() - t0:.1f}s）：{os.path.basename(path)}")
                    return True
                if time.time() - t0 > 120:   # 播放看门狗：防挂死
                    print(f"[TTS] 播放超时（>120s），强制停止：{os.path.basename(path)}")
                    return True
                stream.write(pcm[pos:pos + chunk])
                pos += chunk
        finally:
            stream.stop()
            stream.close()
        print(f"[TTS] 播放完成（{time.time() - t0:.1f}s）：{os.path.basename(path)}")
        return False
    except ImportError:
        return _play_mci(path, stop_check)


def _play_mci(path: str, stop_check=None) -> bool:
    """MCI（winmm）兜底播放。别名带序号避免并发冲突；60s 看门狗。"""
    global _alias_seq
    _alias_seq += 1
    winmm = ctypes.windll.winmm
    alias = f"jarvis_tts_{os.getpid()}_{_alias_seq}"
    path = os.path.abspath(path).replace("/", "\\")
    t0 = time.time()
    r = winmm.mciSendStringW(f'open "{path}" type mpegvideo alias {alias}', None, 0, None)
    if r:
        raise RuntimeError(f"MCI open 失败（错误码 {r}）：{path}")
    interrupted = False

    def _play():
        winmm.mciSendStringW(f"play {alias} wait", None, 0, None)

    thread = threading.Thread(target=_play, daemon=True)
    thread.start()
    try:
        while thread.is_alive():
            if stop_check and stop_check():
                winmm.mciSendStringW(f"stop {alias}", None, 0, None)
                interrupted = True
                break
            if time.time() - t0 > 60:
                print(f"[TTS] MCI 播放超时（>60s），强制停止：{os.path.basename(path)}")
                winmm.mciSendStringW(f"stop {alias}", None, 0, None)
                interrupted = True
                break
            time.sleep(0.05)
        thread.join(timeout=2)
    finally:
        winmm.mciSendStringW(f"close {alias}", None, 0, None)
    print(f"[TTS] MCI 播放完成（{time.time() - t0:.1f}s）：{os.path.basename(path)}")
    return interrupted


class TextToSpeech:
    def __init__(self):
        self._fallback = None   # pyttsx3 离线引擎，需要时才初始化

    def speak(self, text: str, stop_check=None) -> bool:
        """按句合成+播报；stop_check() 返回 True 时中断。返回是否被中断。"""
        text = self._clean(text.strip())
        if not text:
            return False
        if len(text) > config.TTS_MAX_CHARS:
            text = text[: config.TTS_MAX_CHARS] + "。以上是回复的前半部分。"
        voice = config.TTS_VOICE_ZH if self._is_mostly_chinese(text) else config.TTS_VOICE_EN
        print(f"[TTS] 播报中 ...（{voice}）")
        path = os.path.join(config.BASE_DIR, "tts_reply.mp3")
        try:
            for sentence in self._split_sentences(text):
                asyncio.run(self._synth(sentence, voice, path))
                if play_audio(path, stop_check):
                    print("[TTS] 播报被用户打断")
                    return True
            return False
        except Exception as e:
            print(f"[TTS] edge-tts 失败（{e}），回退本地语音")
            self._speak_fallback(text)
            return False

    async def _synth(self, text: str, voice: str, path: str) -> None:
        # 微软接口偶尔限流（NoAudioReceived），重试两次；每次带超时防连接挂死
        for attempt in range(3):
            try:
                await asyncio.wait_for(
                    edge_tts.Communicate(text, voice, rate=config.TTS_EDGE_RATE).save(path),
                    timeout=25,
                )
                return
            except Exception:
                if attempt == 2:
                    raise
                await asyncio.sleep(1.5)

    # ---- pyttsx3 离线兜底 ----
    def _speak_fallback(self, text: str) -> None:
        if self._fallback is None:
            self._fallback = pyttsx3.init()
            self._fallback.setProperty("rate", config.TTS_RATE)
            self._fallback.setProperty("voice", self._pick_sapi_voice())
        self._fallback.say(text)
        self._fallback.runAndWait()

    @staticmethod
    def _pick_sapi_voice() -> str | None:
        engine = pyttsx3.init()
        for v in engine.getProperty("voices"):
            if re.search(r"huihui", v.name, re.I):
                return v.id
        return None

    def stop(self) -> None:
        if self._fallback is not None:
            self._fallback.stop()

    # ---- 文本处理 ----
    @staticmethod
    def _is_mostly_chinese(text: str) -> bool:
        cjk = len(re.findall(r"[一-鿿]", text))
        return cjk / max(len(text), 1) > 0.2

    @staticmethod
    def _split_sentences(text: str) -> list[str]:
        """按中英文句末标点切句；无标点则按 60 字分段。"""
        parts = [s.strip() for s in re.split(r"(?<=[。！？!?；;])", text) if s.strip()]
        if not parts:
            return [text]
        merged = []
        buf = ""
        for p in parts:
            buf += p
            if len(buf) >= 60:
                merged.append(buf)
                buf = ""
        if buf:
            merged.append(buf)
        return merged

    @staticmethod
    def _clean(text: str) -> str:
        """去掉常见 Markdown 符号，念起来更自然。"""
        text = re.sub(r"```.*?```", "（代码省略）", text, flags=re.S)
        text = re.sub(r"[*#_`>|]", "", text)
        return text
