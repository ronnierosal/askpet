#!/usr/bin/env python3
"""Build the FPV newbie FAQ knowledge pack from fpv_newbie_faq.json.

Unlike transcript packs (build_knowledge_pack.py), this content IS
committed: short original-wording answers synthesized from public
community sources, each credited with its source URL. One Q&A per
chunk — small chunks retrieve much more precisely than transcript
slabs for FAQ-style questions.

The built pack lands in the user-data dir
(%LOCALAPPDATA%/AskPet/knowledge/<id>) next to any transcript packs;
packs stack, so battery questions can pull from both.

Usage: python build_faq_pack.py [src.json]
"""

import json
import sys
from datetime import datetime
from pathlib import Path

import askpet as pm

sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def main():
    src = Path(sys.argv[1] if len(sys.argv) > 1 else "fpv_newbie_faq.json")
    data = json.loads(src.read_text(encoding="utf-8-sig"))
    faqs = data["faqs"]
    chunks = []
    for f in faqs:
        chunks.append({
            "v": f.get("source_url", ""),
            "t": f"FAQ: {f['q']}",
            "x": f"Q: {f['q']}\nA: {f['a']} (source: {f.get('source_name', 'community FAQ')})",
        })
    pack_dir = pm.KNOWLEDGE_DIR / data["id"]
    pack_dir.mkdir(parents=True, exist_ok=True)
    pm.save_json(pack_dir / "pack.json", {
        "id": data["id"],
        "name": data["name"],
        "credit": data["credit"],
        "keywords": data["keywords"],
        "source": str(src.name),
        "built": datetime.now().isoformat(timespec="seconds"),
        "n_chunks": len(chunks),
    })
    pm.save_json(pack_dir / "chunks.json", chunks)
    topics = {}
    for f in faqs:
        topics[f.get("topic", "other")] = topics.get(f.get("topic", "other"), 0) + 1
    print(f"pack '{data['id']}': {len(chunks)} Q&A chunks -> {pack_dir}")
    print("topics:", dict(sorted(topics.items(), key=lambda t: -t[1])))


if __name__ == "__main__":
    main()
