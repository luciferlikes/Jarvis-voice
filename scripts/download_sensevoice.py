"""下载 SenseVoice 模型（约 230MB）到 models/sense-voice/。

用法：.venv/Scripts/python scripts/download_sensevoice.py
来源：ModelScope 国内 CDN（github/hf-mirror 国际线路慢时用这个）。
文件：model_q8.onnx + tokens.txt。
"""
import os
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config  # noqa: E402

BASE = "https://modelscope.cn/models/xiaowangge/sherpa-onnx-sense-voice-small/resolve/master"
FILES = {
    "model_q8.onnx": f"{BASE}/model_q8.onnx",     # Q8 量化，约 229MB
    "tokens.txt": f"{BASE}/tokens.txt",
}
TARGET = config.SENSEVOICE_MODEL_DIR


def download(url: str, dest: str, max_retries: int = 10) -> None:
    """带断点续传的下载：连接中断后从已下载位置继续。"""
    for attempt in range(max_retries):
        try:
            exist = os.path.getsize(dest) if os.path.isfile(dest) else 0
            req = urllib.request.Request(url)
            if exist:
                req.add_header("Range", f"bytes={exist}-")
            with urllib.request.urlopen(req, timeout=30) as r, open(dest, "ab") as f:
                total = int(r.headers.get("Content-Length", 0)) + exist
                done = exist
                while True:
                    chunk = r.read(1 << 20)
                    if not chunk:
                        break
                    f.write(chunk)
                    done += len(chunk)
                    if total:
                        print(f"\r下载中 {done / 1048576:.0f}/{total / 1048576:.0f} MB",
                              end="", flush=True)
            print()
            return
        except Exception as e:
            print(f"\n[!] 第 {attempt + 1} 次下载中断：{e}，续传重试 ...")
    raise RuntimeError(f"下载失败（已重试 {max_retries} 次）：{url}")


def main() -> None:
    os.makedirs(TARGET, exist_ok=True)
    for name, url in FILES.items():
        dest = os.path.join(TARGET, name)
        if os.path.isfile(dest):
            print(f"已存在：{dest}")
            continue
        print(f"下载 {name} → {dest}")
        download(url, dest)
    print(f"完成：{TARGET}")


if __name__ == "__main__":
    main()
