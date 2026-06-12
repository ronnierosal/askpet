# PromptMate 🐾

A local-only desktop pet that turns messy task descriptions into optimized,
copy-ready prompts for **Codex**, **Claude Code**, **ChatGPT**, or **Claude**.

A pixel pet floats on top of all your windows. Click it, tell it what you're
trying to do — typos, shorthand, and bad grammar welcome — and it replies in
an iMessage-style chat with:

- **Where the prompt belongs** — execution work goes to Codex/Claude Code,
  planning and writing go to ChatGPT/Claude, hybrid work gets both.
- **A recommended prompt template** with task-contract structure (scope,
  inputs, constraints, outputs, verification).
- **Agent modules** — reusable instruction blocks (Infrastructure, Jira,
  Documentation, Validation, Harness, and more).
- **A context checklist** of what to paste in for better results.
- **The finished prompt**, one click to copy.

Everything runs locally: no cloud AI, no accounts, no telemetry. The only
network access is downloading a pet sprite from codex-pets.net when *you*
ask for one.

![PromptMate chat](docs/chat-screenshot.png)

## MCP server

PromptMate doubles as a local MCP server, so coding agents (Claude Code,
Claude Desktop, anything MCP-capable) can use it as a tool:

```
python promptmate.py --mcp
```

The repo ships a `.mcp.json`, so Claude Code sessions opened in this folder
get the `promptmate` server automatically. Five tools: `ask` (chat with the
brain — prompts for tasks, knowledge-base answers for questions),
`build_prompt` (task + clarification answers → final prompt),
`list_library`, `search_library`, and `get_item` (browse the
template/module/skill content). Stateless, read-only, stdlib-only — and
still fully local.

## What's new

**0.17.4** (2026-06-12)
- Typos now show as a thin red underline under normal-colored text
  instead of solid red words — red text stays reserved for keyword
  highlighting, so the two can't be confused. Right-click a flagged
  word for corrections, as before.
- The editor's spell pass also handles contractions now ("doesn't" no
  longer flags), matching the chat window.

**0.17.3** (2026-06-12)
- Pet search survives typos online too: when codex-pets.net's exact
  search returns nothing, PromptMate retries progressively shorter
  prefixes per word — "godzila" finds "Godzilla Blue" site-wide now,
  not just among already-loaded pets.

**0.17.2** (2026-06-11)
- Spell check actually works now: a bundled 370k-word English dictionary
  (public domain, dwyl/english-words) replaces the ~250-word IT seed
  vocabulary that flagged everyday words like "meeting" and "calendar"
  as typos — real misspellings were drowning in red noise.
- Contractions and possessives ("doesn't", "kogi's", "users'") are no
  longer flagged; suggestions come from the full dictionary
  ("tommorow" → "tomorrow", "definately" → "definitely").
- Common product names (ChatGPT, Claude, Notion, Synology, Meraki, …)
  are pre-seeded so they don't light up red.
- New test_spell.py suite, run on every build.

**0.17.1** (2026-06-11)
- Pet browser overhaul: click column headers to sort (name, creator,
  kind, ♥ likes — likes start most-loved-first), a preview image appears
  when you select a pet, and search is now typo-tolerant and
  word-order-independent ("blue godzila" finds "Godzilla Blue").
- Press Enter (or the new button) to search ALL of codex-pets.net via
  the site API instead of only the pages you've loaded.
- Previews load in the background and are cached; no preview ever
  blocks the browser.

**0.17.0** (2026-06-11)
- Creative, academic, and analyst round: game design (core loops,
  design docs, playtest plans), art direction (briefs, AI image
  prompting one variable at a time), tutoring (step-by-step with
  verification, "the goal is you can do the next one without me" —
  covers math, science, history, essays), equity research (10-K-first
  company research, bull AND bear case, valuations with visible
  assumptions — always information, never financial advice), and deep
  research (triangulate claims, cite per claim, name disagreements).
- Four new templates: creative/game brief, tutoring session, investment
  research (with the not-advice disclaimer baked in), deep research
  brief.
- Routing fixes: "evaluate <company>" no longer lands on the vendor
  support template; script security reviews get the security review
  template instead of Conditional Access.
- 56 templates / 93 modules / 132 skills. Mega battery now 2,640
  variants, 0 flagged.

