"""唤醒词检测：中英文双路——

- 中文路：Vosk 实时转写，匹配「贾维斯」（含同音字），模型由 scripts/download_vosk_model.py 下载
- 英文路：openWakeWord 的 hey_jarvis 声学模型（喊 "Jarvis" / "Hey Jarvis" 触发）
"""
import json

import numpy as np
import vosk
from openwakeword.model import Model

import config


class WakeWordDetector:
    """喂 80ms 音频帧，两路任一路命中即触发。"""

    def __init__(self):
        model = vosk.Model(config.WAKE_MODEL_PATH)
        self._rec = vosk.KaldiRecognizer(model, config.SAMPLE_RATE)
        self._rec.SetWords(False)
        self._ow = Model(wakeword_models=[config.WAKE_MODEL_EN], inference_framework="onnx")
        self._ow_threshold = config.WAKE_THRESHOLD_EN
        self._ow_error_logged = False

    def reset(self) -> None:
        """清空中文识别状态，防止上一轮的「贾维斯」残留导致重复触发。"""
        self._rec.Reset()

    def detect(self, chunk: np.ndarray) -> bool:
        """chunk：float32，长度 1280（80ms @ 16kHz）。

        中英两路各自隔离：任一路崩溃只跳过该路，不拖垮语音主循环。
        """
        flat = chunk.flatten()[:1280]
        # 中文路：vosk 关键词
        try:
            pcm = (flat * 32767).astype(np.int16).tobytes()
            self._rec.AcceptWaveform(pcm)
            partial = json.loads(self._rec.PartialResult()).get("partial", "")
            if any(k in partial for k in config.WAKE_KEYWORDS):
                return True
        except Exception as e:
            print(f"[Wake] 中文路异常（已跳过）：{e}")
        # 英文路：openWakeWord hey_jarvis
        # （openwakeword 0.5.1 在 numpy 2.x 下有 vstack 崩溃 bug，只记录一次）
        try:
            prediction = self._ow.predict(np.expand_dims(flat, 0))
            score = max(v[0] if isinstance(v, np.ndarray) else v for v in prediction.values())
            return score > self._ow_threshold
        except Exception as e:
            if not self._ow_error_logged:
                print(f"[Wake] 英文路异常（已跳过，仅中文路生效）：{e}")
                self._ow_error_logged = True
            return False
