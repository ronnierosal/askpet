"""Normalize raw ChatGPT pixel-art exports into game-ready Eldermark assets.

Drop raw PNGs into assets/eldermark/raw/ using these base names:
    mosslight_gate_bg.png    (background, any size ~3:2)
    hero_down.png hero_up.png hero_right.png    (sprites on solid magenta #fe00fe)
    mossback.png             (sprite on solid magenta #fe00fe)
Then run:   python tools/prep_eldermark_art.py
Outputs normalized PNGs into assets/eldermark/ (hero_left is auto-mirrored).

This is a build-time tool only and needs Pillow (pip install pillow). The game
itself never imports PIL.
"""
import sys
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    sys.exit("This tool needs Pillow:  pip install pillow")

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "assets" / "eldermark" / "raw"
OUT = ROOT / "assets" / "eldermark"

GREENS = [(0x0f, 0x38, 0x0f), (0x30, 0x62, 0x30),
          (0x8b, 0xac, 0x0f), (0x9b, 0xbc, 0x0f)]   # dark -> light
KEY = (0xfe, 0x00, 0xfe)                            # magenta -> transparent

BG_SIZE = (720, 480)
SPRITE_H = {"hero_down": 128, "hero_up": 128, "hero_right": 128,
            "mossback": 140, "gloomling": 150, "thistlewisp": 140,
            "hedge_pixie": 150, "mire_warden": 168}
BACKGROUNDS = ("mosslight_gate_bg.png", "battle_bg.png", "whisperwood_bg.png")
SPRITES = ("hero_down", "hero_up", "hero_right", "mossback", "gloomling",
           "thistlewisp", "hedge_pixie", "mire_warden")


def _nearest_green(r, g, b):
    lum = 0.299 * r + 0.587 * g + 0.114 * b
    return GREENS[min(3, max(0, int(lum // 64)))]


def quantize(img, keep_alpha):
    """Snap every pixel to the 4-green palette (drop near-transparent ones)."""
    img = img.convert("RGBA")
    px = img.load()
    w, h = img.size
    for y in range(h):
        for x in range(w):
            r, g, b, a = px[x, y]
            if keep_alpha and a < 24:
                px[x, y] = (0, 0, 0, 0)
                continue
            nr, ng, nb = _nearest_green(r, g, b)
            px[x, y] = (nr, ng, nb, 255)
    return img


def key_to_alpha(img, tol=70):
    """Make magenta-ish pixels fully transparent."""
    img = img.convert("RGBA")
    px = img.load()
    w, h = img.size
    for y in range(h):
        for x in range(w):
            r, g, b, a = px[x, y]
            if r > 255 - tol and g < tol and b > 255 - tol:
                px[x, y] = (0, 0, 0, 0)
    return img


def autocrop(img):
    bbox = img.split()[-1].getbbox()       # crop to the alpha bounding box
    return img.crop(bbox) if bbox else img


def resize_h(img, target_h):
    w, h = img.size
    nw = max(1, round(w * target_h / h))
    return img.resize((nw, target_h), Image.NEAREST)


def do_bg(name):
    src = RAW / name
    if not src.exists():
        return False
    img = Image.open(src).convert("RGB").resize(BG_SIZE, Image.LANCZOS)
    img = quantize(img, keep_alpha=False).convert("RGB")
    img.save(OUT / name)
    print(f"  bg   {name}  -> {BG_SIZE[0]}x{BG_SIZE[1]}")
    return True


def do_sprite(base):
    src = RAW / f"{base}.png"
    if not src.exists():
        return None
    img = key_to_alpha(Image.open(src))
    img = quantize(img, keep_alpha=True)
    img = resize_h(autocrop(img), SPRITE_H.get(base, 128))
    img.save(OUT / f"{base}.png")
    print(f"  spr  {base}.png  -> {img.size[0]}x{img.size[1]}")
    return img


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    RAW.mkdir(parents=True, exist_ok=True)
    did = False
    for bg in BACKGROUNDS:
        did |= do_bg(bg)
    right = None
    for base in SPRITES:
        img = do_sprite(base)
        if base == "hero_right" and img is not None:
            right = img
    if right is not None:                  # left facing = mirrored right
        right.transpose(Image.FLIP_LEFT_RIGHT).save(OUT / "hero_left.png")
        print("  spr  hero_left.png  (mirrored from hero_right)")
        did = True
    if not did:
        print(f"No raw art found in {RAW}")
    else:
        print(f"Done. Normalized art written to {OUT}")
        print("Remember to add --add-data lines for the new PNGs (see README).")


if __name__ == "__main__":
    main()
