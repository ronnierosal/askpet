#!/usr/bin/env python3
"""Image -> monospace ASCII art for the AskPet game screens.

The technique (standard image-to-ASCII, the same idea behind real-time game
"ASCII shaders"): downscale the image to the target character grid, convert to
grayscale by luminosity, then map each cell's brightness to a character from a
density ramp. Monospace cells are ~2x taller than wide, so we squash vertically
to keep proportions.

This is a DEV-ONLY authoring tool (it uses Pillow). The shipped app stays
dependency-free — you paste the printed art into the game art constants in
askpet.py. The arcade screen is light-green on near-black, so by default a
BRIGHT source pixel becomes a DENSE/"lit" glyph (use --light-bg to flip it).

Usage:
  python tools/img2ascii.py image.png --width 46
  python tools/img2ascii.py image.png --width 40 --ramp fine
  python tools/img2ascii.py --demo            # no image needed; draws a sample
"""
import argparse

from PIL import Image, ImageDraw

# Density ramps, ordered DARK -> LIGHT (most ink first).
RAMPS = {
    "blocks": "@#%*+=:-. ",
    "classic": "@%#*+=-:. ",
    # Unicode block shades for a chunky pixel-art / anime-cel look (all
    # single-width in Consolas, so alignment holds): full -> light -> empty.
    "pixel": "█▓▒░ ",
    "fine": ("$@B%8&WM#*oahkbdpqwmZO0QLCJUYXzcvunxrjft/|()1{}[]?-_+~<>i!lI;:,"
             "\"^`. "),
}
CHAR_ASPECT = 0.5   # monospace cell height/width ~2:1 -> compress rows


def to_ascii(img, width=46, ramp="classic", dark_bg=True, gamma=1.0):
    chars = RAMPS.get(ramp, RAMPS["classic"])
    if dark_bg:                      # bright pixel -> dense glyph on a dark screen
        chars = chars[::-1]
    w, h = img.size
    rows = max(1, int(round(width * (h / w) * CHAR_ASPECT)))
    small = img.convert("L").resize((width, rows))
    px = small.load()
    n = len(chars) - 1
    lines = []
    for y in range(rows):
        line = []
        for x in range(width):
            v = (px[x, y] / 255.0) ** gamma
            line.append(chars[int(round(v * n))])
        lines.append("".join(line).rstrip())
    # trim fully-blank top/bottom rows
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    return "\n".join(lines)


def to_halfblock(img, width=46, dark_bg=True, thr=0.5):
    """HIGH-DETAIL mode: pack two vertical pixels per character using the upper/
    lower half blocks (▀▄█), doubling vertical resolution for a crisp 1-bit
    manga/anime look (like high-contrast black-and-white art). `thr` is the
    black/white cutoff (0..1). On our dark screen a BRIGHT pixel = lit block."""
    img = img.convert("L")
    w, h = img.size
    px_rows = max(2, int(round(width * (h / w))))      # square-ish pixels
    if px_rows % 2:
        px_rows += 1
    small = img.resize((width, px_rows))
    p = small.load()
    out = []
    for ry in range(0, px_rows, 2):
        line = []
        for x in range(width):
            top = p[x, ry] / 255.0
            bot = p[x, ry + 1] / 255.0 if ry + 1 < px_rows else 0.0
            if not dark_bg:                            # dark ink on light paper
                top, bot = 1 - top, 1 - bot
            t, b = top >= thr, bot >= thr
            line.append("█" if t and b else "▀" if t else "▄" if b else " ")
        out.append("".join(line).rstrip())
    while out and not out[0].strip():
        out.pop(0)
    while out and not out[-1].strip():
        out.pop()
    return "\n".join(out)


def as_python_literal(art, indent="    "):
    """Print the art as a paste-ready Python concatenated string literal."""
    rows = art.split("\n")
    out = []
    for i, r in enumerate(rows):
        esc = r.replace("\\", "\\\\").replace('"', '\\"')
        nl = "" if i == len(rows) - 1 else "\\n"
        out.append(f'{indent}"{esc}{nl}"')
    return "\n".join(out)


def _demo_image():
    """An original shaded sphere + spinning top, to show the gradient mapping."""
    im = Image.new("L", (240, 240), 0)
    d = ImageDraw.Draw(im)
    # radial-ish shaded sphere (light from top-left)
    cx, cy, r = 120, 95, 70
    for yy in range(cy - r, cy + r):
        for xx in range(cx - r, cx + r):
            dx, dy = (xx - cx) / r, (yy - cy) / r
            if dx * dx + dy * dy <= 1:
                # brightness falls off from the top-left highlight
                b = max(0.0, 1.0 - ((dx + 0.5) ** 2 + (dy + 0.5) ** 2) ** 0.5)
                im.putpixel((xx, yy), int(40 + b * 215))
    # a little stem/tip below it
    d.polygon([(105, 165), (135, 165), (120, 205)], fill=160)
    return im


def main():
    ap = argparse.ArgumentParser(description="Image -> monospace ASCII art")
    ap.add_argument("image", nargs="?", help="path to a PNG/JPG (omit with --demo)")
    ap.add_argument("--width", type=int, default=46, help="output width in chars")
    ap.add_argument("--ramp", default="classic", choices=list(RAMPS))
    ap.add_argument("--light-bg", action="store_true",
                    help="dark glyphs on a light background (default is the "
                         "arcade's light-on-dark)")
    ap.add_argument("--gamma", type=float, default=1.0,
                    help="<1 brightens mids, >1 darkens (default 1.0)")
    ap.add_argument("--demo", action="store_true", help="draw a sample image")
    ap.add_argument("--detail", action="store_true",
                    help="HIGH-DETAIL half-block 1-bit mode (best for converting "
                         "real anime/line art)")
    ap.add_argument("--thr", type=float, default=0.5,
                    help="black/white cutoff for --detail (0..1)")
    a = ap.parse_args()

    img = _demo_image() if a.demo else Image.open(a.image)
    if a.detail:
        art = to_halfblock(img, width=a.width, dark_bg=not a.light_bg, thr=a.thr)
    else:
        art = to_ascii(img, width=a.width, ramp=a.ramp, dark_bg=not a.light_bg,
                       gamma=a.gamma)
    print(art)
    print("\n# --- paste-ready Python literal -------------------------------")
    print(as_python_literal(art))


if __name__ == "__main__":
    main()
