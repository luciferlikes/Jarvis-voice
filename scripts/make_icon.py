"""生成托盘图标 icon.png：钢铁侠弧反应堆风格的青色圆环。"""
import os

from PIL import Image, ImageDraw

SIZE = 128
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "icon.png")


def main() -> None:
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    cx = cy = SIZE / 2
    # 深色底盘
    d.ellipse([cx - 52, cy - 52, cx + 52, cy + 52], fill=(8, 16, 32, 235))
    # 内圈发光环
    d.ellipse([cx - 44, cy - 44, cx + 44, cy + 44], outline=(0, 229, 255, 180), width=3)
    # 外圈亮环
    d.ellipse([cx - 54, cy - 54, cx + 54, cy + 54], outline=(0, 229, 255, 255), width=5)
    # 中心核心（亮斑）
    d.ellipse([cx - 14, cy - 14, cx + 14, cy + 14], fill=(0, 229, 255, 255))
    d.ellipse([cx - 6, cy - 6, cx + 6, cy + 6], fill=(240, 255, 255, 255))
    img.save(OUT)
    print(f"图标已生成：{OUT}")


if __name__ == "__main__":
    main()
