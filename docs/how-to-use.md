# How to use PromptMate

PromptMate is a local-only desktop pet (Kogi the corgi) that turns a rough
description of what you're trying to do into an optimized, copy-ready prompt
for **Codex**, **Claude Code**, **ChatGPT**, or **Claude**.

## The pet

Kogi floats on top of all your windows and wanders, waves, and naps on its own.

- **Left-click** Kogi → open/close the chat window.
- **Drag** Kogi anywhere; the position is remembered.
- **Right-click** Kogi → menu: open chat, open full editor, stop/allow
  wandering, exit.

In the chat, type what you're trying to do (typos fine). Kogi replies with
where the prompt belongs, what context to include, and the generated prompt
with **Copy / Save / Adjust in editor** buttons.

Run `python promptmate.py --editor` to use the classic full editor without
the pet.

## Installing (Windows)

Run `installer\PromptMate-Setup-<version>.exe`. It installs per-user (no admin
rights) to `%LOCALAPPDATA%\Programs\PromptMate` with a Start Menu shortcut,
plus optional desktop and start-at-sign-in shortcuts. The installed app does
not need Python.

Silent install (Intune/enterprise):

```
PromptMate-Setup-0.1.0.exe /VERYSILENT /NORESTART
```

Installing over a running PromptMate closes it and relaunches it
automatically. User data is never touched, including on uninstall.

To rebuild the installer after changing the app:
`powershell -ExecutionPolicy Bypass -File build-installer.ps1`
(needs PyInstaller and Inno Setup, dev machine only).

## Requirements (running from source)

- Python 3.10+ (with Tkinter, included in the standard installer)
- No other dependencies. No internet connection needed.

## Run it

```
python promptmate.py
```

## Workflow

1. **Pick your team.** IT is the only profile in the MVP; more teams
   (Engineering, Security, Finance Ops) come later.
2. **Describe your task** in the chat box. Messy input is fine — PromptMate
   fixes common typos (`jirra` → `Jira`) and expands shorthand
   (`iac` → `infrastructure as code`, `o365` → `Microsoft 365`).
   - Unknown words are underlined in red.
   - Right-click an underlined word for suggestions, or add it to your
     personal dictionary. Accepted corrections are remembered.
3. **Click "Ask PromptMate"** (or press `Ctrl+Enter`). PromptMate will:
   - clean up your input,
   - recommend a destination (**Codex**, **ChatGPT web**, or **Both**),
   - pre-select a prompt template, agent modules, and skill templates,
   - show a context checklist.
4. **Adjust anything** — change the template, select/deselect modules and
   skills, tick the context items you can provide.
5. **Click "Generate Prompt"**, then **Copy to Clipboard** and paste into
   Codex or ChatGPT web.
6. **Save Prompt** keeps a local history (last 200 prompts).

## Where your data lives

PromptMate never stores user data in the install folder.

| Platform | Location |
|---|---|
| Windows | `%LOCALAPPDATA%\PromptMate\` |
| macOS | `~/Library/Application Support/PromptMate/` |

Files: `settings.json`, `prompt-history.json`, `custom-dictionary.json`,
`learned-corrections.json`.

## When does it recommend what?

- **Codex** — code, files, repo work, scripts, local project changes,
  testing, implementation.
- **ChatGPT web** — planning, architecture, prompt refinement, documentation
  drafting, strategy, analysis.
- **Both** — ChatGPT designs the approach, Codex executes it locally.

## Credits

The Kogi sprite is "Kogi" by daichi, downloaded from codex-pets.net
(https://codex-pets.net/#/pets/kogi). Check the site for usage terms before
distributing PromptMate outside personal use.

## Privacy

Everything runs locally. No cloud AI, no API calls, no authentication,
no telemetry.
