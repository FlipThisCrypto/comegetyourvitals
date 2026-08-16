from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"
OUT = ROOT / "generated" / "client-character-concept-sheet.png"

ROSTERS = [
    [
        ("CLIENT_01", "MARA", "Copperband butterflyfish"),
        ("CLIENT_02", "DREW", "Oscar cichlid"),
        ("CLIENT_03", "SAM", "Moorish idol"),
        ("CLIENT_04", "QUINN", "Yellow-green boxfish"),
        ("CLIENT_05", "LEE", "Silver arowana"),
    ],
    [
        ("CLIENT_06", "AVERY", "Purple firefish"),
        ("CLIENT_07", "NICO", "California sheephead"),
        ("CLIENT_08", "JUNE", "Golden koi"),
        ("CLIENT_09", "TESS", "Sable sea catfish"),
        ("CLIENT_10", "CAL", "Lined seahorse"),
    ],
]


def font(name: str, size: int):
    try:
        return ImageFont.truetype(f"C:/Windows/Fonts/{name}", size)
    except OSError:
        return ImageFont.load_default()


def main():
    width = 2400
    label_w = 330
    image_w = width - label_w
    image_h = round(image_w * 2 / 3)
    header_h = 170
    sheet_header_h = 68
    gap = 36
    height = header_h + 2 * (sheet_header_h + image_h) + gap + 70
    canvas = Image.new("RGB", (width, height), "#071722")
    draw = ImageDraw.Draw(canvas)
    title = font("seguisb.ttf", 52)
    subtitle = font("segoeui.ttf", 25)
    heading = font("seguisb.ttf", 27)
    body = font("segoeui.ttf", 22)
    small = font("segoeui.ttf", 17)

    draw.text((58, 32), "COME GET YOUR VITALS — CLIENT CHARACTER SYSTEM", font=title, fill="#f2fbff")
    draw.text((60, 100), "Same fictional adult clients across DETOX → STABILIZING → RESIDENTIAL. Identity markers remain locked.", font=subtitle, fill="#9dd8e7")

    y = header_h
    for sheet_index, file_name in enumerate(["client-concept-sheet-a.png", "client-concept-sheet-b.png"]):
        draw.rectangle((0, y, width, y + sheet_header_h), fill="#0e2c3a")
        col_w = image_w / 3
        for idx, label in enumerate(["EARLY DETOX", "STABILIZING", "RESIDENTIAL"]):
            cx = label_w + idx * col_w + col_w / 2
            box = draw.textbbox((0, 0), label, font=heading)
            draw.text((cx - (box[2] - box[0]) / 2, y + 16), label, font=heading, fill=["#91a8b4", "#6ec5cf", "#f0d68b"][idx])
        y += sheet_header_h
        source = Image.open(ASSETS / file_name).convert("RGB").resize((image_w, image_h), Image.Resampling.LANCZOS)
        canvas.paste(source, (label_w, y))
        row_h = image_h / 5
        for row, (cid, name, species) in enumerate(ROSTERS[sheet_index]):
            y0 = y + int(row * row_h)
            y1 = y + int((row + 1) * row_h)
            if row % 2 == 0:
                draw.rectangle((0, y0, label_w, y1), fill="#0b2230")
            draw.text((34, y0 + 35), cid, font=heading, fill="#72d9ec")
            draw.text((34, y0 + 74), name, font=heading, fill="#ffffff")
            draw.multiline_text((34, y0 + 116), species, font=body, fill="#b8cbd3", spacing=5)
            draw.text((34, y1 - 34), "ADULT • FICTIONAL", font=small, fill="#698f9c")
            draw.line((label_w - 2, y0, width, y0), fill="#1a4c5c", width=2)
        y += image_h
        if sheet_index == 0:
            y += gap
    draw.text((60, height - 46), "Concept art: built-in image generation from canonical nurse-sheet style references; production labels rendered deterministically in code.", font=small, fill="#648b98")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(OUT, quality=95)
    print(OUT)


if __name__ == "__main__":
    main()
