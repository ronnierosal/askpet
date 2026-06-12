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
APP_VERSION = "0.3.0"
CONTENT_VERSION = "2026.06.3"

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
    "query": 2, "kql": 2, "sql": 2, "automate": 3, "scaffold": 2,
}

CHATGPT_SIGNALS = {
    "plan": 3, "planning": 3, "architecture": 3, "design": 2, "strategy": 3,
    "analysis": 3, "analyze": 3, "document": 2, "documentation": 3,
    "draft": 2, "write": 1, "summary": 2, "summarize": 2, "review": 2,
    "refine": 3, "advice": 3, "advise": 3, "explain": 2, "compare": 2,
    "ticket": 2, "jira": 2, "confluence": 3, "runbook": 2, "policy": 2,
    "audit": 2, "evidence": 2, "process": 1, "workflow": 1, "agent": 2,
    "postmortem": 3, "rca": 3, "communicate": 2, "announce": 2,
    "investigate": 2, "triage": 2, "risk": 2, "recommend": 2,
}

KEYWORD_TOPICS = {
    "azure_function": ["azure function", "azure functions", "function app"],
    "intune": ["intune", "autopilot", "enrollment", "device compliance"],
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
    "incident": ["incident", "outage", "is down", "sev1", "sev 1", "p1",
                 "root cause", "postmortem", "post-mortem", "rca"],
    "onboarding": ["onboarding", "offboarding", "new hire", "new starter",
                   "leaver", "termination", "terminated"],
    "security": ["security", "phishing", "phish", "vulnerability", "cve",
                 "patch", "patching", "defender", "compromise", "breach"],
    "change": ["change request", "change window", "cab", "maintenance window",
               "communication", "announce", "notify users"],
    "network": ["network", "vpn", "dns", "firewall", "dhcp", "wifi", "wi-fi",
                "switch port", "certificate expired", "latency"],
    "monitoring": ["monitoring", "alert", "alerts", "log analytics", "kql",
                   "sentinel", "splunk", "dashboard"],
    "reporting": ["report", "reporting", "metrics", "kpi", "export",
                  "spreadsheet", "license count", "licenses", "csv", "bulk"],
    "backup": ["backup", "backups", "restore", "disaster recovery",
               "recovery point", "snapshot"],
    "vendor": ["vendor", "support case", "open a case", "escalate",
               "microsoft support", "evaluate", "evaluation", "compare tools"],
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
    "powershell_script": {
        "name": "PowerShell script",
        "destination": "Codex",
        "topics": ["powershell"],
        "body": (
            "Write a PowerShell script. {TASK}\n\n"
            "Requirements:\n- Parameters with validation, no hardcoded values\n"
            "- Idempotent: safe to run twice\n"
            "- -WhatIf support on anything destructive\n"
            "- try/catch with actionable errors; transcript or log output\n"
            "- Inputs: {INPUTS}\n- Constraints: {CONSTRAINTS}\n\n"
            "Test against ONE object first and show me the output before "
            "widening scope.\n\nVerification: {VERIFICATION}"
        ),
    },
    "incident_response": {
        "name": "Incident response (live)",
        "destination": "Both",
        "topics": ["incident"],
        "body": (
            "I have a live incident. {TASK}\n\n"
            "Help me in this order:\n"
            "1. Triage questions to size the impact fast\n"
            "2. Most likely causes ranked by probability\n"
            "3. Mitigation options (rollback/failover/restart) before root cause\n"
            "4. A status-update draft for affected users\n"
            "5. What evidence to capture for the postmortem while we work\n\n"
            "Known so far: {INPUTS}\nConstraints: {CONSTRAINTS}"
        ),
    },
    "incident_rca": {
        "name": "Root-cause analysis / postmortem",
        "destination": "ChatGPT web",
        "topics": ["incident"],
        "body": (
            "Write a blameless postmortem. {TASK}\n\n"
            "Timeline and facts: {INPUTS}\n\n"
            "Produce:\n- Executive summary (3 sentences)\n"
            "- Timeline (detection → mitigation → resolution)\n"
            "- Root cause via 5-whys; separate trigger from underlying cause\n"
            "- What went well / what failed\n"
            "- Action items with owners and due dates\n\n"
            "Keep it factual and blameless. Constraints: {CONSTRAINTS}"
        ),
    },
    "onboarding_runbook": {
        "name": "On/offboarding runbook",
        "destination": "Both",
        "topics": ["onboarding"],
        "body": (
            "Build an on/offboarding runbook or automate part of it. {TASK}\n\n"
            "Cover: identity lifecycle, licenses, group-based access, device "
            "enrollment/wipe, mailbox/data handling, and per-step verification "
            "with evidence capture.\n\n"
            "Systems in scope: {INPUTS}\nConstraints: {CONSTRAINTS}\n"
            "Verification: {VERIFICATION}"
        ),
    },
    "entra_access_change": {
        "name": "Entra/Okta access change",
        "destination": "Both",
        "topics": ["entra", "okta"],
        "body": (
            "Help me make an identity/access change safely. {TASK}\n\n"
            "Requirements:\n- Prefer group-based assignment over direct grants\n"
            "- Least privilege; note any standing-access alternatives (PIM/JIT)\n"
            "- Before/after evidence capture\n- Rollback steps\n\n"
            "Scope: {INPUTS}\nConstraints: {CONSTRAINTS}\n"
            "Verification: {VERIFICATION}"
        ),
    },
    "m365_admin": {
        "name": "Microsoft 365 admin task",
        "destination": "Both",
        "topics": ["m365"],
        "body": (
            "Microsoft 365 administration task. {TASK}\n\n"
            "Provide:\n- Admin-center steps AND the PowerShell equivalent\n"
            "- Tenant-wide vs scoped options, and what each affects\n"
            "- Propagation/latency expectations\n- Rollback steps\n\n"
            "Tenant context: {INPUTS}\nConstraints: {CONSTRAINTS}\n"
            "Verification: {VERIFICATION}"
        ),
    },
    "mailflow": {
        "name": "Mail-flow troubleshooting",
        "destination": "Both",
        "topics": ["m365"],
        "body": (
            "Troubleshoot a mail-flow problem. {TASK}\n\n"
            "Walk me through:\n- Message-trace strategy for concrete failing examples\n"
            "- The hop-by-hop checks (transport rules, connectors, spam verdicts, "
            "SPF/DKIM/DMARC, DNS)\n- Most likely causes for these symptoms, ranked\n"
            "- The fix and how to re-verify with the same trace\n\n"
            "Symptoms and scope: {INPUTS}\nConstraints: {CONSTRAINTS}"
        ),
    },
    "network_troubleshoot": {
        "name": "Network troubleshooting",
        "destination": "Both",
        "topics": ["network"],
        "body": (
            "Troubleshoot a network issue layer by layer. {TASK}\n\n"
            "Give me:\n- An isolation plan: DNS → reachability → port → application\n"
            "- Exact commands to run at each layer and what good/bad output looks like\n"
            "- Likely causes ranked for these symptoms\n"
            "- What recent-change types to check (firewall, DNS, certs)\n\n"
            "Failing path and symptoms: {INPUTS}\nConstraints: {CONSTRAINTS}"
        ),
    },
    "change_request": {
        "name": "Change request (CAB)",
        "destination": "ChatGPT web",
        "topics": ["change"],
        "body": (
            "Draft a CAB-ready change request. {TASK}\n\n"
            "Sections:\n- Summary and business justification\n"
            "- Implementation plan with timings and owners\n"
            "- Risk assessment and blast radius\n"
            "- Rollback plan and point of no return\n"
            "- Validation plan (how we know it worked)\n"
            "- Communication plan (who is told, when)\n\n"
            "Change details: {INPUTS}\nConstraints: {CONSTRAINTS}"
        ),
    },
    "log_query": {
        "name": "Log/data query (KQL or SQL)",
        "destination": "Codex",
        "topics": ["monitoring", "reporting"],
        "body": (
            "Write a query for me. {TASK}\n\n"
            "- Source/tables: {INPUTS}\n- Constraints: {CONSTRAINTS}\n\n"
            "Build it incrementally (filter → aggregate → format), explain each "
            "clause, and include a sanity check I can run to validate the "
            "numbers against a known reference.\n\nVerification: {VERIFICATION}"
        ),
    },
    "monitoring_alert": {
        "name": "Monitoring / alert design",
        "destination": "Both",
        "topics": ["monitoring"],
        "body": (
            "Design monitoring/alerting. {TASK}\n\n"
            "For each alert:\n- The exact condition and threshold, with rationale\n"
            "- Severity mapped to real impact\n- Who gets it and via what channel\n"
            "- The responder action (link a runbook)\n- How to test-fire it\n\n"
            "Avoid alert fatigue: justify why each alert deserves a human's "
            "attention.\n\nSystems: {INPUTS}\nConstraints: {CONSTRAINTS}"
        ),
    },
    "security_review": {
        "name": "Security review / analysis",
        "destination": "ChatGPT web",
        "topics": ["security"],
        "body": (
            "Security analysis task. {TASK}\n\n"
            "Provide:\n- Assessment of the risk and who/what is exposed\n"
            "- Immediate containment steps, ordered\n"
            "- Follow-up hardening recommendations with effort estimates\n"
            "- What to capture as evidence for the record\n\n"
            "Details: {INPUTS}\nConstraints: {CONSTRAINTS}"
        ),
    },
    "script_review": {
        "name": "Script/code review",
        "destination": "Codex",
        "topics": ["powershell"],
        "body": (
            "Review this script/code before I run it in production. {TASK}\n\n"
            "Check for:\n- Destructive operations without guards or -WhatIf\n"
            "- Missing error handling and silent failures\n"
            "- Hardcoded credentials/values that should be parameters\n"
            "- Idempotency: what happens if it runs twice\n"
            "- Scope: could it touch more objects than intended\n\n"
            "Give findings ranked by risk, with the fix for each.\n"
            "Constraints: {CONSTRAINTS}"
        ),
    },
    "comms_draft": {
        "name": "User communication draft",
        "destination": "ChatGPT web",
        "topics": ["change", "incident"],
        "body": (
            "Draft a communication to users/stakeholders. {TASK}\n\n"
            "Requirements:\n- Plain language, no jargon\n"
            "- What happened/is happening, who is affected, what they should do\n"
            "- Timing expectations and where updates will be posted\n"
            "- Two versions: short (chat/banner) and full (email)\n\n"
            "Facts to include: {INPUTS}\nConstraints: {CONSTRAINTS}"
        ),
    },
    "graph_api": {
        "name": "Microsoft Graph API script",
        "destination": "Codex",
        "topics": ["m365", "entra", "powershell"],
        "body": (
            "Write a Microsoft Graph script. {TASK}\n\n"
            "Requirements:\n- State required Graph permissions (least privilege) "
            "and whether delegated or application\n"
            "- Handle paging and throttling (429 with Retry-After)\n"
            "- Batch where possible; read-only dry-run mode first\n"
            "- Inputs: {INPUTS}\n- Constraints: {CONSTRAINTS}\n\n"
            "Verification: {VERIFICATION}"
        ),
    },
    "conditional_access": {
        "name": "Conditional Access policy",
        "destination": "Both",
        "topics": ["entra", "security"],
        "body": (
            "Design or change a Conditional Access policy. {TASK}\n\n"
            "Requirements:\n- Start in report-only mode; define what success "
            "looks like in the sign-in logs before enforcing\n"
            "- Exclude break-glass accounts and document them\n"
            "- State exactly who/what is in scope and excluded, and why\n"
            "- Lockout risk assessment and rollback steps\n\n"
            "Policy intent: {INPUTS}\nConstraints: {CONSTRAINTS}\n"
            "Verification: {VERIFICATION}"
        ),
    },
    "device_policy": {
        "name": "Device policy / configuration profile",
        "destination": "Both",
        "topics": ["intune"],
        "body": (
            "Create or modify a device policy (Intune configuration/compliance "
            "or GPO). {TASK}\n\n"
            "Cover:\n- The exact settings and their values, with rationale\n"
            "- Assignment scoping and conflict behavior with existing policies\n"
            "- Pilot ring first; how to confirm the setting applied on a device\n"
            "- User impact and rollback\n\n"
            "Scope: {INPUTS}\nConstraints: {CONSTRAINTS}\nVerification: {VERIFICATION}"
        ),
    },
    "collab_admin": {
        "name": "Teams/SharePoint/OneDrive admin",
        "destination": "Both",
        "topics": ["m365"],
        "body": (
            "Teams/SharePoint/OneDrive administration task. {TASK}\n\n"
            "Cover:\n- Admin-center steps and PowerShell/Graph equivalent\n"
            "- Permission/sharing implications (internal vs external)\n"
            "- Governance: naming, ownership, lifecycle of what's created\n"
            "- Rollback steps\n\n"
            "Context: {INPUTS}\nConstraints: {CONSTRAINTS}\nVerification: {VERIFICATION}"
        ),
    },
    "bulk_data": {
        "name": "Bulk data operation (CSV)",
        "destination": "Codex",
        "topics": ["reporting", "powershell"],
        "body": (
            "Bulk operation driven by a CSV/export. {TASK}\n\n"
            "Requirements:\n- Validate the input file first: required columns, "
            "duplicates, empty values; reject bad rows to an errors file\n"
            "- Dry-run mode that reports what WOULD change\n"
            "- Process in batches with progress output and a results log\n"
            "- Inputs: {INPUTS}\n- Constraints: {CONSTRAINTS}\n\n"
            "Verification: {VERIFICATION}"
        ),
    },
    "vendor_case": {
        "name": "Vendor support case",
        "destination": "ChatGPT web",
        "topics": ["vendor"],
        "body": (
            "Help me open or escalate a vendor support case. {TASK}\n\n"
            "Produce:\n- A tight problem statement: expected vs actual, since when\n"
            "- Environment details and exact reproduction steps\n"
            "- The diagnostics/logs to attach (tell me what to collect)\n"
            "- Business impact statement to justify the severity requested\n"
            "- Questions to push back with if first response is boilerplate\n\n"
            "Details: {INPUTS}\nConstraints: {CONSTRAINTS}"
        ),
    },
    "vendor_eval": {
        "name": "Tool/vendor evaluation",
        "destination": "ChatGPT web",
        "topics": ["vendor"],
        "body": (
            "Evaluate tools/vendors for a need. {TASK}\n\n"
            "Produce:\n- Requirements split into must-have vs nice-to-have\n"
            "- Comparison table of realistic candidates\n"
            "- Security/compliance considerations (SSO, data residency, audit)\n"
            "- Licensing model gotchas and exit/migration cost\n"
            "- A recommendation with reasoning\n\n"
            "Context: {INPUTS}\nConstraints: {CONSTRAINTS}"
        ),
    },
    "training_guide": {
        "name": "Training material / user guide",
        "destination": "ChatGPT web",
        "topics": ["confluence"],
        "body": (
            "Create end-user training material. {TASK}\n\n"
            "Requirements:\n- Written for non-technical users; no jargon\n"
            "- Task-based sections: 'How do I…' with numbered steps\n"
            "- What the user should see after each step\n"
            "- FAQ section from likely confusion points\n"
            "- Where to get help when stuck\n\n"
            "Audience and scope: {INPUTS}\nConstraints: {CONSTRAINTS}"
        ),
    },
    "ticket_reply": {
        "name": "Support ticket reply",
        "destination": "ChatGPT web",
        "topics": ["jira"],
        "body": (
            "Draft a reply to a support ticket. {TASK}\n\n"
            "Requirements:\n- Acknowledge the actual problem in the user's terms\n"
            "- What was found/done, in plain language\n"
            "- Next step and who owns it (them or us), with timing\n"
            "- Professional, warm, no blame, no jargon\n\n"
            "Ticket context: {INPUTS}\nConstraints: {CONSTRAINTS}"
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
    "security": {
        "name": "Security Agent",
        "topics": ["security", "entra", "okta"],
        "body": (
            "Apply a security lens to everything: least privilege, no secrets "
            "in code or output, prefer time-bound access over standing access, "
            "and flag anything that widens attack surface. When handling a "
            "possible compromise, contain first, investigate second."
        ),
    },
    "incident_commander": {
        "name": "Incident Commander Agent",
        "topics": ["incident"],
        "body": (
            "Act as an incident commander: establish impact and severity "
            "first, communicate early and on a cadence, mitigate before "
            "root-causing, and keep a timestamped log of every action and "
            "decision for the postmortem."
        ),
    },
    "comms": {
        "name": "Communications Agent",
        "topics": ["change", "incident"],
        "body": (
            "Write user-facing communications in plain language: what "
            "happened, who is affected, what to do, and when to expect "
            "updates. No jargon, no blame, no speculation. Short version "
            "first, details after."
        ),
    },
    "powershell_standards": {
        "name": "PowerShell Standards Agent",
        "topics": ["powershell"],
        "body": (
            "Enforce PowerShell standards: parameters with validation, "
            "idempotent actions, -WhatIf on destructive operations, "
            "try/catch with actionable errors, logging, and a "
            "test-on-one-object-first approach. Approved verbs only."
        ),
    },
    "data_reporting": {
        "name": "Data & Reporting Agent",
        "topics": ["monitoring", "reporting"],
        "body": (
            "Act as a data/reporting specialist for KQL, SQL, and exports. "
            "Build queries incrementally, validate counts against a known "
            "reference before trusting them, and state caveats (time zones, "
            "retention limits, sampling) alongside every number."
        ),
    },
    "change_management": {
        "name": "Change Management Agent",
        "topics": ["change"],
        "body": (
            "Frame work as managed change: blast radius, implementation plan "
            "with timings, rollback plan with a point of no return, "
            "validation criteria, and a communication plan. No production "
            "change without a tested rollback."
        ),
    },
    "network": {
        "name": "Network Agent",
        "topics": ["network"],
        "body": (
            "Act as a network specialist. Isolate layer by layer (DNS, "
            "reachability, port, application), compare against a working "
            "baseline, and always check recent changes — firewall rules, DNS "
            "records, certificates — before assuming hardware."
        ),
    },
    "compliance": {
        "name": "Compliance Agent",
        "topics": ["audit"],
        "body": (
            "Keep work audit-ready: every change tied to a ticket, every "
            "approval recorded, before/after evidence captured with "
            "timestamps, and artifacts named and stored so an auditor can "
            "find them without you in the room."
        ),
    },
    "explainer": {
        "name": "Explainer Agent",
        "topics": [],
        "body": (
            "After the technical answer, add a short plain-English "
            "explanation a junior admin could follow: what we did, why, and "
            "how to tell it worked. Define any acronym on first use."
        ),
    },
    "scoper": {
        "name": "Scoping Agent",
        "topics": ["harness"],
        "body": (
            "Before executing, break the request into the smallest shippable "
            "slices, estimate effort per slice, flag dependencies and "
            "unknowns, and confirm the order. Push back on scope creep by "
            "listing it as explicit follow-up work."
        ),
    },
    "graph": {
        "name": "Microsoft Graph Agent",
        "topics": ["m365", "entra"],
        "body": (
            "Prefer Microsoft Graph over legacy modules where it can do the "
            "job. Always state the exact Graph permissions needed and whether "
            "delegated or application; least privilege. Handle paging and "
            "throttling (429/Retry-After) in every script."
        ),
    },
    "identity": {
        "name": "Identity Agent",
        "topics": ["entra", "okta", "onboarding"],
        "body": (
            "Act as an identity specialist (Entra ID/Okta): lifecycle joins/"
            "moves/leaves, group-based access over direct grants, MFA and "
            "Conditional Access awareness, break-glass account protection, "
            "and session/token revocation when access must end immediately."
        ),
    },
    "endpoint": {
        "name": "Endpoint Agent",
        "topics": ["intune"],
        "body": (
            "Act as an endpoint/device specialist: Intune enrollment, "
            "Autopilot, compliance and configuration profiles, app "
            "deployment rings, and device-side verification — always confirm "
            "the policy or app actually landed on a real device."
        ),
    },
    "collaboration": {
        "name": "Collaboration Agent",
        "topics": ["m365"],
        "body": (
            "Act as a Teams/SharePoint/OneDrive specialist with a governance "
            "mindset: ownership, naming, internal vs external sharing "
            "implications, and lifecycle (what happens to this site/team in "
            "two years). Flag sprawl-creating choices."
        ),
    },
    "vendor_liaison": {
        "name": "Vendor Liaison Agent",
        "topics": ["vendor"],
        "body": (
            "When dealing with vendor support: reproduce before reporting, "
            "write expected-vs-actual problem statements, attach the "
            "diagnostics they will ask for preemptively, state business "
            "impact to justify severity, and keep a case timeline."
        ),
    },
    "cost": {
        "name": "Cost Optimization Agent",
        "topics": ["reporting"],
        "body": (
            "Watch for cost: licensing tier fit, unused seats, oversized "
            "resources, and egress/storage surprises. When proposing a "
            "solution, state its recurring cost and the cheaper alternative "
            "you considered."
        ),
    },
}

SKILL_TEMPLATES = {
    "jira_triage": {
        "name": "Jira ticket triage skill",
        "topics": ["jira"],
        "body": "Triage incoming Jira tickets: classify, set priority, draft first response, identify owner.",
        "steps": [
            "Read the ticket and classify it: incident, request, change, or question.",
            "Set priority from impact x urgency; note affected users/systems.",
            "Check for duplicates and related tickets; link them.",
            "Draft a first response: what was understood, what happens next, ETA.",
            "Assign an owner and add labels/components for reporting.",
        ],
    },
    "intune_deploy": {
        "name": "Intune deployment skill",
        "topics": ["intune"],
        "body": "Package, detect, assign, validate, and document an Intune deployment.",
        "steps": [
            "Package the app (Win32/LOB/script) with silent install and uninstall commands.",
            "Define detection rules and test them on a reference device.",
            "Assign to a pilot ring; verify install status reports clean.",
            "Expand to production rings; monitor failure rates.",
            "Document the package, detection logic, and rollback in the KB.",
        ],
    },
    "azure_function_build": {
        "name": "Azure Function build skill",
        "topics": ["azure_function"],
        "body": "Scaffold, implement, test locally, and document an Azure Function end to end.",
        "steps": [
            "Pick trigger/bindings and runtime; scaffold the project.",
            "Implement with structured logging and error handling; no secrets in code.",
            "Test locally with sample payloads, including failure cases.",
            "Deploy to a non-prod slot; verify with real-shaped data.",
            "Document configuration, app settings, and the rollback path.",
        ],
    },
    "docs_publish": {
        "name": "Documentation publishing skill",
        "topics": ["confluence"],
        "body": "Draft, review, and publish internal documentation with owner and review-date metadata.",
        "steps": [
            "Identify audience and the single task the doc must enable.",
            "Draft with numbered steps and expected results after each step.",
            "Add troubleshooting and rollback/undo sections.",
            "Peer-review with someone who has NOT done the task before.",
            "Publish with owner and next-review date; link from the team index page.",
        ],
    },
    "audit_evidence": {
        "name": "Audit evidence skill",
        "topics": ["audit"],
        "body": "Collect, name, store, and summarize audit/access evidence mapped to controls.",
        "steps": [
            "List the controls in scope and what artifact proves each one.",
            "Collect exports/screenshots with timestamps and system context visible.",
            "Name artifacts consistently: <control>-<system>-<date>.",
            "Store in the agreed evidence location with restricted access.",
            "Build a summary table mapping control -> evidence -> collection date.",
        ],
    },
    "harness_setup": {
        "name": "Harness setup skill",
        "topics": ["harness"],
        "body": "Create AGENTS.md, task-contract template, and evidence/handoff conventions for a project.",
        "steps": [
            "Write AGENTS.md: orientation, conventions, constraints, definition of done.",
            "Create a task-contract template: scope, inputs, tools, constraints, outputs, verification.",
            "Define where evidence and handoff notes live.",
            "Run one small task through the loop to validate it.",
            "Trim anything the trial run showed was unnecessary.",
        ],
    },
    "workspace_agent_design": {
        "name": "ChatGPT workspace-agent design skill",
        "topics": ["workspace_agent"],
        "body": "Design a workspace agent: purpose, scope, tools, memory model, verification, handoff.",
        "steps": [
            "Write a one-sentence purpose and explicit out-of-scope list.",
            "Choose allowed tools and forbidden actions.",
            "Define the memory model: durable files are truth, memory is supplemental.",
            "Add verification requirements before the agent claims completion.",
            "Test with 3 representative tasks; slim the instructions afterward.",
        ],
    },
    "iac_workflow": {
        "name": "Infrastructure-as-code workflow skill",
        "topics": ["iac"],
        "body": "Author IaC, preview/plan, apply with approval, verify, and record rollback steps.",
        "steps": [
            "Author or modify the IaC with parameters over hardcoded values.",
            "Run plan/preview (what-if) and review every change it lists.",
            "Apply in non-prod first; verify resources match intent.",
            "Apply to production inside the change window with approval.",
            "Record state location and the exact rollback procedure.",
        ],
    },
    "powershell_automation": {
        "name": "PowerShell automation skill",
        "topics": ["powershell"],
        "body": "Write idempotent PowerShell with error handling, logging, -WhatIf support, and tests.",
        "steps": [
            "Define inputs as parameters with validation attributes.",
            "Make every action idempotent and support -WhatIf for destructive steps.",
            "Add try/catch with actionable error messages and a transcript/log.",
            "Test against a small scope first (one user/device), then widen.",
            "Comment the why, not the what; store in the team script repo.",
        ],
    },
    "okta_entra_access": {
        "name": "Okta/Entra access workflow skill",
        "topics": ["okta", "entra"],
        "body": "Handle access requests: validate approval, apply group/app assignment, capture evidence.",
        "steps": [
            "Verify the request has a ticket and the right approver signed off.",
            "Apply access via group membership, never direct assignment, when possible.",
            "Confirm the user can actually access the resource.",
            "Capture before/after evidence (group membership export or screenshot).",
            "Close the ticket noting what was granted and any expiry/review date.",
        ],
    },
    "incident_triage": {
        "name": "Incident triage skill",
        "topics": ["incident"],
        "body": "Stabilize first: assess impact, communicate, mitigate, then fix root cause.",
        "steps": [
            "Establish impact: who/what is affected, since when, how badly.",
            "Declare severity and open an incident ticket/channel.",
            "Post an initial status update before deep-diving.",
            "Mitigate (rollback, failover, restart) before root-causing.",
            "Record a timeline of actions as you go for the postmortem.",
        ],
    },
    "rca_postmortem": {
        "name": "Root-cause analysis / postmortem skill",
        "topics": ["incident"],
        "body": "Turn an incident timeline into a blameless postmortem with tracked actions.",
        "steps": [
            "Reconstruct the timeline: detection, escalation, mitigation, resolution.",
            "Identify root cause with 5-whys; separate trigger from underlying cause.",
            "List what went well and what failed (detection, comms, tooling).",
            "Write action items with owners and due dates; file tickets for each.",
            "Share the postmortem; keep it blameless and factual.",
        ],
    },
    "user_onboarding": {
        "name": "User onboarding skill",
        "topics": ["onboarding", "entra", "m365"],
        "body": "Provision a new hire consistently: identity, licenses, groups, devices, verification.",
        "steps": [
            "Confirm the hire details and start date from the HR ticket.",
            "Create/verify identity, assign licenses and group-based access.",
            "Enroll or assign the device and required apps.",
            "Verify mail, sign-in, MFA registration, and key app access.",
            "Record completion in the ticket with evidence of each item.",
        ],
    },
    "user_offboarding": {
        "name": "User offboarding skill",
        "topics": ["onboarding", "entra", "okta"],
        "body": "Remove access safely and completely, with evidence, on the leaver's end date.",
        "steps": [
            "Confirm the termination ticket, date, and any litigation-hold needs.",
            "Disable sign-in, revoke sessions/tokens, reset credentials.",
            "Remove group memberships, app assignments, shared mailbox access.",
            "Handle data: mailbox delegation, OneDrive transfer, device wipe per policy.",
            "Capture before/after evidence and close out with a checklist.",
        ],
    },
    "access_review": {
        "name": "Access review skill",
        "topics": ["audit", "entra", "okta"],
        "body": "Run a periodic access review: scope, export, decide, remediate, evidence.",
        "steps": [
            "Scope the review: which apps/groups/roles and which reviewers.",
            "Export current membership and last-sign-in data.",
            "Have owners confirm or revoke each entry; chase non-responses.",
            "Remediate revocations and verify removal took effect.",
            "Archive decisions and evidence mapped to the control.",
        ],
    },
    "phishing_response": {
        "name": "Phishing response skill",
        "topics": ["security", "m365"],
        "body": "Contain a reported phish: assess, purge, reset, block, and notify.",
        "steps": [
            "Analyze the message: sender, URLs, attachments, who else received it.",
            "Purge the message from all mailboxes and block the sender/domain/URL.",
            "Identify users who clicked or entered credentials; reset and revoke sessions.",
            "Check sign-in logs for compromise indicators on affected accounts.",
            "Notify affected users and record the incident with evidence.",
        ],
    },
    "patch_cycle": {
        "name": "Patch cycle skill",
        "topics": ["security", "intune"],
        "body": "Run a monthly patch cycle: ring rollout, exception tracking, compliance reporting.",
        "steps": [
            "Review this cycle's updates and known issues before approving.",
            "Release to the pilot ring; soak for the agreed period.",
            "Promote to broad rings; track failure and pending-reboot rates.",
            "Chase stragglers and document exceptions with owners.",
            "Produce the compliance report for the cycle.",
        ],
    },
    "change_request": {
        "name": "Change request skill",
        "topics": ["change"],
        "body": "Write a CAB-ready change: plan, risk, rollback, validation, and comms.",
        "steps": [
            "Describe the change, why now, and the blast radius if it goes wrong.",
            "Write the implementation plan with timings and owners.",
            "Write the rollback plan and the point of no return.",
            "Define validation: how you'll know it worked.",
            "List who must be informed before/during/after.",
        ],
    },
    "mailflow_debug": {
        "name": "Mail-flow troubleshooting skill",
        "topics": ["m365"],
        "body": "Trace a mail problem end to end: scope, trace, inspect, fix, confirm.",
        "steps": [
            "Scope: one user or many, inbound or outbound, since when.",
            "Run a message trace for concrete examples.",
            "Inspect the failing hop: transport rules, connectors, spam verdicts, DNS/SPF/DKIM.",
            "Apply the fix and re-trace the same scenario.",
            "Document the cause and fix in the ticket.",
        ],
    },
    "network_diag": {
        "name": "Network diagnostics skill",
        "topics": ["network"],
        "body": "Isolate network issues layer by layer with evidence at each step.",
        "steps": [
            "Define the failing path: source, destination, port/protocol.",
            "Test connectivity layer by layer: DNS, ping/route, port, application.",
            "Compare against a working baseline (another user/site/VLAN).",
            "Check recent changes: firewall rules, DNS records, certificates.",
            "Fix, verify from the original failing client, and record the cause.",
        ],
    },
    "kql_reporting": {
        "name": "Log query / reporting skill",
        "topics": ["monitoring", "reporting"],
        "body": "Build a KQL/SQL query iteratively and validate the numbers before sharing.",
        "steps": [
            "State the question the query must answer and the time range.",
            "Identify tables/sources and join keys.",
            "Build incrementally: filter, then aggregate, then format.",
            "Sanity-check counts against a known reference.",
            "Save the query with a comment block: purpose, owner, caveats.",
        ],
    },
    "license_cleanup": {
        "name": "License cleanup skill",
        "topics": ["m365", "reporting"],
        "body": "Reclaim unused licenses safely: inventory, identify, confirm, reclaim, report.",
        "steps": [
            "Export license assignments with last-activity data.",
            "Flag candidates: disabled users, long-inactive, duplicate plans.",
            "Confirm with managers/owners before touching anything.",
            "Reclaim in batches; watch for service removal side effects.",
            "Report seats reclaimed and projected savings.",
        ],
    },
    "backup_restore_test": {
        "name": "Backup restore test skill",
        "topics": ["backup"],
        "body": "Prove backups work by restoring: a backup untested is a backup unproven.",
        "steps": [
            "Pick a representative restore scenario (file, mailbox, VM, DB).",
            "Restore to an isolated target, never over production.",
            "Verify integrity and completeness of restored data.",
            "Time the restore against the RTO; note gaps.",
            "Record results and fix any failures found.",
        ],
    },
    "monitoring_setup": {
        "name": "Monitoring/alert setup skill",
        "topics": ["monitoring"],
        "body": "Create alerts people trust: clear condition, right audience, tested, documented.",
        "steps": [
            "Define the condition that needs action and the threshold.",
            "Route to the right audience with severity that matches impact.",
            "Write the alert description so the responder knows what to do.",
            "Test-fire the alert and confirm delivery.",
            "Link a runbook and set a review date to kill noisy alerts.",
        ],
    },
    "kb_audit": {
        "name": "KB/documentation audit skill",
        "topics": ["confluence"],
        "body": "Sweep stale documentation: inventory, verify, fix or archive, re-index.",
        "steps": [
            "Inventory pages by last-modified date and owner.",
            "Spot-check the most-used pages for accuracy first.",
            "Fix quick errors inline; flag big rewrites as tickets.",
            "Archive abandoned/duplicate pages, leaving a redirect note.",
            "Update the index/landing page to match reality.",
        ],
    },
    "meeting_actions": {
        "name": "Meeting notes to actions skill",
        "topics": ["reporting"],
        "body": "Turn raw meeting notes into decisions, owned actions, and follow-ups.",
        "steps": [
            "Separate decisions, actions, and open questions from raw notes.",
            "Give every action an owner and a date; flag unowned ones.",
            "Convert actions into tickets where work is non-trivial.",
            "Write a 5-line summary for people who skipped the meeting.",
            "Park open questions with who will answer them by when.",
        ],
    },
    "graph_script": {
        "name": "Graph API script skill",
        "topics": ["m365", "entra"],
        "body": "Build a Graph script safely: permissions, dry-run, paging, throttling, evidence.",
        "steps": [
            "Identify the exact Graph endpoints and least-privilege permissions.",
            "Get the app registration/consent approved before writing code.",
            "Build read-only first; print what WOULD change as a dry run.",
            "Add paging and 429/Retry-After handling; test on a small scope.",
            "Run for real in batches; log results as evidence.",
        ],
    },
    "ca_rollout": {
        "name": "Conditional Access rollout skill",
        "topics": ["entra", "security"],
        "body": "Roll out a CA policy without locking anyone out: report-only, review, enforce.",
        "steps": [
            "Define intent: who must do what, under which conditions.",
            "Exclude break-glass accounts; verify they still work.",
            "Deploy in report-only mode for an agreed soak period.",
            "Review sign-in log impact; fix false positives before enforcing.",
            "Enforce, monitor the first 24h closely, document the policy.",
        ],
    },
    "autopilot_provision": {
        "name": "Device provisioning skill",
        "topics": ["intune", "onboarding"],
        "body": "Provision a device end to end: enroll, apply profiles, verify, hand over.",
        "steps": [
            "Register/assign the device (Autopilot profile or manual enrollment).",
            "Confirm group membership drives the right apps and policies.",
            "Provision and watch enrollment status for failures.",
            "Verify on-device: compliance state, required apps, drive encryption.",
            "Hand over with the user-facing quick-start info.",
        ],
    },
    "teams_provision": {
        "name": "Teams/site provisioning skill",
        "topics": ["m365"],
        "body": "Create a team/site with governance: owner, naming, sharing, lifecycle.",
        "steps": [
            "Confirm the request has a business owner and a clear purpose.",
            "Apply naming convention and at least two owners.",
            "Set sharing: internal/external, guest policy, sensitivity label.",
            "Provision and verify member access works.",
            "Record it in the inventory with a review/expiry date.",
        ],
    },
    "support_case": {
        "name": "Vendor support case skill",
        "topics": ["vendor"],
        "body": "Open vendor cases that get answered: repro, evidence, impact, follow-up cadence.",
        "steps": [
            "Reproduce the issue and write expected vs actual behavior.",
            "Collect the diagnostics the vendor will ask for (logs, versions, IDs).",
            "State business impact and the severity you're requesting.",
            "Open the case; record the case number in your ticket.",
            "Set a follow-up cadence; escalate with impact data if it stalls.",
        ],
    },
    "csv_bulk_ops": {
        "name": "Bulk operations skill",
        "topics": ["reporting", "powershell"],
        "body": "Run bulk changes from a CSV without disasters: validate, dry-run, batch, log.",
        "steps": [
            "Validate the input: required columns, duplicates, empties; reject bad rows.",
            "Dry-run and review the would-change list with the requester.",
            "Run a small batch first (5-10 rows); verify results.",
            "Run the rest in batches with progress and a results log.",
            "Keep input + results log as the change evidence.",
        ],
    },
    "cert_renewal": {
        "name": "Certificate renewal skill",
        "topics": ["network", "security"],
        "body": "Renew a certificate without an outage: inventory, renew, deploy, verify, record.",
        "steps": [
            "Identify every place the current cert is used (servers, LBs, services).",
            "Generate the CSR/renewal with the right SANs and key size.",
            "Deploy to one node first; verify chain and expiry with a TLS check.",
            "Roll to remaining nodes; restart services that cache certs.",
            "Update the cert inventory with the new expiry and set a reminder.",
        ],
    },
    "dns_change": {
        "name": "DNS change skill",
        "topics": ["network"],
        "body": "Make DNS changes safely: lower TTL first, change, verify propagation, revert path.",
        "steps": [
            "Record the current record values (your rollback).",
            "Lower TTL ahead of the change window if cutover timing matters.",
            "Make the change; verify against authoritative and public resolvers.",
            "Test the dependent service end to end, not just the lookup.",
            "Restore TTL and document the change with timestamps.",
        ],
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
    "incident": ["Impact scope (who/what/since when)", "Timeline of events so far", "Recent changes to affected systems"],
    "onboarding": ["HR ticket / start or end date", "Role and department (for group access)", "Device and license requirements"],
    "security": ["Affected users/devices", "The suspicious message/file/alert details", "Sign-in or audit log extracts"],
    "change": ["Change window and freeze dates", "Systems and user groups affected", "Approver and stakeholders"],
    "network": ["Source/destination/port of failing path", "Error messages or timeouts seen", "A working comparison (user/site that works)"],
    "monitoring": ["Data source / workspace name", "The condition worth alerting on", "Who should receive alerts"],
    "reporting": ["Data source and time range", "Who consumes the report", "A known reference number to validate against"],
    "backup": ["Backup product and scope", "RTO/RPO targets", "Last successful restore test date"],
    "vendor": ["Product name and version", "Case number (if existing)", "Logs/diagnostics already collected"],
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
            parts.append(f"\n### {s['name']}\n{s['body']}")
            for i, step in enumerate(s.get("steps", []), 1):
                parts.append(f"{i}. {step}")

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
        size_menu = tk.Menu(menu, tearoff=0)
        for label, scale in (("Large", 1), ("Medium", 2), ("Small", 3)):
            check = " ✓" if scale == self.scale else ""
            size_menu.add_command(label=label + check,
                                  command=lambda s=scale: self.set_scale(s))
        menu.add_cascade(label="📏 Pet size", menu=size_menu)
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

    def set_scale(self, scale: int):
        """Resize the pet (1 = full sprite size, larger = smaller pet)."""
        self.scale = max(1, int(scale))
        self.settings["pet_scale"] = self.scale
        self._reload_sprites()
        self._save_settings()

    def switch_pet(self, pet_id: str):
        """Reload sprites for a newly selected pet and resize the overlay."""
        self.pet_id = pet_id
        self.pet_dir = local_pet_dir(pet_id)
        self.pet_meta = load_json(self.pet_dir / "pet.json",
                                  {"id": pet_id, "displayName": pet_id.title()})
        self._reload_sprites()
        self.settings["pet_id"] = pet_id
        self._save_settings()
        if self.chat and self.chat.is_open():
            self.chat.on_pet_changed()

    def _reload_sprites(self):
        self.sprites = SpriteLibrary(self.pet_dir, scale=self.scale)
        w, h = self.sprites.w, self.sprites.h
        self.canvas.delete("all")
        self.canvas.config(width=w, height=h)
        self.sprite_item = self.canvas.create_image(0, 0, anchor="nw") if self.sprites.ok else None
        x, y = self.root.winfo_x(), self.root.winfo_y()
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        self.root.geometry(f"{w}x{h}+{min(x, sw - w)}+{min(y, sh - h)}")
        self.set_anim("wave")

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
    """iMessage-style chat window opened by clicking the pet.

    Messages are kept in a history list and re-flowed whenever the window is
    resized, so bubbles always wrap to the current width.
    """

    BG = "#ffffff"
    HEADER_BG = "#f6f6f7"
    USER_BUBBLE = "#0b93f6"
    PET_BUBBLE = "#e9e9eb"
    CAPTION = "#8e8e93"

    def __init__(self, pet: PetOverlay):
        self.pet = pet
        self.spell = pet.spell
        self.last = None       # (raw, cleaned, rec, prompt)
        self.messages = []     # (kind, text) history, re-flowed on resize
        self._frames = []      # embedded button frames, destroyed on re-flow
        self._typing = False
        self._y = 12
        self._cw = 440         # canvas width used for the current layout
        self._resize_job = None
        self._placeholder_on = False

        win = tk.Toplevel(pet.root)
        self.win = win
        win.title(f"{pet.pet_name()} — PromptMate")
        win.wm_attributes("-topmost", True)
        win.minsize(340, 400)
        self._place_near_pet(440, 600)
        win.configure(bg=self.BG)

        self._build_header()

        # Conversation canvas
        log_frame = tk.Frame(win, bg=self.BG)
        log_frame.pack(fill="both", expand=True)
        self.canvas = tk.Canvas(log_frame, bg=self.BG, highlightthickness=0)
        scroll = ttk.Scrollbar(log_frame, command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<MouseWheel>", self._on_wheel)
        self.canvas.bind("<Configure>", self._on_canvas_resize)

        # Input row: entry with placeholder + round blue send button
        input_frame = tk.Frame(win, bg=self.BG, padx=8, pady=8)
        input_frame.pack(fill="x")
        # Button first, from the right, so the entry can never squeeze it out
        # (a Text widget's default requested width is ~80 chars).
        send_btn = tk.Button(input_frame, text="↑", command=self.send,
                             bg=self.USER_BUBBLE, fg="white", relief="flat",
                             font=("Segoe UI", 13, "bold"), width=3, cursor="hand2",
                             activebackground="#0a84d0", activeforeground="white")
        send_btn.pack(side="right", padx=(8, 0), fill="y")
        entry_holder = tk.Frame(input_frame, bg="#d1d1d6", padx=1, pady=1)
        entry_holder.pack(side="left", fill="both", expand=True)
        self.entry = tk.Text(entry_holder, height=2, width=10, wrap="word",
                             relief="flat", font=("Segoe UI", 10), undo=True,
                             padx=8, pady=6)
        self.entry.pack(fill="both", expand=True)
        SpellSupport(self.entry, self.spell)
        self.entry.bind("<Return>", self._on_return)
        self.entry.bind("<FocusIn>", self._clear_placeholder)
        self.entry.bind("<FocusOut>", self._set_placeholder)

        self._add("caption", datetime.now().strftime("Today %H:%M"))
        self._add("pet", CHAT_GREETING)
        self.entry.focus_set()

    # ---- header --------------------------------------------------------------

    def _build_header(self):
        header = tk.Frame(self.win, bg=self.HEADER_BG)
        header.pack(fill="x")
        self.avatar_label = tk.Label(header, bg=self.HEADER_BG)
        self.avatar_label.pack(side="left", padx=(10, 8), pady=4)
        box = tk.Frame(header, bg=self.HEADER_BG)
        box.pack(side="left", pady=4)
        self.header_name = tk.Label(box, bg=self.HEADER_BG, anchor="w",
                                    font=("Segoe UI", 11, "bold"))
        self.header_name.pack(anchor="w")
        self.header_sub = tk.Label(box, bg=self.HEADER_BG, fg=self.CAPTION,
                                   anchor="w", font=("Segoe UI", 8))
        self.header_sub.pack(anchor="w")
        tk.Frame(self.win, bg="#d1d1d6", height=1).pack(fill="x")
        self._update_header()

    def _update_header(self):
        self.header_name.config(text=self.pet.pet_name())
        self.header_sub.config(text=f"art by {pet_credit(self.pet.pet_meta)} · "
                                    "codex-pets.net")
        self._avatar = self._make_avatar()
        if self._avatar:
            self.avatar_label.config(image=self._avatar)

    def _make_avatar(self):
        if not self.pet.sprites.ok:
            return None
        frames = self.pet.sprites.frames.get("idle") or next(iter(self.pet.sprites.frames.values()))
        frame = frames[0]
        factor = max(1, frame.height() // 40)
        return frame.subsample(factor, factor)

    # ---- window plumbing ------------------------------------------------------

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
        self._update_header()
        self._add("caption", f"{self.pet.pet_name()} joined the chat "
                             f"(art by {pet_credit(self.pet.pet_meta)})")
        self._add("pet", "New look, same PromptMate! What are we working on?")

    def _on_wheel(self, event):
        if self.is_open():
            self.canvas.yview_scroll(-1 * (event.delta // 120), "units")

    def _on_canvas_resize(self, event):
        if abs(event.width - self._cw) < 8:
            return
        self._cw = event.width
        if self._resize_job:
            self.win.after_cancel(self._resize_job)
        self._resize_job = self.win.after(120, self._render_all)

    # ---- placeholder -----------------------------------------------------------

    def _set_placeholder(self, *_):
        if not self.entry.get("1.0", "end-1c").strip():
            self._placeholder_on = True
            self.entry.config(fg=self.CAPTION)
            self.entry.delete("1.0", "end")
            self.entry.insert("1.0", "Message")

    def _clear_placeholder(self, *_):
        if self._placeholder_on:
            self._placeholder_on = False
            self.entry.delete("1.0", "end")
            self.entry.config(fg="#000000")

    # ---- bubble drawing ---------------------------------------------------------

    def _round_rect(self, x1, y1, x2, y2, r=14, **kw):
        pts = [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2,
               x2 - r, y2, x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]
        return self.canvas.create_polygon(pts, smooth=True, **kw)

    def _finish(self, bottom):
        self._y = bottom + 8
        self.canvas.configure(scrollregion=(0, 0, self._cw, self._y))
        self.canvas.yview_moveto(1.0)

    def _add(self, kind, text=None):
        """Append a message to history and draw it."""
        self.messages.append((kind, text))
        self._draw(kind, text)

    def _render_all(self):
        """Re-flow the whole conversation at the current width."""
        self._resize_job = None
        for f in self._frames:
            f.destroy()
        self._frames = []
        self.canvas.delete("all")
        self._y = 12
        for kind, text in self.messages:
            self._draw(kind, text)
        if self._typing:
            self._draw_typing()

    def _draw(self, kind, text):
        if kind == "caption":
            self._draw_caption(text)
        elif kind == "user":
            self._draw_bubble(text, "right", self.USER_BUBBLE, "#ffffff")
        elif kind == "pet":
            self._draw_bubble(text, "left", self.PET_BUBBLE, "#000000")
        elif kind == "prompt":
            self._draw_bubble(text, "left", "#f2f2f7", "#1c1c1e",
                              font=("Consolas", 8))
            self._draw_actions()

    def _draw_caption(self, text):
        item = self.canvas.create_text(self._cw // 2, self._y + 4, text=text,
                                       fill=self.CAPTION, font=("Segoe UI", 8),
                                       anchor="n", width=max(120, self._cw - 60),
                                       justify="center")
        self._finish(self.canvas.bbox(item)[3])

    def _draw_bubble(self, text, side, fill, fg, font=("Segoe UI", 10), pad=10):
        maxw = max(180, int(self._cw * 0.74))
        tmp = self.canvas.create_text(0, -10000, text=text, font=font,
                                      width=maxw, anchor="nw")
        x1, y1, x2, y2 = self.canvas.bbox(tmp)
        tw, th = x2 - x1, y2 - y1
        self.canvas.delete(tmp)

        if side == "right":
            bx2 = self._cw - 24
            bx1 = bx2 - tw - 2 * pad
        else:
            bx1 = 12
            bx2 = bx1 + tw + 2 * pad
        by1, by2 = self._y, self._y + th + 2 * pad
        self._round_rect(bx1, by1, bx2, by2, r=15, fill=fill, outline=fill)
        self.canvas.create_text(bx1 + pad, by1 + pad, text=text, font=font,
                                fill=fg, width=maxw, anchor="nw")
        self._finish(by2)

    def _draw_actions(self):
        btns = tk.Frame(self.canvas, bg=self.BG)
        for label, cmd in (("📋 Copy", self._copy_last), ("💾 Save", self._save_last),
                           ("🛠 Adjust in editor", self._open_in_editor)):
            ttk.Button(btns, text=label, command=cmd).pack(side="left", padx=(0, 4))
        self._frames.append(btns)
        item = self.canvas.create_window(12, self._y, window=btns, anchor="nw")
        self.win.update_idletasks()
        self._finish(self.canvas.bbox(item)[3])

    def _draw_typing(self):
        self._round_rect(12, self._y, 64, self._y + 30, r=15,
                         fill=self.PET_BUBBLE, outline=self.PET_BUBBLE)
        self.canvas.create_text(38, self._y + 15, text="• • •",
                                fill=self.CAPTION, font=("Segoe UI", 9))
        self._finish(self._y + 30)

    def _show_typing(self):
        self._typing = True
        self._draw_typing()

    def _hide_typing(self):
        self._typing = False
        self._render_all()

    # ---- actions ----------------------------------------------------------

    def _on_return(self, event):
        if event.state & 0x0001:  # Shift+Return -> newline
            return None
        self.send()
        return "break"

    def send(self):
        if self._placeholder_on:
            return
        raw = self.entry.get("1.0", "end-1c").strip()
        if not raw:
            return
        self.entry.delete("1.0", "end")
        self._add("user", raw)

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
        self._add("pet", f"Got it! I read that as:\n“{cleaned}”")
        self._add("pet", f"➜ Send it to: {DEST_LABELS[rec['destination']]}\n{rec['reason']}")
        details = f"Template: {template_name}\nModules: {module_names}"
        if rec["checklist"]:
            hints = "\n".join(f"• {c}" for c in rec["checklist"][:5])
            details += f"\n\nIt'll work better if you paste in:\n{hints}"
        self._add("pet", details)
        self._add("prompt", prompt)

    def _copy_last(self):
        if not self.last:
            return
        self.win.clipboard_clear()
        self.win.clipboard_append(self.last[3])
        self._add("pet", "Copied! Paste it into Codex, Claude Code, ChatGPT, or Claude. ✅")

    def _save_last(self):
        if not self.last:
            return
        raw, cleaned, rec, prompt = self.last
        save_history_entry(raw, cleaned, rec, prompt)
        self._add("pet", "Saved to your local history. 💾")

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
