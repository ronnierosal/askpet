"""Normalize raw ChatGPT black-and-white manga art into Spirit-Beast Blades assets.

Drop raw PNGs into assets/spinstory/raw/ using these base names:
    backgrounds (~3:2, any size):  arena_bg.png  training_bg.png  finals_bg.png
                                   (optional extras: crowd / gate / sky / podium)
    characters  (on solid magenta #fe00fe), <name>_<expression>.png:
        kael_*   with neutral/smug/fierce/shocked
        mira_*   with neutral/cool/fierce/shocked
        brakk_*  with neutral/grin/fierce/shocked
        mentor_* with neutral/smile
Then run:  python tools/prep_spin_art.py
Outputs normalized GRAYSCALE PNGs into assets/spinstory/. Names not listed in
BACKGROUNDS/SPRITES below are ignored — add new ones there to process them.

Build-time tool only; needs Pillow (pip install pillow). The game never imports PIL.
"""
import sys
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    sys.exit("This tool needs Pillow:  pip install pillow")

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "assets" / "spinstory" / "raw"
OUT = ROOT / "assets" / "spinstory"
KEY = (0xfe, 0x00, 0xfe)            # magenta -> transparent
BG_SIZE = (720, 480)
SPRITE_H = 300
BACKGROUNDS = ("arena_bg.png", "training_bg.png", "finals_bg.png",
               "clash_bg.png", "launch_bg.png", "spirit_bg.png",          # action scenes
               "crowd_bg.png", "gate_bg.png", "sky_bg.png", "podium_bg.png")
SPRITES = ("kael_neutral", "kael_smug", "kael_fierce", "kael_shocked",
           "mira_neutral", "mira_cool", "mira_fierce", "mira_shocked",
           "brakk_neutral", "brakk_grin", "brakk_fierce", "brakk_shocked",
           "mentor_neutral", "mentor_smile",
           "raze_masked", "raze_cold", "raze_shocked",                   # the Masked Ace
           "sign_focus", "sign_burst",                                   # spirit-weaving hand signs
           "top_hero", "top_kael", "top_mira", "top_brakk")              # spirit-beast tops


def key_to_alpha(img, tol=70):
    img = img.convert("RGBA")
    px = img.load()
    w, h = img.size
    for y in range(h):
        for x in range(w):
            r, g, b, a = px[x, y]
            if r > 255 - tol and g < tol and b > 255 - tol:
                px[x, y] = (0, 0, 0, 0)
    return img


def grayscale_rgba(img):
    img = img.convert("RGBA")
    a = img.split()[-1]
    lum = img.convert("L")
    return Image.merge("RGBA", (lum, lum, lum, a))


def autocrop(img):
    bbox = img.split()[-1].getbbox()
    return img.crop(bbox) if bbox else img


def resize_h(img, target_h):
    w, h = img.size
    return img.resize((max(1, round(w * target_h / h)), target_h), Image.NEAREST)


def do_bg(name):
    src = RAW / name
    if not src.exists():
        return False
    img = Image.open(src).convert("L").convert("RGB").resize(BG_SIZE, Image.LANCZOS)
    img.save(OUT / name)
    print(f"  bg   {name}  -> {BG_SIZE[0]}x{BG_SIZE[1]} (grayscale)")
    return True


def do_sprite(base):
    src = RAW / f"{base}.png"
    if not src.exists():
        return False
    img = grayscale_rgba(key_to_alpha(Image.open(src)))
    img = resize_h(autocrop(img), SPRITE_H)
    img.save(OUT / f"{base}.png")
    print(f"  spr  {base}.png  -> {img.size[0]}x{img.size[1]} (B&W, keyed)")
    return True


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    RAW.mkdir(parents=True, exist_ok=True)
    did = False
    for bg in BACKGROUNDS:
        did |= do_bg(bg)
    for base in SPRITES:
        did |= do_sprite(base)
    print("Done. Normalized art written to " + str(OUT) if did
          else "No raw art found in " + str(RAW))


if __name__ == "__main__":
    main()
