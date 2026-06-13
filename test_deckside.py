#!/usr/bin/env python3
"""DeckSide live-data integration tests: routing (which messages are meet
questions vs DeckSide dev tasks vs unrelated asks), client config, and a
live round-trip that is skipped when DeckSide isn't running so the build
gate passes headless."""

import os
import sys

import askpet as pm

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# --- routing: meet-data questions go to the DeckSide lane --------------------
DATA = [
    "when is the next meet?",
    "how many swimmers are on the team?",
    "who is swimming the girls 50 free?",
    "what's the lineup for the next meet?",
    "is mabel scratched from the relay?",
    "show me the meet schedule",
    "who's on the A relay?",
    "what heat sheet are we on?",
    "list the swimmers in deckside",
    "how did san leandro score at champs?",
    "is everyone checked in for the dual meet?",
    "what meets are on the schedule this season?",
    "show me the season calendar of meets",
]
for q in DATA:
    assert pm.deckside_data_lane(q), f"should route to DeckSide: {q!r}"

# --- routing: DeckSide *dev* tasks keep building prompts ----------------------
DEV = [
    "build a check-in tab for deckside",
    "fix the deckside pdf parser",
    "implement a relay lineup feature in deckside",
    "refactor the deckside ipc boundary",
    "write a commit message for the deckside lineup change",
]
for q in DEV:
    assert not pm.deckside_data_lane(q), f"dev task must NOT route to data: {q!r}"

# --- routing: unrelated asks are untouched ------------------------------------
OTHER = [
    "how do i charge a 1s battery",          # FPV
    "whats the best 1s battery",             # FPV
    "reset a password in entra",             # IT
    "write a powershell script to clean temp files",  # IT
    "summarize this meeting",                # "meeting" must not match "meet"
    "draft an email to the landlord",        # email
    "what does dns actually do?",            # general
    "schedule a task to clean temp files?",  # "scheduled"/"schedule" IT task
    "can you schedule a meeting with the team?",  # schedule + meeting, not meet
]
for q in OTHER:
    assert not pm.deckside_data_lane(q), f"unrelated must NOT route to data: {q!r}"

# a statement, even with swim words, isn't a question -> not the data lane
assert not pm.deckside_data_lane("the relay swam great today")
print("routing OK")

# --- client config ------------------------------------------------------------
saved = os.environ.pop("DECKSIDE_AGENT_PORT", None)
try:
    assert pm.deckside_base() == "http://127.0.0.1:41973", pm.deckside_base()
    os.environ["DECKSIDE_AGENT_PORT"] = "5005"
    assert pm.deckside_base() == "http://127.0.0.1:5005", pm.deckside_base()
finally:
    os.environ.pop("DECKSIDE_AGENT_PORT", None)
    if saved is not None:
        os.environ["DECKSIDE_AGENT_PORT"] = saved
print("client config OK")

# --- live round-trip (skipped when DeckSide isn't running) --------------------
version = pm.deckside_health()
if version:
    answer, reason = pm.deckside_ask("when is the next meet?")
    assert answer and reason is None, (answer, reason)
    assert "meet" in answer.lower(), answer
    # An unanswerable question degrades to a reason, never a crash.
    a2, r2 = pm.deckside_ask("qwzx not a real meet question zzz")
    assert a2 is None or isinstance(a2, str)
    print(f"live round-trip OK (DeckSide {version}): {answer!r}")
else:
    print("live round-trip SKIPPED (DeckSide agent server not reachable)")

print("DECKSIDE TEST PASSED")
