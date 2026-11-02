"""Génère les icônes de QuakePad (Windows .ico/.png + extension Chrome).

Usage : python tools/make_icons.py   (nécessite Pillow)
"""
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
BG, ACCENT, LINE = (17, 19, 24, 255), (240, 167, 66, 255), (214, 219, 228, 255)


def draw(size: int) -> Image.Image:
    s = size * 4  # sur-échantillonnage pour un rendu net
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    r = int(s * 0.2)
    d.rounded_rectangle((0, 0, s - 1, s - 1), r, fill=BG)
    # bandeau supérieur ambre : la console qui « descend » du haut
    mask = Image.new("L", (s, s), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, s - 1, s - 1), r, fill=255)
    band = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    ImageDraw.Draw(band).rectangle((0, 0, s, int(s * 0.2)), fill=ACCENT)
    img.paste(band, (0, 0), Image.composite(band, Image.new("RGBA", (s, s)), mask).split()[3])
    # chevron « > » + lignes de texte
    m, lw = int(s * 0.17), max(4, int(s * 0.065))
    y0 = int(s * 0.36)
    d.line([(m, y0), (m + int(s * 0.12), y0 + int(s * 0.1)), (m, y0 + int(s * 0.2))], fill=ACCENT, width=lw, joint="curve")
    # (x de départ, y, x de fin) en fraction de la taille
    for xs, yf, xe in ((0.37, 0.46, 0.80), (0.17, 0.66, 0.62), (0.17, 0.80, 0.74)):
        y = int(s * yf)
        d.rounded_rectangle((int(s * xs), y - lw // 2, int(s * xe), y + lw // 2), lw // 2, fill=LINE)
    return img.resize((size, size), Image.LANCZOS)


def main() -> None:
    win_assets = ROOT / "windows" / "assets"
    ext_icons = ROOT / "chrome-extension" / "icons"
    win_assets.mkdir(parents=True, exist_ok=True)
    ext_icons.mkdir(parents=True, exist_ok=True)
    big = draw(256)
    big.save(win_assets / "quakepad.png")
    big.save(win_assets / "quakepad.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    for n in (16, 32, 48, 128):
        draw(n).save(ext_icons / f"icon{n}.png")
    print("Icônes générées.")


if __name__ == "__main__":
    main()
