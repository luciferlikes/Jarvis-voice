"""唤醒词冒烟测试：监听 10 秒，打印识别到的 partial 文本，命中关键词即报告。

配合外部播放"贾维斯"的声音使用。
用法：.venv/Scripts/python scripts/test_wake.py
"""
import json
import os
import sys
import time

import numpy as np
import sounddevice as sd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import vosk  # noqa: E402

import config  # noqa: E402

CHUNK = 1280
DURATION = 10

model = vosk.Model(config.WAKE_MODEL_PATH)
rec = vosk.KaldiRecognizer(model, config.SAMPLE_RATE)
q = []


def callback(indata, _frames, _time_info, _status):
    q.append(indata.copy())


with sd.InputStream(
    samplerate=config.SAMPLE_RATE, channels=1, dtype="float32", blocksize=CHUNK, callback=callback
):
    start = time.time()
    print("监听中 10 秒，请播放「贾维斯」声音 ...")
    while time.time() - start < DURATION:
        while q:
            chunk = q.pop(0)
            pcm = (chunk.flatten() * 32767).astype(np.int16).tobytes()
            rec.AcceptWaveform(pcm)
            partial = json.loads(rec.PartialResult()).get("partial", "")
            if partial:
                hit = any(k in partial for k in config.WAKE_KEYWORDS)
                print(f"{time.time() - start:.1f}s  partial={partial}  {'★ 触发！' if hit else ''}")
        time.sleep(0.02)
print("done")
