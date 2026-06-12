#!/usr/bin/env python3
"""FPV battery: generate 1,000+ micro-drone questions, verify they route
to the knowledge lane, that retrieval finds source chunks, and (unless
--route-only) push them through the local model with grounding checks.
Results -> fpv_battery_results.json. Run after building the fpv pack.
"""

import json
import re
import sys
import time
from collections import Counter

import askpet as pm

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
spell = pm.SpellHelper()

CRAFTS = ["air65", "air65 ii", "meteor75", "meteor75 pro", "mobula6",
          "mobula7", "mobula7 2s", "65mm whoop", "75mm whoop", "tiny whoop"]
COMPONENTS = ["motors", "props", "battery", "vtx", "camera",
              "flight controller", "receiver", "antenna", "frame", "canopy"]
SYMPTOMS = ["wobble in turns", "sag on punchouts", "drift when hovering",
            "lose video behind trees", "not arm in betaflight",
            "feel washed out mid throttle", "drop signal across the field",
            "yaw twitch on rolls", "overheat after a pack",
            "vibrate at full throttle"]

COMP_TEMPLATES = [
    "what {comp} should i run on the {craft}?",
    "best {comp} for the {craft}",
    "is it worth upgrading the {comp} on a {craft}?",
    "how do i choose {comp} for a {craft}?",
    "{comp} recommendations for the {craft}?",
    "are the stock {comp} okay on the {craft}?",
]
SYMPTOM_TEMPLATES = [
    "why does my {craft} {symptom}?",
    "how do i fix it when my {craft} starts to {symptom}?",
]
CRAFT_TEMPLATES = [
    "how do i bind the {craft}?",
    "good betaflight rates for the {craft}?",
    "whats a good first flight checklist for the {craft}?",
    "how long do batteries last on the {craft}?",
    "is the {craft} good for beginners?",
    "can the {craft} fly outside in wind?",
    "what spare parts should i stock for the {craft}?",
    "how do i make the {craft} faster?",
]
VERSUS = [
    "should i get the {a} or the {b}?",
    "{a} vs {b} for indoor flying?",
]
GENERAL = [
    "whats the difference between analog and digital fpv?",
    "is the dji o4 lite worth it on a 65mm whoop?",
    "elrs or crsf, whats the difference?",
    "how do i set up a failsafe on a whoop?",
    "what do motor kv numbers actually mean?",
    "1s or 2s for indoor whoop flying?",
    "how do i stop my hv lipos from puffing?",
    "whats turtle mode and how do i enable it?",
    "which fpv goggles are best for tiny whoops?",
    "how do i practice freestyle in a sim?",
    "what rates do most micro pilots fly?",
    "how do i solder a new vtx antenna on a whoop?",
    "why is my whoop osd not showing?",
    "whats prop wash and how do i tune it out?",
    "do i need a smoke stopper for a whoop build?",
    "how often should i replace props on a 65mm?",
    "whats the deal with 0802 vs 1102 motors?",
    "how do i update betaflight without breaking my setup?",
    "whats a good charge rate for 1s hv lipos?",
    "how do i waterproof a micro drone?",
    "whats the difference between a whoop and a toothpick?",
    "how do i film smooth cinematic lines on a whoop?",
    "why do my motors get hot on 2s?",
    "can i fly fpv in my backyard legally?",
    "how do i stop video static when i punch out?",
    "whats expresslrs telemetry good for?",
    "what camera angle should i run indoors?",
    "how do i carry lipos safely when traveling?",
    "whats the best simulator for tiny whoop practice?",
    "how do i get longer flight times on a 75mm?",
    "do prop guards change how a whoop flies?",
    "how do i fix a bent motor shaft?",
    "what tools do i need for whoop repairs?",
    "how do i set up betaflight osd warnings?",
    "whats a good ladder to learn freestyle tricks?",
    "how do i tune pids on a brushless whoop?",
    "when should i retire a lipo?",
    "whats the right way to break in new motors?",
]
PHRASINGS = ["{q}", "hey, {q}", "{q} thanks", "quick fpv question: {q}"]


