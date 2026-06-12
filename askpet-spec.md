# AskPet — Product Spec

## Objective
- Build AskPet, a local-only Windows/macOS app that helps users create optimized copy-ready prompts.
- AskPet guides users through a lightweight chatbot/pet-style interface and recommends the right destination (Codex, Claude Code, ChatGPT web, or Claude), templates, agent modules, and skills.

## Current State
- App name: AskPet.
- Target platform: Windows and macOS.
- Language: Python preferred.
- Dependency model: no external dependencies for MVP.
- UI: clean, simple, minimal clicks, local desktop GUI.
- UI framework: Python Tkinter (built into standard Python, cross-platform).
- App must run fully local. No cloud AI, no API calls, no authentication, no telemetry.
- Output is copy-ready text for Codex, Claude Code, ChatGPT web, or Claude.
- Initial team profile: IT.
- Future team profiles may include Engineering, Security, Finance Ops, etc.

## Important Context / Constraints
- User works in IT backend/system administration.
- Common technologies/workflows: Azure Functions, Intune deployments, Microsoft 365/O365, Entra ID/Azure AD, Okta, PowerShell automation, Jira ticketing, Atlassian/Confluence internal documentation, Infrastructure as Code, audit/access evidence workflows.
- AskPet must support messy user input: spelling errors, poor grammar, missing punctuation, aliases and shorthand.
- MVP spell/grammar support is practical but local:
  - fuzzy matching using Python standard library difflib
  - local typo dictionary
  - local aliases dictionary
  - basic sentence cleanup and punctuation normalization
  - red underline for unknown/weak-match words in the Tkinter Text widget
  - right-click suggestions to replace words
  - learned corrections saved locally
- Do not build true AI grammar correction in MVP.

## Core Product Model
- Three main local libraries:
  1. Prompt Templates — reusable prompt structures with placeholders
  2. Agent Modules — reusable instruction blocks, not actual AI agents
  3. Skill Templates — reusable workflow templates that can later become ChatGPT/Codex skills or workflows
- AskPet recommends whether the final prompt belongs in Codex/Claude Code, ChatGPT/Claude, or Both.

## Decision Logic
- Recommend **Codex / Claude Code** when the task involves: code, files, repo work, scripts, local project changes, testing, implementation.
- Recommend **ChatGPT web / Claude** when the task involves: planning, architecture discussion, prompt refinement, documentation drafting, strategy, analysis.
- Recommend **Both** when ChatGPT/Claude should design the approach and Codex/Claude Code should execute it locally.

## MVP User Flow
1. User opens AskPet.
2. User clicks/talks to the AskPet pet/chat UI.
3. User describes what they are trying to do.
4. App cleans spelling/grammar/punctuation enough to classify intent.
5. App detects team profile, task type, likely destination, and keywords.
6. App recommends: destination, prompt template, agent modules, skill templates, context files to include, verification checklist.
7. User reviews or adjusts recommendations.
8. App generates one optimized copy-ready prompt.
9. User copies prompt into their assistant of choice.
10. App optionally saves generated prompt history locally.

## Pet Mode (post-MVP addition, now default)
- The pet (Kogi, a chibi corgi sprite from codex-pets.net) floats above all windows: borderless, transparent, always on top.
- Left-click the pet opens/closes a chat window; drag moves it (position persisted); right-click opens a menu (chat, full editor, wandering toggle, exit).
- The pet idles, blinks, waves, emotes, and occasionally walks across the screen; it sits while the chat is open.
- Chat replies include interpretation, destination recommendation, context hints, and the generated prompt with Copy / Save / Adjust-in-editor buttons.
- `python askpet.py --editor` opens the classic full editor without the pet.

## Local Folder Structure

```
AskPet/
├── askpet.py
├── assets/kogi/            (spritesheet.png + manifest.json; convert_sprites.py is the dev-time converter)
├── data/
│   ├── app-version.json
│   └── teams/it/           (prompt-templates.json, agent-modules.json, skill-templates.json, recommendations.json)
├── dictionary/             (aliases.json, corrections.json)
├── docs/how-to-use.md
└── output/generated-prompts/
```

