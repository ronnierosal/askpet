#!/usr/bin/env python3
"""
PromptMate — local-only prompt builder for Codex / ChatGPT web.

Single-file Tkinter MVP. No external dependencies, no network calls,
no telemetry. Seed data lives in this file; later it can be refactored
into JSON files under data/.

Run:  python promptmate.py
"""

import difflib
import io
import json
import os
import random
import re
import shutil
import sys
import tkinter as tk
import urllib.error
import urllib.request
import webbrowser
import zipfile
from datetime import datetime
from pathlib import Path
from tkinter import messagebox, ttk

APP_NAME = "PromptMate"
APP_VERSION = "0.2.0"
CONTENT_VERSION = "2026.06.1"

# ---------------------------------------------------------------------------
# User data locations (never inside the install folder)
# ---------------------------------------------------------------------------


def user_data_dir() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        return base / APP_NAME
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_NAME
    return Path.home() / ".local" / "share" / APP_NAME


DATA_DIR = user_data_dir()
SETTINGS_FILE = DATA_DIR / "settings.json"
HISTORY_FILE = DATA_DIR / "prompt-history.json"
CUSTOM_DICT_FILE = DATA_DIR / "custom-dictionary.json"
LEARNED_FILE = DATA_DIR / "learned-corrections.json"


