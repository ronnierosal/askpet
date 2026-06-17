# Spirit-Beast Blades — manga story art

Black-and-white manga art for the `/spinstory` visual-novel (`SpinMangaScreen`
in `askpet.py`).

## How it works
Each story beat shows a painted **background** (`arena_bg.png`) plus a
**character sprite with an expression** (`kael_<expr>.png`), with a code-drawn
manga speech box + choices on top. Missing files fall back to placeholders, so
it always runs. Canonical scene is **720x480**, palette is **black & white**.

## Pipeline (the easy workflow)
1. Open **`ART_PROMPTS.txt`** and paste each prompt into ChatGPT.
2. Save the results into **`raw/`** with the exact base names (or to Downloads —
   I can grab them either way):
   - `arena_bg.png` — background, ~3:2
   - `kael_neutral.png` `kael_smug.png` `kael_fierce.png` `kael_shocked.png`
     — the SAME character, four expressions, on solid magenta `#fe00fe`
3. Run: `python tools/prep_spin_art.py`
   - resizes the bg to 720x480, keys magenta -> transparent on the character,
     and converts everything to grayscale B&W.

`raw/` is gitignored (inputs only); the normalized PNGs here are committed. To
ship, add `--add-data "assets\spinstory\*.png;assets\spinstory"` to
`build-installer.ps1` (the glob picks up new PNGs automatically).
