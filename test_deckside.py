#!/usr/bin/env python3
"""DeckSide live-data integration tests: routing (which messages are meet
questions vs DeckSide dev tasks vs unrelated asks), client config, and a
live round-trip that is skipped when DeckSide isn't running so the build
gate passes headless."""

import json
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
    # event / heat / stroke questions (yes-no + imperative forms too)
    "what events is mabel in?",
    "who is in event 14?",
    "check on the 50 free",
    "is mabel in any events?",
    "what heat is the 100 free?",
    "is grace swimming today?",
    "is the 100 back done?",
    "how did event 12 go?",
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
    "check the event log",                   # IT: "event log" collision guard
    "what events are in the audit log?",     # IT: "audit log" collision guard
    "is the smtp relay working?",            # IT: "smtp relay" collision guard
    "create a calendar event",               # IT: "calendar event" collision guard
    "best props for freestyle?",             # FPV: bare "freestyle" must not route
    "tiny whoop or freestyle?",              # FPV
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

# --- roster name matching --------------------------------------------------
assert pm.roster_flip_name("Smith, Jane") == "Jane Smith"
assert pm.roster_flip_name("Cher") == "Cher"
assert pm.roster_flip_name("") == ""

# typing context: (current word being typed, completed word before it)
assert pm.roster_typing_context("scratch ma") == ("ma", "scratch")
assert pm.roster_typing_context("scratch Mabel fr") == ("fr", "Mabel")
assert pm.roster_typing_context("Mabel") == ("Mabel", "")        # sentence start
assert pm.roster_typing_context("replace Mabel with joa") == ("joa", "with")
assert pm.roster_typing_context("the relay ") == ("", "relay")   # no word being typed

NAMES = ["Jane Smith", "Ethan Rosal", "Ethan Kang", "Cyla Doe"]
# EXACT-prefix matching on the single current word (no fuzzy, no two-word).
assert pm.roster_prefix_matches(NAMES, "smit")[0] == "Jane Smith"  # last-name prefix
assert pm.roster_prefix_matches(NAMES, "jane")[0] == "Jane Smith"  # first-name prefix
assert pm.roster_prefix_matches(NAMES, "smiht") == []             # NO fuzzy -> quiet
assert pm.roster_prefix_matches(NAMES, "z") == []                 # < 2 chars
assert set(pm.roster_prefix_matches(NAMES, "ethan")) == {"Ethan Rosal", "Ethan Kang"}

# the "name slot" gate — the core of the over-triggering fix
known = {"is", "the", "when", "free", "relay", "do", "from", "mara"}.__contains__
slot = lambda cur, prev: pm.roster_in_name_slot(cur, prev, known)
assert slot("eth", "scratch") is True       # after an action cue
assert slot("mab", "is") is True            # after a state cue
assert slot("joa", "with") is True          # after a connector cue
assert slot("eth", "") is True              # sentence start
assert slot("fr", "Mabel") is False         # word right AFTER a name -> no predict
assert slot("relay", "the") is False        # prev is a cue but "relay" is a word
assert slot("meet", "the") is False         # "the" isn't a cue, "meet"/prose
assert slot("is", "scratch") is False       # current word is an ordinary word
assert slot("a", "scratch") is False        # too short

# accept replaces only the current word (accept inserts the full "First Last")
assert pm.roster_replace_len("scratch eth") == 3        # just "eth"
assert pm.roster_replace_len("replace Mabel with joa") == 3  # just "joa"
print("roster matching OK")

# --- deckside_roster fetch / cache / offline (mocked HTTP) --------------------
import urllib.request as _ur


class _Resp:
    def __init__(self, payload):
        self._b = json.dumps(payload).encode()

    def read(self):
        return self._b

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


_calls = {"n": 0}


def _fake_urlopen(req, timeout=0):
    _calls["n"] += 1
    return _Resp({"ok": True, "data": {"roster": [
        {"fullName": "Smith, Jane"},
        {"fullName": "Doe, Cyla"},
        {"fullName": "Doe, Cyla"},   # duplicate -> deduped
        {"fullName": ""},            # blank -> dropped
    ]}})


_saved_health, _saved_urlopen = pm.deckside_health, _ur.urlopen
try:
    pm._ROSTER_CACHE.update(names=[], fetched=0.0, ver=None)
    pm.deckside_health = lambda timeout=2: "1.9.30"
    _ur.urlopen = _fake_urlopen
    names = pm.deckside_roster()
    assert names == ["Cyla Doe", "Jane Smith"], names   # flipped, sorted, deduped
    n_before = _calls["n"]
    pm.deckside_roster()                                  # same version, within TTL
    assert _calls["n"] == n_before, "cache should avoid a second fetch"
    pm.deckside_health = lambda timeout=2: None          # DeckSide goes offline
    pm._ROSTER_CACHE.update(names=[], fetched=0.0, ver=None)
    assert pm.deckside_roster() == []                     # graceful empty, no throw
finally:
    pm.deckside_health, _ur.urlopen = _saved_health, _saved_urlopen
    pm._ROSTER_CACHE.update(names=[], fetched=0.0, ver=None)
print("deckside_roster OK")

print("DECKSIDE TEST PASSED")
