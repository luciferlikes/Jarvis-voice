"""麦克风诊断：录 6 秒，每秒打印 RMS，验证麦克风真实收音。

配合外部播放声音使用（比如 TTS 播"贾维斯"），正常时对应秒的 RMS 会明显升高。
用法：.venv/Scripts/python scripts/test_mic.py
"""
import time

import numpy as np
import sounddevice as sd

print("输入设备：", sd.query_devices(kind="input")["name"])
q = []


def cb(indata, _frames, _time_info, _status):
    q.append((time.time(), indata.copy()))


with sd.InputStream(samplerate=16000, channels=1, dtype="float32", blocksize=1280, callback=cb):
    start = time.time()
    while time.time() - start < 6:
        time.sleep(0.05)

secs = {}
for t, chunk in q:
    sec = int(t - start)
    rms = float(np.sqrt(np.mean(chunk.flatten() ** 2)))
    secs.setdefault(sec, []).append(rms)
for sec in sorted(secs):
    print(f"第{sec}秒 RMS={np.mean(secs[sec]):.5f}")
