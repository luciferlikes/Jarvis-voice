"""下载 Vosk 中文模型（alphacephei.com 官方源），用于唤醒词检测。

用法：.venv/Scripts/python scripts/download_vosk_model.py
"""
import io
import os
import zipfile

import requests

URL = "https://alphacephei.com/vosk/models/vosk-model-small-cn-0.22.zip"
TARGET_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "models"
)


def main() -> None:
    os.makedirs(TARGET_DIR, exist_ok=True)
    print("[down] vosk-model-small-cn-0.22.zip (~42MB) ...")
    with requests.get(URL, stream=True, timeout=60) as r:
        r.raise_for_status()
        buf = io.BytesIO()
        for chunk in r.iter_content(1024 * 1024):
            buf.write(chunk)
        print(f"[ ok ] 已下载 {buf.tell() / 1e6:.1f} MB，解压中 ...")
        with zipfile.ZipFile(buf) as z:
            z.extractall(TARGET_DIR)
    print(f"模型就绪：{os.path.join(TARGET_DIR, 'vosk-model-small-cn-0.22')}")


if __name__ == "__main__":
    main()