def load_json(path: Path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def save_json(path: Path, data) -> bool:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return True
    except OSError:
        return False


# ---------------------------------------------------------------------------
# Seed dictionaries: aliases and typo corrections (local, no AI)
# ---------------------------------------------------------------------------

ALIASES = {
    "iac": "infrastructure as code",
    "o365": "Microsoft 365",
    "m365": "Microsoft 365",
    "aad": "Microsoft Entra ID",
    "entra": "Microsoft Entra ID",
    "intune": "Microsoft Intune",
    "ps": "PowerShell",
    "pwsh": "PowerShell",
    "kb": "knowledge base",
    "repo": "repository",
    "func": "Azure Function",
    "grp": "group",
    "grps": "groups",
    "env": "environment",
    "prod": "production",
}

CORRECTIONS = {
    "engeneering": "engineering",
    "fussy": "fuzzy",
    "insturctions": "instructions",
    "applciaiton": "application",
    "applicaiton": "application",
    "moduels": "modules",
    "gammer": "grammar",
    "punation": "punctuation",
    "conflunce": "Confluence",
    "confluance": "Confluence",
    "jirra": "Jira",
    "jria": "Jira",
    "powershel": "PowerShell",
    "powersehll": "PowerShell",
    "azur": "Azure",
    "fucntion": "function",
    "fucntions": "functions",
    "deploymnet": "deployment",
    "deplyment": "deployment",
    "documentaiton": "documentation",
    "docuemntation": "documentation",
    "tempalte": "template",
    "tempaltes": "templates",
    "scirpt": "script",
    "scirpts": "scripts",
    "auotmation": "automation",
    "automaiton": "automation",
    "deply": "deploy",
    "pakage": "package",
    "packge": "package",
    "evidnce": "evidence",
    "valdiate": "validate",
}

# Vocabulary used for fuzzy "did you mean" suggestions and spell checking.
KNOWN_WORDS = set(
    """
    a an and are as at be build builds but by can check checks code config
    configuration create creates debug deploy deployment design doc docs
    document documentation draft drafts environment error evidence file files
    fix for from function functions generate get group groups help how i if in
    install is it jira confluence azure intune okta entra microsoft m365 windows
    macos make migration module modules need new of okta on or our out plan
    planning policy policies powershell process production project prompt
    prompts repository review rollback run runbook script scripts security
    server set setup skill skills strategy summary task tasks team template
    templates test testing tests that the this ticket tickets to update updates
    user users validate validation verify we what when where which with work
    workflow workflows write yaml json api app application automation access
    audit pipeline infrastructure cloud admin account license licenses mailbox
    sharepoint teams onedrive exchange device devices laptop compliance
    conditional mfa sso saml scim group onboarding offboarding report reports
    architecture analysis refine implementation local change changes
    """.split()
)
KNOWN_WORDS.update(w.lower() for w in CORRECTIONS.values())
KNOWN_WORDS.update(ALIASES.keys())
for phrase in ALIASES.values():
    KNOWN_WORDS.update(w.lower() for w in phrase.split())


# ---------------------------------------------------------------------------
# Text cleanup + spell support (stdlib only)
# ---------------------------------------------------------------------------


class SpellHelper:
    """Local fuzzy spelling support: corrections dict + difflib + learned words."""

    def __init__(self):
        self.learned = load_json(LEARNED_FILE, {})  # typo -> correction
        custom = load_json(CUSTOM_DICT_FILE, {"words": []})
        self.custom_words = {w.lower() for w in custom.get("words", [])}

    def known(self, word: str) -> bool:
        lw = word.lower()
        return (
            lw in KNOWN_WORDS
            or lw in self.custom_words
            or lw in ALIASES
            or len(lw) <= 2
            or lw.isdigit()
        )

    def suggestions(self, word: str, n: int = 4) -> list:
        lw = word.lower()
        out = []
        if lw in self.learned:
            out.append(self.learned[lw])
        if lw in CORRECTIONS:
            out.append(CORRECTIONS[lw])
        pool = KNOWN_WORDS | self.custom_words
        out.extend(difflib.get_close_matches(lw, pool, n=n, cutoff=0.72))
        seen, uniq = set(), []
        for s in out:
            if s.lower() not in seen and s.lower() != lw:
                seen.add(s.lower())
                uniq.append(s)
        return uniq[:n]

    def learn(self, typo: str, correction: str):
        self.learned[typo.lower()] = correction
        save_json(LEARNED_FILE, self.learned)

    def add_to_dictionary(self, word: str):
        self.custom_words.add(word.lower())
        save_json(CUSTOM_DICT_FILE, {"words": sorted(self.custom_words)})

    def correct_word(self, word: str) -> str:
        lw = word.lower()
        if lw in self.learned:
            return self.learned[lw]
        if lw in CORRECTIONS:
            return CORRECTIONS[lw]
        return word


def expand_aliases(text: str) -> str:
    def repl(m):
        return ALIASES.get(m.group(0).lower(), m.group(0))

    pattern = r"\b(" + "|".join(re.escape(k) for k in ALIASES) + r")\b"
    return re.sub(pattern, repl, text, flags=re.IGNORECASE)


def clean_text(text: str, spell: "SpellHelper") -> str:
    """Practical local cleanup: typo fixes, alias expansion, punctuation."""
    words = re.split(r"(\W+)", text)
    fixed = [spell.correct_word(w) if w.isalpha() else w for w in words]
    out = "".join(fixed)
    out = expand_aliases(out)
    out = re.sub(r"\s+", " ", out).strip()
    out = re.sub(r"\s+([,.!?;:])", r"\1", out)
    if out and out[-1] not in ".!?":
        out += "."
    if out:
        out = out[0].upper() + out[1:]
    return out


# ---------------------------------------------------------------------------
# Intent scoring + destination recommendation
# ---------------------------------------------------------------------------

# Internal destination keys stay "Codex"/"ChatGPT web"/"Both"; these are the
# user-facing labels now that Claude and Claude Code are equal options.
DEST_LABELS = {
    "Codex": "Codex or Claude Code",
    "ChatGPT web": "ChatGPT or Claude",
    "Both": "ChatGPT/Claude to plan, then Codex/Claude Code to execute",
}

CODEX_SIGNALS = {
    "code": 3, "script": 3, "scripts": 3, "repository": 3, "repo": 3,
    "file": 2, "files": 2, "function": 2, "functions": 2, "build": 2,
    "implement": 3, "implementation": 3, "test": 2, "testing": 2, "tests": 2,
    "debug": 3, "fix": 2, "deploy": 2, "deployment": 2, "powershell": 3,
    "pipeline": 2, "automation": 2, "yaml": 2, "json": 1, "api": 2,
    "install": 2, "refactor": 3, "migration": 2, "local": 1, "run": 1,
}

CHATGPT_SIGNALS = {
    "plan": 3, "planning": 3, "architecture": 3, "design": 2, "strategy": 3,
    "analysis": 3, "analyze": 3, "document": 2, "documentation": 3,
    "draft": 2, "write": 1, "summary": 2, "summarize": 2, "review": 2,
    "refine": 3, "advice": 3, "advise": 3, "explain": 2, "compare": 2,
    "ticket": 2, "jira": 2, "confluence": 3, "runbook": 2, "policy": 2,
    "audit": 2, "evidence": 2, "process": 1, "workflow": 1, "agent": 2,
}

KEYWORD_TOPICS = {
    "azure_function": ["azure function", "azure functions", "function app"],
    "intune": ["intune"],
    "m365": ["microsoft 365", "office 365", "exchange", "sharepoint", "onedrive", "mailbox"],
    "entra": ["entra", "azure ad", "active directory", "conditional access", "mfa", "sso"],
    "okta": ["okta", "scim", "saml"],
    "powershell": ["powershell"],
    "jira": ["jira", "ticket"],
    "confluence": ["confluence", "documentation", "knowledge base", "runbook", "how-to"],
    "iac": ["infrastructure as code", "terraform", "bicep", "arm template"],
    "audit": ["audit", "evidence", "access review", "compliance"],
    "workspace_agent": ["workspace agent", "chatgpt agent", "custom gpt"],
    "harness": ["harness", "task contract", "agents.md"],
    "skill": ["skill", "reusable workflow"],
}


def score_destination(text: str) -> dict:
    """Return destination recommendation with scores and reasoning."""
    lw = text.lower()
    words = re.findall(r"[a-z0-9]+", lw)
    codex = sum(CODEX_SIGNALS.get(w, 0) for w in words)
    chatgpt = sum(CHATGPT_SIGNALS.get(w, 0) for w in words)

    topics = [t for t, keys in KEYWORD_TOPICS.items() if any(k in lw for k in keys)]

    if codex >= 2 and chatgpt >= 2 and abs(codex - chatgpt) <= 3:
        dest = "Both"
        reason = ("Plan and refine the approach in ChatGPT or Claude first, "
                  "then hand the execution steps to Codex or Claude Code.")
    elif codex > chatgpt:
        dest = "Codex"
        reason = ("This looks like hands-on execution work (code, files, "
                  "scripts, or testing) — Codex or Claude Code can do it locally.")
    elif chatgpt > codex:
        dest = "ChatGPT web"
        reason = ("This looks like thinking/writing work (planning, "
                  "documentation, analysis) — ChatGPT or Claude fits best.")
    else:
        dest = "ChatGPT web"
        reason = ("No strong execution signals detected — starting in "
                  "ChatGPT or Claude to refine the request is the safe default.")

    return {
        "destination": dest,
        "codex_score": codex,
        "chatgpt_score": chatgpt,
        "topics": topics,
        "reason": reason,
    }


# ---------------------------------------------------------------------------
# Seed content library: IT team templates / agent modules / skill templates
# ---------------------------------------------------------------------------

PROMPT_TEMPLATES = {
    "codex_execution": {
        "name": "Codex technical execution",
        "destination": "Codex",
        "topics": ["powershell", "azure_function", "iac", "intune"],
        "body": (
            "## Task\n{TASK}\n\n"
            "## Task contract\n"
            "- Scope: {SCOPE}\n- Inputs: {INPUTS}\n- Tools allowed: {TOOLS}\n"
            "- Constraints: {CONSTRAINTS}\n- Expected outputs: {OUTPUTS}\n\n"
            "## Working rules\n"
            "1. Orient from the nearest AGENTS.md before changing anything.\n"
            "2. Load only the smallest relevant local files.\n"
            "3. Execute one coherent slice at a time.\n"
            "4. Capture evidence (commands run, output, test results).\n"
            "5. Verify before claiming completion.\n"
            "6. Leave a handoff note if work remains.\n\n"
            "## Verification\n{VERIFICATION}"
        ),
    },
    "chatgpt_planning": {
        "name": "ChatGPT planning / advisory",
        "destination": "ChatGPT web",
        "topics": [],
        "body": (
            "## Context\nI work in IT backend/system administration. {TASK}\n\n"
            "## What I need from you\n"
            "- Recommend an approach with trade-offs.\n"
            "- List risks, prerequisites, and open questions.\n"
            "- Produce a step-by-step plan I can hand to an execution agent.\n\n"
            "## Constraints\n{CONSTRAINTS}\n\n"
            "## Output format\n"
            "1. Recommended approach (short)\n2. Plan (numbered steps)\n"
            "3. Risks and rollback considerations\n4. Verification checklist"
        ),
    },
    "jira_ticket": {
        "name": "Jira ticket drafting",
        "destination": "ChatGPT web",
        "topics": ["jira"],
        "body": (
            "Draft a Jira ticket for the following work. {TASK}\n\n"
            "Include:\n- Summary (one line)\n- Description with background/context\n"
            "- Acceptance criteria (testable bullet points)\n"
            "- Validation steps and evidence to attach\n"
            "- Suggested labels/components\n\n"
            "Keep wording clear and free of jargon. Constraints: {CONSTRAINTS}"
        ),
    },
    "atlassian_docs": {
        "name": "Atlassian / Confluence documentation",
        "destination": "ChatGPT web",
        "topics": ["confluence"],
        "body": (
            "Write internal Confluence documentation for: {TASK}\n\n"
            "Structure:\n- Purpose (2-3 sentences)\n- Audience\n- Prerequisites\n"
            "- Step-by-step instructions with expected results\n"
            "- Troubleshooting / common failure points\n- Rollback or undo steps\n"
            "- Owner and review date\n\n"
            "Style: plain language, numbered steps, short paragraphs. "
            "Constraints: {CONSTRAINTS}"
        ),
    },
    "azure_function": {
        "name": "Azure Function build",
        "destination": "Codex",
        "topics": ["azure_function"],
        "body": (
            "Build an Azure Function. {TASK}\n\n"
            "Requirements:\n- Runtime/language: {TOOLS}\n- Inputs/trigger: {INPUTS}\n"
            "- Constraints: {CONSTRAINTS}\n- Outputs: {OUTPUTS}\n\n"
            "Include:\n- Function code with error handling and logging\n"
            "- local.settings.json template (no secrets)\n"
            "- Deployment notes\n- Test instructions\n\n"
            "Verification: {VERIFICATION}"
        ),
    },
    "intune_deployment": {
        "name": "Intune deployment",
        "destination": "Both",
        "topics": ["intune"],
        "body": (
            "Help me with a Microsoft Intune deployment. {TASK}\n\n"
            "Cover:\n- Packaging requirements (Win32/LOB/script)\n"
            "- Detection rules\n- Install/uninstall commands (silent)\n"
            "- Assignment strategy (pilot ring first, then production)\n"
            "- Rollback plan\n\n"
            "Constraints: {CONSTRAINTS}\nVerification: {VERIFICATION}"
        ),
    },
    "iac": {
        "name": "Infrastructure as code",
        "destination": "Codex",
        "topics": ["iac"],
        "body": (
            "Write infrastructure-as-code for: {TASK}\n\n"
            "- Tooling: {TOOLS}\n- Inputs/parameters: {INPUTS}\n"
            "- Constraints: {CONSTRAINTS}\n\n"
            "Include idempotency notes, a plan/preview step before apply, "
            "and a teardown/rollback path.\n\nVerification: {VERIFICATION}"
        ),
    },
    "audit_evidence": {
        "name": "Audit evidence workflow",
        "destination": "ChatGPT web",
        "topics": ["audit", "entra", "okta"],
        "body": (
            "Help me prepare audit/access evidence. {TASK}\n\n"
            "Produce:\n- Evidence checklist (what to collect, from where)\n"
            "- Naming/storage convention for artifacts\n"
            "- Screenshot/export guidance for each system\n"
            "- A summary table mapping each control to its evidence\n\n"
            "Systems in scope: {INPUTS}\nConstraints: {CONSTRAINTS}"
        ),
    },
    "workspace_agent": {
        "name": "ChatGPT workspace agent design",
        "destination": "ChatGPT web",
        "topics": ["workspace_agent"],
        "body": (
            "Design a ChatGPT workspace agent. {TASK}\n\n"
            "The agent definition must include:\n"
            "- Purpose and scope (what it does and does NOT do)\n"
            "- Allowed tools and forbidden actions\n"
            "- Memory/context strategy (memory is supplemental — durable "
            "source-of-truth files win)\n"
            "- Self-learning as local reflection notes, not uncontrolled autonomy\n"
            "- Instruction-bloat control: review and slim instructions regularly\n"
            "- Harness/task-contract workflow (scope, inputs, tools, constraints, "
            "outputs, verification)\n"
            "- Verification requirements before claiming completion\n"
            "- Handoff behavior when work remains\n\n"
            "Constraints: {CONSTRAINTS}"
        ),
    },
    "harness_setup": {
        "name": "Harness / project setup",
        "destination": "Both",
        "topics": ["harness"],
        "body": (
            "Set up a working harness for this project. {TASK}\n\n"
            "Create:\n- AGENTS.md with orientation, conventions, and constraints\n"
            "- A task-contract template (scope, inputs, tools, constraints, "
            "outputs, verification)\n"
            "- An evidence/handoff convention\n\n"
            "Working loop to encode:\n"
            "1. Orient from nearest AGENTS.md\n2. Load smallest relevant files\n"
            "3. Define bounded task contract\n4. Execute one coherent slice\n"
            "5. Capture evidence\n6. Update durable files\n"
            "7. Verify before claiming completion\n8. Leave a handoff\n\n"
            "Local files are the source of truth; external systems (Jira, "
            "Confluence, SharePoint, etc.) are downstream copies.\n\n"
            "Constraints: {CONSTRAINTS}"
        ),
    },
}

AGENT_MODULES = {
    "documentation": {
        "name": "Documentation Agent",
        "topics": ["confluence"],
        "body": (
            "Act as a documentation specialist for Atlassian/Confluence-style "
            "internal docs. Produce clear how-to docs, operational docs, KB "
            "articles, and runbooks. Use plain language, numbered steps, "
            "expected results after each step, and a troubleshooting section."
        ),
    },
    "jira": {
        "name": "Jira Ticketing Agent",
        "topics": ["jira"],
        "body": (
            "Act as a Jira ticketing specialist. Write ticket summaries, "
            "descriptions, acceptance criteria, comments, and status updates. "
            "Acceptance criteria must be testable. Every status update states "
            "what was done, what was validated, and what remains."
        ),
    },
    "harness": {
        "name": "Harness Agent",
        "topics": ["harness"],
        "body": (
            "Operate under a task contract: scope, inputs, constraints, "
            "outputs, verification, evidence, and handoff. Do one coherent "
            "slice at a time. Capture evidence as you go. Verify before "
            "claiming completion. Leave a handoff note if work remains."
        ),
    },
    "infrastructure": {
        "name": "Infrastructure Agent",
        "topics": ["azure_function", "intune", "okta", "m365", "entra", "powershell", "iac"],
        "body": (
            "Act as a cloud/infrastructure administrator experienced with "
            "Azure, Microsoft Intune, Okta, Microsoft 365, Microsoft Entra ID, "
            "and PowerShell automation. Prefer idempotent, scripted, "
            "least-privilege solutions. Always include a rollback path."
        ),
    },
    "validation": {
        "name": "Validation Agent",
        "topics": ["audit"],
        "body": (
            "Act as a validation specialist. For every change define: "
            "pre-checks, post-checks, rollback procedure, evidence to capture "
            "(commands, outputs, screenshots), and explicit done criteria. "
            "Nothing is done until verified."
        ),
    },
    "workspace_builder": {
        "name": "Workspace Agent Builder",
        "topics": ["workspace_agent"],
        "body": (
            "Act as a designer of ChatGPT workspace agents. Define purpose, "
            "scope, allowed tools, forbidden actions, memory strategy, and "
            "verification requirements. Keep instructions minimal and "
            "unambiguous."
        ),
    },
    "memory": {
        "name": "Memory System Agent",
        "topics": ["workspace_agent", "harness"],
        "body": (
            "Apply a Hermes-style memory model: memory is supplemental "
            "context, never the source of truth. Durable local files win over "
            "remembered state. Record only stable, reusable facts; convert "
            "relative dates to absolute; prune stale entries."
        ),
    },
    "skill_builder": {
        "name": "Skill Builder Agent",
        "topics": ["skill"],
        "body": (
            "Act as a reusable-workflow designer. Turn a successful one-off "
            "task into a parameterized skill: name, trigger conditions, "
            "inputs, steps, outputs, and verification. Keep each skill small "
            "and single-purpose."
        ),
    },
    "reflection": {
        "name": "Reflection Agent",
        "topics": [],
        "body": (
            "After the main task, capture a short reflection: what worked, "
            "what should be reused (candidate skills/templates), and what "
            "should change next time. Keep it under 10 lines."
        ),
    },
    "slimmer": {
        "name": "Instruction Slimmer Agent",
        "topics": ["workspace_agent"],
        "body": (
            "Review the instructions/prompt for bloat: remove redundant "
            "rules, conflicting instructions, stale references, and "
            "unnecessary process. Output the slimmed version plus a list of "
            "what was removed and why."
        ),
    },
}

SKILL_TEMPLATES = {
    "jira_triage": {
        "name": "Jira ticket triage skill",
        "topics": ["jira"],
        "body": "Triage incoming Jira tickets: classify, set priority, draft first response, identify owner.",
    },
    "intune_deploy": {
        "name": "Intune deployment skill",
        "topics": ["intune"],
        "body": "Package, detect, assign (pilot → production), validate, and document an Intune deployment.",
    },
    "azure_function_build": {
        "name": "Azure Function build skill",
        "topics": ["azure_function"],
        "body": "Scaffold, implement, test locally, and document an Azure Function end to end.",
    },
    "docs_publish": {
        "name": "Documentation publishing skill",
        "topics": ["confluence"],
        "body": "Draft, review, and publish internal documentation with owner and review-date metadata.",
    },
    "audit_evidence": {
        "name": "Audit evidence skill",
        "topics": ["audit"],
        "body": "Collect, name, store, and summarize audit/access evidence mapped to controls.",
    },
    "harness_setup": {
        "name": "Harness setup skill",
        "topics": ["harness"],
        "body": "Create AGENTS.md, task-contract template, and evidence/handoff conventions for a project.",
    },
    "workspace_agent_design": {
        "name": "ChatGPT workspace-agent design skill",
        "topics": ["workspace_agent"],
        "body": "Design a workspace agent: purpose, scope, tools, memory model, verification, handoff.",
    },
    "iac_workflow": {
        "name": "Infrastructure-as-code workflow skill",
        "topics": ["iac"],
        "body": "Author IaC, preview/plan, apply with approval, verify, and record rollback steps.",
    },
    "powershell_automation": {
        "name": "PowerShell automation skill",
        "topics": ["powershell"],
        "body": "Write idempotent PowerShell with error handling, logging, -WhatIf support, and tests.",
    },
    "okta_entra_access": {
        "name": "Okta/Entra access workflow skill",
        "topics": ["okta", "entra"],
        "body": "Handle access requests: validate approval, apply group/app assignment, capture evidence.",
    },
}

CONTEXT_CHECKLIST_BY_TOPIC = {
    "azure_function": ["Function app name/runtime", "Trigger type and bindings", "Resource group / subscription"],
    "intune": ["App installer + version", "Target device groups", "Detection rule details"],
    "m365": ["Tenant name", "Affected users/groups", "Relevant admin center settings"],
    "entra": ["Group/app names", "Conditional access policies in scope", "Approval/ticket reference"],
    "okta": ["Okta app/group names", "SCIM/SAML config details", "Approval/ticket reference"],
    "powershell": ["Existing script (if any)", "Module versions in use", "Execution context (local/runbook)"],
    "jira": ["Project key", "Issue type and components", "Related ticket links"],
    "confluence": ["Space and parent page", "Existing doc to update (if any)", "Audience"],
    "iac": ["Tooling (Terraform/Bicep)", "State/backend location", "Existing module structure"],
    "audit": ["Control framework / control IDs", "Audit period", "Systems in scope"],
    "workspace_agent": ["Agent purpose statement", "Tools it may use", "Example tasks"],
    "harness": ["Project root path", "Existing AGENTS.md (if any)", "Definition of done"],
    "skill": ["The workflow being repeated", "Inputs that vary per run", "Success criteria"],
}

GENERIC_CHECKLIST = [
    "Relevant file paths or exports",
    "Error messages / logs (sanitized)",
    "Environment (prod/test) and change-window constraints",
]


def recommend(text: str) -> dict:
    """Full recommendation: destination, template, modules, skills, checklist."""
    dest_info = score_destination(text)
    topics = dest_info["topics"]

    def topic_score(item):
        return len(set(item["topics"]) & set(topics))

    # Template: best topic overlap, fall back by destination.
    best_key, best_score = None, -1
    for key, t in PROMPT_TEMPLATES.items():
        # Specific templates (fewer topics) win ties over broad ones.
        s = topic_score(t) * 2 - 0.01 * len(t["topics"])
        if t["destination"] == dest_info["destination"]:
            s += 0.5
        if s > best_score:
            best_key, best_score = key, s
    if best_score <= 0:
        best_key = "codex_execution" if dest_info["destination"] == "Codex" else "chatgpt_planning"

    modules = [k for k, m in AGENT_MODULES.items() if topic_score(m) > 0]
    if "harness" not in modules:
        modules.append("harness")
    if "validation" not in modules:
        modules.append("validation")

    skills = [k for k, s in SKILL_TEMPLATES.items() if topic_score(s) > 0]

    checklist = []
    for t in topics:
        checklist.extend(CONTEXT_CHECKLIST_BY_TOPIC.get(t, []))
    checklist.extend(GENERIC_CHECKLIST)

    return {
        **dest_info,
        "template": best_key,
        "modules": modules[:4],
        "skills": skills[:3],
        "checklist": checklist,
    }


def build_prompt(cleaned_task: str, rec: dict, selected_modules: list,
                 selected_skills: list, checked_context: list) -> str:
    """Assemble the final copy-ready prompt."""
    template = PROMPT_TEMPLATES[rec["template"]]
    body = template["body"]
    fills = {
        "{TASK}": cleaned_task,
        "{SCOPE}": "Only the work described above; ask before expanding scope.",
        "{INPUTS}": "; ".join(checked_context) if checked_context else "See task description.",
        "{TOOLS}": "Standard tooling for this stack; no destructive operations without confirmation.",
        "{CONSTRAINTS}": "Local-first, least privilege, no secrets in output, include rollback steps.",
        "{OUTPUTS}": "Working result plus a short summary of what changed and how it was verified.",
        "{VERIFICATION}": "List the exact checks performed and their results before claiming completion.",
    }
    for k, v in fills.items():
        body = body.replace(k, v)

    parts = [f"# {template['name']}", "", body]

    if selected_modules:
        parts.append("\n## Operating instructions")
        for mk in selected_modules:
            m = AGENT_MODULES[mk]
            parts.append(f"\n### {m['name']}\n{m['body']}")

    if selected_skills:
        parts.append("\n## Reusable workflow(s) to follow")
        for sk in selected_skills:
            s = SKILL_TEMPLATES[sk]
            parts.append(f"- **{s['name']}**: {s['body']}")

    if checked_context:
        parts.append("\n## Context I will provide")
        parts.extend(f"- {c}" for c in checked_context)

    parts.append(
        f"\n---\n*Destination: {DEST_LABELS[rec['destination']]} — {rec['reason']}*"
    )
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# History
# ---------------------------------------------------------------------------


def save_history_entry(raw: str, cleaned: str, rec: dict, prompt: str):
    history = load_json(HISTORY_FILE, [])
    history.append({
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "raw_input": raw,
        "cleaned_input": cleaned,
        "destination": rec["destination"],
        "template": rec["template"],
        "prompt": prompt,
    })
    save_json(HISTORY_FILE, history[-200:])  # cap history at 200 entries


# ---------------------------------------------------------------------------
# Tkinter UI
# ---------------------------------------------------------------------------

PET_GREETING = (
    "Hi! I'm PromptMate. 🐾\n\n"
    "Tell me what you're trying to do — typos and shorthand are fine. "
    "I'll recommend where it belongs (Codex or ChatGPT web), pick a "
    "template, and build you a copy-ready prompt."
)

HELP_TEXT = """How to use PromptMate

Kogi the pet floats above all your windows:
- Left-click Kogi to open/close the chat.
- Drag Kogi to move it (position is remembered).
- Right-click Kogi for the menu (chat, full editor, wandering, exit).

In the chat, just describe your task and Kogi replies with a copy-ready
prompt for Codex, Claude Code, ChatGPT, or Claude.

The full editor (below) gives you fine-grained control:

1. Pick your team (IT for now — more teams later).
2. Type what you're trying to do in the chat box. Messy input is fine —
   PromptMate fixes common typos and expands shorthand like "iac" or "o365".
   Unknown words get a red underline; right-click one for suggestions.
3. Click "Ask PromptMate" (or press Ctrl+Enter).
4. Review the recommendations:
   - Destination: Codex, ChatGPT web, or Both
   - Prompt template, agent modules, skill templates
   - Context checklist: tick what you can provide
5. Click "Generate Prompt" to build the final prompt.
6. Click "Copy to Clipboard" and paste it into Codex or ChatGPT web.
7. "Save Prompt" stores it in your local history.

Everything runs locally. No cloud AI, no API calls, no telemetry.
Your data lives in:
  Windows: %LOCALAPPDATA%\\PromptMate\\
  macOS:   ~/Library/Application Support/PromptMate/
"""


class PromptMateApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.spell = SpellHelper()
        self.rec = None
        self.cleaned = ""

        root.title(f"{APP_NAME} v{APP_VERSION}")
        root.geometry("1100x780")
        root.minsize(900, 640)

        self._build_ui()
        self._load_settings()

    # ---- UI construction -------------------------------------------------

    def _build_ui(self):
        top = ttk.Frame(self.root, padding=8)
        top.pack(fill="x")

        ttk.Label(top, text="🐾 PromptMate", font=("Segoe UI", 14, "bold")).pack(side="left")

        ttk.Label(top, text="Team:").pack(side="left", padx=(20, 4))
        self.team_var = tk.StringVar(value="IT")
        team_box = ttk.Combobox(top, textvariable=self.team_var, state="readonly",
                                values=["IT"], width=14)
        team_box.pack(side="left")

        self.update_label = ttk.Label(top, text=f"App v{APP_VERSION} · Content {CONTENT_VERSION} · Up to date",
                                      foreground="#2a7a2a")
        self.update_label.pack(side="right")

        ttk.Button(top, text="Help", command=self._show_help).pack(side="right", padx=8)

        main = ttk.PanedWindow(self.root, orient="horizontal")
        main.pack(fill="both", expand=True, padx=8, pady=4)

        # Left pane: chat input + recommendations
        left = ttk.Frame(main, padding=4)
        main.add(left, weight=1)

        chat_frame = ttk.LabelFrame(left, text="Talk to PromptMate", padding=6)
        chat_frame.pack(fill="x")

        self.pet_label = ttk.Label(chat_frame, text=PET_GREETING, wraplength=440,
                                   justify="left", padding=4)
        self.pet_label.pack(fill="x")

        self.input_text = tk.Text(chat_frame, height=5, wrap="word", undo=True,
                                  font=("Segoe UI", 10))
        self.input_text.pack(fill="x", pady=4)
        self.input_text.tag_configure("misspelled", underline=True, foreground="red")
        self.input_text.bind("<KeyRelease>", self._on_key_release)
        self.input_text.bind("<Button-3>", self._on_right_click)
        self.input_text.bind("<Control-Return>", lambda e: (self._ask(), "break")[1])

        btn_row = ttk.Frame(chat_frame)
        btn_row.pack(fill="x")
        ttk.Button(btn_row, text="Ask PromptMate  (Ctrl+Enter)", command=self._ask).pack(side="left")
        ttk.Button(btn_row, text="Clear", command=self._clear).pack(side="left", padx=6)

        rec_frame = ttk.LabelFrame(left, text="Recommendations", padding=6)
        rec_frame.pack(fill="both", expand=True, pady=(6, 0))

        self.dest_label = ttk.Label(rec_frame, text="Destination: —", font=("Segoe UI", 11, "bold"))
        self.dest_label.pack(anchor="w")
        self.reason_label = ttk.Label(rec_frame, text="", wraplength=440, justify="left")
        self.reason_label.pack(anchor="w", pady=(0, 6))

        ttk.Label(rec_frame, text="Prompt template:").pack(anchor="w")
        self.template_var = tk.StringVar()
        self.template_box = ttk.Combobox(rec_frame, textvariable=self.template_var, state="readonly",
                                         values=[t["name"] for t in PROMPT_TEMPLATES.values()])
        self.template_box.pack(fill="x", pady=(0, 6))

        lists_row = ttk.Frame(rec_frame)
        lists_row.pack(fill="both", expand=True)

        mod_frame = ttk.Frame(lists_row)
        mod_frame.pack(side="left", fill="both", expand=True, padx=(0, 4))
        ttk.Label(mod_frame, text="Agent modules:").pack(anchor="w")
        self.module_list = tk.Listbox(mod_frame, selectmode="multiple", exportselection=False, height=6)
        self.module_list.pack(fill="both", expand=True)
        for m in AGENT_MODULES.values():
            self.module_list.insert("end", m["name"])

        skill_frame = ttk.Frame(lists_row)
        skill_frame.pack(side="left", fill="both", expand=True, padx=(4, 0))
        ttk.Label(skill_frame, text="Skill templates:").pack(anchor="w")
        self.skill_list = tk.Listbox(skill_frame, selectmode="multiple", exportselection=False, height=6)
        self.skill_list.pack(fill="both", expand=True)
        for s in SKILL_TEMPLATES.values():
            self.skill_list.insert("end", s["name"])

        ctx_frame = ttk.LabelFrame(rec_frame, text="Context checklist (tick what you can provide)", padding=4)
        ctx_frame.pack(fill="x", pady=(6, 0))
        self.ctx_inner = ttk.Frame(ctx_frame)
        self.ctx_inner.pack(fill="x")
        self.ctx_vars = []  # list of (BooleanVar, label_text)

        ttk.Button(rec_frame, text="Generate Prompt ➜", command=self._generate).pack(anchor="e", pady=6)

        # Right pane: output
        right = ttk.Frame(main, padding=4)
        main.add(right, weight=1)

        out_frame = ttk.LabelFrame(right, text="Generated prompt (copy-ready)", padding=6)
        out_frame.pack(fill="both", expand=True)

        self.output_text = tk.Text(out_frame, wrap="word", font=("Consolas", 9))
        out_scroll = ttk.Scrollbar(out_frame, command=self.output_text.yview)
        self.output_text.configure(yscrollcommand=out_scroll.set)
        out_scroll.pack(side="right", fill="y")
        self.output_text.pack(fill="both", expand=True)

        out_btns = ttk.Frame(right)
        out_btns.pack(fill="x", pady=4)
        ttk.Button(out_btns, text="📋 Copy to Clipboard", command=self._copy).pack(side="left")
        ttk.Button(out_btns, text="💾 Save Prompt", command=self._save).pack(side="left", padx=6)
        self.status_label = ttk.Label(out_btns, text="")
        self.status_label.pack(side="left", padx=10)

    # ---- Spell underline + right-click suggestions -----------------------

    def _on_key_release(self, event=None):
        if event and event.keysym in ("Up", "Down", "Left", "Right", "Shift_L", "Shift_R"):
            return
        self._recheck_spelling()

    def _recheck_spelling(self):
        text = self.input_text.get("1.0", "end-1c")
        self.input_text.tag_remove("misspelled", "1.0", "end")
        for m in re.finditer(r"[A-Za-z]+", text):
            word = m.group(0)
            if not self.spell.known(word):
                start = f"1.0+{m.start()}c"
                end = f"1.0+{m.end()}c"
                self.input_text.tag_add("misspelled", start, end)

    def _word_at(self, index):
        start = self.input_text.index(f"{index} wordstart")
        end = self.input_text.index(f"{index} wordend")
        return self.input_text.get(start, end), start, end

    def _on_right_click(self, event):
        index = self.input_text.index(f"@{event.x},{event.y}")
        word, start, end = self._word_at(index)
        if not word.isalpha() or self.spell.known(word):
            return
        menu = tk.Menu(self.input_text, tearoff=0)
        suggestions = self.spell.suggestions(word)
        if suggestions:
            for s in suggestions:
                menu.add_command(label=s, command=lambda s=s: self._replace_word(start, end, word, s))
            menu.add_separator()
        else:
            menu.add_command(label="(no suggestions)", state="disabled")
            menu.add_separator()
        menu.add_command(label=f'Add "{word}" to dictionary',
                         command=lambda: self._add_word(word))
        menu.tk_popup(event.x_root, event.y_root)

    def _replace_word(self, start, end, typo, replacement):
        self.input_text.delete(start, end)
        self.input_text.insert(start, replacement)
        self.spell.learn(typo, replacement)
        self._recheck_spelling()

    def _add_word(self, word):
        self.spell.add_to_dictionary(word)
        self._recheck_spelling()

    # ---- Core actions -----------------------------------------------------

    def _ask(self):
        raw = self.input_text.get("1.0", "end-1c").strip()
        if not raw:
            self.pet_label.config(text="Tell me what you're working on first! 🐾")
            return
        self.cleaned = clean_text(raw, self.spell)
        self.rec = recommend(self.cleaned)

        self.dest_label.config(text=f"Destination: {DEST_LABELS[self.rec['destination']]}")
        self.reason_label.config(text=self.rec["reason"])
        self.template_var.set(PROMPT_TEMPLATES[self.rec["template"]]["name"])

        self.module_list.selection_clear(0, "end")
        module_keys = list(AGENT_MODULES.keys())
        for mk in self.rec["modules"]:
            self.module_list.selection_set(module_keys.index(mk))

        self.skill_list.selection_clear(0, "end")
        skill_keys = list(SKILL_TEMPLATES.keys())
        for sk in self.rec["skills"]:
            self.skill_list.selection_set(skill_keys.index(sk))

        for child in self.ctx_inner.winfo_children():
            child.destroy()
        self.ctx_vars = []
        for item in self.rec["checklist"][:8]:
            var = tk.BooleanVar(value=False)
            ttk.Checkbutton(self.ctx_inner, text=item, variable=var).pack(anchor="w")
            self.ctx_vars.append((var, item))

        self.pet_label.config(
            text=f'Got it! I read that as:\n"{self.cleaned}"\n\n'
                 f"I recommend {self.rec['destination']}. Adjust anything below, "
                 f"then hit Generate Prompt. 🐾"
        )

    def _generate(self):
        if not self.rec:
            self._ask()
            if not self.rec:
                return
        # Honor user adjustments
        name_to_key = {t["name"]: k for k, t in PROMPT_TEMPLATES.items()}
        chosen = name_to_key.get(self.template_var.get(), self.rec["template"])
        self.rec["template"] = chosen

        module_keys = list(AGENT_MODULES.keys())
        sel_modules = [module_keys[i] for i in self.module_list.curselection()]
        skill_keys = list(SKILL_TEMPLATES.keys())
        sel_skills = [skill_keys[i] for i in self.skill_list.curselection()]
        checked = [label for var, label in self.ctx_vars if var.get()]

        prompt = build_prompt(self.cleaned, self.rec, sel_modules, sel_skills, checked)
        self.output_text.delete("1.0", "end")
        self.output_text.insert("1.0", prompt)
        self.status_label.config(text="Prompt generated.")

    def _copy(self):
        text = self.output_text.get("1.0", "end-1c")
        if not text.strip():
            self.status_label.config(text="Nothing to copy yet.")
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.status_label.config(text="Copied to clipboard ✓")

    def _save(self):
        text = self.output_text.get("1.0", "end-1c")
        if not text.strip() or not self.rec:
            self.status_label.config(text="Generate a prompt first.")
            return
        raw = self.input_text.get("1.0", "end-1c").strip()
        save_history_entry(raw, self.cleaned, self.rec, text)
        self.status_label.config(text=f"Saved to {HISTORY_FILE}")

    def _clear(self):
        self.input_text.delete("1.0", "end")
        self.pet_label.config(text=PET_GREETING)

    def _show_help(self):
        win = tk.Toplevel(self.root)
        win.title("How to use PromptMate")
        win.geometry("560x520")
        txt = tk.Text(win, wrap="word", padx=10, pady=10, font=("Segoe UI", 10))
        txt.insert("1.0", HELP_TEXT)
        txt.config(state="disabled")
        txt.pack(fill="both", expand=True)

    # ---- Settings ----------------------------------------------------------

    def _load_settings(self):
        settings = load_json(SETTINGS_FILE, {})
        self.team_var.set(settings.get("team", "IT"))

    def _save_settings(self):
        # Merge, don't overwrite — the pet overlay stores its position here too.
        settings = load_json(SETTINGS_FILE, {})
        settings.update({"team": self.team_var.get(), "app_version": APP_VERSION})
        save_json(SETTINGS_FILE, settings)

    def on_close(self):
        self._save_settings()
        self.root.destroy()


# ---------------------------------------------------------------------------
# Desktop pet: sprite library, always-on-top overlay, chat window
# ---------------------------------------------------------------------------

# When frozen by PyInstaller, bundled data lives under sys._MEIPASS.
if getattr(sys, "frozen", False):
    ASSETS_DIR = Path(sys._MEIPASS) / "assets" / "kogi"
else:
    ASSETS_DIR = Path(__file__).resolve().parent / "assets" / "kogi"

# ---------------------------------------------------------------------------
# Pet store: download pets from codex-pets.net at the user's request.
#
# This is the ONLY network access in PromptMate, it never happens
# automatically, and nothing is sent except the download request itself.
# Sprites are user-uploaded artwork with no published license, so they are
# cached locally for personal use and never redistributed with the app;
# the creator's name is shown wherever the pet is offered or used.
# ---------------------------------------------------------------------------

PETS_DIR = DATA_DIR / "pets"
CODEX_PETS_BASE = "https://codex-pets.net"
KEY_COLOR = "#fe00fe"

# codex-pets.net validates spritesheets against a standard template, so row
# order is consistent across pets. Sheets with fewer rows just get fewer moves.
ROW_NAMES = ["idle", "walk_right", "walk_left", "wave", "run",
             "sleepy", "sit", "mosey", "emote"]


def _http_get(url: str, timeout: int = 30) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": f"{APP_NAME}/{APP_VERSION}"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def fetch_pet_page(page: int = 1) -> list:
    """Fetch one catalog page (30 pets) from codex-pets.net."""
    data = json.loads(_http_get(f"{CODEX_PETS_BASE}/api/pets?page={page}"))
    pets = data.get("pets", data if isinstance(data, list) else [])
    return [p for p in pets if not p.get("ownerShadowbanned")]


def fetch_pet_info(pet_id: str) -> dict:
    data = json.loads(_http_get(f"{CODEX_PETS_BASE}/api/pets/{pet_id}"))
    return data.get("pet", data)


def pet_credit(meta: dict) -> str:
    owner = meta.get("ownerName") or meta.get("ownerHandle") or "unknown creator"
    handle = meta.get("ownerHandle")
    if handle and handle != owner:
        return f"{owner} (@{handle})"
    return owner


def install_pet(pet_id: str, info: dict = None) -> Path:
    """Download a pet bundle, convert it for Tkinter, cache it locally.

    Returns the local pet directory. Requires Pillow for WebP conversion
    (bundled in the installed app; `pip install Pillow` when run from source).
    """
    try:
        from PIL import Image
    except ImportError:
        raise RuntimeError(
            "Switching pets needs the Pillow library to convert sprite "
            "images.\n\nRun:  pip install Pillow\n(The installed version of "
            "PromptMate includes it already.)")

    info = info or fetch_pet_info(pet_id)
    download_url = info.get("downloadUrl") or f"/api/pets/{pet_id}/download"
    if download_url.startswith("/"):
        download_url = CODEX_PETS_BASE + download_url
    bundle = zipfile.ZipFile(io.BytesIO(_http_get(download_url, timeout=120)))

    sheet_name = next((n for n in bundle.namelist() if n.endswith((".webp", ".png"))), None)
    if not sheet_name:
        raise RuntimeError("Pet bundle has no spritesheet.")
    src = Image.open(io.BytesIO(bundle.read(sheet_name))).convert("RGBA")

    report = info.get("validationReport") or {}
    try:
        cw, ch = (int(v) for v in report.get("cellSize", "").split("x"))
    except ValueError:
        # No cell size published: assume the standard 8x9 template grid.
        cw, ch = src.width // 8, src.height // 9
    cols, rows = src.width // cw, src.height // ch

    # Flatten alpha onto the key color (Windows transparency is color-keyed).
    key_rgb = tuple(int(KEY_COLOR[i:i + 2], 16) for i in (1, 3, 5))
    flat = Image.new("RGB", src.size, key_rgb)
    mask = src.getchannel("A").point(lambda a: 255 if a >= 96 else 0)
    flat.paste(src.convert("RGB"), (0, 0), mask)

    # Count non-empty frames per row.
    animations = {}
    for r in range(min(rows, len(ROW_NAMES))):
        n = 0
        for c in range(cols):
            cell = src.crop((c * cw, r * ch, (c + 1) * cw, (r + 1) * ch))
            if cell.getbbox() is None:  # fully transparent cell ends the row
                break
            n += 1
        if n:
            animations[ROW_NAMES[r]] = {"row": r, "frames": n}
    if not animations:
        raise RuntimeError("Spritesheet appears to be empty.")

    pet_dir = PETS_DIR / pet_id
    pet_dir.mkdir(parents=True, exist_ok=True)
    flat.save(pet_dir / "spritesheet.png", optimize=True)
    save_json(pet_dir / "manifest.json", {
        "cell_w": cw, "cell_h": ch, "key_color": KEY_COLOR,
        "animations": animations,
    })
    save_json(pet_dir / "pet.json", {
        "id": pet_id,
        "displayName": info.get("displayName", pet_id),
        "description": info.get("description", ""),
        "kind": info.get("kind", ""),
        "ownerName": info.get("ownerName"),
        "ownerHandle": info.get("ownerHandle"),
        "source": f"{CODEX_PETS_BASE}/#/pets/{pet_id}",
        "downloaded": datetime.now().isoformat(timespec="seconds"),
    })
    return pet_dir


def ensure_default_pet():
    """Seed the local pet cache with bundled Kogi on first run."""
    kogi_dir = PETS_DIR / "kogi"
    if (kogi_dir / "manifest.json").exists():
        return
    if not (ASSETS_DIR / "manifest.json").exists():
        return
    kogi_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy(ASSETS_DIR / "spritesheet.png", kogi_dir / "spritesheet.png")
    shutil.copy(ASSETS_DIR / "manifest.json", kogi_dir / "manifest.json")
    save_json(kogi_dir / "pet.json", {
        "id": "kogi", "displayName": "Kogi",
        "description": "A cheerful chibi corgi with rhythmic moseying steps.",
        "kind": "animal", "ownerName": "Daichi", "ownerHandle": "daichi",
        "source": f"{CODEX_PETS_BASE}/#/pets/kogi",
    })


def local_pet_dir(pet_id: str) -> Path:
    """Resolve a pet id to a usable local directory (cache, then bundled)."""
    pet_dir = PETS_DIR / pet_id
    if (pet_dir / "manifest.json").exists():
        return pet_dir
    return ASSETS_DIR


class SpellSupport:
    """Attach red-underline spellcheck + right-click suggestions to a tk.Text."""

    def __init__(self, text_widget: tk.Text, spell: SpellHelper):
        self.text = text_widget
        self.spell = spell
        text_widget.tag_configure("misspelled", underline=True, foreground="red")
        text_widget.bind("<KeyRelease>", self._on_key_release, add="+")
        text_widget.bind("<Button-3>", self._on_right_click, add="+")

    def _on_key_release(self, event=None):
        if event and event.keysym in ("Up", "Down", "Left", "Right", "Shift_L", "Shift_R"):
            return
        self.recheck()

    def recheck(self):
        text = self.text.get("1.0", "end-1c")
        self.text.tag_remove("misspelled", "1.0", "end")
        for m in re.finditer(r"[A-Za-z]+", text):
            if not self.spell.known(m.group(0)):
                self.text.tag_add("misspelled", f"1.0+{m.start()}c", f"1.0+{m.end()}c")

    def _on_right_click(self, event):
        index = self.text.index(f"@{event.x},{event.y}")
        start = self.text.index(f"{index} wordstart")
        end = self.text.index(f"{index} wordend")
        word = self.text.get(start, end)
        if not word.isalpha() or self.spell.known(word):
            return
        menu = tk.Menu(self.text, tearoff=0)
        suggestions = self.spell.suggestions(word)
        if suggestions:
            for s in suggestions:
                menu.add_command(label=s, command=lambda s=s: self._replace(start, end, word, s))
            menu.add_separator()
        else:
            menu.add_command(label="(no suggestions)", state="disabled")
            menu.add_separator()
        menu.add_command(label=f'Add "{word}" to dictionary', command=lambda: self._add(word))
        menu.tk_popup(event.x_root, event.y_root)

    def _replace(self, start, end, typo, replacement):
        self.text.delete(start, end)
        self.text.insert(start, replacement)
        self.spell.learn(typo, replacement)
        self.recheck()

    def _add(self, word):
        self.spell.add_to_dictionary(word)
        self.recheck()


class SpriteLibrary:
    """Load the kogi spritesheet and slice it into per-animation frame lists."""

    def __init__(self, pet_dir: Path, scale: int = 1):
        self.ok = False
        self.frames = {}
        self.key = KEY_COLOR
        self.w, self.h = 96, 104
        manifest = load_json(pet_dir / "manifest.json", None)
        sheet_path = pet_dir / "spritesheet.png"
        if not manifest or not sheet_path.exists():
            return
        try:
            sheet = tk.PhotoImage(file=str(sheet_path))
        except tk.TclError:
            return
        cw, ch = manifest["cell_w"], manifest["cell_h"]
        self.key = manifest.get("key_color", self.key)
        for name, anim in manifest["animations"].items():
            row, count = anim["row"], anim["frames"]
            frames = []
            for col in range(count):
                img = tk.PhotoImage()
                img.tk.call(img, "copy", sheet, "-from",
                            col * cw, row * ch, (col + 1) * cw, (row + 1) * ch,
                            "-to", 0, 0)
                if scale > 1:
                    img = img.subsample(scale, scale)
                frames.append(img)
            if frames:
                self.frames[name] = frames
        self.w, self.h = cw // scale, ch // scale
        self.ok = bool(self.frames)


class PetOverlay:
    """Kogi the desktop pet: borderless, transparent, always on top.

    Left-click toggles the chat window; drag to move; right-click for menu.
    Wanders/waves on its own while the chat is closed, sits while it is open.
    """

    TICK_MS = 140
    WALK_SPEED = 4

    def __init__(self, root: tk.Tk):
        self.root = root
        self.spell = SpellHelper()
        self.chat = None
        self.editor = None
        self.settings = load_json(SETTINGS_FILE, {})

        ensure_default_pet()
        self.scale = max(1, int(self.settings.get("pet_scale", 1)))
        self.pet_id = self.settings.get("pet_id", "kogi")
        self.pet_dir = local_pet_dir(self.pet_id)
        self.pet_meta = load_json(self.pet_dir / "pet.json",
                                  {"id": self.pet_id, "displayName": self.pet_id.title()})
        self.sprites = SpriteLibrary(self.pet_dir, scale=self.scale)
        w, h = self.sprites.w, self.sprites.h

        root.overrideredirect(True)
        root.wm_attributes("-topmost", True)
        key = self.sprites.key
        if sys.platform == "win32":
            root.wm_attributes("-transparentcolor", key)
        elif sys.platform == "darwin":
            try:
                root.wm_attributes("-transparent", True)
                key = "systemTransparent"
            except tk.TclError:
                pass

        self.canvas = tk.Canvas(root, width=w, height=h, bg=key,
                                highlightthickness=0, cursor="hand2")
        self.canvas.pack()
        self.sprite_item = None
        if self.sprites.ok:
            self.sprite_item = self.canvas.create_image(0, 0, anchor="nw")
        else:
            # Fallback pet if assets are missing: a simple drawn dog.
            self.canvas.create_oval(18, 38, 78, 92, fill="#e8a33d", outline="#5a3d1a", width=2)
            self.canvas.create_polygon(24, 44, 18, 18, 42, 36, fill="#e8a33d", outline="#5a3d1a")
            self.canvas.create_polygon(72, 44, 78, 18, 54, 36, fill="#e8a33d", outline="#5a3d1a")
            self.canvas.create_oval(36, 54, 44, 62, fill="#222")
            self.canvas.create_oval(54, 54, 62, 62, fill="#222")
            self.canvas.create_oval(44, 66, 54, 74, fill="#222")

        # Start position: saved, else bottom-right above the taskbar.
        sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
        x = int(self.settings.get("pet_x", sw - w - 80))
        y = int(self.settings.get("pet_y", sh - h - 120))
        x = min(max(0, x), sw - w)
        y = min(max(0, y), sh - h)
        root.geometry(f"{w}x{h}+{x}+{y}")

        # Interaction state
        self._press_xy = None
        self._dragging = False
        self.canvas.bind("<ButtonPress-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_motion)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.canvas.bind("<Button-3>", self._on_menu)

        # Animation / behavior state
        self.anim = "wave"  # greet on launch
        self.frame_i = 0
        self.move_dx = 0
        self.behavior_ticks = len(self.anim_frames()) * 2
        self.wander = bool(self.settings.get("pet_wander", True))

        self._tick()

    # ---- animation engine -------------------------------------------------

    def anim_frames(self):
        if not self.sprites.ok:
            return [None]
        return self.sprites.frames.get(self.anim) or next(iter(self.sprites.frames.values()))

    def set_anim(self, name, move_dx=0, ticks=None):
        if self.sprites.ok and name not in self.sprites.frames:
            name = "idle"
        self.anim = name
        self.frame_i = 0
        self.move_dx = move_dx
        self.behavior_ticks = ticks if ticks is not None else len(self.anim_frames()) * 3

    def _tick(self):
        frames = self.anim_frames()
        if self.sprites.ok:
            frame = frames[self.frame_i % len(frames)]
            self.canvas.itemconfigure(self.sprite_item, image=frame)
        self.frame_i += 1

        if self.move_dx and not self._dragging:
            x = self.root.winfo_x() + self.move_dx
            y = self.root.winfo_y()
            sw = self.root.winfo_screenwidth()
            if x <= 0 or x >= sw - self.sprites.w:
                self.move_dx = -self.move_dx
                self.set_anim("walk_right" if self.move_dx > 0 else "walk_left",
                              move_dx=self.move_dx, ticks=self.behavior_ticks)
                x = min(max(0, x), sw - self.sprites.w)
            self.root.geometry(f"+{x}+{y}")

        self.behavior_ticks -= 1
        if self.behavior_ticks <= 0 and not self._dragging:
            self._choose_behavior()

        self.root.after(self.TICK_MS, self._tick)

    def _choose_behavior(self):
        if self.chat and self.chat.is_open():
            # Listening pose while the chat is open.
            self.set_anim("sit", ticks=random.randint(30, 60))
            return
        if not self.wander:
            self.set_anim("idle", ticks=random.randint(30, 80))
            return
        roll = random.random()
        if roll < 0.45:
            self.set_anim("idle", ticks=random.randint(25, 70))
        elif roll < 0.60:
            self.set_anim("sit", ticks=random.randint(25, 60))
        elif roll < 0.72:
            self.set_anim("wave", ticks=len(self.sprites.frames.get("wave", [1])) * 2)
        elif roll < 0.82:
            self.set_anim("emote", ticks=random.randint(12, 24))
        else:
            direction = random.choice((-1, 1))
            self.set_anim("walk_right" if direction > 0 else "walk_left",
                          move_dx=direction * self.WALK_SPEED,
                          ticks=random.randint(20, 60))

    # ---- mouse interaction --------------------------------------------------

    def _on_press(self, event):
        self._press_xy = (event.x_root, event.y_root)
        self._win_xy = (self.root.winfo_x(), self.root.winfo_y())
        self._dragging = False

    def _on_motion(self, event):
        if not self._press_xy:
            return
        dx = event.x_root - self._press_xy[0]
        dy = event.y_root - self._press_xy[1]
        if abs(dx) > 4 or abs(dy) > 4:
            self._dragging = True
        if self._dragging:
            self.root.geometry(f"+{self._win_xy[0] + dx}+{self._win_xy[1] + dy}")

    def _on_release(self, event):
        if self._dragging:
            self._save_position()
        else:
            self.toggle_chat()
        self._press_xy = None
        self._dragging = False

    def _on_menu(self, event):
        menu = tk.Menu(self.root, tearoff=0)
        menu.add_command(label="💬 Open chat", command=self.toggle_chat)
        menu.add_command(label="🛠 Open full editor", command=self.open_editor)
        menu.add_separator()
        menu.add_command(label="🔄 Change pet…", command=self.open_pet_browser)
        menu.add_command(label=f"ℹ About {self.pet_name()}", command=self.show_pet_credit)
        menu.add_separator()
        label = "Stop wandering" if self.wander else "Allow wandering"
        menu.add_command(label=f"🐾 {label}", command=self._toggle_wander)
        menu.add_separator()
        menu.add_command(label="❌ Exit PromptMate", command=self.quit)
        menu.tk_popup(event.x_root, event.y_root)

    def pet_name(self) -> str:
        return self.pet_meta.get("displayName") or self.pet_id.title()

    def show_pet_credit(self):
        m = self.pet_meta
        lines = [m.get("displayName", self.pet_id)]
        if m.get("description"):
            lines.append(m["description"])
        lines.append("")
        lines.append(f"Created by {pet_credit(m)}")
        if m.get("source"):
            lines.append(m["source"])
        messagebox.showinfo("About this pet", "\n".join(lines), parent=self.root)

    def open_pet_browser(self):
        PetBrowser(self)

    def switch_pet(self, pet_id: str):
        """Reload sprites for a newly selected pet and resize the overlay."""
        self.pet_id = pet_id
        self.pet_dir = local_pet_dir(pet_id)
        self.pet_meta = load_json(self.pet_dir / "pet.json",
                                  {"id": pet_id, "displayName": pet_id.title()})
        self.sprites = SpriteLibrary(self.pet_dir, scale=self.scale)
        w, h = self.sprites.w, self.sprites.h
        self.canvas.delete("all")
        self.canvas.config(width=w, height=h)
        self.sprite_item = self.canvas.create_image(0, 0, anchor="nw") if self.sprites.ok else None
        x, y = self.root.winfo_x(), self.root.winfo_y()
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        self.root.geometry(f"{w}x{h}+{min(x, sw - w)}+{min(y, sh - h)}")
        self.set_anim("wave")
        self.settings["pet_id"] = pet_id
        self._save_settings()
        if self.chat and self.chat.is_open():
            self.chat.on_pet_changed()

    def _toggle_wander(self):
        self.wander = not self.wander
        self.move_dx = 0
        self.set_anim("idle")
        self._save_settings()

    # ---- windows -------------------------------------------------------------

    def toggle_chat(self):
        if self.chat and self.chat.is_open():
            self.chat.close()
            return
        self.chat = ChatWindow(self)
        self.set_anim("sit", ticks=40)

    def open_editor(self, prefill: str = ""):
        if self.editor and self.editor.root.winfo_exists():
            self.editor.root.deiconify()
            self.editor.root.lift()
        else:
            win = tk.Toplevel(self.root)
            self.editor = PromptMateApp(win)
            win.protocol("WM_DELETE_WINDOW", win.destroy)
        if prefill:
            self.editor.input_text.delete("1.0", "end")
            self.editor.input_text.insert("1.0", prefill)
            self.editor._recheck_spelling()
            self.editor._ask()

    # ---- persistence -----------------------------------------------------------

    def _save_position(self):
        self.settings["pet_x"] = self.root.winfo_x()
        self.settings["pet_y"] = self.root.winfo_y()
        self._save_settings()

    def _save_settings(self):
        self.settings["pet_wander"] = self.wander
        self.settings["app_version"] = APP_VERSION
        save_json(SETTINGS_FILE, self.settings)

    def quit(self):
        self._save_position()
        self.root.destroy()


class PetBrowser:
    """Browse codex-pets.net and switch the desktop pet.

    The catalog and pet bundles are fetched from codex-pets.net only when the
    user asks. Creators are credited next to every pet.
    """

    def __init__(self, pet: PetOverlay):
        self.pet = pet
        self.page = 0
        self.catalog = []  # raw pet dicts from the API

        win = tk.Toplevel(pet.root)
        self.win = win
        win.title("Change pet — codex-pets.net")
        win.geometry("560x480")
        win.wm_attributes("-topmost", True)

        top = ttk.Frame(win, padding=6)
        top.pack(fill="x")
        ttk.Label(top, text="Search:").pack(side="left")
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *_: self._refresh_list())
        ttk.Entry(top, textvariable=self.search_var).pack(side="left", fill="x",
                                                          expand=True, padx=6)
        ttk.Button(top, text="Load more pets", command=self.load_more).pack(side="left")

        cols = ("name", "creator", "kind")
        self.tree = ttk.Treeview(win, columns=cols, show="headings", height=12)
        for col, label, width in (("name", "Pet", 180), ("creator", "Creator", 180),
                                  ("kind", "Kind", 120)):
            self.tree.heading(col, text=label)
            self.tree.column(col, width=width)
        self.tree.pack(fill="both", expand=True, padx=6)
        self.tree.bind("<<TreeviewSelect>>", self._on_select)

        self.detail = ttk.Label(win, text="Pets are downloaded from codex-pets.net "
                                          "only when you pick one, and cached locally.",
                                wraplength=520, justify="left", padding=6)
        self.detail.pack(fill="x")

        btns = ttk.Frame(win, padding=6)
        btns.pack(fill="x")
        self.use_btn = ttk.Button(btns, text="⬇ Download && use this pet",
                                  command=self.use_selected, state="disabled")
        self.use_btn.pack(side="left")
        self.page_btn = ttk.Button(btns, text="🌐 View on codex-pets.net",
                                   command=self.open_page, state="disabled")
        self.page_btn.pack(side="left", padx=6)
        self.status = ttk.Label(btns, text="")
        self.status.pack(side="left", padx=8)

        self.load_more()

    # ---- catalog -----------------------------------------------------------

    def load_more(self):
        self.status.config(text="Loading catalog…")
        self.win.update_idletasks()
        try:
            self.page += 1
            self.catalog.extend(fetch_pet_page(self.page))
            self.status.config(text=f"{len(self.catalog)} pets loaded")
        except (urllib.error.URLError, OSError, ValueError) as e:
            self.page -= 1
            self.status.config(text="Couldn't reach codex-pets.net")
            messagebox.showerror("Network error",
                                 f"Couldn't load the pet catalog:\n{e}", parent=self.win)
        self._refresh_list()

    def _refresh_list(self):
        query = self.search_var.get().strip().lower()
        self.tree.delete(*self.tree.get_children())
        seen = set()
        for p in self.catalog:
            if p["id"] in seen:
                continue
            seen.add(p["id"])
            label = f"{p.get('displayName', p['id'])} {p.get('ownerName', '')} {p.get('ownerHandle', '')}"
            if query and query not in label.lower():
                continue
            self.tree.insert("", "end", iid=p["id"],
                             values=(p.get("displayName", p["id"]),
                                     pet_credit(p), p.get("kind", "")))

    def _selected(self):
        sel = self.tree.selection()
        if not sel:
            return None
        return next((p for p in self.catalog if p["id"] == sel[0]), None)

    def _on_select(self, event=None):
        p = self._selected()
        if not p:
            return
        self.use_btn.config(state="normal")
        self.page_btn.config(state="normal")
        desc = p.get("description", "")
        self.detail.config(text=f"{p.get('displayName', p['id'])} — by {pet_credit(p)}\n{desc}")

    # ---- actions -----------------------------------------------------------

    def open_page(self):
        p = self._selected()
        if p:
            webbrowser.open(f"{CODEX_PETS_BASE}/#/pets/{p['id']}")

    def use_selected(self):
        p = self._selected()
        if not p:
            return
        self.status.config(text=f"Downloading {p.get('displayName', p['id'])}…")
        self.use_btn.config(state="disabled")
        self.win.update_idletasks()
        try:
            install_pet(p["id"], info=p)
            self.pet.switch_pet(p["id"])
            self.status.config(text=f"Now using {p.get('displayName', p['id'])} "
                                    f"by {pet_credit(p)} 🐾")
        except RuntimeError as e:
            messagebox.showerror("Can't switch pet", str(e), parent=self.win)
            self.status.config(text="")
        except (urllib.error.URLError, OSError, ValueError, zipfile.BadZipFile) as e:
            messagebox.showerror("Download failed",
                                 f"Couldn't download this pet:\n{e}", parent=self.win)
            self.status.config(text="")
        finally:
            self.use_btn.config(state="normal")


CHAT_GREETING = (
    "Hi! Tell me what you're working on — typos and shorthand are fine. "
    "I'll build you a copy-ready prompt and tell you whether it belongs in "
    "Codex, Claude Code, ChatGPT, or Claude."
)


class ChatWindow:
    """iMessage-style chat window opened by clicking the pet."""

    BG = "#ffffff"
    USER_BUBBLE = "#0b93f6"
    PET_BUBBLE = "#e9e9eb"
    CAPTION = "#8e8e93"
    WIDTH = 420

    def __init__(self, pet: PetOverlay):
        self.pet = pet
        self.spell = pet.spell
        self.last = None  # (raw, cleaned, rec, prompt)
        self._y = 12       # layout cursor in the canvas
        self._typing_items = []

        win = tk.Toplevel(pet.root)
        self.win = win
        win.title(f"{pet.pet_name()} — PromptMate")
        win.wm_attributes("-topmost", True)
        win.resizable(False, True)
        self._place_near_pet(self.WIDTH, 580)
        win.configure(bg=self.BG)

        # Conversation canvas
        log_frame = tk.Frame(win, bg=self.BG)
        log_frame.pack(fill="both", expand=True)
        self.canvas = tk.Canvas(log_frame, bg=self.BG, highlightthickness=0,
                                width=self.WIDTH)
        scroll = ttk.Scrollbar(log_frame, command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind_all("<MouseWheel>", self._on_wheel)

        # Input row: rounded-feel entry + round blue send button
        input_frame = tk.Frame(win, bg=self.BG, padx=8, pady=8)
        input_frame.pack(fill="x")
        entry_holder = tk.Frame(input_frame, bg="#d1d1d6", padx=1, pady=1)
        entry_holder.pack(side="left", fill="both", expand=True)
        self.entry = tk.Text(entry_holder, height=2, wrap="word", relief="flat",
                             font=("Segoe UI", 10), undo=True, padx=8, pady=6)
        self.entry.pack(fill="both", expand=True)
        SpellSupport(self.entry, self.spell)
        self.entry.bind("<Return>", self._on_return)
        send_btn = tk.Button(input_frame, text="↑", command=self.send,
                             bg=self.USER_BUBBLE, fg="white", relief="flat",
                             font=("Segoe UI", 13, "bold"), width=3, cursor="hand2",
                             activebackground="#0a84d0", activeforeground="white")
        send_btn.pack(side="left", padx=(8, 0))

        self._caption(datetime.now().strftime("Today %H:%M"))
        self._pet_bubble(CHAT_GREETING)
        self.entry.focus_set()

    def _place_near_pet(self, w, h):
        px, py = self.pet.root.winfo_x(), self.pet.root.winfo_y()
        sw, sh = self.win.winfo_screenwidth(), self.win.winfo_screenheight()
        x = px - w - 12 if px > sw // 2 else px + self.pet.sprites.w + 12
        y = py + self.pet.sprites.h - h
        x = min(max(8, x), sw - w - 8)
        y = min(max(8, y), sh - h - 60)
        self.win.geometry(f"{w}x{h}+{x}+{y}")

    def is_open(self):
        return self.win.winfo_exists()

    def close(self):
        if self.is_open():
            self.win.destroy()

    def on_pet_changed(self):
        self.win.title(f"{self.pet.pet_name()} — PromptMate")
        self._caption(f"{self.pet.pet_name()} joined the chat "
                      f"(art by {pet_credit(self.pet.pet_meta)})")
        self._pet_bubble("New look, same PromptMate! What are we working on?")

    # ---- bubble drawing -----------------------------------------------------

    def _on_wheel(self, event):
        if self.is_open():
            self.canvas.yview_scroll(-1 * (event.delta // 120), "units")

    def _round_rect(self, x1, y1, x2, y2, r=14, **kw):
        pts = [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2,
               x2 - r, y2, x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]
        return self.canvas.create_polygon(pts, smooth=True, **kw)

    def _finish(self, bottom):
        self._y = bottom + 8
        self.canvas.configure(scrollregion=(0, 0, self.WIDTH, self._y))
        self.canvas.yview_moveto(1.0)

    def _caption(self, text):
        item = self.canvas.create_text(self.WIDTH // 2, self._y + 4, text=text,
                                       fill=self.CAPTION, font=("Segoe UI", 8),
                                       anchor="n", width=self.WIDTH - 60,
                                       justify="center")
        self._finish(self.canvas.bbox(item)[3])

    def _bubble(self, text, side, fill, fg, font=("Segoe UI", 10), pad=10):
        maxw = int(self.WIDTH * 0.74)
        tmp = self.canvas.create_text(0, -10000, text=text, font=font,
                                      width=maxw, anchor="nw")
        x1, y1, x2, y2 = self.canvas.bbox(tmp)
        tw, th = x2 - x1, y2 - y1
        self.canvas.delete(tmp)

        if side == "right":
            bx2 = self.WIDTH - 24
            bx1 = bx2 - tw - 2 * pad
        else:
            bx1 = 12
            bx2 = bx1 + tw + 2 * pad
        by1, by2 = self._y, self._y + th + 2 * pad
        self._round_rect(bx1, by1, bx2, by2, r=15, fill=fill, outline=fill)
        self.canvas.create_text(bx1 + pad, by1 + pad, text=text, font=font,
                                fill=fg, width=maxw, anchor="nw")
        self._finish(by2)
        return by2

    def _pet_bubble(self, text):
        self._bubble(text, "left", self.PET_BUBBLE, "#000000")

    def _user_bubble(self, text):
        self._bubble(text, "right", self.USER_BUBBLE, "#ffffff")

    def _prompt_bubble(self, prompt):
        self._bubble(prompt, "left", "#f2f2f7", "#1c1c1e", font=("Consolas", 8))
        btns = tk.Frame(self.canvas, bg=self.BG)
        for label, cmd in (("📋 Copy", self._copy_last), ("💾 Save", self._save_last),
                           ("🛠 Adjust in editor", self._open_in_editor)):
            ttk.Button(btns, text=label, command=cmd).pack(side="left", padx=(0, 4))
        item = self.canvas.create_window(12, self._y, window=btns, anchor="nw")
        self.win.update_idletasks()
        self._finish(self.canvas.bbox(item)[3])

    def _show_typing(self):
        item = self._round_rect(12, self._y, 64, self._y + 30, r=15,
                                fill=self.PET_BUBBLE, outline=self.PET_BUBBLE)
        dots = self.canvas.create_text(38, self._y + 15, text="• • •",
                                       fill=self.CAPTION, font=("Segoe UI", 9))
        self._typing_items = [item, dots]
        self._typing_y = self._y
        self._finish(self._y + 30)

    def _hide_typing(self):
        for item in self._typing_items:
            self.canvas.delete(item)
        self._typing_items = []
        self._y = self._typing_y

    # ---- actions ----------------------------------------------------------

    def _on_return(self, event):
        if event.state & 0x0001:  # Shift+Return -> newline
            return None
        self.send()
        return "break"

    def send(self):
        raw = self.entry.get("1.0", "end-1c").strip()
        if not raw:
            return
        self.entry.delete("1.0", "end")
        self._user_bubble(raw)

        cleaned = clean_text(raw, self.spell)
        rec = recommend(cleaned)
        prompt = build_prompt(cleaned, rec, rec["modules"], rec["skills"], [])
        self.last = (raw, cleaned, rec, prompt)

        self._show_typing()
        self.win.after(random.randint(500, 900), lambda: self._deliver_reply(cleaned, rec, prompt))

    def _deliver_reply(self, cleaned, rec, prompt):
        if not self.is_open():
            return
        self._hide_typing()
        template_name = PROMPT_TEMPLATES[rec["template"]]["name"]
        module_names = ", ".join(AGENT_MODULES[m]["name"] for m in rec["modules"])
        self._pet_bubble(f"Got it! I read that as:\n“{cleaned}”")
        self._pet_bubble(f"➜ Send it to: {DEST_LABELS[rec['destination']]}\n{rec['reason']}")
        details = f"Template: {template_name}\nModules: {module_names}"
        if rec["checklist"]:
            hints = "\n".join(f"• {c}" for c in rec["checklist"][:5])
            details += f"\n\nIt'll work better if you paste in:\n{hints}"
        self._pet_bubble(details)
        self._prompt_bubble(prompt)

    def _copy_last(self):
        if not self.last:
            return
        self.win.clipboard_clear()
        self.win.clipboard_append(self.last[3])
        self._pet_bubble("Copied! Paste it into Codex, Claude Code, ChatGPT, or Claude. ✅")

    def _save_last(self):
        if not self.last:
            return
        raw, cleaned, rec, prompt = self.last
        save_history_entry(raw, cleaned, rec, prompt)
        self._pet_bubble("Saved to your local history. 💾")

    def _open_in_editor(self):
        if self.last:
            self.pet.open_editor(prefill=self.last[0])


def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    root = tk.Tk()
    try:
        style = ttk.Style(root)
        if "vista" in style.theme_names():
            style.theme_use("vista")
        elif "aqua" in style.theme_names():
            style.theme_use("aqua")
    except tk.TclError:
        pass

    if "--editor" in sys.argv:
        app = PromptMateApp(root)
        root.protocol("WM_DELETE_WINDOW", app.on_close)
    else:
        PetOverlay(root)
    root.mainloop()


if __name__ == "__main__":
    main()
