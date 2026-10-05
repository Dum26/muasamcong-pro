"""Tạo icon MuaSamCong đa kích thước, đồng bộ với bảng màu giao diện."""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


SIZE = 1024
PROJECT_ROOT = Path(__file__).resolve().parents[1]
NAVY = "#0B2239"
TEAL = "#078B82"
WHITE = "#FFFFFF"


def main() -> None:
    canvas = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)

    # Bóng và nền bo góc được vẽ ở độ phân giải lớn để các cỡ nhỏ vẫn sắc.
    draw.rounded_rectangle((70, 86, 970, 986), radius=210, fill=(11, 34, 57, 70))
    draw.rounded_rectangle((54, 54, 954, 954), radius=210, fill=TEAL)
    draw.rounded_rectangle((90, 90, 918, 918), radius=175, outline="#2BB3A8", width=12)

    font_path = Path("C:/Windows/Fonts/segoeuib.ttf")
    font = ImageFont.truetype(str(font_path), 540)
    bbox = draw.textbbox((0, 0), "M", font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]
    x = (SIZE - text_width) / 2 - bbox[0]
    y = (SIZE - text_height) / 2 - bbox[1] - 18
    draw.text((x, y), "M", font=font, fill=WHITE)

    canvas.save(PROJECT_ROOT / "app_icon.png")
    canvas.save(
        PROJECT_ROOT / "app_icon.ico",
        format="ICO",
        sizes=[(16, 16), (20, 20), (24, 24), (32, 32), (40, 40),
               (48, 48), (64, 64), (128, 128), (256, 256)],
    )


if __name__ == "__main__":
    main()
