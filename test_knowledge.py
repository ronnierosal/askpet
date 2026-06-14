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

# A second pack with battery/charging content — packs must STACK, not
# shadow each other (first-match-only retrieval hid every later pack).
faq_dir = tmp / "faq-test"
faq_dir.mkdir(parents=True)
pm.save_json(faq_dir / "pack.json", {
    "id": "faq-test", "name": "FAQ test pack",
    "credit": "FAQ sources (example.com)",
    "keywords": ["1s battery", "lipo", "mah", "tiny whoop"],
})
pm.save_json(faq_dir / "chunks.json", [
    {"v": "u1", "t": "FAQ: charging 1s batteries",
     "x": "Q: how do i charge a 1s battery? A: use a dedicated 1s charger "
          "and charge lipo packs to 4.20v or lihv to 4.35v. a 300mah or "
          "450 mah whoop battery charges at 1c. never leave charging "
          "batteries unattended."},
    {"v": "u2", "t": "FAQ: best 1s battery",
     "x": "Q: whats the best 1s battery for a tiny whoop? A: popular solid "
          "choices are the bt2.0 450mah lihv and gnb 300mah for 65mm "
          "whoops. higher c rating sags less on punchouts."},
])

# --- loading -----------------------------------------------------------------
packs = pm.knowledge_packs()
assert len(packs) == 2, packs
by_id = {p["id"]: p for p in packs}
fpv, faq = by_id["fpv-test"], by_id["faq-test"]
print("pack loading OK")

# --- pack matching ------------------------------------------------------------
assert pm.knowledge_pack_for("what motors for my air65?") is not None
assert pm.knowledge_pack_for("how do i bind elrs on the meteor75") is not None
assert pm.knowledge_pack_for("reset a password in entra") is None
assert pm.knowledge_pack_for("summarize this meeting") is None
# unit-split: "500mah" must reach the "mah" keyword despite no word break
assert pm.knowledge_pack_for("i have a 500mah battery, how do i charge") is faq
# packs stack: craft term hits one pack, battery term the other
both = pm.knowledge_packs_for("best 1s battery for my air65")
assert {p["id"] for p in both} == {"fpv-test", "faq-test"}, both
print("pack matching OK")

# --- retrieval ranks the right chunk first ------------------------------------
top = pm.knowledge_retrieve(fpv, "what motors and props for the air65?")
assert top and top[0]["t"] == "Air65 motor guide", [c["t"] for c in top]
top = pm.knowledge_retrieve(fpv, "how to bind elrs on meteor75")
assert top and top[0]["t"] == "Meteor75 setup", [c["t"] for c in top]
top = pm.knowledge_retrieve(fpv, "vtx antenna ripped off how to fix")
assert top and top[0]["t"] == "VTX antenna repair", [c["t"] for c in top]
assert pm.knowledge_retrieve(fpv, "the of and") == []
# unit-split works query-side too: "500mah" finds chunks that say "450 mah"
top = pm.knowledge_retrieve(faq, "i have a 500mah battery, how do i charge")
assert top and top[0]["t"] == "FAQ: charging 1s batteries", \
    [c["t"] for c in top]
print("retrieval ranking OK")

# --- grounded system prompt ----------------------------------------------------
sysp = pm.knowledge_system_prompt(fpv, "what props for the air65?")
assert sysp and "TestChannel" in sysp and "SOURCE EXCERPTS" in sysp
assert "31mm" in sysp, "expected the relevant chunk in the prompt"
# multi-pack: chunks and credits merge across every matching pack
sysp = pm.knowledge_system_prompt(both, "best 1s battery for my air65")
assert sysp and "TestChannel" in sysp and "FAQ sources" in sysp, sysp
assert "bt2.0" in sysp, "expected the FAQ battery chunk in the prompt"
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
# the screenshot trio: newbie battery questions must answer locally
assert lane_for("how do i charge a 1s battery") == "knowledge"
assert lane_for("whats the best 1s battery") == "knowledge"
assert lane_for("i have a 500mah battery, how do I charge") == "knowledge"
# statement-shaped question, >14 words: embedded question must carry it
assert lane_for("i just got a tiny whoop with a 450mah lipo and a usb "
                "charger, how do i charge it safely") == "knowledge"
# IT battery asks must NOT be stolen by the hobby pack
assert lane_for("my laptop battery dies in an hour, fix it") != "knowledge"
assert lane_for("why does my laptop battery drain so fast?") != "knowledge"
# non-pack questions keep their lanes
assert lane_for("what does dns actually do?") == "answer"
# execution / long task-shaped messages are no longer auto-routed to the
# prompt builder — general chat ("answer") is the default now (use /fix-prompt
# to build a prompt). Knowledge-pack matches above still win.
assert lane_for("write a powershell script to clean temp files") == "answer"
assert lane_for("plan a complete build guide for a 75mm whoop including all "
                "parts list prices and assembly steps for beginners") == "answer"
print("lane routing OK")

print("KNOWLEDGE TEST PASSED")
