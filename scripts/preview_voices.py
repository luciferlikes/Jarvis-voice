"""声线试听：依次播放候选语音，帮助挑选贾维斯的声线。

用法：.venv/Scripts/python scripts/preview_voices.py
"""
import asyncio
import os
import sys
import time

import edge_tts

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from text_to_speech import play_audio  # noqa: E402

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CANDIDATES = [
    ("1号 云扬（新闻腔男声）", "zh-CN-YunyangNeural", "晚上好，先生。所有系统已就绪。"),
    ("2号 云健（浑厚男声）", "zh-CN-YunjianNeural", "晚上好，先生。所有系统已就绪。"),
    ("3号 云夏（少年感男声）", "zh-CN-YunxiaNeural", "晚上好，先生。所有系统已就绪。"),
    ("4号 晓晓（温柔女声）", "zh-CN-XiaoxiaoNeural", "晚上好，先生。所有系统已就绪。"),
]


async def synth(voice: str, text: str, path: str) -> None:
    # 微软接口偶尔限流（NoAudioReceived），重试两次
    for attempt in range(3):
        try:
            await edge_tts.Communicate(text, voice).save(path)
            return
        except Exception as e:
            print(f"      第{attempt + 1}次失败：{e}")
            await asyncio.sleep(2)
    raise RuntimeError(f"{voice} 三次尝试均失败")


def main() -> None:
    # 可选参数：只试听指定序号，如 python preview_voices.py 4 5
    picks = [int(a) for a in sys.argv[1:]]
    print("依次播放候选声线 ...")
    for i, (label, voice, text) in enumerate(CANDIDATES, start=1):
        if picks and i not in picks:
            continue
        path = os.path.join(BASE, "tts_preview.mp3")
        print(f"▶ {label}  {voice}")
        asyncio.run(synth(voice, text, path))
        play_audio(path)
        time.sleep(1)


if __name__ == "__main__":
    main()