## Runtime/User Data Locations
- Never store user data inside the application install folder.
- Windows: `%LOCALAPPDATA%\AskPet\` — macOS: `~/Library/Application Support/AskPet/`
- Store locally: settings.json, prompt-history.json, custom-dictionary.json, learned-corrections.json, user-created templates/modules/skills.

## Initial Agent Modules
Documentation Agent, Jira Ticketing Agent, Harness Agent (task contract: inputs, constraints, outputs, verification, evidence, handoff), Infrastructure Agent (Azure/Intune/Okta/M365/PowerShell), Validation Agent (checks, rollback, testing, evidence, done criteria), Workspace Agent Builder, Memory System Agent (Hermes-style memory/context), Skill Builder Agent, Reflection Agent, Instruction Slimmer Agent.

## Initial Prompt Templates
Codex technical execution, ChatGPT planning/advisory, Jira ticket drafting, Atlassian documentation, Azure Function build, Intune deployment, Infrastructure-as-code, Audit evidence workflow, ChatGPT workspace agent, Harness/project setup.

## Initial Skill Templates
Jira ticket triage, Intune deployment, Azure Function build, Documentation publishing, Audit evidence, Harness setup, ChatGPT workspace-agent design, Infrastructure-as-code workflow, PowerShell automation, Okta/Entra access workflow.

## Harness Concepts Built Into Templates
- Each work item has a small task contract: scope, inputs, tools, constraints, outputs, verification.
- Recommended loop: orient from nearest AGENTS.md → load smallest relevant files → define bounded task contract → execute one coherent slice → capture evidence → update durable files → verify before claiming completion → leave a handoff if work remains.
- Local files are the source of truth; external systems (Jira, Confluence, GitHub, Slack, SharePoint, Box, OneDrive, Notion) are downstream copies.

## ChatGPT Workspace Agent Template Requirements
Core sections: purpose, scope, allowed tools, forbidden actions, memory/context strategy, Hermes-style memory model, self-learning/reflection, auto skill-building ideas, instruction-bloat control, harness/task-contract workflow, verification requirements, handoff behavior.
Self-learning is local reflection notes/templates, not uncontrolled autonomy. Memory is supplemental and never replaces durable source-of-truth files.

## Spell/Fuzzy Match Requirements
- Python standard library only: difflib, re, json, os, pathlib, datetime, tkinter.
- Local alias/correction examples: engeneering→engineering, fussy→fuzzy, insturctions→instructions, applciaiton→application, moduels→modules, gammer→grammar, punation→punctuation, conflunce→Confluence, jirra→Jira, entra→Microsoft Entra ID, intune→Microsoft Intune, iac→infrastructure as code, o365→Microsoft 365, aad→Microsoft Entra ID.
- Underline unknown/weak-match words in red; right-click shows suggestions; clicking a suggestion replaces the word; accepted corrections are saved to the learned corrections file.

## Update/Deployment Architecture (future)
- Deploy via Intune/Jamf/NinjaOne; silent install; install over current version without breaking active use; never overwrite locked running files.
- Architecture: AskPet Launcher (tiny, rarely changes) + versioned side-by-side app installs + content library + user data.
- New version installs silently; pet prompts "AskPet update is ready. Restart now or later?"; launcher opens newest version on next restart.
- Separate app version from content library version. Channels: Production, Pilot, Development. Migration logic for settings/templates/modules/skills on schema changes.

## MVP Coding Direction
- Single-file Python Tkinter app with seed data embedded (refactor to JSON under data/ later).
- Required MVP screens/panels: pet/chat input, team selector, destination recommendation, template recommendation, agent module recommendation, skill template recommendation, context checklist, generated prompt output, copy-to-clipboard button, save prompt button, how-to-use/help panel, basic update-ready placeholder/status panel.
- Keep UI simple and functional.

## Build Order
1. Single-file Python Tkinter MVP named askpet.py. ✅
2. Local seed libraries for IT team templates/modules/skills. ✅
3. Fuzzy matching and correction dictionary. ✅
4. Intent scoring and destination recommendation. ✅
5. Generated copy-ready prompt output. ✅
6. Prompt history saved to local user data folder. ✅
7. Placeholder update-status model for future launcher/deployment architecture. ✅
8. Keep the app local-only and dependency-free. ✅
