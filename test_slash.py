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
print("parse_slash OK")

# --- registry ----------------------------------------------------------------
VALID_ACTIONS = {"rewrite", "email", "summarize", "answer", "knowledge",
                 "prompt", "help"}
names = [n for n, _, _ in pm.SLASH_COMMANDS]
assert all(n.startswith("/") for n in names), names
assert len(names) == len(set(names)), "duplicate command names"
assert set(pm.SLASH_BY_NAME) == {n[1:] for n in names}
for name, desc, action in pm.SLASH_COMMANDS:
    assert action in VALID_ACTIONS, (name, action)
    assert desc and isinstance(desc, str)
# the writing/answer lanes a command forces must actually exist
for _, _, action in pm.SLASH_COMMANDS:
    if action in ("rewrite", "email", "summarize", "answer"):
        assert action in pm.LOCAL_AI_LANES, action
# the core commands are present
assert {"rewrite", "email", "summarize", "ask", "fpv", "prompt", "help"} <= set(pm.SLASH_BY_NAME)
print("registry OK")

# --- dispatch mapping (what _run_slash will look up) -------------------------
assert pm.SLASH_BY_NAME["rewrite"][1] == "rewrite"
assert pm.SLASH_BY_NAME["fpv"][1] == "knowledge"
assert pm.SLASH_BY_NAME["prompt"][1] == "prompt"
assert pm.SLASH_BY_NAME["help"][1] == "help"
print("dispatch mapping OK")

print("SLASH TEST PASSED")
