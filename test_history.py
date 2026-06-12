#!/usr/bin/env python3
"""History retention test. Redirects HISTORY_FILE to a temp file so the
real user history is never touched. Offline."""

import json
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import promptmate as pm

tmp = Path(tempfile.mkdtemp()) / "prompt-history.json"
pm.HISTORY_FILE = tmp  # all history helpers read the module global


def entry(hours_ago, prompt):
    ts = (datetime.now() - timedelta(hours=hours_ago)).isoformat(timespec="seconds")
    return {"timestamp": ts, "raw_input": "x", "cleaned_input": "x",
            "destination": "Codex", "template": "codex_execution",
            "prompt": prompt}


# default 72h: keep 1h and 71h, drop 73h and 200h, drop unreadable timestamp
pm.save_json(tmp, [entry(200, "old"), entry(73, "older"), entry(71, "recent"),
                   entry(1, "new"), {"prompt": "no-ts"}])
kept = pm.prune_history(72)
assert kept == 2, kept
prompts = [e["prompt"] for e in json.loads(tmp.read_text(encoding="utf-8"))]
assert prompts == ["recent", "new"], prompts
print("prune 72h OK ->", prompts)

# 24h window drops the 71h entry
assert pm.prune_history(24) == 1
print("prune 24h OK")

# 168h window keeps everything younger than a week
pm.save_json(tmp, [entry(150, "six-days"), entry(1, "new")])
assert pm.prune_history(168) == 2
print("prune 168h OK")

# auto-save dedupes the same prompt saved twice in a row
pm.save_json(tmp, [])
rec = {"destination": "Codex", "template": "codex_execution"}
pm.save_history_entry("a", "a", rec, "same-prompt")
pm.save_history_entry("a", "a", rec, "same-prompt")
assert len(json.loads(tmp.read_text(encoding="utf-8"))) == 1
print("dedupe OK")

# manual clear
pm.clear_history()
assert json.loads(tmp.read_text(encoding="utf-8")) == []
print("clear OK")

# retention setting validation: bad values fall back to 72
assert pm.history_retention_hours({"history_retention_hours": 24}) == 24
assert pm.history_retention_hours({"history_retention_hours": 999}) == 72
assert pm.history_retention_hours({}) == 72
print("retention setting OK")

print("HISTORY TEST PASSED")
