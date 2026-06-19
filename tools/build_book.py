"""Assemble the 19 written chapters (_book_src.json) into the playable book graph
(assets/spinstory/book.json) the SpinStoryBook reader loads.

Each chapter is an ordered list of pages (prose / choice / manga). This builder:
  - prefixes ids per chapter (c<ch>_<id>), converts art tokens to refs,
  - links pages linearly and across chapters,
  - wires choices + their branch rejoins, the three scoring flags, the battle
    choices, and the flag-driven ending,
  - inserts manga page layouts at the manga markers,
  - validates connectivity / flags / endings / documented art, then writes book.json.
Build-time tool only; the game just loads the JSON.
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SPIN = ROOT / "assets" / "spinstory"
SRC = SPIN / "_book_src.json"
OUT = SPIN / "book.json"

chapters = json.load(open(SRC, encoding="utf-8"))
chapters.sort(key=lambda c: c["chapter"])

TITLES = {
    1: "The Chipped Blade", 2: "The Six Signs", 3: "The Coliseum Gate", 4: "The Gauntlet",
    5: "Kael, the Cocky Qualifier", 6: "Wolf and the Wobble", 7: "Between Rounds",
    8: "The Strategist's Eye", 9: "Mind Against Mind", 10: "The Spirit-Sage",
    11: "The Frost-Sage", 12: "The Gentle Giant", 13: "Thunder and Heart", 14: "The Night Before",
    15: "The Masked Ace", 16: "The Cold Blade", 17: "You Are Not Alone", 18: "The Silence Breaks",
    19: "Champion",
}


def nid(ch, pid):
    return f"c{ch}_{pid}"


def art_ref(token):
    """'bg:dishhall' -> ['bg','dishhall']; 'char:kael:smug' -> ['char','kael','smug'];
    'img:top_hero' -> ['img','top_hero']."""
    if not token:
        return None
    parts = token.split(":")
    return parts


# -- manga page layouts (reuse the proven panel grammar; real action art) ------
def _battle(rival):
    """wide clash (impact) / rival fierce close-up / launch beat / wide prompt."""
    p2 = ({"grid": [0, 1, 1, 1], "char": [rival, "fierce"], "shot": "close", "fx": "focus"}
          if rival else {"grid": [0, 1, 1, 1], "fx": "focus", "caption": "Steel screams."})
    return {"cols": 2, "rows": 3, "panels": [
        {"grid": [0, 0, 2, 1], "bg": "clash", "caption": "THE BLADES COLLIDE!", "border": "impact"},
        p2,
        {"grid": [1, 1, 1, 1], "bg": "launch", "caption": "Steel sings."},
        {"grid": [0, 2, 2, 1], "bg": "arena", "caption": "What will Rin do?"}]}


def _reveal():
    return {"cols": 2, "rows": 3, "panels": [
        {"grid": [0, 0, 2, 1], "bg": "finals", "caption": "THE MASKED ACE", "border": "bold"},
        {"grid": [0, 1, 1, 2], "char": ["raze", "masked"], "shot": "close", "fx": "focus"},
        {"grid": [1, 1, 1, 1], "bg": "gate", "caption": "Who is he?"},
        {"grid": [1, 2, 1, 1], "bg": "crowd", "caption": "The crowd holds its breath."}]}


def _sever():
    return {"cols": 2, "rows": 3, "panels": [
        {"grid": [0, 0, 2, 1], "bg": "clash", "fx": "flash", "caption": "THE COLD BLADE", "border": "impact"},
        {"grid": [0, 1, 1, 1], "char": ["raze", "cold"], "shot": "close", "fx": "focus"},
        {"grid": [1, 1, 1, 1], "bg": "launch", "caption": "Knocked from the sky."},
        {"grid": [0, 2, 2, 1], "bg": "finals", "caption": "One breath to decide."}]}


def _unite():
    return {"cols": 2, "rows": 3, "panels": [
        {"grid": [0, 0, 2, 1], "bg": "finals", "caption": "YOU ARE NOT ALONE!", "border": "bold"},
        {"grid": [0, 1, 1, 1], "char": ["kael", "fierce"], "shot": "close", "fx": "flash"},
        {"grid": [1, 1, 1, 1], "char": ["mira", "fierce"], "shot": "close", "fx": "flash"},
        {"grid": [0, 2, 2, 1], "char": ["brakk", "grin"], "fx": "focus", "caption": "Three friends stand with Rin."}]}


def _awaken():
    return {"cols": 2, "rows": 3, "panels": [
        {"grid": [0, 0, 2, 1], "bg": "spirit", "caption": "THE TRUE FORM AWAKENS!", "border": "bold"},
        {"grid": [0, 1, 1, 1], "fx": "flash", "caption": "Radiant!"},
        {"grid": [1, 1, 1, 1], "char": ["mentor", "smile"], "shot": "close", "fx": "flash"},
        {"grid": [0, 2, 2, 1], "bg": "finals", "caption": "The bond blazes bright."}]}


def _silence():
    return {"cols": 2, "rows": 3, "panels": [
        {"grid": [0, 0, 2, 1], "bg": "spirit", "fx": "flash", "caption": "THE SILENCE BREAKS", "border": "bold"},
        {"grid": [0, 1, 1, 1], "char": ["raze", "shocked"], "shot": "close", "fx": "focus"},
        {"grid": [1, 1, 1, 1], "img_caption": 1, "char": ["mentor", "smile"], "shot": "close", "fx": "flash"},
        {"grid": [0, 2, 2, 1], "bg": "finals", "caption": "Light crosses the dish."}]}


# manga layout chosen per chapter (battle chapters carry the tactical choice)
def manga_layout(ch):
    if ch == 4:
        return _battle(None)
    if ch == 6:
        return _battle("kael")
    if ch == 9:
        return _battle("mira")
    if ch == 13:
        return _battle("brakk")
    if ch == 15:
        return _reveal()
    if ch == 16:
        return _sever()
    if ch == 18:
        return _silence()
    return None  # ch17 handled specially (two pages)


HEART = ("calm", "kind", "steady")
FIRE = ("bold", "fierce", "reckless")
SCORING = set(HEART) | set(FIRE)

# fallback scene behind a character portrait when the chapter has no bg page
CHAR_BG = {"kael": "arena", "mira": "arena", "brakk": "arena", "raze": "finals",
           "mentor": "training", "pae": "dishhall", "vehesal": "pavilion",
           "oru": "finals", "rin": "arena"}

nodes = {}
start = nid(1, chapters[0]["pages"][0]["id"])

# first-page id of each chapter (for cross-chapter linking)
first_of = {c["chapter"]: nid(c["chapter"], c["pages"][0]["id"]) for c in chapters}

for ci, ch in enumerate(chapters):
    num = ch["chapter"]
    pages = ch["pages"]
    idx = {p["id"]: j for j, p in enumerate(pages)}

    bg_pages = [(j, pp["art"].split(":")[1]) for j, pp in enumerate(pages)
                if (pp.get("art") or "").startswith("bg:")]

    def scene_for(j, cid):
        """A scene id to place behind a character portrait: the chapter's nearest
        preceding background, else its first, else a per-character default."""
        prev = [b for (k, b) in bg_pages if k <= j]
        if prev:
            return prev[-1]
        if bg_pages:
            return bg_pages[0][1]
        return CHAR_BG.get(cid, "arena")

    def default_next(j):
        if j + 1 < len(pages):
            return nid(num, pages[j + 1]["id"])
        if num < 19:
            return first_of[num + 1]
        return None  # last page of book -> end

    # precompute, per choice, the branch entries + merge target
    branch_next = {}   # page id -> forced next (rejoin)
    for j, p in enumerate(pages):
        opts = p.get("options")
        if not opts:
            continue
        entries = [o["goto"] for o in opts if o.get("goto") in idx]
        if not entries:
            continue
        eidx = [idx[g] for g in entries]
        lo, hi = min(eidx), max(eidx)
        merge = default_next(hi)
        entryset = set(entries)
        for k in range(lo, hi + 1):
            pg = pages[k]
            # the END of a branch (a single-page entry, or the block's last page)
            # rejoins at the natural merge point, overriding any explicit next that
            # would skip a shared continuation page
            if k == hi or pages[k + 1]["id"] in entryset:
                branch_next[pg["id"]] = merge

    for j, p in enumerate(pages):
        node = {}
        pid = p["id"]
        n = nid(num, pid)
        if p.get("art"):
            a = art_ref(p["art"])
            if a and a[0] == "char":
                a = a + [scene_for(j, a[1])]      # composite the portrait over a scene
            node["art"] = a
        if p.get("text"):
            node["text"] = p["text"]
        if num == 1 and j == 0 and "chapter" not in node:
            pass  # chapter label handled below
        # chapter label + title on the first page of each chapter
        if j == 0:
            node["chapter"] = f"CHAPTER {num}"
            node["title"] = TITLES.get(num, "")

        is_manga = p["kind"] == "manga"
        opts = p.get("options")

        if is_manga:
            node["type"] = "manga"
            if num == 17:
                # two manga pages in ch17: unite then awaken (by order)
                node["page"] = _unite() if pid in ("unite", "rivals_rise", "page_a") or "unite" in pid or "alone" in pid else _awaken()
            else:
                node["page"] = manga_layout(num) or _battle(None)

        # exits
        if num == 19 and opts and any(o["goto"].startswith("end_") for o in opts):
            # flag-driven ending router (NOT a reader choice)
            node["flag_next"] = {
                "heart": nid(19, "end_heart"),
                "fire": nid(19, "end_fire"),
                "blade": nid(19, "end_blade"),
            }
        elif opts:
            chs = []
            for o in opts:
                c = {"label": o["label"], "to": nid(num, o["goto"])}
                if o.get("flag") and o["flag"] in SCORING:
                    c["set"] = o["flag"]
                chs.append(c)
            node["choices"] = chs
        else:
            if pid in branch_next and branch_next[pid]:
                node["next"] = branch_next[pid]
            elif p.get("next"):
                node["next"] = nid(num, p["next"])
            else:
                dn = default_next(j)
                if dn:
                    node["next"] = dn
                else:
                    node["end"] = True
        nodes[n] = node

book = {"start": start, "nodes": nodes}

# ---- validation -----------------------------------------------------------
errs = []
# documented art
arts = set()
for f in sorted(SPIN.glob("ART_PROMPTS*.txt")):
    arts |= set(re.findall(r"([A-Za-z0-9_]+\.png)", f.read_text(encoding="utf-8", errors="ignore")))


def check_art(a, where):
    if not a:
        return
    pngs = []
    if a[0] == "bg":
        pngs = [f"{a[1]}_bg.png"]
    elif a[0] == "char":
        pngs = [f"{a[1]}_{a[2]}.png"] + ([f"{a[3]}_bg.png"] if len(a) > 3 else [])
    elif a[0] == "img":
        pngs = [f"{a[1]}.png"]
    for png in pngs:
        if png not in arts:
            errs.append(f"{where}: undocumented art {png} ({a})")


for n, node in nodes.items():
    kinds = ("next" in node) + ("choices" in node) + bool(node.get("end")) + ("flag_next" in node)
    if kinds != 1:
        errs.append(f"{n}: must have exactly one exit (has {kinds}): "
                    f"{[k for k in ('next','choices','end','flag_next') if node.get(k)]}")
    check_art(node.get("art"), n)
    for c in node.get("choices", []):
        if c["to"] not in nodes:
            errs.append(f"{n}: choice -> missing {c['to']}")
    if node.get("next") and node["next"] not in nodes:
        errs.append(f"{n}: next -> missing {node['next']}")
    for t in (node.get("flag_next") or {}).values():
        if t not in nodes:
            errs.append(f"{n}: flag_next -> missing {t}")
    if node.get("type") == "manga":
        for p in node["page"]["panels"]:
            if p.get("char"):
                check_art(["char"] + list(p["char"]), n + " (manga)")
            if p.get("bg"):
                check_art(["bg", p["bg"]], n + " (manga)")

# reachability + flags
seen, stack = set(), [start]
while stack:
    cur = stack.pop()
    if cur in seen or cur not in nodes:
        continue
    seen.add(cur)
    nd = nodes[cur]
    if nd.get("next"):
        stack.append(nd["next"])
    for c in nd.get("choices", []):
        stack.append(c["to"])
    for t in (nd.get("flag_next") or {}).values():
        stack.append(t)
unreached = set(nodes) - seen
if unreached:
    errs.append(f"UNREACHABLE ({len(unreached)}): {sorted(list(unreached))[:12]}")

flags_set = set()
for node in nodes.values():
    for c in node.get("choices", []):
        if c.get("set"):
            flags_set.add(c["set"])
if flags_set != SCORING:
    errs.append(f"flags set = {sorted(flags_set)} (want {sorted(SCORING)})")

print(f"nodes: {len(nodes)}  reachable: {len(seen)}  flags: {sorted(flags_set)}")
manga = [n for n, v in nodes.items() if v.get("type") == "manga"]
print(f"manga pages: {len(manga)} -> {manga}")
if errs:
    print("\n!!! VALIDATION ERRORS:")
    for e in errs:
        print("  -", e)
    raise SystemExit(1)

json.dump(book, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(f"\nOK -> wrote {OUT} ({OUT.stat().st_size} bytes)")
