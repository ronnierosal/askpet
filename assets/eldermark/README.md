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
   - `gloomling.png` — battle creature, on solid magenta `#fe00fe`
   - `thistlewisp.png` `hedge_pixie.png` `mire_warden.png` — more creatures for
     the Creature Journal + future scenes, on solid magenta `#fe00fe`
   - `battle_bg.png` — optional battle backdrop, ~3:2 (defaults to reusing
     `mosslight_gate_bg.png`). The battle player back-sprite reuses `hero_up.png`.
   - `whisperwood_bg.png` — the Whisperwood exploration scene, ~3:2 landscape
   - `wayshrine_bg.png` — the glowing Wayshrine ending scene, ~3:2 landscape
3. Run: `python tools/prep_eldermark_art.py`
   - resizes the background to 720x480, keys magenta -> transparent on sprites,
     quantizes everything to the 4 greens, and auto-mirrors `hero_left.png`.
   - normalized output lands here, next to this README.

`raw/` is gitignored (inputs only). The normalized PNGs here ARE committed.

## Shipping in the installer
These PNGs are committed and bundled automatically — `build-installer.ps1` uses a
glob:

```
--add-data "assets\eldermark\*.png;assets\eldermark"
```

so any new PNG dropped here ships with no build-script change. (PyInstaller
regenerates `AskPet.spec` from those CLI args every build; the spec is gitignored
— don't hand-edit it.)
