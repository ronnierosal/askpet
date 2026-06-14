#!/usr/bin/env python3
"""Slash-command parsing + registry tests (pure logic, no GUI)."""

import sys

import askpet as pm

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# --- parse_slash ------------------------------------------------------------
assert pm.parse_slash("/rewrite make this shorter") == ("rewrite", "make this shorter")
assert pm.parse_slash("/help") == ("help", "")
assert pm.parse_slash("/HELP") == ("help", "")           # command case-insensitive
assert pm.parse_slash("  /ask what is dns?") == ("ask", "what is dns?")  # leading ws
assert pm.parse_slash("/email\nthe body") == ("email", "the body")      # arg may span
assert pm.parse_slash("/xyz foo bar") == ("xyz", "foo bar")  # unknown name still parses
assert pm.parse_slash("hello world") is None             # no leading slash
assert pm.parse_slash("rewrite this /thing") is None     # slash not at start
assert pm.parse_slash("") is None
assert pm.parse_slash("/") is None                       # bare slash, no command word
# library-template commands have underscores/digits in the name
assert pm.parse_slash("/incident_rca email is down") == ("incident_rca", "email is down")
assert pm.parse_slash("/codex_execution build a thing") == ("codex_execution", "build a thing")
# hyphenated command names parse (e.g. /fix-prompt)
assert pm.parse_slash("/fix-prompt make a deploy prompt") == ("fix-prompt", "make a deploy prompt")
print("parse_slash OK")

# --- registry ----------------------------------------------------------------
VALID_ACTIONS = {"rewrite", "email", "summarize", "review", "answer",
                 "knowledge", "prompt", "help"}
names = [n for n, _, _ in pm.SLASH_COMMANDS]
assert all(n.startswith("/") for n in names), names
assert len(names) == len(set(names)), "duplicate command names"
# every command name is in the lookup; plus the back-compat "prompt" alias
assert {n[1:] for n in names} <= set(pm.SLASH_BY_NAME)
assert "prompt" in pm.SLASH_BY_NAME  # alias for /fix-prompt
for name, desc, action in pm.SLASH_COMMANDS:
    assert action in VALID_ACTIONS, (name, action)
    assert desc and isinstance(desc, str)
# the writing/answer/review lanes a command forces must actually exist
for _, _, action in pm.SLASH_COMMANDS:
    if action in ("rewrite", "email", "summarize", "review", "answer"):
        assert action in pm.LOCAL_AI_LANES, action
# the core commands are present (general-chat-first: /fix-prompt builds prompts)
assert {"rewrite", "summarize", "review", "email", "ask",
        "fix-prompt", "help"} <= set(pm.SLASH_BY_NAME)
# /fpv was removed — FPV questions are auto-detected, not a slash command
assert "fpv" not in pm.SLASH_BY_NAME
print("registry OK")

# --- dispatch mapping (what _run_slash will look up) -------------------------
assert pm.SLASH_BY_NAME["rewrite"][1] == "rewrite"
assert pm.SLASH_BY_NAME["review"][1] == "review"
assert pm.SLASH_BY_NAME["fix-prompt"][1] == "prompt"   # /fix-prompt builds prompts
assert pm.SLASH_BY_NAME["prompt"][1] == "prompt"       # back-compat alias
assert pm.SLASH_BY_NAME["help"][1] == "help"
print("dispatch mapping OK")

# --- library templates surface as commands ----------------------------------
# A template name is NOT a core command but IS a valid PROMPT_TEMPLATES key,
# which is how _run_slash routes it to a forced-template build.
cmd, _ = pm.parse_slash("/codex_execution build a thing")
assert cmd not in pm.SLASH_BY_NAME and cmd in pm.PROMPT_TEMPLATES
assert pm.PROMPT_TEMPLATES["codex_execution"].get("destination")  # has a destination
assert len(pm.PROMPT_TEMPLATES) >= 20, len(pm.PROMPT_TEMPLATES)
print("library templates OK")

print("SLASH TEST PASSED")
