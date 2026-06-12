#!/usr/bin/env python3
"""Knowledge pack tests: loading, retrieval, lane routing, grounded
prompt building. Uses a synthetic pack in a temp dir — fully offline,
never touches real user data."""

import sys
import tempfile
from pathlib import Path

import askpet as pm

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

tmp = Path(tempfile.mkdtemp())
pm.KNOWLEDGE_DIR = tmp
pm._KNOWLEDGE_PACKS = None  # force reload from the temp dir

pack_dir = tmp / "fpv-test"
pack_dir.mkdir(parents=True)
pm.save_json(pack_dir / "pack.json", {
    "id": "fpv-test", "name": "FPV test pack",
    "credit": "TestChannel (youtube.com/@test)",
    "keywords": ["fpv", "whoop", "air65", "meteor75", "betaflight",
                 "vtx", "elrs", "drone prop"],
})
pm.save_json(pack_dir / "chunks.json", [
    {"v": "v1", "t": "Air65 motor guide",
     "x": "for the air65 i run the 0802 19500kv motors with the gemfan 31mm "
          "props they give the best punch for 1s freestyle and the amps stay "
          "reasonable so your battery sag is manageable on hv lipos"},
    {"v": "v2", "t": "Meteor75 setup",
     "x": "the meteor75 pro comes with the elrs receiver built into the aio "
          "flight controller bind it by holding the boot button then power "
          "cycle three times betaflight shows the rx on uart two"},
    {"v": "v3", "t": "VTX antenna repair",
     "x": "when the vtx antenna rips off a whoop you can solder a new ufl "
          "pigtail use low heat and flux the pad first or you lift the pad "
          "and then the repair gets much harder"},
])

# --- loading -----------------------------------------------------------------
packs = pm.knowledge_packs()
assert len(packs) == 1 and packs[0]["id"] == "fpv-test", packs
print("pack loading OK")

# --- pack matching ------------------------------------------------------------
assert pm.knowledge_pack_for("what motors for my air65?") is not None
assert pm.knowledge_pack_for("how do i bind elrs on the meteor75") is not None
assert pm.knowledge_pack_for("reset a password in entra") is None
assert pm.knowledge_pack_for("summarize this meeting") is None
print("pack matching OK")

# --- retrieval ranks the right chunk first ------------------------------------
top = pm.knowledge_retrieve(packs[0], "what motors and props for the air65?")
assert top and top[0]["t"] == "Air65 motor guide", [c["t"] for c in top]
top = pm.knowledge_retrieve(packs[0], "how to bind elrs on meteor75")
assert top and top[0]["t"] == "Meteor75 setup", [c["t"] for c in top]
top = pm.knowledge_retrieve(packs[0], "vtx antenna ripped off how to fix")
assert top and top[0]["t"] == "VTX antenna repair", [c["t"] for c in top]
assert pm.knowledge_retrieve(packs[0], "the of and") == []
print("retrieval ranking OK")

# --- grounded system prompt ----------------------------------------------------
sysp = pm.knowledge_system_prompt(packs[0], "what props for the air65?")
assert sysp and "TestChannel" in sysp and "SOURCE EXCERPTS" in sysp
assert "31mm" in sysp, "expected the relevant chunk in the prompt"
print("grounded prompt OK")

# --- lane routing ---------------------------------------------------------------
spell = pm.SpellHelper()


def lane_for(msg):
    return pm.local_ai_lane(msg, pm.recommend(pm.clean_text(msg, spell)))


# knowledge questions go local even with execution-flavored words
assert lane_for("how do i fix a broken motor on my air65?") == "knowledge"
assert lane_for("best props for the meteor75") == "knowledge"
assert lane_for("whats a good vtx for a 65mm whoop?") == "knowledge"
assert lane_for("betaflight rates for smooth freestyle?") == "knowledge"
# non-pack questions keep their lanes
assert lane_for("what does dns actually do?") == "answer"
assert lane_for("write a powershell script to clean temp files") is None
# long task-shaped FPV messages still build prompts (not question, >14 words)
assert lane_for("plan a complete build guide for a 75mm whoop including all "
                "parts list prices and assembly steps for beginners") is None
print("lane routing OK")

print("KNOWLEDGE TEST PASSED")
