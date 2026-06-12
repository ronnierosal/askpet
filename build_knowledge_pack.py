#!/usr/bin/env python3
"""Build a local AskPet knowledge pack from a YouTube channel's
auto-transcripts. Dev tool — requires yt-dlp (pip install yt-dlp).

The pack lands in the user-data dir (%LOCALAPPDATA%/AskPet/knowledge)
for personal, local use only. Transcript content is NEVER committed to
the repo or redistributed; the creator is credited in every answer.

Usage:
  python build_knowledge_pack.py URL PACK_ID --name "..." --credit "..."
      --keywords kw1,kw2,... [--limit N]
"""

import argparse
import json
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import askpet as pm

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
PY = sys.executable
CACHE = Path("_subs")  # gitignored download cache, resumable


def list_videos(url):
    out = subprocess.run(
        [PY, "-m", "yt_dlp", "--flat-playlist", "--print", "%(id)s\t%(title)s",
         url], capture_output=True, text=True, encoding="utf-8", errors="replace")
    videos = []
    for line in out.stdout.splitlines():
        if "\t" in line:
            vid, title = line.split("\t", 1)
            videos.append((vid.strip(), title.strip()))
    return videos


def fetch_vtt(video_id):
    target = CACHE / f"{video_id}.en.vtt"
    if target.exists():
        return target
    subprocess.run(
        [PY, "-m", "yt_dlp", "--write-auto-subs", "--sub-langs", "en",
         "--skip-download", "--no-warnings", "-o", str(CACHE / "%(id)s"),
         f"https://www.youtube.com/watch?v={video_id}"],
        capture_output=True, text=True)
    return target if target.exists() else None


def parse_vtt(path):
    """Rolling auto-captions repeat each line; keep first occurrences."""
    lines, last = [], None
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = re.sub(r"<[^>]+>", "", raw).strip()
        if (not line or "-->" in line or line.startswith(("WEBVTT", "Kind:", "Language:"))
                or line == last):
            continue
        if lines and line == lines[-1]:
            continue
        lines.append(line)
        last = line
    text = " ".join(lines)
    text = re.sub(r"\[(music|applause|laughter)\]", " ", text, flags=re.I)
    text = re.sub(r"\[\s*(&nbsp;)?__+\s*(&nbsp;)?\]", " ", text)  # censor marks
    return re.sub(r"\s+", " ", text).strip()


# A chunk must actually talk about the hobby to earn its place — flight
# edits give us song lyrics, livestream chatter gives us noise. Grounding
# an answer in lyrics is worse than no grounding at all.
TOPIC_TERMS = ("whoop", "fpv", "drone", "quad", "motor", "prop", "battery",
               "lipo", "vtx", "goggle", "betaflight", "flight controller",
               "fly", "flying", "flight", "bind", "receiver", "elrs",
               "antenna", "camera", "frame", "throttle", "tune", "pid",
               "rates", "crash", "hover", "freestyle", "analog", "digital",
               "transmitter", "kv", "esc", "aio", "soldering", "solder")


def on_topic(chunk: str) -> bool:
    xl = chunk.lower()
    hits = sum(xl.count(t) for t in TOPIC_TERMS)
    return hits >= 3


def chunk_text(text, size=1100, overlap=150):
    chunks, start = [], 0
    while start < len(text):
        end = min(len(text), start + size)
        if end < len(text):  # break at a sentence/word boundary if close
            cut = text.rfind(". ", start + size // 2, end)
            if cut == -1:
                cut = text.rfind(" ", start + size // 2, end)
            if cut > start:
                end = cut + 1
        chunks.append(text[start:end].strip())
        if end >= len(text):
            break
        start = max(start + 1, end - overlap)
    return [c for c in chunks if len(c) > 80]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("url")
    ap.add_argument("pack_id")
    ap.add_argument("--name", required=True)
    ap.add_argument("--credit", required=True)
    ap.add_argument("--keywords", required=True)
    ap.add_argument("--limit", type=int)
    args = ap.parse_args()

    CACHE.mkdir(exist_ok=True)
    videos = list_videos(args.url)
    if args.limit:
        videos = videos[:args.limit]
    print(f"{len(videos)} videos listed")

    all_chunks, used = [], 0
    for i, (vid, title) in enumerate(videos, 1):
        vtt = fetch_vtt(vid)
        if not vtt:
            continue
        text = parse_vtt(vtt)
        if len(text) < 200:  # music-only / no real speech
            continue
        kept = [x for x in chunk_text(text) if on_topic(x)]
        if not kept:
            continue
        used += 1
        for x in kept:
            all_chunks.append({"v": vid, "t": title, "x": x})
        if i % 25 == 0:
            print(f"  {i}/{len(videos)} videos ({used} with speech, "
                  f"{len(all_chunks)} chunks)")
        time.sleep(0.3)  # be kind to YouTube

    pack_dir = pm.KNOWLEDGE_DIR / args.pack_id
    pack_dir.mkdir(parents=True, exist_ok=True)
    pm.save_json(pack_dir / "pack.json", {
        "id": args.pack_id,
        "name": args.name,
        "credit": args.credit,
        "keywords": [k.strip() for k in args.keywords.split(",") if k.strip()],
        "source": args.url,
        "built": datetime.now().isoformat(timespec="seconds"),
        "videos": used,
        "n_chunks": len(all_chunks),
        "note": "Personal local use only - do not redistribute transcript content.",
    })
    pm.save_json(pack_dir / "chunks.json", all_chunks)
    print(f"pack '{args.pack_id}': {used} videos, {len(all_chunks)} chunks -> {pack_dir}")


if __name__ == "__main__":
    main()
