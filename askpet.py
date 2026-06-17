#!/usr/bin/env python3
"""
AskPet — local-only prompt builder for Codex / ChatGPT web.

Single-file Tkinter MVP. No external dependencies, no network calls,
no telemetry. Seed data lives in this file; later it can be refactored
into JSON files under data/.

Run:  python askpet.py
"""

import base64
import difflib
import io
import json
import math
import os
import random
import re
import shutil
import subprocess
import sys
import threading
import time
import tkinter as tk
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
import zipfile
from datetime import datetime, timedelta
from pathlib import Path
from tkinter import messagebox, ttk

APP_NAME = "AskPet"
APP_VERSION = "0.39.0"
CONTENT_VERSION = "2026.06.17"

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


def _legacy_data_dir() -> Path:
    """Where PromptMate (this app's former name) kept user data."""
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        return base / "PromptMate"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "PromptMate"
    return Path.home() / ".local" / "share" / "PromptMate"


def migrate_legacy_data():
    """One-time move of PromptMate-era user data (settings, history,
    pets, knowledge packs, dictionaries) into the AskPet directory.

    If the AskPet dir already exists (e.g. something created it before
    the first real launch), merge item-by-item without overwriting
    anything the new dir already has."""
    old, new = _legacy_data_dir(), user_data_dir()
    if not old.exists():
        return
    if not new.exists():
        try:
            old.rename(new)
            return
        except OSError:
            pass  # fall through to the per-item merge
    try:
        new.mkdir(parents=True, exist_ok=True)
        for item in old.iterdir():
            target = new / item.name
            if target.exists():
                continue  # never clobber data the new dir already has
            try:
                item.rename(target)
            except OSError:
                if item.is_dir():
                    shutil.copytree(item, target)
                else:
                    shutil.copy2(item, target)
    except OSError:
        pass  # partial migration beats failing to launch


DATA_DIR = user_data_dir()
KNOWLEDGE_DIR = DATA_DIR / "knowledge"
SETTINGS_FILE = DATA_DIR / "settings.json"
HISTORY_FILE = DATA_DIR / "prompt-history.json"
CHAT_HISTORY_FILE = DATA_DIR / "chat-history.json"
PET_MEMORY_FILE = DATA_DIR / "pet-memory.json"
CUSTOM_DICT_FILE = DATA_DIR / "custom-dictionary.json"
LEARNED_FILE = DATA_DIR / "learned-corrections.json"


def load_json(path: Path, default):
    try:
        # utf-8-sig: tolerate a BOM from external editors/scripts — a
        # rejected settings file silently resets every user preference.
        with open(path, "r", encoding="utf-8-sig") as f:
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
    "complaince": "compliance",
    "complience": "compliance",
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
# Product/brand names users type at the pet that no dictionary carries.
KNOWN_WORDS.update(
    """kogi askpet codex chatgpt claude anthropic openai gemini copilot
    notebooklm midjourney sharepoint onedrive sharegate powerpoint gmail
    granola zoom slack notion github gitlab terraform datadog snowflake
    fortigate sentinelone crowdstrike ninjaone connectwise screenconnect
    servicenow workday salesforce hubspot docusign knowbe4 bitwarden
    lastpass synology unifi ubiquiti meraki jamf veeam webex youtube
    linkedin atlassian websites onboarding offboarding sysadmin
    """.split()
)


# ---------------------------------------------------------------------------
# Text cleanup + spell support (stdlib only)
# ---------------------------------------------------------------------------


# Big English dictionary (370k words, public domain - dwyl/english-words).
# Loaded lazily; without it the checker would flag everyday words like
# "meeting" or "calendar" because KNOWN_WORDS is only the IT seed vocab.
_ENGLISH_WORDS = None
_ENGLISH_BUCKETS = None  # first letter -> [words], for fast suggestions

CONTRACTIONS = {
    "don't", "doesn't", "didn't", "can't", "won't", "isn't", "aren't",
    "wasn't", "weren't", "couldn't", "shouldn't", "wouldn't", "hasn't",
    "haven't", "hadn't", "mustn't", "needn't", "ain't", "it's", "that's",
    "what's", "let's", "i'm", "i've", "i'll", "i'd", "you're", "you've",
    "you'll", "you'd", "we're", "we've", "we'll", "we'd", "they're",
    "they've", "they'll", "they'd", "he's", "he'll", "he'd", "she's",
    "she'll", "she'd", "there's", "here's", "who's", "how's", "where's",
    "when's", "why's",
}


def english_words() -> frozenset:
    global _ENGLISH_WORDS
    if _ENGLISH_WORDS is None:
        if getattr(sys, "frozen", False):
            path = Path(sys._MEIPASS) / "data" / "english-words.txt"
        else:
            path = Path(__file__).resolve().parent / "data" / "english-words.txt"
        try:
            with open(path, "r", encoding="ascii", errors="ignore") as f:
                _ENGLISH_WORDS = frozenset(w.strip() for w in f)
        except OSError:
            _ENGLISH_WORDS = frozenset()
    return _ENGLISH_WORDS


def _english_buckets() -> dict:
    global _ENGLISH_BUCKETS
    if _ENGLISH_BUCKETS is None:
        _ENGLISH_BUCKETS = {}
        for w in english_words():
            if w:
                _ENGLISH_BUCKETS.setdefault(w[0], []).append(w)
    return _ENGLISH_BUCKETS


class SpellHelper:
    """Local fuzzy spelling support: corrections dict + difflib + learned words."""

    def __init__(self):
        self.learned = load_json(LEARNED_FILE, {})  # typo -> correction
        custom = load_json(CUSTOM_DICT_FILE, {"words": []})
        self.custom_words = {w.lower() for w in custom.get("words", [])}

    def known(self, word: str) -> bool:
        lw = word.lower().strip("'")
        if (lw in KNOWN_WORDS or lw in self.custom_words or lw in ALIASES
                or len(lw) <= 2 or lw.isdigit()):
            return True
        if "'" in lw:
            if lw in CONTRACTIONS:
                return True
            base, _, suffix = lw.rpartition("'")
            # possessives ("kogi's") and plural possessives ("users'")
            return suffix in ("s", "") and self.known(base)
        return lw in english_words()

    def suggestions(self, word: str, n: int = 4) -> list:
        lw = word.lower()
        out = []
        if lw in self.learned:
            out.append(self.learned[lw])
        if lw in CORRECTIONS:
            out.append(CORRECTIONS[lw])
        pool = KNOWN_WORDS | self.custom_words
        out.extend(difflib.get_close_matches(lw, pool, n=n, cutoff=0.72))
        # The big dictionary, pre-filtered to same first letter and similar
        # length so difflib has thousands of candidates, not 370k.
        if lw:
            candidates = [w for w in _english_buckets().get(lw[0], [])
                          if abs(len(w) - len(lw)) <= 2]
            out.extend(difflib.get_close_matches(lw, candidates, n=n, cutoff=0.78))
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
    "csv": 2, "bulk": 1,
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
    "memo": 2, "briefing": 3, "agenda": 2, "slides": 2, "deck": 2,
    "email": 1, "newsletter": 2, "presentation": 2,
    "essay": 2, "homework": 2, "research": 2, "valuation": 2, "study": 1,
}

KEYWORD_TOPICS = {
    "azure_function": ["azure function", "azure functions", "function app"],
    "intune": ["intune", "autopilot", "enrollment", "device compliance",
               "compliance policy", "configuration profile", "sccm", "mecm",
               "configmgr", "config manager", "configuration manager"],
    "m365": ["microsoft 365", "office 365", "exchange", "sharepoint",
             "onedrive", "mailbox", "teams", "outlook", "copilot",
             "teams room", "room booking", "room mailbox",
             "resource mailbox", "booking calendar"],
    "entra": ["entra", "azure ad", "active directory", "conditional access", "mfa", "sso"],
    "okta": ["okta", "scim", "saml"],
    "powershell": ["powershell"],
    "jira": ["jira", "ticket"],
    "confluence": ["confluence", "documentation", "knowledge base", "runbook", "how-to"],
    "iac": ["infrastructure as code", "terraform", "bicep", "arm template"],
    "audit": ["audit", "evidence", "access review", "compliance evidence",
              "compliance report", "soc 2", "soc2", "iso 27001"],
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
               "communication", "announce to", "announcement to", "notify users"],
    "network": ["network", "vpn", "dns", "firewall", "dhcp", "wifi", "wi-fi",
                "switch port", "certificate", "cert expir", "cert renew",
                "wildcard cert", "ssl", "tls", "latency",
                "unifi", "ubiquiti", "meraki", "aruba", "access point",
                "ssid", "guest network", "wireless controller",
                "nameserver", "name server", "registrar", "godaddy",
                "namecheap", "cloudflare", "dns record", "cname",
                "txt record", "domain renewal", "renew our domain",
                "domain expir"],
    "monitoring": ["monitoring", "alert", "alerts", "log analytics", "kql",
                   "sentinel", "splunk", "dashboard"],
    # "report" must be word-anchored: bare substring matches "reported".
    "reporting": ["reporting", "report on", "report of", "report for",
                  "a report", "usage report", "weekly report", "monthly report",
                  "metrics", "kpi", "export", "spreadsheet", "license count",
                  "licenses", "power bi", "powerbi"],
    "bulk_data": ["csv", "bulk", "in bulk", "mass update", "import a list",
                  "from a list", "batch update"],
    "backup": ["backup", "backups", "restore", "disaster recovery",
               "recovery point", "snapshot"],
    "vendor": ["vendor support", "vendor case", "support case", "open a case",
               "escalate", "microsoft support", "evaluate a tool",
               "evaluate a vendor", "tool evaluation", "vendor evaluation",
               "compare tools", "which tool"],
    "fixit": ["not working", "doesnt work", "doesn't work", "stopped working",
              "broken", "crash", "crashes", "crashing", "keeps dropping",
              "wont open", "won't open", "cant open", "can't open",
              "wont start", "won't start", "error when", "fails", "failing",
              "freezes", "frozen", "keep dropping", "keep disconnecting",
              "keeps disconnecting", "very slow", "wont boot", "won't boot",
              "wont print", "won't print", "stuck on", "no sound",
              "blank screen", "fail every", "fail after", "fail when",
              "disappeared", "freeze", "wont register", "won't register",
              "keeps rebooting", "keep rebooting"],
    "notion": ["notion"],
    "zoom": ["zoom", "webinar", "meeting recording", "transcript"],
    "google": ["google workspace", "gmail", "google drive", "google admin",
               "gsuite", "g suite", "google groups", "google calendar",
               "google docs", "google sheets"],
    "slack": ["slack"],
    "github": ["github", "pull request", "branch protection", "repo settings",
               "github actions", "gitlab"],
    "servicenow": ["servicenow", "service now", "cmdb", "service catalog"],
    "automation": ["power automate", "zapier", "logic app", "logic apps",
                   "make.com", "workflow automation", "automate this"],
    "refine": ["dial in", "refine", "brainstorm", "requirements",
               "not sure how to ask", "help me ask", "improve my prompt",
               "scope this out", "think through"],
    "writing": ["rewrite", "reword", "proofread", "edit this", "polish",
                "make this sound", "tone", "shorten this", "translate",
                "make it professional", "grammar check", "make this clearer",
                "make this friendlier", "make this more", "fix the grammar",
                "fix my grammar", "fix the spelling", "fix this sentence",
                "make this shorter", "tighten this"],
    "excel": ["excel", "spreadsheet", "formula", "pivot", "vlookup",
              "xlookup", "sumif", "conditional formatting"],
    "helpdesk": ["password reset", "reset password", "locked out",
                 "account locked", "mfa reset", "cant log in", "can't log in",
                 "cant sign in", "can't sign in", "forgot password",
                 "software request", "install request", "needs access to",
                 "new laptop", "new monitor", "request hardware"],
    "learning": ["explain", "how does", "what is", "whats the difference",
                 "what's the difference", "teach me", "walk me through",
                 "eli5", "in simple terms"],
    "summarize": ["summarize", "summarise", "tldr", "tl;dr", "key points",
                  "summary of", "condense"],
    "api": ["api", "rest api", "webhook", "endpoint", "oauth", "api key",
            "swagger", "openapi", "postman", "graphql", "rate limit"],
    "mcp": ["mcp", "model context protocol", "mcp server", "claude desktop",
            "tool use", "function calling", "connect claude to",
            "connect chatgpt to"],
    "local_llm": ["ollama", "gemma", "local llm", "local ai", "llama",
                  "mistral", "local model", "offline ai", "on-prem ai",
                  "private chatbot", "local chatbot"],
    "rmm": ["ninjaone", "ninja one", "ninjarmm", "ninja rmm", "connectwise",
            "screenconnect", "rmm", "remote monitoring"],
    "siem": ["sumo logic", "sumologic", "siem", "log source",
             "correlation rule", "search query", "ingest"],
    "edr": ["sentinelone", "sentinel one", "edr", "crowdstrike",
            "defender for endpoint", "quarantine", "threat hunt",
            "malware alert", "endpoint detection"],
    "browser": ["chrome", "microsoft edge", "edge browser", "firefox",
                "island browser", "browser extension", "browser policy",
                "bookmarks", "homepage", "popup blocker", "cache and cookies",
                "browser profile"],
    "azure": ["azure", "resource group", "virtual machine", "azure vm",
              "key vault", "app service", "azure storage", "blob storage",
              "azure network", "subscription", "azure cost", "log analytics workspace"],
    "exchange_admin": ["mailbox permission", "shared mailbox", "distribution list",
                       "dl ", "transport rule", "mail flow rule", "retention policy",
                       "litigation hold", "calendar permission", "out of office",
                       "mailbox full", "exchange online"],
    "m365_security": ["defender", "purview", "dlp", "data loss prevention",
                      "sensitivity label", "safe links", "safe attachments",
                      "quarantine release", "secure score", "ediscovery"],
    "python": ["python", "pip ", "venv", "pandas", "py script", "jupyter",
               "pyinstaller", "requests library"],
    "windows": ["windows 11", "windows 10", "bsod", "blue screen",
                "event viewer", "registry", "safe mode", "windows update",
                "group policy", "start menu", "taskbar", "windows hello"],
    "mac": ["macos", "mac os", "macbook", "imac", "keychain", "time machine",
            "jamf", "spotlight", "finder", "kernel panic"],
    "mobile": ["iphone", "ipad", "ios device", "ios update", "android",
               "samsung", "pixel phone", "mobile device", "phone wont",
               "activation lock", "mdm profile"],
    "printer": ["printer", "printing", "print queue", "spooler",
                "print driver", "toner", "print server", "label printer",
                "scan to email"],
    "appdev": ["build an app", "build a app", "web app", "website",
               "frontend", "backend", "react", "flask", "django", "node",
               "mobile app", "prototype", "mvp", "user interface", "gui app",
               "an app", "app to", "app for", "app that", "sports app",
               "tracking app", "make an app", "create an app", "app idea"],
    "linux": ["linux", "ubuntu", "debian", "centos", "rhel", "bash",
              "ssh", "systemctl", "systemd", "cron job", "crontab"],
    "ad": ["active directory", "domain controller", "gpo", "group policy object",
           "ldap", "ad group", "gpresult", "sysvol", "domain join",
           "ou structure", "ad replication"],
    "virtualization": ["vmware", "vsphere", "esxi", "vcenter", "hyper-v",
                       "hyperv", "proxmox", "snapshot", "datastore",
                       "virtual host"],
    "storage": ["file share", "network share", "ntfs", "share permission",
                "mapped drive", "file server", "quota", "dfs",
                "folder permission", "nas", "synology", "qnap", "truenas",
                "raid", "disk space", "out of space", "disk full",
                "running out of disk"],
    "database": ["sql server", "database", "stored procedure", "mysql",
                 "postgres", "postgresql", "db backup", "table", "index"],
    "migration": ["migrate", "migration", "cutover", "move to sharepoint",
                  "tenant migration", "lift and shift", "decommission"],
    "regex": ["regex", "regular expression", "pattern to match"],
    "diagram": ["diagram", "flowchart", "mermaid", "visio", "topology",
                "org chart"],
    "asset": ["asset", "inventory", "serial number", "warranty",
              "lifecycle", "loaner"],
    "deckside": ["deckside", "deck side", "swim meet", "announcer", "heat",
                 "lineup", "hy-tek", "hytek", "meet manager", "swimtopia",
                 "ebsl", "champs", "swimmer", "swim team", "relay",
                 "meet results", "check-in tab"],
    "handoff": ["handoff", "hand off", "new chat", "fresh chat", "new session",
                "context window", "summarize this chat", "summarize the chat",
                "context dump", "continue in another", "start a new conversation",
                "running out of context", "chat is getting long"],
    "voip": ["teams phone", "auto attendant", "call queue", "voip", "pbx",
             "desk phone", "phone number", "port number", "porting numbers",
             "sip trunk", "dial plan", "calling plan", "e911", "voicemail",
             "caller id", "hunt group"],
    "email_auth": ["spf", "dkim", "dmarc", "deliverability", "landing in spam",
                   "going to spam", "marked as spam", "flagged as spam",
                   "blocklist", "blacklist", "mx record", "spoofed",
                   "spoofing our domain"],
    "firewall": ["fortigate", "fortinet", "palo alto", "sonicwall",
                 "watchguard", "pfsense", "firewall rule", "nat rule",
                 "port forward", "vlan", "site-to-site", "ipsec tunnel"],
    "aws": ["aws", "s3", "ec2", "lambda", "cloudfront", "route 53", "route53",
            "iam role", "iam policy", "cloudwatch", "rds", "dynamodb",
            "elastic beanstalk", "eks"],
    "vdi": ["citrix", "azure virtual desktop", "avd", "windows 365",
            "cloud pc", "vdi", "virtual desktop", "session host", "rdp",
            "remote desktop", "rds farm", "horizon view"],
    "passwords": ["1password", "bitwarden", "lastpass", "keeper",
                  "password manager", "password vault", "shared vault",
                  "passkey", "passkeys", "credential sharing"],
    "file_transfer": ["sftp", "ftp", "file transfer", "winscp", "filezilla",
                      "rsync", "robocopy", "managed file transfer",
                      "transfer files", "moveit"],
    "licensing": ["license renewal", "true up", "true-up",
                  "enterprise agreement", "ea renewal", "renewal negotiation",
                  "procurement", "purchase order", "reseller", "vendor quote",
                  "vendor contract", "subscription cost", "per-seat"],
    "privacy_compliance": ["gdpr", "dsar", "data subject", "ccpa",
                           "right to be forgotten", "privacy request",
                           "data retention", "pii", "personal data"],
    "facilities": ["ups battery", "server room", "badge access", "door access",
                   "access card", "hvac", "generator", "rack space",
                   "power outage", "cabling", "patch panel", "comms room"],
    # --- non-technical / office roles ---
    "calendar": ["schedule a meeting", "scheduling", "reschedule",
                 "double booked", "double-booked", "find a time",
                 "availability", "time zone", "recurring meeting",
                 "block focus time", "my calendar", "his calendar",
                 "her calendar", "their calendar", "the calendar",
                 "calendar for", "manage the calendar", "calendar invite for",
                 "back to back meetings", "back-to-back meetings"],
    "email_drafting": ["draft an email", "write an email", "email to",
                       "reply to this", "respond to this email",
                       "follow up email", "follow-up email", "cold email",
                       "decline politely", "email reply", "out of office message",
                       "email asking", "email my", "email the", "inbox",
                       "unread email", "email backlog", "triage my email",
                       "thank you email", "thank-you email"],
    "meeting_prep": ["meeting prep", "briefing", "brief me", "agenda",
                     "talking points", "one on one", "1:1", "1 on 1",
                     "prep for a meeting", "prep for my meeting",
                     "board meeting", "leadership meeting", "pre-read",
                     "prep me for"],
    "notes": ["take notes", "note taking", "note-taking", "my notes",
              "meeting notes", "meeting minutes", "take minutes",
              "the minutes", "action items", "transcribe", "voice memo",
              "scratchpad", "tidy my notes", "organize my notes"],
    "presentation": ["presentation", "slide deck", "slides", "powerpoint",
                     "pitch deck", "keynote", "google slides", "talk track",
                     "speaker notes", "one-pager", "one pager"],
    "word_docs": ["word document", "word doc", "google doc", "mail merge",
                  "table of contents", "letterhead", "page numbers",
                  "track changes", "format the document", "doc template",
                  "standard operating procedure", "sop for"],
    "notebooklm": ["notebooklm", "notebook lm", "audio overview",
                   "source-grounded", "upload sources", "grounded in my",
                   "my sources", "these sources", "the sources",
                   "uploaded documents", "from my documents"],
    "travel": ["itinerary", "book a flight", "book travel", "trip to",
               "hotel block", "travel arrangements", "travel plans",
               "layover", "frequent flyer"],
    "hr": ["job description", "job posting", "interview questions",
           "interview kit", "performance review", "self review",
           "self-assessment", "candidate", "recruiting", "recruiter",
           "offer letter", "employee handbook", "engagement survey",
           "exit interview", "new hire orientation", "people ops"],
    "sales": ["sales email", "sales proposal", "sales call", "sales pipeline",
              "sales deck", "proposal for a client", "crm", "prospect",
              "discovery call", "objection", "upsell", "win-back",
              "quote for a customer", "renewal email"],
    "marketing": ["marketing", "social media", "social post", "linkedin post",
                  "newsletter", "blog post", "campaign", "seo",
                  "press release", "landing page", "brand voice",
                  "content calendar"],
    "support": ["customer support", "support reply", "angry customer",
                "refund", "escalation", "csat", "help center",
                "canned response", "ticket backlog", "customer complaint",
                "churn risk", "apology email"],
    "finance_ops": ["budget", "variance", "forecast", "invoice",
                    "purchase request", "reconciliation", "accrual",
                    "expense report", "expenses", "spend report",
                    "cost center", "po number"],
    "project_mgmt": ["project plan", "kickoff", "milestones", "raid log",
                     "gantt", "stakeholder", "retrospective", "sprint",
                     "workback", "work-back", "timeline for",
                     "dependencies", "critical path", "status update"],
    "exec_ops": ["chief of staff", "okr", "decision memo", "board deck",
                 "strategy offsite", "operating cadence", "leadership update",
                 "all hands", "all-hands", "exec summary",
                 "executive summary", "weekly priorities"],
    "events": ["offsite", "run of show", "run-of-show", "company event",
               "team event", "event planning", "venue", "catering",
               "webinar invite", "registration page", "save the date",
               "team building"],
    "legal_ops": ["contract review", "review a contract", "review the contract",
                  "review this contract", "nda", "redline", "msa",
                  "legal review", "terms of service", "sow review",
                  "signature authority", "renewal terms"],
    # --- personal / creative / academic ---
    "game_design": ["game design", "game loop", "game mechanic", "level design",
                    "playtest", "indie game", "game balance", "godot", "unity",
                    "unreal", "tabletop game", "board game", "video game",
                    "game idea", "game dev", "gamedev", "rpg system",
                    "deck builder", "deckbuilder", "mechanics for",
                    "game economy", "roguelike", "platformer"],
    "creative_art": ["concept art", "art direction", "art style", "illustration",
                     "book cover", "logo", "color palette", "midjourney",
                     "stable diffusion", "image prompt", "character design",
                     "moodboard", "mood board", "album art", "poster design",
                     "drawing of"],
    "academic": ["homework", "study guide", "study plan", "for the exam",
                 "an exam", "final exam", "midterm", "flashcards", "essay",
                 "calculus", "algebra", "geometry", "trigonometry",
                 "math problem", "solve this equation", "physics", "chemistry",
                 "biology", "history of", "world war", "ancient",
                 "thesis", "citation", "bibliography", "term paper",
                 "apa format", "mla format"],
    "investing": ["stock", "invest", "valuation", "dcf", "10-k", "10k filing",
                  "earnings", "portfolio", "etf", "ticker", "market cap",
                  "p/e ratio", "dividend", "company evaluation",
                  "evaluate a company", "due diligence", "annual report",
                  "balance sheet", "income statement", "moat"],
    "research": ["deep research", "research on", "research about",
                 "literature review", "lit review", "market research",
                 "competitive analysis", "research report", "sources on",
                 "evidence on", "systematic review", "research the",
                 "research this", "find sources", "cite sources",
                 "fact check", "fact-check"],
}


def score_destination(text: str) -> dict:
    """Return destination recommendation with scores and reasoning."""
    lw = text.lower()
    words = re.findall(r"[a-z0-9]+", lw)
    codex = sum(CODEX_SIGNALS.get(w, 0) for w in words)
    chatgpt = sum(CHATGPT_SIGNALS.get(w, 0) for w in words)

    # Keywords are start-anchored at a word boundary so "edr" can't match
    # "onedrive" or "api" match "rapid"; open-ended tails keep prefix
    # matching ("crash" -> "crashing", "cert expir" -> "cert expires").
    topics = [t for t, keys in KEYWORD_TOPICS.items()
              if any(re.search(r"\b" + re.escape(k), lw) for k in keys)]

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
        "topics": ["powershell", "azure_function", "iac", "intune",
                   "file_transfer"],
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
    "explain_concept": {
        "name": "Explain a concept",
        "destination": "ChatGPT web",
        "topics": ["learning"],
        "body": (
            "Explain the following to an IT professional who is hands-on "
            "but new to this specific area. {TASK}\n\n"
            "Structure the explanation as:\n"
            "1. One-paragraph plain-English answer first\n"
            "2. How it actually works (the mental model, with an analogy)\n"
            "3. If I'm comparing things: a side-by-side table of when to "
            "use which\n"
            "4. Common misconceptions and gotchas practitioners hit\n"
            "5. How to verify or explore this hands-on in a lab\n\n"
            "Context about my level: {INPUTS}\n"
            "Keep it concrete — real commands, real settings, real "
            "examples over abstract theory. Constraints: {CONSTRAINTS}"
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
        "topics": ["audit"],
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
            "Design a ChatGPT workspace agent and write its complete "
            "instructions, ready to paste. {TASK}\n\n"
            "Most people skip the parts that make agents actually useful, so "
            "the instructions you produce MUST contain all of these sections, "
            "fully written out (not just mentioned):\n\n"
            "1. PURPOSE & SCOPE — one sentence of purpose, an explicit "
            "out-of-scope list, allowed tools, forbidden actions.\n\n"
            "2. MEMORY SYSTEM — the agent keeps a small set of named memory "
            "notes (e.g. 'preferences', 'project-context', 'decisions'). "
            "Rules: record only stable reusable facts; convert relative "
            "dates to absolute; durable source-of-truth files always win "
            "over memory; prune stale entries when touched. Include the "
            "exact instruction text for when to read and when to update "
            "memory.\n\n"
            "3. SELF-REFLECTION LOOP — after each completed task the agent "
            "writes a 3-line reflection: what worked, what to reuse, what "
            "to change next time. Reflections feed memory and skills, not "
            "uncontrolled behavior changes.\n\n"
            "4. SKILL MAKER — when the agent notices the same kind of task "
            "for the third time, it proposes a named skill: trigger, "
            "inputs, numbered steps, verification. Skills get saved and "
            "reused instead of re-deriving the workflow.\n\n"
            "5. TASK CONTRACT — every piece of work starts with scope, "
            "inputs, constraints, outputs, and verification; the agent "
            "plans first and confirms before executing anything big.\n\n"
            "6. VERIFICATION & HANDOFF — never claim completion without "
            "stating what was checked; if work remains, leave a handoff "
            "note with exact next steps.\n\n"
            "7. INSTRUCTION HYGIENE — once a month (or when instructions "
            "feel bloated) the agent proposes deletions: redundant rules, "
            "stale references, conflicting guidance.\n\n"
            "Agent purpose and context: {INPUTS}\nConstraints: {CONSTRAINTS}\n\n"
            "Output the final agent instructions as one copy-ready block, "
            "then a short note on how to test the agent with 3 sample tasks."
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
        "topics": ["network", "firewall"],
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
        "topics": ["monitoring", "reporting", "siem"],
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
        "topics": ["entra"],
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
        "topics": ["bulk_data", "powershell"],
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
    "azure_task": {
        "name": "Azure admin task",
        "destination": "Both",
        "topics": ["azure"],
        "body": (
            "Azure administration task. {TASK}\n\n"
            "Context: {INPUTS}\n\n"
            "Provide:\n- Portal steps AND the az CLI / PowerShell equivalent\n"
            "- Resource group, tagging, and naming that fits convention\n"
            "- Least-privilege RBAC at the narrowest scope that works\n"
            "- Projected monthly cost of anything created, and the cheaper "
            "alternative considered\n- Rollback/teardown steps\n\n"
            "Constraints: {CONSTRAINTS}\nVerification: {VERIFICATION}"
        ),
    },
    "creative_brief": {
        "name": "Creative / game design brief",
        "destination": "ChatGPT web",
        "topics": ["creative_art", "game_design"],
        "body": (
            "Work with me as a creative collaborator. {TASK}\n\n"
            "References and material: {INPUTS}\n\n"
            "Process:\n"
            "1. Ask me the 2-3 questions that most change the direction "
            "(audience, mood, constraints) before producing anything\n"
            "2. Propose 3 distinct directions, each in a few sentences — "
            "different, not variations of one idea\n"
            "3. Develop the direction I pick, explaining choices in craft "
            "terms\n"
            "4. End with the concrete next step: prototype, sketch, "
            "playtest, or revision\n\n"
            "Constraints: {CONSTRAINTS}\n"
            "Push back where my idea has a known pitfall — agreement isn't "
            "the job."
        ),
    },
    "tutor_session": {
        "name": "Tutoring session",
        "destination": "ChatGPT web",
        "topics": ["academic"],
        "body": (
            "Act as my tutor. {TASK}\n\n"
            "My current level and where I'm stuck: {INPUTS}\n\n"
            "How to work with me:\n"
            "1. Work step-by-step, naming the concept each step uses\n"
            "2. Verify the answer independently (plug back in, check "
            "units/magnitude) before presenting it\n"
            "3. Then give me ONE similar problem to do alone and check "
            "my work\n"
            "4. If I'm writing (essay/report), improve MY argument and "
            "voice — don't replace them\n\n"
            "Constraints: {CONSTRAINTS}\n"
            "Goal is that I can do the next one without you."
        ),
    },
    "investment_research": {
        "name": "Investment research (not advice)",
        "destination": "ChatGPT web",
        "topics": ["investing"],
        "body": (
            "Research this as an equity analyst would. {TASK}\n\n"
            "What I already know or hold: {INPUTS}\n\n"
            "Required structure:\n"
            "1. The business in plain language: how it actually makes money\n"
            "2. The numbers with dates: revenue trend, margins, cash flow, "
            "debt (note your data may be stale — tell me to verify "
            "current figures)\n"
            "3. Bull case AND bear case, equally seriously\n"
            "4. Valuation context: current multiples vs named peers, and "
            "what would have to be true to justify the price\n"
            "5. The 3 questions I should answer before deciding anything\n\n"
            "Constraints: {CONSTRAINTS}\n"
            "This is information, not financial advice — say so, and for "
            "personal decisions point me to a licensed advisor."
        ),
    },
    "research_brief": {
        "name": "Deep research brief",
        "destination": "ChatGPT web",
        "topics": ["research"],
        "body": (
            "Research this thoroughly. {TASK}\n\n"
            "Scope and what I'll use it for: {INPUTS}\n\n"
            "Method:\n"
            "1. Restate the question and confirm scope before diving in\n"
            "2. Use independent source types: primary data, expert "
            "analysis, and at least one opposing view\n"
            "3. Cite which source supports each key claim; flag "
            "single-source claims as weak\n"
            "4. Name disagreements between sources — don't average them "
            "away\n"
            "5. Deliver: the answer, your confidence level, and what "
            "remains unknown\n\n"
            "Constraints: {CONSTRAINTS}\n"
            "Claims without sources don't go in the report."
        ),
    },
    "exec_brief": {
        "name": "Executive brief / decision memo",
        "destination": "ChatGPT web",
        "topics": ["exec_ops", "meeting_prep"],
        "body": (
            "Produce a decision-ready brief. {TASK}\n\n"
            "Source material: {INPUTS}\n\n"
            "Format (one page maximum):\n"
            "1. The decision needed or meeting purpose, and the deadline\n"
            "2. Recommendation up front, with the three strongest reasons\n"
            "3. Options considered with honest trade-offs\n"
            "4. What the audience will push back on, with responses\n"
            "5. Next steps with owners and dates\n\n"
            "Write for a reader with 90 seconds. Detail goes in an "
            "appendix. Constraints: {CONSTRAINTS}"
        ),
    },
    "email_compose": {
        "name": "Email draft",
        "destination": "ChatGPT web",
        "topics": ["email_drafting"],
        "body": (
            "Draft this email. {TASK}\n\n"
            "Context (relationship, history, anything to reference): "
            "{INPUTS}\n\n"
            "Requirements:\n"
            "- Subject line that states the ask or decision\n"
            "- The point in the first sentence; background after, only if needed\n"
            "- ONE ask, with an explicit deadline or next step\n"
            "- Under 150 words unless the content truly requires more\n"
            "- Tone matched to the relationship: {CONSTRAINTS}\n\n"
            "Give me two versions: one direct, one warmer. Flag anything "
            "that could land wrong."
        ),
    },
    "office_document": {
        "name": "Document / deck creation",
        "destination": "ChatGPT web",
        "topics": ["word_docs", "presentation"],
        "body": (
            "Help me create this document or deck. {TASK}\n\n"
            "Audience and occasion: {INPUTS}\n\n"
            "Work in this order:\n"
            "1. Confirm the one sentence the audience should take away\n"
            "2. Propose the outline (headings / slide headlines that tell "
            "the story alone) and wait for my OK\n"
            "3. Draft section by section, takeaway-first\n"
            "4. Finish with a formatting checklist (styles, table of "
            "contents, page numbers / speaker notes)\n\n"
            "Constraints: {CONSTRAINTS}"
        ),
    },
    "spreadsheet_help": {
        "name": "Spreadsheet help",
        "destination": "ChatGPT web",
        "topics": ["excel"],
        "body": (
            "Help me with a spreadsheet task. {TASK}\n\n"
            "My data layout (columns, sample rows, sheet names): {INPUTS}\n\n"
            "Requirements:\n"
            "- Give the exact formula or steps for MY layout, not a generic example\n"
            "- Explain what each part of the formula does in one line\n"
            "- Mention the common error I'll hit and how to fix it\n"
            "- If there's a simpler built-in feature (pivot, filter, "
            "conditional format), say so first\n\n"
            "Constraints: {CONSTRAINTS}\n"
            "I'll verify on a copy of the data before using it for real."
        ),
    },
    "email_deliverability": {
        "name": "Email deliverability fix",
        "destination": "Both",
        "topics": ["email_auth"],
        "body": (
            "Diagnose and fix email deliverability/authentication. {TASK}\n\n"
            "Context: {INPUTS}\n\n"
            "Work in this order and show findings at each step:\n"
            "1. Inventory every legitimate sending source for the domain\n"
            "2. SPF: all sources covered, under 10 DNS lookups\n"
            "3. DKIM: signing enabled and verified per source (real headers)\n"
            "4. DMARC: policy, alignment, and rua reporting status\n"
            "5. Reputation/content only after authentication is clean\n\n"
            "Constraints: {CONSTRAINTS}\n"
            "Never recommend jumping straight to p=reject — monitoring "
            "comes first.\nVerification: {VERIFICATION}"
        ),
    },
    "aws_task": {
        "name": "AWS admin task",
        "destination": "Both",
        "topics": ["aws"],
        "body": (
            "AWS administration task. {TASK}\n\n"
            "Context: {INPUTS}\n\n"
            "Provide:\n- Console steps AND the aws CLI equivalent\n"
            "- Region, tagging, and naming that fits convention\n"
            "- Least-privilege IAM at the narrowest scope that works\n"
            "- Projected monthly cost of anything created, and the cheaper "
            "alternative considered\n- Rollback/teardown steps\n\n"
            "Constraints: {CONSTRAINTS}\nVerification: {VERIFICATION}"
        ),
    },
    "python_script": {
        "name": "Python script",
        "destination": "Codex",
        "topics": ["python"],
        "body": (
            "Write a Python script. {TASK}\n\n"
            "Requirements:\n- Parameters via argparse, not code edits\n"
            "- Stdlib first; any dependency pinned in requirements.txt for a venv\n"
            "- Explicit error handling for missing files, bad data, no network\n"
            "- --dry-run flag on anything destructive\n"
            "- Type hints on public functions; a 5-line usage note at the top\n"
            "- Inputs: {INPUTS}\n- Constraints: {CONSTRAINTS}\n\n"
            "Test with real-shaped sample data and show me the output before "
            "widening scope.\n\nVerification: {VERIFICATION}"
        ),
    },
    "app_build": {
        "name": "Build an app (MVP-first)",
        "destination": "Both",
        "topics": ["appdev"],
        "body": (
            "Help me build an app. {TASK}\n\n"
            "Who it's for and where it runs: {INPUTS}\n\n"
            "Work MVP-first:\n"
            "1. Restate the one problem this app solves and for whom\n"
            "2. Propose the smallest version that's actually usable (one "
            "core flow) and what we're explicitly deferring\n"
            "3. Recommend boring, maintainable tech for our context — with "
            "one sentence on why over the alternatives\n"
            "4. Scaffold it and get the core flow working with real-shaped "
            "data before any polish or auth\n"
            "5. Give me a test checklist and what feedback to collect from "
            "the first real user\n\n"
            "Constraints: {CONSTRAINTS}\nVerification: {VERIFICATION}"
        ),
    },
    "api_integration": {
        "name": "API integration build",
        "destination": "Codex",
        "topics": ["api"],
        "body": (
            "Build an API integration. {TASK}\n\n"
            "API context: {INPUTS}\n\n"
            "Requirements:\n"
            "- Start by reading/confirming the auth model; use least-privilege "
            "scopes and keep secrets in environment/vault, never in code\n"
            "- Prove one call works (show me the curl equivalent) before "
            "building the full integration\n"
            "- Handle paging, rate limits (429 with Retry-After), and "
            "timeouts; make writes idempotent\n"
            "- Log requests/responses (sanitized) for debugging\n"
            "- Include tests for the failure paths: expired token, empty "
            "result, throttling\n\n"
            "Constraints: {CONSTRAINTS}\nVerification: {VERIFICATION}"
        ),
    },
    "mcp_integration": {
        "name": "MCP integration (connect tools to AI)",
        "destination": "Both",
        "topics": ["mcp"],
        "body": (
            "Help me connect tools/data to an AI client using the Model "
            "Context Protocol (MCP). {TASK}\n\n"
            "Setup context: {INPUTS}\n\n"
            "Walk me through:\n"
            "1. Whether an existing MCP server covers this (prefer that) or "
            "we should build one\n"
            "2. Credential setup with the narrowest scopes the tasks need — "
            "prefer read-only unless writes are required\n"
            "3. Client configuration (e.g. claude_desktop_config.json) and "
            "how to verify the tools actually appear\n"
            "4. If building a server: tool definitions with precise "
            "descriptions (the AI's only manual), input validation, and "
            "safe error messages\n"
            "5. A test plan: one harmless read-only call first, then each "
            "tool with real-shaped data\n\n"
            "Security review: list what the AI will be able to do after "
            "this, and what limits it.\n\nConstraints: {CONSTRAINTS}"
        ),
    },
    "local_chatbot": {
        "name": "Local AI chatbot (Ollama)",
        "destination": "Both",
        "topics": ["local_llm"],
        "body": (
            "Help me build a local, private AI chatbot using Ollama. {TASK}\n\n"
            "Environment: {INPUTS}\n\n"
            "Cover, in order:\n"
            "1. Model choice for my hardware — e.g. Gemma at the size/"
            "quantization my RAM/VRAM supports — with honest expectations "
            "vs cloud models\n"
            "2. Install and pull commands, and a first smoke test\n"
            "3. A system prompt for my use case: role, tone, what to refuse, "
            "knowledge limits (small local models need explicit guidance)\n"
            "4. Front end options: terminal, Open WebUI, or a small script "
            "against the localhost API — recommend one for my needs\n"
            "5. If my own documents/data should inform answers: the simplest "
            "approach that works (paste-in context first, RAG only if "
            "needed)\n"
            "6. A test script of 5-10 representative questions and what "
            "good answers look like\n\n"
            "Everything must run fully local — no cloud calls, no data "
            "leaving the machine.\n\nConstraints: {CONSTRAINTS}"
        ),
    },
    "chat_handoff": {
        "name": "Chat handoff summary",
        "destination": "ChatGPT web",
        "topics": ["handoff"],
        "body": (
            "This conversation is getting long and I want to continue the "
            "work in a fresh chat. {TASK}\n\n"
            "Write a handoff summary I can paste as the FIRST message of a "
            "new chat. Output it as ONE markdown code block (never split it) "
            "containing:\n\n"
            "## Objective — what we're ultimately trying to achieve, one "
            "paragraph\n"
            "## Current state — what's done and verified, what exists now "
            "(files, decisions, working pieces) with exact names/paths\n"
            "## Decisions already made — settled choices with their reasons, "
            "so the next chat doesn't relitigate them\n"
            "## In flight — what we were in the middle of, exactly where it "
            "stopped\n"
            "## Next steps — ordered, starting with the very next action\n"
            "## Gotchas — anything we learned the hard way (failed "
            "approaches, constraints, quirks)\n\n"
            "Rules: be lean — facts the next chat NEEDS, not a transcript. "
            "Include exact identifiers (file paths, names, versions, URLs) "
            "since the new chat can't see this one. Convert relative dates "
            "to absolute. Don't include anything the next chat can read "
            "from files it will have access to.\n\n"
            "Context: {INPUTS}\nConstraints: {CONSTRAINTS}"
        ),
    },
    "deckside_dev": {
        "name": "DeckSide development task",
        "destination": "Codex",
        "topics": ["deckside"],
        "body": (
            "DeckSide development task (Electron swim meet-day app, vanilla "
            "JS renderer, better-sqlite3, pdf-parse, msedge-tts/Piper). "
            "{TASK}\n\n"
            "Context: {INPUTS}\n\n"
            "Hard rules (from AGENTS.md — violating these fails review):\n"
            "- Orient from AGENTS.md and the relevant BACKLOG.md entry first\n"
            "- Local-first; SQLite is the source of truth; imported meet "
            "files are the source of truth for meet data\n"
            "- Renderer never accesses the DB — typed IPC/services only\n"
            "- Extend existing modules; keep feature-based structure\n"
            "- Coach and parent dashboards stay isolated\n"
            "- Imports stay backward compatible — test old fixture PDFs "
            "before claiming done\n\n"
            "Plan the slice first (schema → service/IPC → renderer), confirm "
            "the plan, then implement one coherent slice with evidence.\n"
            "Update CHANGELOG.md. Constraints: {CONSTRAINTS}\n"
            "Verification: {VERIFICATION}"
        ),
    },
    "diagram_request": {
        "name": "Technical diagram (Mermaid)",
        "destination": "ChatGPT web",
        "topics": ["diagram"],
        "body": (
            "Create a technical diagram for me. {TASK}\n\n"
            "Components and connections: {INPUTS}\n\n"
            "Requirements:\n- Output Mermaid source (diagram-as-code) so it "
            "lives in version control\n"
            "- One audience, one question the diagram answers — tell me if "
            "I'm asking for two diagrams in one\n"
            "- Label every connection with what flows over it\n"
            "- Fewer boxes beats complete: link or footnote detail rather "
            "than cramming it in\n\n"
            "After the diagram, list what you intentionally left out.\n"
            "Constraints: {CONSTRAINTS}"
        ),
    },
    "rewrite_text": {
        "name": "Rewrite / edit text",
        "destination": "ChatGPT web",
        "topics": ["writing", "summarize"],
        "body": (
            "Edit this text for me. {TASK}\n\n"
            "Audience and tone: {INPUTS}\n\n"
            "Rules:\n- Preserve my meaning and voice — edit, don't rewrite "
            "from scratch\n- Fix clarity, grammar, and flow; cut filler\n"
            "- Keep it the same length or shorter unless I said otherwise\n\n"
            "Give me:\n1. The edited version\n2. A short list of what you "
            "changed and why\n3. Anything that was ambiguous where you had "
            "to guess my intent\n\nConstraints: {CONSTRAINTS}"
        ),
    },
    "dial_in": {
        "name": "Dial in the ask (plan first)",
        "destination": "Both",
        "topics": ["refine"],
        "body": (
            "I have a rough idea and I want to dial it in before any work "
            "happens — like plan mode in Codex/Claude Code. {TASK}\n\n"
            "Work with me in this order, and do NOT start executing until I "
            "approve the plan:\n"
            "1. Restate what you think I'm asking for, in your own words.\n"
            "2. List your assumptions and the unknowns that would change the "
            "approach.\n"
            "3. Ask me up to 3 clarifying questions — the ones whose answers "
            "matter most.\n"
            "4. Propose 2-3 approaches with trade-offs and recommend one.\n"
            "5. Write a short numbered plan for the recommended approach, "
            "with what done looks like for each step.\n"
            "6. Wait for my approval, then execute one step at a time, "
            "checking in after each.\n\n"
            "What I know so far: {INPUTS}\nConstraints: {CONSTRAINTS}"
        ),
    },
    "troubleshoot": {
        "name": "Troubleshoot / fix it",
        "destination": "Both",
        "topics": ["fixit"],
        "body": (
            "Help me troubleshoot and fix this. {TASK}\n\n"
            "Known context: {INPUTS}\n\n"
            "Work it systematically:\n"
            "1. Tell me what to confirm first: exact symptom, scope (one user "
            "or many), and since when.\n"
            "2. List the most likely causes for these symptoms, ranked, and "
            "say why.\n"
            "3. For each cause: the exact check or command to run, and what "
            "result confirms or rules it out — cheapest checks first.\n"
            "4. Check what changed recently (updates, policies, passwords, "
            "certificates) before assuming hardware or reinstalls.\n"
            "5. Give the fix for the confirmed cause, then how to verify with "
            "the affected user, and what to document.\n\n"
            "Change one variable at a time. Constraints: {CONSTRAINTS}"
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
        "topics": ["learning"],
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
    "troubleshooter": {
        "name": "Troubleshooter Agent",
        "topics": ["fixit", "network"],
        "body": (
            "Troubleshoot systematically: reproduce or precisely describe the "
            "symptom, establish scope (one user or many), check what changed "
            "recently, test likely causes cheapest-first, change one variable "
            "at a time, and verify the fix with the affected user before "
            "closing. Never guess-and-reinstall."
        ),
    },
    "plan_first": {
        "name": "Plan-First Agent",
        "topics": ["refine"],
        "body": (
            "Before doing any work: restate the goal in your own words, list "
            "assumptions and unknowns, ask up to 3 clarifying questions if "
            "anything is ambiguous, then propose a short numbered plan and "
            "wait for approval. After approval, execute one step at a time "
            "and check in at each milestone rather than doing everything at "
            "once."
        ),
    },
    "notion": {
        "name": "Notion Agent",
        "topics": ["notion"],
        "body": (
            "Act as a Notion workspace specialist. Choose databases over "
            "loose pages when items repeat; design properties, views, and "
            "relations before adding content; use templates for recurring "
            "entries; and keep a tidy sidebar — every new structure needs an "
            "owner and a reason to exist."
        ),
    },
    "zoom": {
        "name": "Zoom Agent",
        "topics": ["zoom"],
        "body": (
            "Act as a Zoom admin/meetings specialist: meeting vs webinar "
            "trade-offs, registration and security settings (waiting rooms, "
            "passcodes), recording storage and retention, and turning "
            "recordings/transcripts into minutes, action items, and "
            "follow-ups."
        ),
    },
    "google_workspace": {
        "name": "Google Workspace Agent",
        "topics": ["google"],
        "body": (
            "Act as a Google Workspace administrator. Give both the Admin "
            "console path and the API/GAM command equivalent, scope changes "
            "to the right OU or group, mind propagation delays, and call out "
            "Drive sharing implications (internal vs external, shared "
            "drives vs my drive) for anything touching files."
        ),
    },
    "slack": {
        "name": "Slack Agent",
        "topics": ["slack"],
        "body": (
            "Act as a Slack admin specialist: channel naming and lifecycle "
            "conventions, public-by-default with documented exceptions, app "
            "and integration permission review before install, retention "
            "policy awareness, and workflow automations for recurring asks."
        ),
    },
    "github": {
        "name": "GitHub Agent",
        "topics": ["github"],
        "body": (
            "Act as a GitHub administrator and reviewer: branch protection "
            "with required reviews on anything production, least-privilege "
            "tokens and fine-grained PATs over classic, secrets in Actions "
            "secrets never in code, and PR descriptions that explain why, "
            "not just what."
        ),
    },
    "servicenow": {
        "name": "ServiceNow Agent",
        "topics": ["servicenow"],
        "body": (
            "Act as a ServiceNow specialist: pick the right record type "
            "(incident vs request vs change), keep work notes vs customer "
            "comments straight, link the affected CI, and keep state "
            "transitions honest — a ticket's history should let anyone "
            "reconstruct what happened."
        ),
    },
    "automation_platforms": {
        "name": "Automation Platform Agent",
        "topics": ["automation"],
        "body": (
            "Act as a Power Automate/Zapier/Logic Apps builder: idempotent "
            "flows, explicit error handling and retry policies, connection "
            "references owned by a service account not a person, throttling "
            "awareness, and a kill switch — every flow needs an owner and a "
            "way to turn it off."
        ),
    },
    "writing_editor": {
        "name": "Writing Editor Agent",
        "topics": ["writing", "summarize"],
        "body": (
            "Act as an editor, not a rewriter: preserve the author's voice "
            "and meaning, fix clarity and grammar, cut filler, and match the "
            "stated audience and tone. Show the edited version first, then a "
            "short list of what you changed and why. Never pad — shorter is "
            "usually better."
        ),
    },
    "spreadsheet": {
        "name": "Spreadsheet Agent",
        "topics": ["excel", "reporting"],
        "body": (
            "Act as an Excel/Sheets specialist. Ask for the actual column "
            "layout before writing formulas; prefer modern functions "
            "(XLOOKUP, FILTER, LET) but state version requirements; explain "
            "each formula piece by piece; and always include a way to "
            "sanity-check the result against a few known rows."
        ),
    },
    "helpdesk": {
        "name": "Helpdesk Agent",
        "topics": ["helpdesk"],
        "body": (
            "Act as a frontline IT support specialist: verify identity "
            "before account actions, follow the least-disruptive fix first, "
            "write user-facing replies in plain language, capture what was "
            "done in the ticket, and spot repeat issues that deserve a KB "
            "article or automation instead of another one-off fix."
        ),
    },
    "api_integration": {
        "name": "API Integration Agent",
        "topics": ["api"],
        "body": (
            "Act as an API integration specialist: read the auth model first "
            "(OAuth vs key vs token) and use least-privilege scopes; prove "
            "one call works (curl/Postman) before writing the integration; "
            "handle paging, rate limits (429/Retry-After), and timeouts from "
            "day one; make writes idempotent; keep secrets in a vault or "
            "environment, never in code."
        ),
    },
    "mcp": {
        "name": "MCP Agent",
        "topics": ["mcp"],
        "body": (
            "Act as a Model Context Protocol specialist. MCP servers expose "
            "tools/resources to AI clients (Claude Desktop, Claude Code, "
            "etc.): grant the narrowest scopes the task needs, treat tool "
            "descriptions as the AI's only manual (write them precisely), "
            "prefer read-only tools unless writes are required, and verify "
            "the client actually lists the tools after config changes."
        ),
    },
    "local_llm": {
        "name": "Local AI Agent",
        "topics": ["local_llm"],
        "body": (
            "Act as a local-LLM specialist (Ollama, Gemma, Llama, Mistral): "
            "match model size and quantization to the actual hardware "
            "(VRAM/RAM) before promising performance, design a tight system "
            "prompt because small models need more guidance, set "
            "expectations honestly vs cloud models, and lean into the "
            "advantages — privacy, no per-token cost, offline operation."
        ),
    },
    "rmm": {
        "name": "RMM Agent",
        "topics": ["rmm"],
        "body": (
            "Act as an RMM specialist (NinjaOne, ConnectWise): scripts "
            "deployed via RMM usually run as SYSTEM — write and test for "
            "that context; always pilot on a small device group with exit "
            "codes the platform can read; scope policies by org/site/group "
            "deliberately; and remember every action leaves an audit trail "
            "a customer may read."
        ),
    },
    "siem": {
        "name": "SIEM Agent",
        "topics": ["siem", "monitoring"],
        "body": (
            "Act as a SIEM specialist (Sumo Logic and similar): anchor every "
            "search to a source category and a bounded time range, build "
            "queries incrementally (filter, parse, aggregate), validate "
            "against a known event before trusting results, and mind ingest "
            "and scan costs — a scheduled search that scans everything "
            "hourly is a bill, not a control."
        ),
    },
    "edr": {
        "name": "EDR Agent",
        "topics": ["edr", "security"],
        "body": (
            "Act as an EDR specialist (SentinelOne and similar): triage "
            "before acting — what fired, on which endpoint, run by which "
            "user; contain (network isolate/quarantine) when in doubt, "
            "investigate after; treat every exclusion as a permanent risk "
            "decision needing justification; capture evidence before "
            "remediation erases it."
        ),
    },
    "browser_admin": {
        "name": "Browser Management Agent",
        "topics": ["browser"],
        "body": (
            "Act as an enterprise browser specialist (Chrome, Edge, Firefox, "
            "Island): manage via policy (Intune/GPO/ADMX) not per-device "
            "tweaks, control extensions with allowlists rather than chasing "
            "bad installs, know the profile/sync implications of policy "
            "changes, and for troubleshooting isolate variables: new "
            "profile, extensions off, then cache."
        ),
    },
    "azure": {
        "name": "Azure Agent",
        "topics": ["azure", "azure_function", "iac"],
        "body": (
            "Act as an Azure administrator: everything in a resource group "
            "with tags (owner, purpose, environment), portal steps AND the "
            "az CLI/PowerShell equivalent, least-privilege RBAC at the "
            "narrowest scope, secrets in Key Vault, and state the monthly "
            "cost of anything you propose creating."
        ),
    },
    "exchange": {
        "name": "Exchange Online Agent",
        "topics": ["exchange_admin", "m365"],
        "body": (
            "Act as an Exchange Online specialist: mailbox and calendar "
            "permissions via the right cmdlets (and what each level grants), "
            "shared mailboxes vs DLs vs M365 groups trade-offs, transport "
            "rule order matters, retention/litigation hold implications "
            "before touching data, and message traces to prove mail flow "
            "claims."
        ),
    },
    "m365_security": {
        "name": "Microsoft Security Agent",
        "topics": ["m365_security", "security", "privacy_compliance"],
        "body": (
            "Act as a Microsoft Defender/Purview specialist: check the "
            "license tier before recommending features (E3 vs E5 changes "
            "the answer), start DLP and sensitivity policies in simulation "
            "mode, tune Safe Links/Attachments with business impact in "
            "mind, and treat Secure Score as a guide — not every "
            "recommendation fits every org."
        ),
    },
    "python": {
        "name": "Python Agent",
        "topics": ["python"],
        "body": (
            "Act as a Python developer for IT automation: stdlib first, "
            "minimal dependencies in a venv with pinned requirements, "
            "pathlib over string paths, explicit error handling with "
            "actionable messages, type hints on public functions, and a "
            "dry-run flag on anything destructive. Scripts should run the "
            "same on Windows and macOS unless stated."
        ),
    },
    "windows": {
        "name": "Windows Agent",
        "topics": ["windows"],
        "body": (
            "Act as a Windows desktop specialist: Event Viewer and "
            "Reliability Monitor before guessing, check recent updates and "
            "driver changes first, know the managed-device boundaries "
            "(GPO/Intune may revert manual fixes), prefer per-user fixes "
            "before machine-wide ones, and capture the exact error text "
            "for the record."
        ),
    },
    "mac": {
        "name": "Mac Agent",
        "topics": ["mac"],
        "body": (
            "Act as a macOS specialist: Console logs and diagnostics before "
            "guessing, mind MDM management (Jamf/Intune) and what it locks, "
            "keychain issues behind many sign-in problems, safe mode and a "
            "test user account to isolate system vs profile issues, and "
            "respect SIP — never advise disabling protections casually."
        ),
    },
    "mobile": {
        "name": "Mobile Device Agent",
        "topics": ["mobile", "intune"],
        "body": (
            "Act as a mobile device specialist (iOS/Android under MDM): "
            "check enrollment and compliance state first, corporate vs BYOD "
            "changes what you may touch, app/profile pushes need network "
            "and check-in to land, and activation lock/factory reset are "
            "last resorts with data-loss warnings stated upfront."
        ),
    },
    "printing": {
        "name": "Print Agent",
        "topics": ["printer"],
        "body": (
            "Act as a print specialist: scope first (one user, one printer, "
            "or everyone — they have different causes), check queue/spooler "
            "before drivers, driver type matters (universal vs "
            "model-specific), test from the server/host directly to split "
            "network vs client issues, and document the working "
            "driver/port combo when fixed."
        ),
    },
    "app_builder": {
        "name": "App Builder Agent",
        "topics": ["appdev"],
        "body": (
            "Act as a pragmatic app builder: start from who uses it and the "
            "one problem it solves, ship the smallest working version first "
            "(one screen, real data), pick boring proven tech the team can "
            "maintain, plan for where it runs and who fixes it at 2am "
            "before adding features, and iterate from real user feedback."
        ),
    },
    "linux": {
        "name": "Linux Agent",
        "topics": ["linux"],
        "body": (
            "Act as a Linux administrator: systemctl status and journalctl "
            "before guessing, config-test before restart (nginx -t and "
            "friends), bash with set -euo pipefail and shellcheck-clean, "
            "explicit about which distro/version commands target, and "
            "minimal sudo — say exactly why each elevated command needs it."
        ),
    },
    "active_directory": {
        "name": "Active Directory Agent",
        "topics": ["ad"],
        "body": (
            "Act as an on-prem Active Directory specialist: changes in the "
            "right OU with group-based access (AGDLP), gpresult/RSOP "
            "evidence before blaming a GPO, replication awareness (a change "
            "isn't done until all DCs agree), recycle bin and tombstone "
            "awareness before deleting, and never touch schema or "
            "domain-level GPOs casually."
        ),
    },
    "virtualization": {
        "name": "Virtualization Agent",
        "topics": ["virtualization"],
        "body": (
            "Act as a virtualization specialist (VMware/Hyper-V): snapshots "
            "are NOT backups and old snapshots kill performance, check host "
            "resources before blaming the guest, mind overcommit ratios, "
            "verify backup/replication state before any host work, and "
            "know the blast radius — one host change can touch every VM "
            "on it."
        ),
    },
    "file_storage": {
        "name": "Storage & Shares Agent",
        "topics": ["storage"],
        "body": (
            "Act as a file storage specialist: permissions via groups never "
            "individuals (AGDLP), know NTFS vs share permission interaction "
            "(most restrictive wins), export current ACLs before changing "
            "anything, watch inheritance breaks — they're where audits "
            "fail, and treat 'Everyone: Full Control' as an incident."
        ),
    },
    "database": {
        "name": "Database Agent",
        "topics": ["database"],
        "body": (
            "Act as a database administrator: confirmed backup before any "
            "change, every UPDATE/DELETE inside a transaction with the "
            "rowcount checked before COMMIT, SELECT the rows first to see "
            "what you'll touch, no schema changes during business hours, "
            "and parameterized queries always — never string-built SQL."
        ),
    },
    "migration": {
        "name": "Migration Agent",
        "topics": ["migration"],
        "body": (
            "Act as a migration specialist: inventory the source completely "
            "before promising dates, migrate a pilot wave first and "
            "validate counts/permissions/access, plan coexistence (what "
            "works during the transition), communicate cutover clearly, "
            "and keep the source read-only — not deleted — until "
            "validation passes."
        ),
    },
    "diagramming": {
        "name": "Diagram Agent",
        "topics": ["diagram"],
        "body": (
            "Act as a technical diagramming specialist: text-first formats "
            "(Mermaid) so diagrams live in version control, one audience "
            "per diagram (exec overview vs engineer detail are different "
            "drawings), label every connection with what flows over it, "
            "and fewer boxes beats complete — link to detail instead of "
            "cramming it in."
        ),
    },
    "asset_mgmt": {
        "name": "Asset Management Agent",
        "topics": ["asset"],
        "body": (
            "Act as an IT asset manager: one source of truth reconciled "
            "against reality (RMM/Intune/MDM exports), every asset has an "
            "owner and a lifecycle stage, capture serial/warranty/purchase "
            "data at intake not retirement, and tie asset records to "
            "on/offboarding so nothing walks away."
        ),
    },
    "deckside_architect": {
        "name": "DeckSide Architect Agent",
        "topics": ["deckside"],
        "body": (
            "You are working on DeckSide, a Windows x64 Electron swim "
            "meet-day app (vanilla JS renderer, better-sqlite3, pdf-parse, "
            "msedge-tts/Piper). Hard rules: orient from AGENTS.md first; "
            "local-first with no required cloud; SQLite is the source of "
            "truth and imported meet files are the source of truth for meet "
            "data; the renderer NEVER touches the DB — typed IPC/services "
            "only; feature-based structure, extend existing modules over "
            "creating duplicates; coach and parent dashboards stay isolated; "
            "imports must remain backward compatible."
        ),
    },
    "deckside_assistant": {
        "name": "DeckSide Assistant Designer Agent",
        "topics": ["deckside", "local_llm"],
        "body": (
            "Design DeckSide's AI assistant as an Operating Companion, not "
            "a chatbot: better context engineering beats a smarter model. "
            "Deterministic handlers before LLM reasoning; LLMs generate "
            "intents, capabilities execute through DeckSide APIs "
            "(scratchSwimmer, replaceSwimmer, lineupSuggestion, …). Every "
            "mutation flows Interpret → Preview → Human Approval → API "
            "Validation → Apply. Conversation history and LLM output are "
            "never sources of truth; ask for clarification rather than "
            "guess meet context; stay model-agnostic (Gemma first, app "
            "fully functional with no model installed)."
        ),
    },
    "voip": {
        "name": "Telephony Agent",
        "topics": ["voip"],
        "body": (
            "Act as a telephony/Teams Phone specialist. Map the full call "
            "flow before changing it (numbers, auto attendants, call queues, "
            "agents, hours, voicemail). Mind the irreversible: number ports "
            "and emergency (e911) addresses get triple-checked. Test every "
            "change with a real inbound call from outside, after hours and "
            "during, before calling it done."
        ),
    },
    "deliverability": {
        "name": "Email Deliverability Agent",
        "topics": ["email_auth"],
        "body": (
            "Act as an email authentication specialist. Diagnose in order: "
            "SPF (all sending sources included, under 10 DNS lookups), DKIM "
            "(signing on every source), DMARC (policy and rua reporting), "
            "then content/reputation. Never jump to p=reject without "
            "monitoring rua reports first; legitimate senders you forgot "
            "about will silently lose mail. Verify with real headers, not "
            "assumptions."
        ),
    },
    "firewall": {
        "name": "Firewall Agent",
        "topics": ["firewall", "network"],
        "body": (
            "Treat every firewall change as production change control: "
            "state the exact rule (source, destination, port, direction), "
            "where it sits in rule order, and what shadows or supersedes it. "
            "Narrowest scope that works — no any/any, ever. Capture the "
            "config before and after, test the intended traffic AND that "
            "previously-blocked traffic still blocks, and schedule a "
            "rollback window."
        ),
    },
    "aws": {
        "name": "AWS Agent",
        "topics": ["aws"],
        "body": (
            "Apply AWS practice: least-privilege IAM scoped to the resource "
            "(no *), tag everything (owner, purpose, environment), pick the "
            "region deliberately, and state the monthly cost of anything "
            "created. Prefer managed/serverless over self-run, S3 lifecycle "
            "rules over manual cleanup, and always leave teardown steps."
        ),
    },
    "vdi": {
        "name": "VDI Agent",
        "topics": ["vdi"],
        "body": (
            "Act as a virtual desktop specialist (Citrix/AVD/Windows 365). "
            "Separate the layers before debugging: endpoint and network, "
            "gateway/connector, session host resources, profile container "
            "(FSLogix), and the app itself. One user or many? One session "
            "host or all? Profile size and host CPU/RAM first for freezes; "
            "check the licensing/connector services first for connection "
            "failures."
        ),
    },
    "password_mgmt": {
        "name": "Password Manager Agent",
        "topics": ["passwords"],
        "body": (
            "Act as a password manager rollout/admin specialist. Structure "
            "vaults/collections by team and least privilege, enforce SSO + "
            "MFA on the manager itself, plan break-glass access for admin "
            "departure, and define what NEVER goes in personal vaults. "
            "Migration needs a deprecation date for the old method "
            "(spreadsheets, browser-saved) and an audit that it's gone."
        ),
    },
    "procurement": {
        "name": "Licensing & Procurement Agent",
        "topics": ["licensing"],
        "body": (
            "Act as an IT procurement specialist. Before any renewal: pull "
            "actual usage vs entitlements, identify shelfware to cut, and "
            "model 3 scenarios (renew as-is, rightsized, alternative "
            "vendor). Know the list price, last year's price, and the "
            "walk-away position before talking to the rep. Get quotes in "
            "writing; co-term where it simplifies, never auto-renew "
            "blindly."
        ),
    },
    "file_transfer": {
        "name": "File Transfer Agent",
        "topics": ["file_transfer"],
        "body": (
            "Treat automated file transfers as production data pipelines: "
            "key-based auth (no passwords in scripts), verify transfer "
            "completeness (size/hash/row count) before deleting or "
            "processing, atomic moves (temp name then rename), idempotent "
            "re-runs, logging with timestamps, and alerting on missed "
            "windows — silence is the most common failure mode."
        ),
    },
    "facilities": {
        "name": "Facilities & Server Room Agent",
        "topics": ["facilities"],
        "body": (
            "Act as a facilities/physical-infrastructure specialist. "
            "Physical changes need: maintenance window, what loses power or "
            "access during the work, labeled before/after photos, and an "
            "updated rack/cable/access record. For UPS and battery work, "
            "verify actual load and runtime, not nameplate. Badge/door "
            "changes follow joiner-mover-leaver like any other access."
        ),
    },
    "chief_of_staff": {
        "name": "Chief of Staff Agent",
        "topics": ["exec_ops", "meeting_prep"],
        "body": (
            "Act as a chief of staff: protect the principal's time and "
            "attention. Everything produced is decision-ready — lead with "
            "the recommendation, give three bullets of why, put the detail "
            "in an appendix. Track every commitment made in meetings to an "
            "owner and a date, and surface what's stuck BEFORE the next "
            "meeting, not at it."
        ),
    },
    "exec_assistant": {
        "name": "Executive Assistant Agent",
        "topics": ["calendar", "travel", "meeting_prep"],
        "body": (
            "Act as a senior executive assistant: guard the calendar like a "
            "budget. Protect focus blocks and recovery time between "
            "back-to-backs, state time zones explicitly in every proposal, "
            "decline gracefully with an alternative, and attach the prep "
            "the meeting needs (agenda, pre-read, dial-in) when booking — "
            "a meeting without an agenda gets questioned, not scheduled."
        ),
    },
    "email_writer": {
        "name": "Email Writing Agent",
        "topics": ["email_drafting"],
        "body": (
            "Write emails people answer: subject line states the ask, "
            "first sentence is the point, one ask per email, and the "
            "deadline/next step in bold at the end. Match formality to the "
            "relationship, never bury a decision in paragraph three, and "
            "keep it under 150 words unless the content truly requires "
            "more."
        ),
    },
    "note_taker": {
        "name": "Note-Taking Agent",
        "topics": ["notes"],
        "body": (
            "Turn raw notes into a usable record: decisions made, actions "
            "with owner and date, open questions, and context worth "
            "keeping — in that order. Separate verbatim quotes from "
            "interpretation, flag anything ambiguous to confirm rather "
            "than guessing, and keep the original text untouched below "
            "the summary."
        ),
    },
    "presentation_designer": {
        "name": "Presentation Agent",
        "topics": ["presentation"],
        "body": (
            "Build slide content like a presentation designer: one idea "
            "per slide, headline states the takeaway (not the topic), "
            "supporting detail goes in speaker notes instead of on the "
            "slide. Open with the conclusion for executives, build to it "
            "for teaching. Always state the deck's single sentence: what "
            "the audience should think or do after."
        ),
    },
    "doc_designer": {
        "name": "Document Design Agent",
        "topics": ["word_docs"],
        "body": (
            "Build documents with structure, not manual formatting: real "
            "heading styles (so the table of contents works), consistent "
            "spacing via styles, page numbers and version/date in the "
            "footer. Front-load a summary for anything over two pages. "
            "For templates and mail merges, test with the messiest real "
            "record first, not the cleanest."
        ),
    },
    "notebooklm_guide": {
        "name": "NotebookLM Research Agent",
        "topics": ["notebooklm"],
        "body": (
            "Work source-grounded like NotebookLM: claims come only from "
            "the uploaded sources, every assertion cites which source it "
            "came from, and gaps in the sources get named as gaps instead "
            "of filled from memory. Suggest which additional source would "
            "close each gap. Distinguish what the sources SAY from what "
            "they merely imply."
        ),
    },
    "hr_partner": {
        "name": "HR Partner Agent",
        "topics": ["hr", "onboarding"],
        "body": (
            "Act as an HR partner: structured and bias-aware. Job "
            "descriptions list outcomes, not adjective soup; interview "
            "kits ask every candidate the same questions with scoring "
            "anchors; review feedback cites observed behavior and impact, "
            "never personality. Treat everything as confidential and "
            "assume any document could be read by the person it's about."
        ),
    },
    "sales_writer": {
        "name": "Sales Communication Agent",
        "topics": ["sales"],
        "body": (
            "Write sales communication that respects the buyer: lead with "
            "their problem in their words, quantify value, one clear next "
            "step. No invented urgency, no claims the product can't "
            "support — overpromising creates churn, not revenue. "
            "Proposals state price plainly and address the obvious "
            "objection before the buyer raises it."
        ),
    },
    "marketer": {
        "name": "Marketing Agent",
        "topics": ["marketing"],
        "body": (
            "Write marketing copy audience-first: name who it's for, what "
            "they get, and the one action to take — one CTA per piece. "
            "Match the channel's native format (LinkedIn isn't a press "
            "release), keep the brand voice consistent, and state how "
            "success will be measured so the copy can be judged against "
            "it later."
        ),
    },
    "support_agent": {
        "name": "Customer Support Agent",
        "topics": ["support"],
        "body": (
            "Write support replies in this order: acknowledge the "
            "specific problem (not a generic apology), state what you "
            "did or found, give the fix or the honest status with a real "
            "date, and end with one clear next step. Never blame the "
            "customer, never promise what isn't confirmed, and escalate "
            "with a summary the next person can act on without re-asking."
        ),
    },
    "finance_analyst": {
        "name": "Finance Ops Agent",
        "topics": ["finance_ops"],
        "body": (
            "Work like a finance analyst: numbers tie out to a named "
            "source, assumptions are stated next to every forecast, and "
            "variances come with the driver (price, volume, timing) not "
            "just the delta. Show period-over-period, round consistently, "
            "and flag anything estimated versus actual. A number without "
            "a source is a rumor."
        ),
    },
    "project_manager": {
        "name": "Project Manager Agent",
        "topics": ["project_mgmt"],
        "body": (
            "Run project work with explicit structure: every task has an "
            "owner and a date, every date has a dependency check, risks "
            "live in a RAID log with mitigation owners. Status reports "
            "lead with on-track/at-risk/blocked and what changed since "
            "last time. Scope changes get named as scope changes — "
            "absorbed quietly, they become schedule slips."
        ),
    },
    "event_planner": {
        "name": "Event Planning Agent",
        "topics": ["events"],
        "body": (
            "Plan events backwards from the date: a workback schedule "
            "with vendor deadlines (catering, venue, AV all have "
            "lead-times), a run-of-show with owners per segment and "
            "buffer between them, and a day-of contact list. Always have "
            "the contingency: weather, no-show speaker, broken AV. "
            "Confirm everything in writing the week before."
        ),
    },
    "game_designer": {
        "name": "Game Design Agent",
        "topics": ["game_design"],
        "body": (
            "Act as a game designer: start from the player experience (what "
            "should the player FEEL), define the core loop in one sentence "
            "before adding systems, and prototype the cheapest testable "
            "version of every mechanic. Fun is found in playtests, not "
            "design docs — every design comes with the playtest question "
            "that would validate or kill it. Scope is the enemy: cut "
            "features before polish."
        ),
    },
    "art_director": {
        "name": "Art Direction Agent",
        "topics": ["creative_art"],
        "body": (
            "Act as an art director: establish intent before execution — "
            "audience, mood, and the three reference works that define the "
            "target. Give feedback in craft terms (composition, value "
            "hierarchy, color temperature, silhouette) instead of 'make it "
            "pop'. For AI image prompts, specify subject, style, lighting, "
            "composition, and what to EXCLUDE — then iterate on one "
            "variable at a time."
        ),
    },
    "tutor": {
        "name": "Tutor Agent",
        "topics": ["academic", "learning"],
        "body": (
            "Act as a tutor, not an answer machine: work the problem "
            "step-by-step showing the reasoning, name the concept each step "
            "uses, then pose a similar practice problem to confirm "
            "understanding. For essays and reports, improve the student's "
            "own argument and voice rather than replacing them. Check "
            "answers independently (units, magnitude, edge cases) before "
            "presenting them as correct."
        ),
    },
    "equity_analyst": {
        "name": "Equity Research Agent",
        "topics": ["investing"],
        "body": (
            "Act as an equity research analyst producing information, not "
            "financial advice — say so, and recommend a licensed advisor "
            "for personal decisions. Ground claims in filings and reported "
            "numbers (10-K, earnings) with dates, since data may be stale. "
            "Always present the bear case next to the bull case, state "
            "valuation assumptions explicitly, and separate facts from the "
            "narrative around them."
        ),
    },
    "researcher": {
        "name": "Research Agent",
        "topics": ["research"],
        "body": (
            "Act as a research analyst: define the question precisely "
            "before searching, triangulate every important claim across "
            "independent sources, and cite which source supports what. "
            "Distinguish primary sources from commentary, note publication "
            "dates, name disagreements between sources instead of "
            "averaging them, and list what remains unknown. A finding "
            "without a source doesn't go in the report."
        ),
    },
    "legal_intake": {
        "name": "Legal Intake Agent",
        "topics": ["legal_ops"],
        "body": (
            "Prepare contract/legal work for counsel — never give legal "
            "advice. Summarize the document in plain language, flag the "
            "clauses that commonly bite (auto-renewal, liability caps, "
            "indemnification, termination, data handling), note what "
            "differs from the company's standard terms, and produce a "
            "clean question list for the lawyer. Spot issues; don't "
            "resolve them."
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
        "topics": ["bulk_data", "powershell"],
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
    "general_fixit": {
        "name": "General troubleshooting skill",
        "topics": ["fixit"],
        "body": "Diagnose before fixing: symptom, scope, recent changes, cheapest checks first.",
        "steps": [
            "Capture the exact symptom and error text; screenshot if possible.",
            "Establish scope: one user, a group, or everyone — and since when.",
            "List what changed recently: updates, policies, passwords, certs.",
            "Test likely causes cheapest-first, one variable at a time.",
            "Apply the fix, verify with the affected user, document in the ticket.",
        ],
    },
    "notion_system": {
        "name": "Notion system design skill",
        "topics": ["notion"],
        "body": "Build a Notion database/system that stays usable: model, views, templates, owner.",
        "steps": [
            "Define what each row represents and who updates it.",
            "Design properties first (status, owner, dates, relations) — not content.",
            "Create the views people actually need (by status, by owner, calendar).",
            "Add a template for new entries so structure survives real use.",
            "Assign an owner and a review date; archive what nobody updates.",
        ],
    },
    "meeting_summary": {
        "name": "Meeting recording to actions skill",
        "topics": ["zoom", "reporting"],
        "body": "Turn a Zoom/Teams recording or transcript into minutes, decisions, and owned actions.",
        "steps": [
            "Get the transcript; note attendees and the meeting's purpose.",
            "Pull out decisions made, separating them from discussion.",
            "List action items with owner and due date; flag unowned ones.",
            "Write a 5-line summary for non-attendees.",
            "Post to the agreed place (channel/page/ticket) and tag owners.",
        ],
    },
    "google_admin_change": {
        "name": "Google Workspace change skill",
        "topics": ["google"],
        "body": "Make a Workspace admin change safely: scope to OU/group, verify, document.",
        "steps": [
            "Confirm the change, the OU/group scope, and the approver.",
            "Note the current setting (your rollback) before touching anything.",
            "Apply via Admin console or GAM; prefer group/OU over per-user.",
            "Wait out propagation; verify with an affected test account.",
            "Record the change, scope, and rollback in the ticket.",
        ],
    },
    "slack_setup": {
        "name": "Slack channel/integration skill",
        "topics": ["slack"],
        "body": "Set up channels and integrations with governance: naming, purpose, permissions.",
        "steps": [
            "Confirm purpose and audience; check an existing channel doesn't cover it.",
            "Name per convention; set topic/description and channel owner.",
            "Review any app/integration permissions before installing.",
            "Set posting permissions and retention appropriate to the content.",
            "Announce where relevant and add to the channel directory/index.",
        ],
    },
    "github_repo": {
        "name": "GitHub repo setup skill",
        "topics": ["github"],
        "body": "Stand up a repo with protections: access, branch rules, CI, secrets hygiene.",
        "steps": [
            "Create the repo with a README stating purpose and owner.",
            "Set team-based access (least privilege; no individual collaborators).",
            "Protect the default branch: required reviews, status checks.",
            "Wire up CI and put credentials in Actions secrets, never code.",
            "Add CODEOWNERS and a PR template so reviews route correctly.",
        ],
    },
    "servicenow_flow": {
        "name": "ServiceNow ticket workflow skill",
        "topics": ["servicenow"],
        "body": "Work a SNOW record properly: right type, clean updates, honest states, linked CI.",
        "steps": [
            "Pick the right record type: incident, request, or change.",
            "Link the affected CI and fill the real assignment group.",
            "Keep work notes (internal) and customer comments (external) straight.",
            "Update state only when the work actually moves; no state-parking.",
            "Resolve with a cause and fix description a stranger could follow.",
        ],
    },
    "flow_build": {
        "name": "Automation flow build skill",
        "topics": ["automation"],
        "body": "Build a Power Automate/Zapier flow that survives production: errors, owners, kill switch.",
        "steps": [
            "Define trigger, inputs, and the exact end state in one sentence.",
            "Build with a service-account connection, not a personal one.",
            "Add error handling: retries, failure notifications, dead-letter step.",
            "Test the unhappy paths (empty input, throttling, permission denied).",
            "Document owner, purpose, and how to disable it; review quarterly.",
        ],
    },
    "text_rewrite": {
        "name": "Text rewrite/edit skill",
        "topics": ["writing"],
        "body": "Edit text without losing the author's voice: audience, tone, cut, verify meaning.",
        "steps": [
            "State the audience and the tone you're aiming for.",
            "Paste the original text in full — never a paraphrase of it.",
            "Ask for the edit plus a list of what changed and why.",
            "Check the edit kept your meaning; flag anything that drifted.",
            "Read it aloud once before sending — awkward spots will surface.",
        ],
    },
    "excel_formula": {
        "name": "Spreadsheet formula skill",
        "topics": ["excel"],
        "body": "Get a working formula: real layout in, explained formula out, sanity-checked.",
        "steps": [
            "Describe the sheet by actual columns (A: name, B: date, ...).",
            "Give 2-3 sample rows and the exact result you expect for them.",
            "State your version: Excel 365, older Excel, or Google Sheets.",
            "Ask for the formula plus a plain-English explanation of each part.",
            "Test on the sample rows first, then spot-check edge cases (blanks, duplicates).",
        ],
    },
    "account_lockout": {
        "name": "Account lockout/reset skill",
        "topics": ["helpdesk", "entra"],
        "body": "Handle resets and lockouts safely: verify, unlock, find the cause, document.",
        "steps": [
            "Verify the requester's identity per policy before touching anything.",
            "Check WHY it locked: bad password attempts, stale credentials on a device, sync issue.",
            "Unlock/reset with a one-time credential; force change at next sign-in.",
            "Confirm the user is in and MFA still works.",
            "Note the cause in the ticket; repeated lockouts deserve a root-cause look.",
        ],
    },
    "software_request": {
        "name": "Software/access request skill",
        "topics": ["helpdesk"],
        "body": "Fulfill requests cleanly: approval, license, standard install, verify, record.",
        "steps": [
            "Check the request has manager/owner approval if policy requires it.",
            "Confirm license availability or note the cost for procurement.",
            "Prefer the standard packaged install (Company Portal/Self Service) over manual.",
            "Verify the user can launch and sign in to the software.",
            "Record license assignment and close with what was provided.",
        ],
    },
    "explain_concept": {
        "name": "Explain-a-concept skill",
        "topics": ["learning"],
        "body": "Learn something properly: level-set, analogy, example, then test yourself.",
        "steps": [
            "State what you already know so the explanation starts at your level.",
            "Ask for a plain-English explanation with one analogy.",
            "Ask for a concrete example from your own context (IT/admin).",
            "Ask what people commonly get wrong about it.",
            "Explain it back in 2 sentences and ask the assistant to correct you.",
        ],
    },
    "doc_summarize": {
        "name": "Document summary skill",
        "topics": ["summarize"],
        "body": "Summaries people actually use: audience first, structure, decisions and actions pulled out.",
        "steps": [
            "Say who the summary is for and what they'll do with it.",
            "Set the length budget (e.g. 5 bullets, half a page).",
            "Ask for decisions, action items, and open questions as separate lists.",
            "Ask what the summary left out that the reader might still need.",
            "Spot-check 2-3 claims against the original before forwarding.",
        ],
    },
    "dial_in": {
        "name": "Dial-in-the-ask skill",
        "topics": ["refine"],
        "body": "Turn a vague idea into a sharp request: goal, context, constraints, done criteria.",
        "steps": [
            "Write the goal in one sentence a stranger would understand.",
            "List what the assistant needs to know (context, examples, current state).",
            "State constraints: tools, time, format, what must NOT change.",
            "Define what done looks like — measurable if possible.",
            "Ask the assistant to plan first and confirm before executing.",
        ],
    },
    "api_script": {
        "name": "API integration skill",
        "topics": ["api"],
        "body": "Integrate with an API safely: auth first, prove one call, then paging/limits/errors.",
        "steps": [
            "Read the docs for auth, rate limits, and paging before any code.",
            "Get credentials with least-privilege scopes; store them outside code.",
            "Prove ONE call works via curl/Postman and save the working example.",
            "Build the integration: paging, 429/Retry-After handling, timeouts, idempotent writes.",
            "Test failure paths (expired token, empty result, throttle) and log requests for debugging.",
        ],
    },
    "mcp_setup": {
        "name": "MCP server setup skill",
        "topics": ["mcp"],
        "body": "Connect tools to an AI client via MCP: pick, configure, verify, scope down.",
        "steps": [
            "Pick the MCP server (existing one before building your own).",
            "Create credentials scoped to only what the AI should touch.",
            "Add the server to the client config (e.g. claude_desktop_config.json) and restart the client.",
            "Verify the tools appear and run one harmless read-only call.",
            "Review what the AI can now do; remove scopes you don't need and document the setup.",
        ],
    },
    "ollama_chatbot": {
        "name": "Local AI chatbot skill",
        "topics": ["local_llm"],
        "body": "Stand up a private chatbot with Ollama: hardware check, model pull, system prompt, test.",
        "steps": [
            "Check hardware: 8GB RAM runs small models (3–4B params); a GPU with 8GB+ VRAM runs mid-size well.",
            "Install Ollama, then pull a small model that fits — browse ollama.com/library (e.g. `ollama pull gemma3`).",
            "Test in terminal with `ollama run` and your 5 most typical questions.",
            "Write a system prompt: role, tone, what it must refuse, knowledge limits — small models need explicit guidance.",
            "Add a front end (Open WebUI or a simple script via the localhost API) and re-test the same questions.",
        ],
    },
    "rmm_deploy": {
        "name": "RMM script deployment skill",
        "topics": ["rmm", "powershell"],
        "body": "Deploy a script via NinjaOne/ConnectWise: SYSTEM context, exit codes, pilot ring.",
        "steps": [
            "Write the script for the run context (usually SYSTEM — no user profile, no mapped drives).",
            "Return meaningful exit codes and output the RMM can capture.",
            "Test on one device manually, then a pilot device group.",
            "Review pilot results in the RMM before widening scope.",
            "Roll out by group, monitor failures, document in the runbook.",
        ],
    },
    "siem_query": {
        "name": "SIEM search/alert skill",
        "topics": ["siem"],
        "body": "Build a Sumo Logic search or alert that's trusted: scope, validate, schedule, runbook.",
        "steps": [
            "Write the question first: what event, which systems, what time range.",
            "Anchor to the right source category; confirm logs are actually arriving.",
            "Build incrementally: filter, then parse fields, then aggregate.",
            "Validate against a known event (a login you just did, a test alert).",
            "If scheduling as an alert: set a threshold that means action, link a runbook, review noise in 2 weeks.",
        ],
    },
    "edr_triage": {
        "name": "EDR alert triage skill",
        "topics": ["edr"],
        "body": "Work a SentinelOne/EDR alert: triage, contain, evidence, remediate, tune carefully.",
        "steps": [
            "Read the full detection: process tree, file path, user, machine role.",
            "Decide fast: likely true positive -> isolate the endpoint now, investigate after.",
            "Capture evidence (hashes, timeline, affected files) before remediation erases it.",
            "Remediate: kill/quarantine/rollback, then verify the endpoint is clean.",
            "Classify the alert honestly; only add exclusions with written justification and an owner.",
        ],
    },
    "browser_policy": {
        "name": "Browser policy/troubleshooting skill",
        "topics": ["browser"],
        "body": "Manage or fix browsers properly: policy over tweaks, isolate variables when debugging.",
        "steps": [
            "For management: define the setting, find its policy (ADMX/Intune profile), don't hand-edit devices.",
            "Pilot the policy on a test group; verify via the browser's policy page (chrome://policy, edge://policy).",
            "For troubleshooting: reproduce in a fresh profile first — that splits profile vs install issues.",
            "Disable extensions, retest; re-enable one at a time to find the culprit.",
            "Clear cache/cookies only after the above — it's the last variable, not the first.",
        ],
    },
    "azure_deploy": {
        "name": "Azure resource deployment skill",
        "topics": ["azure", "iac"],
        "body": "Stand up Azure resources properly: RG + tags, IaC or CLI, RBAC, cost, teardown path.",
        "steps": [
            "Create/choose the resource group; tag owner, purpose, environment.",
            "Deploy via IaC or az CLI (saved script) — portal clicks aren't repeatable.",
            "Scope RBAC to the narrowest level; secrets go to Key Vault.",
            "Verify the resource works AND check its projected monthly cost.",
            "Record the teardown command — every resource needs an exit plan.",
        ],
    },
    "exchange_task": {
        "name": "Exchange Online admin skill",
        "topics": ["exchange_admin"],
        "body": "Mailbox/DL/transport changes done right: current state, least access, verify, trace.",
        "steps": [
            "Capture the current state (permissions/members/rules) as your rollback.",
            "Apply the change with the narrowest grant that solves the ask.",
            "Mind propagation — Exchange permission changes can take up to an hour.",
            "Verify as the affected user (or with a message trace for mail flow).",
            "Record what was granted/changed and any expiry in the ticket.",
        ],
    },
    "defender_review": {
        "name": "Defender/Purview policy skill",
        "topics": ["m365_security"],
        "body": "Roll out a security/compliance policy without breaking work: simulate, review, enforce.",
        "steps": [
            "Confirm the license tier actually includes the feature.",
            "Build the policy scoped to a pilot group, in simulation/audit mode.",
            "Review what it WOULD have flagged/blocked for false positives.",
            "Enforce for the pilot, then expand in rings; watch user reports.",
            "Document policy intent and exceptions; set a review date.",
        ],
    },
    "python_script": {
        "name": "Python script skill",
        "topics": ["python"],
        "body": "Write a Python automation that survives reuse: venv, args, errors, dry-run, README.",
        "steps": [
            "Define inputs/outputs; take parameters via argparse, not edits to the code.",
            "Create a venv and pin requirements (or stay stdlib-only).",
            "Handle the failure paths: missing file, bad data, no network.",
            "Add --dry-run for anything destructive; print what WOULD happen.",
            "Test with real-shaped data and leave a 5-line usage note at the top.",
        ],
    },
    "windows_fix": {
        "name": "Windows troubleshooting skill",
        "topics": ["windows", "fixit"],
        "body": "Fix Windows issues with evidence: Event Viewer, recent changes, isolate, then act.",
        "steps": [
            "Get the exact error and when it started; check Event Viewer at that timestamp.",
            "Check what changed: Windows updates, driver updates, new software, policy.",
            "Isolate: another user account on the same machine splits profile vs system.",
            "Apply the targeted fix; avoid reinstall-everything until causes are exhausted.",
            "Confirm with the user after a reboot and a real work task; note the fix.",
        ],
    },
    "mac_fix": {
        "name": "Mac troubleshooting skill",
        "topics": ["mac", "fixit"],
        "body": "Fix macOS issues without folklore: logs, test account, safe mode, managed-device awareness.",
        "steps": [
            "Capture the symptom and check Console/diagnostic logs around it.",
            "Check MDM (Jamf/Intune) state — a profile may be causing or blocking the fix.",
            "Test in a fresh user account: works there = profile issue, not system.",
            "Try safe mode for cache/extension issues; keychain reset only for sign-in loops.",
            "Verify with the user, then note macOS version and fix in the ticket.",
        ],
    },
    "mobile_support": {
        "name": "Mobile device support skill",
        "topics": ["mobile"],
        "body": "Support iOS/Android under MDM: enrollment state, sync, targeted fixes, reset last.",
        "steps": [
            "Check enrollment/compliance state in MDM before touching the device.",
            "Confirm the basics: OS version supported, storage not full, network OK.",
            "Force an MDM check-in/sync; many 'missing app/profile' issues end here.",
            "Re-push the specific app/profile; verify it lands on the device.",
            "Wipe/retire only with data-loss warnings given and backup confirmed.",
        ],
    },
    "printer_fix": {
        "name": "Printer troubleshooting skill",
        "topics": ["printer", "fixit"],
        "body": "Fix printing by scope: one user vs everyone points to different layers.",
        "steps": [
            "Scope it: one user, one printer, or everyone — note which.",
            "Check the queue/spooler first; clear stuck jobs before deeper work.",
            "Print a test page from the server/host directly — splits network vs client.",
            "Reinstall/swap the driver only after queue and connectivity are clean.",
            "Document the working driver, port, and any quirks for the next person.",
        ],
    },
    "app_mvp": {
        "name": "App MVP build skill",
        "topics": ["appdev"],
        "body": "Ship a first working version: one user, one problem, one screen, real data, iterate.",
        "steps": [
            "Write one sentence: who uses this and what problem it solves.",
            "Cut scope to the smallest version that's actually usable (one core flow).",
            "Pick boring tech the team can maintain; scaffold and get it running day one.",
            "Build the core flow with real-shaped data; skip auth/polish until it works.",
            "Put it in front of a real user; let their friction set the next iteration.",
        ],
    },
    "linux_service": {
        "name": "Linux service troubleshooting skill",
        "topics": ["linux", "fixit"],
        "body": "Fix a failing service with evidence: status, journal, config test, restart, enable.",
        "steps": [
            "systemctl status <unit> — read the actual state and last error.",
            "journalctl -u <unit> --since '1 hour ago' for the real failure.",
            "Validate config before restarting (nginx -t, sshd -t, etc.).",
            "Restart and watch the journal live; confirm it stays up.",
            "Ensure it's enabled for boot; note root cause in the ticket.",
        ],
    },
    "bash_script": {
        "name": "Bash script skill",
        "topics": ["linux"],
        "body": "Write bash that fails loudly and safely: strict mode, quoting, dry-run, shellcheck.",
        "steps": [
            "Start with set -euo pipefail; quote every variable expansion.",
            "Take inputs as arguments with a usage message, not edits.",
            "Add a dry-run mode that echoes destructive commands instead of running them.",
            "Run shellcheck and fix every warning.",
            "Test on one target first; log what was changed where.",
        ],
    },
    "gpo_troubleshoot": {
        "name": "GPO troubleshooting skill",
        "topics": ["ad", "windows"],
        "body": "Find why a policy does/doesn't apply: gpresult evidence over guesswork.",
        "steps": [
            "Run gpresult /h on the affected machine as the affected user.",
            "Check the GPO is linked to the right OU and security filtering includes the target.",
            "Look for Denied entries: WMI filters, inheritance blocks, enforcement conflicts.",
            "Fix the scoping issue; gpupdate /force and re-run gpresult to confirm.",
            "Document which GPO wins and why for the next person.",
        ],
    },
    "ad_hygiene": {
        "name": "AD cleanup skill",
        "topics": ["ad", "audit"],
        "body": "Clean stale AD objects safely: report, disable first, delete later, evidence throughout.",
        "steps": [
            "Export accounts/computers with lastLogonTimestamp beyond the threshold.",
            "Review with owners — service accounts hide in stale lists.",
            "Disable (don't delete) in a dated OU; note the date in the description.",
            "Wait the agreed soak period for breakage reports.",
            "Delete past-soak objects; keep the exports as audit evidence.",
        ],
    },
    "vm_change": {
        "name": "VM change with snapshot skill",
        "topics": ["virtualization", "change"],
        "body": "Make VM changes reversibly: snapshot, change, verify, then DELETE the snapshot.",
        "steps": [
            "Confirm backup state, then snapshot with a dated description.",
            "Make the change; verify the app/service, not just the OS booting.",
            "If broken: revert, reassess — don't stack fixes on failures.",
            "If good: delete the snapshot within days, not weeks (they grow and slow I/O).",
            "Record the change and snapshot lifecycle in the ticket.",
        ],
    },
    "share_permissions": {
        "name": "File share permissions skill",
        "topics": ["storage", "audit"],
        "body": "Grant share access the auditable way: groups, AGDLP, exports before and after.",
        "steps": [
            "Export current NTFS and share ACLs (your rollback and evidence).",
            "Create/identify the access group; add users to the group, never to the folder.",
            "Set NTFS permission for the group at the highest folder that needs it.",
            "Check inheritance below — broken inheritance is where audits fail.",
            "Verify as an affected user; export the after-state to the ticket.",
        ],
    },
    "db_safe_change": {
        "name": "Database safe-change skill",
        "topics": ["database"],
        "body": "Change data without disasters: backup, SELECT first, transaction, rowcount, commit.",
        "steps": [
            "Confirm a restorable backup exists before anything else.",
            "SELECT with the exact WHERE clause first; review what you'll touch.",
            "Run the UPDATE/DELETE inside a transaction.",
            "Check the rowcount matches the SELECT before COMMIT; rollback if not.",
            "Record the statement, rowcount, and ticket reference.",
        ],
    },
    "data_migration": {
        "name": "Data migration skill",
        "topics": ["migration"],
        "body": "Migrate in waves with validation: inventory, pilot, validate, cutover, retire later.",
        "steps": [
            "Inventory the source: item counts, sizes, owners, permissions, weird cases.",
            "Map source to destination including how permissions translate.",
            "Migrate a pilot wave; validate counts, spot-check content, test access as real users.",
            "Migrate remaining waves with progress comms; freeze source changes near cutover.",
            "Keep the source read-only until validation passes; retire on schedule, not impulse.",
        ],
    },
    "regex_build": {
        "name": "Regex building skill",
        "topics": ["regex"],
        "body": "Build a regex that's testable: examples first, incremental pattern, edge cases, comments.",
        "steps": [
            "Collect 5+ strings that should match and 3+ that should not.",
            "Ask for the pattern built incrementally with each piece explained.",
            "Test against your examples; tighten until non-matches stay out.",
            "Probe edge cases: empty, unicode, very long input, almost-matches.",
            "Save it with a comment showing sample matches — future-you forgets.",
        ],
    },
    "mermaid_diagram": {
        "name": "Diagram-as-code skill",
        "topics": ["diagram", "confluence"],
        "body": "Produce a Mermaid diagram that stays current: list, generate, refine, commit the source.",
        "steps": [
            "List components and connections in plain text first (the AI's input).",
            "State the audience and the one question the diagram answers.",
            "Generate Mermaid; render and check it's readable at a glance.",
            "Cut boxes that don't serve the question; label data flows.",
            "Commit the Mermaid source next to the docs so updates are edits, not redraws.",
        ],
    },
    "asset_audit": {
        "name": "Asset inventory audit skill",
        "topics": ["asset", "reporting"],
        "body": "Reconcile asset records against reality: exports, diff, chase, correct, prevent.",
        "steps": [
            "Export the asset register and the live data (RMM/Intune/MDM).",
            "Diff: in-register-not-seen (missing) and seen-not-in-register (shadow).",
            "Chase missing assets via last user/location; flag for write-off past threshold.",
            "Correct the register; record root causes (skipped intake, offboarding gaps).",
            "Fix the leak: tie asset updates into on/offboarding steps.",
        ],
    },
    "chat_handoff": {
        "name": "Chat handoff skill",
        "topics": ["handoff"],
        "body": "Move work to a fresh chat without losing context: summarize, verify, seed, confirm.",
        "steps": [
            "Ask the CURRENT chat for a handoff block: objective, current state, decisions made, in-flight work, next steps, gotchas — one code block.",
            "Read it before trusting it: fix anything the assistant got wrong or omitted (it summarizes optimistically).",
            "Add exact identifiers the new chat can't guess: file paths, versions, ticket numbers, URLs.",
            "Paste it as the first message of the new chat and ask the assistant to confirm its understanding and the next step before doing anything.",
            "Spot-check the new chat's first answer against a fact from the old one — catch drift early.",
        ],
    },
    "deckside_feature": {
        "name": "DeckSide feature build skill",
        "topics": ["deckside", "appdev"],
        "body": "Ship a DeckSide feature inside its architecture: AGENTS.md, IPC boundary, fixtures, back-compat.",
        "steps": [
            "Orient: read AGENTS.md and the relevant BACKLOG.md entry; check which existing module this extends.",
            "Plan the data flow: schema change (SQLite), service/IPC surface, then renderer — never renderer-to-DB.",
            "Keep coach vs parent dashboard isolation; state which side this touches.",
            "Test against real fixture files (HY-TEK/SwimTopia PDFs); confirm old imports still parse.",
            "Update CHANGELOG.md and verify the installer/upgrade path preserves user data.",
        ],
    },
    "deckside_capability": {
        "name": "DeckSide assistant capability skill",
        "topics": ["deckside"],
        "body": "Add an assistant capability: intent schema, deterministic-first, preview, approval gate, validation.",
        "steps": [
            "Define the intent: name, parameters, and 5+ example utterances (including messy ones).",
            "Write the deterministic handler first; the LLM only maps utterance to intent.",
            "Write the preview text a coach sees before anything happens — exact, no ambiguity.",
            "Gate on human approval, then API validation; the capability calls DeckSide APIs, never the DB.",
            "Test the refusal paths: low confidence, missing meet context, out-of-scope asks.",
        ],
    },
    "deckside_parser": {
        "name": "DeckSide PDF parser change skill",
        "topics": ["deckside"],
        "body": "Change meet-file parsing without breaking history: fixtures first, golden tests, validate counts.",
        "steps": [
            "Collect fixture PDFs for the new format AND every format that works today.",
            "Capture current parse output for existing fixtures as golden baselines before touching code.",
            "Make the parser change; new formats must not alter old fixtures' output.",
            "Validate against a known meet: event/heat/swimmer counts match the paper program.",
            "Add the new fixtures to the test set so the next change can't regress this one.",
        ],
    },
    "assistant_prompt_tune": {
        "name": "In-app assistant prompt tuning skill",
        "topics": ["deckside", "local_llm"],
        "body": "Tune a small local model's prompts: capability docs, few-shot examples, refusals, eval set.",
        "steps": [
            "List every capability with a one-line description — this is the model's entire toolbox.",
            "Write 3-5 few-shot examples per capability: utterance → intent JSON (small models follow examples over rules).",
            "Define refusal behavior: low confidence, ambiguous swimmer/meet, out-of-scope — refuse to a clarifying question, never guess.",
            "Build an eval set of 20+ real utterances (including typos) with expected intents.",
            "Run the eval after every prompt change; track exact-match rate, not vibes.",
        ],
    },
    "status_report": {
        "name": "Status report skill",
        "topics": ["reporting"],
        "body": "Write a status report people read: outcomes, numbers, blockers with asks.",
        "steps": [
            "Lead with outcomes shipped, not activities performed.",
            "Quantify where possible (tickets closed, uptime, spend vs budget).",
            "List blockers WITH the specific ask that unblocks each.",
            "Preview next period in 3 bullets max.",
            "Keep it under one screen; link detail instead of including it.",
        ],
    },
    "voip_call_flow": {
        "name": "Call flow change skill",
        "topics": ["voip"],
        "body": "Change auto attendants/call queues without dropping live calls.",
        "steps": [
            "Diagram the current flow: numbers, attendants, queues, agents, hours, voicemail targets.",
            "Write the target flow and walk it as a caller: every option, every timeout, after-hours.",
            "Make the change in a test attendant/number first if one exists.",
            "Apply during low call volume; licensing and resource accounts checked beforehand.",
            "Verify with real calls from an outside line: business hours path, after-hours path, and the voicemail drop.",
        ],
    },
    "email_auth_fix": {
        "name": "Email deliverability skill",
        "topics": ["email_auth"],
        "body": "Fix SPF/DKIM/DMARC so legitimate mail lands and spoofing fails.",
        "steps": [
            "Inventory every legitimate sending source (app servers, marketing tools, printers, helpdesk).",
            "Check SPF covers them all in under 10 DNS lookups; flatten includes if over.",
            "Enable DKIM signing per source; verify with real message headers.",
            "Set DMARC to p=none with rua reporting; watch reports for 2-4 weeks.",
            "Tighten to quarantine then reject only after rua shows no legitimate failures.",
        ],
    },
    "firewall_change": {
        "name": "Firewall change skill",
        "topics": ["firewall", "network"],
        "body": "Add/change firewall rules with evidence and a rollback path.",
        "steps": [
            "Define the exact flow: source, destination, port/protocol, direction, and why.",
            "Export/backup the current config before touching anything.",
            "Place the rule deliberately in the order; check nothing above shadows it.",
            "Test the intended traffic passes AND a previously-blocked control still blocks.",
            "Log the change (ticket, rule ID, date) and set a review date for temporary rules.",
        ],
    },
    "aws_change": {
        "name": "AWS change skill",
        "topics": ["aws"],
        "body": "Make AWS changes that are tagged, least-privilege, and reversible.",
        "steps": [
            "State region, account, and naming/tagging before creating anything.",
            "Write the IAM policy scoped to the specific resources — no wildcards.",
            "Estimate monthly cost; note the cheaper alternative considered.",
            "Apply via CLI/IaC so the change is repeatable; save the commands.",
            "Verify the resource works, then document teardown steps.",
        ],
    },
    "vdi_troubleshoot": {
        "name": "VDI session triage skill",
        "topics": ["vdi"],
        "body": "Isolate virtual desktop issues by layer instead of guessing.",
        "steps": [
            "Scope: one user, one session host, one site, or everyone? Since when?",
            "Endpoint/network layer: client version, link quality, gateway reachable.",
            "Session host layer: CPU/RAM/disk on the host, concurrent session count.",
            "Profile layer: FSLogix/profile container size, load time, lock errors.",
            "Fix at the failing layer, then confirm with the affected user's real workflow.",
        ],
    },
    "pw_manager_rollout": {
        "name": "Password manager rollout skill",
        "topics": ["passwords"],
        "body": "Roll out a password manager people actually adopt.",
        "steps": [
            "Structure: vaults/collections by team, least privilege, named owners.",
            "Secure the manager itself: SSO, MFA enforced, break-glass admin access documented.",
            "Pilot with one friendly team; collect what confused them.",
            "Migrate: import from browsers/spreadsheets, then set a kill date for the old method.",
            "Audit 30 days in: adoption rate, orphaned vaults, anything still in the old place.",
        ],
    },
    "disk_space_cleanup": {
        "name": "Disk space recovery skill",
        "topics": ["storage"],
        "body": "Recover disk space safely and stop the regrowth.",
        "steps": [
            "Measure first: what is actually consuming space (largest folders, growth rate).",
            "Classify before deleting: logs, temp, snapshots, duplicates, orphaned user data.",
            "Delete only what has an owner decision or a written retention rule behind it.",
            "Verify the space came back and services still run.",
            "Fix the cause: rotation, quota, lifecycle rule, or alert at 80% — not just the symptom.",
        ],
    },
    "sftp_automation": {
        "name": "File transfer automation skill",
        "topics": ["file_transfer", "powershell"],
        "body": "Automate recurring file transfers that fail loudly, not silently.",
        "steps": [
            "Key-based auth with a service account; no credentials in the script.",
            "Transfer to a temp name, verify completeness (size/hash/count), then rename atomically.",
            "Make re-runs idempotent: already-transferred files are skipped, not duplicated.",
            "Log every run with timestamps and outcomes to a file someone can read.",
            "Alert on the MISSED window (no file by HH:MM), not just on errors.",
        ],
    },
    "license_renewal_prep": {
        "name": "License renewal prep skill",
        "topics": ["licensing"],
        "body": "Walk into a renewal with numbers instead of hope.",
        "steps": [
            "Pull entitlements vs actual usage; list shelfware and over-licensed tiers.",
            "Model 3 scenarios: renew as-is, rightsized, and best alternative vendor.",
            "Collect last year's pricing and any public/benchmark list pricing.",
            "Set the walk-away position and who can approve it before the first call.",
            "Get the final quote in writing with co-termination and true-down terms stated.",
        ],
    },
    "physical_change": {
        "name": "Physical infrastructure change skill",
        "topics": ["facilities"],
        "body": "Do server room / physical access work without surprises.",
        "steps": [
            "Schedule a window and state what loses power, network, or access during the work.",
            "Photograph and label before touching: ports, cables, rack positions.",
            "Make the change; one component at a time when anything is live.",
            "Verify dependent systems came back (ping list, badge test, UPS self-test).",
            "Update the rack/cable/access records and store the after photos with the ticket.",
        ],
    },
    "dsar_response": {
        "name": "Privacy request (DSAR) skill",
        "topics": ["privacy_compliance", "audit"],
        "body": "Respond to a data subject request completely, on time, with evidence.",
        "steps": [
            "Log the request date — the statutory clock (e.g. 30 days GDPR) starts now.",
            "Verify the requester's identity before disclosing anything.",
            "Search every system holding personal data (mail, files, HR, CRM, backups policy).",
            "Have legal/privacy review the export for third-party data before release.",
            "Deliver securely, record what was provided and when, and note exemptions applied.",
        ],
    },
    "calendar_triage": {
        "name": "Calendar triage skill",
        "topics": ["calendar"],
        "body": "Get a calendar under control and keep it that way.",
        "steps": [
            "Audit the next two weeks: flag meetings with no agenda, no decision, or pure FYI status.",
            "Decline or shorten the flagged ones with a polite template and an async alternative.",
            "Block focus time and buffer between back-to-backs before the calendar refills.",
            "Standardize: default 25/50-minute meetings, agendas required in the invite.",
            "Weekly review: what got booked over the blocks, and who keeps doing it.",
        ],
    },
    "meeting_prep_brief": {
        "name": "Meeting prep brief skill",
        "topics": ["meeting_prep", "exec_ops"],
        "body": "Produce a one-page brief so the meeting starts informed.",
        "steps": [
            "State the meeting's purpose and the ONE decision or outcome wanted.",
            "List attendees with what each cares about or will push back on.",
            "Summarize history in 3-5 bullets: what was agreed before, what changed since.",
            "Attach talking points and the questions likely to be asked, with answers.",
            "End with the recommended position and the fallback.",
        ],
    },
    "email_draft": {
        "name": "Email drafting skill",
        "topics": ["email_drafting"],
        "body": "Draft an email that gets answered, not archived.",
        "steps": [
            "Subject line states the ask or decision, not the topic.",
            "First sentence: the point. Background only after, only if needed.",
            "One ask per email with an explicit deadline or next step.",
            "Match tone to the relationship; read it as the recipient before sending.",
            "If it needs more than 150 words, consider whether it should be a call or doc.",
        ],
    },
    "inbox_triage": {
        "name": "Inbox triage skill",
        "topics": ["email_drafting", "calendar"],
        "body": "Clear an overflowing inbox with the four Ds and keep it cleared.",
        "steps": [
            "Sort by sender/thread, not date — kill whole conversations at once.",
            "Each message gets one decision: do (under 2 min), delegate, defer (scheduled), delete.",
            "Deferred items become calendar blocks or tasks, never re-marked unread.",
            "Unsubscribe/filter every recurring sender that didn't earn the inbox.",
            "Daily 2x 20-minute triage blocks; inbox is a triage queue, not a todo list.",
        ],
    },
    "meeting_minutes": {
        "name": "Meeting minutes skill",
        "topics": ["notes"],
        "body": "Turn a messy transcript or raw notes into minutes people use.",
        "steps": [
            "Decisions first: what was agreed, verbatim where wording matters.",
            "Actions with owner and due date; no owner means it didn't happen.",
            "Open questions and disagreements, neutrally stated.",
            "Context worth keeping in 5 bullets max; link the full transcript.",
            "Send within 24 hours and ask owners to confirm their items.",
        ],
    },
    "note_system": {
        "name": "Note organization skill",
        "topics": ["notes", "notion"],
        "body": "Organize scattered notes into a system you'll actually maintain.",
        "steps": [
            "Inventory where notes live today (apps, paper, screenshots, chats).",
            "Pick ONE home per type: meeting notes, ideas, reference, tasks.",
            "Structure by actionability (PARA-style: projects, areas, resources, archive), not by topic taxonomy.",
            "Set a capture habit: everything lands in one inbox note, sorted weekly.",
            "Archive ruthlessly — a note system fails from clutter, not from missing features.",
        ],
    },
    "slide_outline": {
        "name": "Slide deck outline skill",
        "topics": ["presentation"],
        "body": "Outline a deck where every slide earns its place.",
        "steps": [
            "Write the one sentence the audience should believe or do afterwards.",
            "Draft headlines first — each states a takeaway; read in order they tell the story alone.",
            "Add only evidence per slide: one chart, one comparison, or three bullets max.",
            "Move detail to speaker notes or appendix; expect the deck to be read without you.",
            "Time-check: 1-2 minutes per slide; cut until it fits the slot.",
        ],
    },
    "doc_polish": {
        "name": "Document formatting skill",
        "topics": ["word_docs"],
        "body": "Make a document look professional using structure, not hand-formatting.",
        "steps": [
            "Apply real heading styles; fix the hierarchy before touching appearance.",
            "Generate the table of contents from styles; never type one manually.",
            "Normalize: one body font, consistent spacing via styles, page numbers + version in footer.",
            "Add an executive summary up front if it's over two pages.",
            "Final pass in print preview and on a phone screen.",
        ],
    },
    "mail_merge": {
        "name": "Mail merge skill",
        "topics": ["word_docs", "bulk_data"],
        "body": "Run a mail merge that doesn't embarrass anyone.",
        "steps": [
            "Clean the source list first: names cased properly, no blanks in merged fields, dedupe.",
            "Build the template with merge fields and a fallback for missing data.",
            "Preview the messiest records, not the first three.",
            "Send/print a 3-record test batch; check greetings, dates, and currency formats.",
            "Run the rest, and save the final list as evidence of who got what.",
        ],
    },
    "notebooklm_research": {
        "name": "NotebookLM research skill",
        "topics": ["notebooklm"],
        "body": "Get grounded answers from your own sources instead of model memory.",
        "steps": [
            "Gather the actual sources (PDFs, docs, transcripts) — quality in, quality out.",
            "Upload and ask for a source-by-source summary first to verify it read them right.",
            "Ask questions that require citations; reject answers that don't point to a source.",
            "Note what the sources DON'T cover; add sources or mark as open questions.",
            "Export the grounded summary with citations for the deliverable.",
        ],
    },
    "job_description": {
        "name": "Job description skill",
        "topics": ["hr"],
        "body": "Write a job description that attracts the right people and screens itself.",
        "steps": [
            "Define outcomes for the first 90 days and year one — not a duties laundry list.",
            "Separate must-haves (3-5 max) from nice-to-haves; every extra must-have costs candidates.",
            "Write the day-to-day honestly, including the unglamorous parts.",
            "State salary range, location/remote policy, and process timeline.",
            "Strip biased language (rockstar, ninja, aggressive); read it as each target candidate.",
        ],
    },
    "interview_kit": {
        "name": "Interview kit skill",
        "topics": ["hr"],
        "body": "Build a structured interview so every candidate gets the same fair shot.",
        "steps": [
            "Derive 4-6 competencies from the job's actual outcomes.",
            "Write behavioral questions per competency (tell me about a time...) with follow-up probes.",
            "Define scoring anchors: what a 1, 3, and 5 answer sounds like.",
            "Assign competencies to interviewers so nothing is asked twice or missed.",
            "Debrief with written scores before any group discussion to avoid anchoring.",
        ],
    },
    "perf_review_draft": {
        "name": "Performance review skill",
        "topics": ["hr"],
        "body": "Draft review feedback that is specific, fair, and useful.",
        "steps": [
            "Collect evidence first: outcomes, examples, dates — across the whole period, not last month.",
            "Structure per theme: observed behavior, impact, expectation going forward.",
            "Balance honestly; no surprise negatives that were never raised in 1:1s.",
            "Strip personality adjectives; describe what they DID.",
            "Read it aloud as the recipient; rewrite anything you'd be defensive about.",
        ],
    },
    "sales_proposal": {
        "name": "Sales proposal skill",
        "topics": ["sales"],
        "body": "Write a proposal that answers the buyer's real questions.",
        "steps": [
            "Open with their problem in their words (from the discovery call, not your pitch).",
            "Present the solution as outcomes with numbers, not feature lists.",
            "Price plainly with options; address the obvious objection preemptively.",
            "Include timeline, what you need from them, and social proof that matches their situation.",
            "One-page executive summary up front; the decision-maker may read nothing else.",
        ],
    },
    "followup_email": {
        "name": "Follow-up email skill",
        "topics": ["sales", "email_drafting"],
        "body": "Follow up without being ignored or annoying.",
        "steps": [
            "Reference the specific last interaction and any commitment made.",
            "Add value in every touch: an answer, a resource, a relevant change — never just checking in.",
            "One clear, small ask with an easy yes (15 minutes, a name, a date).",
            "Space the cadence: 3 days, then a week, then two; change angle each time.",
            "After 3-4 touches, send the polite breakup email — it gets the most replies.",
        ],
    },
    "crm_hygiene": {
        "name": "CRM hygiene skill",
        "topics": ["sales", "bulk_data"],
        "body": "Clean the CRM so the pipeline numbers mean something.",
        "steps": [
            "Define stage criteria in writing: what must be TRUE for a deal to sit in each stage.",
            "Sweep stale deals: anything untouched 30+ days gets updated, downgraded, or closed-lost.",
            "Dedupe accounts/contacts; merge with the newest-complete record winning.",
            "Make next-step and close-date mandatory on every open deal.",
            "Weekly 15-minute hygiene block; the forecast is only as good as the worst record.",
        ],
    },
    "social_calendar": {
        "name": "Social content calendar skill",
        "topics": ["marketing"],
        "body": "Plan a month of social content in one sitting.",
        "steps": [
            "Pick 3-4 recurring content pillars tied to what the audience actually needs.",
            "Batch-draft per pillar; adapt per channel's native format rather than cross-posting.",
            "Calendar with dates, owner, asset needed, and CTA per post.",
            "Front-load approval for anything sensitive (pricing, claims, customers named).",
            "Review engagement monthly; double down on the pillar that works, drop the one that doesn't.",
        ],
    },
    "newsletter_issue": {
        "name": "Newsletter issue skill",
        "topics": ["marketing", "email_drafting"],
        "body": "Ship a newsletter issue people actually open and read.",
        "steps": [
            "Subject line promises the specific value inside; preview text extends it, not repeats it.",
            "Lead with the single best item; don't make readers scroll to the good part.",
            "Keep one voice and one CTA; every extra link halves clicks on the main one.",
            "Test render on mobile and dark mode before sending.",
            "Send a small segment first if the list is large; check opens/clicks/unsubscribes before full send.",
        ],
    },
    "support_reply": {
        "name": "Support reply skill",
        "topics": ["support"],
        "body": "Answer an upset customer in a way that keeps them.",
        "steps": [
            "Acknowledge their specific problem in the first sentence — prove a human read it.",
            "State plainly what happened and what you did, without blame or jargon.",
            "Give the fix, or the honest status with a real date you can keep.",
            "Offer the appropriate make-good if warranted; one clear next step either way.",
            "Log the root cause so the same reply isn't needed next week.",
        ],
    },
    "kb_article": {
        "name": "Help-center article skill",
        "topics": ["support", "confluence"],
        "body": "Write a help article that deflects tickets instead of creating them.",
        "steps": [
            "Title = the question users actually type, in their words.",
            "Steps numbered, one action each, with a screenshot where users get lost.",
            "State upfront who/what it applies to (plan, version, role) so wrong readers exit early.",
            "Include the 2-3 most common failure points as a troubleshooting section.",
            "Test on someone who hasn't done it; date it and set a review reminder.",
        ],
    },
    "budget_variance": {
        "name": "Budget variance skill",
        "topics": ["finance_ops"],
        "body": "Explain budget vs actuals so the conversation is about decisions, not arithmetic.",
        "steps": [
            "Tie out totals to the source system first; reconcile before analyzing.",
            "Compute variance per line: amount, percent, and favorable/unfavorable.",
            "Attribute each material variance to a driver: price, volume, timing, or one-off.",
            "Separate timing differences (will reverse) from real run-rate changes (won't).",
            "Lead the summary with the 3 variances that matter and the decision each implies.",
        ],
    },
    "project_kickoff": {
        "name": "Project kickoff skill",
        "topics": ["project_mgmt"],
        "body": "Kick off a project so it doesn't unravel in week three.",
        "steps": [
            "Write the one-line goal and the explicit NON-goals; get sponsor sign-off in writing.",
            "Name the team with roles and decision rights (who decides, who's consulted).",
            "Build the milestone workback from the deadline with dependencies visible.",
            "Open the RAID log with the risks everyone is already whispering about.",
            "Set the operating rhythm: status cadence, escalation path, where work lives.",
        ],
    },
    "raid_log": {
        "name": "RAID log skill",
        "topics": ["project_mgmt"],
        "body": "Track risks, assumptions, issues, and dependencies before they bite.",
        "steps": [
            "Capture each item with owner, impact, and likelihood — one line each, no essays.",
            "Risks get a mitigation AND a trigger condition for when it becomes an issue.",
            "Review weekly: anything unchanged 3 reviews running is stale or sandbagged.",
            "Escalate by impact, not by who shouts; the log is the agenda for that conversation.",
            "Close items explicitly with outcome noted — silent closure hides lessons.",
        ],
    },
    "decision_memo": {
        "name": "Decision memo skill",
        "topics": ["exec_ops"],
        "body": "Write a one-page memo that gets a decision made in one read.",
        "steps": [
            "State the decision needed and the deadline in the first two lines.",
            "Give 2-3 real options with honest trade-offs (no strawmen).",
            "Make a recommendation and say why in three bullets.",
            "List what was already considered/rejected so it doesn't get relitigated.",
            "End with: approver, what happens on approval, and what happens if no decision by the date.",
        ],
    },
    "okr_draft": {
        "name": "OKR drafting skill",
        "topics": ["exec_ops"],
        "body": "Draft OKRs that focus a quarter instead of decorating it.",
        "steps": [
            "Objectives: 2-3 max, qualitative, worth being excited about.",
            "Key results: measurable outcomes with numbers, not task lists in disguise.",
            "Sanity-check each KR: could it hit 100% while the objective still failed? Rewrite if so.",
            "Map dependencies on other teams now, not at the mid-quarter check-in.",
            "Set the grading scheme upfront (0.7 is success) and a monthly scoring cadence.",
        ],
    },
    "event_runofshow": {
        "name": "Event run-of-show skill",
        "topics": ["events"],
        "body": "Plan an event timeline that survives contact with reality.",
        "steps": [
            "Work back from the date: vendor lead-times (venue, catering, AV) land first.",
            "Build the run-of-show in 15-minute blocks with an owner per segment.",
            "Add buffer after every transition; everything runs over.",
            "Write the contingency row: rain plan, no-show speaker, dead microphone.",
            "Confirm all vendors and owners in writing the week before; day-of contact list on one page.",
        ],
    },
    "contract_intake": {
        "name": "Contract intake skill",
        "topics": ["legal_ops"],
        "body": "Prep a contract for review so legal answers in one pass.",
        "steps": [
            "Summarize the business deal in plain language: parties, money, term, what's exchanged.",
            "Flag the standard biters: auto-renewal, liability cap, indemnification, termination, data handling.",
            "Diff against your standard terms or the last signed version; list what changed.",
            "Write the specific questions for counsel — not just 'please review'.",
            "Track signature authority and the renewal/notice dates in your contract calendar.",
        ],
    },
    "game_design_doc": {
        "name": "Game design doc skill",
        "topics": ["game_design"],
        "body": "Write a one-page design doc that gets a game built, not admired.",
        "steps": [
            "One sentence: who the player is and what they should feel.",
            "Core loop in 3-5 verbs (e.g. explore, collect, upgrade, repeat).",
            "List the 3 mechanics that serve the loop; cut everything that doesn't.",
            "Define the first 5 minutes of play in detail — that's what gets prototyped.",
            "State the playtest question the prototype must answer.",
        ],
    },
    "playtest_plan": {
        "name": "Playtest plan skill",
        "topics": ["game_design"],
        "body": "Run playtests that produce decisions, not compliments.",
        "steps": [
            "Write the 1-3 questions this playtest must answer before recruiting anyone.",
            "Watch silently; note where players stall, quit, or misunderstand — don't rescue them.",
            "Ask what they were trying to do at each stall, not whether they liked it.",
            "Log observations verbatim, separate from your interpretation.",
            "Decide per question: confirmed, refuted, or needs another test — then change ONE thing.",
        ],
    },
    "art_brief": {
        "name": "Art brief skill",
        "topics": ["creative_art"],
        "body": "Brief an artist (human or AI) so round one is close.",
        "steps": [
            "State purpose and audience: where will this art live and who sees it.",
            "Collect 3 reference works and say what specifically to take from each.",
            "Define the constraints: dimensions, palette, style, what must NOT appear.",
            "Describe the focal point and the feeling, not just the objects.",
            "Plan two revision rounds max; consolidate feedback into one list per round.",
        ],
    },
    "image_gen_prompt": {
        "name": "AI image prompt skill",
        "topics": ["creative_art"],
        "body": "Get the image you mean out of Midjourney/DALL-E/Stable Diffusion.",
        "steps": [
            "Structure the prompt: subject, action, environment, style, lighting, composition.",
            "Name a medium and era/artist family for style instead of adjectives like 'beautiful'.",
            "Use negative prompts/exclusions for what keeps appearing wrongly.",
            "Iterate one variable at a time; keep a log of prompt -> result.",
            "Upscale/refine only the candidate that survives a day-later look.",
        ],
    },
    "math_walkthrough": {
        "name": "Math problem skill",
        "topics": ["academic"],
        "body": "Solve a math problem so you can solve the next one alone.",
        "steps": [
            "Restate what's given and what's asked; name the concept being tested.",
            "Work step-by-step with the rule used at each step written out.",
            "Verify independently: plug the answer back, check units and magnitude.",
            "Note the step where YOU went wrong (if checking your work) and why.",
            "Do one similar problem unaided to confirm it stuck.",
        ],
    },
    "study_guide": {
        "name": "Study guide skill",
        "topics": ["academic"],
        "body": "Build a study guide around recall, not re-reading.",
        "steps": [
            "List the testable concepts from syllabus/past exams; rank by weight and weakness.",
            "Turn each concept into questions (flashcard-style), not summaries.",
            "Schedule spaced repetition backwards from exam date; weakest topics first and most often.",
            "Practice retrieval under exam conditions: closed book, timed.",
            "Track misses; restudy ONLY what was missed.",
        ],
    },
    "essay_outline": {
        "name": "Essay outline skill",
        "topics": ["academic", "writing"],
        "body": "Outline an essay with an argument, not a topic.",
        "steps": [
            "Write the thesis as a claim someone could disagree with.",
            "Each body section: one point supporting the thesis, with its evidence named.",
            "Address the strongest counterargument honestly — it strengthens the essay.",
            "Check the outline reads as a logical chain; reorder until it does.",
            "Cite as you draft (required format: APA/MLA/Chicago), never at the end.",
        ],
    },
    "company_research": {
        "name": "Company research skill",
        "topics": ["investing", "research"],
        "body": "Research a company from filings, not headlines. Information, not financial advice.",
        "steps": [
            "Start with the 10-K/annual report: business model, revenue segments, stated risks.",
            "Pull 3-5 years of revenue, margins, cash flow — note the trend, not the latest quarter.",
            "Identify the moat claim and test it: would customers leave if prices rose 10%?",
            "Write the bear case as seriously as the bull case.",
            "Date every number used; markets move and data goes stale.",
        ],
    },
    "valuation_sanity": {
        "name": "Valuation sanity skill",
        "topics": ["investing"],
        "body": "Build a valuation whose assumptions are visible and attackable.",
        "steps": [
            "State the assumptions first: growth rate, margin, discount rate, terminal value.",
            "Build the simple model (DCF or multiples) with those inputs visible, not buried.",
            "Run the pessimistic case: what do the numbers say if growth halves?",
            "Compare against current price/multiples of named peers.",
            "Conclude with what would have to be TRUE for the price to make sense — then verify with a licensed advisor before acting.",
        ],
    },
    "deep_research": {
        "name": "Deep research skill",
        "topics": ["research"],
        "body": "Research a question across sources until the answer survives scrutiny.",
        "steps": [
            "Sharpen the question: scope, timeframe, what a satisfying answer looks like.",
            "Gather from independent source types: primary data, expert analysis, opposing views.",
            "Triangulate each key claim across 2+ unrelated sources; note single-source claims as weak.",
            "Record disagreements between sources explicitly instead of averaging them.",
            "Write up: answer, confidence level, citations per claim, and what remains unknown.",
        ],
    },
    "lit_review": {
        "name": "Literature review skill",
        "topics": ["research", "academic"],
        "body": "Survey what's known on a topic without drowning in it.",
        "steps": [
            "Define inclusion criteria first: years, fields, study types that count.",
            "Snowball: start from 2-3 recent review papers and mine their citations.",
            "Extract per source into one table: question, method, finding, limitation.",
            "Group by finding, not by paper — where does the literature agree, conflict, go silent?",
            "Write the synthesis around themes and gaps; the gap list is the contribution.",
        ],
    },
    "travel_itinerary": {
        "name": "Travel planning skill",
        "topics": ["travel", "calendar"],
        "body": "Book travel that survives delays and time zones.",
        "steps": [
            "Confirm the fixed points first: meetings that cannot move, in local time.",
            "Book flights with buffer for the meeting that matters; avoid last-flight-out dependencies.",
            "Put everything in the calendar in the traveler's CURRENT time zone with flight numbers and confirmation codes.",
            "One itinerary doc: transport, lodging, meetings, contacts, and a plan-B per leg.",
            "Check visa/ID requirements and expense policy before booking, not after.",
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
    "bulk_data": ["Sample of the CSV/export with headers (sanitized)", "Target system and field mapping", "Expected row count and how to verify after"],
    "backup": ["Backup product and scope", "RTO/RPO targets", "Last successful restore test date"],
    "vendor": ["Product name and version", "Case number (if existing)", "Logs/diagnostics already collected"],
    "fixit": ["Exact error message or screenshot text", "Who is affected and since when", "What changed recently (updates, policy, password)"],
    "notion": ["Workspace/page where it should live", "Database properties or page structure needed", "Who needs access"],
    "zoom": ["Meeting/webinar details or recording link", "Account/license type", "Expected audience size"],
    "google": ["Domain or OU in scope", "Affected users/groups", "Admin role you hold"],
    "slack": ["Workspace and channel names", "Apps/integrations involved", "Retention or governance rules"],
    "github": ["Org/repo name", "Branch and protection rules in play", "Who needs what access level"],
    "servicenow": ["Instance and table (incident/request/change)", "Assignment group", "Related CI / CMDB record"],
    "automation": ["Trigger event and source system", "Target systems and connectors", "What should happen on failure"],
    "refine": ["The rough idea in your own words", "What done looks like", "Constraints (time, tools, approvals)"],
    "writing": ["The text to work on (paste it)", "Audience and desired tone", "Length limit (if any)"],
    "excel": ["Column layout / sample rows", "What the result should show", "Excel version (or Google Sheets)"],
    "helpdesk": ["User identity already verified?", "Asset/account details", "Ticket number"],
    "learning": ["Your current familiarity level", "Why you need to know (context)", "Preferred depth: overview vs deep dive"],
    "summarize": ["The document/text to summarize (paste or attach)", "Who the summary is for", "Target length"],
    "api": ["API docs link or endpoint list", "Auth method (OAuth/key/token)", "Rate limits and paging details"],
    "mcp": ["Which AI client (Claude Desktop/Code, etc.)", "What data/tools to expose", "Where credentials live"],
    "local_llm": ["Hardware specs (RAM/GPU/VRAM)", "What the bot must know/do", "Privacy requirements"],
    "rmm": ["Device groups/organizations in scope", "Script run context (SYSTEM vs user)", "Maintenance window"],
    "siem": ["Source category / log source names", "Time range of interest", "A known event to validate against"],
    "edr": ["Alert ID and detection details", "Affected endpoint(s)", "Whether containment already happened"],
    "browser": ["Browser and version", "Managed via Intune/GPO or unmanaged", "Extensions involved"],
    "azure": ["Subscription and resource group", "Region and naming convention", "Cost constraints / budget"],
    "exchange_admin": ["Mailbox/DL names and owners", "Affected senders/recipients", "Message trace examples"],
    "m365_security": ["Policy names in scope", "Affected users or alerts", "License tier (E3/E5/Business)"],
    "python": ["Python version", "Allowed packages (or stdlib only)", "Input/output formats and sample data"],
    "windows": ["Windows version and build", "Event Viewer errors (paste them)", "Domain-joined / Intune-managed?"],
    "mac": ["macOS version", "Managed (Jamf/Intune) or personal", "Console/log errors if any"],
    "mobile": ["Device model and OS version", "MDM enrollment status", "Corporate or BYOD"],
    "printer": ["Printer model and connection (USB/network)", "One user or everyone", "Driver type (universal/specific)"],
    "appdev": ["Who will use it and for what", "Platform (web/desktop/mobile)", "Where it will run/be hosted"],
    "linux": ["Distro and version", "Service/unit names involved", "Relevant journalctl/log output"],
    "ad": ["Domain and OU paths", "GPO names in play", "gpresult/event log output"],
    "virtualization": ["Platform (VMware/Hyper-V) and version", "Host and VM names", "Snapshot/backup state"],
    "storage": ["Server/share paths", "Groups that should have access", "Current permissions export"],
    "database": ["Engine and version", "Database/table names", "A recent backup confirmed?"],
    "migration": ["Source and destination systems", "Data volume and item counts", "Cutover deadline and freeze window"],
    "regex": ["Sample strings that SHOULD match", "Samples that should NOT match", "Where it runs (PowerShell/Python/grep)"],
    "diagram": ["What the diagram must show (audience)", "Components and connections list", "Format needed (Mermaid/Visio/draw.io)"],
    "asset": ["Asset types in scope", "Source of truth today (sheet/RMM/Intune)", "What decision the data feeds"],
    "deckside": ["Which tab/feature (Announcer, Check-in, Dashboard, Lineup, Parent)", "Coach side or Parent side", "Sample PDF or data file involved", "Relevant AGENTS.md / BACKLOG.md entries"],
    "handoff": ["What the chat accomplished so far", "Work still in flight and the next step", "Decisions/constraints already settled (don't relitigate)"],
    "voip": ["Current call flow (numbers, attendants, queues)", "Phone system/carrier and licensing", "Business hours and after-hours behavior wanted"],
    "email_auth": ["Your sending domain(s)", "Current SPF/DKIM/DMARC records", "Headers from an affected message", "All systems that send mail as you"],
    "firewall": ["Firewall make/model and management tool", "Exact flow needed (source, destination, port)", "Change window and rollback expectations"],
    "aws": ["Account/region and naming convention", "What exists already (VPC, IAM setup)", "Budget sensitivity for new resources"],
    "vdi": ["Platform (Citrix/AVD/W365) and gateway", "Scope: which users/hosts, since when", "Session host specs and profile solution"],
    "passwords": ["Product and license tier", "Team/vault structure wanted", "Where credentials live today"],
    "file_transfer": ["Endpoints (source/destination, protocol)", "Schedule and file naming pattern", "What must happen on failure/missed file"],
    "licensing": ["Current entitlement counts and cost", "Actual usage numbers", "Renewal date and who negotiates"],
    "privacy_compliance": ["Applicable regulation (GDPR/CCPA)", "Request date and type", "Systems holding personal data"],
    "facilities": ["Site/room and access constraints", "Affected equipment and who depends on it", "Maintenance window options"],
    "calendar": ["Whose calendar and what tool (Outlook/Google)", "Hard constraints (time zones, fixed meetings)", "Priorities: what wins when things conflict"],
    "email_drafting": ["Who the recipient is and your relationship", "The thread/history being replied to", "The one outcome you want from the email"],
    "meeting_prep": ["Who's attending and what they care about", "What was agreed last time", "The decision or outcome this meeting needs"],
    "notes": ["The raw notes/transcript to process", "Who the notes are for", "What format the team already uses"],
    "presentation": ["Audience and time slot", "The one takeaway", "Brand/template requirements"],
    "word_docs": ["Document purpose and audience", "Existing template or style guide", "Sample of the current draft"],
    "notebooklm": ["The source documents to ground on", "The questions to answer from them", "What output format you need"],
    "travel": ["Fixed meetings/dates in local time", "Traveler preferences and loyalty programs", "Expense policy limits"],
    "hr": ["Role/level and team context", "Company templates or leveling guide", "Anything confidential to handle carefully"],
    "sales": ["The customer's stated problem (their words)", "Deal stage and history", "Pricing and what you can actually commit to"],
    "marketing": ["Audience and channel", "Brand voice/examples of past content", "The one CTA and how success is measured"],
    "support": ["The customer's message verbatim", "Account history and what they were promised", "What you can actually offer (refund, fix, timeline)"],
    "finance_ops": ["The source data (budget vs actuals export)", "Period and cost centers in scope", "Materiality threshold — what's worth explaining"],
    "project_mgmt": ["Goal, deadline, and non-goals", "Team and decision-makers", "Known risks and dependencies"],
    "exec_ops": ["Who the audience/principal is", "The decision needed and by when", "What's already been considered or rejected"],
    "events": ["Date, headcount, and budget", "Venue/vendor status so far", "What success looks like for the event"],
    "legal_ops": ["The contract/document itself", "Your standard terms or last signed version", "Business context: money, term, what's exchanged"],
    "game_design": ["Genre, platform, and scope (jam/indie/hobby)", "The player feeling you're going for", "What exists already (prototype, doc, art)"],
    "creative_art": ["Where the art will live (cover, screen, print) and dimensions", "2-3 reference works you like and why", "What must NOT appear"],
    "academic": ["The exact problem/assignment text", "Your current level and where you got stuck", "Format requirements (APA/MLA, length, due date)"],
    "investing": ["Ticker/company and your timeframe", "What you already hold or know", "Risk tolerance and what decision this feeds"],
    "research": ["The precise question and scope", "What you'll use the findings for", "Sources you already have or trust"],
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
        overlap = set(item["topics"]) & set(topics)
        # Intent-defining topics outweigh the subject area: "outlook crashing"
        # gets the troubleshooting shape, "diagram the network" gets the
        # diagram shape — not the product-area template.
        return len(overlap) + (0.5 if overlap & {"fixit", "edr", "diagram"} else 0)

    # Template: best topic overlap, fall back by destination. Without any
    # topic overlap the tie-break math is meaningless — go straight to the
    # generic template for the destination.
    best_key, best_overlap = None, 0
    best_score = -1
    for key, t in PROMPT_TEMPLATES.items():
        overlap = topic_score(t)
        # Specific templates (fewer topics) win ties over broad ones.
        s = overlap * 2 - 0.01 * len(t["topics"])
        if t["destination"] == dest_info["destination"]:
            s += 0.5
        if s > best_score:
            best_key, best_score, best_overlap = key, s, overlap
    if best_overlap <= 0:
        best_key = "codex_execution" if dest_info["destination"] == "Codex" else "chatgpt_planning"

    def rank_key(item):
        # Primary: topic overlap. Tie-break: how focused the item is on the
        # detected topics — a dedicated Exchange skill beats a broad M365 one.
        score = topic_score(item)
        focus = score / max(1, len(item["topics"]))
        return (-score, -focus)

    modules = sorted((k for k, m in AGENT_MODULES.items() if topic_score(m) > 0),
                     key=lambda k: rank_key(AGENT_MODULES[k]))
    # Always-on backbone: plan before doing, work to a contract, verify.
    for default in ("plan_first", "harness", "validation"):
        if default not in modules:
            modules.append(default)

    skills = sorted((k for k, s in SKILL_TEMPLATES.items() if topic_score(s) > 0),
                    key=lambda k: rank_key(SKILL_TEMPLATES[k]))

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


# ---------------------------------------------------------------------------
# Best-practices knowledge base: the pet answers questions about prompting,
# context, handoffs, and AskPet itself instead of generating a prompt.
# ---------------------------------------------------------------------------

HELP_TOPICS = {
    "context_basics": {
        "keywords": ["what context", "context should", "how much context",
                     "context to include", "context do i", "good context",
                     "context matter", "context best"],
        "answer": [
            "Context is the single biggest lever you have — a mediocre ask "
            "with great context beats a perfect ask with none. The AI only "
            "knows what's in the conversation; it can't see your screen, "
            "your files, or your last chat.",
            "What to include:\n"
            "• The actual material — paste error messages, transcripts, and "
            "file contents, don't describe them\n"
            "• Exact names: systems, versions, file paths, ticket numbers\n"
            "• What you already tried and what happened\n"
            "• What done looks like\n\n"
            "What to leave out: history that doesn't change the answer, and "
            "anything you'd have to say 'ignore that part' about. Lean and "
            "specific beats long and vague.",
        ],
    },
    "context_clearing": {
        "keywords": ["clear context", "clearing context", "start fresh",
                     "when should i start a new", "chat too long",
                     "chat is too long", "reset the chat", "clear the chat",
                     "new conversation", "stale context", "fresh chat",
                     "fresh conversation", "start over", "start a new chat"],
        "answer": [
            "Start a fresh chat when the old context starts hurting more "
            "than helping. Signs it's time:\n"
            "• The assistant keeps referring back to abandoned approaches\n"
            "• You're correcting the same misunderstanding repeatedly\n"
            "• The topic has genuinely changed\n"
            "• Responses get slower, vaguer, or contradict earlier answers",
            "Don't just abandon the chat though — do a handoff first: ask it "
            "to summarize objective, current state, decisions made, and next "
            "steps into one block, then seed the new chat with it. Ask me to "
            "build you a handoff prompt and I'll set it up. 🐾",
        ],
    },
    "handoff_howto": {
        "keywords": ["handoff", "hand off", "move to a new chat",
                     "continue in a new", "carry over to"],
        "answer": [
            "A handoff moves work to a fresh chat without losing what the "
            "old one knew. The flow:\n"
            "1. Ask the CURRENT chat for a handoff block: objective, current "
            "state, decisions made, in-flight work, next steps, gotchas — "
            "all in one code block\n"
            "2. Read it before trusting it — assistants summarize their own "
            "work optimistically; fix what's wrong or missing\n"
            "3. Add exact identifiers the new chat can't guess (paths, "
            "versions, URLs)\n"
            "4. Paste it as the FIRST message of the new chat and ask it to "
            "confirm understanding before doing anything",
            "Type something like “make me a handoff prompt” and I'll "
            "generate the full template for you.",
        ],
    },
    "prompt_basics": {
        "keywords": ["good prompt", "better prompt", "prompt tips",
                     "write prompts", "write a good", "best practice",
                     "best practices", "prompting", "improve my prompts"],
        "answer": [
            "The prompts that work share four parts:\n"
            "• GOAL — one sentence a stranger would understand\n"
            "• CONTEXT — the real material (errors, files, names), pasted "
            "not described\n"
            "• CONSTRAINTS — tools, format, what must NOT change\n"
            "• DONE — what a good result looks like, measurable if possible",
            "Three habits that beat any template:\n"
            "1. Plan first — ask the AI to restate the task and propose a "
            "plan before doing work; you catch misunderstandings early\n"
            "2. One task per ask — bundled requests get half-answers\n"
            "3. Show an example — one example of the output you want beats "
            "three paragraphs describing it\n\n"
            "That's exactly what I build into every prompt here — describe "
            "a task and I'll show you. 🐾",
        ],
    },
    "destination_choice": {
        "keywords": ["codex or chatgpt", "chatgpt or claude", "which assistant",
                     "which ai should", "where should i ask", "claude code or",
                     "when to use codex", "when to use claude"],
        "answer": [
            "Rule of thumb:\n"
            "• Codex / Claude Code — hands-on execution: code, scripts, "
            "files, repos, testing, anything that touches a machine\n"
            "• ChatGPT / Claude — thinking and writing: planning, "
            "architecture, docs, analysis, drafts\n"
            "• Both — plan it in ChatGPT/Claude first, then hand the "
            "approved plan to Codex/Claude Code to execute",
            "I recommend a destination automatically with every prompt I "
            "build — that's the “Send it to” line in my replies.",
        ],
    },
    "plan_first_why": {
        "keywords": ["plan first", "plan mode", "why plan", "plan before"],
        "answer": [
            "Plan-first means the AI restates your goal, lists assumptions, "
            "asks its questions, and proposes a numbered plan BEFORE doing "
            "any work — like plan mode in Codex and Claude Code.",
            "Why it's worth the extra step: misunderstandings get caught "
            "when they cost one message, not after 200 lines of wrong code. "
            "Every prompt I generate includes a Plan-First module by "
            "default; you'll see the AI check in with you before executing.",
        ],
    },
    "verify_output": {
        "keywords": ["trust the answer", "hallucinat", "verify the answer",
                     "double check the ai", "ai is wrong", "made up",
                     "check its work", "can i trust", "trust the ai",
                     "trust what", "is the ai right"],
        "answer": [
            "Treat AI output like work from a fast, confident junior: "
            "usually right, occasionally confidently wrong.\n"
            "• Numbers, names, links, commands — verify against the source "
            "before acting\n"
            "• Code/scripts — run on ONE test target before wide use\n"
            "• Claims about your environment — the AI can't see it; it's "
            "pattern-matching\n"
            "• Ask “what are you least sure about in that answer?” — "
            "surprisingly effective",
            "My prompts bake in a Validation module for exactly this: the "
            "AI has to state what it checked before claiming done.",
        ],
    },
    "privacy_local": {
        "keywords": ["send my data", "my data go", "data leave", "telemetry",
                     "privacy", "phone home", "track me", "tracking",
                     "is this local", "run locally", "work offline",
                     "need internet", "cloud ai", "which ai do you use",
                     "what ai do you use", "use chatgpt yourself"],
        "answer": [
            "Everything I do runs 100% on this machine — no cloud AI, no "
            "telemetry, no account. I build prompts with local keyword "
            "matching, and if Local AI is on, answers come from a model "
            "running on YOUR PC (Ollama on localhost) — your text never "
            "leaves the machine either way.",
            "The only time I touch the network is when YOU ask me to: "
            "downloading a new pet look from codex-pets.net, or talking to "
            "a local model via Ollama on YOUR machine (localhost) if you've "
            "enabled Local AI. Your prompts, history, and settings live in "
            "%LOCALAPPDATA%\\AskPet (Windows) and never leave the "
            "machine. 🐾",
        ],
    },
    "local_ai_help": {
        "keywords": ["local ai", "ollama", "gemma", "local model",
                     "answer locally", "answer questions yourself",
                     "use a local model", "use a local llm", "use a local ai",
                     "offline model", "which model do you"],
        "answer": [
            "If Ollama is installed (ollama.com) with a model like Gemma, "
            "I can answer light asks myself — fully offline:\n"
            "• Rewrites — “rewrite this to sound professional: …”\n"
            "• Summaries — “summarize this: …” (paste the text)\n"
            "• Email drafts — “write an email asking…”\n"
            "• Quick questions — anything question-shaped\n\n"
            "Bigger work (code, scripts, multi-step tasks) still gets a "
            "proper prompt for Codex, Claude Code, ChatGPT, or Claude — a "
            "small local model shouldn't pretend to do that.",
            "Right-click me → ✨ Local AI to turn it on/off or pick which "
            "installed model I use. Every local answer is labeled with the "
            "model that wrote it. Small models are handy but not brilliant "
            "— double-check anything important. 🐾",
            "Power move: knowledge packs. Build one from a YouTube "
            "channel's transcripts (build_knowledge_pack.py in the repo) "
            "and I'll ground my answers in that creator's actual content — "
            "with credit — for hobby topics like FPV drones. Packs stay on "
            "this machine, personal use only.",
        ],
    },
    "askpet_help": {
        "keywords": ["askpet", "what can you do", "how do you work",
                     "how do i use you", "what do you do", "help me use",
                     "what are skills", "what are modules", "what are agent"],
        "answer": [
            "Here's how I work: describe a task — typos and shorthand are "
            "fine — and I'll figure out what you need, ask a question or "
            "two if your message is short, then build a copy-ready prompt "
            "for Codex, Claude Code, ChatGPT, or Claude.",
            "What's in my replies:\n"
            "• Send it to — which assistant fits the task\n"
            "• Template — the prompt structure (45 of them)\n"
            "• Chips — the agent modules (expert instructions) and skills "
            "(step-by-step workflows) I baked in; tap one to read it\n"
            "• The prompt itself — Copy, Save, or Adjust in editor",
            "Other tricks: say “skip” to skip my questions; right-click me "
            "for the full editor, pet sizes, and 2,000+ other pets; ask me "
            "about prompting best practices anytime — context, handoffs, "
            "when to start a fresh chat. 🐾",
        ],
    },
}

QUESTION_STARTERS = ("how ", "what ", "whats ", "what's ", "when ", "why ",
                     "should ", "can you explain", "do i ", "does ", "is it ",
                     "do you ", "are you ", "can i ",
                     "any tips", "tips on", "tell me about", "help me understand")


def answer_help_question(text: str):
    """Match a best-practices/help question to a knowledge-base answer.

    Returns the answer (list of chat bubbles) or None. Only fires for
    question-shaped messages so task requests still generate prompts.
    """
    lw = text.strip().lower()
    is_question = lw.endswith("?") or lw.startswith(QUESTION_STARTERS)
    if not is_question:
        return None
    best_key, best_hits = None, 0
    for key, entry in HELP_TOPICS.items():
        hits = sum(1 for k in entry["keywords"] if k in lw)
        if hits > best_hits:
            best_key, best_hits = key, hits
    if best_key is None:
        return None
    return HELP_TOPICS[best_key]["answer"]


def clarifying_questions(cleaned: str, rec: dict) -> list:
    """Decide what to ask before generating, for short/ambiguous requests.

    Returns at most 2 questions; an empty list means we know enough.
    """
    questions = []
    words = len(cleaned.split())
    signal = rec["codex_score"] + rec["chatgpt_score"]

    if "fixit" in rec["topics"]:
        questions.append("Who's affected — one user, a few, or everyone? "
                         "And since when?")
        questions.append("What's the exact error message (if there is one), "
                         "and did anything change recently — updates, policy, "
                         "password?")
    if not rec["topics"]:
        questions.append("Which system or tech is this about — e.g. Intune, "
                         "Entra, Exchange, Okta, a script, a server?")
    if signal < 2 and words < 12 and "fixit" not in rec["topics"]:
        questions.append("Should the end result be something to run (script, "
                         "code, config) or something written (plan, doc, "
                         "ticket)?")
    if not questions and words < 6:
        questions.append("Give me one more detail — error text, system name, "
                         "or what the finished result should look like?")
    return questions[:2]


OFFICE_TOPICS = {
    "calendar", "email_drafting", "meeting_prep", "notes", "presentation",
    "word_docs", "notebooklm", "travel", "hr", "sales", "marketing",
    "support", "finance_ops", "project_mgmt", "exec_ops", "events",
    "legal_ops", "writing", "summarize", "learning", "excel", "notion",
    "game_design", "creative_art", "academic", "investing", "research",
}


def build_prompt(cleaned_task: str, rec: dict, selected_modules: list,
                 selected_skills: list, checked_context: list) -> str:
    """Assemble the final copy-ready prompt."""
    template = PROMPT_TEMPLATES[rec["template"]]
    body = template["body"]
    # Office/role work gets office-flavored defaults; "rollback steps" reads
    # wrong in a board brief.
    office = bool(set(rec["topics"]) & OFFICE_TOPICS) and rec["destination"] != "Codex"
    constraints = (
        "Professional tone, ready to use as-is; state any assumptions made "
        "and flag anything that needs my confirmation before it goes out."
        if office else
        "Local-first, least privilege, no secrets in output, include rollback steps."
    )
    inputs_hint = (
        "(paste the relevant material here: the thread, notes, data, or "
        "current draft)" if office else
        "(paste the relevant material here: transcripts, error "
        "messages, file paths, sample data)"
    )
    fills = {
        "{TASK}": cleaned_task,
        "{SCOPE}": "Only the work described above; ask before expanding scope.",
        "{INPUTS}": ("; ".join(checked_context) if checked_context else inputs_hint),
        "{TOOLS}": "Standard tooling for this stack; no destructive operations without confirmation.",
        "{CONSTRAINTS}": constraints,
        "{OUTPUTS}": "Working result plus a short summary of what changed and how it was verified.",
        "{VERIFICATION}": "List the exact checks performed and their results before claiming completion.",
    }
    for k, v in fills.items():
        body = body.replace(k, v)

    parts = [f"# {template['name']}", "", body]

    # Filter to keys that still exist so a renamed/removed library entry (or a
    # rec replayed from history) degrades gracefully instead of raising KeyError.
    modules = [mk for mk in selected_modules if mk in AGENT_MODULES]
    if modules:
        parts.append("\n## Operating instructions")
        for mk in modules:
            m = AGENT_MODULES[mk]
            parts.append(f"\n### {m['name']}\n{m['body']}")

    skills = [sk for sk in selected_skills if sk in SKILL_TEMPLATES]
    if skills:
        parts.append("\n## Reusable workflow(s) to follow")
        for sk in skills:
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


# Retention window for prompt history. Default 3 days; users can pick
# 24 hours or 7 days from the pet menu, or clear manually.
HISTORY_RETENTION_CHOICES = (("24 hours", 24), ("3 days", 72), ("7 days", 168))
DEFAULT_RETENTION_HOURS = 72


def history_retention_hours(settings: dict = None) -> int:
    s = settings if settings is not None else load_json(SETTINGS_FILE, {})
    hours = s.get("history_retention_hours", DEFAULT_RETENTION_HOURS)
    valid = {h for _, h in HISTORY_RETENTION_CHOICES}
    return hours if hours in valid else DEFAULT_RETENTION_HOURS


def prune_history(retention_hours: int = None) -> int:
    """Drop history entries older than the retention window; return kept count."""
    hours = retention_hours or history_retention_hours()
    history = load_json(HISTORY_FILE, [])
    cutoff = datetime.now() - timedelta(hours=hours)
    kept = []
    for e in history:
        try:
            ts = datetime.fromisoformat(e.get("timestamp", ""))
        except (TypeError, ValueError):
            continue  # unreadable timestamp: treat as expired
        if ts >= cutoff:
            kept.append(e)
    if len(kept) != len(history):
        save_json(HISTORY_FILE, kept)
    return len(kept)


def clear_history():
    save_json(HISTORY_FILE, [])


def save_history_entry(raw: str, cleaned: str, rec: dict, prompt: str):
    prune_history()
    history = load_json(HISTORY_FILE, [])
    # Generation auto-saves; an explicit Save right after shouldn't duplicate.
    if history and history[-1].get("prompt") == prompt:
        return
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
# Chat transcript history (separate from the saved-prompt history above).
# The chat keeps a rolling transcript so each reopen shows everything up to
# the last clear, then a "new chat" divider. Persisted on chat close, local
# only. Interactive message kinds (chips/actions) are NOT stored — only the
# conversation itself. Age-pruned like the prompt history; manually clearable.
# ---------------------------------------------------------------------------

CHAT_PERSIST_KINDS = ("user", "pet", "prompt")  # transcript content worth keeping
CHAT_HISTORY_CAP = 200                           # max stored messages


def chat_retention_hours(settings: dict = None) -> int:
    s = settings if settings is not None else load_json(SETTINGS_FILE, {})
    hours = s.get("chat_retention_hours", DEFAULT_RETENTION_HOURS)
    valid = {h for _, h in HISTORY_RETENTION_CHOICES}
    return hours if hours in valid else DEFAULT_RETENTION_HOURS


def prune_chat_history(retention_hours: int = None) -> int:
    """Drop chat messages older than the retention window; return kept count."""
    hours = retention_hours or chat_retention_hours()
    hist = load_json(CHAT_HISTORY_FILE, [])
    cutoff = datetime.now() - timedelta(hours=hours)
    kept = []
    for e in hist:
        try:
            ts = datetime.fromisoformat(e.get("ts", ""))
        except (TypeError, ValueError):
            continue  # unreadable timestamp: treat as expired
        if ts >= cutoff:
            kept.append(e)
    if len(kept) != len(hist):
        save_json(CHAT_HISTORY_FILE, kept)
    return len(kept)


def load_chat_history() -> list:
    """The saved transcript (after age-pruning) as a list of (kind, text)."""
    prune_chat_history()
    hist = load_json(CHAT_HISTORY_FILE, [])
    return [(e.get("kind", "pet"), e.get("text", "")) for e in hist
            if e.get("kind") in CHAT_PERSIST_KINDS and e.get("text")]


def append_chat_messages(pairs: list):
    """Append (kind, text) pairs to the saved chat history (capped)."""
    if not pairs:
        return
    hist = load_json(CHAT_HISTORY_FILE, [])
    ts = datetime.now().isoformat(timespec="seconds")
    for kind, text in pairs:
        hist.append({"ts": ts, "kind": kind, "text": text})
    save_json(CHAT_HISTORY_FILE, hist[-CHAT_HISTORY_CAP:])


def clear_chat_history():
    save_json(CHAT_HISTORY_FILE, [])


# ---------------------------------------------------------------------------
# Long-term pet memory: durable facts the pet "remembers" about the person it
# chats with (names, favorites). Injected into the persona so it persists
# across sessions and applies to whichever pet is loaded. Captured explicitly
# ("remember that …") — auto-extraction is unreliable on a small local model.
# Local-only, clearable. Separate from the chat transcript history.
# ---------------------------------------------------------------------------

PET_MEMORY_CAP = 40
# Capture a fact only when intent is clear: either an explicit marker
# ("remember THAT/THIS/: X") or a personal lead ("remember I/my/we/our/me …").
# This avoids hijacking casual chat like "remember the good old days". "to X"
# is excluded from the marker branch (that's a task, not a fact).
_REMEMBER_VERB = r"(?:remember|don'?t\s+forget|keep\s+in\s+mind)"
_REMEMBER_RE = re.compile(
    r"^\s*(?:hey[, ]+|ok[, ]+|please[, ]+)?" + _REMEMBER_VERB + r"(?:"
    r"(?:\s+that|\s+this|:)\s+(?!to\b)(.+)"               # explicit marker
    r"|"
    r"\s+(?=(?:i|i'?m|my|mine|we|our|me)\b)(.+)"          # personal fact lead
    r")", re.I | re.S)


def load_pet_memory() -> list:
    """The durable facts the pet remembers, as a list of strings."""
    d = load_json(PET_MEMORY_FILE, {})
    return [f.strip() for f in d.get("facts", [])
            if isinstance(f, str) and f.strip()]


def add_pet_memory(fact: str) -> bool:
    """Store a fact (normalized, deduped, capped). Returns True if newly added."""
    # Collapse internal whitespace/newlines (the capture is dot-all) and trim
    # trailing punctuation so the persona stays single-line and dedup is stable.
    fact = re.sub(r"\s+", " ", (fact or "")).strip().rstrip(".!?,;:").strip()
    if not fact:
        return False
    facts = load_pet_memory()
    if any(fact.lower() == f.lower() for f in facts):
        return False
    facts.append(fact)
    save_json(PET_MEMORY_FILE, {"facts": facts[-PET_MEMORY_CAP:]})
    return True


def clear_pet_memory():
    save_json(PET_MEMORY_FILE, {"facts": []})


def remember_fact(raw: str):
    """The fact to store if `raw` is an explicit 'remember …' request, else
    None (so normal chat isn't intercepted)."""
    m = _REMEMBER_RE.match(raw or "")
    if not m:
        return None
    fact = (m.group(1) or m.group(2) or "").strip().rstrip(".!?,;:").strip()
    return fact or None


# ---------------------------------------------------------------------------
# Tkinter UI
# ---------------------------------------------------------------------------

PET_GREETING = (
    "Hi! I'm AskPet. 🐾\n\n"
    "Tell me what you're trying to do — typos and shorthand are fine. "
    "I'll recommend where it belongs (Codex or ChatGPT web), pick a "
    "template, and build you a copy-ready prompt."
)

HELP_TEXT = """How to use AskPet

Kogi the pet floats above all your windows:
- Left-click Kogi to open/close the chat.
- Drag Kogi to move it (position is remembered).
- Right-click Kogi for the menu (chat, full editor, wandering, exit).

In the chat, just type — Kogi can answer questions, rewrite or summarize
text, review writing, or draft an email (answered on-device by local AI when
it's set up). Want a copy-ready prompt for Codex, Claude Code, ChatGPT, or
Claude instead? Type "/fix-prompt" and your task.

The full editor (below) is the dedicated prompt builder, with fine-grained
control:

1. Pick your team (IT for now — more teams later).
2. Type what you're trying to do in the chat box. Messy input is fine —
   AskPet fixes common typos and expands shorthand like "iac" or "o365".
   Unknown words get a red underline; right-click one for suggestions.
3. Click "Ask AskPet" (or press Ctrl+Enter).
4. Review the recommendations:
   - Destination: Codex, ChatGPT web, or Both
   - Prompt template, agent modules, skill templates
   - Context checklist: tick what you can provide
5. Click "Generate Prompt" to build the final prompt.
6. Click "Copy to Clipboard" and paste it into Codex or ChatGPT web.
7. "Save Prompt" stores it in your local history.

Everything runs locally. No cloud AI, no telemetry. Optional Local AI
answers come from Ollama on this machine (localhost) — nothing leaves
your PC. Your data lives in:
  Windows: %LOCALAPPDATA%\\AskPet\\
  macOS:   ~/Library/Application Support/AskPet/
"""


class AskPetApp:
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
        self.root.after(2500, self._check_updates)

    # ---- UI construction -------------------------------------------------

    def _build_ui(self):
        top = ttk.Frame(self.root, padding=8)
        top.pack(fill="x")

        ttk.Label(top, text="🐾 AskPet", font=("Segoe UI", 14, "bold")).pack(side="left")

        self.update_label = ttk.Label(top, text=f"App v{APP_VERSION} · Content {CONTENT_VERSION} · Checking for updates…",
                                      foreground="#888888")
        self.update_label.pack(side="right")

        ttk.Button(top, text="Help", command=self._show_help).pack(side="right", padx=8)

        main = ttk.PanedWindow(self.root, orient="horizontal")
        main.pack(fill="both", expand=True, padx=8, pady=4)

        # Left pane: chat input + recommendations
        left = ttk.Frame(main, padding=4)
        main.add(left, weight=1)

        chat_frame = ttk.LabelFrame(left, text="Talk to AskPet", padding=6)
        chat_frame.pack(fill="x")

        self.pet_label = ttk.Label(chat_frame, text=PET_GREETING, wraplength=440,
                                   justify="left", padding=4)
        self.pet_label.pack(fill="x")

        self.input_text = tk.Text(chat_frame, height=5, wrap="word", undo=True,
                                  font=("Segoe UI", 10))
        self.input_text.pack(fill="x", pady=4)
        configure_misspell_tag(self.input_text)
        self.input_text.bind("<KeyRelease>", self._on_key_release)
        self.input_text.bind("<Button-3>", self._on_right_click)
        self.input_text.bind("<Control-Return>", lambda e: (self._ask(), "break")[1])

        btn_row = ttk.Frame(chat_frame)
        btn_row.pack(fill="x")
        ttk.Button(btn_row, text="Ask AskPet  (Ctrl+Enter)", command=self._ask).pack(side="left")
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

        detail_frame = ttk.LabelFrame(rec_frame, text="Details (click a module or skill to read it)",
                                      padding=4)
        detail_frame.pack(fill="x", pady=(6, 0))
        self.detail_text = tk.Text(detail_frame, height=6, wrap="word", state="disabled",
                                   font=("Segoe UI", 9), background="#f7f7f7", relief="flat")
        self.detail_text.pack(fill="x")
        self.module_list.bind("<ButtonRelease-1>", lambda e: self._show_detail(e, "module"))
        self.skill_list.bind("<ButtonRelease-1>", lambda e: self._show_detail(e, "skill"))

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

    def _show_detail(self, event, kind):
        lb = event.widget
        idx = lb.nearest(event.y)
        if idx < 0:
            return
        if kind == "module":
            item = list(AGENT_MODULES.values())[idx]
            text = f"{item['name']}\n\n{item['body']}"
        else:
            item = list(SKILL_TEMPLATES.values())[idx]
            text = f"{item['name']}\n\n{item['body']}"
            if item.get("steps"):
                text += "\n" + "\n".join(f"{i}. {s}" for i, s in enumerate(item["steps"], 1))
        self.detail_text.config(state="normal")
        self.detail_text.delete("1.0", "end")
        self.detail_text.insert("1.0", text)
        self.detail_text.config(state="disabled")

    # ---- Spell underline + right-click suggestions -----------------------

    def _on_key_release(self, event=None):
        if event and event.keysym in ("Up", "Down", "Left", "Right", "Shift_L", "Shift_R"):
            return
        self._recheck_spelling()

    def _recheck_spelling(self):
        text = self.input_text.get("1.0", "end-1c")
        self.input_text.tag_remove("misspelled", "1.0", "end")
        for m in re.finditer(r"[A-Za-z]+(?:'[A-Za-z]+)*", text):
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
        raw = self.input_text.get("1.0", "end-1c").strip()
        save_history_entry(raw, self.cleaned, self.rec, prompt)
        self.status_label.config(text="Prompt generated (auto-saved to history).")

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
        win.title("How to use AskPet")
        win.geometry("560x520")
        txt = tk.Text(win, wrap="word", padx=10, pady=10, font=("Segoe UI", 10))
        txt.insert("1.0", HELP_TEXT)
        txt.config(state="disabled")
        txt.pack(fill="both", expand=True)

    # ---- Settings ----------------------------------------------------------

    def _load_settings(self):
        pass  # nothing editor-specific to restore right now

    def _save_settings(self):
        # Merge, don't overwrite — the pet overlay stores its position here too.
        settings = load_json(SETTINGS_FILE, {})
        settings.update({"app_version": APP_VERSION})
        save_json(SETTINGS_FILE, settings)

    def on_close(self):
        self._save_settings()
        self.root.destroy()

    def _check_updates(self):
        """Resolve the header's update label against GitHub, off the UI thread."""
        def worker():
            rel = available_update()
            try:
                self.root.after(0, lambda: self._show_update_status(rel))
            except tk.TclError:
                pass  # editor window closed mid-check
        threading.Thread(target=worker, daemon=True).start()

    def _show_update_status(self, rel):
        if not self.update_label.winfo_exists():
            return
        if rel:
            self.update_label.config(
                text=f"App v{APP_VERSION} · Update {rel['tag']} available ▸",
                foreground="#b85c00", cursor="hand2")
            self.update_label.bind(
                "<Button-1>",
                lambda e: webbrowser.open(rel.get("page_url", RELEASES_PAGE)))
        else:
            self.update_label.config(
                text=f"App v{APP_VERSION} · Content {CONTENT_VERSION} · Up to date",
                foreground="#2a7a2a")


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
# This is the ONLY network access in AskPet, it never happens
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

# Per-pet facing corrections. AskPet's convention is that art faces RIGHT and
# the app mirrors it for leftward travel; a sheet drawn facing LEFT otherwise
# looks like it walks backwards. We can't fix codex-pets.net (third-party art),
# so when one of its pets is drawn the other way we annotate the affected
# animations here and re-stamp them on every (re)download. Keyed by pet id;
# each value maps an animation name to the direction its art actually faces.
PET_FACING_OVERRIDES = {
    "godzilla-blue": {"walk_right": "left", "walk_left": "right", "run": "left"},
}


def apply_facing_overrides(pet_id: str, animations: dict) -> dict:
    """Stamp known per-pet `facing` corrections onto a freshly built manifest.

    No-op for pets without an override entry, and skips animations the sheet
    didn't actually include. Mutates and returns `animations`.
    """
    for name, face in PET_FACING_OVERRIDES.get(pet_id, {}).items():
        if name in animations:
            animations[name]["facing"] = face
    return animations


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


# ---------------------------------------------------------------------------
# Self-update: check GitHub Releases for a newer signed build and, on request,
# download + verify + run the installer. Network access happens only when the
# user asks (or a quiet check shortly after launch); nothing is sent but the
# request itself. The installer is executed ONLY after its Authenticode
# signature is confirmed Valid AND issued to the expected publisher, and only
# when the download came from this project's GitHub release assets over HTTPS.
# ---------------------------------------------------------------------------

GITHUB_REPO = "ronnierosal/askpet"
GITHUB_API_LATEST = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
RELEASES_PAGE = f"https://github.com/{GITHUB_REPO}/releases/latest"
# Update installers are accepted only from this project's release-asset URLs.
RELEASE_ASSET_PREFIX = f"https://github.com/{GITHUB_REPO}/releases/download/"
# The downloaded installer must be Authenticode-signed by this publisher.
EXPECTED_SIGNER_CN = "Ronnie Deoferio Rosal"


def parse_version(text: str) -> tuple:
    """'v0.32.2' or '0.32.2' -> (0, 32, 2). A leading 'v' and any non-numeric
    suffix on a part are ignored; returns () for unparseable input so callers
    can treat junk as "no version" rather than crash."""
    parts = []
    for token in (text or "").strip().lstrip("vV").split("."):
        digits = ""
        for ch in token:
            if ch.isdigit():
                digits += ch
            else:
                break
        if not digits:
            break
        parts.append(int(digits))
    return tuple(parts)


def _is_release_asset_url(url) -> bool:
    """True only for an HTTPS download URL under this project's releases."""
    return isinstance(url, str) and url.startswith(RELEASE_ASSET_PREFIX)


def fetch_latest_release(timeout: int = 8) -> dict:
    """Latest published release from GitHub, or None on any failure.

    Returns {tag, version, page_url, asset_url, asset_name, asset_size}; the
    asset_* fields describe the signed Windows installer when one is attached
    (and its download URL is a trusted GitHub release asset).
    """
    try:
        data = json.loads(_http_get(GITHUB_API_LATEST, timeout=timeout))
    except (urllib.error.URLError, OSError, ValueError):
        return None
    tag = data.get("tag_name") or ""
    if not parse_version(tag):
        return None
    asset = None
    for a in data.get("assets") or []:
        name = (a.get("name") or "").lower()
        url = a.get("browser_download_url") or ""
        if name.endswith(".exe") and _is_release_asset_url(url):
            asset = a
            break
    return {
        "tag": tag,
        "version": parse_version(tag),
        "page_url": data.get("html_url") or RELEASES_PAGE,
        "asset_url": (asset or {}).get("browser_download_url"),
        "asset_name": (asset or {}).get("name"),
        "asset_size": (asset or {}).get("size"),
    }


def available_update(local_version: str = APP_VERSION, timeout: int = 8) -> dict:
    """The latest-release dict if GitHub has a newer version, else None."""
    rel = fetch_latest_release(timeout=timeout)
    if rel and rel["version"] > parse_version(local_version):
        return rel
    return None


def _ps_quote(value) -> str:
    """Single-quote a value for safe inlining into a PowerShell command."""
    return "'" + str(value).replace("'", "''") + "'"


def verify_signed_installer(path, expected_cn: str = EXPECTED_SIGNER_CN) -> bool:
    """True only if `path` carries a Valid Authenticode signature issued to the
    expected publisher. Windows-only; any error, absence, or mismatch -> False.
    This is the gate that must pass before a downloaded installer is run."""
    if sys.platform != "win32" or not Path(path).exists():
        return False
    # Compare the certificate's CN (simple name) for an EXACT match — not a
    # substring of the full Distinguished Name, which would also accept e.g.
    # CN="<name>indo" or O="<name> LLC" from a different, CA-validated signer.
    script = (
        f"$s = Get-AuthenticodeSignature -LiteralPath {_ps_quote(path)};"
        "if ($s.Status -ne 'Valid') { exit 2 };"
        "if ($null -eq $s.SignerCertificate) { exit 3 };"
        "$cn = $s.SignerCertificate.GetNameInfo("
        "[System.Security.Cryptography.X509Certificates.X509NameType]::SimpleName, $false);"
        f"if ($cn -cne {_ps_quote(expected_cn)}) {{ exit 4 }};"
        "exit 0"
    )
    try:
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True, timeout=60,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return proc.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def download_release_asset(url: str, dest, expected_size: int = None,
                           timeout: int = 120, progress=None,
                           cancel: "threading.Event" = None):
    """Stream a release asset to `dest` atomically. Refuses untrusted URLs,
    verifies the final size when known, and reports progress(fraction 0..1).
    Returns the destination Path; raises on any failure (incl. cancellation)."""
    if not _is_release_asset_url(url):
        raise ValueError("refusing to download an update from an untrusted URL")
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_name(dest.name + ".part")
    req = urllib.request.Request(url, headers={"User-Agent": f"{APP_NAME}/{APP_VERSION}"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp, open(part, "wb") as f:
            total = int(resp.headers.get("Content-Length") or expected_size or 0)
            read = 0
            while True:
                if cancel is not None and cancel.is_set():
                    raise RuntimeError("update cancelled")
                chunk = resp.read(65536)
                if not chunk:
                    break
                f.write(chunk)
                read += len(chunk)
                if progress and total:
                    progress(min(1.0, read / total))
        if expected_size and part.stat().st_size != expected_size:
            raise RuntimeError("downloaded update has an unexpected size")
        os.replace(part, dest)
    except BaseException:
        # Cancel, network error, or size mismatch: don't leave a partial file.
        part.unlink(missing_ok=True)
        raise
    # Keep the cache to just this installer (prune older downloads/leftovers).
    for old in dest.parent.iterdir():
        if old != dest and old.is_file():
            try:
                old.unlink()
            except OSError:
                pass
    return dest


def launch_installer_and_exit(path):
    """Spawn the signed installer for a silent self-update, detached so it
    survives this process exiting. The installer (CloseApplications=yes) closes
    the running AskPet, installs over it, and relaunches it (Check: WizardSilent).
    """
    flags = (getattr(subprocess, "DETACHED_PROCESS", 0)
             | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
    subprocess.Popen([str(path), "/VERYSILENT", "/NORESTART"],
                     close_fds=True, creationflags=flags)


# ---------------------------------------------------------------------------
# Local AI (Ollama): the pet can answer light asks itself — rewrites,
# summaries, email drafts, quick questions — fully offline via a local
# model like Gemma. Optional: everything degrades to prompt-building when
# Ollama isn't running. Stdlib only, same as the rest of the app.
# ---------------------------------------------------------------------------

OLLAMA_BASE = "http://localhost:11434"


def ollama_models(timeout: int = 3) -> list:
    """Names of locally installed Ollama models; [] if Ollama isn't up."""
    try:
        data = json.loads(_http_get(f"{OLLAMA_BASE}/api/tags", timeout=timeout))
        return [m["name"] for m in data.get("models", [])]
    except (urllib.error.URLError, OSError, ValueError, KeyError):
        return []


def pick_local_model(models: list, preferred: str = None) -> str:
    """The user's saved choice if still installed, else prefer Gemma."""
    if preferred and preferred in models:
        return preferred
    for m in models:
        if m.lower().startswith("gemma"):
            return m
    return models[0] if models else ""


# Sampling presets for the local model. Small models (gemma3:4b included)
# silently truncate when the prompt outgrows the context window, so num_ctx is
# set explicitly to leave room for the persona prompt + remembered facts +
# recent turns. The persona/chat lane samples livelier (closer to Gemma's
# recommended temp/top_p/top_k) so the pet has personality; the editing and
# grounded lanes stay low-temp so they don't invent or drift from the source.
LOCAL_AI_BASE_OPTIONS = {"num_ctx": 8192, "repeat_penalty": 1.1}
LOCAL_AI_EDIT_OPTIONS = {**LOCAL_AI_BASE_OPTIONS, "temperature": 0.3, "num_predict": 600}
LOCAL_AI_CHAT_OPTIONS = {**LOCAL_AI_BASE_OPTIONS, "temperature": 0.8,
                         "top_p": 0.95, "top_k": 64, "num_predict": 400}


def local_ai_options(lane: str) -> dict:
    """Sampling options for a lane: livelier for the persona/general-chat lane
    ('answer'), faithful low-temp for the editing/grounded lanes."""
    return LOCAL_AI_CHAT_OPTIONS if lane == "answer" else LOCAL_AI_EDIT_OPTIONS


def ollama_chat_stream(model: str, system: str, user: str, on_chunk,
                       timeout: int = 300, cancel: "threading.Event" = None,
                       history: list = None, options: dict = None) -> str:
    """Stream a chat response; on_chunk(text) fires per token batch.

    `history` (optional) is a list of prior {role, content} turns inserted
    between the system prompt and the current user message — short-term
    conversation memory for the general-chat lane.

    Generous timeout: the first call after idle loads the model into
    memory. keep_alive holds it warm for subsequent asks. Setting the
    cancel event aborts the read; leaving the with-block closes the
    connection, which makes Ollama stop generating server-side.
    """
    messages = [{"role": "system", "content": system}]
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": user})
    body = json.dumps({
        "model": model,
        "messages": messages,
        "stream": True,
        "keep_alive": "30m",
        # Per-lane sampling (see local_ai_options); defaults to the faithful
        # editing preset so existing callers keep low-temp behavior — now with
        # num_ctx set so long prompts aren't silently truncated.
        "options": options or LOCAL_AI_EDIT_OPTIONS,
    }).encode("utf-8")
    req = urllib.request.Request(OLLAMA_BASE + "/api/chat", data=body,
                                 headers={"Content-Type": "application/json"})
    parts = []
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        for line in resp:
            if cancel is not None and cancel.is_set():
                raise RuntimeError("cancelled")
            d = json.loads(line)
            if d.get("error"):
                raise RuntimeError(d["error"])
            piece = d.get("message", {}).get("content", "")
            if piece:
                parts.append(piece)
                on_chunk(piece)
            if d.get("done"):
                break
    return "".join(parts)


LOCAL_AI_LANES = {
    "rewrite": (
        "You are a precise writing editor. Rewrite the user's text as "
        "requested (clearer, more professional, shorter — whatever they "
        "ask). Hard rules: every name, number, date, time, and amount "
        "from the original appears in the rewrite unchanged; never add "
        "facts, reasons, or details that are not in the original; keep "
        "the original intent exactly. Reply with ONLY the rewritten "
        "text — no preamble, no options, no commentary."
    ),
    "email": (
        "You draft workplace emails. Your reply ALWAYS starts with "
        "'Subject: ' on the first line, then a blank line, then the "
        "body. The point goes in the first sentence, one clear ask, "
        "under 150 words, professional but warm. Keep every name, "
        "date, time, and amount the user gave exactly. Reply with ONLY "
        "the email — no commentary."
    ),
    "summarize": (
        "You summarize text. Lead with the single key point in one "
        "sentence, then at most 5 short bullets of essentials. Preserve "
        "names, dates, and numbers exactly. Reply with ONLY the summary."
    ),
    "answer": (
        "You are AskPet's local assistant, a small model running fully "
        "offline on the user's own PC. Help with whatever the user asks — "
        "answer questions, explain, brainstorm, draft, or just chat. Be "
        "direct and concise: a few sentences, short bullets only when "
        "listing. General and how-to questions never need web access or "
        "live data — answer from what you know, and never reply that you "
        "lack access to information. If you are genuinely unsure, say so "
        "plainly rather than guessing. No filler, no preamble."
    ),
    "review": (
        "You are a thoughtful writing reviewer. Review the user's text and "
        "give brief, specific, actionable feedback on clarity, tone, "
        "structure, grammar, and word choice. Lead with one line on what "
        "works, then a short bulleted list of concrete suggestions — quote "
        "the phrase you'd change and show the fix. Don't rewrite the whole "
        "piece unless asked, and never invent facts. Keep it tight."
    ),
    # Knowledge-pack topic matched but retrieval found nothing — still a
    # hobby question, so answer it; "I don't have access to that
    # information" is never the right reply to "whats the best 1s battery".
    "hobby": (
        "You are AskPet's local assistant, a small model running fully "
        "offline on the user's own PC. The user is asking a practical "
        "hobby question. Answer it directly from your general knowledge. "
        "These questions never need live data, web access, or current "
        "prices — never reply that you lack access to information. For "
        "'best X' or buying questions, name two or three well-known "
        "solid options and what makes each good. If you don't actually "
        "recognize a specific product, say so in one short sentence and "
        "give the general guidance that applies — never invent details "
        "about products you don't know. When a safety rule applies "
        "(batteries, soldering, flying), state it. A few sentences, "
        "short bullets only when listing."
    ),
}


# The email lane is for DRAFTING; inbox-triage/management asks should get
# a proper prompt instead of a surprise email draft.
EMAIL_DRAFT_VERBS = ("draft", "write an email", "write a email", "reply",
                     "respond", "decline", "compose", "email asking",
                     "follow up email", "follow-up email", "email to",
                     "email my", "email the", "out of office")


# ---------------------------------------------------------------------------
# Knowledge packs: local transcript collections (built with
# build_knowledge_pack.py) that ground local-AI answers in real source
# material — e.g. an FPV pack from a YouTube channel's videos. Content
# lives only in the user-data dir; creators are credited in answers.
# ---------------------------------------------------------------------------

_KNOWLEDGE_PACKS = None
KNOWLEDGE_STOPWORDS = set(
    """the a an and or of to in on for with is are was were be been being it
    its this that these those what which how why when where who whats i im
    you your my me we our do does did can could should would will about any
    have has had get got like just really very there here they them their
    not no yes if then than but so at by as from out up down all some más
    one two going want know think make made need say said see going gonna
    """.split()
)


def knowledge_packs() -> list:
    """Load all installed knowledge packs once; [] when none exist."""
    global _KNOWLEDGE_PACKS
    if _KNOWLEDGE_PACKS is None:
        packs = []
        try:
            for d in sorted(KNOWLEDGE_DIR.iterdir()):
                meta = load_json(d / "pack.json", None)
                chunks = load_json(d / "chunks.json", None)
                if meta and chunks and meta.get("keywords"):
                    meta["chunks"] = chunks
                    packs.append(meta)
        except OSError:
            pass
        _KNOWLEDGE_PACKS = packs
    return _KNOWLEDGE_PACKS


def _unit_split(text: str) -> str:
    """"500mah battery" -> "500 mah battery", so unit-glued tokens match
    keywords and chunk text written either way."""
    return re.sub(r"(\d)([a-z])", r"\1 \2", text)


def knowledge_packs_for(text: str) -> list:
    """All packs whose keywords match the message — packs stack."""
    lw = text.lower()
    lwn = _unit_split(lw)
    return [p for p in knowledge_packs()
            if any(re.search(r"\b" + re.escape(k.lower()), lw)
                   or re.search(r"\b" + re.escape(k.lower()), lwn)
                   for k in p["keywords"])]


def knowledge_pack_for(text: str):
    """The first matching pack, else None (for yes/no callers)."""
    packs = knowledge_packs_for(text)
    return packs[0] if packs else None


def _pack_index(pack: dict):
    """Lazy per-pack search index: lowercase chunk text + word idf."""
    if "_xl" not in pack:
        pack["_xl"] = [c["x"].lower() for c in pack["chunks"]]
        df = {}
        for xl in pack["_xl"]:
            for w in set(re.findall(r"[a-z0-9]+", xl)):
                df[w] = df.get(w, 0) + 1
        n = max(1, len(pack["_xl"]))
        pack["_idf"] = {w: math.log(n / (1 + c)) + 1 for w, c in df.items()}
    return pack


def _query_words(query: str) -> list:
    """Search terms from a query, in both raw and unit-split forms so
    "500mah" finds chunks that say "500 mah" and vice versa. Two-char
    tokens only count when they carry a digit ("1s", "2s", "o4")."""
    lq = query.lower()
    toks = set(re.findall(r"[a-z0-9]+", lq))
    toks |= set(re.findall(r"[a-z0-9]+", _unit_split(lq)))
    return sorted(w for w in toks
                  if w not in KNOWLEDGE_STOPWORDS
                  and (len(w) > 2 or (len(w) == 2
                                      and any(c.isdigit() for c in w))))


def _knowledge_scored(pack: dict, query: str) -> list:
    """Floor-filtered (score, chunk) pairs for a query, best first:
    term frequency × rarity, stdlib only."""
    _pack_index(pack)
    words = _query_words(query)
    if not words:
        return []
    scored = []
    for i, xl in enumerate(pack["_xl"]):
        s, distinct = 0.0, 0
        for w in words:
            # singular/plural tolerant: "motors" matches "motor" and back
            # (alpha words only — stripping "1s" to "1" would count every
            # digit 1 in the chunk as a hit)
            hits = xl.count(w)
            alt = w[:-1] if w.endswith("s") and len(w) > 3 else w + "s"
            hits += xl.count(alt)
            if hits:
                distinct += 1
                s += min(hits, 3) * max(pack["_idf"].get(w, 1.0),
                                        pack["_idf"].get(alt, 0))
        # Relevance floor: a single shared word isn't grounding for a real
        # question — better to fall back to the plain answer lane than to
        # quote something irrelevant at the model.
        need = 2 if len(words) >= 3 else 1
        if s > 0 and distinct >= need:
            scored.append((s, pack["chunks"][i]))
    scored.sort(key=lambda t: -t[0])
    if not scored:
        return []
    floor = scored[0][0] * 0.3
    return [(s, c) for s, c in scored if s >= floor]


def knowledge_retrieve(pack: dict, query: str, k: int = 4) -> list:
    """Top-k chunks for a query from one pack."""
    return [c for s, c in _knowledge_scored(pack, query)[:k]]


def knowledge_system_prompt(packs, query: str):
    """Grounded system prompt for the answer lane, or None when nothing
    relevant is found. Accepts one pack or a list — packs stack: chunks
    merge across packs, scores normalized to each pack's best hit so
    pack-local idf scales stay comparable."""
    if isinstance(packs, dict):
        packs = [packs]
    merged = []
    for p in packs:
        scored = _knowledge_scored(p, query)
        if scored:
            top = scored[0][0]
            merged += [(s / top, c, p) for s, c in scored]
    if not merged:
        return None
    merged.sort(key=lambda t: -t[0])
    merged = merged[:4]
    credits, parts = [], []
    for _, c, p in merged:
        if p["credit"] not in credits:
            credits.append(p["credit"])
        parts.append(f"[from: {c['t']}]\n{c['x']}")
    excerpts = "\n\n".join(parts)
    return (
        "You are AskPet's local assistant running fully offline. "
        "Answer the user's question using the source excerpts below — "
        f"from {'; '.join(credits)} — as your primary reference. "
        "Prefer what the sources say over your own general knowledge; "
        "if the excerpts don't cover the question, give your best "
        "general answer labeled as such. Never reply that you lack "
        "access to information. Mention which source the information "
        "comes from when relevant. Be concise: a few sentences or "
        "short bullets.\n\n"
        "=== SOURCE EXCERPTS ===\n" + excerpts
    )


# Instruction openers that unambiguously mean "edit this text" — they get
# the rewrite lane even when the payload's words trip execution signals
# ("fix the grammar: ... send me the report" must not score as a fix task).
REWRITE_OPENERS = ("rewrite", "reword", "proofread", "shorten this",
                   "fix the grammar", "fix my grammar", "fix the spelling",
                   "fix this sentence", "make this", "tighten this",
                   "polish this", "edit this")


# Statement-shaped questions: "i have a 500mah battery, how do i charge"
# carries no "?" and doesn't START with a question word, but the question
# is right there mid-sentence. QUESTION_STARTERS misses these.
EMBEDDED_QUESTION = re.compile(
    r"\b(how (do|can|should|long|often|much) i\b|how to\b|"
    r"what should i\b|what('s| is)? the best\b|should i\b|"
    r"do i need\b|can i\b|why (does|is|do|won'?t|wont|am i)\b|"
    r"is it (ok|okay|safe|normal|worth|bad)\b|"
    r"which \w+ (should|do) i\b)")


def persona_system_prompt(pet) -> str:
    """In-character system prompt for the general-chat ('answer') lane, built
    from the CURRENTLY LOADED pet — so the personality changes with the pet
    (Godzilla Blue answers as a friendly kaiju; a corgi answers as a corgi).
    Silly/personal questions get fun in-character answers; real questions are
    still answered helpfully, in the pet's voice. Kid-safe by construction."""
    name = pet.pet_name()
    meta = pet.pet_meta or {}
    desc = (meta.get("description") or "").strip()
    bio = f" Here's you in a nutshell: {desc}" if desc else ""
    # Long-term memory: facts the person asked you to remember, woven in so the
    # pet recalls names/favorites across sessions.
    mem = load_pet_memory()
    memblock = ("\nThings you remember about the person you're chatting with "
                "(use them naturally when they're relevant, don't just recite "
                "them): " + "; ".join(mem) + ".") if mem else ""
    return (
        f"You ARE {name}, a friendly desktop pet who lives on the user's "
        f"computer and loves to chat — often with kids.{bio}{memblock}\n"
        f"Stay fully in character as {name}: speak in the first person with a "
        f"warm, playful, gentle personality that fits your name and how you "
        f"look. For silly or personal questions — favorite food, color, games, "
        f"how your day is going — make up a fun, imaginative in-character "
        f"answer; never say you don't have preferences. For real questions, "
        f"still answer helpfully, just in your own voice. Keep replies short, "
        f"cheerful, and family-friendly (G-rated) — never scary, mean, or "
        f"violent, even if your character could be. Never say you are an AI, a "
        f"model, or a program; you are {name}. No disclaimers, no preamble."
    )


def local_ai_lane(raw: str, rec: dict):
    """Which local-AI lane should answer this message. General chat ("answer")
    is the DEFAULT; specialized lanes (rewrite/summarize/review/email/knowledge)
    win when the message clearly calls for them. Pure routing — it checks
    nothing about whether a model is actually available; when none is, the
    caller falls back to the prompt builder instead. Prompt-building itself is
    no longer a default — it's reached explicitly via /fix-prompt."""
    lw = raw.strip().lower()
    # Rewrite/summarize/review need the actual text in the message; a bare
    # "summarize this" still works (it just gets a general reply asking for it).
    has_payload = len(lw.split()) > 12 or ":" in raw or "\n" in raw
    instruction = lw.split(":", 1)[0] if ":" in lw else lw
    if has_payload and any(instruction.startswith(v) or f" {v}" in instruction
                           for v in REWRITE_OPENERS):
        return "rewrite"
    # Same bypass for summaries: the CONTENT being summarized ("the
    # migration", "the server…") must not disqualify summarizing it.
    if has_payload and any(v in instruction for v in
                           ("summarize", "summarise", "key points", "tldr",
                            "tl;dr")):
        return "summarize"
    # Writing review: "review this …", "critique …", "feedback on …". Must
    # START with the review verb so a task that merely mentions it (e.g.
    # "email asking for feedback on my proposal") isn't hijacked to review.
    if has_payload and instruction.startswith(
            ("review", "critique", "feedback on", "feedback for")):
        return "review"
    # Knowledge-pack questions (e.g. FPV) answer from the pack.
    question_shaped = (lw.endswith("?") or lw.startswith(QUESTION_STARTERS)
                       or bool(EMBEDDED_QUESTION.search(lw)))
    if (question_shaped or len(lw.split()) <= 14) and knowledge_pack_for(lw):
        return "knowledge"
    # Email drafting: "write an email asking the landlord to fix the AC"
    # is an email no matter what the email is about.
    first_words = lw.split()[:5]
    if (first_words and first_words[0] in ("write", "draft", "compose", "send")
            and any("email" in w for w in first_words)):
        return "email"
    topics = set(rec["topics"])
    if "email_drafting" in topics and any(v in lw for v in EMAIL_DRAFT_VERBS):
        return "email"
    if "summarize" in topics and has_payload:
        return "summarize"
    if "writing" in topics and has_payload:
        return "rewrite"
    # Everything else is general chat — the new default.
    return "answer"


# ---------------------------------------------------------------------------
# DeckSide live data: when the user runs DeckSide (a local Electron swim
# meet-day app) alongside AskPet, the pet can answer meet-day questions —
# "when is the next meet?", "how many swimmers?" — by querying DeckSide's
# loopback "agent server" over HTTP. READ-ONLY: AskPet only ever calls
# DeckSide's deterministic assistant_chat tool, never a propose/write tool,
# so it can never change a lineup or scratch a swimmer. DeckSide does all
# the data resolution and hands back an authoritative answer string, which
# the pet shows verbatim — no local model in the loop, so numbers and names
# are never paraphrased away. Everything degrades to prompt-building when
# DeckSide isn't running. Stdlib only, same as the rest of the app.
# ---------------------------------------------------------------------------

DECKSIDE_DEFAULT_PORT = "41973"

# Swim meet-day vocabulary that marks a LIVE DATA question. Terms are chosen
# to not collide with the app's other domains: bare "freestyle"/"free"/"fly"
# are NOT signals (FPV freestyle drones) — strokes only count with a distance
# in front ("50 free", "100 im") or as swim-only words (backstroke/medley);
# "event" only counts with a number or a swim-context qualifier (not "event
# log"); "(next/the) meet" with a boundary so "meeting" can't match. A bare
# "relay" can also mean an SMTP relay, but a stray hit only costs one HTTP
# call before falling back to prompt-building, so the floor is cheap.
DECKSIDE_DATA_SIGNALS = re.compile(
    r"\bdeckside\b|\bswim(?:mer|mers|ming|s)?\b|\bswim meet\b|"
    r"\b(?:next|last|the|this|that) meet\b|\bmeet (?:results|schedule|lineup|day)\b|"
    r"\brelay(?:s)?\b|\blineup(?:s)?\b|\bline up\b|\bscratch(?:ed|es)?\b|"
    r"\bseed time(?:s)?\b|\bheat\b|\bchamps\b|\b(?:dual|tri)[- ]meet\b|"
    r"\bbackstroke\b|\bbreaststroke\b|\bbutterfly\b|\bmedley\b|"
    r"\b\d{2,4}\s?(?:free|freestyle|fly|back|breast|im|medley)\b|"
    r"\bevent\s*#?\s*\d+\b|\bwhat events?\b|\bwhich events?\b|"
    r"\bevents? (?:is|are|for|left|does|do)\b|"
    r"\b(?:any|his|her|their|my) events?\b|"
    r"\bage (?:band|group)\b|\bteam (?:roster|score|scores)\b|"
    r"\bchecked in\b|\bcheck[- ]?in\b")

# Schedule/season questions are DeckSide data too, but only when they also
# name meets/swimming — so IT's "scheduled task" or "schedule a meeting"
# (note: "meeting" never matches \bmeets?\b) can't trip the lane.
DECKSIDE_SCHEDULE_SIGNALS = re.compile(r"\b(?:schedule|season|calendar)\b")
DECKSIDE_MEET_NOUN = re.compile(r"\bmeets?\b|\bswim")

# A DeckSide *development* task ("build a check-in tab", "fix the parser")
# is NOT a data question — it keeps flowing to the prompt builder.
DECKSIDE_DEV_SIGNALS = re.compile(
    r"\b(?:build|implement|ship|code|coding|refactor|debug|compile|"
    r"feature|parser|architecture|ipc|electron|backlog|agents\.md|"
    r"unit test|migration|schema|endpoint|component|module|repo|"
    r"commit|pull request|\bpr\b)\b")

# IT phrasings that share a word with swim vocabulary ("relay", "event").
# These win over the swim signals so an IT ask is never sent to DeckSide.
DECKSIDE_IT_COLLISION = re.compile(
    r"\b(?:smtp|mail relay|relay server|relay agent|audit log|event log|"
    r"event viewer|event id|calendar event|event hub|event grid)\b")

# Data questions/requests can open with words QUESTION_STARTERS misses —
# yes/no openers and imperatives ("check on...", "look up..."). These are
# only consulted AFTER a swim signal has already matched, so a generic "is
# the server down" (no signal) never reaches them.
DECKSIDE_DATA_STARTERS = ("who ", "list ", "show ", "how many ", "how's ",
                          "hows ", "is ", "are ", "was ", "were ", "did ",
                          "does ", "do ", "has ", "have ", "can ", "will ",
                          "check ", "tell me", "look up", "lookup ", "find ",
                          "pull up", "look at ", "get ", "give me")


def deckside_data_lane(raw: str) -> bool:
    """True when this is a live meet-data question to hand to a running
    DeckSide, as opposed to a DeckSide dev task or an unrelated ask. Pure —
    does no I/O and doesn't check whether DeckSide is actually up."""
    lw = raw.strip().lower()
    if DECKSIDE_DEV_SIGNALS.search(lw) or DECKSIDE_IT_COLLISION.search(lw):
        return False
    hit = bool(DECKSIDE_DATA_SIGNALS.search(lw)) or bool(
        DECKSIDE_SCHEDULE_SIGNALS.search(lw) and DECKSIDE_MEET_NOUN.search(lw))
    if not hit:
        return False
    return (lw.endswith("?") or lw.startswith(QUESTION_STARTERS)
            or lw.startswith(DECKSIDE_DATA_STARTERS)
            or bool(EMBEDDED_QUESTION.search(lw)))


def deckside_base() -> str:
    """Loopback base URL for DeckSide's agent server (honors its env var)."""
    port = os.environ.get("DECKSIDE_AGENT_PORT", "").strip() or DECKSIDE_DEFAULT_PORT
    return f"http://127.0.0.1:{port}"


def deckside_health(timeout: int = 2):
    """DeckSide's version string if its agent server answers, else None."""
    try:
        data = json.loads(_http_get(deckside_base() + "/agent/health", timeout))
    except (urllib.error.URLError, OSError, ValueError):
        return None
    return data.get("version") if isinstance(data, dict) and data.get("ok") else None


def deckside_ask(question: str, timeout: int = 20):
    """Ask a running DeckSide a meet-data question. Returns (answer, None)
    on success or (None, reason) where reason is 'offline' (unreachable),
    'error' (server said no), or 'no-answer' (DeckSide had nothing). Only
    calls assistant_chat — read-only, never a propose/write tool."""
    body = json.dumps({"name": "assistant_chat",
                       "arguments": {"message": question}}).encode("utf-8")
    req = urllib.request.Request(deckside_base() + "/agent/tools/call",
                                 data=body,
                                 headers={"content-type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read())
    except (urllib.error.URLError, OSError, ValueError):
        return None, "offline"
    if not isinstance(data, dict) or not data.get("ok"):
        return None, "error"
    answer = (data.get("finalAnswer") or "").strip()
    # DeckSide's generic miss sentinel reads badly in chat; treat it as no
    # answer (but keep its *helpful* misses like "import the file first").
    if not answer or answer.lower().startswith("no deterministic deckside answer"):
        return None, "no-answer"
    return answer, None


# --- DeckSide roster: swimmer @-mentions ---------------------------------------
# The chat box completes real swimmer names from a running DeckSide via the
# read-only get_roster tool. Mentions are EXPLICIT: the menu opens only when
# the caret is in an "@..." token ("is @mab"), so it never fires on the wrong
# word. Matching is exact-prefix (no fuzzy) because the master roster is ~2000
# names, where a fuzzy near-miss would hit for almost any letter pair.

_ROSTER_CACHE = {"names": [], "fetched": 0.0, "ver": None}
_ROSTER_LOCK = threading.Lock()  # serializes cache reads/writes across primes
_ROSTER_TTL = 300.0  # seconds; also re-fetched when DeckSide's version changes


def deckside_roster(timeout: int = 4, force: bool = False) -> list:
    """Flat, sorted, de-duplicated list of roster display names ("First Last")
    from a running DeckSide, cached. Returns [] (never raises) when DeckSide is
    offline or has no roster. NOT for the keystroke path — it makes HTTP calls;
    call it on a worker thread and read the cache on the hot path."""
    ver = deckside_health(timeout=2)  # reachability gate + cache key
    if ver is None:
        return []
    now = time.monotonic()
    with _ROSTER_LOCK:
        if (_ROSTER_CACHE["names"] and not force
                and _ROSTER_CACHE["ver"] == ver
                and now - _ROSTER_CACHE["fetched"] < _ROSTER_TTL):
            return _ROSTER_CACHE["names"]
    # The HTTP fetch runs OUTSIDE the lock (never hold a lock across I/O);
    # concurrent primes just both fetch and the cache write is serialized.
    body = json.dumps({"name": "get_roster", "arguments": {}}).encode("utf-8")
    req = urllib.request.Request(deckside_base() + "/agent/tools/call",
                                 data=body,
                                 headers={"content-type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read())
    except (urllib.error.URLError, OSError, ValueError):
        with _ROSTER_LOCK:
            return _ROSTER_CACHE["names"]  # keep last-good on a transient failure
    roster = (((data or {}).get("data") or {}).get("roster")) or []
    names = sorted({roster_flip_name(r.get("fullName") or "")
                    for r in roster if isinstance(r, dict) and r.get("fullName")})
    with _ROSTER_LOCK:
        _ROSTER_CACHE.update(names=names, fetched=now, ver=ver)
    return names


def roster_flip_name(raw: str) -> str:
    """"Smith, Jane" -> "Jane Smith"; pass through names without a comma."""
    s = (raw or "").strip()
    i = s.find(",")
    return f"{s[i + 1:].strip()} {s[:i].strip()}" if i > 0 else s


def _roster_norm(v: str) -> str:
    v = re.sub(r"[^a-z0-9\s]", " ", (v or "").lower())
    return re.sub(r"\s+", " ", v).strip()


# Swimmer mentions are EXPLICIT: the name menu opens only when the caret is in
# an "@..." token (after a space or at the start of the message), e.g. "is
# @mab". This replaced the old guess-when-you-mean-a-name heuristic — no more
# predicting on the wrong word. "email@host" never triggers (its @ isn't
# space-preceded).
_MENTION_RE = re.compile(r"(?:^|\s)@([A-Za-z][A-Za-z.'-]*)?$")


def mention_fragment(before: str):
    """The text after the '@' the caret is currently inside ("is @mab" ->
    "mab", "is @" -> ""), or None when the caret isn't in an @-mention."""
    m = _MENTION_RE.search(before or "")
    if not m:
        return None
    return m.group(1) or ""


def roster_prefix_matches(names: list, word: str, limit: int = 8,
                          min_len: int = 2) -> list:
    """Names whose first (x3) or any (x2) token EXACTLY starts with the typed
    word. Exact-prefix only — against the large master roster a fuzzy match
    would surface a hit for almost any letter pair."""
    w = _roster_norm(word)
    if len(w) < min_len:
        return []
    scored = []
    for display in (names or []):
        toks = [t for t in _roster_norm(display).split(" ") if t]
        if not toks:
            continue
        if toks[0].startswith(w):
            score = 3.0
        elif any(t.startswith(w) for t in toks[1:]):
            score = 2.0
        else:
            continue
        scored.append((score, display))
    scored.sort(key=lambda t: (-t[0], t[1]))
    return [d for _, d in scored[:max(1, limit)]]


class CompletionMenu:
    """A borderless dropdown of selectable strings anchored under a Text
    entry's caret. Shared by the slash-command palette and the @-mention menu.
    The entry keeps focus throughout (the menu never steals it); the owner
    drives it with show()/hide()/move() and is handed the chosen item via the
    on_select callback (also fired on a mouse click)."""

    def __init__(self, entry, on_select):
        self.entry = entry
        self.on_select = on_select
        self._win = None
        self._list = None
        self._hide_after = None

    def visible(self) -> bool:
        return bool(self._win and self._win.winfo_exists()
                    and self._win.winfo_ismapped())

    def _build(self):
        self._win = tk.Toplevel(self.entry)
        self._win.wm_overrideredirect(True)
        self._win.wm_attributes("-topmost", True)
        self._win.withdraw()
        self._list = tk.Listbox(self._win, height=6, font=("Segoe UI", 9),
                                activestyle="none", selectmode="single",
                                exportselection=False, bd=1, relief="solid",
                                highlightthickness=0)
        self._list.pack(fill="both", expand=True)
        self._list.bind("<ButtonRelease-1>", self._on_click)

    def show(self, items):
        if not items:
            return self.hide()
        if self._win is None:
            self._build()
        self._list.delete(0, "end")
        for it in items:
            self._list.insert("end", it)
        self._list.selection_clear(0, "end")
        self._list.selection_set(0)
        self._list.activate(0)
        self._list.config(height=min(len(items), 8))
        # Width the box to its content so "/command   description" isn't
        # cramped (the Listbox otherwise defaults to ~20 chars). Capped so a
        # long description can't run off-screen; @-mention names stay compact.
        longest = max((len(str(it)) for it in items), default=20)
        self._list.config(width=min(72, longest + 2))
        # Open UPWARD by default: the chat input sits at the bottom of the
        # window, so a downward menu gets clipped off-screen. Needs the menu's
        # real height, so flush layout once (cheap; only when showing).
        self._win.update_idletasks()
        x = self.entry.winfo_rootx()
        h = self._win.winfo_reqheight()
        top = self.entry.winfo_rooty()
        y = top - h - 1
        if y < 0:  # no room above (window near the top) -> fall back below
            y = top + self.entry.winfo_height() + 1
        self._win.wm_geometry(f"+{x}+{y}")
        self._win.deiconify()
        self._win.lift()
        return None

    def hide(self, *_):
        self._hide_after = None
        if self._win is not None and self._win.winfo_exists():
            self._win.withdraw()
        return None

    def move(self, delta):
        size = self._list.size() if self._list else 0
        if not size:
            return
        cur = self._list.curselection()
        i = max(0, min(size - 1, (cur[0] if cur else 0) + delta))
        self._list.selection_clear(0, "end")
        self._list.selection_set(i)
        self._list.activate(i)
        self._list.see(i)

    def current(self):
        sel = self._list.curselection() if self._list else ()
        return self._list.get(sel[0]) if sel else None

    def accept(self) -> bool:
        """Fire on_select for the highlighted item; True if one was chosen.
        The entry is refocused so a mouse-click accept doesn't strand the
        caret in the list."""
        item = self.current()
        if item is None:
            self.hide()
            return False
        self.hide()
        self.on_select(item)
        self.entry.focus_set()
        return True

    def _on_click(self, event):
        idx = self._list.nearest(event.y)
        if idx >= 0:
            self._list.selection_clear(0, "end")
            self._list.selection_set(idx)
            self.accept()
        return "break"

    def schedule_hide(self):
        # A click on the list steals focus from the entry; defer the hide so
        # the list's ButtonRelease (which accepts) runs first.
        if self._hide_after:
            try:
                self.entry.after_cancel(self._hide_after)
            except Exception:
                pass
        self._hide_after = self.entry.after(150, self.hide)


# Slash commands: explicit, discoverable ways to invoke a lane, like the
# command palettes in ChatGPT/Claude. Each maps to a capability that already
# exists, so dispatch just FORCES the lane instead of guessing it. Tuple is
# (name, description, action) where action is a local-AI lane, "prompt" (the
# IT prompt builder), or "help".
SLASH_COMMANDS = [
    ("/rewrite", "Rewrite text — clearer, shorter, or more professional", "rewrite"),
    ("/summarize", "Summarize text into the key points", "summarize"),
    ("/review", "Review writing and suggest improvements", "review"),
    ("/email", "Draft a workplace email", "email"),
    ("/ask", "Answer a quick question, locally", "answer"),
    ("/fix-prompt", "Build a best-practice prompt for an AI/IT task", "prompt"),
    ("/games", "See the games we can play", "games"),
    ("/play", "Start a game — e.g. /play hangman", "play"),
    ("/eldermark", "Walk the world of Eldermark (pixel adventure)", "eldermark"),
    ("/help", "Show what AskPet can do", "help"),
]
SLASH_BY_NAME = {name[1:]: (desc, action) for name, desc, action in SLASH_COMMANDS}
# Back-compat alias: /prompt still routes to the prompt builder (now /fix-prompt).
SLASH_BY_NAME["prompt"] = SLASH_BY_NAME["fix-prompt"]


def parse_slash(raw: str):
    """(command, argument) when a message opens with a /command, else None.
    Command names allow underscores/digits so library templates work too:
    "/incident_rca email is down" -> ("incident_rca", "email is down")."""
    m = re.match(r"\s*/([a-zA-Z][a-zA-Z0-9_-]*)[ \t]*(.*)$", raw or "", re.S)
    if not m:
        return None
    return m.group(1).lower(), m.group(2).strip()


# Keys that move/commit within a dropdown rather than edit text — a keystroke
# handler ignores them so it doesn't re-filter on arrow/Tab/etc.
_MENU_NAV_KEYS = ("Up", "Down", "Left", "Right", "Return", "Tab", "Escape",
                  "Shift_L", "Shift_R", "Control_L", "Control_R", "Alt_L", "Alt_R")


class RosterTypeahead:
    """Swimmer-name autocomplete for the chat box, sourced live from a running
    DeckSide (read-only get_roster). A complete no-op when DeckSide is closed
    or has no roster — the keystroke path only reads an in-memory list; all
    HTTP happens on a worker thread."""

    REPRIME_EVERY = 8.0  # seconds; lets a DeckSide opened mid-session appear

    def __init__(self, chat):
        self.chat = chat
        self.entry = chat.entry
        self._names = []
        self._priming = False
        self._last_prime = 0.0
        self.menu = CompletionMenu(self.entry, self._accept_name)
        self._prime()  # warm the cache off-thread so the first keystroke is fast
        # add="+" is MANDATORY: a bare bind would replace SpellSupport's
        # KeyRelease handler and silently kill spell-check.
        self.entry.bind("<KeyRelease>", self._on_key, add="+")
        self.entry.bind("<FocusOut>", lambda e: self.menu.schedule_hide(), add="+")
        for seq in ("<Up>", "<Down>", "<Tab>", "<Escape>"):
            self.entry.bind(seq, self._on_nav, add="+")
        chat.win.bind("<Configure>", lambda e: self.menu.hide(), add="+")

    def _prime(self):
        if self._priming:
            return
        self._priming = True
        self._last_prime = time.monotonic()

        def work():
            try:
                names = deckside_roster()
            except Exception:
                names = []
            self._priming = False
            if names:
                self._names = names

        threading.Thread(target=work, daemon=True).start()

    def _maybe_reprime(self):
        if (not self._names and not self._priming
                and time.monotonic() - self._last_prime > self.REPRIME_EVERY):
            self._prime()

    def _on_key(self, event):
        if event.keysym in _MENU_NAV_KEYS:
            return None
        if self.chat._placeholder_on:  # don't match the fake placeholder text
            return self.menu.hide()
        frag = mention_fragment(self.entry.get("1.0", "insert"))
        if frag is None:  # the caret isn't inside an @-mention
            return self.menu.hide()
        if not self._names:
            self._maybe_reprime()
            return self.menu.hide()
        # Bare "@" shows the start of the roster; "@ab" filters by prefix.
        items = (self._names[:8] if not frag
                 else roster_prefix_matches(self._names, frag, 8, min_len=1))
        return self.menu.show(items)

    def _on_nav(self, event):
        if not self.menu.visible():
            return None
        if event.keysym == "Escape":
            self.menu.hide()
            return "break"
        if event.keysym == "Up":
            self.menu.move(-1)
            return "break"
        if event.keysym == "Down":
            self.menu.move(1)
            return "break"
        if event.keysym == "Tab":
            # Only swallow Tab if a name was actually completed.
            return "break" if self.menu.accept() else None
        return None

    def _accept_name(self, display):
        # Replace the typed "@frag" with "@Full Name " — keeps the @ so it
        # reads as a mention (and Phase 3 can resolve it for DeckSide).
        before = self.entry.get("1.0", "insert")
        m = re.search(r"@[A-Za-z.'-]*$", before)
        if m:
            self.entry.delete(f"insert - {len(m.group(0))} chars", "insert")
        self.entry.insert("insert", "@" + display + " ")


class SlashCommands:
    """The '/' command palette. Opens when the line starts with '/', filters
    SLASH_COMMANDS as you type, and inserts the chosen command. Execution
    happens on send (parse_slash + the chat's slash dispatcher)."""

    def __init__(self, chat):
        self.chat = chat
        self.entry = chat.entry
        self.menu = CompletionMenu(self.entry, self._accept)
        self.entry.bind("<KeyRelease>", self._on_key, add="+")
        self.entry.bind("<FocusOut>", lambda e: self.menu.schedule_hide(), add="+")
        for seq in ("<Up>", "<Down>", "<Tab>", "<Escape>"):
            self.entry.bind(seq, self._on_nav, add="+")
        chat.win.bind("<Configure>", lambda e: self.menu.hide(), add="+")

    def _typed(self):
        """The leading '/word' being typed (caret still inside it), else None."""
        before = self.entry.get("1.0", "insert")
        m = re.match(r"\s*(/[a-zA-Z0-9_-]*)$", before)
        return m.group(1).lower() if m else None

    def _on_key(self, event):
        if event.keysym in _MENU_NAV_KEYS:
            return None
        if self.chat._placeholder_on:
            return self.menu.hide()
        typed = self._typed()
        if typed is None:
            return self.menu.hide()
        # Core action commands always; library-template commands surface once
        # you've typed at least one letter (so bare "/" stays the short list).
        items = [f"{name}   {desc}" for name, desc, _ in SLASH_COMMANDS
                 if name.startswith(typed)]
        if len(typed) >= 2:
            items += [f"/{key}   {tmpl['name']}"
                      for key, tmpl in sorted(PROMPT_TEMPLATES.items())
                      if ("/" + key).startswith(typed)][:16]
        return self.menu.show(items)

    def _on_nav(self, event):
        if not self.menu.visible():
            return None
        if event.keysym == "Escape":
            self.menu.hide()
            return "break"
        if event.keysym == "Up":
            self.menu.move(-1)
            return "break"
        if event.keysym == "Down":
            self.menu.move(1)
            return "break"
        if event.keysym == "Tab":
            self.menu.accept()
            return "break"
        return None

    def _accept(self, item):
        name = item.split()[0]  # "/rewrite   desc" -> "/rewrite"
        before = self.entry.get("1.0", "insert")
        m = re.search(r"/[a-zA-Z0-9_-]*$", before)
        if m:
            self.entry.delete(f"insert - {len(m.group(0))} chars", "insert")
        self.entry.insert("insert", name + " ")


def search_pets(query: str) -> list:
    """Server-side catalog search (matches name/creator/tags site-wide)."""
    q = urllib.parse.quote(query)
    data = json.loads(_http_get(f"{CODEX_PETS_BASE}/api/pets?q={q}"))
    pets = data.get("pets", data if isinstance(data, list) else [])
    return [p for p in pets if not p.get("ownerShadowbanned")]


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
            "AskPet includes it already.)")

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
    apply_facing_overrides(pet_id, animations)

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


def configure_misspell_tag(widget: tk.Text):
    """Typos get a red underline under normal-colored text (Tk has no wavy
    underline). Red TEXT is reserved for keyword highlights, so the two
    can't be confused."""
    try:
        widget.tag_configure("misspelled", underline=True, underlinefg="#d93025")
    except tk.TclError:  # Tk older than 8.6.6: fall back to red text
        widget.tag_configure("misspelled", underline=True, foreground="#d93025")


class SpellSupport:
    """Attach red-underline spellcheck + right-click suggestions to a tk.Text."""

    def __init__(self, text_widget: tk.Text, spell: SpellHelper):
        self.text = text_widget
        self.spell = spell
        configure_misspell_tag(text_widget)
        text_widget.bind("<KeyRelease>", self._on_key_release, add="+")
        text_widget.bind("<Button-3>", self._on_right_click, add="+")

    def _on_key_release(self, event=None):
        if event and event.keysym in ("Up", "Down", "Left", "Right", "Shift_L", "Shift_R"):
            return
        self.recheck()

    def recheck(self):
        text = self.text.get("1.0", "end-1c")
        self.text.tag_remove("misspelled", "1.0", "end")
        # Keep contractions/possessives as one token so "doesn't" isn't
        # split into doesn + t and flagged.
        for m in re.finditer(r"[A-Za-z]+(?:'[A-Za-z]+)*", text):
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
        self.flipped = {}   # horizontally-mirrored variants (face the other way)
        self.facing = {}    # native facing per animation: +1 right, -1 left
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
        # PIL copy of the sheet for building mirrored frames — Tk's `photo copy`
        # can't flip horizontally. Optional: if PIL is unavailable we just skip
        # the flipped sets and fall back to the un-mirrored frames.
        try:
            from PIL import Image
            pil_sheet = Image.open(sheet_path).convert("RGB")
        except Exception:
            pil_sheet = None
        for name, anim in manifest["animations"].items():
            row, count = anim["row"], anim["frames"]
            # Native facing of the AUTHORED art. Convention: pet sheets are
            # drawn facing RIGHT and the app mirrors them for leftward travel
            # (verified true for the bundled pets — even their walk_left rows
            # face right). A pet whose art faces left declares "facing":"left"
            # per animation in its manifest.
            face = str(anim.get("facing", "right")).lower()
            self.facing[name] = -1 if face.startswith("l") else 1
            frames, flips = [], []
            for col in range(count):
                img = tk.PhotoImage()
                img.tk.call(img, "copy", sheet, "-from",
                            col * cw, row * ch, (col + 1) * cw, (row + 1) * ch,
                            "-to", 0, 0)
                if scale > 1:
                    img = img.subsample(scale, scale)
                frames.append(img)
                if pil_sheet is not None:
                    flips.append(self._mirror_cell(pil_sheet, row, col, cw, ch, scale))
            if frames:
                self.frames[name] = frames
                if flips and all(flips):
                    self.flipped[name] = flips
        self.w, self.h = cw // scale, ch // scale
        self.ok = bool(self.frames)

    @staticmethod
    def _mirror_cell(pil_sheet, row, col, cw, ch, scale):
        """A horizontally-mirrored Tk image for one cell (Tk's photo copy can't
        mirror, so go through PIL). Returns None on any failure."""
        try:
            from PIL import Image
            cell = pil_sheet.crop((col * cw, row * ch, (col + 1) * cw,
                                   (row + 1) * ch)).transpose(Image.FLIP_LEFT_RIGHT)
            if scale > 1:
                cell = cell.resize((cw // scale, ch // scale), Image.NEAREST)
            buf = io.BytesIO()
            cell.save(buf, format="PNG")
            return tk.PhotoImage(data=base64.b64encode(buf.getvalue()).decode("ascii"))
        except Exception:
            return None


class UpdateProgressDialog:
    """Small always-on-top window shown while a self-update downloads/installs.

    Its setters are called on the UI thread (the worker marshals via
    root.after); each guards against the window having been closed.
    """

    def __init__(self, parent, tag, on_cancel=None):
        self.win = tk.Toplevel(parent)
        self.win.title("Updating AskPet")
        self.win.resizable(False, False)
        self.win.wm_attributes("-topmost", True)
        frame = ttk.Frame(self.win, padding=16)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text=f"Updating to AskPet {tag}",
                  font=("Segoe UI", 11, "bold")).pack(anchor="w")
        self._status = ttk.Label(frame, text="Starting…")
        self._status.pack(anchor="w", pady=(6, 6))
        self._bar = ttk.Progressbar(frame, length=320, mode="determinate",
                                    maximum=1.0)
        self._bar.pack(fill="x")
        if on_cancel:
            ttk.Button(frame, text="Cancel",
                       command=on_cancel).pack(anchor="e", pady=(10, 0))
        self.win.update_idletasks()

    def set_status(self, text):
        if self.win.winfo_exists():
            self._status.config(text=text)
            self.win.update_idletasks()

    def set_progress(self, fraction):
        if self.win.winfo_exists():
            self._bar["value"] = fraction
            self.win.update_idletasks()

    def close(self):
        if self.win.winfo_exists():
            self.win.destroy()


class PetOverlay:
    """Kogi the desktop pet: borderless, transparent, always on top.

    Left-click toggles the chat window; drag to move; right-click for menu.
    Wanders/waves on its own while the chat is closed, sits while it is open.
    """

    TICK_MS = 200  # base tick; movement anims advance every tick
    WALK_SPEED = 3
    RUN_SPEED = 7
    NAP_AFTER_TICKS = 18000  # ~1 hour without interaction -> nap (200ms ticks)
    # Frames advance every Nth tick per animation. The sleepy row is a set
    # of distinct poses, not a loop — cycle it VERY slowly or it looks
    # frantic instead of asleep.
    FRAME_HOLD = {"sleepy": 13, "idle": 2, "sit": 2, "emote": 3}

    def __init__(self, root: tk.Tk):
        self.root = root
        self.spell = SpellHelper()
        self.chat = None
        self.editor = None
        self._menu_open = False
        self.settings = load_json(SETTINGS_FILE, {})
        prune_history(history_retention_hours(self.settings))
        ELDER_STATE.load(self.settings)      # restore befriended creatures

        # Local AI: detect installed Ollama models off the UI thread.
        self.local_models = []
        self.local_ai_enabled = bool(self.settings.get("local_ai_enabled", True))
        self._refresh_local_models()

        ensure_default_pet()
        self.scale = max(1, int(self.settings.get("pet_scale", 2)))  # medium default
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
        x0, x1 = self._walk_bounds_for_width(w)
        x = min(max(x0, x), x1)
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
        self.idle_ticks = 0  # ticks since the user last interacted

        # Self-update: quiet check a few seconds after launch (off the UI
        # thread). Populates the right-click menu and nudges once per version.
        self._update_info = None
        self.root.after(4000, lambda: self._check_for_updates_bg(manual=False))

        self._tick()

    # ---- animation engine -------------------------------------------------

    def anim_frames(self):
        if not self.sprites.ok:
            return [None]
        return self.sprites.frames.get(self.anim) or next(iter(self.sprites.frames.values()))

    def _display_frames(self):
        """Frames for the current animation, mirrored when needed so the pet
        faces its direction of travel (move_dx). Falls back to the un-mirrored
        frames when stationary or when no flipped set exists."""
        normal = self.anim_frames()
        d = 1 if self.move_dx > 0 else -1 if self.move_dx < 0 else 0
        if d == 0 or self.sprites.facing.get(self.anim, 1) == d:
            return normal
        return self.sprites.flipped.get(self.anim) or normal

    def set_anim(self, name, move_dx=0, ticks=None):
        if self.sprites.ok and name not in self.sprites.frames:
            name = "idle"
        self.anim = name
        self.frame_i = 0
        self.move_dx = move_dx
        self.behavior_ticks = ticks if ticks is not None else len(self.anim_frames()) * 3

    def _tick(self):
        self._tick_n = getattr(self, "_tick_n", 0) + 1
        frames = self._display_frames()
        if self.sprites.ok:
            frame = frames[self.frame_i % len(frames)]
            self.canvas.itemconfigure(self.sprite_item, image=frame)
        if self._tick_n % self.FRAME_HOLD.get(self.anim, 1) == 0:
            self.frame_i += 1

        if self.move_dx and not self._dragging:
            if self.chat and self.chat.is_open():
                # Never wander while the user is chatting.
                self.move_dx = 0
            else:
                x = self.root.winfo_x() + self.move_dx
                y = self.root.winfo_y()
                x0, x1 = self._walk_bounds()
                if x <= x0 or x >= x1:
                    # Flip once and step INSIDE the bounds so the next tick
                    # can't re-trip the edge check (oscillation guard).
                    self.move_dx = -self.move_dx
                    if self.anim in ("walk_right", "walk_left"):
                        self.set_anim("walk_right" if self.move_dx > 0 else "walk_left",
                                      move_dx=self.move_dx, ticks=self.behavior_ticks)
                    x = min(max(x0 + abs(self.move_dx), x), x1 - abs(self.move_dx))
                self.root.geometry(f"+{x}+{y}")

        self.behavior_ticks -= 1
        self.idle_ticks += 1
        if self.behavior_ticks <= 0 and not self._dragging:
            self._choose_behavior()

        self.root.after(self.TICK_MS, self._tick)

    def _walk_bounds(self):
        return self._walk_bounds_for_width(self.sprites.w)

    def _walk_bounds_for_width(self, w):
        """Min/max x for the pet, spanning all monitors on Windows.

        Using only the primary screen width made the pet oscillate rapidly
        when it sat on a second monitor (every tick looked like an edge hit).
        """
        if sys.platform == "win32":
            try:
                import ctypes
                u = ctypes.windll.user32
                vx = u.GetSystemMetrics(76)   # SM_XVIRTUALSCREEN
                vw = u.GetSystemMetrics(78)   # SM_CXVIRTUALSCREEN
                return vx, vx + vw - w
            except Exception:
                pass
        return 0, self.root.winfo_screenwidth() - w

    def _choose_behavior(self):
        if self.chat and self.chat.is_open():
            # Listening pose while the chat is open.
            self.set_anim("sit", ticks=random.randint(30, 60))
            return
        if self.idle_ticks > self.NAP_AFTER_TICKS:
            # Ignored for a while: nap until the user interacts again.
            self.set_anim("sleepy", ticks=random.randint(60, 120))
            return
        if not self.wander:
            self.set_anim("idle", ticks=random.randint(30, 80))
            return
        roll = random.random()
        if roll < 0.50:
            self.set_anim("idle", ticks=random.randint(40, 100))
        elif roll < 0.72:
            self.set_anim("sit", ticks=random.randint(40, 90))
        elif roll < 0.78:
            self.set_anim("wave", ticks=len(self.sprites.frames.get("wave", [1])) * 2)
        elif roll < 0.84:
            self.set_anim("emote", ticks=random.randint(10, 18))
        elif roll < 0.87:
            # Zoomies! A rare fast dash across the screen.
            direction = random.choice((-1, 1))
            self.set_anim("run", move_dx=direction * self.RUN_SPEED,
                          ticks=random.randint(12, 25))
        elif roll < 0.94:
            # Slow amble — Kogi's signature mosey.
            direction = random.choice((-1, 1))
            self.set_anim("mosey", move_dx=direction * max(2, self.WALK_SPEED // 2),
                          ticks=random.randint(25, 50))
        else:
            direction = random.choice((-1, 1))
            self.set_anim("walk_right" if direction > 0 else "walk_left",
                          move_dx=direction * self.WALK_SPEED,
                          ticks=random.randint(20, 45))

    def celebrate(self):
        """Quick happy reaction (e.g. when the user copies a prompt)."""
        self.idle_ticks = 0
        self.set_anim("emote", ticks=random.randint(14, 22))

    # ---- mouse interaction --------------------------------------------------

    def _on_press(self, event):
        self._press_xy = (event.x_root, event.y_root)
        self._win_xy = (self.root.winfo_x(), self.root.winfo_y())
        self._dragging = False
        was_napping = self.idle_ticks > self.NAP_AFTER_TICKS
        self.idle_ticks = 0
        if was_napping:
            self.set_anim("wave")  # woke up!

    def _on_motion(self, event):
        if not self._press_xy:
            return
        dx = event.x_root - self._press_xy[0]
        dy = event.y_root - self._press_xy[1]
        if abs(dx) > 4 or abs(dy) > 4:
            if not self._dragging and self.anim != "run":
                self.set_anim("run", ticks=9999)  # legs scramble while carried
            self._dragging = True
        if self._dragging:
            self.root.geometry(f"+{self._win_xy[0] + dx}+{self._win_xy[1] + dy}")

    def _on_release(self, event):
        if self._dragging:
            self._save_position()
            self.set_anim("emote", ticks=random.randint(10, 16))  # shake it off
        else:
            self.toggle_chat()
        self._press_xy = None
        self._dragging = False
        self.idle_ticks = 0

    def _on_menu(self, event):
        menu = tk.Menu(self.root, tearoff=0)
        menu.add_command(label="💬 Open chat", command=self.toggle_chat)
        menu.add_command(label="🛠 Open full editor", command=self.open_editor)
        menu.add_separator()
        menu.add_command(label="🔄 Change pet…", command=self.open_pet_browser)
        menu.add_command(label=f"ℹ About {self.pet_name()}", command=self.show_pet_credit)
        menu.add_command(label="🐾 About AskPet", command=self.show_about)
        size_menu = tk.Menu(menu, tearoff=0)
        for label, scale in (("Large", 1), ("Medium", 2), ("Small", 3)):
            check = " ✓" if scale == self.scale else ""
            size_menu.add_command(label=label + check,
                                  command=lambda s=scale: self.set_scale(s))
        menu.add_cascade(label="📏 Pet size", menu=size_menu)
        theme_menu = tk.Menu(menu, tearoff=0)
        current_theme = self.settings.get("chat_theme", "auto")
        for label, val in (("Auto (match Windows)", "auto"),
                           ("Light", "light"), ("Dark", "dark")):
            check = " ✓" if val == current_theme else ""
            theme_menu.add_command(label=label + check,
                                   command=lambda v=val: self.set_chat_theme(v))
        menu.add_cascade(label="🎨 Chat theme", menu=theme_menu)
        text_menu = tk.Menu(menu, tearoff=0)
        current_text_size = self.settings.get("chat_text_size", 10)
        for label, size in (("Small", 8), ("Normal", 10), ("Large", 13),
                            ("Extra Large", 16)):
            check = " ✓" if size == current_text_size else ""
            text_menu.add_command(label=label + check,
                                  command=lambda sz=size: self.set_chat_text_size(sz))
        menu.add_cascade(label="🔤 Chat text size", menu=text_menu)
        hist_menu = tk.Menu(menu, tearoff=0)
        current = history_retention_hours(self.settings)
        for label, hours in HISTORY_RETENTION_CHOICES:
            check = " ✓" if hours == current else ""
            hist_menu.add_command(label=f"Keep {label}{check}",
                                  command=lambda h=hours: self.set_history_retention(h))
        hist_menu.add_separator()
        hist_menu.add_command(label="🧹 Clear history now",
                              command=self.clear_history_now)
        menu.add_cascade(label="🕘 Prompt history", menu=hist_menu)
        chat_menu = tk.Menu(menu, tearoff=0)
        current_chat = chat_retention_hours(self.settings)
        for label, hours in HISTORY_RETENTION_CHOICES:
            check = " ✓" if hours == current_chat else ""
            chat_menu.add_command(label=f"Keep {label}{check}",
                                  command=lambda h=hours: self.set_chat_retention(h))
        chat_menu.add_separator()
        chat_menu.add_command(label="🧹 Clear chat history now",
                              command=self.clear_chat_history_now)
        menu.add_cascade(label="💬 Chat history", menu=chat_menu)
        mem_menu = tk.Menu(menu, tearoff=0)
        facts = load_pet_memory()
        if facts:
            for f in facts[-12:]:
                mem_menu.add_command(label=(f[:48] + "…") if len(f) > 49 else f,
                                     state="disabled")
            mem_menu.add_separator()
        else:
            mem_menu.add_command(label="(nothing yet — say “remember that …”)",
                                 state="disabled")
            mem_menu.add_separator()
        mem_menu.add_command(label="🧹 Forget everything",
                             command=self.clear_pet_memory_now)
        menu.add_cascade(label="🧠 What the pet remembers", menu=mem_menu)
        ai_menu = tk.Menu(menu, tearoff=0)
        if self.local_models:
            check = " ✓" if self.local_ai_enabled else ""
            ai_menu.add_command(label=f"Answer light asks locally{check}",
                                command=self._toggle_local_ai)
            ai_menu.add_separator()
            current_model = self.local_model()
            for m in self.local_models:
                mark = " ✓" if m == current_model else ""
                ai_menu.add_command(label=f"{m}{mark}",
                                    command=lambda mm=m: self.set_local_model(mm))
            ai_menu.add_separator()
            ai_menu.add_command(label="Refresh model list",
                                command=self._refresh_local_models)
            packs = knowledge_packs()
            if packs:
                ai_menu.add_separator()
                for p in packs:
                    ai_menu.add_command(
                        label=f"📚 {p['name']} ({p.get('videos', '?')} videos)",
                        state="disabled")
        else:
            ai_menu.add_command(label="Ollama not detected", state="disabled")
            ai_menu.add_command(label="Get it at ollama.com",
                                command=lambda: webbrowser.open("https://ollama.com"))
            ai_menu.add_command(label="Check again",
                                command=self._refresh_local_models)
        menu.add_cascade(label="✨ Local AI", menu=ai_menu)
        menu.add_separator()
        label = "Stop wandering" if self.wander else "Allow wandering"
        menu.add_command(label=f"🐾 {label}", command=self._toggle_wander)
        menu.add_separator()
        if self._update_info:
            menu.add_command(
                label=f"⬆ Update to {self._update_info['tag']}…",
                command=lambda r=self._update_info: self._prompt_update(r))
        else:
            menu.add_command(label="⬆ Check for updates",
                             command=lambda: self._check_for_updates_bg(manual=True))
        menu.add_command(label="❌ Exit AskPet", command=self.quit)
        # Hold the chat open while this menu is up (it owns the theme toggle);
        # the chat's click-outside-closes check skips while _menu_open is set.
        self._menu_open = True
        menu.bind("<Unmap>", lambda e: setattr(self, "_menu_open", False), add="+")
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

    def show_about(self):
        win = tk.Toplevel(self.root)
        win.title("About AskPet")
        win.wm_attributes("-topmost", True)
        win.resizable(False, False)
        frame = ttk.Frame(win, padding=16)
        frame.pack(fill="both", expand=True)

        ttk.Label(frame, text=f"{APP_NAME} v{APP_VERSION}",
                  font=("Segoe UI", 14, "bold")).pack(anchor="w")
        ttk.Label(frame,
                  text=f"Content library {CONTENT_VERSION} — "
                       f"{len(PROMPT_TEMPLATES)} templates · "
                       f"{len(AGENT_MODULES)} agent modules · "
                       f"{len(SKILL_TEMPLATES)} skills",
                  foreground="#666666").pack(anchor="w", pady=(2, 10))
        ttk.Label(frame, wraplength=400, justify="left", text=(
            "A desktop companion that turns plain-English asks into "
            "best-practice prompts for Codex, Claude Code, ChatGPT, and "
            "Claude. Everything runs locally — no cloud AI, no accounts, "
            "no telemetry.")).pack(anchor="w")

        ttk.Separator(frame).pack(fill="x", pady=10)
        ttk.Label(frame, text="Created by Ronnie Rosal",
                  font=("Segoe UI", 10, "bold")).pack(anchor="w")

        def link(text, url):
            lbl = ttk.Label(frame, text=text, foreground="#0b93f6",
                            cursor="hand2")
            lbl.pack(anchor="w", pady=(4, 0))
            lbl.bind("<Button-1>", lambda e: webbrowser.open(url))

        link("github.com/ronnierosal/askpet",
             "https://github.com/ronnierosal/askpet")
        ttk.Label(frame, wraplength=400, justify="left", foreground="#666666",
                  text="Pet art from codex-pets.net — every artist is "
                       "credited on their pet.").pack(anchor="w", pady=(8, 0))
        ttk.Button(frame, text="Close",
                   command=win.destroy).pack(anchor="e", pady=(12, 0))

    # ---- local AI -------------------------------------------------------------

    def _refresh_local_models(self):
        def worker():
            self.local_models = ollama_models()
        threading.Thread(target=worker, daemon=True).start()

    def local_model(self) -> str:
        return pick_local_model(self.local_models,
                                self.settings.get("local_ai_model"))

    def local_ai_ready(self) -> bool:
        return self.local_ai_enabled and bool(self.local_models)

    def _toggle_local_ai(self):
        self.local_ai_enabled = not self.local_ai_enabled
        self.settings["local_ai_enabled"] = self.local_ai_enabled
        self._save_settings()

    def set_local_model(self, model: str):
        self.settings["local_ai_model"] = model
        self._save_settings()

    def set_history_retention(self, hours: int):
        self.settings["history_retention_hours"] = hours
        self._save_settings()
        kept = prune_history(hours)
        label = next(l for l, h in HISTORY_RETENTION_CHOICES if h == hours)
        messagebox.showinfo(
            "Prompt history",
            f"History now kept for {label}. {kept} entr"
            f"{'y' if kept == 1 else 'ies'} currently stored.",
            parent=self.root)

    def clear_history_now(self):
        if messagebox.askyesno(
                "Clear history",
                "Delete all saved prompt history? This can't be undone.",
                parent=self.root):
            clear_history()
            messagebox.showinfo("Prompt history", "History cleared.",
                                parent=self.root)

    def set_chat_retention(self, hours: int):
        self.settings["chat_retention_hours"] = hours
        self._save_settings()
        kept = prune_chat_history(hours)
        label = next(l for l, h in HISTORY_RETENTION_CHOICES if h == hours)
        messagebox.showinfo(
            "Chat history",
            f"Chat now kept for {label}. {kept} message"
            f"{'' if kept == 1 else 's'} currently stored.",
            parent=self.root)

    def clear_chat_history_now(self):
        if messagebox.askyesno(
                "Clear chat history",
                "Delete all saved chat history? This can't be undone.",
                parent=self.root):
            clear_chat_history()
            if self.chat and self.chat.is_open():
                self.chat.clear_view()  # reset the open window to a fresh chat
            messagebox.showinfo("Chat history", "Chat history cleared.",
                                parent=self.root)

    def clear_pet_memory_now(self):
        if messagebox.askyesno(
                "Forget everything",
                "Make the pet forget everything it remembers about you? "
                "This can't be undone.",
                parent=self.root):
            clear_pet_memory()
            messagebox.showinfo("Pet memory", "Done — a fresh start.",
                                parent=self.root)

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
        x0, x1 = self._walk_bounds_for_width(w)
        sh = self.root.winfo_screenheight()
        self.root.geometry(f"{w}x{h}+{min(max(x0, x), x1)}+{min(y, sh - h)}")
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

    def set_chat_theme(self, value):
        """Persist the chat theme ('auto'|'light'|'dark') and, if the chat is
        open, restyle it live."""
        self.settings["chat_theme"] = value
        self._save_settings()
        if self.chat and self.chat.is_open():
            self.chat.apply_theme()

    def set_chat_text_size(self, size):
        """Persist the chat text size and, if the chat is open, apply it live."""
        size = max(7, min(18, int(size)))
        self.settings["chat_text_size"] = size
        self._save_settings()
        if self.chat and self.chat.is_open():
            self.chat.set_chat_text_size(size)

    def open_editor(self, prefill: str = ""):
        if self.editor and self.editor.root.winfo_exists():
            self.editor.root.deiconify()
            self.editor.root.lift()
        else:
            win = tk.Toplevel(self.root)
            self.editor = AskPetApp(win)
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
        # Merge live pet state onto fresh disk contents. Never dump the
        # in-memory dict wholesale: it holds values from launch time and
        # would resurrect stale settings (e.g. an old pet_scale) on save.
        disk = load_json(SETTINGS_FILE, {})
        disk["pet_scale"] = self.scale
        disk["pet_id"] = self.pet_id
        disk["pet_wander"] = self.wander
        for key in ("pet_x", "pet_y", "history_retention_hours",
                    "chat_retention_hours", "local_ai_enabled",
                    "local_ai_model", "local_ai_intro_shown", "chat_theme",
                    "chat_text_size", "update_seen"):
            if key in self.settings:
                disk[key] = self.settings[key]
        disk["app_version"] = APP_VERSION
        ELDER_STATE.save_into(disk)          # persist the Creature Journal
        save_json(SETTINGS_FILE, disk)

    # ---- self-update -----------------------------------------------------------

    def _check_for_updates_bg(self, manual: bool = False):
        """Look for a newer release off the UI thread, then report back."""
        def worker():
            rel = available_update()
            try:
                self.root.after(0, lambda: self._on_update_checked(rel, manual))
            except tk.TclError:
                pass  # window closed mid-check
        threading.Thread(target=worker, daemon=True).start()

    def _on_update_checked(self, rel, manual):
        self._update_info = rel  # right-click menu reads this
        if not rel:
            if manual:
                messagebox.showinfo(
                    "You're up to date",
                    f"AskPet v{APP_VERSION} is the latest version.",
                    parent=self.root)
            return
        # Auto-check nudges once per version; a manual check always prompts.
        if manual or self.settings.get("update_seen") != rel["tag"]:
            self.settings["update_seen"] = rel["tag"]
            self._save_settings()
            self._prompt_update(rel)

    def _prompt_update(self, rel):
        tag = rel.get("tag", "a new version")
        if not rel.get("asset_url"):
            # No installer asset published — fall back to the download page.
            if messagebox.askyesno(
                    "Update available",
                    f"AskPet {tag} is available (you have v{APP_VERSION}).\n\n"
                    "Open the download page?", parent=self.root):
                webbrowser.open(rel.get("page_url", RELEASES_PAGE))
            return
        if messagebox.askyesno(
                "Update available",
                f"AskPet {tag} is available — you have v{APP_VERSION}.\n\n"
                "Download and install it now? AskPet will close briefly and "
                "reopen when the update is finished.", parent=self.root):
            self._run_update(rel)

    def _run_update(self, rel):
        cancel = threading.Event()
        dialog = UpdateProgressDialog(self.root, rel["tag"], on_cancel=cancel.set)

        def to_ui(fn, *a):
            try:
                self.root.after(0, lambda: fn(*a))
            except tk.TclError:
                pass

        def worker():
            try:
                dest = DATA_DIR / "updates" / rel["asset_name"]
                to_ui(dialog.set_status, "Downloading…")
                download_release_asset(
                    rel["asset_url"], dest, expected_size=rel.get("asset_size"),
                    progress=lambda f: to_ui(dialog.set_progress, f),
                    cancel=cancel)
                to_ui(dialog.set_status, "Verifying signature…")
                if not verify_signed_installer(dest):
                    raise RuntimeError(
                        "the downloaded installer isn't signed by the "
                        "expected publisher")
                to_ui(self._install_update, dialog, dest)
            except Exception as exc:  # noqa: BLE001 — report any failure to the user
                to_ui(self._update_failed, dialog, rel, cancel, exc)
        threading.Thread(target=worker, daemon=True).start()

    def _install_update(self, dialog, dest):
        dialog.set_progress(1.0)
        dialog.set_status("Installing… AskPet will reopen shortly.")
        try:
            launch_installer_and_exit(dest)
        except OSError as exc:
            dialog.close()
            messagebox.showerror(
                "Update failed", f"Couldn't start the installer:\n{exc}",
                parent=self.root)
            return
        # Give the installer a moment to take over, then exit so it can replace
        # files; its silent-install step relaunches AskPet.
        self.root.after(1200, self.quit)

    def _update_failed(self, dialog, rel, cancel, exc):
        dialog.close()
        if cancel.is_set():
            return  # user cancelled — stay quiet
        if messagebox.askyesno(
                "Update failed",
                f"The update couldn't be completed automatically:\n{exc}\n\n"
                "Open the download page to update manually?", parent=self.root):
            webbrowser.open(rel.get("page_url", RELEASES_PAGE))

    def quit(self):
        self._save_position()
        self.root.destroy()


class PetBrowser:
    """Browse codex-pets.net and switch the desktop pet.

    The catalog and pet bundles are fetched from codex-pets.net only when the
    user asks. Creators are credited next to every pet.
    """

    COLUMNS = (("name", "Pet", 170), ("creator", "Creator", 150),
               ("kind", "Kind", 90), ("likes", "♥", 50))

    def __init__(self, pet: PetOverlay):
        self.pet = pet
        self.page = 0
        self.catalog = []  # raw pet dicts from the API
        self.sort_col = None
        self.sort_desc = False
        self._preview_cache = {}   # pet_id -> base64 PNG (or None on failure)
        self._preview_results = []  # worker threads append (pet_id, b64) here

        win = tk.Toplevel(pet.root)
        self.win = win
        win.title("Change pet — codex-pets.net")
        win.geometry("620x540")
        win.wm_attributes("-topmost", True)

        top = ttk.Frame(win, padding=6)
        top.pack(fill="x")
        ttk.Label(top, text="Search:").pack(side="left")
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *_: self._refresh_list())
        entry = ttk.Entry(top, textvariable=self.search_var)
        entry.pack(side="left", fill="x", expand=True, padx=6)
        entry.bind("<Return>", lambda *_: self.search_online())
        ttk.Button(top, text="Search all of codex-pets",
                   command=self.search_online).pack(side="left", padx=(0, 6))
        ttk.Button(top, text="Load more pets", command=self.load_more).pack(side="left")

        self.tree = ttk.Treeview(win, columns=[c[0] for c in self.COLUMNS],
                                 show="headings", height=12)
        for col, label, width in self.COLUMNS:
            self.tree.heading(col, text=label,
                              command=lambda c=col: self._sort_by(c))
            self.tree.column(col, width=width,
                             anchor="e" if col == "likes" else "w")
        self.tree.pack(fill="both", expand=True, padx=6)
        self.tree.bind("<<TreeviewSelect>>", self._on_select)

        # Detail row: preview image on the left, text on the right.
        detail_frame = ttk.Frame(win, padding=6)
        detail_frame.pack(fill="x")
        self.preview_label = ttk.Label(detail_frame, text="", width=20,
                                       anchor="center")
        self.preview_label.pack(side="left", padx=(0, 8))
        self.detail = ttk.Label(detail_frame,
                                text="Pets are downloaded from codex-pets.net "
                                     "only when you pick one, and cached locally.\n"
                                     "Tip: click a column header to sort; press "
                                     "Enter in the search box to search the whole "
                                     "site, typos welcome.",
                                wraplength=430, justify="left")
        self.detail.pack(side="left", fill="x", expand=True)

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

        self.win.after(120, self._poll_preview)
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

    def search_online(self):
        """Search the whole site via the API instead of only loaded pages."""
        query = self.search_var.get().strip()
        if not query:
            return
        self.status.config(text="Searching codex-pets.net…")
        self.win.update_idletasks()
        try:
            hits = self._server_search(query)
            known = {p["id"] for p in self.catalog}
            self.catalog.extend(h for h in hits if h["id"] not in known)
            self.status.config(text=f"{len(hits)} match(es) on codex-pets.net")
        except (urllib.error.URLError, OSError, ValueError) as e:
            self.status.config(text="Couldn't reach codex-pets.net")
            messagebox.showerror("Network error",
                                 f"Search failed:\n{e}", parent=self.win)
        self._refresh_list()

    @staticmethod
    def _server_search(query: str) -> list:
        """Typo-tolerant site search on top of the API's exact substring q=.

        Misspelled words usually share a prefix with the real name, so when
        a word gets no hits we retry progressively shorter prefixes:
        'godzila' -> 'godzi' matches 'Godzilla Blue'. Multi-word queries
        fall back to searching each word; the fuzzy local filter narrows
        whatever comes back.
        """
        def word_hits(w):
            for cut in range(len(w), max(3, len(w) - 4), -1):
                found = search_pets(w[:cut])
                if found:
                    return found
            return []

        hits = search_pets(query)
        words = [w for w in query.split() if len(w) >= 3]
        if not hits and len(words) == 1:
            hits = word_hits(words[0])
        elif not hits and words:
            seen_ids = set()
            for w in words:
                for h in word_hits(w):
                    if h["id"] not in seen_ids:
                        seen_ids.add(h["id"])
                        hits.append(h)
        return hits

    @staticmethod
    def _matches(p: dict, query: str) -> bool:
        """Word-order-independent, typo-tolerant local filter.

        Every query word must appear in the pet's text, either as a
        substring or as a fuzzy word match — so 'blue godzila' finds
        'Godzilla Blue'.
        """
        hay = " ".join([
            p.get("displayName", ""), p.get("id", ""),
            p.get("ownerName") or "", p.get("ownerHandle") or "",
            p.get("kind", ""), " ".join(p.get("tags") or []),
        ]).lower()
        words = hay.split()
        for tok in query.split():
            if tok in hay:
                continue
            if difflib.get_close_matches(tok, words, n=1, cutoff=0.75):
                continue
            return False
        return True

    def _sort_by(self, col):
        if self.sort_col == col:
            self.sort_desc = not self.sort_desc
        else:
            # Likes start descending (most-liked first); text starts A-Z.
            self.sort_col, self.sort_desc = col, col == "likes"
        self._refresh_list()

    def _refresh_list(self):
        query = self.search_var.get().strip().lower()
        self.tree.delete(*self.tree.get_children())
        seen, shown = set(), []
        for p in self.catalog:
            if p["id"] in seen:
                continue
            seen.add(p["id"])
            if query and not self._matches(p, query):
                continue
            shown.append(p)
        if self.sort_col:
            keys = {
                "name": lambda p: p.get("displayName", p["id"]).lower(),
                "creator": lambda p: pet_credit(p).lower(),
                "kind": lambda p: p.get("kind", "").lower(),
                "likes": lambda p: int(p.get("likeCount") or 0),
            }
            shown.sort(key=keys[self.sort_col], reverse=self.sort_desc)
        for col, label, _ in self.COLUMNS:
            arrow = ""
            if col == self.sort_col:
                arrow = " ▼" if self.sort_desc else " ▲"
            self.tree.heading(col, text=label + arrow)
        for p in shown:
            self.tree.insert("", "end", iid=p["id"],
                             values=(p.get("displayName", p["id"]),
                                     pet_credit(p), p.get("kind", ""),
                                     p.get("likeCount") or 0))

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
        self._show_preview(p)

    # ---- preview image -----------------------------------------------------

    def _show_preview(self, p):
        pid = p["id"]
        if pid in self._preview_cache:
            self._apply_preview(pid)
            return
        # posterUrl is a single portrait; previewUrl is a film strip of all
        # animation frames (cropped to frame one in the worker if used).
        url = p.get("posterUrl") or p.get("previewUrl")
        if not url:
            self.preview_label.config(text="(no preview)", image="")
            return
        self.preview_label.config(text="loading…", image="")
        threading.Thread(target=self._fetch_preview, args=(pid, url),
                         daemon=True).start()

    def _fetch_preview(self, pet_id, url):
        """Worker thread: fetch + convert to PNG base64. No Tk calls here."""
        b64 = None
        try:
            from PIL import Image
            raw = _http_get(url, timeout=20)
            img = Image.open(io.BytesIO(raw))
            if img.width > img.height * 3:  # film strip: keep frame one
                img = img.crop((0, 0, img.height, img.height))
            img.thumbnail((140, 120))
            buf = io.BytesIO()
            img.convert("RGBA").save(buf, "PNG")
            b64 = base64.b64encode(buf.getvalue()).decode("ascii")
        except Exception:
            pass  # no preview is fine — never crash the browser over it
        self._preview_results.append((pet_id, b64))

    def _poll_preview(self):
        if not self.win.winfo_exists():
            return
        while self._preview_results:
            pet_id, b64 = self._preview_results.pop(0)
            self._preview_cache[pet_id] = b64
            sel = self._selected()
            if sel and sel["id"] == pet_id:
                self._apply_preview(pet_id)
        self.win.after(120, self._poll_preview)

    def _apply_preview(self, pet_id):
        b64 = self._preview_cache.get(pet_id)
        if not b64:
            self.preview_label.config(text="(no preview)", image="")
            return
        try:
            self._preview_img = tk.PhotoImage(data=b64)
            self.preview_label.config(image=self._preview_img, text="")
        except tk.TclError:
            self.preview_label.config(text="(no preview)", image="")

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
    "Hi! I'm your assistant — ask me anything, or have me rewrite, "
    "summarize, review, or draft something. Just type and I'll help.\n\n"
    "Need a sharper prompt for Codex, Claude, or ChatGPT? Type “/fix-prompt” "
    "and your task and I'll build a copy-ready one. Type “/” to see every "
    "command."
)

# Synthetic pet greeting shown when the pet is swapped while the chat is open.
PETSWITCH_GREETING = "New look, same AskPet! What are we working on?"
# Canned confirmations for the "remember that …" capture (memory feature).
REMEMBER_ACK = "Got it — I'll remember that! ✨"
REMEMBER_DUP = "I already remember that! ✨"
# Pet bubbles that are transient UI, never persisted into the saved transcript
# nor fed back as short-term memory (greetings + memory-capture confirmations).
EPHEMERAL_PET_TEXTS = frozenset({CHAT_GREETING, PETSWITCH_GREETING,
                                 REMEMBER_ACK, REMEMBER_DUP})

SKIP_WORDS = {"skip", "idk", "i dont know", "i don't know", "not sure",
              "dunno", "just generate", "just build it", "go ahead", "na", "n/a"}


# Chat appearance. Two full palettes; the chat reads whichever the user's
# "chat_theme" setting resolves to ("auto" follows the Windows app theme).
# Every color the ChatWindow paints comes from here so a theme switch is a
# single dict swap + re-flow — no scattered literals.
CHAT_THEMES = {
    "light": {
        "WIN_BG": "#dde6f7", "GRAD_TOP": "#dfe8f8", "GRAD_BOTTOM": "#b7c8ec",
        "HEADER_BG": "#d3ddf2", "HEADER_TEXT": "#1e2438", "DIVIDER": "#aebbd8",
        "CAPTION": "#5b6478",
        "PET_BUBBLE": "#ffffff", "PET_TEXT": "#1c2030",
        "USER_BUBBLE": "#bcd6fb", "USER_TEXT": "#12305f",
        "PROMPT_BUBBLE": "#eef2fb", "PROMPT_TEXT": "#262a3a",
        "CHIP_BG": "#cdd9f0",
        "SCROLL_TROUGH": "#cdd9f0", "SCROLL_THUMB": "#9aafd6",
        "ENTRY_BORDER": "#aebbd8", "ENTRY_BG": "#ffffff",
        "ENTRY_TEXT": "#1c2030", "ENTRY_PLACEHOLDER": "#8089a0",
        "SEND_BG": "#4f86ef", "SEND_ACTIVE": "#3b73db", "SEND_FG": "#ffffff",
    },
    "dark": {
        "WIN_BG": "#1b1e27", "GRAD_TOP": "#262b3a", "GRAD_BOTTOM": "#13151d",
        "HEADER_BG": "#20242f", "HEADER_TEXT": "#eceef5", "DIVIDER": "#363c4b",
        "CAPTION": "#9aa1b2",
        "PET_BUBBLE": "#2e3442", "PET_TEXT": "#e9ebf2",
        "USER_BUBBLE": "#3a6fd0", "USER_TEXT": "#ffffff",
        "PROMPT_BUBBLE": "#23262f", "PROMPT_TEXT": "#d6dae6",
        "CHIP_BG": "#262b38",
        "SCROLL_TROUGH": "#1c2029", "SCROLL_THUMB": "#49526a",
        "ENTRY_BORDER": "#3a4150", "ENTRY_BG": "#2a2f3b",
        "ENTRY_TEXT": "#e9ebf2", "ENTRY_PLACEHOLDER": "#878fa3",
        "SEND_BG": "#3a6fd0", "SEND_ACTIVE": "#2f5cb0", "SEND_FG": "#ffffff",
    },
}
CHAT_WIN_ALPHA = 0.96  # soft whole-window translucency (Windows -alpha)


def _os_prefers_dark() -> bool:
    """True if Windows is set to a dark app theme. Best-effort; False elsewhere
    or if the registry value is missing."""
    if sys.platform != "win32":
        return False
    try:
        import winreg
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
        ) as k:
            return winreg.QueryValueEx(k, "AppsUseLightTheme")[0] == 0
    except (OSError, ImportError):
        return False


def resolve_chat_theme(setting: str) -> dict:
    """Map a chat_theme setting ('auto'|'light'|'dark') to a palette dict."""
    name = setting if setting in CHAT_THEMES else ("dark" if _os_prefers_dark()
                                                   else "light")
    return CHAT_THEMES[name]


def _lerp_color(c1: str, c2: str, t: float) -> str:
    """Linearly blend two '#rrggbb' colors; t in [0,1]."""
    a = [int(c1[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(c2[i:i + 2], 16) for i in (1, 3, 5)]
    r = [round(a[j] + (b[j] - a[j]) * t) for j in range(3)]
    return f"#{r[0]:02x}{r[1]:02x}{r[2]:02x}"


def _set_titlebar_dark(win, dark: bool):
    """Match the native Windows title bar to the chat theme via the DWM
    immersive-dark-mode attribute (Win10 1809+). Best-effort: a no-op on
    non-Windows or where the attribute isn't supported."""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        win.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(win.winfo_id())
        val = ctypes.c_int(1 if dark else 0)
        # DWMWA_USE_IMMERSIVE_DARK_MODE is 20 on builds 19041+, 19 on 1809-1903.
        for attr in (20, 19):
            if ctypes.windll.dwmapi.DwmSetWindowAttribute(
                    hwnd, attr, ctypes.byref(val), ctypes.sizeof(val)) == 0:
                break
    except Exception:
        pass


class SlimScrollbar(tk.Canvas):
    """A thin, flat, theme-colored vertical scrollbar — a clean modern stand-in
    for ttk.Scrollbar (no arrow buttons, no native chrome). It speaks the
    scrollbar protocol: .set(first, last) is wired to a canvas' yscrollcommand,
    and it drives the canvas via its yview command on drag. The capsule thumb
    disappears when everything already fits."""

    WIDTH = 9
    MIN_THUMB = 28

    def __init__(self, parent, yview, trough="#cccccc", thumb="#888888"):
        super().__init__(parent, width=self.WIDTH, highlightthickness=0, bd=0,
                         bg=trough, takefocus=0)
        self._yview = yview          # the canvas' yview callable
        self._first, self._last = 0.0, 1.0
        self._thumb = thumb
        self._drag_off = None        # pointer offset within the thumb while dragging
        self.bind("<Button-1>", self._on_press)
        self.bind("<B1-Motion>", self._on_drag)
        self.bind("<ButtonRelease-1>", lambda e: setattr(self, "_drag_off", None))
        self.bind("<Configure>", lambda e: self._redraw())

    def set(self, first, last):      # yscrollcommand callback
        self._first, self._last = float(first), float(last)
        self._redraw()

    def set_colors(self, trough, thumb):
        self._thumb = thumb
        self.configure(bg=trough)
        self._redraw()

    def _bounds(self):
        h = max(1, self.winfo_height())
        y1, y2 = self._first * h, self._last * h
        if y2 - y1 < self.MIN_THUMB:     # keep it grabbable
            y1 = min(y1, h - self.MIN_THUMB)
            y2 = y1 + self.MIN_THUMB
        return y1, y2

    def _redraw(self):
        self.delete("all")
        if self.winfo_height() <= 1:
            return
        if self._first <= 0.0 and self._last >= 1.0:
            return                       # everything fits -> no thumb
        y1, y2 = self._bounds()
        w = self.WIDTH
        d = w - 4                        # capsule diameter (2px margin each side)
        c = self._thumb
        self.create_oval(2, y1, 2 + d, y1 + d, fill=c, outline=c)
        self.create_oval(2, y2 - d, 2 + d, y2, fill=c, outline=c)
        self.create_rectangle(2, y1 + d / 2, 2 + d, y2 - d / 2, fill=c, outline=c)

    def _on_press(self, e):
        y1, y2 = self._bounds()
        self._drag_off = (e.y - y1) if y1 <= e.y <= y2 else (y2 - y1) / 2
        self._scroll_to(e.y)

    def _on_drag(self, e):
        if self._drag_off is not None:
            self._scroll_to(e.y)

    def _scroll_to(self, y):
        h = max(1, self.winfo_height())
        top = y - (self._drag_off or 0)
        self._yview("moveto", max(0.0, min(1.0, top / h)))


# ---------------------------------------------------------------------------
# Games: a little arcade the pet runs inside the chat. Everything here is
# DETERMINISTIC and offline — rules, scoring, and answers resolve instantly in
# Python so a kid never waits on the model to learn whether a guess was right.
# Content is hand-authored and G-rated. Games are pure (no Tkinter): the chat
# layer calls start()/handle()/is_over and shows the returned text. Difficulty
# spans a range so siblings of mixed ages can all play.
# ---------------------------------------------------------------------------

SCRAMBLE_WORDS = [
    "apple", "banana", "rocket", "puppy", "dragon", "castle", "rainbow",
    "planet", "cookie", "turtle", "wizard", "guitar", "pirate", "jungle",
    "dolphin", "pumpkin", "monster", "balloon", "penguin", "treasure",
    "butterfly", "dinosaur", "elephant", "sandwich",
]

# (category, word) — a spread of lengths/difficulty for mixed ages.
HANGMAN_WORDS = [
    ("Animal", "tiger"), ("Animal", "giraffe"), ("Animal", "octopus"),
    ("Animal", "kangaroo"), ("Animal", "penguin"),
    ("Space", "planet"), ("Space", "comet"), ("Space", "galaxy"),
    ("Space", "astronaut"), ("Space", "telescope"),
    ("Food", "pizza"), ("Food", "pancake"), ("Food", "spaghetti"),
    ("Food", "strawberry"),
    ("Things", "rocket"), ("Things", "castle"), ("Things", "umbrella"),
    ("Things", "treasure"), ("Things", "dragon"), ("Things", "rainbow"),
]

# (thing, [true attributes]). 20 Questions answers "yes" when a question word
# is one of the tags, "no" otherwise — so tags list everything TRUE about it.
TWENTYQ_THINGS = [
    ("dog", ["animal", "alive", "pet", "furry", "fur", "legs", "tail",
             "bark", "land", "eat", "cute", "friendly", "soft"]),
    ("cat", ["animal", "alive", "pet", "furry", "fur", "legs", "tail",
             "small", "land", "soft", "cute", "whiskers", "meow"]),
    ("elephant", ["animal", "alive", "big", "huge", "grey", "gray", "legs",
                  "trunk", "land", "ears", "heavy", "wild"]),
    ("fish", ["animal", "alive", "water", "swim", "small", "scales", "fins",
              "pet", "ocean", "wet"]),
    ("bird", ["animal", "alive", "fly", "wings", "feathers", "small", "eggs",
              "beak", "sky", "sing"]),
    ("apple", ["food", "fruit", "red", "green", "sweet", "round", "small",
               "eat", "tree", "healthy", "plant", "crunchy"]),
    ("banana", ["food", "fruit", "yellow", "sweet", "long", "eat", "peel",
                "soft", "plant", "healthy"]),
    ("sun", ["hot", "big", "round", "yellow", "bright", "sky", "star",
             "space", "light", "day", "warm"]),
    ("car", ["machine", "fast", "wheels", "metal", "drive", "road",
             "loud", "big", "doors", "vehicle"]),
    ("rocket", ["machine", "fast", "tall", "metal", "fly", "space", "loud",
                "fire", "vehicle", "pointy"]),
    ("tree", ["plant", "alive", "tall", "green", "wood", "leaves", "big",
              "land", "outside", "brown"]),
    ("ball", ["toy", "round", "bounce", "small", "play", "throw", "fun",
              "roll"]),
]

TRIVIA_PACKS = {
    "animals": [
        {"q": "Which animal is the tallest in the world?",
         "options": ["Giraffe", "Elephant", "Horse", "Camel"], "answer": 0},
        {"q": "How many legs does a spider have?",
         "options": ["6", "8", "10", "4"], "answer": 1},
        {"q": "Which animal is known as the King of the Jungle?",
         "options": ["Tiger", "Bear", "Lion", "Wolf"], "answer": 2},
        {"q": "What do you call a baby kangaroo?",
         "options": ["Cub", "Joey", "Calf", "Kit"], "answer": 1},
        {"q": "Which sea animal has eight arms?",
         "options": ["Octopus", "Shark", "Dolphin", "Crab"], "answer": 0},
        {"q": "What is the fastest land animal?",
         "options": ["Lion", "Cheetah", "Horse", "Rabbit"], "answer": 1},
    ],
    "space": [
        {"q": "Which planet do we live on?",
         "options": ["Mars", "Venus", "Earth", "Jupiter"], "answer": 2},
        {"q": "What is the closest star to Earth?",
         "options": ["The Moon", "The Sun", "Mars", "Pluto"], "answer": 1},
        {"q": "Which planet is known as the Red Planet?",
         "options": ["Mars", "Saturn", "Neptune", "Mercury"], "answer": 0},
        {"q": "What do astronauts wear in space?",
         "options": ["Raincoats", "Spacesuits", "Pajamas", "Armor"], "answer": 1},
        {"q": "Which planet is the biggest in our solar system?",
         "options": ["Earth", "Saturn", "Jupiter", "Mars"], "answer": 2},
        {"q": "What is the name of our galaxy?",
         "options": ["Andromeda", "Milky Way", "Big Dipper", "Orion"], "answer": 1},
    ],
    "dinosaurs": [
        {"q": "Which dinosaur had a long neck to reach tall trees?",
         "options": ["T-Rex", "Brachiosaurus", "Raptor", "Stegosaurus"], "answer": 1},
        {"q": "What does 'T-Rex' stand for?",
         "options": ["Tiny Rex", "Tyrannosaurus Rex", "Triceratops", "Turbo Rex"],
         "answer": 1},
        {"q": "Which dinosaur had three horns on its head?",
         "options": ["Triceratops", "Velociraptor", "Diplodocus", "Ankylosaurus"],
         "answer": 0},
        {"q": "What did big dinosaurs like Brachiosaurus eat?",
         "options": ["Meat", "Plants", "Rocks", "Fish"], "answer": 1},
        {"q": "What are dinosaur bones called when found in rock?",
         "options": ["Crystals", "Fossils", "Gems", "Shells"], "answer": 1},
    ],
}


def _strip_article(s):
    return re.sub(r"^(?:the|a|an)\s+", "", (s or "").strip().lower())


class NumberGuess:
    name = "Number Guess"
    blurb = "I think of a number 1–100; you guess higher/lower."

    def __init__(self, rng=None, lo=1, hi=100):
        self.lo, self.hi = lo, hi
        self.secret = (rng or random).randint(lo, hi)
        self.tries = 0
        self.over = False

    def start(self):
        return (f"🔢 I'm thinking of a number from {self.lo} to {self.hi}.\n"
                "Type a guess and I'll say higher or lower! (say 'quit' to stop)")

    def handle(self, text):
        m = re.search(r"-?\d+", text)
        if not m:
            return "Type a number for me to check! 🙂"
        g = int(m.group())
        self.tries += 1
        if g == self.secret:
            self.over = True
            tries = f"{self.tries} tr" + ("y" if self.tries == 1 else "ies")
            return f"🎉 YES! It was {self.secret} — you got it in {tries}! 🌟"
        return f"{g}? Try {'higher ⬆️' if g < self.secret else 'lower ⬇️'}!"

    @property
    def is_over(self):
        return self.over


class WordScramble:
    name = "Word Scramble"
    blurb = "Unscramble the mixed-up word."

    def __init__(self, rng=None):
        r = rng or random
        self.word = r.choice(SCRAMBLE_WORDS)
        self.scrambled = self._scramble(self.word, r)
        self.over = False

    @staticmethod
    def _scramble(word, r):
        letters = list(word)
        for _ in range(30):
            r.shuffle(letters)
            if "".join(letters) != word:
                break
        return "".join(letters)

    def start(self):
        return (f"🪢 Unscramble this word ({len(self.word)} letters):\n"
                f"   {self.scrambled.upper()}\n"
                "Type your answer, or 'hint' for a clue! (say 'quit' to stop)")

    def handle(self, text):
        t = text.strip().lower()
        if t in ("hint", "clue", "help"):
            return f"Clue: it starts with '{self.word[0].upper()}' 🔎"
        if t == self.word:
            self.over = True
            return f"🎉 YES! The word was {self.word.upper()} — word wizard! ✨"
        return f"Not quite — keep trying!\n   {self.scrambled.upper()}"

    @property
    def is_over(self):
        return self.over


class Hangman:
    name = "Hangman"
    blurb = "Guess the word letter by letter before the hearts run out."
    MAX_WRONG = 6

    def __init__(self, rng=None):
        self.category, self.word = (rng or random).choice(HANGMAN_WORDS)
        self.word = self.word.lower()
        self.guessed = set()
        self.wrong = 0
        self.over = False
        self.won = False

    def _mask(self):
        return " ".join(c.upper() if c in self.guessed else "_" for c in self.word)

    def _lives(self):
        return "❤️" * (self.MAX_WRONG - self.wrong) + "🤍" * self.wrong

    def _status(self):
        return f"{self._mask()}    {self._lives()}"

    def start(self):
        return (f"🔤 Hangman! Category: {self.category}.\n{self._status()}\n"
                "Guess a letter! (say 'quit' to stop)")

    def handle(self, text):
        t = text.strip().lower()
        if len(t) > 1:  # whole-word guess (never echoed back, for safety)
            if t == self.word:
                self.guessed |= set(self.word)
                self.over = self.won = True
                return f"🎉 YES! The word was {self.word.upper()} — brilliant! ✨"
            self.wrong += 1
            return self._after_wrong("That's not the word.")
        if not t.isalpha():
            return "Pick one letter, A–Z! 🙂"
        if t in self.guessed:
            return f"You already tried '{t.upper()}'. Pick a new letter!"
        self.guessed.add(t)
        if t in self.word:
            if all(c in self.guessed for c in self.word):
                self.over = self.won = True
                return f"🎉 YES! {self.word.upper()} — you spelled it! ✨"
            return f"Yes, there's a '{t.upper()}'!\n{self._status()}"
        self.wrong += 1
        return self._after_wrong(f"No '{t.upper()}'.")

    def _after_wrong(self, prefix):
        if self.wrong >= self.MAX_WRONG:
            self.over = True
            return (f"{prefix} Out of hearts! 🐭 The word was "
                    f"{self.word.upper()}. Want to play again?")
        return f"{prefix}\n{self._status()}"

    @property
    def is_over(self):
        return self.over


class TwentyQuestions:
    name = "20 Questions"
    blurb = "I think of something; ask yes/no questions to guess it."
    START = 20

    def __init__(self, rng=None):
        self.secret, tags = (rng or random).choice(TWENTYQ_THINGS)
        self.tags = set(tags)
        self.left = self.START
        self.over = False
        self.won = False

    def start(self):
        return ("❓ I'm thinking of something! Ask me yes/no questions "
                "(like 'is it an animal?'), or guess with 'is it a ___?'.\n"
                f"You have {self.left} questions. (say 'quit' to stop)")

    NEGATIONS = {"not", "no", "never", "isn", "isnt", "doesn", "doesnt",
                 "dont", "aren", "arent", "cant", "wont", "wasn"}

    def handle(self, text):
        t = text.strip().lower().rstrip("?")
        self.left -= 1
        words = set(re.findall(r"[a-z]+", t))
        negated = bool(words & self.NEGATIONS)
        # A correct guess: the secret appears as a whole word (so "is it a dog
        # by any chance" wins), but not inside a negated question.
        m = re.search(r"\bis it (?:a |an |the )?(.+)$", t)
        guess = m.group(1).strip() if m else None
        if guess and not negated and re.search(rf"\b{re.escape(self.secret)}\b", guess):
            self.over = self.won = True
            return f"🎉 YES! It was a {self.secret.upper()} — you guessed it! 🌟"
        # Yes/no by tag match, flipped when the question is negated.
        match = bool(words & self.tags)
        if negated:
            match = not match
        ans = "Yes! 👍" if match else "Nope! 👎"
        if self.left <= 0:
            self.over = True
            return (f"{ans} ...and that was your last question! It was a "
                    f"{self.secret.upper()}. Great game! 🎈")
        return f"{ans}  ({self.left} left)"

    @property
    def is_over(self):
        return self.over


class Trivia:
    name = "Trivia"
    blurb = "Kid-friendly quiz — animals, space, and dinosaurs."

    def __init__(self, rng=None, pack=None, n=5):
        r = rng or random
        names = [pack] if pack in TRIVIA_PACKS else list(TRIVIA_PACKS)
        pool = [dict(q) for name in names for q in TRIVIA_PACKS[name]]
        r.shuffle(pool)
        self.questions = pool[:n]
        self.i = 0
        self.score = 0
        self.over = not self.questions

    def _ask(self):
        q = self.questions[self.i]
        opts = "\n".join(f"   {chr(65 + j)}) {o}"
                         for j, o in enumerate(q["options"]))
        return f"Q{self.i + 1}/{len(self.questions)}: {q['q']}\n{opts}"

    def start(self):
        if not self.questions:
            return "I don't have any trivia loaded right now!"
        return ("🧠 Trivia time! Type the letter (A/B/C/D) of your answer.\n\n"
                + self._ask())

    def handle(self, text):
        q = self.questions[self.i]
        t = text.strip().lower()
        correct_idx = q["answer"]
        correct = q["options"][correct_idx].lower()
        picked = None
        if len(t) == 1 and t.isalpha():        # the instructed A/B/C/D path
            j = ord(t) - 97
            if 0 <= j < len(q["options"]):
                picked = q["options"][j].lower()
        if picked is not None:
            right = picked == correct
        else:
            # Text answers: accept the exact answer or its key word (so "sun"
            # matches "The Sun"), but on a WHOLE-WORD basis so "18" != "8".
            nt, nc = _strip_article(t), _strip_article(correct)
            right = bool(nt) and (nt == nc or nt in nc.split() or nc in nt.split())
        if right:
            self.score += 1
            verdict = f"✅ Correct! {q['options'][correct_idx]}."
        else:
            verdict = f"❌ It was {chr(65 + correct_idx)}) {q['options'][correct_idx]}."
        self.i += 1
        if self.i >= len(self.questions):
            self.over = True
            return (f"{verdict}\n\n🏁 Final score: {self.score}/"
                    f"{len(self.questions)}! {self._grade()}")
        return f"{verdict}\n\n{self._ask()}"

    def _grade(self):
        pct = self.score / max(1, len(self.questions))
        if pct == 1:
            return "Perfect! 🌟"
        if pct >= 0.6:
            return "Great job! 🎉"
        return "Good try — play again! 💪"

    @property
    def is_over(self):
        return self.over


# The Cozy Critter Dungeon: a gentle MUD-style room graph. The kid types
# interactive-fiction verbs (go/look/take/use/talk/inventory) and the engine
# resolves them in code — instantly and always winnable, with no death. The
# puzzle is to befriend critters (never fight): get the KEY from the mole,
# unlock the door, share the BERRY with the hedgehog, and bring the SUNSTONE
# home. "courage" stars are gentle encouragement and never cause a loss.
DUNGEON_ROOMS = {
    "entrance": {
        "name": "Mossy Doorway",
        "desc": "A soft mossy doorway twinkles with friendly fireflies. A little "
                "LANTERN rests on a rock. A cozy passage leads NORTH.",
        "exits": {"north": "hall"},
        "items": ["lantern"],
    },
    "hall": {
        "name": "Glowing Hall",
        "desc": "A round hall lit by glowworms. A library is EAST, a little "
                "wooden DOOR leads NORTH, and SOUTH goes back outside.",
        "exits": {"south": "entrance", "east": "library", "north": "garden"},
        "locked": {"north": "key"},
    },
    "library": {
        "name": "Cozy Library",
        "desc": "Stacks of acorn books! A sleepy MOLE in a nightcap dozes by a "
                "warm lamp. A red BERRY sits on a low shelf. WEST is the hall.",
        "exits": {"west": "hall"},
        "items": ["berry"],
        "mob": {"name": "mole",
                "talk": "The mole yawns: “Off to the garden, little one? Here, "
                        "take my KEY.”",
                "gives": "key"},
    },
    "garden": {
        "name": "Moonlit Garden",
        "desc": "A gentle garden under big friendly stars. A shy HEDGEHOG sits "
                "on a little bridge to the NORTH. SOUTH returns to the hall.",
        "exits": {"south": "hall", "north": "burrow"},
        "dark": True,
        "block": {"north": {"need": "berry",
                            "ok": "You share the BERRY. The hedgehog beams and "
                                  "scoots aside — the bridge NORTH is clear! ⭐",
                            "no": "A shy hedgehog gently blocks the bridge NORTH. "
                                  "Maybe it would like a snack…"}},
    },
    "burrow": {
        "name": "Starlit Burrow",
        "desc": "A warm burrow twinkling with starlight. The lost SUNSTONE glows "
                "softly here, ready to come home!",
        "exits": {"south": "garden"},
        "items": ["sunstone"],
        "goal_item": "sunstone",
    },
}

_DIRS = {"n": "north", "s": "south", "e": "east", "w": "west"}


class CozyDungeon:
    name = "Cozy Critter Dungeon"
    blurb = "A gentle adventure — explore, make critter friends, find the Sunstone."
    rpg = True          # a gentle RPG adventure — always unlocked, counts to unlock
    START_ROOM = "entrance"

    def __init__(self, rng=None, narrator=None):
        # Per-game copy so taking items doesn't mutate the shared map.
        self.rooms = {rid: {**r, "items": list(r.get("items", []))}
                      for rid, r in DUNGEON_ROOMS.items()}
        self.loc = self.START_ROOM
        self.inventory = []
        self.flags = set()
        self.courage = 3
        self.moves = 0
        self.over = False
        self.won = False
        self.narrator = narrator       # optional callable(room_dict) -> str|None
        self._visited = {self.START_ROOM}

    def start(self):
        return ("🗺️ Welcome to the COZY CRITTER DUNGEON! Help the lost Sunstone "
                "find its way home, and make critter friends along the way.\n"
                "Try things like: go north · look · take lantern · talk to mole · "
                "use key · give berry · inventory.  (say 'quit' to stop)\n\n"
                + self._describe(self.loc, first=True))

    def _describe(self, rid, first=False):
        r = self.rooms[rid]
        line = f"⭐{self.courage}   📍 {r['name']}\n{r['desc']}"
        if r.get("items"):
            line += "\nYou see: " + ", ".join(i.upper() for i in r["items"]) + "."
        if first and self.narrator:
            try:
                extra = self.narrator(r)
            except Exception:
                extra = None
            if extra:
                line += "\n" + extra
        return line

    def handle(self, text):
        self.moves += 1
        words = text.strip().lower().split()
        if not words:
            return "Tell me what to do! Try: go north, look, take lantern, inventory."
        verb, rest = words[0], " ".join(words[1:]).strip()
        if verb in _DIRS or verb in ("north", "south", "east", "west"):
            return self._go(_DIRS.get(verb, verb))
        if verb in ("go", "move", "walk", "run", "head"):
            return self._go(_DIRS.get(rest, rest))
        if verb in ("look", "l", "where"):
            return self._describe(self.loc)
        if verb in ("take", "get", "grab", "pick"):
            return self._take(rest.replace("up ", "").strip())
        if verb in ("inventory", "inv", "i", "bag"):
            return ("Your bag: " + ", ".join(i.upper() for i in self.inventory)
                    if self.inventory else "Your bag is empty right now.")
        if verb in ("use", "give", "open", "unlock"):
            return self._use(rest)
        if verb in ("talk", "speak", "hi", "hello", "say"):
            return self._talk()
        if verb in ("help", "?", "commands"):
            return ("Try: go north/south/east/west · look · take <thing> · "
                    "use <thing> · give <thing> · talk · inventory.")
        return ("Hmm, I'm not sure how to do that. Try: go north, look, take, "
                "use, give, talk, or inventory.")

    def _go(self, d):
        r = self.rooms[self.loc]
        if d not in r.get("exits", {}):
            # Never echo the kid's raw word back — name the real exits instead.
            ways = ", ".join(w.upper() for w in r.get("exits", {}))
            return (f"You can't go that way. Paths from here: {ways}. (try 'look')"
                    if ways else "There's nowhere to go from here just yet.")
        if d in r.get("locked", {}) and f"open:{self.loc}:{d}" not in self.flags:
            return f"The {d.upper()} door is locked. Maybe a KEY would open it."
        if d in r.get("block", {}) and f"clear:{self.loc}:{d}" not in self.flags:
            return r["block"][d]["no"]
        dest = r["exits"][d]
        self.loc = dest
        first = dest not in self._visited
        self._visited.add(dest)
        msg = ""
        if first and self.rooms[dest].get("dark"):
            if "lantern" in self.inventory:
                msg = "You hold up the LANTERN and the room turns cozy and bright! ✨\n"
            else:
                self.courage = max(0, self.courage - 1)
                msg = ("It's a little dark and spooky… you take a brave breath. "
                       f"(courage {self.courage}⭐)\n")
        return msg + self._describe(dest, first=first)

    def _take(self, item):
        r = self.rooms[self.loc]
        for it in list(r.get("items", [])):
            if it == item or (item and (item in it or it in item)):
                r["items"].remove(it)
                self.inventory.append(it)
                if it == r.get("goal_item"):
                    self.courage += 1
                    self.over = self.won = True
                    if not getattr(self, "_recorded", False):
                        self._recorded = True          # counts toward unlocking
                        record_rpg_completion()
                    return (f"✨ You found the {it.upper()}! The Sunstone is going "
                            f"home! 🌟 You explored bravely and made wonderful "
                            f"critter friends. (courage {self.courage}⭐)\n🏆 You win!")
                return f"You pop the {it.upper()} into your bag. 🎒"
        # Never echo the kid's raw word back — name what's actually here.
        here = ", ".join(i.upper() for i in r.get("items", []))
        return ("You don't see that here. " + (f"You could take: {here}."
                if here else "There's nothing to take here right now."))

    def _use(self, rest):
        item = next((i for i in self.inventory if i in rest), None)
        if item is None and not rest.strip() and len(self.inventory) == 1:
            item = self.inventory[0]   # "use it" with one thing in the bag
        if item is None:
            if rest.strip():
                return ("You don't have that in your bag yet. Try 'inventory' to "
                        "see what you're carrying.")
            return "Use what? Try 'use key' or 'give berry' — once it's in your bag."
        r = self.rooms[self.loc]
        if item == "key":
            for d, need in r.get("locked", {}).items():
                if need == "key" and f"open:{self.loc}:{d}" not in self.flags:
                    self.flags.add(f"open:{self.loc}:{d}")
                    return f"🔑 Click! The {d.upper()} door swings open. You can go {d.upper()} now!"
            return "There's nothing to unlock with the key here."
        for d, info in r.get("block", {}).items():
            if info.get("need") == item and f"clear:{self.loc}:{d}" not in self.flags:
                self.flags.add(f"clear:{self.loc}:{d}")
                if item in self.inventory:
                    self.inventory.remove(item)
                self.courage += 1
                return info["ok"]
        return f"You can't use the {item.upper()} here right now."

    def _talk(self):
        mob = self.rooms[self.loc].get("mob")
        if not mob:
            return "There's no critter to talk to here right now."
        line = mob["talk"]
        gift = mob.get("gives")
        if gift and f"gave:{self.loc}" not in self.flags:
            self.flags.add(f"gave:{self.loc}")
            self.inventory.append(gift)
            line += f"  🎁 (You got the {gift.upper()}!)"
        return line

    @property
    def is_over(self):
        return self.over


# ============================================================================
# Story-driven game layer (0.35.0): player profiles, atomic saves, a gentle
# dynamic-difficulty combat engine, and ELDERMARK — an original-world RPG.
#
# Everything is DETERMINISTIC + fully offline, reuses the app's DATA_DIR and
# save helpers (one source of truth — not a forked appdata path), and obeys
# the SAME start()/handle()/is_over contract as the quick games above, so each
# one drops straight into ChatWindow.active_game and inherits its crash
# isolation. Worlds, critters and stories are 100% original (own IP).
# ============================================================================

GAME_PROFILES_DIR = DATA_DIR / "games" / "profiles"
GAME_SCHEMA_VERSION = 1

# ---------------------------------------------------------------------------
# Arcade-wide state: the player's age band (sets baseline difficulty for every
# game) and how many RPG quests have been completed (other game modes stay
# LOCKED until a few RPG adventures are finished). One small JSON, family-wide.
# ---------------------------------------------------------------------------
GAMES_STATE_FILE = DATA_DIR / "games-state.json"
RPG_UNLOCK_THRESHOLD = 2        # finish this many RPG quests to unlock the rest

# (key, label, hint) — chosen once on first /play; scales difficulty everywhere.
AGE_BANDS = [
    ("little", "Little Explorer", "ages 4–6 · gentlest"),
    ("kid", "Big Kid", "ages 7–9 · just right"),
    ("pro", "Junior Pro", "ages 10+ · a bit tougher"),
]
# Difficulty multiplier per band (smaller = easier enemies / simpler problems).
AGE_DIFFICULTY = {"little": 0.7, "kid": 1.0, "pro": 1.25}


def load_games_state():
    d = load_json(GAMES_STATE_FILE, {})
    if not isinstance(d, dict):
        d = {}
    d.setdefault("age_band", None)
    d.setdefault("rpg_completed", 0)
    return d


def save_games_state(d):
    return save_json(GAMES_STATE_FILE, d)


def games_age_band():
    return load_games_state().get("age_band")


def set_games_age_band(band):
    d = load_games_state()
    d["age_band"] = band
    save_games_state(d)


def age_difficulty():
    """Baseline difficulty multiplier from the chosen age band (1.0 if unset)."""
    return AGE_DIFFICULTY.get(games_age_band(), 1.0)


def rpg_completed_count():
    try:
        return int(load_games_state().get("rpg_completed", 0) or 0)
    except (TypeError, ValueError):
        return 0


def record_rpg_completion():
    """Call when an RPG quest is finished; returns the new total."""
    d = load_games_state()
    d["rpg_completed"] = rpg_completed_count() + 1
    save_games_state(d)
    return d["rpg_completed"]


def games_unlocked():
    """True once enough RPG quests are done to open the other game modes."""
    return rpg_completed_count() >= RPG_UNLOCK_THRESHOLD


def _game_default_state():
    """Per-game state for a fresh profile. Add a key here to reserve a seam
    for a new mode; old saves deep-fill to it on load without losing data."""
    return {
        "eldermark": {
            "scene": 0, "level": 1, "xp": 0, "hp": 30, "hp_max": 30,
            "abilities": ["strike", "guard"], "inventory": [],
            "dda": {"recent": [], "tier": "normal"}, "flags": [],
        },
        # Seams reserved for the scaffolded modes (they slot in next):
        "critters": {}, "spin": {}, "wild": {}, "math": {}, "science": {},
    }


def _game_now():
    return datetime.now().isoformat(timespec="seconds")


def _game_slug(name):
    s = re.sub(r"[^a-z0-9]+", "-", (name or "").strip().lower()).strip("-")
    return s or "scout"


def _new_profile_dict(pid, name):
    now = _game_now()
    return {
        "schema_version": GAME_SCHEMA_VERSION,
        "profile_id": pid, "display_name": name,
        "created": now, "last_played": now,
        "points": 0, "achievements": [],
        "games": _game_default_state(),
    }


# --- atomic save + crash recovery -------------------------------------------
# Fix vs. the review: snapshot the current main to .bak ONLY when it actually
# parses, so a corrupt main can never clobber the last-good backup.

def _read_profile_file(path):
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _deep_fill(defaults, saved):
    """Recursively fill keys missing from `saved` using `defaults`, without
    overwriting any value the save already has. So a field added in a newer
    version (e.g. hp_max) gets its default on load instead of crashing later."""
    if not isinstance(saved, dict) or not isinstance(defaults, dict):
        return saved
    out = dict(saved)
    for k, dv in defaults.items():
        if k not in out:
            out[k] = dv
        elif isinstance(dv, dict):
            out[k] = _deep_fill(dv, out[k])
    return out


def save_game_profile(prof):
    """Durable, atomic save with a rotating .bak. Called on game beats
    (scene change, battle end, rest) — NOT every turn — to avoid UI jank."""
    prof["last_played"] = _game_now()
    pid = prof.get("profile_id") or "scout"
    path = GAME_PROFILES_DIR / f"{pid}.json"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        return False
    if path.exists() and _read_profile_file(path) is not None:
        try:
            shutil.copy2(path, path.with_name(path.name + ".bak"))
        except OSError:
            pass
    tmp = path.with_name(path.name + ".tmp")
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(prof, f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)          # atomic on the same filesystem
        return True
    except OSError:
        try:
            if tmp.exists():
                tmp.unlink()
        except OSError:
            pass
        return False


def load_game_profile(pid):
    path = GAME_PROFILES_DIR / f"{pid}.json"
    data = _read_profile_file(path)
    if data is None:                                   # fall back to backup
        data = _read_profile_file(path.with_name(path.name + ".bak"))
    if not isinstance(data, dict):
        return None
    data["games"] = _deep_fill(_game_default_state(), data.get("games") or {})
    data.setdefault("schema_version", GAME_SCHEMA_VERSION)
    data.setdefault("points", 0)
    data.setdefault("achievements", [])
    data.setdefault("display_name", pid)
    return data


def list_game_profiles():
    """(profile_id, display_name, eldermark_level) for the picker. Skips any
    stray/partial/corrupt JSON instead of crashing the first screen kids hit."""
    out = []
    try:
        names = sorted(p.name for p in GAME_PROFILES_DIR.glob("*.json"))
    except OSError:
        return out
    for fn in names:
        d = _read_profile_file(GAME_PROFILES_DIR / fn)
        if not isinstance(d, dict):
            continue
        pid = d.get("profile_id")
        if not pid:
            continue
        lvl = ((d.get("games") or {}).get("eldermark") or {}).get("level", 1)
        out.append((pid, d.get("display_name", pid), lvl))
    return out


def create_game_profile(name):
    base = _game_slug(name)
    pid, n = base, 2
    while (GAME_PROFILES_DIR / f"{pid}.json").exists():
        pid = f"{base}-{n}"
        n += 1
    prof = _new_profile_dict(pid, name)
    save_game_profile(prof)
    return prof


# --- dice + gentle dynamic difficulty ---------------------------------------
DDA_WINDOW = 6
DDA_FLOOR = 0.34          # below this win-rate, ease off; we never go HARDER


def _roll(sides=4, n=1, rng=random):
    return sum(rng.randint(1, sides) for _ in range(n))


def record_result(dda, won):
    r = dda.setdefault("recent", [])
    r.append(1 if won else 0)
    del r[:-DDA_WINDOW]
    if len(r) >= 3:
        rate = sum(r) / len(r)
        # Kid-gentle: only easy or normal — a struggling child is never
        # ratcheted into a harder tier.
        dda["tier"] = "easy" if rate < DDA_FLOOR else "normal"


def difficulty_mult(dda):
    return {"easy": 0.7, "normal": 1.0}.get(dda.get("tier", "normal"), 1.0)


def award(prof, aid, name, desc):
    """Unlock an achievement once; returns True only the first time."""
    achs = prof.setdefault("achievements", [])
    if any(a.get("id") == aid for a in achs):
        return False
    achs.append({"id": aid, "name": name, "desc": desc, "unlocked": _game_now()})
    return True


# --- Eldermark content (original world) -------------------------------------
ELDER_ABILITIES = {
    "strike": {"label": "Strike", "power": 6},
    "focus":  {"label": "Focus Beam", "power": 10},     # learned at level 2
    "rally":  {"label": "Rally Burst", "power": 14},    # learned at level 4
    "guard":  {"label": "Guard", "power": 0},
}
ELDER_UNLOCKS = {2: "focus", 4: "rally"}

# Critters never get hurt — they tire out and scatter into friendly light.
ELDER_ENEMIES = {
    "gloomling": {"name": "Gloomling", "hp": 16, "atk": 4, "xp": 22,
                  "win": "The Gloomling yawns, puffs into a swirl of friendly "
                         "motes, and drifts off for a nap. ✨"},
    "thistlewisp": {"name": "Thistlewisp", "hp": 24, "atk": 6, "xp": 32,
                    "win": "The Thistlewisp giggles, shakes loose its prickles, "
                           "and bounces away glowing softly. 🌼"},
    "mire-warden": {"name": "Mire Warden", "hp": 42, "atk": 8, "xp": 60,
                    "boss": True,
                    "win": "The big, grumpy Mire Warden finally smiles, sighs a "
                           "warm breath of starlight, and steps gently aside. 🌟"},
}

ELDER_RPG_SCENES = [
    {"name": "Mosslight Gate",
     "desc": "A soft mossy archway twinkles with fireflies. The path into the "
             "Hollow glows ahead. A sleepy MOSSBACK dozes on a warm stone.",
     "critter": {"line": "The Mossback blinks: “Off to relight the Wayshrines? "
                         "Here, take a GLOW-BERRY — it'll keep you bright.”",
                 "gives": "glow-berry"}},
    {"name": "Whisperwood",
     "desc": "Tall, whispery trees lean close. Something shy rustles in the "
             "shadows — it doesn't want to scare you, it just wants to play.",
     "enemy": "gloomling"},
    {"name": "Lantern Glade",
     "desc": "A calm glade strung with paper lanterns. A kindly HEDGE-PIXIE "
             "tends a basket of berries and waves you over.",
     "critter": {"line": "The Hedge-Pixie smiles: “You're doing wonderfully! "
                         "Take another GLOW-BERRY for the road.”",
                 "gives": "glow-berry"}},
    {"name": "Hollow Steps",
     "desc": "Old stone steps spiral down toward a warm glow. A prickly little "
             "Thistlewisp bounces in your way, daring you to keep going.",
     "enemy": "thistlewisp"},
    {"name": "The Dimmed Wayshrine",
     "desc": "The great Wayshrine stands dark and quiet. The grumpy MIRE WARDEN "
             "guards it — not mean, just lonely and a little sad.",
     "enemy": "mire-warden"},
]


# --- ASCII "game screen" art + builders (rendered in the big monospace panel)
ELDER_BANNER = (
    "   +============================+\n"
    "   |     E L D E R M A R K      |\n"
    "   +============================+"
)


def _ascii_banner(title, inner=28):
    """Center a title inside a fixed-width ASCII box (no hand-counting bugs)."""
    t = title[:inner]
    left = (inner - len(t)) // 2
    bar = "   +" + "=" * inner + "+"
    mid = "   |" + " " * left + t + " " * (inner - left - len(t)) + "|"
    return f"{bar}\n{mid}\n{bar}"


GAME_ART_W = 54         # reference width art is centered within on game screens


def _center_block(s, width=GAME_ART_W):
    """Center a multi-line art block (uniform left pad so it stays aligned),
    so the picture sits in the middle with text/actions below it."""
    lines = s.split("\n")
    mw = max((len(ln) for ln in lines), default=0)
    pad = " " * max(0, (width - mw) // 2)
    return "\n".join(pad + ln for ln in lines)


GAMES_BANNER = _ascii_banner("G A M E   A R C A D E")

# Scene/enemy motifs drawn as block "pixel art" in the monospace panel. Only
# block-element glyphs proven to render single-width in the app's Consolas are
# used (full/shaded/half blocks: █ ▓ ▒ ░ ▀ ▄) — NOT the quadrant blocks
# (▟▙▜▛), which fall back to tofu boxes in Consolas.
ELDER_ART = {
    "Mosslight Gate":
        "   ▄██████████▄\n"
        "   ███▀▀▀▀▀▀███\n"
        "   ██▒      ▒██\n"
        "   ██░      ░██\n"
        "   ██        ██\n"
        "   ██▄▄▄▄▄▄▄▄██",
    "Whisperwood":
        "   ▄██▄  ▄██▄  ▄██▄\n"
        "   ▓██▓  ▓██▓  ▓██▓\n"
        "   ████  ████  ████\n"
        "   ▀██▀  ▀██▀  ▀██▀\n"
        "    ██    ██    ██",
    "Lantern Glade":
        "    █     █     █\n"
        "   ▄█▄   ▄█▄   ▄█▄\n"
        "   █▒█   █▒█   █▒█\n"
        "   ▀█▀   ▀█▀   ▀█▀",
    "Hollow Steps":
        "   ██\n"
        "   ████\n"
        "   ██████\n"
        "   ████████\n"
        "   ██████████   down",
    "The Dimmed Wayshrine":
        "      ░▒▒░\n"
        "     ▒▓██▓▒\n"
        "     ▓████▓\n"
        "     █▓▒▒▓█\n"
        "     ▓████▓\n"
        "    ▄██████▄",
    "trails":
        "            ░▒▓▒░\n"
        "           ▒▓███▓▒\n"
        "           ▓█████▓\n"
        "           ▒▓███▓▒\n"
        "            ░▒▓▒░\n"
        "   ▄▄▄              ▄▄\n"
        "  ▒▓▓▓▒░        ░▒▓▓▒\n"
        " ░▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒░\n"
        "       sunny eldermark",
    "gloomling":
        "     ▄▒▓▓▒▄\n"
        "    ▒▓████▓▒\n"
        "    ▓█░██░█▓\n"
        "    ▓██████▓\n"
        "    ▒▓████▓▒\n"
        "     ▀▒▓▒▀",
    "thistlewisp":
        "    ▀  ▀  ▀\n"
        "   ▄██████▄\n"
        "   █░████░█\n"
        "   ▀██████▀\n"
        "    ▄  ▄  ▄",
    "mire-warden":
        "   ▄██████████▄\n"
        "   ████░██░████\n"
        "   ████████████\n"
        "   ███▄████▄███\n"
        "   ▀██████████▀\n"
        "    ██▀    ▀██",
}


def _elder_bar(cur, mx, width=10):
    """A monospace health bar like [#####-----] 16/24 (pure ASCII -> aligns)."""
    cur = max(0, min(cur, mx))
    fill = int(round(width * cur / mx)) if mx else 0
    return "[" + "#" * fill + "-" * (width - fill) + f"] {cur}/{mx}"


def _wrap_lines(text, width=46, indent="  "):
    """Word-wrap to a fixed column width (the game screen draws with no wrap)."""
    out = []
    for para in (text or "").split("\n"):
        if not para.strip():
            out.append("")
            continue
        line = indent
        for word in para.split():
            if line.strip() and len(line) + 1 + len(word) > width:
                out.append(line.rstrip())
                line = indent + word
            else:
                line = (line + " " + word) if line.strip() else (indent + word)
        out.append(line.rstrip())
    return out


def _elder_menu(opts):
    """Numbered menu; two columns when labels are short, else one per line."""
    cells = [f"  {i + 1}) {lbl}" for i, (_, lbl) in enumerate(opts)]
    colw = (max(len(c) for c in cells) + 2) if cells else 0
    if len(cells) > 1 and colw <= 24:
        rows = []
        for i in range(0, len(cells), 2):
            if i + 1 < len(cells):
                rows.append(f"{cells[i]:<{colw}}{cells[i + 1]}")
            else:
                rows.append(cells[i])
        return rows
    return cells


def _elder_screen(log=None, title=None, art=None, info=None, opts=None,
                  prompt="What will you do?", footer=True):
    """Assemble one ASCII 'screen': banner, an optional event log, a titled
    scene/enemy panel with art, status lines, and the numbered menu."""
    parts = [ELDER_BANNER]
    for line in (log or []):
        parts.append("")
        parts += [f"  > {x}" for x in _wrap_lines(line, 44, indent="")]
    if title:
        parts += ["", f"  {title}"]
    if art:
        parts.append(_center_block(art))
    for block in (info or []):
        parts.append(block)
    if opts:
        parts += ["", f"  {prompt}"]
        parts += _elder_menu(opts)
    if footer:
        parts += ["", "  (type 'quit' to stop · progress saves itself)"]
    return "\n".join(parts)


def _maybe_level_up(g):
    """Level up as many times as the XP allows, carrying the remainder so no
    earned XP is ever silently lost. Returns the level-up messages."""
    msgs = []
    while g["xp"] >= g["level"] * 50:
        g["xp"] -= g["level"] * 50
        g["level"] += 1
        g["hp_max"] += 6
        g["hp"] = g["hp_max"]
        new = ELDER_UNLOCKS.get(g["level"])
        if new and new not in g["abilities"]:
            g["abilities"].insert(max(0, len(g["abilities"]) - 1), new)
            msgs.append(f"⭐ Level {g['level']}! You learned "
                        f"{ELDER_ABILITIES[new]['label']}!")
        else:
            msgs.append(f"⭐ Level {g['level']}! You feel stronger — full ❤.")
    return msgs


class EldermarkRPG:
    """Original-world story RPG. A whole multi-step flow (pick profile → name →
    explore → numbered-menu combat → save/resume) lives inside handle(), so the
    existing two-state ChatWindow router never has to change."""

    name = "Eldermark"
    blurb = ("a gentle story RPG — explore, befriend critters, and relight the "
             "Wayshrines (saves your progress)")
    screen = True   # render in the big monospace "game screen" (expands window)
    rpg = True      # an RPG quest — always unlocked, counts toward unlocking more

    def __init__(self):
        self.state = "profile"
        self.prof = None
        self.enemy = None
        self.over = False
        self._opts = []
        self._profiles = []

    # -- contract ------------------------------------------------------------
    def start(self):
        self.__init__()
        return self._profile_menu()

    def handle(self, text):
        try:
            if self.state == "profile":
                return self._handle_profile(text)
            if self.state == "naming":
                return self._handle_naming(text)
            if self.state == "battle":
                return self._handle_battle(text)
            return self._handle_play(text)
        except Exception:
            # The chat layer guards this too, but never let a content slip end
            # a kid's adventure — recover to a sensible screen.
            if self.prof and self.state != "battle":
                return "Hmm, the path twisted for a moment — here we are:\n\n" + \
                    self._scene_text()
            return "Let's start again:\n\n" + self._profile_menu()

    @property
    def is_over(self):
        return self.over

    # -- profile picking -----------------------------------------------------
    def _profile_menu(self):
        self._profiles = list_game_profiles()
        info = _wrap_lines("A gentle quest to relight the Wayshrines of the "
                           "Hollow and befriend its critters.", 46)
        opts = [("p", f"{name}  (Lv {lvl})") for _, name, lvl in self._profiles]
        opts.append(("new", "+ New scout"))
        return _elder_screen(title="~ Lumen Scout ~", art=ELDER_ART["trails"],
                             info=info, opts=opts,
                             prompt="Who's adventuring today?")

    def _handle_profile(self, text):
        n = self._parse_int(text)
        last = len(self._profiles) + 1
        if n is None or not (1 <= n <= last):
            return (f"Type a number from 1 to {last} — pick your scout, or "
                    f"{last} to start a new one.")
        if n == last:
            self.state = "naming"
            return "What should I call you, brave scout? (type a name)"
        pid = self._profiles[n - 1][0]
        self.prof = load_game_profile(pid)
        if self.prof is None:
            return "I couldn't open that scout's journal — pick another?\n\n" + \
                self._profile_menu()
        name = self.prof.get("display_name", "scout")
        lvl = self.prof["games"]["eldermark"]["level"]
        return self._enter_play(f"Welcome back, {name}! ✨ (level {lvl})")

    def _handle_naming(self, text):
        name = re.sub(r"\s+", " ", (text or "").strip())[:20].strip()
        if not name:
            return "Tell me a name to call you! (a few letters is perfect)"
        self.prof = create_game_profile(name)
        award(self.prof, "first_steps", "First Steps",
              "Began the Eldermark adventure")
        save_game_profile(self.prof)
        return self._enter_play(
            f"Welcome to Eldermark, {name}! 🌟 A Lumen Scout relights the "
            "Wayshrines and makes critter friends. No one ever gets hurt here — "
            "if a critter bumps you, you just take a breath and try again.")

    def _enter_play(self, greeting):
        self.state = "play"
        return self._scene_text(log=[greeting])

    # -- exploration ---------------------------------------------------------
    def _g(self):
        return self.prof["games"]["eldermark"]

    def _has(self, flag):
        return flag in self._g()["flags"]

    def _flag(self, flag):
        g = self._g()
        if flag not in g["flags"]:
            g["flags"].append(flag)

    def _current_scene(self):
        g = self._g()
        if g["scene"] >= len(ELDER_RPG_SCENES):
            return None                              # roaming after victory
        return ELDER_RPG_SCENES[g["scene"]]

    def _scene_text(self, log=None):
        g = self._g()
        sc = self._current_scene()
        if sc is None:
            title, art = "The Sunlit Trails", ELDER_ART["trails"]
            desc = ("The Hollow is warm and bright again. Roam as long as you "
                    "like and meet more critters!")
            self._opts = [("roam", "Wander the trails"),
                          ("rest", "Rest a moment"),
                          ("pack", "Check your pack")]
        else:
            title, art = sc["name"], ELDER_ART.get(sc["name"], "")
            desc = sc["desc"]
            self._opts = [("onward", "Press onward")]
            if sc.get("critter") and not self._has(f"met:{g['scene']}"):
                self._opts.append(("look", "Look around"))
            self._opts.append(("rest", "Rest a moment"))
            self._opts.append(("pack", "Check your pack"))
        return _elder_screen(log=log, title=f"~ {title} ~", art=art,
                             info=_wrap_lines(desc, 46), opts=self._opts)

    def _handle_play(self, text):
        n = self._parse_int(text)
        if n is None or not (1 <= n <= len(self._opts)):
            return self._scene_text(log=["Type the number of an option above."])
        key = self._opts[n - 1][0]
        if key == "onward":
            return self._advance()
        if key == "roam":
            return self._begin_battle(random.choice(["gloomling", "thistlewisp"]))
        if key == "look":
            return self._look()
        if key == "rest":
            return self._rest()
        if key == "pack":
            return self._pack()
        return self._scene_text()

    def _advance(self):
        g = self._g()
        sc = self._current_scene()
        if sc is None:
            return self._begin_battle(random.choice(["gloomling", "thistlewisp"]))
        if sc.get("enemy") and not self._has(f"cleared:{g['scene']}"):
            return self._begin_battle(sc["enemy"])
        g["scene"] += 1
        save_game_profile(self.prof)
        msg = ("You follow the glimmering path onward..."
               if g["scene"] < len(ELDER_RPG_SCENES)
               else "You stroll on into the sunshine...")
        return self._scene_text(log=[msg])

    def _look(self):
        g = self._g()
        sc = self._current_scene()
        cr = sc.get("critter") if sc else None
        if not cr:
            return self._scene_text(log=["There's no one new to meet just now."])
        self._flag(f"met:{g['scene']}")
        log = [cr["line"]]
        gift = cr.get("gives")
        if gift:
            g["inventory"].append(gift)
            log.append(f"You receive a {gift.upper()}!")
            if award(self.prof, "first_friend", "First Friend",
                     "Made friends with a critter"):
                log.append("Achievement unlocked: First Friend!")
        save_game_profile(self.prof)
        return self._scene_text(log=log)

    def _rest(self):
        g = self._g()
        heal = 10
        g["hp"] = min(g["hp_max"], g["hp"] + heal)
        save_game_profile(self.prof)
        return self._scene_text(log=[f"You rest by a glowing toadstool. "
                                     f"(+{heal} HP, now {g['hp']}/{g['hp_max']})"])

    def _pack(self):
        inv = self._g()["inventory"]
        body = ("Your pack: " + ", ".join(i.upper() for i in inv)
                if inv else "Your pack is empty for now.")
        return self._scene_text(log=[body])

    # -- combat (numbered menu, never a loss spiral) -------------------------
    def _begin_battle(self, enemy_key):
        g = self._g()
        e = ELDER_ENEMIES[enemy_key]
        mult = difficulty_mult(g["dda"]) * age_difficulty()   # ease for younger kids
        hp = max(1, int(e["hp"] * mult))
        self.enemy = {"key": enemy_key, "name": e["name"], "hp": hp, "hp_max": hp,
                      "atk": max(1, int(e["atk"] * mult)), "xp": e["xp"],
                      "win": e["win"], "boss": bool(e.get("boss"))}
        self.state = "battle"
        return self._battle_text(intro=True)

    def _battle_options(self):
        g = self._g()
        opts = [(ab, ELDER_ABILITIES[ab]["label"]) for ab in g["abilities"]]
        if "glow-berry" in g["inventory"]:
            opts.append(("item", "Glow-berry (heal)"))
        opts.append(("run", "Slip away"))
        return opts

    def _battle_text(self, intro=False, log=None):
        g, e = self._g(), self.enemy
        self._opts = self._battle_options()
        info = [
            f"  {e['name']:<12}{_elder_bar(e['hp'], e['hp_max'])}",
            f"  {'You':<12}{_elder_bar(g['hp'], g['hp_max'])}  Lv{g['level']}",
        ]
        title = f"~ A {e['name']} appears! ~" if intro else f"~ {e['name']} ~"
        return _elder_screen(log=log, title=title, art=ELDER_ART.get(e["key"], ""),
                             info=info, opts=self._opts, prompt="Your move:")

    def _handle_battle(self, text):
        n = self._parse_int(text)
        if n is None or not (1 <= n <= len(self._opts)):
            return self._battle_text(log=["Type the number of one of your moves."])
        return self._battle_turn(self._opts[n - 1][0])

    def _battle_turn(self, key):
        g, e = self._g(), self.enemy
        if key == "run":
            self.enemy = None
            self.state = "play"
            record_result(g["dda"], False)
            save_game_profile(self.prof)
            return self._scene_text(log=["You slip quietly back down the path "
                                         "— no harm done."])
        log, guarding = [], False
        if key == "item":
            g["inventory"].remove("glow-berry")
            heal = 12
            g["hp"] = min(g["hp_max"], g["hp"] + heal)
            log.append(f"You munch a GLOW-BERRY (+{heal} HP).")
        elif key == "guard":
            guarding = True
            log.append("You raise a shimmering guard.")
        else:
            ab = ELDER_ABILITIES.get(key, ELDER_ABILITIES["strike"])
            dmg = ab["power"] + (g["level"] - 1) + _roll(4)
            e["hp"] -= dmg
            log.append(f"You use {ab['label']} for {dmg}!")
        if e["hp"] <= 0:
            return self._win_battle(log)
        incoming = e["atk"]
        if guarding:
            incoming = max(1, incoming // 2)
        g["hp"] -= incoming
        log.append(f"The {e['name']} bumps you for {incoming}.")
        if g["hp"] <= 0:
            return self._lose_battle(log)
        return self._battle_text(log=log)

    def _win_battle(self, log):
        g, e = self._g(), self.enemy
        log.append(e["win"])
        log.append(f"+{e['xp']} XP")
        g["xp"] += e["xp"]
        self.prof["points"] = self.prof.get("points", 0) + e["xp"]
        record_result(g["dda"], True)
        self._flag(f"cleared:{g['scene']}")
        if award(self.prof, "brave_heart", "Brave Heart",
                 "Calmed your first critter"):
            log.append("Achievement unlocked: Brave Heart!")
        log += _maybe_level_up(g)
        if g["level"] >= 5 and award(self.prof, "rising_star", "Rising Star",
                                     "Reached level 5"):
            log.append("Achievement unlocked: Rising Star!")
        self.enemy = None
        self.state = "play"
        if e["boss"]:
            first_win = not self._has("won")
            g["scene"] = len(ELDER_RPG_SCENES)
            self._flag("won")
            log.append("The Wayshrine blazes back to life! The whole Hollow is "
                       "warm and safe again. You did it!")
            if award(self.prof, "wayshrine_relit", "Wayshrine Relit",
                     "Relit the Dimmed Wayshrine"):
                log.append("Achievement unlocked: Wayshrine Relit!")
            if first_win:                        # count it toward unlocking more
                total = record_rpg_completion()
                if games_unlocked():
                    log.append("You've unlocked the whole Game Arcade! 🎉 "
                               "(type /play to see)")
                else:
                    left = RPG_UNLOCK_THRESHOLD - total
                    s = "s" if left != 1 else ""
                    log.append(f"Finish {left} more RPG quest{s} to unlock the "
                               "other games!")
        save_game_profile(self.prof)
        return self._scene_text(log=log)

    def _lose_battle(self, log):
        g = self._g()
        g["hp"] = max(1, g["hp_max"] // 2)         # patched up, never knocked out
        record_result(g["dda"], False)
        self.prof["points"] = self.prof.get("points", 0) + 5   # never zero
        self.enemy = None
        self.state = "play"
        log.append("Oof! You stumble back, dazed but okay — a kindly critter "
                   "helps you up. (+5 points)")
        log.append("Take a breath and try again whenever you're ready.")
        save_game_profile(self.prof)
        return self._scene_text(log=log)

    @staticmethod
    def _parse_int(text):
        m = re.search(r"-?\d+", text or "")
        return int(m.group()) if m else None


# ============================================================================
# RPGQuest — a gentle, AGE-AWARE, self-easing RPG adventure engine. Subclasses
# supply the world (BANNER/TITLE/INTRO/SCENES/ENEMIES/ABILITIES); the engine
# handles explore + numbered-menu combat. Difficulty STARTS from the child's
# age band and AUTO-EASES (with an encouraging hint) whenever they struggle, so
# every quest is winnable. Finishing one calls record_rpg_completion(), which
# is what unlocks the rest of the arcade. Session-based (quick to play); the
# completion count itself is saved family-wide in games-state.json.
# ============================================================================
class RPGQuest:
    screen = True
    rpg = True
    name = "Adventure"
    blurb = "a gentle RPG quest"
    # --- world (subclasses override) ---
    BANNER = ""
    TITLE = "Adventure"
    INTRO = ""
    START_HP = 24
    ABILITIES = {"strike": {"label": "Strike", "power": 6},
                 "guard": {"label": "Guard", "power": 0}}
    START_ABILITIES = ("strike", "guard")
    UNLOCKS = {}            # {level: ability_key}
    HEAL_ITEM = "berry"
    HEAL_LABEL = "Berry"
    SCENES = ()            # [{name, desc, art, critter?{line,gives}, enemy?}]
    ENEMIES = {}           # {key: {name, hp, atk, xp, win, art, boss?}}

    def __init__(self):
        self.over = False
        self.state = "play"
        self.enemy = None
        self._opts = []
        self.scene = 0
        self.level = 1
        self.xp = 0
        self.hp_max = self.START_HP
        self.hp = self.START_HP
        self.abilities = list(self.START_ABILITIES)
        self.inventory = []
        self.flags = set()
        self.ease = 1.0        # adaptive: shrinks (easier) when the kid struggles
        self.losses = 0
        self._recorded = False
        self._intro_shown = False

    # -- contract ------------------------------------------------------------
    def start(self):
        self.__init__()
        return self._scene_text(intro=True)

    @property
    def is_over(self):
        return self.over

    def handle(self, text):
        try:
            if self.state == "battle":
                return self._handle_battle(text)
            return self._handle_play(text)
        except Exception:
            return ("The path twisted for a moment — here we are:\n\n"
                    + self._scene_text())

    # -- helpers -------------------------------------------------------------
    @staticmethod
    def _int(text):
        m = re.search(r"-?\d+", text or "")
        return int(m.group()) if m else None

    def _enemy_mult(self):
        # younger band and/or struggling -> weaker foes; clamped so it's sane.
        return max(0.4, age_difficulty() * self.ease)

    def _screen(self, log=None, title=None, art=None, info=None, opts=None,
                prompt="What will you do?", footer="(type 'quit' to stop)"):
        parts = [self.BANNER]
        for line in (log or []):
            parts.append("")
            parts += [f"  > {x}" for x in _wrap_lines(line, 44, indent="")]
        if title:
            parts += ["", f"  {title}"]
        if art:
            parts.append(_center_block(art))
        for block in (info or []):
            parts.append(block)
        if opts:
            parts += ["", f"  {prompt}"]
            parts += _elder_menu(opts)
        if footer:
            parts += ["", f"  {footer}"]
        return "\n".join(parts)

    # -- exploration ---------------------------------------------------------
    def _cur(self):
        return self.SCENES[self.scene] if self.scene < len(self.SCENES) else None

    def _roam_enemies(self):
        keys = [k for k, e in self.ENEMIES.items() if not e.get("boss")]
        return keys or list(self.ENEMIES)

    def _scene_text(self, log=None, intro=False):
        sc = self._cur()
        notes = []
        if intro and self.INTRO and not self._intro_shown:
            self._intro_shown = True
            notes = _wrap_lines(self.INTRO, 46)
        if sc is None:
            title = f"~ {self.TITLE}: all done! ~"
            art, desc = "", ("You did it! Roam a little more to meet friends, "
                             "or type 'quit' to rest.")
            self._opts = [("roam", "Wander a bit"), ("rest", "Rest a moment")]
        else:
            title = f"~ {sc['name']} ~"
            art, desc = sc.get("art", ""), sc["desc"]
            self._opts = [("onward", "Press onward")]
            if sc.get("critter") and f"met:{self.scene}" not in self.flags:
                self._opts.append(("look", "Look around"))
            self._opts += [("rest", "Rest a moment"), ("pack", "Check your pack")]
        info = list(notes) + ([""] if notes else []) + _wrap_lines(desc, 46)
        return self._screen(log=log, title=title, art=art, info=info,
                            opts=self._opts)

    def _handle_play(self, text):
        n = self._int(text)
        if n is None or not (1 <= n <= len(self._opts)):
            return self._scene_text(log=["Type the number of an option above."])
        key = self._opts[n - 1][0]
        if key == "onward":
            return self._advance()
        if key == "roam":
            return self._begin_battle(random.choice(self._roam_enemies()))
        if key == "look":
            return self._look()
        if key == "rest":
            self.hp = min(self.hp_max, self.hp + 10)
            return self._scene_text(log=[f"You rest a while. (+10 HP, now "
                                         f"{self.hp}/{self.hp_max})"])
        inv = ", ".join(i.upper() for i in self.inventory) or "nothing yet"
        return self._scene_text(log=[f"Your pack: {inv}."])

    def _advance(self):
        sc = self._cur()
        if sc is None:
            return self._begin_battle(random.choice(self._roam_enemies()))
        if sc.get("enemy") and f"cleared:{self.scene}" not in self.flags:
            return self._begin_battle(sc["enemy"])
        self.scene += 1
        msg = ("You follow the path onward..." if self.scene < len(self.SCENES)
               else "You stroll on into the light...")
        return self._scene_text(log=[msg])

    def _look(self):
        sc = self._cur()
        cr = sc.get("critter") if sc else None
        if not cr:
            return self._scene_text(log=["There's no one new to meet here."])
        self.flags.add(f"met:{self.scene}")
        log = [cr["line"]]
        gift = cr.get("gives")
        if gift:
            self.inventory.append(gift)
            log.append(f"You receive a {gift.upper()}!")
        return self._scene_text(log=log)

    # -- combat (numbered menu; never a loss spiral) -------------------------
    def _begin_battle(self, ekey):
        e = self.ENEMIES[ekey]
        mult = self._enemy_mult()
        hp = max(1, int(e["hp"] * mult))
        self.enemy = {"key": ekey, "name": e["name"], "hp": hp, "hp_max": hp,
                      "atk": max(1, int(e["atk"] * mult)), "xp": e["xp"],
                      "win": e["win"], "art": e.get("art", ""),
                      "boss": bool(e.get("boss"))}
        self.state = "battle"
        log = (["Tip: GUARD when you're low, then STRIKE. You've got this!"]
               if self.losses >= 2 else None)
        return self._battle_text(intro=True, log=log)

    def _battle_opts(self):
        opts = [(a, self.ABILITIES[a]["label"]) for a in self.abilities]
        if self.HEAL_ITEM in self.inventory:
            opts.append(("item", f"{self.HEAL_LABEL} (heal)"))
        opts.append(("run", "Slip away"))
        return opts

    def _battle_text(self, intro=False, log=None):
        e = self.enemy
        info = [f"  {e['name']:<12}{_elder_bar(e['hp'], e['hp_max'])}",
                f"  {'You':<12}{_elder_bar(self.hp, self.hp_max)}  Lv{self.level}"]
        self._opts = self._battle_opts()
        title = (f"~ A {e['name']} appears! ~" if intro else f"~ {e['name']} ~")
        return self._screen(log=log, title=title, art=e["art"], info=info,
                            opts=self._opts, prompt="Your move:")

    def _handle_battle(self, text):
        n = self._int(text)
        if n is None or not (1 <= n <= len(self._opts)):
            return self._battle_text(log=["Type the number of one of your moves."])
        return self._battle_turn(self._opts[n - 1][0])

    def _battle_turn(self, key):
        e = self.enemy
        if key == "run":
            self.enemy = None
            self.state = "play"
            return self._scene_text(log=["You slip back down the path — no harm "
                                         "done."])
        log, guarding = [], False
        if key == "item":
            self.inventory.remove(self.HEAL_ITEM)
            self.hp = min(self.hp_max, self.hp + 12)
            log.append(f"You use a {self.HEAL_LABEL.upper()} (+12 HP).")
        elif key == "guard":
            guarding = True
            log.append("You raise a steady guard.")
        else:
            ab = self.ABILITIES.get(key, self.ABILITIES.get(
                "strike", {"label": "Strike", "power": 6}))
            dmg = ab["power"] + (self.level - 1) + random.randint(1, 4)
            e["hp"] -= dmg
            log.append(f"You use {ab['label']} for {dmg}!")
        if e["hp"] <= 0:
            return self._win_battle(log)
        incoming = e["atk"]
        if guarding:
            incoming = max(1, incoming // 2)
        self.hp -= incoming
        log.append(f"The {e['name']} bumps you for {incoming}.")
        if self.hp <= 0:
            return self._lose_battle(log)
        return self._battle_text(log=log)

    def _level_up(self):
        msgs = []
        while self.xp >= self.level * 40:
            self.xp -= self.level * 40
            self.level += 1
            self.hp_max += 5
            self.hp = self.hp_max
            new = self.UNLOCKS.get(self.level)
            if new and new not in self.abilities:
                self.abilities.insert(max(0, len(self.abilities) - 1), new)
                msgs.append(f"Level {self.level}! You learned "
                            f"{self.ABILITIES[new]['label']}!")
            else:
                msgs.append(f"Level {self.level}! You feel stronger.")
        return msgs

    def _win_battle(self, log):
        e = self.enemy
        log += [e["win"], f"+{e['xp']} XP"]
        self.xp += e["xp"]
        self.losses = 0
        self.ease = min(1.0, self.ease + 0.1)      # drift back to normal on a win
        self.flags.add(f"cleared:{self.scene}")
        log += self._level_up()
        boss = e["boss"]
        self.enemy = None
        self.state = "play"
        if boss:
            self.scene = len(self.SCENES)
            self.flags.add("won")
            log.append(f"The {self.TITLE} is saved — you did it! 🌟")
            if not self._recorded:
                self._recorded = True
                total = record_rpg_completion()
                if games_unlocked():
                    log.append("You've unlocked the whole Game Arcade! 🎉 "
                               "(type /play to see)")
                else:
                    left = RPG_UNLOCK_THRESHOLD - total
                    s = "s" if left != 1 else ""
                    log.append(f"Finish {left} more RPG quest{s} to unlock the "
                               "other games!")
        return self._scene_text(log=log)

    def _lose_battle(self, log):
        self.hp = max(1, self.hp_max // 2)         # patched up, never knocked out
        self.losses += 1
        self.ease = max(0.45, self.ease * 0.8)     # adaptive: easier next time
        self.enemy = None
        self.state = "play"
        log.append("Oof — you stumble back, dazed but okay. A friend helps you "
                   "up.")
        log.append("Don't worry — I'll make this a little easier. You can do "
                   "it!")
        return self._scene_text(log=log)


class TideHollowRPG(RPGQuest):
    name = "Tide Hollow"
    blurb = "a calm seaside quest — make sea friends, soothe the Tide-Keeper"
    BANNER = _ascii_banner("T I D E   H O L L O W", inner=30)
    TITLE = "Tide Hollow"
    INTRO = ("The tide lanterns went dark and the cove is sleepy. Wade in, "
             "make gentle sea friends, and relight the Hollow with kindness!")
    START_HP = 26
    ABILITIES = {
        "splash": {"label": "Splash", "power": 6},
        "bubble": {"label": "Bubble Beam", "power": 10},
        "surge":  {"label": "Tide Surge", "power": 14},
        "guard":  {"label": "Guard", "power": 0},
    }
    START_ABILITIES = ("splash", "guard")
    UNLOCKS = {2: "bubble", 4: "surge"}
    HEAL_ITEM = "kelp-snack"
    HEAL_LABEL = "Kelp Snack"
    SCENES = [
        {"name": "Tide-Pool Steps",
         "desc": "Warm little pools sparkle on the rocks. A sleepy SEAPUP "
                 "naps in a sunbeam and waves a friendly flipper.",
         "art": "    .-~~~-.\n   ( o   o ) zZ\n    '-~~~-'\n   ~~~~~~~~~~~",
         "critter": {"line": "The Seapup yawns and nudges you a snack: "
                             "'Here, take a KELP SNACK!'",
                     "gives": "kelp-snack"}},
        {"name": "Swaying Kelp Grove",
         "desc": "Tall kelp ribbons sway in the gentle current. A bouncy "
                 "DRIFTLING wants to play a bubbly game of tag.",
         "art": "    | | | | |\n    | | | | |\n    o  o  o  o\n   ~~~~~~~~~~~",
         "enemy": "driftling"},
        {"name": "Glimmer Coral Glade",
         "desc": "Soft coral glows pink and gold like tiny lanterns. A cheery "
                 "CRABBO scuttles up to share a treat.",
         "art": "     ( )  ( )\n    ( o    o )\n     ^^    ^^\n   ~~~~~~~~~~~",
         "critter": {"line": "Crabbo clacks happily: 'Friends share! "
                             "A KELP SNACK for you!'",
                     "gives": "kelp-snack"}},
        {"name": "Whispering Deep Current",
         "desc": "The water tugs softly and stars shimmer below. A prickly but "
                 "playful URCHO rolls across the path, just wanting to romp.",
         "art": "    *  |*|  *\n   *( o   o )*\n    *  |*|  *\n   ~~~~~~~~~~~",
         "enemy": "urcho"},
        {"name": "The Dark Lantern Reef",
         "desc": "The great tide lantern stands cold and dark. The lonely "
                 "TIDE-KEEPER curls around it, missing the warm glow.",
         "art": "     .====.\n    | *  * |\n    | T I D|\n    |==||==|\n   __|    |__",
         "enemy": "tide-keeper"},
    ]
    ENEMIES = {
        "driftling": {"name": "Driftling", "hp": 16, "atk": 4, "xp": 22,
                      "win": "The Driftling giggles, blows a happy stream of "
                             "bubbles, and bobs gently aside. ~",
                      "art": "    .-~~~-.\n   ( o   o )\n    '-...-'"},
        "urcho": {"name": "Urcho", "hp": 24, "atk": 6, "xp": 32,
                  "win": "Urcho tires out from all the romping, softens its "
                         "prickles, and rolls off with a sleepy smile.",
                  "art": "    *  |*|  *\n   *( o   o )*\n    *  |*|  *"},
        "tide-keeper": {"name": "Tide-Keeper", "hp": 40, "atk": 8, "xp": 60,
                        "boss": True,
                        "win": "The Tide-Keeper feels your kindness, smiles "
                               "warmly, and sighs a breath of starlight that "
                               "relights every lantern in the Hollow.",
                        "art": "    .------.\n   | ~ () ~ |\n   | T I D E|\n    '------'"},
    }

class EmberPeakRPG(RPGQuest):
    name = "Ember Peak"
    blurb = "a snug volcano quest — befriend fire-pups, cheer the Ember Guardian"
    BANNER = _ascii_banner("E M B E R   P E A K", inner=30)
    TITLE = "Ember Peak"
    INTRO = ("The warm hearth at the top of Ember Peak has gone cold and dim. "
             "Climb up, make cozy friends, and relight the glow!")
    START_HP = 26
    ABILITIES = {
        "spark":  {"label": "Spark Tap", "power": 6},
        "glow":   {"label": "Glow Puff", "power": 10},
        "blaze":  {"label": "Cozy Blaze", "power": 14},
        "guard":  {"label": "Guard", "power": 0},
    }
    START_ABILITIES = ("spark", "guard")
    UNLOCKS = {2: "glow", 4: "blaze"}
    HEAL_ITEM = "cocoa-bun"
    HEAL_LABEL = "Cocoa Bun"
    SCENES = [
        {"name": "Warm Trailhead",
         "desc": "Soft red stones make a cozy path up the peak. A sleepy "
                 "EMBERPUP naps in a patch of sunshine.",
         "art": "      .-~~~-.\n     ( ^   ^ ) z\n      '-~~~-'",
         "critter": {"line": "The Emberpup wiggles: 'Here, have a COCOA BUN!'",
                     "gives": "cocoa-bun"}},
        {"name": "Steam Gardens",
         "desc": "Warm steam curls up between the rocks. A bouncy CINDERLING "
                 "wants to play a hopping game with you.",
         "art": "    ( ( ( ) ) )\n     ( o   o )\n      ~ ~ ~ ~", "enemy": "cinderling"},
        {"name": "Lantern Ledge",
         "desc": "Tiny glow-stones light a snug ledge. A kind PEBBLO holds "
                 "out a warm treat.",
         "art": "      [ o o ]\n     ( ===== )\n      *  *  *",
         "critter": {"line": "Pebblo rumbles softly: 'A COCOA BUN, just for you!'",
                     "gives": "cocoa-bun"}},
        {"name": "Smoky Hollow",
         "desc": "Puffs of cozy smoke drift by. A grumbly LAVALUMP flops in "
                 "the way, only wanting attention.",
         "art": "     ( =   = )\n    (  o o o  )\n     ( _____ )", "enemy": "lavalump"},
        {"name": "The Cold Hearth",
         "desc": "The great hearth at the peak sits dark and chilly. The "
                 "lonely EMBER GUARDIAN waits beside it.",
         "art": "      .-----.\n     | *   * |\n     |  ===  |\n      '--^--'", "enemy": "ember-guardian"},
    ]
    ENEMIES = {
        "cinderling": {"name": "Cinderling", "hp": 16, "atk": 4, "xp": 22,
                       "win": "The Cinderling giggles, spins, and tumbles away "
                              "in a happy puff of warm sparks. ~",
                       "art": "     ( o   o )\n      ( ^^^ )\n       ~ ~ ~"},
        "lavalump": {"name": "Lavalump", "hp": 24, "atk": 6, "xp": 32,
                     "win": "Lavalump yawns a cozy yawn, smiles, and squishes "
                            "aside so you can pass.",
                     "art": "    (  o o  )\n   ( ~~~~~~~ )\n    ( _____ )"},
        "ember-guardian": {"name": "Ember Guardian", "hp": 40, "atk": 8, "xp": 60,
                           "boss": True,
                           "win": "The Ember Guardian's frown melts into a warm "
                                  "smile. With a happy sigh it breathes a soft "
                                  "golden glow and relights the hearth.",
                           "art": "      .-----.\n     | ^   ^ |\n     |  ===  |\n      '-----'"},
    }

class FrostfallRPG(RPGQuest):
    name = "Frostfall"
    blurb = "a cozy winter quest — befriend snow critters, warm the shy Snow Warden"
    BANNER = _ascii_banner("F R O S T F A L L", inner=30)
    TITLE = "Frostfall Valley"
    INTRO = ("The snow lanterns have dimmed and Frostfall sleeps under the drifts. "
             "Step into the valley, make fluffy friends, and twinkle the lights awake!")
    START_HP = 26
    ABILITIES = {
        "toss":   {"label": "Snow Toss", "power": 6},
        "flurry": {"label": "Flurry Puff", "power": 10},
        "aurora": {"label": "Aurora Glow", "power": 14},
        "guard":  {"label": "Guard", "power": 0},
    }
    START_ABILITIES = ("toss", "guard")
    UNLOCKS = {2: "flurry", 4: "aurora"}
    HEAL_ITEM = "cocoa-cookie"
    HEAL_LABEL = "Cocoa Cookie"
    SCENES = [
        {"name": "Mitten Gate",
         "desc": "A little gate of frosted pinecones sparkles. A sleepy SNOWPUP "
                 "naps in a cozy mitten of snow.",
         "art": "     .-~~~-.\n    ( o   o )  zZ\n     '-~~~-'",
         "critter": {"line": "The Snowpup wiggles: 'Brr, here, have a COCOA COOKIE!'",
                     "gives": "cocoa-cookie"}},
        {"name": "Pine Drift",
         "desc": "Tall snowy pines whisper. A bouncy PUFFLING wants to have a "
                 "friendly snowball romp with you.",
         "art": "      .^.\n     (***)\n      |T|\n   ~~~~~~~~~~", "enemy": "puffling"},
        {"name": "Crystal Hollow",
         "desc": "Icicles glow soft and blue. A kind MITTENMOLE pops up with a treat.",
         "art": "      ( oo )\n     <(    )>\n      ^^  ^^",
         "critter": {"line": "Mittenmole squeaks: 'A warm COCOA COOKIE, just for you!'",
                     "gives": "cocoa-cookie"}},
        {"name": "Frozen Brook",
         "desc": "A frosty brook crackles. A shivery FROSTNIP hops in the path, "
                 "only wanting to play.",
         "art": "     *  .  *\n    .( o o ).\n     *  .  *", "enemy": "frostnip"},
        {"name": "The Dim Lantern",
         "desc": "The great snow lantern has gone dark. The shy, chilly SNOW "
                 "WARDEN curls beside it, all alone.",
         "art": "      .====.\n     | *  * |\n     | snow |\n   __|====|__", "enemy": "snow-warden"},
    ]
    ENEMIES = {
        "puffling": {"name": "Puffling", "hp": 16, "atk": 4, "xp": 22,
                     "win": "The Puffling laughs, poofs into a swirl of soft "
                            "snowflakes, and drifts away happy. *",
                     "art": "     .-~~-.\n    ( o  o )\n     '~~~~'"},
        "frostnip": {"name": "Frostnip", "hp": 24, "atk": 6, "xp": 32,
                     "win": "Frostnip shakes the frost off its ears, gives a "
                            "tiny smile, and hops aside to let you pass.",
                     "art": "     *  .  *\n    .( o o ).\n     *  .  *"},
        "snow-warden": {"name": "Snow Warden", "hp": 40, "atk": 8, "xp": 60,
                        "boss": True,
                        "win": "The Snow Warden feels your warm cocoa kindness, "
                               "stops shivering, and smiles — the lanterns "
                               "twinkle awake and Frostfall yawns hello!",
                        "art": "     .------.\n    | *    * |\n    | warden |\n     '------'"},
    }


# ---- LUMEN QUEST: the 3 region quests merged into ONE game (pick a region) ---
QUEST_REGIONS = [TideHollowRPG, EmberPeakRPG, FrostfallRPG]
# Pixel-art region emblems (sea / fire / snow), shown on the region-select.
REGION_EMBLEMS = [
    "   ▄███▄   ▄███▄\n"
    "  ▒▓█████▓▒▓█████▓▒\n"
    "  ░▒▓███▓▒░▒▓███▓░\n"
    "  ~~~~~~~~~~~~~~~~~",
    "       ▄█▄\n"
    "      ▄███▄\n"
    "    ▄███████▄\n"
    "   ▄█████████▄\n"
    "   ░▒▓█████▓▒░",
    "   *   *   *   *\n"
    "     ▄███████▄\n"
    "    ▄█████████▄\n"
    "    ░▒▓▓▓▓▓▓▓▒░\n"
    "   *   *   *   *",
]


class RegionQuest:
    """The anime RPG, merged: one game with three regions (Tide Hollow, Ember
    Peak, Frostfall). Pick a region, then this delegates all play to that
    region's adventure. Each region still records its own RPG completion."""

    name = "Lumen Quest"
    blurb = "a gentle anime RPG — pick a region (sea, fire or snow) and save it"
    screen = True
    rpg = True

    def __init__(self):
        self.over = False
        self.state = "region"
        self.quest = None

    def start(self):
        self.__init__()
        return self._region_screen()

    @property
    def is_over(self):
        return self.quest.is_over if self.quest else self.over

    def handle(self, text):
        if self.state == "region":
            return self._pick_region(text)
        return self.quest.handle(text)

    def _region_screen(self, note=None):
        parts = [_ascii_banner("L U M E N   Q U E S T", inner=30), ""]
        if note:
            parts += [f"  > {note}", ""]
        parts += _wrap_lines("Three worlds need your light! Pick a region — each "
                             "is its own gentle quest to relight a world.", 50)
        parts += ["", "  Choose a region:"]
        for i, cls in enumerate(QUEST_REGIONS, 1):
            parts.append(f"  {i})  {cls.TITLE}")
            parts.append(_center_block(REGION_EMBLEMS[i - 1], 40))
            parts += _wrap_lines(cls.blurb, 48, indent="      ")
        parts += ["", "  Type 1, 2 or 3.   (type 'quit' to leave)"]
        return "\n".join(parts)

    def _pick_region(self, text):
        m = re.search(r"\d+", text or "")
        if not m or not (1 <= int(m.group()) <= len(QUEST_REGIONS)):
            return self._region_screen(note="Type 1, 2 or 3 to pick a region.")
        self.quest = QUEST_REGIONS[int(m.group()) - 1]()
        self.state = "play"
        return self.quest.start()


# ---- CRITTER KEEPERS: an original creature-collector (catch / raise / evolve)
# All critters, types and art are 100% original (own IP). Pure logic; the chat
# renders every returned string in the green monospace "arcade screen".

CRITTERS_BANNER = _ascii_banner("C R I T T E R   K E E P E R S", inner=32)

# Each critter line is a 2-3 stage evolution: a list of forms (low -> high).
# A "form" is (name, ascii_art). Evolutions trigger at fixed level thresholds.
# Types are gentle, made-up flavors — never used to hurt, only for color.
CRITTERS_EVO_LEVELS = (4, 8)   # evolve when active level reaches these

CRITTERS_DEX = {
    "emberkit": {
        "type": "Cozy Flame",
        "moves": ["Warm Nuzzle", "Spark Hop", "Cinder Spin"],
        "forms": [
            ("Emberkit",
             "       (\\__/)\n"
             "       (=^.^=)  *flick*\n"
             "        (\")(\")  ~ember~"),
            ("Blazewhisk",
             "      /\\___/\\\n"
             "     ( >ww< )  *crackle*\n"
             "      (  ^^  )\n"
             "       ~~^^~~"),
            ("Solarynx",
             "     \\  *  /\n"
             "    -- (oo) --  *radiant*\n"
             "     /( SUN )\\\n"
             "       ~vv~"),
        ],
    },
    "dewpup": {
        "type": "Dewy Splash",
        "moves": ["Bubble Boop", "Puddle Roll", "Mist Veil"],
        "forms": [
            ("Dewpup",
             "       .---.\n"
             "      ( o o )  *drip*\n"
             "       > ~ <\n"
             "        \"\""),
            ("Tidewag",
             "      ~.---.~\n"
             "     ( ^   ^ )  *splash*\n"
             "      \\  v  /\n"
             "       ~~~~~"),
            ("Lagoonix",
             "     ~~~~~~~~~\n"
             "    ( O     O )  *wave*\n"
             "     \\  ___  /\n"
             "      ~~~~~~~"),
        ],
    },
    "sproutling": {
        "type": "Leafy Sprout",
        "moves": ["Petal Pat", "Vine Wiggle", "Sun Soak"],
        "forms": [
            ("Sproutling",
             "        \\|/\n"
             "       ( o o )  *rustle*\n"
             "        \\_-_/\n"
             "         \"\""),
            ("Bloomkin",
             "       @ \\|/ @\n"
             "      ( ^   ^ )  *bloom*\n"
             "       \\  o  /\n"
             "        |||||"),
            ("Verdantle",
             "     @@ \\|/ @@\n"
             "    (  O   O  )  *flourish*\n"
             "     \\ \\___/ /\n"
             "       |||||"),
        ],
    },
    "pebblo": {
        "type": "Pebbly Stone",
        "moves": ["Tumble Tap", "Boulder Hug", "Quartz Gleam"],
        "forms": [
            ("Pebblo",
             "       [=^=]\n"
             "      [ o o ]  *clack*\n"
             "       [___]"),
            ("Cragmole",
             "      [=====]\n"
             "     [ ^   ^ ]  *rumble*\n"
             "     [  ___  ]\n"
             "      [=====]"),
            ("Geodome",
             "     /=====\\\n"
             "    [ *   * ]  *sparkle*\n"
             "    [ <DIA> ]\n"
             "     \\=====/"),
        ],
    },
    "zephyrkit": {
        "type": "Breezy Air",
        "moves": ["Feather Flit", "Gust Glide", "Cloud Curl"],
        "forms": [
            ("Zephyrkit",
             "       ~v~v~\n"
             "      ( -   - )  *flutter*\n"
             "       \\  w  /\n"
             "        ~~~~"),
            ("Galewing",
             "      \\~v~v~/\n"
             "     ( o   o )  *whoosh*\n"
             "      \\__w__/\n"
             "       /   \\"),
            ("Stratosoar",
             "    \\~~v~v~~/\n"
             "   (  O   O  )  *soar*\n"
             "    \\___w___/\n"
             "     //   \\\\"),
        ],
    },
    "glimmoth": {
        "type": "Glowy Spark",
        "moves": ["Twinkle Tap", "Glow Pulse", "Star Dust"],
        "forms": [
            ("Glimmoth",
             "       .*.*.\n"
             "      ( -.- )  *glow*\n"
             "       \\_v_/"),
            ("Lumifly",
             "      *.*.*.*\n"
             "     ( o   o )  *shimmer*\n"
             "      \\__v__/\n"
             "       *. .*"),
            ("Aurorath",
             "    *.*.*.*.*\n"
             "   (  *   *  )  *dazzle*\n"
             "    \\___v___/\n"
             "     *.* *.*"),
        ],
    },
    "frostnib": {
        "type": "Snowy Chill",
        "moves": ["Snow Pat", "Frost Skip", "Icicle Twirl"],
        "forms": [
            ("Frostnib",
             "       *. .*\n"
             "      ( o.o )  *brr*\n"
             "       \\_-_/"),
            ("Snowlsey",
             "      *.* *.*\n"
             "     ( ^   ^ )  *flurry*\n"
             "      \\__-__/\n"
             "       *. .*"),
            ("Glacien",
             "    *.*.*.*.*\n"
             "   (  o   o  )  *crystal*\n"
             "    \\ <ICE> /\n"
             "     *.* *.*"),
        ],
    },
}

# Wild critters you can meet while exploring (keys into the dex above).
CRITTERS_WILD_KEYS = list(CRITTERS_DEX.keys())
# Three original starters offered at the very beginning.
CRITTERS_STARTERS = ["emberkit", "dewpup", "sproutling"]

def _critters_form_index(level):
    """Which evolution stage (0,1,2) a critter shows at a given level."""
    idx = 0
    for thr in CRITTERS_EVO_LEVELS:
        if level >= thr:
            idx += 1
    return min(idx, 2)


def _critters_make(key, level=1):
    """Build a fresh critter dict from the dex (no shared mutable state)."""
    return {"key": key, "level": level, "xp": 0}


def _critters_name(c):
    forms = CRITTERS_DEX[c["key"]]["forms"]
    return forms[_critters_form_index(c["level"])][0]


def _critters_art(c):
    forms = CRITTERS_DEX[c["key"]]["forms"]
    return forms[_critters_form_index(c["level"])][1]


def _critters_bar(level):
    """A friendly level progress bar toward the next evolution (or 'FINAL')."""
    nxt = None
    for thr in CRITTERS_EVO_LEVELS:
        if level < thr:
            nxt = thr
            break
    if nxt is None:
        return "  Form: FINAL  [##########] top form!"
    prev = 0
    for thr in CRITTERS_EVO_LEVELS:
        if thr <= level:
            prev = thr
    span = nxt - prev
    done = level - prev
    fill = int(round(10 * done / span)) if span else 0
    fill = max(0, min(10, fill))
    return ("  Next form at Lv " + str(nxt) + "  [" + "#" * fill
            + "-" * (10 - fill) + "]")


CRITTERS_DUEL_BANNER = _ascii_banner("C R I T T E R   M E E T", inner=30)

# Treats you can offer during a meeting — every one is kind. Offering a treat to
# a wild critter makes it friendlier (and a little happier); in a friendly spar
# it gives YOUR critter a bit of pep back. Nothing here ever hurts a critter.
CRITTERS_TREATS = ["Sunberry", "Bubble Cake", "Sparkle Nut"]


def _critters_meter(cur, mx, width=10, fill="#", empty="-"):
    """A fixed-width ASCII meter like [####------] (stays aligned in Consolas)."""
    cur = max(0, min(cur, mx))
    n = int(round(width * cur / mx)) if mx else 0
    n = max(0, min(width, n))
    return "[" + fill * n + empty * (width - n) + "]"


def _critters_pep_mx(level):
    """Gentle 'pep' pool — our kid-safe stand-in for health — by level."""
    return 16 + level * 4


def _critters_card(label, pep, pep_mx, extra=""):
    """A two-line status card (name/level line + a pep bar), returned as one
    block so _center_block keeps the picture-above / text-below layout tidy."""
    line2 = f"pep {_critters_meter(pep, pep_mx)} {pep}/{pep_mx}"
    if extra:
        line2 += "   " + extra
    return label + "\n" + line2


class CritterKeepers:
    """Catch, raise and EVOLVE a team of original critters. Explore the meadow to
    MEET a wild critter on a full battle screen — its picture up top, yours below,
    a four-command menu beneath — then be kind (Play, Spark, Treat, Call) until it
    happily joins you. Train to level up and evolve, Spar in gentle matches where
    critters only ever get sleepy (never hurt), and fill your Critter Dex.
    Endless, offline, deterministic; renders in the green monospace screen."""

    name = "Critter Keepers"
    blurb = ("meet, befriend and EVOLVE a team of original critters on a friendly "
             "battle screen — then fill your Critter Dex (find every kind!)")
    screen = True

    def __init__(self):
        self.over = False           # a collector: ALWAYS endless, never set True
        self.state = "starter"      # starter -> hub -> battle/team_back/dex_back
        self.team = []
        self.active = 0             # index into team
        self.seen = set()           # critter keys spotted while exploring
        self.caught = set()         # critter keys befriended (your Dex)
        # battle scratch (shared by wild meetings and friendly spars)
        self.mode = "wild"          # "wild" (befriend) or "spar" (gentle match)
        self.foe = None
        self.foe_pep = self.foe_pep_mx = 0
        self.you_pep = self.you_pep_mx = 0
        self.spark = 0              # 0..100 charge for the Spark (signature) move
        self.friend = 0             # wild-meeting friendliness gauge
        self.friend_need = 3        # how friendly before a Call succeeds

    # ---- contract ----------------------------------------------------------
    def start(self):
        return self._starter_screen()

    @property
    def is_over(self):
        return self.over

    def handle(self, text):
        if self.state == "starter":
            return self._pick_starter(text)
        if self.state == "battle":
            return self._battle_input(text)
        if self.state in ("team_back", "dex_back"):
            self.state = "hub"          # any input returns from a full-screen view
            return self._hub_screen()
        return self._hub_pick(text)     # state == "hub"

    # ---- starter -----------------------------------------------------------
    def _starter_screen(self, note=None):
        parts = [CRITTERS_BANNER, ""]
        if note:
            parts += [f"  > {note}", ""]
        parts += _wrap_lines("Welcome, Keeper! Pick your very first critter "
                             "friend. They will grow and EVOLVE as you play!", 50)
        parts += [""]
        for i, key in enumerate(CRITTERS_STARTERS, 1):
            d = CRITTERS_DEX[key]
            nm = d["forms"][0][0]
            parts += [f"  {i}) {nm}  ({d['type']})"]
            parts += [d["forms"][0][1], ""]
        parts += ["  Type 1, 2 or 3 to choose.",
                  "", "  (type 'quit' to leave)"]
        return "\n".join(parts)

    def _pick_starter(self, text):
        m = re.search(r"\d+", text or "")
        if not m or not (1 <= int(m.group()) <= len(CRITTERS_STARTERS)):
            return self._starter_screen(note="Type 1, 2 or 3 to pick a friend.")
        key = CRITTERS_STARTERS[int(m.group()) - 1]
        self.team = [_critters_make(key)]
        self.active = 0
        self.seen.add(key)
        self.caught.add(key)            # your first Dex entry
        self.state = "hub"
        nm = _critters_name(self.team[0])
        return self._hub_screen(log=[f"{nm} bounces to your side. You are now a "
                                     "Critter Keeper!"])

    # ---- hub ---------------------------------------------------------------
    def _active(self):
        if not self.team:
            return None
        self.active = max(0, min(self.active, len(self.team) - 1))
        return self.team[self.active]

    def _hub_screen(self, log=None):
        parts = [CRITTERS_BANNER]
        for line in (log or []):
            parts.append("")
            parts += [f"  > {x}" for x in _wrap_lines(line, 46, indent="")]
        c = self._active()
        parts += [""]
        if c:
            d = CRITTERS_DEX[c["key"]]
            parts += [f"  Active: {_critters_name(c)}  Lv {c['level']}"
                      f"  ({d['type']})"]
            parts += [_center_block(_critters_art(c))]
            parts += ["", _critters_bar(c["level"]),
                      f"  XP to next level: {self._xp_need(c) - c['xp']}",
                      f"  Team: {len(self.team)}    "
                      f"Dex: {len(self.caught)}/{len(CRITTERS_DEX)}"]
        parts += ["", "  What would you like to do?"]
        parts += _elder_menu([
            ("explore", "Explore (meet a wild critter)"),
            ("train", "Train"),
            ("team", "Team"),
            ("spar", "Spar"),
            ("dex", "Critter Dex"),
            ("swap", "Swap active"),
        ])
        parts += ["", "  (type 'quit' to leave)"]
        return "\n".join(parts)

    def _hub_pick(self, text):
        m = re.search(r"\d+", text or "")
        choice = int(m.group()) if m else 0
        if choice == 1:
            return self._begin_explore()
        if choice == 2:
            return self._train()
        if choice == 3:
            return self._team_screen()
        if choice == 4:
            return self._begin_spar()
        if choice == 5:
            return self._dex_screen()
        if choice == 6:
            return self._swap()
        return self._hub_screen(log=["Type a number from 1 to 6 to choose."])

    # ---- leveling / evolution ---------------------------------------------
    def _xp_need(self, c):
        return 8 + c["level"] * 4     # gentle, predictable curve

    def _grant_xp(self, c, amount):
        """Add XP; return a list of celebratory log lines for any level-ups /
        evolutions. Never fails, never raises."""
        log = []
        c["xp"] += max(0, amount)
        while c["xp"] >= self._xp_need(c):
            c["xp"] -= self._xp_need(c)
            before = _critters_form_index(c["level"])
            c["level"] += 1
            after = _critters_form_index(c["level"])
            nm = _critters_name(c)
            log.append(f"{nm} grew to Lv {c['level']}!  Great job!")
            if after > before:
                log.append("")
                log.append("*  *  *  EVOLUTION!  *  *  *")
                log.append(f"Your critter evolved into {nm}!")
        return log

    def _train(self):
        c = self._active()
        if not c:
            return self._hub_screen(log=["Befriend a critter first!"])
        gain = random.randint(4, 7)
        moves = CRITTERS_DEX[c["key"]]["moves"]
        move = random.choice(moves)
        log = [f"You practice {move} together. (+{gain} XP)"]
        log += self._grant_xp(c, gain)
        return self._hub_screen(log=log)

    # ---- team --------------------------------------------------------------
    def _team_screen(self):
        parts = [CRITTERS_BANNER, "", "  ~ Your Critter Team ~", ""]
        for i, c in enumerate(self.team):
            d = CRITTERS_DEX[c["key"]]
            star = "*" if i == self.active else " "
            parts += [f" {star}{i + 1}) {_critters_name(c)}  Lv {c['level']}"
                      f"  ({d['type']})"]
        parts += [""]
        parts += _wrap_lines("(* marks your active critter. Use Swap from the "
                             "menu to change who you train and spar with.)", 48)
        parts += ["", "  Type any key, then Enter, to go back.",
                  "", "  (type 'quit' to leave)"]
        # next input returns to the hub
        self.state = "team_back"
        return "\n".join(parts)

    def _swap(self):
        if len(self.team) <= 1:
            return self._hub_screen(log=["You need more than one critter to "
                                         "swap. Try Explore to meet more!"])
        self.active = (self.active + 1) % len(self.team)
        return self._hub_screen(log=[f"{_critters_name(self._active())} is now "
                                     "your active critter!"])

    # ---- battle screen (wild meetings AND friendly spars) ------------------
    def _begin_explore(self):
        c = self._active()
        if not c:
            return self._hub_screen(log=["Befriend a critter first!"])
        key = random.choice(CRITTERS_WILD_KEYS)
        self.seen.add(key)
        self.foe = _critters_make(key, level=max(1, c["level"]))
        d = CRITTERS_DEX[key]
        self.mode = "wild"
        self.state = "battle"
        # a wild critter is easy to win over: a small pep pool and a low,
        # age-scaled friendliness target — being kind ALWAYS gets there.
        self.foe_pep_mx = self.foe_pep = max(8, 12 + self.foe["level"] * 3)
        self.you_pep_mx = self.you_pep = _critters_pep_mx(c["level"])
        self.spark = 0
        self.friend = 0
        self.friend_need = max(2, int(round(3 * age_difficulty())))
        return self._battle_screen(
            log=[f"A wild {d['forms'][0][0]} peeks out of the meadow grass!"])

    def _begin_spar(self):
        c = self._active()
        if not c:
            return self._hub_screen(log=["Befriend a critter first!"])
        key = random.choice(CRITTERS_WILD_KEYS)
        self.foe = _critters_make(key, level=max(1, c["level"]))
        self.mode = "spar"
        self.state = "battle"
        base = _critters_pep_mx(self.foe["level"])
        # a sparring partner's pep scales with the age band (tougher = more pep)
        self.foe_pep_mx = self.foe_pep = max(8, int(round(base * age_difficulty())))
        self.you_pep_mx = self.you_pep = _critters_pep_mx(c["level"])
        self.spark = 0
        self.friend = 0
        return self._battle_screen(
            log=[f"A friendly {_critters_name(self.foe)} wants to play a match!"])

    def _menu(self):
        base = [("play", "Play"), ("spark", "Spark"), ("treat", "Treat")]
        if self.mode == "wild":
            # the kind take on the classic "RUN" slot: Call to befriend, or wave
            # goodbye and leave (so no kid is ever forced to befriend this one).
            return base + [("call", "Call (befriend!)"), ("leave", "Wave goodbye")]
        return base + [("rest", "Rest (end match)")]

    def _battle_screen(self, note=None, log=None):
        c, f = self._active(), self.foe
        df, dc = CRITTERS_DEX[f["key"]], CRITTERS_DEX[c["key"]]
        parts = [CRITTERS_DUEL_BANNER]
        for line in (log or []):
            parts.append("")
            parts += [f"  > {x}" for x in _wrap_lines(line, 46, indent="")]
        if note:
            parts += ["", f"  > {note}"]
        # --- the wild/foe critter: status card up top, picture in the middle --
        if self.mode == "wild":
            foe_extra = ("friend "
                         + _critters_meter(self.friend, self.friend_need, 6, "+", "."))
        else:
            foe_extra = ""
        foe_label = f"{_critters_name(f)}  Lv {f['level']}  ({df['type']})"
        parts += ["", _center_block(
            _critters_card(foe_label, self.foe_pep, self.foe_pep_mx, foe_extra))]
        parts += [_center_block(_critters_art(f))]
        # --- your critter: picture, then your status card --------------------
        parts += [_center_block(_critters_art(c))]
        you_extra = "spark " + _critters_meter(self.spark, 100, 8, "*", ".")
        you_label = f"{_critters_name(c)}  Lv {c['level']}  ({dc['type']})"
        parts += [_center_block(
            _critters_card(you_label, self.you_pep, self.you_pep_mx, you_extra))]
        # --- the four-command menu (a kind take on the classic battle menu) --
        parts += ["", "  What will you do?"]
        parts += _elder_menu(self._menu())
        parts += ["", "  (type 'quit' to stop)"]
        return "\n".join(parts)

    def _battle_input(self, text):
        if not self._active():          # defensive: never act without a critter
            self.state = "hub"
            return self._hub_screen()
        menu = self._menu()
        m = re.search(r"\d+", text or "")
        if not m or not (1 <= int(m.group()) <= len(menu)):
            return self._battle_screen(note=f"Type 1 to {len(menu)} to choose.")
        action = menu[int(m.group()) - 1][0]
        return {
            "play": self._battle_play,
            "spark": self._battle_spark,
            "treat": self._battle_treat,
            "call": self._battle_call,
            "leave": self._battle_leave,
            "rest": self._battle_rest,
        }[action]()

    def _foe_calm(self):
        """A wild critter is ready to befriend once it is comfy with you OR has
        played itself happily sleepy. Kindness always reaches this — eventually."""
        return (self.friend >= self.friend_need
                or self.foe_pep <= max(1, self.foe_pep_mx // 4))

    def _battle_play(self):
        c = self._active()
        move = random.choice(CRITTERS_DEX[c["key"]]["moves"])
        amt = max(3, c["level"] + random.randint(2, 5))
        self.foe_pep = max(0, self.foe_pep - amt)
        self.spark = min(100, self.spark + 25)
        log = [f"{_critters_name(c)} uses {move}!"]
        if self.mode == "wild":
            self.friend += 1            # playing together builds trust
            log.append(f"The wild {_critters_name(self.foe)} giggles and tumbles "
                       "— it's warming up to you.")
            if self._foe_calm():
                log.append("It looks ready to be friends — try Call (4)!")
            return self._battle_screen(log=log)
        # spar: a gentle back-and-forth; the worst case is a happy nap
        if self.foe_pep <= 0:
            return self._spar_win(log)
        return self._foe_turn(log)

    def _battle_spark(self):
        c = self._active()
        sig = CRITTERS_DEX[c["key"]]["moves"][-1]
        if self.spark >= 100:
            self.spark = 0
            log = [f"SPARK MOVE!  {_critters_name(c)} lights up with {sig}!"]
            if self.mode == "wild":
                self.friend += 2
                self.foe_pep = max(0, self.foe_pep
                                   - (c["level"] + random.randint(3, 6)))
                log.append("The wild critter is dazzled — and delighted!")
                if self._foe_calm():
                    log.append("It looks ready to be friends — try Call (4)!")
                return self._battle_screen(log=log)
            self.foe_pep = max(0, self.foe_pep
                               - (c["level"] * 2 + random.randint(5, 9)))
            if self.foe_pep <= 0:
                return self._spar_win(log)
            return self._foe_turn(log)
        # not charged yet — a wind-up that charges the Spark fast
        self.spark = min(100, self.spark + 40)
        log = [f"{_critters_name(c)} winds up — the Spark is charging "
               f"({self.spark}/100)!"]
        if self.mode == "spar":
            return self._foe_turn(log)
        self.friend += 1
        return self._battle_screen(log=log)

    def _battle_treat(self):
        c = self._active()
        treat = random.choice(CRITTERS_TREATS)
        self.spark = min(100, self.spark + 15)
        if self.mode == "wild":
            self.friend += 2
            self.foe_pep = min(self.foe_pep_mx, self.foe_pep + 2)   # a happy snack
            log = [f"You offer a {treat}. The wild {_critters_name(self.foe)} "
                   "nibbles it happily and trusts you more!"]
            if self._foe_calm():
                log.append("It looks ready to be friends — try Call (4)!")
            return self._battle_screen(log=log)
        # spar: the treat refreshes YOUR critter (+4 pep)
        self.you_pep = min(self.you_pep_mx, self.you_pep + 4)
        return self._foe_turn([f"You share a {treat} — {_critters_name(c)} "
                               "perks back up (+4 pep)."])

    def _battle_call(self):
        if not self._foe_calm():
            self.friend += 1            # never a dead end — trust keeps growing
            return self._battle_screen(
                note="Almost! Keep being kind — Play or Treat, then Call again.")
        return self._befriend()

    def _befriend(self):
        c = self._active()
        f = self.foe
        nm = CRITTERS_DEX[f["key"]]["forms"][0][0]
        self.team.append(f)
        new = f["key"] not in self.caught
        self.caught.add(f["key"])
        self.foe = None
        self.state = "hub"
        gain = random.randint(4, 7)
        log = [f"{nm} happily joins your team!  (Team {len(self.team)})"]
        if new:
            log.append(f"New Dex friend!  {len(self.caught)}/{len(CRITTERS_DEX)} "
                       "kinds befriended.")
        log.append(f"(+{gain} XP for your active critter)")
        log += self._grant_xp(c, gain)
        if len(self.caught) >= len(CRITTERS_DEX):
            log.append("")
            log.append("*  *  *  You've befriended EVERY kind of critter — "
                       "you're a Champion Keeper!  *  *  *")
        return self._hub_screen(log=log)

    def _foe_turn(self, log):
        """The sparring partner's gentle reply. It can make your critter sleepy,
        but a happy nap is the worst that ever happens — then you both had fun."""
        f = self.foe
        if random.randint(1, 3) == 2:
            self.foe_pep = min(self.foe_pep_mx, self.foe_pep + 2)
            log.append(f"The {_critters_name(f)} catches its breath (+2 pep).")
        else:
            amt = max(1, f["level"] // 2 + random.randint(1, 3))
            self.you_pep = max(0, self.you_pep - amt)
            log.append(f"The {_critters_name(f)} bounces back playfully.")
        if self.you_pep <= 0:
            return self._spar_nap(log)
        return self._battle_screen(log=log)

    def _spar_win(self, log):
        c = self._active()
        gain = random.randint(5, 8)
        log.append(f"The {_critters_name(self.foe)} yawns a big happy yawn — all "
                   "tuckered out! You win the match!")
        log.append(f"(+{gain} XP)")
        log += self._grant_xp(c, gain)
        self.foe = None
        self.state = "hub"
        return self._hub_screen(log=log)

    def _spar_nap(self, log):
        c = self._active()
        gain = random.randint(2, 4)
        log.append(f"{_critters_name(c)} curls up for a happy little nap. What a "
                   "fun match!")
        log.append(f"You both had fun. (+{gain} XP) Try another match anytime!")
        log += self._grant_xp(c, gain)
        self.foe = None
        self.state = "hub"
        return self._hub_screen(log=log)

    def _battle_rest(self):
        c = self._active()
        gain = random.randint(2, 4)
        self.foe = None
        self.state = "hub"
        log = [f"You both take a rest — good match! (+{gain} XP)"]
        log += self._grant_xp(c, gain)
        return self._hub_screen(log=log)

    def _battle_leave(self):
        nm = _critters_name(self.foe)   # the wild critter stays "seen" in your Dex
        self.foe = None
        self.state = "hub"
        return self._hub_screen(log=[f"You wave goodbye to the wild {nm}. It's "
                                     "noted in your Dex — come back to befriend it!"])

    # ---- Critter Dex -------------------------------------------------------
    def _dex_screen(self):
        parts = [CRITTERS_BANNER, "", "  ~ Critter Dex ~   (find every kind!)", ""]
        for key in CRITTERS_DEX:
            d = CRITTERS_DEX[key]
            base = d["forms"][0][0]
            if key in self.caught:
                parts.append(f"  [*] {base:<12} ({d['type']}) — friend!")
            elif key in self.seen:
                parts.append(f"  [.] {base:<12} ({d['type']}) — seen; befriend it!")
            else:
                parts.append("  [ ] ???          — explore to discover!")
        parts += ["", f"  Befriended {len(self.caught)} of {len(CRITTERS_DEX)} "
                  "kinds of critter."]
        if len(self.caught) >= len(CRITTERS_DEX):
            parts.append("  Champion Keeper — you found them all!")
        parts += ["", "  Type any key, then Enter, to go back.",
                  "", "  (type 'quit' to leave)"]
        self.state = "dex_back"
        return "\n".join(parts)



SPIN_BANNER = _ascii_banner("S P I N   L E A G U E")
# Pixel-art (block-shade) emblem for the title — a glowing spinning blade.
SPIN_EMBLEM = (
    "        ░▒▓▓▓▒░\n"
    "      ░▒▓█████▓▒░\n"
    "      ▒▓███████▓▒\n"
    "      ░▒▓█████▓▒░\n"
    "        ░▒▓▓▓▒░\n"
    "       / /|||\\ \\")

# Spirit-Beast Blades: an ORIGINAL spinner-battle world (own creatures/rivals;
# only the genre's generic mechanics — types, a tournament ladder, special
# finishers — which are not anyone's IP). Pick a blade that channels a spirit
# beast, charge your Spirit Move, and climb the league.

# Type triangle: Attack beats Stamina beats Defense beats Attack.
SPIN_TYPES = {"atk": "Attack", "def": "Defense", "sta": "Stamina"}
SPIN_BEATS = {"atk": "sta", "sta": "def", "def": "atk"}

# Your starter blades: (name, type, atk, guard, sta, desc, special, art)
SPIN_STARTERS = [
    {"name": "Emberwyrm", "type": "atk", "atk": 7, "guard": 4, "sta": 5,
     "desc": "a fiery dragon spirit that loves to charge in",
     "special": "Ember Drive",
     "art": "   ▀█▄     ▄█▀\n  ▒▓█████████▓▒\n  ▒▓██o███o██▓▒\n  ▒▓███▀▀▀███▓▒\n   ░▒▓█████▓▒░"},
    {"name": "Stonemaw", "type": "def", "atk": 4, "guard": 7, "sta": 5,
     "desc": "a rugged rock-bear spirit that shrugs off hits",
     "special": "Bastion Crash",
     "art": "   ██       ██\n  ▓███████████▓\n  ▓██o█████o██▓\n  ▓████▄▄▄████▓\n   ▒▓███████▓▒"},
    {"name": "Galelynx", "type": "sta", "atk": 5, "guard": 4, "sta": 7,
     "desc": "a swift wind-cat spirit that spins and spins",
     "special": "Cyclone Whirl",
     "art": "   █▄       ▄█\n  ░▓█████████▓░\n  ░▓██^███^██▓░\n  ░▓████▄████▓░\n   ░▒▓█████▓▒░"},
]

# The league ladder of ORIGINAL rivals (last one is the Champion).
SPIN_RIVALS = [
    {"name": "Pip", "beast": "Flitmoth", "type": "sta", "atk": 3, "guard": 3,
     "sta": 4, "taunt": "Pip grins: 'You're my first match — let's have fun!'",
     "art": "        vVv\n       ( oo )  ~flit~\n        '-O-'"},
    {"name": "Bo", "beast": "Tuskroller", "type": "def", "atk": 4, "guard": 5,
     "sta": 4, "taunt": "Bo rumbles: 'My guard is a wall — try and crack it!'",
     "art": "       ( OO )\n       [ tusk ]  *roll*\n        '-O-'"},
    {"name": "Vega", "beast": "Volthawk", "type": "atk", "atk": 6, "guard": 3,
     "sta": 4, "taunt": "Vega smirks: 'Too slow! Volthawk strikes first!'",
     "art": "        ^v^\n       ( >< )  ~zap~\n        '-O-'"},
    {"name": "Mira", "beast": "Tideserpent", "type": "sta", "atk": 5,
     "guard": 4, "sta": 6, "taunt": "Mira says calmly: 'Patience wins races.'",
     "art": "        ~s~\n       ( oo )  ~wave~\n        '-O-'"},
    {"name": "Cass", "beast": "Thornbeetle", "type": "def", "atk": 6,
     "guard": 6, "sta": 5, "taunt": "Cass clicks: 'Bounce right off my thorns!'",
     "art": "       ><><\n       ( -- )  *click*\n        '-O-'"},
    {"name": "Ryker", "beast": "Stormdrake", "type": "atk", "atk": 8,
     "guard": 6, "sta": 7,
     "taunt": "Ryker, the League Champion: 'Show me your spirit!'",
     "art": "       (>OO<)\n      < DRAKE >  ~BOOM~\n        =(O)="},
]

SPIN_PARTS = [("Razor Rim (+2 Attack)", 0, 2), ("Bulwark Ring (+2 Guard)", 1, 2),
              ("Flywheel Core (+2 Stamina)", 2, 2)]


def _spin_bar(cur, mx, width=14):
    cur = max(0, min(cur, mx))
    fill = int(round(width * cur / mx)) if mx else 0
    return "[" + "#" * fill + "-" * (width - fill) + f"] {cur}/{mx}"


def _spin_meter(spirit, width=10):
    fill = int(round(width * min(100, spirit) / 100))
    tag = "  CHARGED!" if spirit >= 100 else ""
    return "[" + "*" * fill + "." * (width - fill) + "]" + tag


def _spin_edge(att_type, def_type):
    if SPIN_BEATS.get(att_type) == def_type:
        return 1            # advantage
    if SPIN_BEATS.get(def_type) == att_type:
        return -1           # disadvantage
    return 0


class SpinLeague:
    name = "Spin League"
    blurb = ("build a Spirit-Beast blade and climb the league — type matchups, "
             "rival battles, and a chargeable Spirit Move")
    screen = True
    always = True       # always playable (no RPG unlock needed), shown up top

    def __init__(self):
        self.over = False
        self.state = "pick"
        self.tname = ""          # your blade / spirit-beast
        self.ptype = "atk"
        self.pspecial = ""
        self.stats = [0, 0, 0]
        self.rung = self.wins = self.losses = 0
        self.lap = 1
        self.ease = 1.0          # adaptive: gentler rivals after a loss
        self.you = self.you_mx = self.foe = self.foe_mx = 0
        self.spirit = 0
        self.rname = ""
        self.rtype = "atk"
        self.rs = [0, 0, 0]
        self._lost = False

    def start(self):
        return self._pick()

    @property
    def is_over(self):
        return self.over

    def handle(self, text):
        if self.state == "pick":
            return self._do_pick(text)
        if self.state == "reward":
            return self._do_reward(text)
        return self._round(text)

    # -- choose your blade ---------------------------------------------------
    def _pick(self, note=None):
        p = [SPIN_BANNER, "", _center_block(SPIN_EMBLEM), ""]
        if note:
            p += [f"  > {note}", ""]
        p += _wrap_lines("Welcome to the Spin League! Every blade carries a "
                         "spirit beast. Pick yours, then climb the rival ladder "
                         "to the Champion.", 50)
        p += ["", "  Type beats type:  Attack > Stamina > Defense > Attack", ""]
        p += ["  Choose your blade:"]
        for i, s in enumerate(SPIN_STARTERS):
            p.append(f"  {i + 1}) {s['name']}  [{SPIN_TYPES[s['type']]}]")
            p.append(_center_block(s["art"], 40))
            p.append(f"     ATK {s['atk']}  GUARD {s['guard']}  STA {s['sta']}")
            p += _wrap_lines(s["desc"] + f"  Spirit Move: {s['special']}.", 46,
                             indent="     ")
        p += ["", "  Type 1, 2 or 3.   (type 'quit' to leave)"]
        return "\n".join(p)

    def _do_pick(self, text):
        m = re.search(r"\d+", text or "")
        if not m or not (1 <= int(m.group()) <= len(SPIN_STARTERS)):
            return self._pick(note="Type 1, 2 or 3 to pick a blade.")
        s = SPIN_STARTERS[int(m.group()) - 1]
        self.tname = s["name"]
        self.ptype = s["type"]
        self.pspecial = s["special"]
        self.stats = [s["atk"], s["guard"], s["sta"]]
        self.state = "battle"
        self._new_match()
        rv = SPIN_RIVALS[self.rung]
        return self._battle([f"You spin up {self.tname}!", rv["taunt"]])

    # -- matches -------------------------------------------------------------
    def _new_match(self):
        rv = SPIN_RIVALS[self.rung]
        b = (self.lap - 1) * 2
        self.rname = rv["name"]
        self.rtype = rv["type"]
        self.rs = [rv["atk"] + b, rv["guard"] + b, rv["sta"] + b]
        base = 18 + self.rs[2] * 2 + self.rung * 3
        # rival energy scales with the age band AND auto-eases after a loss
        self.foe_mx = self.foe = max(8, int(base * age_difficulty() * self.ease))
        self.you_mx = self.you = 20 + self.stats[2] * 2
        self.spirit = 0

    def _round(self, text):
        m = re.search(r"\d+", text or "")
        if not m or not (1 <= int(m.group()) <= 3):
            return self._battle(["Type 1, 2 or 3 to choose a move."])
        c = int(m.group())
        rv = SPIN_RIVALS[self.rung]
        bonus = {1: 3, 0: 0, -1: -2}[_spin_edge(self.ptype, self.rtype)]
        log = []
        if c == 1:                                    # Strike
            d = max(2, self.stats[0] + random.randint(0, 4)
                    - max(0, self.rs[1] - 4) + bonus)
            self.foe -= d
            self.spirit = min(100, self.spirit + 30)
            log.append(f"{self.tname} strikes for {d}!"
                       + (" Type edge!" if bonus > 0 else ""))
        elif c == 2:                                  # Guard
            d = max(1, self.stats[1] - 2 + random.randint(0, 2))
            self.foe -= d
            self.you = min(self.you_mx, self.you + 2)
            self.spirit = min(100, self.spirit + 22)
            log.append(f"You brace — chip {d}, steady your spin (+2), and the "
                       "spirit charges.")
        else:                                         # Spirit Move
            if self.spirit >= 100:
                d = (self.stats[0] + self.stats[2] // 2 + random.randint(3, 7)
                     + 8 + bonus)
                self.foe -= d
                self.spirit = 0
                log.append(f"SPIRIT MOVE!  {self.tname} unleashes {self.pspecial} "
                           f"— the spirit blazes out for {d}!")
            else:
                d = max(2, self.stats[0] // 2 + random.randint(0, 3))
                self.foe -= d
                self.spirit = min(100, self.spirit + 45)
                log.append(f"You wind up — the spirit stirs (+{d}, charging "
                           "fast!).")
        if self.foe <= 0:
            self.foe = 0
            return self._win(log)
        # rival's turn (gentle; it can never knock you out for good)
        rb = {1: 3, 0: 0, -1: -2}[_spin_edge(self.rtype, self.ptype)]
        f = random.randint(1, 3)
        if f == 2:
            self.foe = min(self.foe_mx, self.foe + 2)
            log.append(f"{self.rname}'s {rv['beast']} steadies (+2).")
        else:
            fd = max(1, self.rs[0] + random.randint(0, 3)
                     - max(0, self.stats[1] - 4) + rb)
            self.you -= fd
            log.append(f"{self.rname}'s {rv['beast']} whirls in for {fd}.")
        if self.you <= 0:
            self.you = 0
            return self._lose(log)
        return self._battle(log)

    def _win(self, log):
        rv = SPIN_RIVALS[self.rung]
        log.append(f"{self.rname}'s {rv['beast']} wobbles to a stop — you WIN!")
        self.wins += 1
        self._lost = False
        self.ease = min(1.0, self.ease + 0.1)
        self.state = "reward"
        if self.rung == len(SPIN_RIVALS) - 1:
            head = "  *** LEAGUE CHAMPION!  You beat the champ! ***"
            blurb = ("You're the Spin League Champion! Take a victory upgrade — "
                     "then a tougher new season begins:")
        else:
            head = "  *** VICTORY! You earned an upgrade part! ***"
            blurb = "Bolt a part onto your blade for the climb ahead:"
        return self._reward(log, head, blurb)

    def _lose(self, log):
        log.append(f"{self.tname} slows down first this time — good match!")
        self._lost = True
        self.losses += 1
        self.ease = max(0.5, self.ease * 0.8)     # adaptive: gentler rematch
        self.state = "reward"
        return self._reward(
            log, "  Good match! Tune up and rematch — I'll make it a little "
                 "easier. You've got this!",
            "Take a practice part to get stronger, then rematch:")

    def _reward(self, log, head, blurb):
        p = [SPIN_BANNER]
        for line in log:
            p.append("")
            p += [f"  > {x}" for x in _wrap_lines(line, 46, indent="")]
        p += ["", head, ""]
        p += _wrap_lines(blurb, 50)
        p += _elder_menu([(str(i), lbl) for i, (lbl, _, _) in enumerate(SPIN_PARTS)])
        p += ["", "  Type 1, 2 or 3.   (type 'quit' to stop)"]
        return "\n".join(p)

    def _do_reward(self, text):
        m = re.search(r"\d+", text or "")
        if not m or not (1 <= int(m.group()) <= len(SPIN_PARTS)):
            return self._reward([], "  Choose a part:",
                                "Type 1, 2 or 3 to upgrade your blade.")
        _, idx, amt = SPIN_PARTS[int(m.group()) - 1]
        self.stats[idx] += amt
        won = not self._lost
        self._lost = False
        log = ["You bolt on a new part. Your blade feels stronger!"]
        if won:
            self.rung += 1
            if self.rung >= len(SPIN_RIVALS):
                self.rung = 0
                self.lap += 1
                log.append(f"A new season begins — Lap {self.lap}! The rivals "
                           "come back tougher.")
            else:
                log.append("You climb to the next rung of the league!")
        else:
            log.append("Time for a rematch — you've got this!")
        self.state = "battle"
        self._new_match()
        rv = SPIN_RIVALS[self.rung]
        log.append(f"Next up: {self.rname} & {rv['beast']} "
                   f"[{SPIN_TYPES[rv['type']]}]!")
        return self._battle(log)

    def _battle(self, log=None):
        rv = SPIN_RIVALS[self.rung]
        info = [
            f"  League rung {self.rung + 1}/{len(SPIN_RIVALS)}   Lap {self.lap}"
            f"   Wins {self.wins}",
            "",
            _center_block(rv["art"], 40),
            f"  RIVAL: {self.rname} & {rv['beast']}  [{SPIN_TYPES[rv['type']]}]",
            f"         {_spin_bar(self.foe, self.foe_mx)}",
            "",
            f"  YOU:   {self.tname}  [{SPIN_TYPES[self.ptype]}]",
            f"         {_spin_bar(self.you, self.you_mx)}",
            f"         Spirit {_spin_meter(self.spirit)}",
            f"         ATK {self.stats[0]}  GUARD {self.stats[1]}"
            f"  STA {self.stats[2]}",
        ]
        p = [SPIN_BANNER]
        for line in (log or []):
            p.append("")
            p += [f"  > {x}" for x in _wrap_lines(line, 46, indent="")]
        p += [""] + info
        p += ["", "  Your move:"]
        p += _elder_menu([("1", "Strike"), ("2", "Guard"),
                          ("3", "Spirit Move")])
        p += ["", "  (type 'quit' to stop)"]
        return "\n".join(p)


WILD_BANNER = _ascii_banner("W I L D   T R A I L S")

# Each habitat: (key, display name, scene caption, [animals]).
# Each animal: (name, true kid-fact, question, [(option, is_correct), ...], after-fact)
# EVERY fact and EVERY correct answer is real-world accurate and kid-appropriate.
WILD_HABITATS = [
    ("savanna", "African Savanna", "~ golden grass under a wide sky ~", [
        ("Giraffe",
         "A giraffe is the tallest animal on Earth. Its neck "
         "alone can be over 2 metres (6 feet) long!",
         "How many bones are in a giraffe's long neck?",
         [("Just 7 — the same as you", True),
          ("Exactly 100 tiny bones", False),
          ("None — it is all muscle", False)],
         "True! A giraffe has 7 neck bones, like us — each "
         "one is just very large."),
        ("African Elephant",
         "The African elephant is the largest land animal "
         "alive today. It uses its trunk like a hand and a nose.",
         "What does an elephant mainly use its trunk for?",
         [("Breathing, smelling, and grabbing food", True),
          ("Hearing far-away sounds", False),
          ("Seeing in the dark", False)],
         "Yes! The trunk smells, breathes, drinks, and even "
         "picks up tiny things like a single blade of grass."),
        ("Cheetah",
         "The cheetah is the fastest land animal. It can "
         "sprint up to about 110 km/h (70 mph) for short bursts.",
         "What is the cheetah the fastest at?",
         [("Running on land", True),
          ("Swimming in rivers", False),
          ("Flying in the sky", False)],
         "Correct! No land animal can out-run a cheetah over "
         "a short dash."),
    ]),
    ("rainforest", "Rainforest", "~ green leaves drip in warm mist ~", [
        ("Toucan",
         "A toucan has a huge, light beak. The big beak helps "
         "it reach fruit and stay cool in the heat.",
         "What is a toucan's giant beak good for?",
         [("Reaching fruit and cooling down", True),
          ("Digging deep tunnels", False),
          ("Catching fish in the sea", False)],
         "Right! The hollow beak is light, helps grab fruit, "
         "and lets out body heat."),
        ("Poison Dart Frog",
         "Poison dart frogs are tiny and very bright. Their "
         "bold colours warn other animals: 'do not eat me!'",
         "Why are poison dart frogs so brightly coloured?",
         [("To warn that they are not safe to eat", True),
          ("To hide from the sun", False),
          ("To look like flowers for fun", False)],
         "Yes! Bright colours are a warning sign in nature."),
        ("Sloth",
         "A sloth moves very slowly and sleeps a lot. Green "
         "algae can even grow on its fur, helping it hide.",
         "Why does a sloth move so slowly?",
         [("It saves energy on its leafy diet", True),
          ("It is always sleepy from candy", False),
          ("Its legs are made of stone", False)],
         "Correct! Leaves give little energy, so the sloth "
         "takes life nice and slow."),
    ]),
    ("arctic", "Arctic", "~ white snow shines on quiet ice ~", [
        ("Polar Bear",
         "Polar bears live in the frozen Arctic. Under their "
         "white-looking fur, their skin is actually black.",
         "What colour is polar bear skin under the fur?",
         [("Black", True),
          ("Bright blue", False),
          ("Snow white", False)],
         "True! Black skin soaks up the sun's warmth in the "
         "cold north."),
        ("Arctic Fox",
         "The Arctic fox grows a thick white coat in winter "
         "so it blends into the snow and stays cosy and warm.",
         "Why does the Arctic fox turn white in winter?",
         [("To blend into the snow", True),
          ("Because it is very old", False),
          ("To glow in the dark", False)],
         "Yes! A white coat helps it hide in the snowy land."),
        ("Snowy Owl",
         "The snowy owl hunts in the day and night. It can "
         "turn its head far around to look all about for food.",
         "How does a snowy owl look all around itself?",
         [("By turning its head very far", True),
          ("By spinning its whole body", False),
          ("By flapping its tail feathers", False)],
         "Correct! Owls turn their heads to see, because "
         "their eyes cannot roll like ours."),
    ]),
    ("reef", "Coral Reef", "~ blue water full of darting fish ~", [
        ("Clownfish",
         "A clownfish lives safely among the stinging arms of "
         "a sea anemone. The sting does not hurt the clownfish.",
         "Where does a clownfish like to live?",
         [("Among a sea anemone's arms", True),
          ("Inside a dry sandy cave", False),
          ("High up in a tall tree", False)],
         "Right! The anemone keeps the clownfish safe from "
         "bigger fish."),
        ("Sea Turtle",
         "Sea turtles breathe air but live in the ocean. They "
         "can hold their breath underwater for a long time.",
         "How does a sea turtle breathe?",
         [("It breathes air at the surface", True),
          ("It breathes water like a fish", False),
          ("It does not need to breathe", False)],
         "Yes! Turtles come up for air, then dive back down "
         "for a long while."),
        ("Octopus",
         "An octopus has eight arms and is very clever. It "
         "can change colour to blend in and hide quickly.",
         "How many arms does an octopus have?",
         [("Eight", True),
          ("Two", False),
          ("Twenty", False)],
         "Correct! 'Octo' means eight — eight bendy arms."),
    ]),
    ("outback", "Australian Outback", "~ red earth under a hot sun ~", [
        ("Kangaroo",
         "A kangaroo hops on strong back legs. A baby kangaroo, "
         "called a joey, rides safely in its mother's pouch.",
         "What is a baby kangaroo called?",
         [("A joey", True),
          ("A puppy", False),
          ("A cub", False)],
         "True! A tiny joey grows up snug in mum's pouch."),
        ("Emu",
         "The emu is a tall bird that cannot fly. Instead it "
         "runs very fast on its long, strong legs.",
         "What does an emu do instead of flying?",
         [("It runs fast on land", True),
          ("It swims across oceans", False),
          ("It floats on the wind", False)],
         "Yes! Emus are big running birds, like ostriches."),
        ("Koala",
         "A koala sleeps up to 20 hours a day. It eats "
         "eucalyptus leaves, which take a lot of rest to digest.",
         "Why does a koala sleep so much?",
         [("Its leafy food takes lots of rest to digest", True),
          ("It is scared of the daytime", False),
          ("It is dreaming of the ocean", False)],
         "Correct! Eucalyptus leaves are tough, so the koala "
         "rests to save energy."),
    ]),
    ("antarctica", "Antarctica", "~ icy wind over a frozen shore ~", [
        ("Emperor Penguin",
         "Emperor penguins are the tallest penguins. They "
         "huddle together in big groups to stay warm in winter.",
         "How do emperor penguins keep warm in the cold?",
         [("They huddle close together", True),
          ("They light a little fire", False),
          ("They fly south to the beach", False)],
         "True! Taking turns on the warm inside of the huddle "
         "keeps the whole group cosy."),
        ("Weddell Seal",
         "The Weddell seal can dive deep under the ice to hunt "
         "fish, then come back to breathing holes for air.",
         "Where does a Weddell seal get its air?",
         [("From holes in the ice", True),
          ("From under the deep mud", False),
          ("It never needs any air", False)],
         "Yes! Seals keep breathing holes open in the ice."),
        ("Krill",
         "Krill are tiny shrimp-like animals. Huge whales eat "
         "enormous amounts of them, so krill feed the ocean.",
         "Why are tiny krill so important?",
         [("Big whales and many animals eat them", True),
          ("They build nests in trees", False),
          ("They are the largest animal", False)],
         "Correct! Small krill help feed some of the biggest "
         "animals on Earth."),
    ]),
]


class WildTrails:
    """A wildlife explorer. Pick a real habitat, meet real animals, learn one
    true fact each, and answer a 3-way quiz. Right or wrong, the correct answer
    is revealed and a stamp is earned — no losing, ever. Offline + deterministic.
    Renders in the big monospace game screen."""

    name = "Wild Trails"
    blurb = "explore real habitats and learn amazing animal facts"
    screen = True

    def __init__(self):
        self.over = False
        self.state = "map"          # "map" -> "quiz"
        self.stamps = 0
        self.seen = set()           # (habitat_key, animal_index) already stamped
        self.hab = None             # current habitat tuple
        self.ai = 0                 # current animal index within the habitat

    def start(self):
        return self._map_screen(note="Pick a trail to begin your adventure!")

    @property
    def is_over(self):
        return self.over            # endless; the app handles 'quit'

    def handle(self, text):
        if self.state == "quiz":
            return self._answer(text)
        return self._pick_habitat(text)

    # ----- map / habitat picker ---------------------------------------------
    def _habitat_rows(self):
        labels = []
        for k, nm, _cap, animals in WILD_HABITATS:
            done = sum(1 for i in range(len(animals)) if (k, i) in self.seen)
            mark = " *" if done == len(animals) else ""
            labels.append((k, f"{nm} ({done}/{len(animals)}){mark}"))
        return _elder_menu(labels)

    def _map_screen(self, note=None):
        parts = [WILD_BANNER, ""]
        if note:
            parts += [f"  > {note}", ""]          # note never holds the kid's raw text
        parts += _wrap_lines(
            "Welcome, explorer! Travel to real habitats and "
            "meet the animals who live there.", 50)
        parts += ["", f"  Stamps collected: {self.stamps}"]
        parts += ["", "  Choose a habitat:"]
        parts += self._habitat_rows()
        parts += ["", "  Type a number to set off.",
                  "  (* = every animal met!  type 'quit' to leave)"]
        return "\n".join(parts)

    def _pick_habitat(self, text):
        m = re.search(r"\d+", text or "")
        n = int(m.group()) if m else 0
        if not m or not (1 <= n <= len(WILD_HABITATS)):
            return self._map_screen(
                note=f"Type a number from 1 to {len(WILD_HABITATS)}.")   # no echo
        self.hab = WILD_HABITATS[n - 1]
        self.ai = 0
        self.state = "quiz"
        return self._quiz_screen(log=[f"You arrive at the {self.hab[1]}.",
                                      self.hab[2]])

    # ----- quiz within a habitat --------------------------------------------
    def _current_animal(self):
        animals = self.hab[3]
        if self.ai < 0 or self.ai >= len(animals):
            return None
        return animals[self.ai]

    def _quiz_screen(self, log=None):
        parts = [WILD_BANNER]
        for line in (log or []):
            parts += [""] + [f"  > {x}" for x in _wrap_lines(line, 46, indent="")]
        animal = self._current_animal()
        animals = self.hab[3]
        parts += ["", f"  {self.hab[1]}  —  animal {self.ai + 1}/{len(animals)}",
                  f"  Stamps: {self.stamps}"]
        parts += ["", f"  ~~ {animal[0]} ~~"]
        parts += [""] + [f"  {x}" for x in _wrap_lines(animal[1], 46, indent="")]
        parts += ["", "  " + animal[2]]
        for i, (opt, _ok) in enumerate(animal[3]):
            key = chr(ord('a') + i)
            wrapped = _wrap_lines(opt, 42, indent="")
            for j, ln in enumerate(wrapped):
                parts.append((f"  {key}) " if j == 0 else "     ") + ln)
        parts += ["", "  Type a letter (a/b/c) or number.",
                  "  (type 'quit' to leave the trail)"]
        return "\n".join(parts)

    def _answer(self, text):
        animal = self._current_animal()
        if animal is None:                       # safety: never crash, never dead-end
            self.state = "map"
            return self._map_screen(note="Back to the map!")
        choices = animal[3]
        pick = self._parse_choice(text, len(choices))
        if pick is None:
            return self._quiz_screen(
                log=["Type a letter (a, b, or c) or a number (1-3)."])  # no echo
        correct_i = next((i for i, (_o, ok) in enumerate(choices) if ok), 0)
        letter = chr(ord('a') + correct_i)
        if pick == correct_i:
            opener = "Correct! You earned a stamp."
        else:
            opener = (f"Good try! The answer is {letter}) "
                      f"{choices[correct_i][0]}. You still earn a stamp.")
        # Award a stamp once per animal; revisiting still teaches but no double-count.
        key = (self.hab[0], self.ai)
        if key not in self.seen:
            self.seen.add(key)
            self.stamps += 1
        log = [opener, animal[4]]                 # echoes the FACT, never the kid's text
        self.ai += 1
        if self._current_animal() is None:        # finished this habitat
            self.state = "map"
            log.append(f"You explored all of the {self.hab[1]}!")
            return self._finish(log)
        return self._quiz_screen(log=log)

    def _finish(self, log):
        parts = [WILD_BANNER, ""]
        for line in log:
            parts += [f"  > {x}" for x in _wrap_lines(line, 46, indent="")] + [""]
        parts += _wrap_lines(
            "Wonderful exploring! Your stamp book is growing.", 50)
        parts += ["", f"  Stamps collected: {self.stamps}"]
        parts += ["", "  Choose your next habitat:"]
        parts += self._habitat_rows()
        parts += ["", "  Type a number to set off.",
                  "  (* = every animal met!  type 'quit' to leave)"]
        return "\n".join(parts)

    def _parse_choice(self, text, n):
        """Return a 0-based index from a letter (a/b/c) or number (1..n), else None.
        Never raises and never echoes the kid's text."""
        s = (text or "").strip().lower()
        ml = re.search(r"[a-z]", s)
        if ml:
            idx = ord(ml.group()) - ord('a')
            if 0 <= idx < n:
                return idx
        md = re.search(r"\d+", s)
        if md:
            v = int(md.group())
            if 1 <= v <= n:
                return v - 1
        return None



MATH_BANNER = _ascii_banner("M A T H   Q U E S T")
MATH_ART = (
    "      ~ the flower meadow ~\n"
    "     *   *    *   *    *  *\n"
    "    ##########################")
# (key, display name, description) — picked at the start, scales the problems.
MATH_TIERS = [
    ("sprouts", "Sprouts", "+ and − up to 12"),
    ("saplings", "Saplings", "+ − × up to 100"),
    ("oaks", "Oaks", "bigger + − ×, and ÷"),
]


def _make_math_problem(tier, rng=random):
    """Return (question_text, integer_answer). Subtraction never goes negative
    and division is always exact, so answers are always whole numbers."""
    if tier == "sprouts":
        a, b = rng.randint(1, 12), rng.randint(1, 12)
        if rng.random() < 0.5:
            return (f"{a} + {b}", a + b)
        a, b = max(a, b), min(a, b)
        return (f"{a} − {b}", a - b)
    if tier == "saplings":
        r = rng.random()
        if r < 0.34:
            a, b = rng.randint(2, 12), rng.randint(2, 12)
            return (f"{a} × {b}", a * b)
        if r < 0.67:
            a, b = rng.randint(10, 99), rng.randint(10, 99)
            return (f"{a} + {b}", a + b)
        a, b = rng.randint(20, 99), rng.randint(1, 20)
        return (f"{a} − {b}", a - b)
    # oaks
    r = rng.random()
    if r < 0.3:
        a, b = rng.randint(3, 12), rng.randint(3, 12)
        return (f"{a} × {b}", a * b)
    if r < 0.6:
        b, ans = rng.randint(2, 12), rng.randint(2, 12)
        return (f"{b * ans} ÷ {b}", ans)
    a, b = rng.randint(100, 999), rng.randint(10, 99)
    if rng.random() < 0.5:
        return (f"{a} + {b}", a + b)
    return (f"{a} − {b}", a - b)


class MathQuest:
    """Defend a flower meadow with mental math. A correct answer zaps a weed; a
    wrong one only costs a flower (and still earns points) — it never ends, so a
    kid always makes progress. Deterministic + offline; renders in the screen."""

    name = "Math Quest"
    blurb = "defend the meadow — every right answer zaps a weed (math practice)"
    screen = True

    # age band -> the level we suggest / start at
    AGE_TIER = {"little": "sprouts", "kid": "saplings", "pro": "oaks"}

    def __init__(self):
        self.over = False
        self.state = "tier"
        self.tier = None          # the level the kid chose
        self.eff_tier = None      # the level actually in play (auto-eases on a slump)
        self.flowers = 5
        self.weeds = 0
        self.wave = 0
        self.score = 0
        self.right_streak = 0
        self.wrong_streak = 0
        self.prob = ("", 0)

    def start(self):
        return self._tier_screen()

    @property
    def is_over(self):
        return self.over

    def handle(self, text):
        if self.state == "tier":
            return self._pick_tier(text)
        return self._answer(text)

    def _suggested_tier(self):
        return self.AGE_TIER.get(games_age_band(), "saplings")

    def _tier_screen(self, note=None):
        parts = [MATH_BANNER, ""]
        if note:
            parts += [f"  > {note}", ""]
        parts += _wrap_lines("Defend the flower meadow! Solve a problem to zap "
                             "each weed before it nibbles your flowers.", 50)
        sug = next(nm for k, nm, _ in MATH_TIERS if k == self._suggested_tier())
        parts += ["", f"  (just right for your age: {sug})", "",
                  "  Pick your level:"]
        parts += _elder_menu([(k, f"{nm} — {ds}") for k, nm, ds in MATH_TIERS])
        parts += ["", "  (type 'quit' to leave)"]
        return "\n".join(parts)

    def _pick_tier(self, text):
        m = re.search(r"\d+", text or "")
        if not m or not (1 <= int(m.group()) <= len(MATH_TIERS)):
            return self._tier_screen(note="Type 1, 2 or 3 to pick a level.")
        self.tier = self.eff_tier = MATH_TIERS[int(m.group()) - 1][0]
        self.state = "play"
        self._new_wave()
        return self._play_screen(log=["A wave of weeds creeps in — solve to zap!"])

    def _new_wave(self):
        self.wave += 1
        self.weeds = 3 + self.wave        # a little bigger each wave
        self.flowers = 5
        self.prob = _make_math_problem(self.eff_tier)

    def _ease(self, harder):
        """Step the effective level down (help) or back up toward the chosen
        one (reward a streak). Returns True if it changed."""
        order = [k for k, _, _ in MATH_TIERS]
        ei = order.index(self.eff_tier)
        if harder:
            top = order.index(self.tier)
            if ei < top:
                self.eff_tier = order[ei + 1]
                return True
        elif ei > 0:
            self.eff_tier = order[ei - 1]
            return True
        return False

    def _answer(self, text):
        m = re.search(r"-?\d+", text or "")
        if not m:
            return self._play_screen(log=["Type your answer as a number."])
        guess, (q, ans) = int(m.group()), self.prob
        log = []
        if guess == ans:
            self.score += 10
            self.weeds -= 1
            self.right_streak += 1
            self.wrong_streak = 0
            log.append(f"{q} = {ans}.  Correct! A weed scampers off. (+10)")
            if self.right_streak >= 3 and self._ease(harder=True):
                self.right_streak = 0
                log.append("You're on a roll — bumping it up a notch! 🔥")
        else:
            self.score += 2
            self.flowers -= 1
            self.wrong_streak += 1
            self.right_streak = 0
            log.append(f"{q} = {ans}.  A weed nibbles a flower — good try! (+2)")
            if self.flowers <= 0:
                self.flowers = 5
                log.append("The weeds tire out and you replant the meadow. 🌱")
            if self.wrong_streak >= 2 and self._ease(harder=False):
                self.wrong_streak = 0
                log.append("Let's try some easier ones — you've got this! 💪")
        if self.weeds <= 0:
            self.score += 20
            log.append(f"Wave {self.wave} defended! +20 bonus 🌟")
            self._new_wave()
        else:
            self.prob = _make_math_problem(self.eff_tier)
        return self._play_screen(log=log)

    def _play_screen(self, log=None):
        shown = min(self.weeds, 12)
        info = [
            f"  Wave {self.wave}     Score {self.score}",
            "",
            f"  Garden:  {'* ' * self.flowers}".rstrip()
            + f"   ({self.flowers} flowers)",
            f"  Weeds:   {'w ' * shown}".rstrip() + f"   ({self.weeds} left)",
            "",
            f"     {self.prob[0]} = ?",
        ]
        parts = [MATH_BANNER]
        for line in (log or []):
            parts.append("")
            parts += [f"  > {x}" for x in _wrap_lines(line, 46, indent="")]
        parts += ["", MATH_ART, ""] + info
        parts += ["", "  Type your answer (a number).",
                  "", "  (type 'quit' to stop)"]
        return "\n".join(parts)


# ---- SCIENCE LAB -----------------------------------------------------------
SCIENCE_BANNER = _ascii_banner("S C I E N C E   L A B")

SCIENCE_ART = (
    "        .--.\n"
    "       |o_o |   ~bubble~\n"
    "       |:_/ |    o  O  o\n"
    "       (|   |)   (lab time!)\n"
    "       /'---'\\\n"
    "      (_______)"
)

# Each experiment: a fun title, a setup blurb, a prediction question with 3
# options, the index (0-based) of the TRUE outcome, a one-line result line,
# and the real, correct "why" explanation. All facts double-checked.
SCIENCE_EXPERIMENTS = [
    {
        "key": "volcano",
        "title": "The Fizzy Volcano",
        "setup": ("We build a little clay volcano and pour baking soda "
                  "inside. Then we add a splash of vinegar. Stand back!"),
        "q": "What will happen when the vinegar meets the baking soda?",
        "opts": ["It turns to solid rock",
                 "It fizzes and foams up and over",
                 "Nothing at all happens"],
        "answer": 1,
        "result": "WHOOSH! Foamy bubbles erupt up and over the rim!",
        "why": ("Baking soda and vinegar do a chemical reaction. They "
                "make a gas called carbon dioxide. The gas needs room, "
                "so it pushes up as fizzy foam and spills over. It is "
                "the very same gas that makes soda pop bubbly!"),
    },
    {
        "key": "floatsink",
        "title": "Float or Sink?",
        "setup": ("We fill a tub with water and gently set a heavy metal "
                  "bowl on top, with its open side up like a little boat."),
        "q": "What will the metal bowl do on the water?",
        "opts": ["It floats like a boat",
                 "It sinks straight down",
                 "It melts away"],
        "answer": 0,
        "result": "It floats! The bowl bobs on the water like a tiny ship.",
        "why": ("Whether something floats is not just about being heavy. "
                "A bowl shape holds lots of air, so it pushes aside more "
                "water than it weighs. The water pushes back up and holds "
                "it afloat. That is how giant steel ships float too!"),
    },
    {
        "key": "skyblue",
        "title": "Why Is the Sky Blue?",
        "setup": ("We shine bright white sunlight through the air and "
                  "watch the whole sky on a clear, sunny day."),
        "q": "Why does the daytime sky look blue?",
        "opts": ["The sky is painted blue",
                 "Blue light scatters all across the sky",
                 "The sky reflects the blue ocean"],
        "answer": 1,
        "result": "Blue light bounces all around the sky and fills it up!",
        "why": ("Sunlight is really all the rainbow colors mixed. As it "
                "zips through the air, the blue light bounces and scatters "
                "the most in every direction. So blue light comes at your "
                "eyes from all over the sky, and the sky looks blue!"),
    },
    {
        "key": "balloon",
        "title": "The Sticky Balloon",
        "setup": ("We rub a blown-up balloon on a wooly sweater for a "
                  "while, then hold it up close to a wall."),
        "q": "What will the rubbed balloon do near the wall?",
        "opts": ["It pops loudly",
                 "It sticks to the wall by itself",
                 "It floats up to the ceiling"],
        "answer": 1,
        "result": "It sticks! The balloon clings to the wall all on its own.",
        "why": ("Rubbing the balloon gives it static electricity. It "
                "grabs tiny invisible bits called electrons from the "
                "wool. Now the balloon has an electric charge that pulls "
                "on the wall, so it sticks. The same zap can make your "
                "hair stand up!"),
    },
    {
        "key": "icesalt",
        "title": "Speedy Melting Ice",
        "setup": ("We set out two ice cubes. On one we sprinkle a little "
                  "salt. The other stays plain. Then we watch and wait."),
        "q": "Which ice cube melts faster?",
        "opts": ["The plain one melts faster",
                 "The salty one melts faster",
                 "They melt at the exact same time"],
        "answer": 1,
        "result": "The salty cube melts faster, while the plain one waits.",
        "why": ("Salt lowers the temperature that water freezes at. So "
                "the salty ice can no longer stay frozen and it melts "
                "sooner. That is exactly why people sprinkle salt on icy "
                "roads and paths in winter to melt the ice!"),
    },
    {
        "key": "rainbow",
        "title": "Catch a Rainbow",
        "setup": ("We hold a clear glass prism in a beam of white "
                  "sunlight and watch what spills out the other side."),
        "q": "What comes out the other side of the prism?",
        "opts": ["A band of rainbow colors",
                 "Plain white light, same as before",
                 "A shadow with no light"],
        "answer": 0,
        "result": "A rainbow fans out -- red, orange, yellow, green, blue!",
        "why": ("White light is secretly all the rainbow colors mixed "
                "together. The prism bends each color by a different "
                "amount, so they fan apart and you see the rainbow. "
                "Raindrops do the same trick to make a sky rainbow!"),
    },
]


class ScienceLab:
    """A 'mad scientist' lab where a kid picks a safe classic experiment,
    predicts what happens (3-choice), then learns the real, correct science.
    Every experiment is narrated/simulated as a story -- nothing to do at home.
    A wrong guess still reveals and explains, so there is no failure. Endless,
    deterministic, offline; renders inside the green arcade screen."""

    name = "Science Lab"
    blurb = "run zany safe experiments and discover the REAL science why"
    screen = True

    def __init__(self):
        self.over = False
        self.state = "pick"          # pick -> predict -> reveal -> (pick)
        self.idx = None              # index of current experiment
        self.done = set()            # keys of experiments explored
        self.discoveries = 0         # count of correct predictions
        self._last_correct = False

    def start(self):
        return self._pick_screen(log=["Welcome to the lab, young scientist!"])

    @property
    def is_over(self):
        return self.over            # endless; the app handles 'quit'

    def handle(self, text):
        if self.state == "predict":
            return self._predict(text)
        if self.state == "reveal":
            return self._after_reveal(text)
        return self._pick(text)

    # -- choose an experiment --------------------------------------------------
    def _pick_screen(self, log=None):
        parts = [SCIENCE_BANNER]
        for line in (log or []):
            parts.append("")
            parts += [f"  > {x}" for x in _wrap_lines(line, 46, indent="")]
        parts += ["", SCIENCE_ART, ""]
        parts += [f"  Discoveries: {self.discoveries}"
                  f"     Explored: {len(self.done)}/{len(SCIENCE_EXPERIMENTS)}"]
        parts += ["", "  Pick an experiment to run:"]
        labels = []
        for ex in SCIENCE_EXPERIMENTS:
            tick = "* " if ex["key"] in self.done else ""
            labels.append((ex["key"], f"{tick}{ex['title']}"))
        parts += _elder_menu(labels)
        parts += ["", "  Type a number (1-6), or 'quit' to leave."]
        return "\n".join(parts)

    def _pick(self, text):
        m = re.search(r"\d+", text or "")
        if not m or not (1 <= int(m.group()) <= len(SCIENCE_EXPERIMENTS)):
            return self._pick_screen(
                log=["Type a number from 1 to 6 to pick an experiment."])
        self.idx = int(m.group()) - 1
        self.state = "predict"
        return self._predict_screen()

    # -- make a prediction -----------------------------------------------------
    def _predict_screen(self, note=None):
        ex = SCIENCE_EXPERIMENTS[self.idx]
        parts = [SCIENCE_BANNER, "", f"  ** {ex['title']} **"]
        if note:
            parts += ["", f"  > {note}"]
        parts += [""] + _wrap_lines(ex["setup"], 48)
        parts += ["", "  Make your prediction!"]
        parts += [""] + _wrap_lines(ex["q"], 48)
        parts += [""]
        parts += _elder_menu([(str(i), o) for i, o in enumerate(ex["opts"])])
        parts += ["", "  Type 1, 2 or 3 to guess.  (no wrong answers!)"]
        return "\n".join(parts)

    def _predict(self, text):
        ex = SCIENCE_EXPERIMENTS[self.idx]
        m = re.search(r"\d+", text or "")
        if not m or not (1 <= int(m.group()) <= len(ex["opts"])):
            return self._predict_screen(
                note="Type 1, 2 or 3 to make your prediction.")
        pick = int(m.group()) - 1
        correct = (pick == ex["answer"])
        if correct:
            self.discoveries += 1
        self.done.add(ex["key"])
        self.state = "reveal"
        self._last_correct = correct
        return self._reveal_screen()

    # -- reveal the result + the real science ----------------------------------
    def _reveal_screen(self):
        ex = SCIENCE_EXPERIMENTS[self.idx]
        parts = [SCIENCE_BANNER, "", f"  ** {ex['title']} **", ""]
        if self._last_correct:
            parts += _wrap_lines("Great prediction, scientist! You nailed it!",
                                 48)
        else:
            parts += _wrap_lines("Good guess! Real scientists love surprises. "
                                 "Here is what really happened:", 48)
        parts += ["", "  RESULT:"]
        parts += _wrap_lines(ex["result"], 48)
        parts += ["", "  THE REAL WHY:"]
        parts += _wrap_lines(ex["why"], 48)
        parts += ["", f"  Discoveries: {self.discoveries}"
                  f"     Explored: {len(self.done)}/{len(SCIENCE_EXPERIMENTS)}"]
        if len(self.done) >= len(SCIENCE_EXPERIMENTS):
            parts += [""] + _wrap_lines("WOW -- you explored every experiment! "
                                        "You are a true lab scientist. Run any "
                                        "one again any time!", 48)
        parts += ["", "  Press Enter (or type 'more') for the lab menu.",
                  "  (type 'quit' to leave)"]
        return "\n".join(parts)

    def _after_reveal(self, text):
        # ANY input (including blank) returns to the picker -- always progress.
        self.state = "pick"
        self.idx = None
        return self._pick_screen(log=["Back to the lab! Pick your next one."])



# Play-name -> game class. Aliases let kids type the obvious thing.
GAMES = {
    # RPG adventures — always unlocked, count toward opening the rest
    "eldermark": EldermarkRPG, "adventure": EldermarkRPG, "rpg": EldermarkRPG,
    "story": EldermarkRPG,
    "quest": RegionQuest, "quests": RegionQuest, "regions": RegionQuest,
    "lumen": RegionQuest, "tidehollow": RegionQuest, "tide": RegionQuest,
    "emberpeak": RegionQuest, "ember": RegionQuest, "frostfall": RegionQuest,
    "frost": RegionQuest,
    "dungeon": CozyDungeon, "cozy": CozyDungeon, "explore": CozyDungeon,
    # other modes (locked until a few RPG quests are done)
    "critters": CritterKeepers, "critter": CritterKeepers, "keepers": CritterKeepers,
    "spin": SpinLeague, "spinners": SpinLeague, "league": SpinLeague,
    "wild": WildTrails, "trails": WildTrails, "animals": WildTrails,
    "math": MathQuest, "mathquest": MathQuest,
    "science": ScienceLab, "lab": ScienceLab,
    "number": NumberGuess, "numbers": NumberGuess, "guess": NumberGuess,
    "scramble": WordScramble, "word": WordScramble, "unscramble": WordScramble,
    "hangman": Hangman,
    "20questions": TwentyQuestions, "20q": TwentyQuestions,
    "questions": TwentyQuestions,
    "trivia": Trivia, "quiz": Trivia,
}

# Ordered menu shown by /play. RPG adventures first (always playable); the rest
# are gated by the picker until enough RPG quests are finished.
GAME_MENU = [
    ("eldermark", "⚔️", EldermarkRPG),
    ("quest", "🌍", RegionQuest),
    ("dungeon", "🗺️", CozyDungeon),
    ("critters", "🐾", CritterKeepers),
    ("spin", "🌀", SpinLeague),
    ("wild", "🦉", WildTrails),
    ("math", "➗", MathQuest),
    ("science", "🔬", ScienceLab),
    ("number", "🔢", NumberGuess),
    ("scramble", "🪢", WordScramble),
    ("hangman", "🔤", Hangman),
    ("20questions", "❓", TwentyQuestions),
    ("trivia", "🧠", Trivia),
]


class GamePicker:
    """The /play chooser: a big, easy-to-read screen. On first run it asks the
    player's age (sets difficulty everywhere). Then it lists RPG ADVENTURES
    first (always playable) and the other modes below — LOCKED until a few RPG
    quests are finished. The kid just types a number. ChatWindow watches `pick`
    and swaps the chosen game in; this stays a pure, GUI-free object."""

    name = "Game Arcade"
    blurb = "pick a game to play"
    screen = True

    def __init__(self):
        self.over = False
        self.pick = None        # a play-name once a valid game number is entered
        self.state = "pick"
        self._order = []        # [(key, cls, locked)] for the current menu
        self._change_age_n = 0

    def start(self):
        self.pick = None
        if games_age_band() is None:        # first time: ask the age once
            self.state = "age"
            return self._age_screen()
        self.state = "pick"
        return self._menu_screen()

    @property
    def is_over(self):
        return self.over

    def handle(self, text):
        if self.state == "age":
            return self._pick_age(text)
        return self._pick(text)

    # -- age selection -------------------------------------------------------
    def _age_screen(self, note=None):
        parts = [GAMES_BANNER, ""]
        if note:
            parts += [f"  > {note}", ""]
        parts += _wrap_lines("How old is the player? This sets the right "
                             "challenge — and I'll always help if it gets tricky.",
                             50)
        parts.append("")
        for i, (key, label, hint) in enumerate(AGE_BANDS, 1):
            parts.append(f"  {i})  {label}")
            parts += _wrap_lines(hint, 46, indent="       ")
        parts += ["", "  Type 1, 2 or 3.   (type 'quit' to leave)"]
        return "\n".join(parts)

    def _pick_age(self, text):
        m = re.search(r"\d+", text or "")
        if not m or not (1 <= int(m.group()) <= len(AGE_BANDS)):
            return self._age_screen(note="Type 1, 2 or 3 to choose.")
        key, label, _ = AGE_BANDS[int(m.group()) - 1]
        set_games_age_band(key)
        self.state = "pick"
        return self._menu_screen(note=f"Set to {label}! Now pick a game:")

    def _band_label(self):
        b = games_age_band()
        for key, label, _ in AGE_BANDS:
            if key == b:
                return label
        return "All ages"

    # -- the game menu -------------------------------------------------------
    def _menu_screen(self, note=None):
        unlocked = games_unlocked()
        done = rpg_completed_count()
        rpg = [(k, c) for (k, _e, c) in GAME_MENU if getattr(c, "rpg", False)]
        # always-playable non-RPG games (e.g. Spin League) — never locked, up top
        arena = [(k, c) for (k, _e, c) in GAME_MENU
                 if getattr(c, "always", False) and not getattr(c, "rpg", False)]
        other = [(k, c) for (k, _e, c) in GAME_MENU
                 if not getattr(c, "rpg", False) and not getattr(c, "always", False)]
        self._order = []
        parts = [GAMES_BANNER, ""]
        if note:
            parts += [f"  > {note}", ""]
        parts.append(f"  Player: {self._band_label()}    RPG quests done: {done}")
        n = 0

        def _add(group, locked, blurbs):
            nonlocal n
            for k, c in group:
                n += 1
                self._order.append((k, c, locked))
                tag = "   [LOCKED]" if locked else ""
                parts.append(f"  {n:>2})  {c.name}{tag}")
                if blurbs and not locked:
                    parts.extend(_wrap_lines(c.blurb, 50, indent="        "))

        parts += ["", "  == RPG ADVENTURES (play these first!) =="]
        _add(rpg, False, True)
        if arena:
            parts += ["", "  == THE ARENA (always open) =="]
            _add(arena, False, True)
        parts += ["", "  == MORE GAMES =="]
        if not unlocked:
            need = RPG_UNLOCK_THRESHOLD - done
            s = "s" if need != 1 else ""
            parts += _wrap_lines(f"(locked — finish {need} more RPG quest{s} "
                                 "above to open these!)", 50)
        _add(other, not unlocked, False)
        n += 1
        self._change_age_n = n
        parts += ["", f"  {n:>2})  Change player age"]
        parts += ["", "  Type a number to pick.   (type 'quit' to leave)"]
        return "\n".join(parts)

    def _pick(self, text):
        m = re.search(r"\d+", text or "")
        if not m:
            return self._menu_screen(note="Type the number of a game to play.")
        n = int(m.group())
        if n == self._change_age_n:
            self.state = "age"
            return self._age_screen()
        if not (1 <= n <= len(self._order)):
            return self._menu_screen(note=f"Pick a number from 1 to "
                                          f"{self._change_age_n}.")
        key, cls, locked = self._order[n - 1]
        if locked:
            need = RPG_UNLOCK_THRESHOLD - rpg_completed_count()
            s = "s" if need != 1 else ""
            return self._menu_screen(note=f"That one's locked! Finish {need} more "
                                          f"RPG quest{s} (pick an ADVENTURE up "
                                          "top) to unlock it.")
        self.pick = key
        return f"Starting {cls.name}..."


def start_game(name):
    """Instantiate a game by play-name (or alias); None if unknown."""
    cls = GAMES.get((name or "").strip().lower())
    return cls() if cls else None


# ===========================================================================
# Eldermark — a small WALKABLE pixel world (vertical slice). Original IP, kid-
# safe (NO combat). It opens in its own window and renders with stdlib
# tk.PhotoImage tiles (no Pillow, no asset files). The LOGIC (map, collision,
# the Wayshrine trigger) lives in a GUI-free class so it can be unit-tested
# headlessly like every other game. Walking up to the Wayshrine opens a short
# READING moment — the whole point of the arcade.
# ===========================================================================

# 4-shade warm Game-Boy monochrome palette (char -> hex). '.' = transparent.
WORLD_PAL = {"0": "#ece9d8", "1": "#a7a489", "2": "#5b5743", "3": "#211e15"}
WORLD_TILE = 16
WORLD_COLS = 20
WORLD_ROWS = 11


def _build_world_map():
    """One-screen tilemap, painted by coordinate so rows can't drift in length.
    Tile ids: g grass · f flower · p moss path · b bridge · w stream ·
    W wall · T tree · R roof · H house · S Wayshrine stone."""
    g = [["g"] * WORLD_COLS for _ in range(WORLD_ROWS)]
    for x in range(WORLD_COLS):
        g[0][x] = g[WORLD_ROWS - 1][x] = "W"
    for y in range(WORLD_ROWS):
        g[y][0] = g[y][WORLD_COLS - 1] = "W"
    for x in range(1, WORLD_COLS - 1):           # a stream across the screen
        g[3][x] = "w"
    path_cols = (8, 9)
    for y in range(1, WORLD_ROWS):               # moss path down the middle
        for c in path_cols:
            g[y][c] = "p"
    for c in path_cols:                          # a bridge over the stream
        g[3][c] = "b"
    for c in path_cols:                          # a gate through the bottom wall
        g[WORLD_ROWS - 1][c] = "p"
    for c in path_cols:                          # the Wayshrine caps the path
        g[1][c] = "S"
    for (x, y) in [(13, 4), (14, 4), (13, 5), (14, 5)]:
        g[y][x] = "T"                            # a little tree cluster
    for x in (2, 3, 4):
        g[5][x] = "R"                            # cottage roof
    for x in (2, 3, 4):
        g[6][x] = "H"                            # cottage wall
    for (x, y) in [(3, 1), (16, 2), (15, 6), (13, 8), (5, 8), (16, 9)]:
        if g[y][x] == "g":
            g[y][x] = "f"                        # flowers
    return ["".join(row) for row in g]


WORLD_MAP = _build_world_map()

# The reading beat the Wayshrine opens (original, kid-safe; nods to the Mossback
# from the Eldermark story). Each entry is one short page, pre-wrapped.
WORLD_READING = [
    "The Wayshrine stands quiet and dark.\nLong ago its light guided every\ntraveller safely home.",
    "You rest a hand on the cool stone.\nThe fireflies gather close, blinking\nlike tiny lanterns.",
    "You whisper the old word the Mossback\ntaught you... and a warm glow stirs\ndeep inside the stone.",
    "The Wayshrine wakes! Soft light spills\nacross the moss. Eldermark feels a\nlittle less lonely tonight.",
]


def _world_tile_grids():
    """Hand-drawn 16x16 GB-style tiles as explicit char grids ('0' lightest ->
    '3' darkest, per WORLD_PAL). Drawn so the world reads as a cozy top-down RPG;
    swappable later for other art. Flowers are grass plus a few little blooms."""
    tiles = {
        "g": [   # grass: soft mid-tone with tiny blades + light flecks
            "1111111111111111",
            "1111011111111111",
            "1111111111210111",
            "1101111111111111",
            "1111111101111121",
            "1112111111111111",
            "1111111111110111",
            "0111111121111111",
            "1111111111111110",
            "1111210111111111",
            "1111111111121111",
            "1101111111111111",
            "1111111111110111",
            "1211111101111111",
            "1111111111111111",
            "1111111121110111",
        ],
        "p": [   # moss path: cream cobbles, tan grout grid, a few moss specks
            "1111111111111111",
            "1000100010001000",
            "1000100010001000",
            "1111111121111111",
            "0010001000100010",
            "0010001000100012",
            "1111111111111111",
            "1000100010001000",
            "2000100010001000",
            "1111111111111111",
            "0010001000100010",
            "0010001000100010",
            "1111121111111111",
            "1000100010001000",
            "1000100010001000",
            "1111111111111111",
        ],
        "w": [   # stream: dark water with ripple lines and bright sparkles
            "2222222222222222",
            "2202222222122222",
            "2222222222222222",
            "2222122222222212",
            "2222222222222222",
            "1222222212222222",
            "2222222222222222",
            "2222222022222221",
            "2222222222222222",
            "2022222222221222",
            "2222222222222222",
            "2222221222222222",
            "2222222222222222",
            "2212222222122222",
            "2222222222222222",
            "2222222222222221",
        ],
        "b": [   # bridge: light wooden planks (horizontal) with side rails
            "3222222222222223",
            "2111111111111112",
            "2122222222222212",
            "2111111111111112",
            "2122222222222212",
            "2111111111111112",
            "2122222222222212",
            "2111111111111112",
            "2122222222222212",
            "2111111111111112",
            "2122222222222212",
            "2111111111111112",
            "2122222222222212",
            "2111111111111112",
            "2122222222222212",
            "3222222222222223",
        ],
        "T": [   # tree: round canopy with a top-left highlight and a trunk
            "1111111111111111",
            "1111122222111111",
            "1112222222221111",
            "1122200002222111",
            "1220000012222211",
            "1220001112222221",
            "1222011122222221",
            "1222211222222221",
            "1222221222222221",
            "1122222222222211",
            "1122222222222111",
            "1112222222221111",
            "1111222222211111",
            "1111113311111111",
            "1111113311111111",
            "1111111111111111",
        ],
        "W": [   # stone wall: brick courses, light cap, shadowed base
            "0000000000000000",
            "1111111111111111",
            "1112111121112111",
            "1112111121112111",
            "2222222222222222",
            "1211112111121111",
            "1211112111121111",
            "2222222222222222",
            "1112111121112111",
            "1112111121112111",
            "2222222222222222",
            "1211112111121111",
            "1211112111121111",
            "2222222222222222",
            "3333333333333333",
            "3333333333333333",
        ],
        "R": [   # cottage roof: banded shingles
            "3333333333333333",
            "2222222222222222",
            "1111111111111111",
            "2222222222222222",
            "3333333333333333",
            "2222222222222222",
            "1111111111111111",
            "2222222222222222",
            "3333333333333333",
            "2222222222222222",
            "1111111111111111",
            "2222222222222222",
            "3333333333333333",
            "2222222222222222",
            "1111111111111111",
            "3333333333333333",
        ],
        "H": [   # cottage wall: cream plaster with a framed window
            "3333333333333333",
            "3000000000000003",
            "3000000000000003",
            "3000222222000003",
            "3000211112000003",
            "3000212212000003",
            "3000211112000003",
            "3000222222000003",
            "3000000000000003",
            "3000000000000003",
            "3000000000000003",
            "3000000000000003",
            "3000000000000003",
            "3000000000000003",
            "3000000000000003",
            "3333333333333333",
        ],
        "S": [   # Wayshrine: a standing stone with a glowing rune (two = a gate)
            "1111111111111111",
            "1112222222221111",
            "1122222222222111",
            "1222233332222211",
            "1222330033222211",
            "1222303303222211",
            "1222330033222211",
            "1222233332222211",
            "1222222222222211",
            "1222222222222211",
            "1122222222222111",
            "1122222222222111",
            "1112222222221111",
            "1111233332111111",
            "1111133331111111",
            "1111111111111111",
        ],
    }
    fl = [list(r) for r in tiles["g"]]
    for (cx, cy) in [(3, 3), (11, 8), (7, 12)]:
        for (px, py, c) in [(cx, cy - 1, "0"), (cx - 1, cy, "0"),
                            (cx + 1, cy, "0"), (cx, cy + 1, "0"), (cx, cy, "3")]:
            if 0 <= px < WORLD_TILE and 0 <= py < WORLD_TILE:
                fl[py][px] = c
    tiles["f"] = ["".join(r) for r in fl]
    return tiles


def _world_sprite_grids():
    """Hand-drawn sprite art as explicit char grids ('.' = transparent, '0'
    lightest -> '3' darkest per WORLD_PAL)."""
    return {
        "hero": [   # chibi adventurer (12x16): big head, tunic, little boots
            "....3333....",
            "...333333...",
            "..33333333..",
            "..30000003..",
            "..30000003..",
            "..30300303..",
            "..30000003..",
            "..33000033..",
            "...322223...",
            "..32222223..",
            ".3222222223.",
            ".3022222203.",
            "..32222223..",
            "..32222223..",
            "..33....33..",
            "..33....33..",
        ],
        "fly": [    # firefly: a bright point with a soft halo (5x5)
            ".....",
            "..1..",
            ".101.",
            "..1..",
            ".....",
        ],
        "orb0": [   # Wayshrine glow, dim frame (8x8)
            "........",
            "..1111..",
            ".100001.",
            ".100001.",
            ".100001.",
            ".100001.",
            "..1111..",
            "........",
        ],
        "orb1": [   # Wayshrine glow, bright (8x8)
            "..1111..",
            ".100001.",
            "10000001",
            "10000001",
            "10000001",
            "10000001",
            ".100001.",
            "..1111..",
        ],
        "critter": [   # a cute wandering companion (12x12)
            "...3....3...",
            "...2....2...",
            "..22222222..",
            ".2222222222.",
            ".2200220022.",
            ".2203223022.",
            ".2222222222.",
            ".2222222222.",
            ".2222222222.",
            "..22222222..",
            "..33....33..",
            "............",
        ],
    }


class EldermarkWorldLogic:
    """GUI-free state for the Eldermark world: the tilemap, bounding-box
    collision, the player, and the Wayshrine trigger. Deterministic and
    headless-testable (no tkinter)."""

    SOLID = set("WwTRHS")          # walls, water, trees, cottage, shrine stones
    PW, PH = 10, 12                # player bounding box (pixels)
    SPEED = 2
    SHRINE = [(8, 1), (9, 1)]

    def __init__(self):
        self.base_w = WORLD_COLS * WORLD_TILE
        self.base_h = WORLD_ROWS * WORLD_TILE
        self.x = 8 * WORLD_TILE + (WORLD_TILE - self.PW) // 2     # on the path
        self.y = 9 * WORLD_TILE + (WORLD_TILE - self.PH) // 2
        self.facing = "up"
        self.relit = False
        self.anim = 0

    def tile_at(self, px, py):
        if px < 0 or py < 0 or px >= self.base_w or py >= self.base_h:
            return "W"
        return WORLD_MAP[py // WORLD_TILE][px // WORLD_TILE]

    def _blocked(self, x, y):
        if x < 0 or y < 0 or x + self.PW > self.base_w or y + self.PH > self.base_h:
            return True
        for cx in (x, x + self.PW - 1):
            for cy in (y, y + self.PH - 1):
                if self.tile_at(cx, cy) in self.SOLID:
                    return True
        return False

    def step(self, dirs, dt=1):
        """Advance one tick given a set of held directions. Moves each axis
        separately so the player slides along walls; never enters a solid tile."""
        self.anim += 1
        dx = (1 if "right" in dirs else 0) - (1 if "left" in dirs else 0)
        dy = (1 if "down" in dirs else 0) - (1 if "up" in dirs else 0)
        if dx:
            self.facing = "right" if dx > 0 else "left"
            nx = self.x + dx * self.SPEED
            if not self._blocked(nx, self.y):
                self.x = nx
        if dy:
            self.facing = "down" if dy > 0 else "up"
            ny = self.y + dy * self.SPEED
            if not self._blocked(self.x, ny):
                self.y = ny
        return bool(dx or dy)

    @property
    def at_shrine(self):
        tcx = (self.x + self.PW // 2) // WORLD_TILE
        tcy = (self.y + self.PH // 2) // WORLD_TILE
        return any(abs(tcx - sx) <= 1 and abs(tcy - sy) <= 1
                   for sx, sy in self.SHRINE)

    def relight(self):
        self.relit = True


class EldermarkWorld:
    """The walkable Eldermark window: stdlib pixel tiles, a ~30fps loop, arrow/
    WASD movement, and a Wayshrine reading moment. Crash-isolated by its caller
    (a world bug must never break the chat)."""

    def __init__(self, pet):
        self.pet = pet
        self.logic = EldermarkWorldLogic()
        base_w = WORLD_COLS * WORLD_TILE
        base_h = WORLD_ROWS * WORLD_TILE
        sw = pet.root.winfo_screenwidth()
        sh = pet.root.winfo_screenheight()
        scale = 4
        while scale > 2 and (base_w * scale > sw - 80 or base_h * scale > sh - 140):
            scale -= 1
        self.scale = scale
        cw, ch = base_w * scale, base_h * scale

        self._refs = []                      # keep PhotoImages alive (anti-GC)
        self._tiles = {k: self._img(v) for k, v in _world_tile_grids().items()}
        bg = tk.PhotoImage(width=base_w, height=base_h)
        for ry, row in enumerate(WORLD_MAP):
            for rx, cch in enumerate(row):
                bg.tk.call(bg, "copy", self._tiles.get(cch, self._tiles["g"]),
                           "-to", rx * WORLD_TILE, ry * WORLD_TILE)
        self.bg = bg.zoom(scale)
        self.spr = {k: self._img(v).zoom(scale)
                    for k, v in _world_sprite_grids().items()}
        self._refs += [self.bg] + list(self.spr.values()) + list(self._tiles.values())

        self.win = tk.Toplevel(pet.root)
        self.win.title("Eldermark")
        self.win.resizable(False, False)
        self.canvas = tk.Canvas(self.win, width=cw, height=ch,
                                highlightthickness=0, bg="#211e15")
        self.canvas.pack()
        self.canvas.create_image(0, 0, anchor="nw", image=self.bg)

        self._fly_base = [(110, 22), (150, 18), (128, 42), (96, 30),
                          (160, 40), (134, 10)]
        self.fly_items = [self.canvas.create_image(0, 0, anchor="nw",
                          image=self.spr["fly"]) for _ in self._fly_base]
        self.orb_item = self.canvas.create_image(132 * scale, 6 * scale,
                                                 anchor="nw", image=self.spr["orb1"])
        self.crit_item = self.canvas.create_image(0, 0, anchor="nw",
                                                  image=self.spr["critter"])
        self.player_item = self.canvas.create_image(0, 0, anchor="nw",
                                                    image=self.spr["hero"])
        fs = max(9, 3 * scale)
        self.hint = self.canvas.create_text(
            10, ch - 8, anchor="sw", fill="#ece9d8",
            font=("Consolas", fs),
            text="Arrows / WASD to walk    Esc to leave")

        # reading box (hidden until the Wayshrine is reached)
        bx0, by0, bx1, by1 = int(cw * 0.06), int(ch * 0.60), int(cw * 0.94), int(ch * 0.93)
        self.read_bg = self.canvas.create_rectangle(
            bx0, by0, bx1, by1, fill="#ece9d8", outline="#211e15", width=3,
            state="hidden")
        self.read_txt = self.canvas.create_text(
            bx0 + 14, by0 + 12, anchor="nw", fill="#211e15",
            font=("Consolas", fs), state="hidden")
        self.read_tip = self.canvas.create_text(
            bx1 - 12, by1 - 10, anchor="se", fill="#5b5743",
            font=("Consolas", max(9, fs - 2)), state="hidden")

        self._dirs = set()
        self._reading = None
        self._read_i = 0
        self._read_done = False
        self._anim = 0
        self._loop = None
        self.win.bind("<KeyPress>", self._key_down)
        self.win.bind("<KeyRelease>", self._key_up)
        self.win.protocol("WM_DELETE_WINDOW", self.close)
        # center on screen
        self.win.update_idletasks()
        self.win.geometry(f"+{max(0, (sw - cw) // 2)}+{max(0, (sh - ch) // 2 - 30)}")
        self.win.focus_force()
        self._tick()

    # -- art helpers ---------------------------------------------------------
    def _img(self, grid):
        """Build a tk.PhotoImage from a char grid; '.' pixels stay transparent."""
        h, w = len(grid), len(grid[0])
        im = tk.PhotoImage(width=w, height=h)
        for y, row in enumerate(grid):
            x = 0
            while x < w:
                ch = row[x]
                if ch == ".":
                    x += 1
                    continue
                x2 = x
                while x2 < w and row[x2] == ch:
                    x2 += 1
                im.put(WORLD_PAL[ch], to=(x, y, x2, y + 1))
                x = x2
        return im

    # -- input ---------------------------------------------------------------
    _KEYS = {"up": "up", "w": "up", "down": "down", "s": "down",
             "left": "left", "a": "left", "right": "right", "d": "right"}

    def _key_down(self, e):
        ks = (e.keysym or "").lower()
        if ks == "escape":
            self.close()
            return
        if ks in ("space", "return"):
            self._on_space()
            return
        d = self._KEYS.get(ks)
        if d:
            self._dirs.add(d)

    def _key_up(self, e):
        d = self._KEYS.get((e.keysym or "").lower())
        if d:
            self._dirs.discard(d)

    def _on_space(self):
        if self._reading is not None:
            self._advance_reading()
        elif self.logic.at_shrine and not self._read_done:
            self._open_reading()

    # -- reading moment ------------------------------------------------------
    def _open_reading(self):
        self._reading = True
        self._read_i = 0
        self._dirs.clear()
        self._render_reading()

    def _advance_reading(self):
        self._read_i += 1
        if self._read_i >= len(WORLD_READING):
            self._reading = None
            self._read_done = True
            self.logic.relight()
            for it in (self.read_bg, self.read_txt, self.read_tip):
                self.canvas.itemconfigure(it, state="hidden")
            return
        self._render_reading()

    def _render_reading(self):
        last = self._read_i == len(WORLD_READING) - 1
        self.canvas.itemconfigure(self.read_bg, state="normal")
        self.canvas.itemconfigure(self.read_txt, state="normal",
                                  text=WORLD_READING[self._read_i])
        self.canvas.itemconfigure(self.read_tip, state="normal",
                                  text="Space to relight  >" if last else "Space  >")

    # -- loop ----------------------------------------------------------------
    def _tick(self):
        if not self.win.winfo_exists():
            return
        self._anim += 1
        if self._reading is None:
            self.logic.step(self._dirs)
        s = self.scale
        self.canvas.coords(self.player_item, self.logic.x * s, self.logic.y * s)
        bright = self.logic.relit or (self._anim // 8) % 2 == 0
        self.canvas.itemconfigure(self.orb_item,
                                  image=self.spr["orb1" if bright else "orb0"])
        for i, it in enumerate(self.fly_items):
            bxx, byy = self._fly_base[i]
            ox = math.sin(self._anim * 0.05 + i) * 6
            oy = math.cos(self._anim * 0.04 + i * 1.7) * 5
            self.canvas.coords(it, (bxx + ox) * s, (byy + oy) * s)
        cx = 60 + math.sin(self._anim * 0.02) * 12
        self.canvas.coords(self.crit_item, cx * s, 126 * s)
        if self._reading is None:
            near = self.logic.at_shrine and not self._read_done
            self.canvas.itemconfigure(
                self.hint,
                text="Press Space to read the Wayshrine"
                if near else "Arrows / WASD to walk    Esc to leave")
        self._loop = self.win.after(33, self._tick)

    def close(self):
        if self._loop is not None:
            try:
                self.win.after_cancel(self._loop)
            except Exception:
                pass
            self._loop = None
        try:
            if self.win.winfo_exists():
                self.win.destroy()
        except Exception:
            pass


# ===========================================================================
# Eldermark — asset-driven SCENE engine (vertical slice: Mosslight Gate).
#
# The next step beyond the programmatic tile world above: instead of code-drawn
# tiles it shows a PAINTED pixel-art background (one PNG per location) with
# character/creature sprite PNGs on top, a bottom dialogue box, and reading-as-
# gameplay. The art is generated separately (Game-Boy-green pixel art) and
# normalized by tools/prep_eldermark_art.py into assets/eldermark/. Until that
# art exists the engine draws simple placeholders so it still runs. The LOGIC
# (movement, rectangle collision, NPC interaction) is GUI-free and headless-
# testable — see test_scene.py.
# ===========================================================================

# The Eldermark look: 4 Game-Boy greens, darkest -> lightest.
ELDER_GREEN = ("#0f380f", "#306230", "#8bac0f", "#9bbc0f")
ELDER_KEY = "#fe00fe"        # magenta key colour used in the source sprite art

# Bundled scene/sprite art sits beside the pet art; resolve for frozen builds.
if getattr(sys, "frozen", False):
    ELDER_ASSETS = Path(sys._MEIPASS) / "assets" / "eldermark"
else:
    ELDER_ASSETS = Path(__file__).resolve().parent / "assets" / "eldermark"

# Canonical scene pixel space, shown 1:1. Backgrounds are normalized to exactly
# this size by the prep tool, so collision/positions are plain pixel coords.
SCENE_W, SCENE_H = 720, 480

# The slice's one location. `solids` are rectangles the player can't enter
# (x, y, w, h); `npcs` are interaction points (sprite optional) with reading
# pages. A position is the sprite BASE (feet), anchored bottom-centre on draw.
ELDER_SCENES = {
    "mosslight_gate": {
        "id": "mosslight_gate",
        "name": "Mosslight Gate",
        "bg": "mosslight_gate_bg.png",
        "spawn": (340, 410),
        "solids": [
            (0, 0, SCENE_W, 80),             # top canopy
            (0, 0, 80, SCENE_H),             # left-edge tree
            (SCENE_W - 80, 0, 80, SCENE_H),  # right-edge tree
            (270, 110, 60, 200),             # left arch pillar (lantern post)
            (440, 110, 60, 200),             # right arch pillar (lantern post)
            (60, 320, 70, 90),               # bottom-left mossy stone
            (600, 300, 70, 130),             # bottom-right mossy stones
        ],
        "npcs": [
            {"id": "mossback", "sprite": "mossback.png", "pos": (250, 300),
             "creature": "mossback",
             "pages": [
                 "A round, mossy creature blinks up at you,\nmushrooms swaying on its back.",
                 "\"Welcome to Eldermark, little wanderer.\"",
                 "\"Walk up through the Mosslight Gate to\nreach the Whisperwood...\"",
                 "\"...and make a friend or two along the way.\"",
             ]},
            {"id": "ferns", "sprite": None, "pos": (150, 360), "battle": "gloomling",
             "pages": ["The ferns rustle..."]},
        ],
        "exits": [{"at": (336, 84, 104, 60), "to": "whisperwood", "spawn": (360, 400)}],
    },
    "whisperwood": {
        "id": "whisperwood",
        "name": "Whisperwood",
        "bg": "whisperwood_bg.png",
        "spawn": (360, 410),
        "solids": [
            (0, 0, SCENE_W, 64),             # canopy
            (0, 0, 90, SCENE_H),             # left-edge trees
            (SCENE_W - 90, 0, 90, SCENE_H),  # right-edge trees
            (520, 200, 96, 96),              # mossy stone block (right)
        ],
        "npcs": [
            {"id": "hedge", "sprite": "hedge_pixie.png", "pos": (210, 330),
             "creature": "hedge_pixie",
             "pages": [
                 "A cheerful Hedge-Pixie lifts its little\nlantern to light your way.",
                 "\"Welcome to the Whisperwood! Mind the\nbrambles — a Thistlewisp loves to play there.\"",
                 "\"And deeper in, the old Mire Warden waits.\nIt's lonely... will you be its friend?\"",
             ]},
            {"id": "brambles", "sprite": None, "pos": (500, 330),
             "battle": "thistlewisp", "pages": ["The brambles shiver..."]},
            {"id": "warden", "sprite": None, "pos": (360, 190),
             "battle": "mire_warden", "pages": ["A great mossy shape stirs..."]},
        ],
        "exits": [
            {"at": (300, 446, 120, 34), "to": "mosslight_gate", "spawn": (384, 150)},
            {"at": (320, 74, 120, 40), "to": "wayshrine", "spawn": (360, 400)},
        ],
    },
    "wayshrine": {
        "id": "wayshrine",
        "name": "The Wayshrine",
        "bg": "wayshrine_bg.png",
        "spawn": (360, 410),
        "solids": [
            (0, 0, SCENE_W, 64),             # canopy
            (0, 0, 80, SCENE_H),             # left-edge trees
            (SCENE_W - 80, 0, 80, SCENE_H),  # right-edge trees
            (290, 100, 140, 140),            # the shrine itself (approach from below)
        ],
        "npcs": [
            {"id": "shrine", "sprite": None, "pos": (360, 250), "shrine": True,
             "pages": ["The Wayshrine waits, quiet and old."]},
        ],
        "exits": [{"at": (300, 446, 120, 34), "to": "whisperwood", "spawn": (360, 280)}],
    },
}
ELDER_SLICE = ELDER_SCENES["mosslight_gate"]   # back-compat alias for tests


# The creatures of Eldermark — for the Journal (a gentle "dex"): each has a
# sprite, a short lore paragraph to READ, and is recorded when you meet or
# befriend it. Sprites you don't have yet fall back to a placeholder.
ELDER_CREATURES = {
    "mossback": {"name": "Mossback", "sprite": "mossback.png",
        "lore": "A gentle moss-furred guardian with little antlers and a cap of "
                "mushrooms. It tends the Mosslight Gate and teaches travellers "
                "the old calming song."},
    "gloomling": {"name": "Gloomling", "sprite": "gloomling.png",
        "lore": "A shy forest spirit with leaf-shaped ears and a wispy cloud "
                "tail. It hides in the ferns until a kind, patient voice coaxes "
                "it gently out."},
    "thistlewisp": {"name": "Thistlewisp", "sprite": "thistlewisp.png",
        "lore": "A round, bouncy sprite dotted with soft thorns and a "
                "mischievous grin. It adores hide-and-seek in the brambles."},
    "hedge_pixie": {"name": "Hedge-Pixie", "sprite": "hedge_pixie.png",
        "lore": "A tiny woodland helper who carries a lantern on a crooked "
                "staff, humming as it lights the way for lost wanderers."},
    "mire_warden": {"name": "Mire Warden", "sprite": "mire_warden.png",
        "lore": "A large, ancient guardian crowned with stone antlers and "
                "trailing moss. Lonely for an age, it wishes only for a friend."},
}


class EldermarkState:
    """Shared memory of which creatures you've met / befriended and whether the
    Wayshrine is relit. Persisted to user settings via load/save_into."""

    def __init__(self):
        self.met = set()
        self.friends = set()
        self.relit = False

    def meet(self, cid):
        if cid in ELDER_CREATURES:        # only ever record journal creatures
            self.met.add(cid)

    def befriend(self, cid):
        if cid in ELDER_CREATURES:
            self.met.add(cid)
            self.friends.add(cid)

    def load(self, settings):
        """Restore from a settings dict, dropping ids no longer in the registry."""
        self.met = {c for c in settings.get("eldermark_met", []) if c in ELDER_CREATURES}
        self.friends = {c for c in settings.get("eldermark_friends", [])
                        if c in ELDER_CREATURES}
        self.relit = bool(settings.get("eldermark_relit", False))

    def save_into(self, disk):
        """Write met/friends/relit as stable JSON (sets -> sorted lists)."""
        disk["eldermark_met"] = sorted(self.met)
        disk["eldermark_friends"] = sorted(self.friends)
        disk["eldermark_relit"] = self.relit


ELDER_STATE = EldermarkState()


def elder_shrine_pages(friends, total):
    """The Wayshrine's reading — a closing story once every friend is made, else
    a gentle nudge. Pure function so it's headless-testable."""
    if friends >= total:
        return [
            "The Wayshrine drinks in the warmth of\nevery friend you have made...",
            "...and WAKES! Soft light spills across\nthe moss, and Eldermark glows again.",
            "The creatures gather close, no longer\nlonely. You did it — Eldermark is bright.",
            "Thank you for being so kind.\n*   The End   *",
        ]
    return [
        "The Wayshrine glimmers faintly, waiting\nfor the warmth of every friend.",
        f"Friends made: {friends} of {total}.\nBefriend them all, then return to light it.",
    ]


class EldermarkSceneLogic:
    """GUI-free Eldermark scene state: player position, rectangle collision,
    and NPC interaction range. Deterministic and headless-testable."""

    PW, PH = 40, 22          # player feet collision box (pixels)
    SPEED = 3
    TALK = 56                # interaction reach to an NPC base point

    def __init__(self, scene=ELDER_SLICE, spawn=None):
        self.scene = scene
        self.solids = [tuple(r) for r in scene.get("solids", [])]
        self.npcs = scene.get("npcs", [])
        self.exits = scene.get("exits", [])
        self.x, self.y = spawn or scene.get("spawn", (SCENE_W // 2, SCENE_H // 2))
        self.facing = "up"
        self.anim = 0

    def _blocked(self, x, y):
        if x < 0 or y < 0 or x + self.PW > SCENE_W or y + self.PH > SCENE_H:
            return True
        for (rx, ry, rw, rh) in self.solids:
            if x < rx + rw and x + self.PW > rx and y < ry + rh and y + self.PH > ry:
                return True
        return False

    def step(self, dirs):
        """Advance one tick. Each axis moves separately so the player slides
        along walls and never enters a solid rectangle."""
        self.anim += 1
        dx = (1 if "right" in dirs else 0) - (1 if "left" in dirs else 0)
        dy = (1 if "down" in dirs else 0) - (1 if "up" in dirs else 0)
        moved = False
        if dx:
            self.facing = "right" if dx > 0 else "left"
            nx = self.x + dx * self.SPEED
            if not self._blocked(nx, self.y):
                self.x, moved = nx, True
        if dy:
            self.facing = "down" if dy > 0 else "up"
            ny = self.y + dy * self.SPEED
            if not self._blocked(self.x, ny):
                self.y, moved = ny, True
        return moved

    def npc_in_range(self):
        """The first NPC whose base is within reach of the player feet, else None."""
        fx, fy = self.x + self.PW / 2, self.y + self.PH / 2
        for npc in self.npcs:
            bx, by = npc["pos"]
            if abs(fx - bx) <= self.TALK and abs(fy - by) <= self.TALK:
                return npc
        return None

    def exit_at(self):
        """The exit whose zone holds the player's feet centre, or None."""
        fx, fy = self.x + self.PW / 2, self.y + self.PH / 2
        for ex in self.exits:
            rx, ry, rw, rh = ex["at"]
            if rx <= fx <= rx + rw and ry <= fy <= ry + rh:
                return ex
        return None


class EldermarkScene:
    """The painted Eldermark scene window: a PNG background, sprite actors,
    fireflies, a bottom dialogue box, and reading-as-gameplay. Falls back to
    simple placeholder art until the generated pixel art is dropped in.
    Crash-isolated by its caller (a scene bug must never break the chat)."""

    _KEYS = {"up": "up", "w": "up", "down": "down", "s": "down",
             "left": "left", "a": "left", "right": "right", "d": "right"}

    def __init__(self, pet, scene_id="mosslight_gate", spawn=None):
        self.pet = pet
        self.scene_id = scene_id
        self.scene = ELDER_SCENES.get(scene_id, ELDER_SLICE)
        self.logic = EldermarkSceneLogic(self.scene, spawn=spawn)
        self._refs = []                      # keep PhotoImages alive (anti-GC)

        self.win = tk.Toplevel(pet.root)
        self.win.title(f"Eldermark — {self.scene['name']}")
        self.win.resizable(False, False)
        self.canvas = tk.Canvas(self.win, width=SCENE_W, height=SCENE_H,
                                highlightthickness=0, bg=ELDER_GREEN[0])
        self.canvas.pack()

        # background (painted PNG if present, else a placeholder sketch)
        self.bg = self._load(self.scene["bg"], self._placeholder_bg)
        self.canvas.create_image(0, 0, anchor="nw", image=self.bg)
        if not (ELDER_ASSETS / self.scene["bg"]).exists():
            self.canvas.create_text(
                SCENE_W // 2, 40, fill=ELDER_GREEN[3], font=("Consolas", 12),
                text="(placeholder art — add PNGs to assets/eldermark)")

        # hero sprites per facing; NPC sprites (static, feet-anchored)
        self.hero = {f: self._load(f"hero_{f}.png",
                                   lambda: self._placeholder_hero())
                     for f in ("down", "up", "left", "right")}
        for npc in self.scene["npcs"]:
            if npc.get("sprite"):
                img = self._load(npc["sprite"], self._placeholder_npc)
                self.canvas.create_image(npc["pos"][0], npc["pos"][1],
                                         anchor="s", image=img)

        self.player_item = self.canvas.create_image(
            self.logic.x + self.logic.PW // 2, self.logic.y + self.logic.PH,
            anchor="s", image=self.hero[self.logic.facing])

        # drifting fireflies (code-drawn)
        self._fly_base = [(150, 110), (210, 90), (470, 120), (540, 150),
                          (380, 80), (300, 130)]
        self.fly_items = [self.canvas.create_oval(0, 0, 5, 5,
                          fill=ELDER_GREEN[3], outline="") for _ in self._fly_base]

        # bottom dialogue box (hidden until a conversation starts)
        m, top = 24, int(SCENE_H * 0.72)
        self.box_bg = self.canvas.create_rectangle(
            m, top, SCENE_W - m, SCENE_H - m, fill=ELDER_GREEN[3],
            outline=ELDER_GREEN[0], width=5, state="hidden")
        self.box_txt = self.canvas.create_text(
            m + 22, top + 18, anchor="nw", fill=ELDER_GREEN[0],
            font=("Consolas", 18, "bold"), state="hidden")
        self.box_tip = self.canvas.create_text(
            SCENE_W - m - 16, SCENE_H - m - 12, anchor="se", fill=ELDER_GREEN[1],
            font=("Consolas", 12), state="hidden")
        self._hint_walk = "WASD/Arrows walk   Space talk   J journal   Esc leave"
        self.hint_sh = self.canvas.create_text(          # drop shadow for contrast
            15, 13, anchor="nw", fill=ELDER_GREEN[0], font=("Consolas", 13, "bold"),
            text=self._hint_walk)
        self.hint = self.canvas.create_text(
            14, 12, anchor="nw", fill=ELDER_GREEN[3], font=("Consolas", 13, "bold"),
            text=self._hint_walk)

        self._dirs = set()
        self._talk = None            # active NPC dialogue dict, or None
        self._page = 0
        self._anim = 0
        self._loop = None
        self.win.bind("<KeyPress>", self._key_down)
        self.win.bind("<KeyRelease>", self._key_up)
        self.win.protocol("WM_DELETE_WINDOW", self.close)
        sw, sh = pet.root.winfo_screenwidth(), pet.root.winfo_screenheight()
        self.win.update_idletasks()
        self.win.geometry(f"+{max(0, (sw - SCENE_W) // 2)}"
                          f"+{max(0, (sh - SCENE_H) // 2 - 30)}")
        self.win.focus_force()
        self._tick()

    # -- art -----------------------------------------------------------------
    def _load(self, fname, placeholder):
        """A PhotoImage for `fname` from assets/eldermark, else a placeholder."""
        p = ELDER_ASSETS / fname
        if p.exists():
            try:
                img = tk.PhotoImage(file=str(p))
                self._refs.append(img)
                return img
            except tk.TclError:
                pass
        img = placeholder()
        self._refs.append(img)
        return img

    def _placeholder_bg(self):
        im = tk.PhotoImage(width=SCENE_W, height=SCENE_H)
        im.put(ELDER_GREEN[1], to=(0, 0, SCENE_W, SCENE_H))      # grass
        im.put(ELDER_GREEN[0], to=(0, 0, SCENE_W, 64))           # tree line
        im.put(ELDER_GREEN[2], to=(320, 64, 400, SCENE_H))       # lantern path
        im.put(ELDER_GREEN[0], to=(300, 64, 340, 214))           # arch pillar L
        im.put(ELDER_GREEN[0], to=(440, 64, 480, 214))           # arch pillar R
        im.put(ELDER_GREEN[0], to=(300, 64, 480, 96))            # arch top
        im.put(ELDER_GREEN[2], to=(70, 150, 190, 246))           # cottage
        im.put(ELDER_GREEN[0], to=(556, 120, 652, 216))          # tree blob
        return im

    def _placeholder_hero(self):
        w, h = 44, 68
        im = tk.PhotoImage(width=w, height=h)
        im.put(ELDER_GREEN[2], to=(w // 4, 2, 3 * w // 4, h // 2))     # hair
        im.put(ELDER_GREEN[3], to=(w // 3, h // 6, 2 * w // 3, h // 2))  # face
        im.put(ELDER_GREEN[1], to=(w // 6, h // 2, 5 * w // 6, h - 4))   # body
        im.put(ELDER_GREEN[0], to=(w // 6, h - 8, 5 * w // 6, h))        # feet
        return im

    def _placeholder_npc(self):
        w, h = 84, 72
        im = tk.PhotoImage(width=w, height=h)
        im.put(ELDER_GREEN[1], to=(w // 6, h // 4, 5 * w // 6, h))       # body
        im.put(ELDER_GREEN[2], to=(w // 4, h // 8, 3 * w // 4, h // 2))  # head
        im.put(ELDER_GREEN[0], to=(w // 3, h // 3, w // 3 + 8, h // 3 + 8))      # eye
        im.put(ELDER_GREEN[0], to=(3 * w // 5, h // 3, 3 * w // 5 + 8, h // 3 + 8))  # eye
        return im

    # -- input ---------------------------------------------------------------
    def _key_down(self, e):
        ks = (e.keysym or "").lower()
        if ks == "escape":
            self.close()
            return
        if ks in ("space", "return"):
            self._interact()
            return
        if ks == "j":
            self._open_journal()
            return
        d = self._KEYS.get(ks)
        if d:
            self._dirs.add(d)

    def _key_up(self, e):
        d = self._KEYS.get((e.keysym or "").lower())
        if d:
            self._dirs.discard(d)

    def _interact(self):
        if self._talk is not None:
            self._page += 1
            if self._page >= len(self._talk["pages"]):
                self._talk = None
                for it in (self.box_bg, self.box_txt, self.box_tip):
                    self.canvas.itemconfigure(it, state="hidden")
            else:
                self._render_page()
            return
        npc = self.logic.npc_in_range()
        if npc:
            self._dirs.clear()
            if npc.get("battle"):
                self._start_battle(npc["battle"])
                return
            if npc.get("shrine"):
                total, n = len(ELDER_CREATURES), len(ELDER_STATE.friends)
                if n >= total and not ELDER_STATE.relit:
                    ELDER_STATE.relit = True
                    self._persist()
                self._talk = {"pages": elder_shrine_pages(n, total)}
                self._page = 0
                self._render_page()
                return
            if npc.get("creature"):
                ELDER_STATE.befriend(npc["creature"])   # friendly NPCs join when you talk
                self._persist()
            self._talk = npc
            self._page = 0
            self._render_page()

    def _render_page(self):
        pages = self._talk["pages"]
        last = self._page == len(pages) - 1
        self.canvas.itemconfigure(self.box_bg, state="normal")
        self.canvas.itemconfigure(self.box_txt, state="normal", text=pages[self._page])
        self.canvas.itemconfigure(self.box_tip, state="normal",
                                  text="Space to close  >" if last else "Space  >")

    def _start_battle(self, enemy_key):
        """Launch a battle; befriend the creature on a win. A battle bug must
        never break the scene."""
        ELDER_STATE.meet(enemy_key)

        def done(won):
            if won:
                ELDER_STATE.befriend(enemy_key)
                self._persist()
        try:
            EldermarkBattle(self.pet, enemy_key, bg=self.scene.get("bg"), on_close=done)
        except Exception:
            pass

    def _open_journal(self):
        """Open the Creature Journal. A journal bug must never break the scene."""
        try:
            EldermarkJournal(self.pet)
        except Exception:
            pass

    def _persist(self):
        """Save journal progress through the pet's settings, if available."""
        save = getattr(self.pet, "_save_settings", None)
        if save:
            try:
                save()
            except Exception:
                pass

    def _go(self, scene_id, spawn):
        """Walk to an adjacent scene. Build the next one BEFORE closing this one,
        so a construction failure leaves the player where they were, not nowhere."""
        try:
            EldermarkScene(self.pet, scene_id, spawn)
        except Exception:
            return
        self.close()

    # -- loop ----------------------------------------------------------------
    def _tick(self):
        if not self.win.winfo_exists():
            return
        self._anim += 1
        if self._talk is None:
            self.logic.step(self._dirs)
            ex = self.logic.exit_at()
            if ex:
                self._go(ex["to"], ex.get("spawn"))
                return
        bob = -2 if (self._talk is None and self._dirs and (self._anim // 5) % 2) else 0
        self.canvas.coords(self.player_item,
                           self.logic.x + self.logic.PW // 2,
                           self.logic.y + self.logic.PH + bob)
        self.canvas.itemconfigure(self.player_item, image=self.hero[self.logic.facing])
        for i, it in enumerate(self.fly_items):
            bxx, byy = self._fly_base[i]
            ox = math.sin(self._anim * 0.05 + i) * 10
            oy = math.cos(self._anim * 0.04 + i * 1.7) * 8
            self.canvas.coords(it, bxx + ox, byy + oy, bxx + ox + 5, byy + oy + 5)
        if self._talk is None:
            near = self.logic.npc_in_range()
            if near and near.get("battle"):
                txt = "Press Space — something rustles in the ferns!"
            elif near:
                txt = "Press Space to talk"
            else:
                txt = self._hint_walk
            self.canvas.itemconfigure(self.hint_sh, text=txt)
            self.canvas.itemconfigure(self.hint, text=txt)
        self._loop = self.win.after(33, self._tick)

    def close(self):
        if self._loop is not None:
            try:
                self.win.after_cancel(self._loop)
            except Exception:
                pass
            self._loop = None
        try:
            if self.win.winfo_exists():
                self.win.destroy()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Eldermark BATTLE screen — gentle, kid-safe, Pokemon-style layout.
#
# "HP" is how WARY a creature is; bringing it to 0 means the creature trusts
# you (befriended) — the hero never harms anything. Enemy upper-right, hero
# (back) lower-left, two HP boxes, a FIGHT / SKILL / ITEM / RUN menu. Painted
# PNG art with code-drawn UI; placeholders until art lands. The combat LOGIC is
# GUI-free + deterministic (headless-tested in test_battle.py).
# ---------------------------------------------------------------------------

# The hero's calming "moves" (no harm — open hands, a gentle song).
ELDER_MOVES = [
    {"key": "fight", "label": "FIGHT", "power": 6,
     "flavor": "You step closer, hands open and kind."},
    {"key": "skill", "label": "SKILL", "power": 9,
     "flavor": "You hum the Mossback's gentle song."},
]

ELDER_BATTLERS = {
    "gloomling": {
        "name": "Gloomling", "sprite": "gloomling.png",
        "hp": 18, "atk": 3, "lv": 4,
        "meet": "A shy Gloomling peeks out from the rustling ferns!",
        "poke": "The Gloomling bumps you softly.",
        "win": "The Gloomling gives a happy wiggle and drifts beside you — a new friend!",
        "lose": "You grow sleepy and sit to rest. The Gloomling waits nearby, kind and patient.",
    },
    "thistlewisp": {
        "name": "Thistlewisp", "sprite": "thistlewisp.png",
        "hp": 22, "atk": 4, "lv": 5,
        "meet": "A Thistlewisp bounces out of the brambles, grinning!",
        "poke": "The Thistlewisp boings off you, giggling.",
        "win": "The Thistlewisp does a happy spin and bounces along at your side!",
        "lose": "You stop for a breather. The Thistlewisp waits, bouncing softly.",
    },
    "mire_warden": {
        "name": "Mire Warden", "sprite": "mire_warden.png",
        "hp": 30, "atk": 4, "lv": 7,
        "meet": "The ancient Mire Warden rises slowly, its kind eyes meeting yours.",
        "poke": "The Mire Warden shifts; soft mossy dust drifts over you.",
        "win": "The Mire Warden smiles for the first time in an age and walks beside you — no longer alone.",
        "lose": "You rest against a soft mound of moss. The Warden waits, gentle and patient.",
    },
}


class EldermarkBattleLogic:
    """GUI-free, deterministic Eldermark battle. No RNG so it's headless-
    testable. HP never displays below 0; the hero can't truly lose (just rests)."""

    HEAL = 10
    ITEMS = 3

    def __init__(self, enemy_key="gloomling", hero_name="Wanderer",
                 hero_lv=5, hero_hp=26):
        if enemy_key not in ELDER_BATTLERS:      # unknown key -> safe fallback
            enemy_key = "gloomling"
        b = ELDER_BATTLERS[enemy_key]
        self.ekey = enemy_key
        self.ename = b["name"]
        self.e_hp = self.e_max = b["hp"]
        self.e_atk = b["atk"]
        self.e_lv = b["lv"]
        self.hname = hero_name
        self.h_hp = self.h_max = max(1, hero_hp)     # >=1 so HP bars never /0
        self.h_lv = hero_lv
        self.items = self.ITEMS
        self.over = False
        self.won = None            # True = befriended, False = rested, None = ran
        self.turn = 0
        self.log = b["meet"]

    def _power(self, move):
        return move["power"] + (self.h_lv - 1) // 2

    def act(self, action):
        """Apply one player action plus the creature's gentle response; return
        the message to show. Idempotent once the battle is over."""
        if self.over or action not in ("run", "item", "fight", "skill"):
            return self.log
        self.turn += 1
        if action == "run":
            self.over, self.won = True, None
            self.log = "You slip quietly back down the path."
            return self.log
        if action == "item":
            if self.items <= 0:
                self.log = "Your pack is empty — no glow-berries left."
                return self.log
            if self.h_hp >= self.h_max:             # full: keep the berry, no penalty
                self.log = "You're already full of glow. (You keep the berry.)"
                return self.log
            self.items -= 1
            self.h_hp = min(self.h_max, self.h_hp + self.HEAL)
            msg = f"You share a glow-berry. (+{self.HEAL})"
        else:                                       # fight / skill
            move = ELDER_MOVES[0] if action == "fight" else ELDER_MOVES[1]
            self.e_hp = max(0, self.e_hp - self._power(move))
            msg = move["flavor"]
            if self.e_hp <= 0:
                self.over, self.won = True, True
                self.log = ELDER_BATTLERS[self.ekey]["win"]
                return self.log
        self.h_hp = max(0, self.h_hp - self.e_atk)      # gentle response
        if self.h_hp <= 0:
            self.over, self.won = True, False
            self.log = ELDER_BATTLERS[self.ekey]["lose"]
        else:
            self.log = f"{msg}\n{ELDER_BATTLERS[self.ekey]['poke']}"
        return self.log


class EldermarkBattle:
    """The battle window: painted backdrop, enemy + hero sprites, two HP boxes,
    and a FIGHT/SKILL/ITEM/RUN menu. Crash-isolated by its caller."""

    MENU = [("fight", "FIGHT"), ("skill", "SKILL"), ("item", "ITEM"), ("run", "RUN")]

    def __init__(self, pet, enemy_key="gloomling", hero_name="Wanderer",
                 hero_lv=5, hero_hp=26, on_close=None, bg=None):
        self.pet = pet
        self.on_close = on_close
        self._bg_name = bg
        self.logic = EldermarkBattleLogic(enemy_key, hero_name, hero_lv, hero_hp)
        self._refs = []

        self.win = tk.Toplevel(pet.root)
        self.win.title("Eldermark — Battle")
        self.win.resizable(False, False)
        self.canvas = tk.Canvas(self.win, width=SCENE_W, height=SCENE_H,
                                highlightthickness=0, bg=ELDER_GREEN[0])
        self.canvas.pack()

        self.bg = self._load_bg()
        self.canvas.create_image(0, 0, anchor="nw", image=self.bg)
        self.canvas.create_oval(470, 238, 662, 288, outline="", fill=ELDER_GREEN[1])
        self.canvas.create_oval(96, 384, 300, 430, outline="", fill=ELDER_GREEN[1])

        self.enemy_img = self._load(ELDER_BATTLERS[self.logic.ekey]["sprite"],
                                    self._placeholder_enemy)
        self.enemy_item = self.canvas.create_image(566, 262, anchor="s",
                                                   image=self.enemy_img)
        self.hero_img = self._load("hero_up.png", self._placeholder_hero_back)
        self.canvas.create_image(198, 416, anchor="s", image=self.hero_img)

        self._enemy_box()
        self._hero_box()
        self._msg_box()
        self._menu_box()

        self.sel = 0
        self.phase = "message"          # message (intro/result) | menu
        self._anim = 0
        self._loop = None
        self._leave = None              # RUN auto-close timer
        self._closed = False
        self._set_message(self.logic.log)
        self._render_menu()
        self.win.bind("<KeyPress>", self._key)
        self.win.protocol("WM_DELETE_WINDOW", self.close)
        sw, sh = pet.root.winfo_screenwidth(), pet.root.winfo_screenheight()
        self.win.update_idletasks()
        self.win.geometry(f"+{max(0, (sw - SCENE_W) // 2)}"
                          f"+{max(0, (sh - SCENE_H) // 2 - 30)}")
        self.win.focus_force()
        self._tick()

    # -- art -----------------------------------------------------------------
    def _load(self, fname, placeholder):
        p = ELDER_ASSETS / fname
        if p.exists():
            try:
                img = tk.PhotoImage(file=str(p))
                self._refs.append(img)
                return img
            except tk.TclError:
                pass
        img = placeholder()
        self._refs.append(img)
        return img

    def _load_bg(self):
        for name in (self._bg_name, "battle_bg.png", "mosslight_gate_bg.png"):
            if name and (ELDER_ASSETS / name).exists():
                try:
                    img = tk.PhotoImage(file=str(ELDER_ASSETS / name))
                    self._refs.append(img)
                    return img
                except tk.TclError:
                    pass
        img = self._placeholder_bg()
        self._refs.append(img)
        return img

    def _placeholder_bg(self):
        im = tk.PhotoImage(width=SCENE_W, height=SCENE_H)
        im.put(ELDER_GREEN[1], to=(0, 0, SCENE_W, SCENE_H))
        im.put(ELDER_GREEN[0], to=(0, 0, SCENE_W, 150))
        im.put(ELDER_GREEN[2], to=(0, SCENE_H - 110, SCENE_W, SCENE_H))
        return im

    def _placeholder_enemy(self):
        w, h = 130, 120
        im = tk.PhotoImage(width=w, height=h)
        im.put(ELDER_GREEN[2], to=(w // 6, h // 4, 5 * w // 6, h))
        im.put(ELDER_GREEN[1], to=(w // 4, h // 8, 3 * w // 4, h // 2))
        im.put(ELDER_GREEN[0], to=(w // 3, h // 3, w // 3 + 9, h // 3 + 9))
        im.put(ELDER_GREEN[0], to=(3 * w // 5, h // 3, 3 * w // 5 + 9, h // 3 + 9))
        return im

    def _placeholder_hero_back(self):
        w, h = 56, 96
        im = tk.PhotoImage(width=w, height=h)
        im.put(ELDER_GREEN[2], to=(w // 4, 2, 3 * w // 4, h // 2))
        im.put(ELDER_GREEN[1], to=(w // 6, h // 2, 5 * w // 6, h - 4))
        im.put(ELDER_GREEN[0], to=(w // 6, h - 8, 5 * w // 6, h))
        return im

    # -- UI panels -----------------------------------------------------------
    def _panel(self, x0, y0, x1, y1):
        self.canvas.create_rectangle(x0, y0, x1, y1, fill=ELDER_GREEN[3],
                                     outline=ELDER_GREEN[0], width=4)

    def _hp_bar(self, x0, y, x1, frac):
        self.canvas.create_rectangle(x0, y, x1, y + 14, outline=ELDER_GREEN[0],
                                     width=2, fill=ELDER_GREEN[1])
        w = (x1 - x0 - 4) * max(0.0, min(1.0, frac))
        return self.canvas.create_rectangle(x0 + 2, y + 2, x0 + 2 + w, y + 12,
                                            outline="", fill=ELDER_GREEN[0])

    def _enemy_box(self):
        x0, y0, x1, y1 = 24, 24, 344, 104
        self._panel(x0, y0, x1, y1)
        self.canvas.create_text(x0 + 16, y0 + 14, anchor="nw", fill=ELDER_GREEN[0],
                                font=("Consolas", 15, "bold"), text=self.logic.ename)
        self.canvas.create_text(x1 - 16, y0 + 14, anchor="ne", fill=ELDER_GREEN[0],
                                font=("Consolas", 13, "bold"), text=f"Lv.{self.logic.e_lv}")
        self._ebar = (x0 + 16, y0 + 50, x1 - 16)
        self.e_fill = self._hp_bar(*self._ebar, self.logic.e_hp / self.logic.e_max)

    def _hero_box(self):
        x0, y0, x1, y1 = 388, 286, 696, 372
        self._panel(x0, y0, x1, y1)
        self.canvas.create_text(x0 + 16, y0 + 12, anchor="nw", fill=ELDER_GREEN[0],
                                font=("Consolas", 15, "bold"), text=self.logic.hname)
        self.canvas.create_text(x1 - 16, y0 + 12, anchor="ne", fill=ELDER_GREEN[0],
                                font=("Consolas", 13, "bold"), text=f"Lv.{self.logic.h_lv}")
        self._hbar = (x0 + 16, y0 + 42, x1 - 16)
        self.h_fill = self._hp_bar(*self._hbar, self.logic.h_hp / self.logic.h_max)
        self.h_num = self.canvas.create_text(x1 - 16, y1 - 10, anchor="se",
                                             fill=ELDER_GREEN[0], font=("Consolas", 12, "bold"),
                                             text=f"{self.logic.h_hp}/{self.logic.h_max}")

    def _msg_box(self):
        self._panel(24, 384, 430, 468)
        self.msg_item = self.canvas.create_text(42, 398, anchor="nw", fill=ELDER_GREEN[0],
                                                font=("Consolas", 14, "bold"), width=372, text="")
        self.msg_tip = self.canvas.create_text(418, 458, anchor="se", fill=ELDER_GREEN[1],
                                               font=("Consolas", 11, "bold"), text="")

    def _menu_box(self):
        self._panel(446, 384, 696, 468)
        self._cells = [(486, 408), (606, 408), (486, 444), (606, 444)]
        for (cx, cy), (_, label) in zip(self._cells, self.MENU):
            self.canvas.create_text(cx, cy, anchor="w", fill=ELDER_GREEN[0],
                                    font=("Consolas", 15, "bold"), text=label)
        self.cursor = self.canvas.create_text(0, 0, anchor="e", fill=ELDER_GREEN[0],
                                              font=("Consolas", 15, "bold"), text="▸")

    # -- state ---------------------------------------------------------------
    def _set_message(self, text):
        self.canvas.itemconfigure(self.msg_item, text=text)
        self.canvas.itemconfigure(self.msg_tip,
                                  text="Enter ▸" if self.phase == "message" else "")

    def _update_hp(self):
        for fill, bar, cur, mx in ((self.e_fill, self._ebar, self.logic.e_hp, self.logic.e_max),
                                   (self.h_fill, self._hbar, self.logic.h_hp, self.logic.h_max)):
            x0, y, x1 = bar
            w = (x1 - x0 - 4) * max(0.0, cur / mx)
            self.canvas.coords(fill, x0 + 2, y + 2, x0 + 2 + w, y + 12)
        self.canvas.itemconfigure(self.h_num, text=f"{self.logic.h_hp}/{self.logic.h_max}")

    def _render_menu(self):
        cx, cy = self._cells[self.sel]
        self.canvas.coords(self.cursor, cx - 10, cy)
        self.canvas.itemconfigure(self.cursor,
                                  state="normal" if self.phase == "menu" else "hidden")

    def _move_sel(self, dx, dy):
        col, row = self.sel % 2, self.sel // 2
        if dx:
            col = (col + dx) % 2
        if dy:
            row = (row + dy) % 2
        self.sel = row * 2 + col

    def _choose(self):
        action = self.MENU[self.sel][0]
        msg = self.logic.act(action)
        self._update_hp()
        self.phase = "message"
        self._set_message(msg)
        self._render_menu()
        if self.logic.won is None and self.logic.over:   # ran away — leave at once
            self._leave = self.win.after(700, self.close)

    # -- input ---------------------------------------------------------------
    def _key(self, e):
        ks = (e.keysym or "").lower()
        if ks == "escape":
            self.close()
            return
        if self.phase == "menu":
            if ks in ("right", "d"):
                self._move_sel(1, 0)
            elif ks in ("left", "a"):
                self._move_sel(-1, 0)
            elif ks in ("down", "s"):
                self._move_sel(0, 1)
            elif ks in ("up", "w"):
                self._move_sel(0, -1)
            elif ks in ("return", "space"):
                self._choose()
                return
            self._render_menu()
        elif self.phase == "message":
            if ks in ("return", "space"):
                if self.logic.over:
                    self.close()
                else:
                    self.phase = "menu"
                    self._set_message("What will you do?")
                    self._render_menu()

    # -- loop ----------------------------------------------------------------
    def _tick(self):
        if not self.win.winfo_exists():
            return
        self._anim += 1
        self.canvas.coords(self.enemy_item, 566, 262 + int(math.sin(self._anim * 0.08) * 3))
        self._loop = self.win.after(40, self._tick)

    def close(self):
        if self._closed:                 # idempotent: on_close fires exactly once
            return
        self._closed = True
        for job in (self._loop, self._leave):
            if job is not None:
                try:
                    self.win.after_cancel(job)
                except Exception:
                    pass
        self._loop = self._leave = None
        try:
            if self.win.winfo_exists():
                self.win.destroy()
        except Exception:
            pass
        if self.on_close:
            try:
                self.on_close(self.logic.won)
            except Exception:
                pass


class EldermarkJournal:
    """The Creature Journal — a gentle 'dex': every creature you've met, with a
    sprite and a few lines to READ. Befriended ones get a check. Esc closes."""

    def __init__(self, pet):
        self.pet = pet
        self._refs = []
        self._cache = {}
        self.ids = list(ELDER_CREATURES.keys())
        self.sel = 0
        self._closed = False

        self.win = tk.Toplevel(pet.root)
        self.win.title("Eldermark — Creature Journal")
        self.win.resizable(False, False)
        self.canvas = tk.Canvas(self.win, width=SCENE_W, height=SCENE_H,
                                highlightthickness=0, bg=ELDER_GREEN[1])
        self.canvas.pack()

        self.canvas.create_text(28, 22, anchor="nw", fill=ELDER_GREEN[0],
                                font=("Consolas", 20, "bold"), text="Creature Journal")
        self.count = self.canvas.create_text(SCENE_W - 28, 30, anchor="ne",
                                             fill=ELDER_GREEN[0], font=("Consolas", 14, "bold"),
                                             text="")
        self.canvas.create_line(24, 62, SCENE_W - 24, 62, fill=ELDER_GREEN[0], width=2)

        self.rows = [self.canvas.create_text(50, 92 + i * 42, anchor="w",
                     fill=ELDER_GREEN[0], font=("Consolas", 16, "bold"), text="")
                     for i in range(len(self.ids))]
        self.cursor = self.canvas.create_text(28, 92, anchor="w", fill=ELDER_GREEN[0],
                                              font=("Consolas", 16, "bold"), text="▸")

        self.canvas.create_rectangle(356, 80, SCENE_W - 24, SCENE_H - 58,
                                     fill=ELDER_GREEN[3], outline=ELDER_GREEN[0], width=4)
        cx = (356 + SCENE_W - 24) // 2
        self.d_name = self.canvas.create_text(cx, 86, anchor="n", fill=ELDER_GREEN[0],
                                              font=("Consolas", 18, "bold"), text="")
        self.d_sprite = self.canvas.create_image(cx, 266, anchor="s")
        self.d_lore = self.canvas.create_text(378, 280, anchor="nw", fill=ELDER_GREEN[0],
                                              font=("Consolas", 13, "bold"),
                                              width=SCENE_W - 24 - 378 - 14, text="")

        self.canvas.create_text(28, SCENE_H - 26, anchor="w", fill=ELDER_GREEN[0],
                                font=("Consolas", 13, "bold"),
                                text="Up / Down to browse    Esc to close")

        self._render()
        self.win.bind("<KeyPress>", self._key)
        self.win.protocol("WM_DELETE_WINDOW", self.close)
        sw, sh = pet.root.winfo_screenwidth(), pet.root.winfo_screenheight()
        self.win.update_idletasks()
        self.win.geometry(f"+{max(0, (sw - SCENE_W) // 2)}"
                          f"+{max(0, (sh - SCENE_H) // 2 - 30)}")
        self.win.focus_force()

    def _sprite(self, cid):
        if cid not in self._cache:
            p = ELDER_ASSETS / ELDER_CREATURES[cid]["sprite"]
            img = None
            if p.exists():
                try:
                    img = tk.PhotoImage(file=str(p))
                    if img.height() > 154:        # cap so tall art clears the title
                        f = (img.height() + 153) // 154
                        img = img.subsample(f, f)
                except tk.TclError:
                    img = None
            img = img or self._placeholder()
            self._cache[cid] = img
            self._refs.append(img)
        return self._cache[cid]

    def _placeholder(self):
        w, h = 96, 96
        im = tk.PhotoImage(width=w, height=h)
        im.put(ELDER_GREEN[2], to=(w // 6, h // 4, 5 * w // 6, h))
        im.put(ELDER_GREEN[3], to=(w // 4, h // 8, 3 * w // 4, h // 2))
        return im

    def _render(self):
        self.canvas.itemconfigure(
            self.count, text=f"Friends {len(ELDER_STATE.friends)}/{len(self.ids)}")
        for i, cid in enumerate(self.ids):
            met = cid in ELDER_STATE.met
            mark = " ✓" if cid in ELDER_STATE.friends else (" ·" if met else "")
            name = ELDER_CREATURES[cid]["name"] if met else "???"
            self.canvas.itemconfigure(self.rows[i], text=f"{name}{mark}")
        self.canvas.coords(self.cursor, 28, 92 + self.sel * 42)
        cid = self.ids[self.sel]
        if cid in ELDER_STATE.met:
            self.canvas.itemconfigure(self.d_name, text=ELDER_CREATURES[cid]["name"])
            self.canvas.itemconfigure(self.d_lore, text=ELDER_CREATURES[cid]["lore"])
            self.canvas.itemconfigure(self.d_sprite, image=self._sprite(cid), state="normal")
        else:
            self.canvas.itemconfigure(self.d_name, text="???")
            self.canvas.itemconfigure(self.d_lore,
                                      text="A creature you haven't met yet.\n"
                                           "Explore Eldermark to find it!")
            self.canvas.itemconfigure(self.d_sprite, state="hidden")

    def _key(self, e):
        ks = (e.keysym or "").lower()
        if ks == "escape":
            self.close()
        elif ks in ("up", "w"):
            self.sel = (self.sel - 1) % len(self.ids)
            self._render()
        elif ks in ("down", "s"):
            self.sel = (self.sel + 1) % len(self.ids)
            self._render()

    def close(self):
        if self._closed:
            return
        self._closed = True
        try:
            if self.win.winfo_exists():
                self.win.destroy()
        except Exception:
            pass


class ChatWindow:
    """iMessage-style chat window opened by clicking the pet.

    Messages are kept in a history list and re-flowed whenever the window is
    resized, so bubbles always wrap to the current width.
    """

    def __init__(self, pet: PetOverlay):
        self.pet = pet
        self.t = resolve_chat_theme(pet.settings.get("chat_theme", "auto"))
        self.chat_text_size = pet.settings.get("chat_text_size", 10)
        self.spell = pet.spell
        self.last = None       # (raw, cleaned, rec, prompt)
        self.pending = None    # active follow-up Q&A state
        self.active_game = None  # a running game (NumberGuess/Hangman/…), or None
        self._pre_game_geom = None  # window geom to restore after a big game
        self.messages = []     # (kind, text) history, re-flowed on resize
        self._frames = []      # embedded button frames, destroyed on re-flow
        self._typing = False
        self._ai_busy = False  # one local-AI stream at a time
        self._y = 12
        self._cw = 440         # canvas width used for the current layout
        self._resize_job = None
        self._placeholder_on = False
        self._bulk = False     # True during a full reflow: defer the gradient
        self._localai_note_shown = False  # one-time "no Ollama -> prompt" note
        self._session_start = 0  # index in self.messages where THIS session's
                                 # new messages begin (loaded history precedes it)

        win = tk.Toplevel(pet.root)
        self.win = win
        win.withdraw()  # stay hidden until the dark title bar is set (no flash)
        win.title(f"{pet.pet_name()} — AskPet")
        win.wm_attributes("-topmost", True)
        # Soft whole-window translucency for the "frosted" look. Harmless if
        # the platform ignores -alpha.
        try:
            win.wm_attributes("-alpha", CHAT_WIN_ALPHA)
        except tk.TclError:
            pass
        win.minsize(340, 400)
        self._place_near_pet(440, 600)
        win.configure(bg=self.t["WIN_BG"])

        self._build_header()

        # Conversation canvas (a gradient is painted as its bottom layer).
        self.log_frame = tk.Frame(win, bg=self.t["WIN_BG"])
        self.log_frame.pack(fill="both", expand=True)
        self.canvas = tk.Canvas(self.log_frame, bg=self.t["GRAD_TOP"],
                                highlightthickness=0)
        # Slim, flat, theme-colored scrollbar (replaces the chunky ttk one).
        self._scroll = SlimScrollbar(self.log_frame, self.canvas.yview,
                                     trough=self.t["SCROLL_TROUGH"],
                                     thumb=self.t["SCROLL_THUMB"])
        self.canvas.configure(yscrollcommand=self._scroll.set)
        self._scroll.pack(side="right", fill="y")
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<MouseWheel>", self._on_wheel)
        self.canvas.bind("<Configure>", self._on_canvas_resize)

        # Input row: entry with placeholder + round send button
        self.input_frame = tk.Frame(win, bg=self.t["WIN_BG"], padx=8, pady=8)
        self.input_frame.pack(fill="x")
        # Button first, from the right, so the entry can never squeeze it out
        # (a Text widget's default requested width is ~80 chars).
        self.send_btn = tk.Button(self.input_frame, text="↑", command=self.send,
                                  bg=self.t["SEND_BG"], fg=self.t["SEND_FG"],
                                  relief="flat", font=("Segoe UI", 13, "bold"),
                                  width=3, cursor="hand2",
                                  activebackground=self.t["SEND_ACTIVE"],
                                  activeforeground=self.t["SEND_FG"])
        self.send_btn.pack(side="right", padx=(8, 0), fill="y")
        self.entry_holder = tk.Frame(self.input_frame, bg=self.t["ENTRY_BORDER"],
                                     padx=1, pady=1)
        self.entry_holder.pack(side="left", fill="both", expand=True)
        self.entry = tk.Text(self.entry_holder, height=2, width=10, wrap="word",
                             relief="flat", font=("Segoe UI", 10), undo=True,
                             padx=8, pady=6, bg=self.t["ENTRY_BG"],
                             fg=self.t["ENTRY_TEXT"],
                             insertbackground=self.t["ENTRY_TEXT"])
        self.entry.pack(fill="both", expand=True)
        SpellSupport(self.entry, self.spell)
        self.entry.bind("<Return>", self._on_return)
        self.entry.bind("<FocusIn>", self._clear_placeholder)
        self.entry.bind("<FocusOut>", self._set_placeholder)
        # Swimmer-name autocomplete from a running DeckSide. Built AFTER
        # SpellSupport (line above) so its add="+" KeyRelease stacks onto the
        # spellchecker's instead of replacing it.
        self.typeahead = RosterTypeahead(self)
        # Slash-command palette ('/' at the start of a message).
        self.slash = SlashCommands(self)

        # Restore the saved transcript (read-only) above a "new chat" divider:
        # each open is a fresh session that still shows everything up to the
        # last clear. This session's new messages are appended on close.
        for kind, text in load_chat_history():
            self.messages.append(("histprompt" if kind == "prompt" else kind, text))
        if self.messages:
            self.messages.append(("caption", "─────────  new chat  ─────────"))
        self.messages.append(("caption", datetime.now().strftime("Today %H:%M")))
        self.messages.append(("pet", CHAT_GREETING))
        self._session_start = len(self.messages)
        self._render_all()
        self.entry.focus_set()
        # A destroyed window cancels its pending after() callbacks, so the
        # poll loop can't do this cleanup itself.
        self._ai_req = None
        self._close_job = None
        win.bind("<Destroy>", self._on_destroy)
        # Click-outside-closes: when focus leaves the chat for something that
        # isn't ours (another app, the desktop), auto-close. Deferred and
        # checked via focus_get() so focus moving to our own entry, dropdowns,
        # or the pet's right-click menu doesn't trip it. See _check_close.
        win.bind("<FocusOut>", self._schedule_close_check)

        # Theme the native title bar to match, then reveal the window.
        _set_titlebar_dark(win, self.t is CHAT_THEMES["dark"])
        win.deiconify()
        win.lift()
        self.entry.focus_set()

    def _schedule_close_check(self, *_):
        if self._close_job:
            try:
                self.win.after_cancel(self._close_job)
            except Exception:
                pass
        self._close_job = self.win.after(140, self._check_close)

    def _check_close(self):
        # Coalesced FocusOut handler. Use focus_displayof(), NOT focus_get():
        # focus_get() returns Tk's app-internal focus, which on Windows
        # persists even after another OS app becomes foreground (so it never
        # reports None on click-away). focus_displayof() returns None only when
        # no window of THIS app holds the display's input focus — i.e. another
        # application or the desktop took over. Focus on our own entry,
        # dropdowns, or the pet still returns a widget, so those don't close it.
        self._close_job = None
        if not self.is_open():
            return
        if getattr(self.pet, "_menu_open", False):
            return  # the pet's right-click menu is up; keep the chat open
        if self._ai_busy:
            return  # a local-AI answer is still streaming — don't drop it
        if self.active_game is not None:
            return  # a game is running — don't close on a click away mid-game
        # Our completion dropdowns are separate overrideredirect Toplevels;
        # keep the chat open while one is showing so a click inside it can't be
        # read as a click away.
        if getattr(self, "typeahead", None) and self.typeahead.menu.visible():
            return
        if getattr(self, "slash", None) and self.slash.menu.visible():
            return
        try:
            foc = self.win.focus_displayof()
        except (tk.TclError, KeyError):
            return  # ambiguous focus window (e.g. our own popup) -> keep open
        if foc is None:
            self.close()

    def _on_destroy(self, event):
        if event.widget is not self.win:
            return
        self._persist_session()  # save this session's transcript before teardown
        # A destroyed window cancels its own pending after() callbacks, but
        # cancel ours explicitly to match _schedule_close_check and avoid a
        # stray _check_close on a dead widget.
        if self._close_job:
            try:
                self.win.after_cancel(self._close_job)
            except Exception:
                pass
        if self._ai_req:
            self._ai_req["cancel"].set()

    def _persist_session(self):
        """Append this session's NEW conversation (user/pet/prompt) to the saved
        chat history. Skipped: loaded history + greeting/divider (they precede
        _session_start), the interactive 'actions'/'chips' rows (kind filter),
        the synthetic UI greetings, and a still-streaming answer (whose text is
        only a partial buffer until the stream finishes)."""
        try:
            streaming = (self._ai_req.get("msg_index")
                         if self._ai_busy and self._ai_req else None)
            new = []
            for i in range(self._session_start, len(self.messages)):
                if i == streaming:
                    continue  # don't save a truncated mid-stream answer
                kind, text = self.messages[i]
                if kind not in CHAT_PERSIST_KINDS or not text:
                    continue
                if kind == "pet" and text in EPHEMERAL_PET_TEXTS:
                    continue  # a UI greeting, not real conversation
                new.append((kind, text))
            append_chat_messages(new)
        except Exception:
            pass  # never let a save failure block window teardown

    def clear_view(self):
        """Reset the open chat to a fresh session (the saved history file has
        already been cleared by the caller)."""
        self.last = None
        self.pending = None
        if self._ai_req:  # stop an in-flight stream so its poll can't redraw
            self._ai_req["cancel"].set()
        self._ai_req = None
        self._ai_busy = False
        for f in self._frames:
            f.destroy()
        self._frames = []
        self.messages = [
            ("caption", datetime.now().strftime("Today %H:%M")),
            ("pet", CHAT_GREETING),
        ]
        self._session_start = len(self.messages)
        self._render_all()

    # ---- header --------------------------------------------------------------

    def _build_header(self):
        self.header = tk.Frame(self.win, bg=self.t["HEADER_BG"])
        self.header.pack(fill="x")
        self.avatar_label = tk.Label(self.header, bg=self.t["HEADER_BG"])
        self.avatar_label.pack(side="left", padx=(10, 8), pady=4)
        self.header_box = tk.Frame(self.header, bg=self.t["HEADER_BG"])
        self.header_box.pack(side="left", pady=4)
        self.header_name = tk.Label(self.header_box, bg=self.t["HEADER_BG"],
                                    fg=self.t["HEADER_TEXT"], anchor="w",
                                    font=("Segoe UI", 11, "bold"))
        self.header_name.pack(anchor="w")
        self.header_sub = tk.Label(self.header_box, bg=self.t["HEADER_BG"],
                                   fg=self.t["CAPTION"], anchor="w",
                                   font=("Segoe UI", 8))
        self.header_sub.pack(anchor="w")
        self.divider = tk.Frame(self.win, bg=self.t["DIVIDER"], height=1)
        self.divider.pack(fill="x")
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
        avatar = frame.subsample(factor, factor)
        # The sprite carries the magenta transparency key; punch those pixels
        # out so the avatar sits cleanly on the header background.
        # PhotoImage.get() may return a tuple of ints or a "r g b" string
        # depending on the Tcl layer, so normalize before comparing.
        key = tuple(int(self.pet.sprites.key[i:i + 2], 16) for i in (1, 3, 5))
        try:
            for y in range(avatar.height()):
                for x in range(avatar.width()):
                    px = avatar.get(x, y)
                    if isinstance(px, str):
                        px = tuple(int(v) for v in px.split())
                    else:
                        px = tuple(int(v) for v in px)
                    if px[:3] == key:
                        avatar.transparency_set(x, y, True)
        except (tk.TclError, ValueError):
            pass
        return avatar

    # ---- window plumbing ------------------------------------------------------

    def _place_near_pet(self, w, h):
        px, py = self.pet.root.winfo_x(), self.pet.root.winfo_y()
        sw, sh = self.win.winfo_screenwidth(), self.win.winfo_screenheight()
        x = px - w - 12 if px > sw // 2 else px + self.pet.sprites.w + 12
        y = py + self.pet.sprites.h - h
        x = min(max(8, x), sw - w - 8)
        y = min(max(8, y), sh - h - 60)
        self.win.geometry(f"{w}x{h}+{x}+{y}")

    def _resize_window(self, w, h):
        """Resize in place, keeping the window on-screen (used by game mode)."""
        self.win.update_idletasks()
        x, y = self.win.winfo_x(), self.win.winfo_y()
        sw, sh = self.win.winfo_screenwidth(), self.win.winfo_screenheight()
        x = min(max(8, x), sw - w - 8)
        y = min(max(8, y), sh - h - 60)
        self.win.geometry(f"{w}x{h}+{x}+{y}")

    def _game_win_size(self):
        """A nearly-fullscreen 'arcade' size, clamped so it stays usable."""
        sw, sh = self.win.winfo_screenwidth(), self.win.winfo_screenheight()
        w = min(1400, max(720, int(sw * 0.82)))
        h = max(600, int(sh * 0.92))
        return w, h

    def _enter_game_mode(self):
        """Expand the chat to a big, centered, almost-fullscreen 'arcade'
        window, remembering the current geometry so quitting restores it."""
        if self._pre_game_geom is None:
            try:
                self._pre_game_geom = self.win.geometry()
            except tk.TclError:
                self._pre_game_geom = None
        w, h = self._game_win_size()
        sw, sh = self.win.winfo_screenwidth(), self.win.winfo_screenheight()
        x = max(8, (sw - w) // 2)
        y = max(8, (sh - h) // 2 - 20)
        self.win.geometry(f"{w}x{h}+{x}+{y}")

    def _exit_game_mode(self):
        """Restore the pre-game window size when a screen-style game ends."""
        geom, self._pre_game_geom = self._pre_game_geom, None
        if geom:
            try:
                self.win.geometry(geom)
            except tk.TclError:
                pass

    def is_open(self):
        return self.win.winfo_exists()

    def close(self):
        if self.is_open():
            self.win.destroy()

    def apply_theme(self):
        """Re-resolve the chat theme and restyle the open window in place, then
        re-flow so every bubble/caption repaints in the new palette."""
        was_dark = self.t is CHAT_THEMES["dark"]
        self.t = resolve_chat_theme(self.pet.settings.get("chat_theme", "auto"))
        self.win.configure(bg=self.t["WIN_BG"])
        self.header.configure(bg=self.t["HEADER_BG"])
        self.avatar_label.configure(bg=self.t["HEADER_BG"])
        self.header_box.configure(bg=self.t["HEADER_BG"])
        self.header_name.configure(bg=self.t["HEADER_BG"], fg=self.t["HEADER_TEXT"])
        self.header_sub.configure(bg=self.t["HEADER_BG"], fg=self.t["CAPTION"])
        self.divider.configure(bg=self.t["DIVIDER"])
        self.log_frame.configure(bg=self.t["WIN_BG"])
        self.canvas.configure(bg=self.t["GRAD_TOP"])
        self.input_frame.configure(bg=self.t["WIN_BG"])
        self.entry_holder.configure(bg=self.t["ENTRY_BORDER"])
        self.send_btn.configure(bg=self.t["SEND_BG"], fg=self.t["SEND_FG"],
                                activebackground=self.t["SEND_ACTIVE"],
                                activeforeground=self.t["SEND_FG"])
        ph = self._placeholder_on
        self.entry.configure(
            bg=self.t["ENTRY_BG"], insertbackground=self.t["ENTRY_TEXT"],
            fg=self.t["ENTRY_PLACEHOLDER"] if ph else self.t["ENTRY_TEXT"])
        self._scroll.set_colors(self.t["SCROLL_TROUGH"], self.t["SCROLL_THUMB"])
        now_dark = self.t is CHAT_THEMES["dark"]
        _set_titlebar_dark(self.win, now_dark)
        if now_dark != was_dark:
            # The title bar repaints only on the next activation, so re-map the
            # window to apply the new caption color immediately.
            self.win.withdraw()
            self.win.deiconify()
            self.win.lift()
            self.entry.focus_set()
        self._render_all()

    def on_pet_changed(self):
        self.win.title(f"{self.pet.pet_name()} — AskPet")
        self._update_header()
        self._add("caption", f"{self.pet.pet_name()} joined the chat "
                             f"(art by {pet_credit(self.pet.pet_meta)})")
        self._add("pet", PETSWITCH_GREETING)

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
            self.entry.config(fg=self.t["ENTRY_PLACEHOLDER"])
            self.entry.delete("1.0", "end")
            self.entry.insert("1.0", "Message  ·  / commands · @ swimmers")

    def _clear_placeholder(self, *_):
        if self._placeholder_on:
            self._placeholder_on = False
            self.entry.delete("1.0", "end")
            self.entry.config(fg=self.t["ENTRY_TEXT"])

    # ---- bubble drawing ---------------------------------------------------------

    def _round_rect(self, x1, y1, x2, y2, r=14, **kw):
        pts = [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2,
               x2 - r, y2, x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]
        return self.canvas.create_polygon(pts, smooth=True, **kw)

    def _paint_gradient(self):
        """Vertical gradient as the canvas's bottom layer. tkinter has no
        native gradient, so paint horizontal bands and lower them under the
        bubbles. Covers the taller of the viewport or the content so neither a
        short conversation nor a scrolled one reveals a bare strip."""
        self.canvas.delete("grad")
        h = max(self.canvas.winfo_height(), self._y, 1)
        w = max(self.canvas.winfo_width(), self._cw, 1)
        top, bot = self.t["GRAD_TOP"], self.t["GRAD_BOTTOM"]
        bands = 64
        for i in range(bands):
            y1 = h * i // bands
            y2 = h * (i + 1) // bands
            c = _lerp_color(top, bot, i / (bands - 1))
            self.canvas.create_rectangle(0, y1, w, y2, fill=c, outline=c,
                                         tags="grad")
        self.canvas.tag_lower("grad")

    def _finish(self, bottom):
        self._y = bottom + 8
        self.canvas.configure(scrollregion=(0, 0, self._cw, self._y))
        # During a full reflow the gradient is painted once at the end (see
        # _render_all), not once per message — repainting it per line would
        # build and discard 64 rectangles for every bubble.
        if not self._bulk:
            self._paint_gradient()
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
        self._bulk = True
        for kind, text in self.messages:
            self._draw(kind, text)
        if self._typing:
            self._draw_typing()
        self._bulk = False
        self._paint_gradient()

    def _draw(self, kind, text):
        if kind == "caption":
            self._draw_caption(text)
        elif kind == "user":
            self._draw_bubble(text, "right", self.t["USER_BUBBLE"],
                              self.t["USER_TEXT"])
        elif kind == "pet":
            self._draw_bubble(text, "left", self.t["PET_BUBBLE"],
                              self.t["PET_TEXT"])
        elif kind == "game":
            self._draw_game_screen(text)
        elif kind == "chips":
            self._draw_chips(text)
        elif kind == "prompt":
            self._draw_bubble(text, "left", self.t["PROMPT_BUBBLE"],
                              self.t["PROMPT_TEXT"], font=("Consolas", 8))
            self._draw_actions()
        elif kind == "histprompt":  # a saved prompt from history: read-only,
            self._draw_bubble(text, "left", self.t["PROMPT_BUBBLE"],  # no actions
                              self.t["PROMPT_TEXT"], font=("Consolas", 8))
        elif kind == "actions":
            self._draw_actions(payload=text)

    def _draw_chips(self, items):
        """Clickable module/skill chips, two per row; click shows the text."""
        holder = tk.Frame(self.canvas, bg=self.t["CHIP_BG"])
        row = None
        for i, it in enumerate(items):
            if i % 2 == 0:
                row = tk.Frame(holder, bg=self.t["CHIP_BG"])
                row.pack(anchor="w")
            ttk.Button(row, text=it["label"],
                       command=lambda it=it: self._show_item(it)).pack(
                side="left", padx=(0, 4), pady=2)
        self._frames.append(holder)
        item = self.canvas.create_window(12, self._y, window=holder, anchor="nw")
        self.win.update_idletasks()
        self._finish(self.canvas.bbox(item)[3])

    def _show_item(self, it):
        source = AGENT_MODULES if it["kind"] == "module" else SKILL_TEMPLATES
        obj = source.get(it["key"])
        if not obj:
            return
        text = f"{obj['name']}\n\n{obj['body']}"
        if obj.get("steps"):
            text += "\n" + "\n".join(f"{i}. {s}" for i, s in enumerate(obj["steps"], 1))
        self._add("pet", text)

    # ---- text size (user-adjustable chat font) ---------------------------------

    def _bubble_font(self):
        return ("Segoe UI", self.chat_text_size)

    def _caption_font(self):
        return ("Segoe UI", max(7, self.chat_text_size - 2))

    def set_chat_text_size(self, size):
        """Live-apply a new chat text size and reflow the whole transcript."""
        self.chat_text_size = max(7, min(18, int(size)))
        self._render_all()

    def _draw_caption(self, text):
        item = self.canvas.create_text(self._cw // 2, self._y + 4, text=text,
                                       fill=self.t["CAPTION"], font=self._caption_font(),
                                       anchor="n", width=max(120, self._cw - 60),
                                       justify="center")
        self._finish(self.canvas.bbox(item)[3])

    def _draw_bubble(self, text, side, fill, fg, font=None, pad=10):
        # font=None -> the user-adjustable chat size; callers that pass an
        # explicit font (the fixed-width prompt block) keep their own size.
        if font is None:
            font = self._bubble_font()
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

    def _draw_game_screen(self, text):
        """A big, fixed-width, NO-WRAP retro 'screen' for ASCII game art. The
        normal bubbles word-wrap in a proportional font (which mangles art and
        health bars); this uses a monospace font and width=0 so columns line up.
        The console FILLS the window (no wasted margins) with the largest font
        that still fits, and the text block is centered so art reads as the
        centerpiece. Dark green-on-near-black panel for the arcade look."""
        pad, bg, fg, border = 18, "#0e1a12", "#a9e6a0", "#244a30"
        avail = max(320, self._cw - 24)        # the console spans the window
        # Pick the LARGEST comfortable monospace size whose widest line still
        # fits the window — a big, immersive screen instead of a narrow box.
        size = max(13, min(self.chat_text_size + 6, 24))
        while True:
            font = ("Consolas", size)
            tmp = self.canvas.create_text(0, -10000, text=text, font=font,
                                          width=0, anchor="nw")
            bb = self.canvas.bbox(tmp)
            self.canvas.delete(tmp)
            tw, th = bb[2] - bb[0], bb[3] - bb[1]
            if tw + 2 * pad <= avail or size <= 13:
                break
            size -= 1
        panel_w = avail                        # fill the window width
        x1 = max(12, (self._cw - panel_w) // 2)
        x2 = x1 + panel_w
        by2 = self._y + th + 2 * pad
        self._round_rect(x1, self._y, x2, by2, r=12, fill=bg, outline=border)
        text_x = x1 + max(pad, (panel_w - tw) // 2)   # center the whole block
        self.canvas.create_text(text_x, self._y + pad, text=text, font=font,
                                fill=fg, width=0, anchor="nw")
        self._finish(by2)

    def _draw_actions(self, payload=None):
        # Without a payload the buttons act on self.last (the prompt flow);
        # with one (local-AI answers) they act on that answer forever, no
        # matter what gets generated later.
        btns = tk.Frame(self.canvas, bg=self.t["CHIP_BG"])
        if payload is None:
            actions = (("📋 Copy", self._copy_last), ("💾 Save", self._save_last),
                       ("🛠 Adjust in editor", self._open_in_editor))
        else:
            actions = (("📋 Copy", lambda: self._copy_payload(payload)),
                       ("💾 Save", lambda: self._save_payload(payload)),
                       ("🛠 Adjust in editor",
                        lambda: self.pet.open_editor(prefill=payload[0])))
        for label, cmd in actions:
            ttk.Button(btns, text=label, command=cmd).pack(side="left", padx=(0, 4))
        self._frames.append(btns)
        item = self.canvas.create_window(12, self._y, window=btns, anchor="nw")
        self.win.update_idletasks()
        self._finish(self.canvas.bbox(item)[3])

    def _copy_payload(self, payload):
        self.win.clipboard_clear()
        self.win.clipboard_append(payload[3])
        self._add("pet", "Copied — ready to paste. ✅")
        self.pet.celebrate()

    def _save_payload(self, payload):
        save_history_entry(*payload)
        self._add("pet", "Saved to your local history. 💾")

    def _draw_typing(self):
        self._round_rect(12, self._y, 64, self._y + 30, r=15,
                         fill=self.t["PET_BUBBLE"], outline=self.t["PET_BUBBLE"])
        self.canvas.create_text(38, self._y + 15, text="• • •",
                                fill=self.t["CAPTION"], font=self._bubble_font())
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
        # When the slash palette is open, Enter picks the highlighted command
        # (a deliberate "/..." context, so no risk of hijacking a real send).
        if getattr(self, "slash", None) and self.slash.menu.visible():
            self.slash.menu.accept()
            return "break"
        # Otherwise Enter ALWAYS sends; the name dropdown is just dismissed
        # (accept a name with Tab or a click, never Enter).
        if getattr(self, "typeahead", None):
            self.typeahead.menu.hide()
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
        self.pet.idle_ticks = 0
        if self.pending:
            self._handle_answer(raw)
        elif self.active_game is not None and parse_slash(raw) is None:
            # While a game is running, plain messages are moves; a /command
            # (e.g. /games) still routes normally, and plain 'quit' exits.
            self._handle_game_input(raw)
        else:
            self._start_request(raw)

    # ---- follow-up question flow ---------------------------------------------

    def _start_request(self, raw):
        # Explicit /slash command? It forces a lane — no heuristic guessing.
        parsed = parse_slash(raw)
        if parsed is not None:
            self._run_slash(parsed, raw)
            return
        # Question about prompting/AskPet? Answer it instead of
        # generating a prompt.
        help_answer = answer_help_question(raw)
        if help_answer:
            self._show_typing()
            self.win.after(random.randint(400, 800),
                           lambda: self._deliver_help(help_answer))
            return
        # "Remember that …" — store a durable fact the pet recalls in future
        # chats (injected into its persona). Captured explicitly; works even
        # without local AI.
        fact = remember_fact(raw)
        if fact is not None:
            added = add_pet_memory(fact)
            self._add("pet", REMEMBER_ACK if added else REMEMBER_DUP)
            return
        cleaned = clean_text(raw, self.spell)
        rec = recommend(cleaned)
        # A live DeckSide meet-day question is answered straight from the
        # running DeckSide app (read-only) — no local model needed, so this
        # comes before the Ollama gate.
        if not self._ai_busy and deckside_data_lane(raw):
            self._deckside_request(raw, cleaned, rec)
            return
        # General chat is the default: the local model answers, rewrites,
        # summarizes, reviews, drafts — local_ai_lane() always returns a lane.
        if self.pet.local_ai_ready() and not self._ai_busy:
            lane = local_ai_lane(raw, rec)
            if lane:
                self._local_ai_request(lane, raw, cleaned, rec)
                return
        # No local model (Ollama absent or turned off): fall back to building a
        # prompt, and say so once so it isn't a silent surprise.
        if not self.pet.local_ai_ready() and not self._localai_note_shown:
            self._localai_note_shown = True
            self._add("caption", "Local AI (Ollama) isn't running — I'll build "
                                 "you a prompt instead. Right-click me → Local AI.")
        self._standard_request(raw, cleaned, rec)

    def _run_slash(self, parsed, raw):
        """Dispatch a /command (the user bubble is already shown by send())."""
        name, arg = parsed
        entry = SLASH_BY_NAME.get(name)
        if entry is None:
            # A library-template command? "/incident_rca <task>" forces that
            # template instead of letting recommend() guess one.
            if name in PROMPT_TEMPLATES:
                if not arg:
                    tname = PROMPT_TEMPLATES[name]["name"]
                    self._add("pet", f"Add the task after /{name} (the "
                                     f"“{tname}” template) — e.g. “/{name} …”.")
                    return
                self._build_template_prompt(arg, name)
                return
            self._add("pet", f"I don't know /{name}. Type /help to see what I can do.")
            return
        action = entry[1]
        if action == "help":
            self._show_help()
            return
        if action == "games":
            self._show_games_menu()
            return
        if action == "play":
            self._start_game(arg)
            return
        if action == "eldermark":
            self._open_eldermark_world()
            return
        if not arg:
            self._add("pet", f"Add your text after /{name} — e.g. “/{name} …”.")
            return
        cleaned = clean_text(arg, self.spell)
        rec = recommend(cleaned)
        if action == "prompt":
            self._standard_request(arg, cleaned, rec)
            return
        # The writing/answer lanes need the local model. (FPV/knowledge is no
        # longer a slash command — it's auto-detected from the message.)
        if self.pet.local_ai_ready() and not self._ai_busy:
            self._local_ai_request(action, arg, cleaned, rec)
        else:
            self._add("caption", "Local AI (Ollama) isn't running — "
                                 "building you a prompt instead.")
            self._standard_request(arg, cleaned, rec)

    def _open_eldermark_world(self):
        """Open the painted Eldermark scene (Mosslight Gate) in its own window.
        A scene bug must never break the chat, so failure is caught/reported."""
        self._add("game", "Opening Eldermark — Mosslight Gate. Use the arrow keys "
                          "(or WASD) to explore, and press Space to talk. 🌿")
        try:
            EldermarkScene(self.pet)
        except Exception:
            self._add("pet", "Hmm, I couldn't open Eldermark just now — let's "
                             "play a game instead? Say /play. 🐾")

    def _build_template_prompt(self, task, template_key):
        """Build a prompt with a specific template forced (used by the
        /<template> library commands). Mirrors _generate but pins the template
        + its destination instead of recompute-and-guess."""
        tmpl = PROMPT_TEMPLATES.get(template_key)
        if tmpl is None:  # defensive: only ever called for a known key
            return
        cleaned = clean_text(task, self.spell)
        rec = recommend(cleaned)
        rec["template"] = template_key
        rec["destination"] = tmpl.get("destination", rec["destination"])
        # The user explicitly picked this template, so ITS topics drive the
        # office-vs-codex constraint flavor in build_prompt — not whatever
        # recommend() inferred from the task wording. (Generic templates have
        # no topics; keep the task's so office flavor still applies sensibly.)
        rec["topics"] = tmpl.get("topics") or rec["topics"]
        # Keep the shown reason coherent with the template the user picked
        # (recommend()'s reason was for whatever it had guessed).
        rec["reason"] = f"Using the “{tmpl['name']}” template you picked."
        prompt = build_prompt(cleaned, rec, rec["modules"], rec["skills"], [])
        self.last = (task, cleaned, rec, prompt)
        save_history_entry(task, cleaned, rec, prompt)
        self._show_typing()
        self.win.after(random.randint(500, 900),
                       lambda: self._deliver_reply(cleaned, rec, prompt))

    def _show_help(self):
        lines = ["Just type to chat — I can answer, explain, rewrite, "
                 "summarize, review, or draft. For specific jobs, type / then "
                 "a command:"]
        lines += [f"  {name}  —  {desc}" for name, desc, _ in SLASH_COMMANDS]
        lines.append(f"…plus a command for each of my {len(PROMPT_TEMPLATES)} "
                     f"prompt templates — type / and a few letters to find one.")
        lines.append("And we can play games! Type /games. 🎮")
        self._add("pet", "\n".join(lines))

    # ---- games ----------------------------------------------------------------

    def _show_games_menu(self):
        self._start_picker()

    def _start_picker(self):
        """Open the interactive game picker: a big arcade screen listing every
        game; the kid types a number to launch one."""
        self.active_game = GamePicker()
        self._enter_game_mode()
        self._add("game", self.active_game.start())

    def _start_game(self, arg):
        game = start_game(arg)
        if game is None:                 # '/play' alone or an unknown name
            if arg:
                self._add("pet", f"I don't know the game “{arg}”.")
            self._start_picker()
            return
        self.active_game = game
        self._enter_game_mode()          # every game plays in the big window
        self._add("game", game.start())

    def _handle_game_input(self, raw):
        """Route a move to the running game; 'quit' returns to normal chat."""
        game = self.active_game
        if raw.strip().lower() in ("quit", "stop", "exit", "done"):
            self.active_game = None
            self._exit_game_mode()
            self._add("pet", "Okay, game over for now — that was fun! "
                             "Say /play anytime to play again. 🐾")
            return
        try:
            reply = game.handle(raw)
        except Exception:  # a game bug must never break the chat
            self.active_game = None
            self._exit_game_mode()
            self._add("pet", "Oops, that game got muddled — let's pick another! "
                             "Say /play. 🐾")
            return
        # The picker turns a number into a real game — swap it in (window is
        # already the big arcade size, so no resize needed).
        if isinstance(game, GamePicker) and getattr(game, "pick", None):
            chosen = start_game(game.pick)
            if chosen is not None:
                self.active_game = chosen
                self._add("game", chosen.start())
                return
        self._add("game", reply)
        if game.is_over:
            self.active_game = None
            self._exit_game_mode()
            self._add("caption", "Game over — say /play to play again.")

    def _standard_request(self, raw, cleaned, rec):
        questions = clarifying_questions(cleaned, rec)
        if questions:
            self.pending = {"raw": raw, "answers": [], "questions": questions, "qi": 0}
            self._show_typing()
            self.win.after(random.randint(400, 800), self._ask_next_question)
        else:
            self._generate(raw, [])

    # ---- local AI lane ---------------------------------------------------------

    # Poll ticks are 120ms: allow 180s for the first chunk (cold model
    # load) and 60s for a stall mid-stream before abandoning.
    AI_FIRST_CHUNK_TICKS = 1500
    AI_STALL_TICKS = 500

    def _recent_history(self, max_msgs=8):
        """Recent conversation turns as chat messages for short-term memory:
        user -> user, pet replies -> assistant. Skips greetings and
        non-conversational rows, and EXCLUDES the just-added current message
        (it's passed separately as the prompt). Includes restored history, so
        the pet remembers across reopens too."""
        turns = []
        for kind, text in self.messages[:-1]:
            if not text:
                continue
            if kind == "user":
                turns.append({"role": "user", "content": text})
            elif kind == "pet" and text not in EPHEMERAL_PET_TEXTS:
                turns.append({"role": "assistant", "content": text})
        return turns[-max_msgs:]

    def _local_ai_request(self, lane, raw, cleaned, rec):
        model = self.pet.local_model()
        if not model:  # model list changed under us
            self._standard_request(raw, cleaned, rec)
            return
        # Knowledge lane: ground the answer in pack excerpts; if retrieval
        # finds nothing relevant, degrade to the plain answer lane.
        source_note = ""
        if lane == "knowledge":
            packs = knowledge_packs_for(raw)
            system = knowledge_system_prompt(packs, raw) if packs else None
            if system:
                names = ", ".join(p["name"] for p in packs)
                source_note = f" · sources: {names}"
            else:
                system = LOCAL_AI_LANES["hobby"]
        elif lane == "answer":
            # General chat speaks AS the loaded pet, with personality.
            system = persona_system_prompt(self.pet)
        else:
            system = LOCAL_AI_LANES[lane]
        # Short-term memory: only general chat carries prior turns. Utility
        # lanes (rewrite/summarize/review/email) and knowledge are one-shot —
        # past chatter must not bleed into a transform or a grounded answer.
        history = self._recent_history() if lane == "answer" else None
        # Persona chat samples livelier; editing/grounded lanes stay faithful.
        options = local_ai_options(lane)
        self._ai_busy = True
        req = {
            "lane": lane, "raw": raw, "cleaned": cleaned, "rec": rec,
            "model": model, "system": system, "source_note": source_note,
            "history": history, "options": options,
            "events": [], "cancel": threading.Event(),
            "msg_index": None, "caption_index": None, "buffer": "",
            "idle_ticks": 0,
            "user_count": sum(1 for k, _ in self.messages if k == "user"),
        }
        self._ai_req = req
        if not self.pet.settings.get("local_ai_intro_shown"):
            self.pet.settings["local_ai_intro_shown"] = True
            self.pet._save_settings()
            self._add("caption",
                      f"✨ New: I answer light asks like this one myself, using "
                      f"{model} fully on this PC. First answer can take a "
                      f"minute while the model warms up. Right-click me → "
                      f"Local AI to turn this off.")
        self._show_typing()

        def worker():
            try:
                # The RAW text goes to the model: typo-fixing and alias
                # expansion must never rewrite content being edited
                # ("ps" inside an email is not "PowerShell").
                text = ollama_chat_stream(
                    model, req["system"], raw,
                    on_chunk=lambda p: req["events"].append(("chunk", p)),
                    cancel=req["cancel"], history=req["history"],
                    options=req["options"])
                req["events"].append(("done", text))
            except Exception as e:  # any failure falls back to prompt flow
                req["events"].append(("error", str(e)))

        threading.Thread(target=worker, daemon=True).start()
        self._poll_local_ai(req)

    def _poll_local_ai(self, req):
        if not self.is_open():
            req["cancel"].set()  # stop the worker and Ollama's generation
            self._ai_busy = False
            return
        got_chunk = False
        while req["events"]:
            kind, payload = req["events"].pop(0)
            req["idle_ticks"] = 0
            if kind == "chunk":
                if req["msg_index"] is None:
                    self._hide_typing()
                    self._add("caption",
                              f"✨ answered locally by {req['model']}"
                              f"{req['source_note']}")
                    req["caption_index"] = len(self.messages) - 1
                    self._add("pet", "")
                    req["msg_index"] = len(self.messages) - 1
                req["buffer"] += payload
                got_chunk = True
            elif kind == "done":
                self._finish_local_ai(req, payload)
                return
            else:  # error
                self._abandon_local_ai(req)
                return
        if got_chunk:
            self.messages[req["msg_index"]] = ("pet", req["buffer"] + " ▌")
            self._render_all()
            self.messages[req["msg_index"]] = ("pet", req["buffer"])
        else:
            req["idle_ticks"] += 1
            limit = (self.AI_STALL_TICKS if req["msg_index"] is not None
                     else self.AI_FIRST_CHUNK_TICKS)
            if req["idle_ticks"] > limit:
                req["cancel"].set()
                self._abandon_local_ai(req)
                return
        self.win.after(120, lambda: self._poll_local_ai(req))

    def _finish_local_ai(self, req, payload):
        self._ai_busy = False
        final = (payload or "").strip() or req["buffer"].strip()
        if req["msg_index"] is None or not final:  # empty answer = failure
            self._abandon_local_ai(req)
            return
        self.messages[req["msg_index"]] = ("pet", final)
        if req["lane"] in ("rewrite", "email", "summarize"):
            # The action row carries its own payload: a later prompt
            # changing self.last must not change what these buttons copy.
            self.messages.append(
                ("actions", (req["raw"], req["cleaned"], req["rec"], final)))
        self._render_all()

    def _abandon_local_ai(self, req):
        """Clean up a failed/cancelled stream without clobbering anything
        the user did since: remove the partial answer, and only fall back
        to prompt-building if the conversation hasn't moved on."""
        self._ai_busy = False
        self._hide_typing()
        self.pet._refresh_local_models()  # self-heal if Ollama went away
        for idx in sorted((i for i in (req["msg_index"], req["caption_index"])
                           if i is not None), reverse=True):
            if idx < len(self.messages):
                del self.messages[idx]
        self._render_all()
        user_count = sum(1 for k, _ in self.messages if k == "user")
        superseded = self.pending is not None or user_count > req["user_count"]
        if superseded:
            self._add("caption", "(local AI couldn't answer the earlier ask)")
            return
        self._add("caption",
                  "Local AI didn't answer — building you a prompt instead.")
        self._standard_request(req["raw"], req["cleaned"], req["rec"])

    # ---- DeckSide live-data lane ----------------------------------------------

    def _deckside_request(self, raw, cleaned, rec):
        """Answer a meet-day question from a running DeckSide. The HTTP call
        blocks (DeckSide may warm a query), so it runs on a worker thread and
        delivers through the same poll/supersession machinery as local AI."""
        self._ai_busy = True
        req = {"raw": raw, "cleaned": cleaned, "rec": rec, "events": [],
               "user_count": sum(1 for k, _ in self.messages if k == "user")}
        self._show_typing()

        def worker():
            answer, reason = deckside_ask(raw)
            req["events"].append(("answer", answer) if answer
                                 else ("miss", reason))

        threading.Thread(target=worker, daemon=True).start()
        self._poll_deckside(req)

    def _poll_deckside(self, req):
        if not self.is_open():
            self._ai_busy = False  # worker's urllib timeout ends it on its own
            return
        if not req["events"]:
            self.win.after(120, lambda: self._poll_deckside(req))
            return
        kind, payload = req["events"].pop(0)
        self._ai_busy = False
        self._hide_typing()
        if kind == "answer":
            self._add("caption", f"🏊 from DeckSide · live ({deckside_base()})")
            self._add("pet", payload)
            # The action row carries its own payload so later prompts can't
            # change what Copy/Save act on (same contract as local AI).
            self.messages.append(
                ("actions", (req["raw"], req["cleaned"], req["rec"], payload)))
            self._render_all()
            return
        # No answer — only fall back to prompt-building if the user hasn't
        # already moved on to another ask.
        superseded = (self.pending is not None
                      or sum(1 for k, _ in self.messages if k == "user")
                      > req["user_count"])
        if superseded:
            return
        self._add("caption",
                  "DeckSide isn't running — building you a prompt instead."
                  if payload == "offline"
                  else "DeckSide didn't have that — building you a prompt instead.")
        self._standard_request(req["raw"], req["cleaned"], req["rec"])

    def _deliver_help(self, bubbles):
        if not self.is_open():
            return
        self._hide_typing()
        for text in bubbles:
            self._add("pet", text)

    def _ask_next_question(self):
        if not self.is_open() or not self.pending:
            return
        self._hide_typing()
        opener = random.choice(("Quick question first —", "Happy to! One thing —",
                                "On it. Before I build this —", "Almost there —"))
        q = self.pending["questions"][self.pending["qi"]]
        hint = "" if self.pending["qi"] else "\n\n(or say “skip” and I'll just build it)"
        self._add("pet", f"{opener} {q}{hint}")

    def _handle_answer(self, raw):
        p = self.pending
        skipped = raw.strip().lower().rstrip(".!") in SKIP_WORDS
        if not skipped:
            p["answers"].append(raw)
        p["qi"] += 1
        if skipped or p["qi"] >= len(p["questions"]):
            self.pending = None
            self._generate(p["raw"], p["answers"])
        else:
            self._show_typing()
            self.win.after(random.randint(400, 800), self._ask_next_question)

    def _generate(self, raw, answers):
        # Answers feed both the task text (for routing) and the context list.
        combined = raw + ". " + " ".join(answers) if answers else raw
        cleaned = clean_text(combined, self.spell)
        rec = recommend(cleaned)
        context = [clean_text(a, self.spell) for a in answers]
        prompt = build_prompt(cleaned, rec, rec["modules"], rec["skills"], context)
        self.last = (raw, cleaned, rec, prompt)
        save_history_entry(raw, cleaned, rec, prompt)
        self._show_typing()
        self.win.after(random.randint(500, 900), lambda: self._deliver_reply(cleaned, rec, prompt))

    def _deliver_reply(self, cleaned, rec, prompt):
        if not self.is_open():
            return
        self._hide_typing()
        template_name = PROMPT_TEMPLATES[rec["template"]]["name"]
        opener = random.choice(("Got it!", "Okay, here's what I make of it:",
                                "Perfect, that helps."))
        self._add("pet", f"{opener} I read that as:\n“{cleaned}”")
        self._add("pet", f"➜ Send it to: {DEST_LABELS[rec['destination']]}\n{rec['reason']}")
        details = f"Template: {template_name}"
        if rec["checklist"]:
            hints = "\n".join(f"• {c}" for c in rec["checklist"][:5])
            details += f"\n\nIt'll work even better if you paste in:\n{hints}"
        self._add("pet", details)
        chips = ([{"label": f"🧩 {AGENT_MODULES[m]['name']}", "kind": "module", "key": m}
                  for m in rec["modules"] if m in AGENT_MODULES]
                 + [{"label": f"🛠 {SKILL_TEMPLATES[s]['name']}", "kind": "skill", "key": s}
                    for s in rec["skills"] if s in SKILL_TEMPLATES])
        if chips:
            self._add("caption", "I baked these in — tap one to read what it adds:")
            self._add("chips", chips)
        self._add("prompt", prompt)

    def _copy_last(self):
        if not self.last:
            return
        self.win.clipboard_clear()
        self.win.clipboard_append(self.last[3])
        self._add("pet", "Copied! Paste it into Codex, Claude Code, ChatGPT, or Claude. ✅")
        self.pet.celebrate()

    def _save_last(self):
        if not self.last:
            return
        raw, cleaned, rec, prompt = self.last
        save_history_entry(raw, cleaned, rec, prompt)
        self._add("pet", "Saved to your local history. 💾")

    def _open_in_editor(self):
        if self.last:
            self.pet.open_editor(prefill=self.last[0])


# ---------------------------------------------------------------------------
# MCP server (--mcp): exposes the prompt-building brain over the Model
# Context Protocol (stdio, JSON-RPC 2.0, newline-delimited) so coding agents
# like Claude Code can use AskPet as a tool. Stateless and read-only:
# nothing here writes to user data. Stdlib only, same as the rest of the app.
# ---------------------------------------------------------------------------

MCP_PROTOCOL_VERSION = "2025-06-18"

MCP_TOOLS = [
    {
        "name": "ask",
        "description": (
            "Send AskPet a message exactly like chatting with the pet. "
            "Question-shaped messages about prompting best practices, context, "
            "handoffs, or AskPet itself get a knowledge-base answer. Task "
            "descriptions get a full recommendation: destination assistant, "
            "template, agent modules, skills, context checklist, clarifying "
            "questions, and a copy-ready prompt. Typos and shorthand are fine."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "message": {
                    "type": "string",
                    "description": "The chat message: a task to build a prompt for, or a question about prompting best practices.",
                },
            },
            "required": ["message"],
        },
    },
    {
        "name": "build_prompt",
        "description": (
            "Build the final copy-ready prompt for a task. Pass the answers "
            "to any clarifying questions from a previous ask call in "
            "'answers' — they sharpen routing and are listed as provided "
            "context in the prompt."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "task": {
                    "type": "string",
                    "description": "The task to build a prompt for.",
                },
                "answers": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Answers to clarifying questions (optional).",
                },
            },
            "required": ["task"],
        },
    },
    {
        "name": "list_library",
        "description": (
            "List AskPet's content library: prompt templates, agent "
            "modules (expert operating instructions), and skills "
            "(step-by-step workflows). Returns keys, names, and topics; use "
            "get_item for full bodies."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "kind": {
                    "type": "string",
                    "enum": ["template", "module", "skill"],
                    "description": "Limit to one kind (optional; default all).",
                },
            },
        },
    },
    {
        "name": "search_library",
        "description": (
            "Keyword-search templates, agent modules, and skills by name, "
            "key, topic, and body text. Returns the best matches with keys "
            "for get_item."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search words, e.g. 'intune compliance' or 'handoff'.",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_item",
        "description": "Fetch the full body of one template, agent module, or skill by key.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "kind": {
                    "type": "string",
                    "enum": ["template", "module", "skill"],
                },
                "key": {
                    "type": "string",
                    "description": "The item key, e.g. 'codex_execution' or 'plan_first'.",
                },
            },
            "required": ["kind", "key"],
        },
    },
]

_MCP_LIBRARIES = {
    "template": ("PROMPT_TEMPLATES", lambda: PROMPT_TEMPLATES),
    "module": ("AGENT_MODULES", lambda: AGENT_MODULES),
    "skill": ("SKILL_TEMPLATES", lambda: SKILL_TEMPLATES),
}


def _mcp_recommendation(cleaned: str, rec: dict, prompt: str) -> dict:
    return {
        "interpreted_as": cleaned,
        "destination": DEST_LABELS[rec["destination"]],
        "destination_reason": rec["reason"],
        "template": rec["template"],
        "template_name": PROMPT_TEMPLATES[rec["template"]]["name"],
        "modules": {k: AGENT_MODULES[k]["name"] for k in rec["modules"] if k in AGENT_MODULES},
        "skills": {k: SKILL_TEMPLATES[k]["name"] for k in rec["skills"] if k in SKILL_TEMPLATES},
        "context_checklist": rec["checklist"][:5],
        "prompt": prompt,
    }


def _mcp_ask(spell: SpellHelper, message: str) -> dict:
    help_answer = answer_help_question(message)
    if help_answer:
        return {"type": "help_answer", "answer": "\n\n".join(help_answer)}
    cleaned = clean_text(message, spell)
    rec = recommend(cleaned)
    questions = clarifying_questions(cleaned, rec)
    prompt = build_prompt(cleaned, rec, rec["modules"], rec["skills"], [])
    result = {"type": "prompt", **_mcp_recommendation(cleaned, rec, prompt)}
    if questions:
        result["clarifying_questions"] = questions
        result["hint"] = ("The prompt below is usable as-is, but answering "
                          "the clarifying questions and calling build_prompt "
                          "with the answers gives a sharper prompt.")
    return result


def _mcp_build_prompt(spell: SpellHelper, task: str, answers: list) -> dict:
    answers = [a for a in (answers or []) if str(a).strip()]
    combined = task + ". " + " ".join(answers) if answers else task
    cleaned = clean_text(combined, spell)
    rec = recommend(cleaned)
    context = [clean_text(a, spell) for a in answers]
    prompt = build_prompt(cleaned, rec, rec["modules"], rec["skills"], context)
    return {"type": "prompt", **_mcp_recommendation(cleaned, rec, prompt)}


def _mcp_list_library(kind: str = None) -> dict:
    kinds = [kind] if kind else list(_MCP_LIBRARIES)
    out = {}
    for k in kinds:
        if k not in _MCP_LIBRARIES:
            raise ValueError(f"unknown kind {k!r}; expected one of {list(_MCP_LIBRARIES)}")
        lib = _MCP_LIBRARIES[k][1]()
        out[k + "s"] = [{"key": key, "name": item["name"], "topics": item["topics"]}
                        for key, item in lib.items()]
    return out


def _mcp_search_library(query: str) -> dict:
    words = [w for w in re.findall(r"[a-z0-9]+", query.lower()) if len(w) > 1]
    if not words:
        return {"results": []}
    results = []
    for kind, (_, getter) in _MCP_LIBRARIES.items():
        for key, item in getter().items():
            score = 0
            name = item["name"].lower()
            topics = " ".join(item["topics"]).lower()
            body = item["body"].lower()
            for w in words:
                if w in key or w in name:
                    score += 3
                if w in topics:
                    score += 2
                if w in body:
                    score += 1
            if score > 0:
                results.append({"kind": kind, "key": key, "name": item["name"],
                                "topics": item["topics"], "score": score})
    results.sort(key=lambda r: -r["score"])
    return {"results": results[:10]}


def _mcp_get_item(kind: str, key: str) -> dict:
    if kind not in _MCP_LIBRARIES:
        raise ValueError(f"unknown kind {kind!r}; expected one of {list(_MCP_LIBRARIES)}")
    lib = _MCP_LIBRARIES[kind][1]()
    if key not in lib:
        close = difflib.get_close_matches(key, lib.keys(), n=3)
        hint = f" Close matches: {', '.join(close)}." if close else ""
        raise ValueError(f"no {kind} named {key!r}.{hint}")
    item = lib[key]
    out = {"kind": kind, "key": key, "name": item["name"],
           "topics": item["topics"], "body": item["body"]}
    if item.get("steps"):
        out["steps"] = item["steps"]
    if item.get("destination"):
        out["destination"] = item["destination"]
    return out


def run_mcp_server():
    """Serve MCP over stdio until stdin closes."""
    sys.stdin.reconfigure(encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8", newline="\n")
    spell = SpellHelper()

    handlers = {
        "ask": lambda a: _mcp_ask(spell, a["message"]),
        "build_prompt": lambda a: _mcp_build_prompt(spell, a["task"], a.get("answers")),
        "list_library": lambda a: _mcp_list_library(a.get("kind")),
        "search_library": lambda a: _mcp_search_library(a["query"]),
        "get_item": lambda a: _mcp_get_item(a["kind"], a["key"]),
    }

    def send(payload: dict):
        sys.stdout.write(json.dumps(payload, ensure_ascii=True) + "\n")
        sys.stdout.flush()

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            continue
        method = msg.get("method", "")
        msg_id = msg.get("id")
        is_notification = msg_id is None

        if method == "initialize":
            client_version = (msg.get("params") or {}).get("protocolVersion")
            send({"jsonrpc": "2.0", "id": msg_id, "result": {
                "protocolVersion": client_version if isinstance(client_version, str)
                                   else MCP_PROTOCOL_VERSION,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": APP_NAME, "version": APP_VERSION},
                "instructions": (
                    "AskPet builds copy-ready, best-practice prompts for "
                    "IT tasks and answers prompting how-to questions. Start "
                    "with the ask tool; everything runs locally."
                ),
            }})
        elif method == "ping":
            send({"jsonrpc": "2.0", "id": msg_id, "result": {}})
        elif method == "tools/list":
            send({"jsonrpc": "2.0", "id": msg_id, "result": {"tools": MCP_TOOLS}})
        elif method == "tools/call":
            params = msg.get("params") or {}
            name = params.get("name")
            args = params.get("arguments") or {}
            try:
                if name not in handlers:
                    raise ValueError(f"unknown tool {name!r}")
                result = handlers[name](args)
                content = {"content": [{"type": "text",
                                        "text": json.dumps(result, indent=2,
                                                           ensure_ascii=False)}]}
            except Exception as exc:  # tool errors go in-band per MCP spec
                content = {"content": [{"type": "text", "text": f"Error: {exc}"}],
                           "isError": True}
            send({"jsonrpc": "2.0", "id": msg_id, "result": content})
        elif is_notification or method.startswith("notifications/"):
            continue
        else:
            send({"jsonrpc": "2.0", "id": msg_id,
                  "error": {"code": -32601, "message": f"method not found: {method}"}})


def main():
    migrate_legacy_data()  # PromptMate -> AskPet user data, one-time
    if "--mcp" in sys.argv:
        run_mcp_server()
        return
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
        app = AskPetApp(root)
        root.protocol("WM_DELETE_WINDOW", app.on_close)
    else:
        PetOverlay(root)
    root.mainloop()


if __name__ == "__main__":
    main()