**0.16.0** (2026-06-11)
- PromptMate isn't just for IT anymore: a non-technical roles round adds
  agents and skills for chiefs of staff (decision memos, OKRs, exec
  briefs), executive assistants (calendar triage, travel itineraries,
  inbox triage), email writing (one ask, deadline bold, two-tone drafts),
  note-taking and Notion organization, presentations (takeaway-first
  slide outlines), Word/Google Docs (styles-not-hand-formatting, mail
  merge), NotebookLM (source-grounded research), HR (job descriptions,
  structured interview kits, review drafts), sales (proposals,
  follow-ups, CRM hygiene), marketing (content calendars, newsletters),
  customer support (replies that keep customers, help-center articles),
  finance ops (budget variance that explains drivers), project
  management (kickoffs, RAID logs), events (run-of-show), and legal
  intake (contract prep for counsel — never legal advice).
- Four new templates: executive brief / decision memo, email draft,
  document/deck creation, spreadsheet help.
- Office-flavored prompts: non-technical asks no longer get "include
  rollback steps" boilerplate in their constraints.
- mega_battery.py: generates 2,100+ phrasing variants across every role
  area and flags weak routing — 0 flagged at ship time.
- 52 templates / 88 modules / 121 skills.

**0.15.0** (2026-06-11)
- Gap-probe content round: ran 36 chats about topics the library didn't
  cover and filled what came back weak. New areas: telephony/Teams Phone
  (call flows, number ports), email deliverability (SPF/DKIM/DMARC, own
  template), firewall changes (FortiGate/Palo Alto/etc., rollback-first
  skill), AWS (admin-task template mirroring the Azure one), virtual
  desktops (Citrix/AVD/W365), password managers (1Password/Bitwarden
  rollouts), file-transfer automation (SFTP done safely), licensing &
  procurement (renewal prep with negotiation levers), privacy/DSAR
  responses, facilities/server-room work, and disk-space recovery.
- Keyword coverage: SCCM routes to Intune-shaped prompts, Copilot and
  Teams Rooms to M365, NAS vendors to storage, Wi-Fi vendors
  (UniFi/Meraki/Aruba) and domain registrars to network, Power BI to
  reporting.
- probe_gaps.py: reusable MCP-driven gap probe that flags topics getting
  generic templates, default-only modules, or no skills.
- 48 templates / 73 modules / 93 skills.

**0.14.0** (2026-06-11)
- MCP server mode (`--mcp`): use PromptMate's prompt-building brain from
  Claude Code or any MCP client — see the MCP server section above.
- Battery-tested routing round: word-anchored topic keywords ("edr" no
  longer matches "onedrive"), bulk/CSV ops get their own topic and Codex
  routing, conditional access/MFA asks reach the Entra template instead of
  audit evidence, "compliance policy" reads as Intune config not audit,
  certificate renewals hit the network topic, backup-failure
  investigations get the troubleshoot shape.
- New "Explain a concept" template — "explain X vs Y" asks now get a
  learning-shaped prompt instead of a product template.