def build_battery():
    qs = []
    for craft in CRAFTS:
        for comp in COMPONENTS:
            for t in COMP_TEMPLATES:
                qs.append(t.format(comp=comp, craft=craft))
    for craft in CRAFTS:
        for sym in SYMPTOMS:
            for t in SYMPTOM_TEMPLATES:
                qs.append(t.format(craft=craft, symptom=sym))
    for craft in CRAFTS:
        for t in CRAFT_TEMPLATES:
            qs.append(t.format(craft=craft))
    for i in range(len(CRAFTS)):
        for j in range(i + 1, len(CRAFTS)):
            qs.append(VERSUS[(i + j) % len(VERSUS)].format(a=CRAFTS[i],
                                                           b=CRAFTS[j]))
    for g in GENERAL:
        for p in PHRASINGS[:2]:
            qs.append(p.format(q=g))
    return qs


def content_words(text):
    return {w for w in re.findall(r"[a-z0-9]+", text.lower())
            if len(w) > 3 and w not in pm.KNOWLEDGE_STOPWORDS}


def main():
    route_only = "--route-only" in sys.argv
    limit = None
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])
    qs = build_battery()
    if limit:
        qs = qs[:limit]
    packs = pm.knowledge_packs()
    assert packs, "no knowledge pack installed - run build_knowledge_pack.py"
    pack = packs[0]
    print(f"{len(qs)} questions; pack '{pack['id']}' "
          f"({pack.get('videos')} videos, {pack.get('n_chunks')} chunks)")

    # Phase 1+2: routing + retrieval (fast, no model)
    not_knowledge, no_chunks = [], []
    for q in qs:
        lane = pm.local_ai_lane(q, pm.recommend(pm.clean_text(q, spell)))
        if lane != "knowledge":
            not_knowledge.append((q, lane))
            continue
        if not pm.knowledge_retrieve(pack, q, k=4):
            no_chunks.append(q)
    print(f"routing: {len(qs) - len(not_knowledge)}/{len(qs)} -> knowledge lane")
    for q, lane in not_knowledge[:10]:
        print(f"   MISROUTE ({lane}): {q}")
    if len(not_knowledge) > 10:
        print(f"   ... +{len(not_knowledge) - 10} more")
    print(f"retrieval: {len(qs) - len(not_knowledge) - len(no_chunks)} with chunks, "
          f"{len(no_chunks)} with none")
    for q in no_chunks[:5]:
        print(f"   NO CHUNKS: {q}")
    if route_only:
        return

    # Phase 3: generation with grounding checks
    model = pm.pick_local_model(pm.ollama_models())
    assert model, "Ollama not running"
    results, t0 = [], time.perf_counter()
    flags = Counter()
    for i, q in enumerate(qs, 1):
        lane = pm.local_ai_lane(q, pm.recommend(pm.clean_text(q, spell)))
        entry = {"q": q, "lane": lane}
        if lane != "knowledge":
            entry["flags"] = ["misrouted"]
        else:
            sysp = pm.knowledge_system_prompt(pack, q) or pm.LOCAL_AI_LANES["answer"]
            grounded = "SOURCE EXCERPTS" in sysp
            t1 = time.perf_counter()
            try:
                out = pm.ollama_chat_stream(model, sysp, q, on_chunk=lambda p: None)
            except Exception as e:
                out, entry["error"] = "", str(e)
            entry["secs"] = round(time.perf_counter() - t1, 2)
            entry["out"] = out
            f = []
            if not out.strip():
                f.append("empty")
            elif len(out) > 1600:
                f.append("rambling")
            if grounded and out.strip():
                overlap = content_words(out) & content_words(sysp)
                ratio = len(overlap) / max(1, len(content_words(out)))
                entry["grounding"] = round(ratio, 2)
                if ratio < 0.25:
                    f.append("weakly-grounded")
            if not grounded:
                f.append("ungrounded-prompt")
            entry["flags"] = f
        flags.update(entry["flags"])
        results.append(entry)
        if i % 50 == 0:
            done = time.perf_counter() - t0
            eta = done / i * (len(qs) - i)
            print(f"  {i}/{len(qs)} ({done:.0f}s, eta {eta / 60:.0f}m)",
                  flush=True)
    with open("fpv_battery_results.json", "w", encoding="utf-8") as fjson:
        json.dump(results, fjson, indent=1, ensure_ascii=False)
    clean = sum(1 for r in results if not r["flags"])
    secs = [r["secs"] for r in results if "secs" in r]
    print(f"\n=== {len(qs)} questions: {clean} clean "
          f"({100 * clean / len(qs):.0f}%), avg {sum(secs) / max(1, len(secs)):.1f}s ===")
    print("flags:", dict(flags.most_common()))


if __name__ == "__main__":
    main()
