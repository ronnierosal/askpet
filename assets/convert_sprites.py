"""One-time dev tool: convert kogi WebP spritesheet to PNG for Tkinter.

Tkinter PhotoImage reads PNG but not WebP, and Windows transparency uses a
color key, so alpha is flattened: transparent -> key color, partial alpha
thresholded. Runtime app stays stdlib-only; Pillow is only needed here.

Outputs:
  kogi/spritesheet.png   - full sheet, alpha flattened onto key color
  kogi/preview-rows.png  - downscaled contact sheet with row numbers (for inspection)
"""
from PIL import Image, ImageDraw

KEY = (254, 0, 254)  # magenta color key, matches '#fe00fe' in the app
CELL_W, CELL_H = 192, 208

src = Image.open("kogi/spritesheet.webp").convert("RGBA")
print("atlas size:", src.size)

flat = Image.new("RGB", src.size, KEY)
mask = src.getchannel("A").point(lambda a: 255 if a >= 96 else 0)
flat.paste(src.convert("RGB"), (0, 0), mask)
flat.save("kogi/spritesheet.png", optimize=True)
print("wrote kogi/spritesheet.png")

cols = src.width // CELL_W
rows = src.height // CELL_H
print(f"grid: {cols} cols x {rows} rows")

preview = flat.resize((src.width // 3, src.height // 3))
d = ImageDraw.Draw(preview)
for r in range(rows):
    y = r * (CELL_H // 3)
    d.line([(0, y), (preview.width, y)], fill=(0, 0, 0), width=1)
    d.text((4, y + 4), f"row {r}", fill=(0, 0, 0))
preview.save("kogi/preview-rows.png")
print("wrote kogi/preview-rows.png")