- Knowledge base: answers about privacy/local-only operation ("do you
  send my data anywhere?"), plus better matching for "can I trust the
  AI" and "start a fresh chat" phrasings.
- 46 templates / 64 modules / 82 skills + 9 help topics.

**0.13.0** (2026-06-11)
- Ask the pet questions: a built-in best-practices knowledge base answers
  questions about context (what to include, when it hurts), handoffs,
  when to clear/start a fresh chat, what makes a good prompt, choosing an
  assistant, plan-first, verifying AI output, and how PromptMate itself
  works. Question-shaped messages get answers; task descriptions still
  generate prompts.

**0.12.0** (2026-06-11)
- Chat handoff support: a template + skill for moving long AI chats to a
  fresh session — generates a single-code-block summary (objective, state,
  decisions made, in-flight work, next steps, gotchas) and a workflow for
  verifying it before seeding the new chat.
- 45 templates / 64 modules / 82 skills.

**0.11.x** (2026-06-11)
- DeckSide development support (templates/agents/skills encoding its
  AGENTS.md rules and capability pattern); pet jitter fix on multi-monitor
  setups; no wandering while chat is open; pet scale no longer reverts on
  update; nap animation slowed to a doze.

**0.11.0** (2026-06-11)
- DeckSide support: a DeckSide development template plus Architect and
  Assistant Designer agents that bake in the app's AGENTS.md rules
  (renderer never touches the DB, typed IPC, coach/parent isolation,
  import back-compat) and the capability pattern (Interpret → Preview →
  Approval → Validate → Apply). Skills for feature builds, assistant
  capabilities, PDF parser changes with golden fixtures, and local-model
  prompt tuning with eval sets.
- 44 templates / 64 modules / 81 skills.

**0.10.0** (2026-06-11)
- Calmer pet: slower animation tick, gentler movement speeds, and more
  time idling/sitting between activities.
- Sysadmin content round: Linux (services, bash), on-prem Active Directory
  (GPO troubleshooting, stale-object cleanup), virtualization
  (VMware/Hyper-V snapshot discipline), file shares & NTFS permissions,
  database safe-changes, data migrations, regex building, diagrams-as-code
  (Mermaid), asset inventory audits, and status reports.
- New Technical Diagram template; routing fixes for vendor/database and
  diagram asks.
- 43 templates / 62 modules / 77 skills.

**0.9.0** (2026-06-11)
- The pet defaults to Medium size (right-click → Pet size to change).
- More pet life: naps after ~4 minutes of being ignored (wakes with a
  wave when touched), rare zoomies dashes, slow mosey ambles, legs
  scramble while you drag it, a shake-off emote when dropped, and a
  happy celebration whenever you copy a prompt.

**0.8.0** (2026-06-11)
- Full Microsoft cloud coverage: Azure admin (RBAC, tagging, cost,
  teardown), Exchange Online (mailboxes, DLs, transport rules), and
  Defender/Purview (DLP, sensitivity labels, simulate-first rollouts).
- Scripting: dedicated Python template/agent/skill alongside PowerShell.
- Platform troubleshooting: Windows (Event Viewer-first), macOS
  (Console/keychain/MDM-aware), iOS/Android under MDM, and printers.
- App building: MVP-first template, agent, and skill for small internal
  apps.
- Smarter ranking: focused specialists now beat broad matches in ties.
- 42 templates / 54 modules / 65 skills.

**0.7.0** (2026-06-11)
- API & MCP integration support: templates, agents, and skills for building
  API integrations (auth, paging, rate limits, idempotency) and connecting
  tools to AI clients via Model Context Protocol.
- Local AI chatbot template: walks you through building a fully-local
  Ollama + Gemma chatbot (hardware fit, system prompt, front end, testing).
- New tool coverage: NinjaOne/ConnectWise (RMM), Sumo Logic (SIEM),
  SentinelOne (EDR), and browser management (Chrome, Edge, Firefox, Island).
- Routing fixes: no-topic-match asks now fall back to the right generic
  template; EDR alerts rank their specialist module first.
- 39 templates / 45 modules / 56 skills.

**0.6.0** (2026-06-11)
- Chat replies now show clickable module/skill chips — tap one to read
  exactly what it adds to your prompt.
- Content informed by what people actually ask AI at work (writing/editing
  text is ~40% of work usage) and top helpdesk tickets (password resets #1):
  new Writing Editor, Spreadsheet, and Helpdesk agents; rewrite/edit
  template; skills for text editing, Excel formulas, account lockouts,
  software requests, explaining concepts, and document summaries
  (36 templates / 38 modules / 49 skills).

**0.5.0** (2026-06-11)
- Tool coverage: agent modules and skills for Notion, Zoom, Google
  Workspace, Slack, GitHub, ServiceNow, and Power Automate/Zapier
  (35 templates / 35 modules / 43 skills).
- Plan-first by default: every generated prompt now includes a Plan-First
  module (restate, ask, plan, wait for approval) — like plan mode in
  Codex/Claude Code — plus a "Dial in the ask" template for vague ideas.
- The ChatGPT workspace-agent template now writes complete agent
  instructions including a memory system, self-reflection loop, skill
  maker, task contracts, and instruction hygiene — the parts people
  don't know to ask for.
- Editor: click any module or skill to read its full text; team dropdown
  removed; chat avatar transparency actually fixed.

**0.4.0** (2026-06-11)
- The pet now asks follow-up questions when your message is short or
  ambiguous ("Who's affected — one user or everyone?"), then folds your
  answers into the generated prompt. Say "skip" to just build it.
- General fix-it support: "outlook keeps crashing", "printer not working",
  "teams calls keep dropping" now route to a systematic troubleshooting
  template (scope → ranked causes → cheapest checks first → fix → verify)
  with a Troubleshooter agent module and diagnose-before-fixing skill.
- Recommended modules/skills are now ranked by relevance.
- Chat header avatar renders with clean transparency.

**0.3.0** (2026-06-11)
- Pet resizing: right-click → Pet size → Large / Medium / Small.
- Chat window is fully resizable — bubbles re-flow to the new width.
- Chat UI polish: header bar with pet avatar, name, and artist credit;
  input placeholder; fixed a bug that hid the send button.
- Third content expansion: 33 prompt templates, 26 agent modules, 34 skill
  templates (Graph API, Conditional Access, device policy, Teams/SharePoint,
  bulk CSV ops, vendor cases/evaluations, training guides, ticket replies,
  cert renewal, DNS changes, and more).

**0.2.0** (2026-06-11)
- Desktop pet mode is now the default: the pet floats over all windows,
  wanders, waves, and naps; click it to chat.
- iMessage-style chat with bubbles, typing indicator, and inline
  Copy / Save / Adjust buttons on every generated prompt.
- Pet browser: switch to any of 2,000+ community pets from codex-pets.net
  (right-click → Change pet…), with creator credits.
- Destinations now include Claude and Claude Code alongside Codex and
  ChatGPT web.

**0.1.0** (2026-06-11)
- Initial MVP: prompt templates, agent modules, skill templates, local
  typo/alias correction, intent scoring, prompt history, full editor.

## Install (Windows)

Build the installer yourself (see [Building the Windows
installer](#building-the-windows-installer)), then run
`installer\PromptMate-Setup-<version>.exe`. It installs per-user — no admin
rights — with optional desktop and start-at-sign-in shortcuts, and upgrades
cleanly over a running copy. For silent/enterprise deployment:

```
PromptMate-Setup-0.2.0.exe /VERYSILENT /NORESTART
```

Prebuilt installers are intentionally **not** published on GitHub: the
build bundles the default pet's sprite, which is creator-owned artwork
(see [Pets & artwork credits](#pets--artwork-credits)).

## Quick start (from source)

Requires Python 3.10+ (Tkinter is included in the standard installer). No
packages needed to run the app:

```
python promptmate.py            # pet mode (default)
python promptmate.py --editor   # classic full editor, no pet
```

On first run the pet appears near the bottom-right of your screen:

| Action | Result |
|---|---|
| Left-click the pet | Open/close the chat |
| Drag the pet | Move it (position is remembered) |
| Right-click the pet | Menu: chat, full editor, change pet, credits, wandering, exit |

Type a task in the chat (e.g. `need a powershel scirpt to deply an intune
app pakage to pilot grp`) and press Enter. PromptMate fixes the typos,
expands shorthand (`iac`, `o365`, `aad`…), and replies with the
recommendation and the copy-ready prompt.

## Pets & artwork credits

PromptMate's pets come from [codex-pets.net](https://codex-pets.net), a
gallery of community-made desktop pet sprites. Right-click the pet →
**Change pet…** to browse the catalog (2,000+ pets) and switch.

**The sprites are not included in this repository.** They are artwork by
individual creators with no published license, so PromptMate downloads a
pet only when you select it, caches it in your local user-data folder for
personal use, and shows the creator's name in the pet browser, the chat,
and the **About this pet** menu. Please don't redistribute downloaded
sprites; visit the creator's page on codex-pets.net instead.

Switching pets requires Pillow for image conversion (`pip install Pillow`)
when running from source; the packaged Windows build includes it.

## Spell support (local, no AI)

- Common-typo dictionary and shorthand aliases (`jirra` → Jira,
  `conflunce` → Confluence, `o365` → Microsoft 365)
- Fuzzy suggestions via Python's difflib
- Red underline on unknown words; right-click for suggestions or to add
  words to your personal dictionary
- Accepted corrections are remembered locally

## Where your data lives

| Platform | Location |
|---|---|
| Windows | `%LOCALAPPDATA%\PromptMate\` |
| macOS | `~/Library/Application Support/PromptMate/` |

Settings, prompt history, your custom dictionary, learned corrections, and
downloaded pets. Never inside the install folder; never uploaded anywhere.

## Building the Windows installer

Dev machine needs PyInstaller and [Inno Setup](https://jrsoftware.org/isinfo.php):

```
powershell -ExecutionPolicy Bypass -File build-installer.ps1
```

Produces `installer\PromptMate-Setup-<version>.exe` — per-user install (no
admin), silent-install capable for Intune (`/VERYSILENT /NORESTART`),
upgrades over a running copy and relaunches it. User data survives
upgrades and uninstalls.

## Project layout

```
promptmate.py        the whole app (stdlib-only at runtime)
promptmate-spec.md   product spec
data/                seed libraries exported as JSON (templates, modules, skills)
dictionary/          alias + correction dictionaries (JSON export)
docs/                how-to-use guide
assets/              convert_sprites.py dev tool (sprite art not committed)
test_*.py            smoke tests (logic, editor GUI, pet, pet store, chat visual)
installer.iss        Inno Setup script
build-installer.ps1  one-command build
```

## License

MIT for all code and seed content in this repository (see [LICENSE](LICENSE)).
Pet sprite artwork is **not** covered — each sprite remains the property of
its creator on codex-pets.net.
