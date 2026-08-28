"""ASR 冒烟测试：转写 test_audio/ 下的合成语音，验证识别链路。
用法：.venv/Scripts/python scripts/test_asr.py
"""
import glob
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from speech_to_text import SpeechToText  # noqa: E402

AUDIO_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "test_audio")

stt = SpeechToText()
for wav in sorted(glob.glob(os.path.join(AUDIO_DIR, "*.wav"))):
    t0 = time.time()
    text = stt.transcribe(wav)
    print(f"{os.path.basename(wav)} -> {text}  ({time.time() - t0:.1f}s)")
