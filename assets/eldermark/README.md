# Eldermark art assets

Painted Game-Boy-green pixel art for the `/eldermark` scene engine
(`EldermarkScene` in `askpet.py`).

## How it works
Each location is one painted PNG **background** plus character/creature
**sprite** PNGs drawn on top, with a code-drawn dialogue box and fireflies. If
a file here is missing the game draws a simple placeholder, so it always runs.

- Display is **1:1** at a canonical **720x480** scene.
- Palette is 4 Game-Boy greens: `#0f380f` (darkest) `#306230` `#8bac0f`
  `#9bbc0f` (lightest).
- Sprites are anchored by their **feet** (bottom-centre).

## Pipeline
1. Generate the art in ChatGPT as PNGs (prompts live with the task notes).
2. Drop the raw exports into `raw/` with these base names:
   - `mosslight_gate_bg.png` — background, ~3:2, any size
   - `hero_down.png` `hero_up.png` `hero_right.png` — on solid magenta `#fe00fe`
   - `mossback.png` — on solid magenta `#fe00fe`
3. Run: `python tools/prep_eldermark_art.py`
   - resizes the background to 720x480, keys magenta -> transparent on sprites,
     quantizes everything to the 4 greens, and auto-mirrors `hero_left.png`.
   - normalized output lands here, next to this README.

`raw/` is gitignored (inputs only). The normalized PNGs here ARE committed.

## Shipping in the installer
These PNGs are committed, but still need bundling into the frozen build. For
each file, add a line to `build-installer.ps1` and `AskPet.spec`, e.g.:

```
--add-data "assets\eldermark\mosslight_gate_bg.png;assets\eldermark"
```
