"""生成唤醒提示音 chime.wav：短促的双音上行提示（科技感"叮"声）。

用法：.venv/Scripts/python scripts/make_chime.py
"""
import os
import wave

import numpy as np

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "chime.wav")


def main() -> None:
    sr = 22050
    dur = 0.28
    t = np.linspace(0, dur, int(sr * dur), endpoint=False)
    f1, f2 = 880.0, 1318.5            # A5 -> E6 上行双音
    signal = np.where(t < 0.13, np.sin(2 * np.pi * f1 * t), np.sin(2 * np.pi * f2 * t))
    env = np.minimum(1.0, t / 0.008) * np.exp(-t * 9)   # 快速起音 + 指数衰减
    audio = (signal * env * 0.45 * 32767).astype(np.int16)
    with wave.open(OUT, "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(sr)
        f.writeframes(audio.tobytes())
    print(f"提示音已生成：{OUT}")


if __name__ == "__main__":
    main()
