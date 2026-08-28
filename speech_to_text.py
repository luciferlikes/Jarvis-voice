"""语音转文字：sherpa-onnx + SenseVoice 本地识别，自动判断中英文（含粤/日/韩）。

替代原 faster-whisper 方案：中文错误率约 1/2.5、CPU 快 5 倍以上。
模型由 scripts/download_sensevoice.py 下载到 models/sense-voice/。
"""
import os
import wave

import numpy as np
import sherpa_onnx

import config


def _resample(samples: np.ndarray, src_rate: int, dst_rate: int) -> np.ndarray:
    """线性插值重采样到 16kHz（SenseVoice 的输入要求）。"""
    n_out = int(len(samples) * dst_rate / src_rate)
    x = np.linspace(0.0, len(samples) - 1, n_out)
    return np.interp(x, np.arange(len(samples)), samples).astype(np.float32)


class SpeechToText:
    """懒加载 SenseVoice 模型，避免程序启动时卡顿。"""

    def __init__(self):
        self._recognizer = None

    def _load_model(self):
        if self._recognizer is not None:
            return self._recognizer
        model_dir = config.SENSEVOICE_MODEL_DIR
        tokens = os.path.join(model_dir, "tokens.txt")
        # 兼容多种量化格式：社区 q8 或官方 int8/fp32
        candidates = ["model_q8.onnx", "model.int8.onnx", "model.onnx"]
        model = next((os.path.join(model_dir, c) for c in candidates
                      if os.path.isfile(os.path.join(model_dir, c))), None)
        if model is None or not os.path.isfile(tokens):
            raise FileNotFoundError(
                f"SenseVoice 模型文件缺失：{model_dir}"
                "（请运行 scripts/download_sensevoice.py 下载）"
            )
        print(f"[ASR] 加载本地 SenseVoice 模型 {os.path.basename(model)} ...")
        # language="auto"：自动判断中/英/粤/日/韩——中英混说场景无需切换
        self._recognizer = sherpa_onnx.OfflineRecognizer.from_sense_voice(
            model=model,
            tokens=tokens,
            use_itn=True,                       # 数字/日期/百分比等转成规范写法
            language=config.SENSEVOICE_LANGUAGE,
            num_threads=4,
            provider="cpu",
            debug=False,
        )
        print("[ASR] 模型加载完成")
        return self._recognizer

    def warmup(self) -> None:
        """预加载模型：启动时调用，避免首次识别时才加载造成卡顿。"""
        self._load_model()

    def transcribe(self, audio_path: str) -> str:
        """转写 WAV 文件，返回文本（16kHz 单声道；其他采样率自动重采样）。"""
        recognizer = self._load_model()
        with wave.open(audio_path, "rb") as f:
            src_rate = f.getframerate()
            samples = (np.frombuffer(f.readframes(f.getnframes()), dtype=np.int16)
                       .astype(np.float32) / 32768.0)
        if src_rate != 16000:
            samples = _resample(samples, src_rate, 16000)
        stream = recognizer.create_stream()
        stream.accept_waveform(16000, samples)
        recognizer.decode_stream(stream)
        return stream.result.text.strip()
