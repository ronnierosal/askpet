"""Headless tests for the Spirit-Beast Blades branching story graph (no tkinter)."""
from askpet import SpinStoryLogic, SPIN_STORY, spin_ending_text


def test_graph_integrity():
    for nid, n in SPIN_STORY.items():
        assert ("next" in n) or ("choices" in n) or n.get("end"), f"{nid} dead-ends"
        if "next" in n:
            assert n["next"] in SPIN_STORY, f"{nid}.next -> {n['next']!r} missing"
        for ch in n.get("choices", []):
            assert ch["to"] in SPIN_STORY, f"{nid} choice -> {ch['to']!r} missing"
            assert ch["label"]
    print("graph integrity OK")


def test_all_nodes_reachable():
    seen, stack = set(), ["intro"]
    while stack:
        nid = stack.pop()
        if nid in seen:
            continue
        seen.add(nid)
        n = SPIN_STORY[nid]
        if "next" in n:
            stack.append(n["next"])
        for ch in n.get("choices", []):
            stack.append(ch["to"])
    assert seen == set(SPIN_STORY), f"unreachable: {set(SPIN_STORY) - seen}"
    print("all nodes reachable OK")


def test_branching_playthroughs():
    # calm + clever counter -> a respectful ending
    a = SpinStoryLogic()
    a.advance(); a.choose(0); a.advance(); a.choose(1); a.advance()
    assert a.over and "calm" in a.flags and "bow" in a.text().lower()
    # bold + power move -> a roaring ending
    b = SpinStoryLogic()
    b.advance(); b.choose(1); b.advance(); b.choose(0); b.advance()
    assert b.over and "bold" in b.flags and "roars" in b.text().lower()
    print("branching playthroughs OK")


def test_ending_varies_and_choose_guard():
    assert spin_ending_text({"calm"}) != spin_ending_text({"bold"})
    L = SpinStoryLogic()
    assert L.choose(9) is None and L.node_id == "intro"   # bad index is a no-op
    assert L.advance() == "taunt"                          # non-choice node advances
    print("ending varies + choose guard OK")


def test_comic_layout():
    from askpet import spin_comic_rects, SPIN_COMIC_SAMPLE as P
    rects = spin_comic_rects(P["panels"], P["cols"], P["rows"], 600, 800)
    assert len(rects) == len(P["panels"])
    for (x, y, w, h) in rects:
        assert x >= 0 and y >= 0 and x + w <= 600 and y + h <= 800 and w > 0 and h > 0
    for i in range(len(rects)):                 # panels must not overlap
        ax, ay, aw, ah = rects[i]
        for j in range(i + 1, len(rects)):
            bx, by, bw, bh = rects[j]
            assert not (ax < bx + bw and ax + aw > bx and ay < by + bh and ay + ah > by), (i, j)
    print("comic layout OK")


def _comic_exits(n):
    """Every node a comic node can hand off to (next + each choice target)."""
    return ([n["next"]] if "next" in n else []) + [c["to"] for c in n.get("choices", [])]


def _documented_art():
    """The set of art filenames promised across the prompt files (ART_PROMPTS.txt
    = to-create, ART_PROMPTS_DONE.txt = completed) — the source of truth for which
    cid_expr.png / id_bg.png the story may reference."""
    import re
    from askpet import SPIN_ASSETS
    arts = set()
    for f in sorted(SPIN_ASSETS.glob("ART_PROMPTS*.txt")):
        arts |= set(re.findall(r"([A-Za-z0-9_]+\.png)", f.read_text(encoding="utf-8", errors="ignore")))
    return arts


def _play(S, policy):
    """Walk the whole arc from 'open' to an end node, asking policy(choices) for
    an index at every decision and auto-advancing everything else."""
    from askpet import SpinStoryLogic
    L, steps = SpinStoryLogic(S, start="open"), 0
    while not L.over and steps < 300:
        steps += 1
        chs = L.choices()
        if chs:
            L.choose(policy(chs))
        elif L.advance() is None:
            break
    return L


def test_comic_story():
    from askpet import (SPIN_COMIC_STORY as S, SPIN_COMIC_SAMPLE, spin_comic_rects,
                        spin_comic_ending, SPIN_HEART, SPIN_FIRE, SPIN_BORDERS, SPIN_BUBBLES,
                        SPIN_FX)
    arts = _documented_art()
    flags_set = set()
    for nid, n in S.items():
        assert n["page"]["panels"], f"{nid} empty page"
        # every node has EXACTLY one exit kind (matches the engine: next/choices/end)
        kinds = ("next" in n) + ("choices" in n) + bool(n.get("end"))
        assert kinds == 1, f"{nid} must have exactly one of next/choices/end (has {kinds})"
        if "next" in n:
            assert n["next"] in S, f"{nid}.next -> {n['next']!r} missing"
        for ch in n.get("choices", []):
            assert ch["to"] in S, f"{nid} choice -> {ch['to']!r} missing"
            assert ch["label"], f"{nid} choice missing label"
            if "set" in ch:
                flags_set.add(ch["set"])
        # every page lays out fully in-bounds (the comic story renders at 600x724)
        for (x, y, w, h) in spin_comic_rects(n["page"]["panels"], n["page"]["cols"],
                                             n["page"]["rows"], 600, 724):
            assert w >= 1 and h >= 1 and 0 <= x and 0 <= y and x + w <= 600 and y + h <= 724, nid
        # every char/bg id resolves to a documented art asset (no typos), and
        # every border / bubble style is a known one (no typos)
        for p in n["page"]["panels"]:
            if p.get("char"):
                cid, expr = p["char"]
                assert f"{cid}_{expr}.png" in arts, f"{nid}: undocumented art {cid}_{expr}.png"
            if p.get("bg"):
                assert f"{p['bg']}_bg.png" in arts, f"{nid}: undocumented bg {p['bg']}_bg.png"
            assert p.get("border", "plain") in SPIN_BORDERS, f"{nid}: bad border {p.get('border')!r}"
            assert p.get("fx", "tone") in SPIN_FX, f"{nid}: bad fx {p.get('fx')!r}"
            assert p.get("bubble_style", "speech") in SPIN_BUBBLES, \
                f"{nid}: bad bubble_style {p.get('bubble_style')!r}"
            if p.get("bubble_style"):               # a style with no balloon is a silent no-op
                assert p.get("bubble") or p.get("ending_bubble"), \
                    f"{nid}: bubble_style on a panel with no bubble"

    # no dead-ends + every node reachable from the entry node "open"
    seen, stack = set(), ["open"]
    while stack:
        cur = stack.pop()
        if cur in seen:
            continue
        seen.add(cur)
        stack.extend(_comic_exits(S[cur]))
    assert seen == set(S), f"unreachable: {set(S) - seen}"

    # the six style flags the story advertises are all actually set by some choice
    assert flags_set == set(SPIN_HEART) | set(SPIN_FIRE), flags_set

    # the /spincomic SAMPLE page resolves its art + uses only known, used styles too
    for p in SPIN_COMIC_SAMPLE["panels"]:
        if p.get("char"):
            cid, expr = p["char"]
            assert f"{cid}_{expr}.png" in arts, f"SAMPLE: undocumented art {cid}_{expr}.png"
        if p.get("bg"):
            assert f"{p['bg']}_bg.png" in arts, f"SAMPLE: undocumented bg {p['bg']}_bg.png"
        assert p.get("border", "plain") in SPIN_BORDERS, f"SAMPLE: bad border {p.get('border')!r}"
        assert p.get("fx", "tone") in SPIN_FX, f"SAMPLE: bad fx {p.get('fx')!r}"
        assert p.get("bubble_style", "speech") in SPIN_BUBBLES, "SAMPLE: bad bubble_style"
        if p.get("bubble_style"):
            assert p.get("bubble") or p.get("ending_bubble"), "SAMPLE: bubble_style w/o bubble"

    # --- the endings are flag-driven: walk the arc three ways -------------
    def pole(want):                       # pick the choice that sets a flag in `want`
        def f(chs):
            for i, c in enumerate(chs):
                if c.get("set") in want:
                    return i
            return 0                      # a battle choice (no style flag) -> first
        return f

    all_heart = _play(S, pole(set(SPIN_HEART)))
    assert all_heart.over and all_heart.node_id == "ending"
    assert all_heart.flags == set(SPIN_HEART), all_heart.flags
    all_fire = _play(S, pole(set(SPIN_FIRE)))
    assert all_fire.over and all_fire.node_id == "ending"
    assert all_fire.flags == set(SPIN_FIRE), all_fire.flags

    # a mixed run: fire only on the 2nd character choice, heart otherwise
    state = {"n": 0}

    def mixed(chs):
        sets = [c.get("set") for c in chs]
        if any(s in set(SPIN_HEART) | set(SPIN_FIRE) for s in sets):  # a character choice
            state["n"] += 1
            want = set(SPIN_FIRE) if state["n"] == 2 else set(SPIN_HEART)
            return next(i for i, c in enumerate(chs) if c.get("set") in want)
        return 0
    blend = _play(S, mixed)
    assert blend.over and blend.node_id == "ending"
    assert blend.flags == {"calm", "fierce", "steady"}, blend.flags

    # all three endings are distinct AND each is reachable by some flag combo
    e_heart = spin_comic_ending(all_heart.flags)
    e_fire = spin_comic_ending(all_fire.flags)
    e_blend = spin_comic_ending(blend.flags)
    assert len({e_heart, e_fire, e_blend}) == 3, (e_heart, e_fire, e_blend)
    assert "HEART" in e_heart and "FIRE" in e_fire and "BLADE" in e_blend
    # spin_comic_ending is a pure function of flags — check the buckets directly,
    # exhaustively, so a boundary regression (e.g. a 1-heart/2-fire mix) can't hide
    assert "HEART" in spin_comic_ending(set(SPIN_HEART))      # all heart
    assert "FIRE" in spin_comic_ending(set(SPIN_FIRE))        # all fire
    for mix in ({"calm", "fierce", "steady"}, {"bold", "kind", "reckless"},
                {"calm", "fierce", "reckless"}, {"bold", "kind", "steady"},
                {"calm", "bold"}, set()):                     # any blend (or none) -> BLADE
        assert "BLADE" in spin_comic_ending(mix), mix
    print("comic story OK")


def test_comic_render_styles():
    """Every border + bubble style draws on a real canvas (each bubble adds items
    AND keeps its text), the all-styles page stays on-canvas, the SAMPLE renders,
    and EVERY story page renders with the ending's champion title injected."""
    import tkinter as tk
    from askpet import (spin_draw_page, spin_comic_ending, SPIN_BORDERS, SPIN_BUBBLES,
                        SPIN_FX, SPIN_COMIC_SAMPLE, SPIN_COMIC_STORY)
    try:
        root = tk.Tk(); root.withdraw()
    except tk.TclError:
        print("comic render styles SKIPPED (no display)"); return
    try:
        cv = tk.Canvas(root, width=600, height=820)

        def render(page, W=600, H=724):
            cv.delete("all")
            spin_draw_page(cv, page, W, H, {}, [])
            return cv.find_all()

        def one(extra):
            return {"cols": 1, "rows": 1, "panels": [{"grid": (0, 0, 1, 1), **extra}]}

        # each bubble style adds items over a bubble-less control AND keeps its text
        # label (so a future silent collapse of the radial/clamp math is caught)
        control = len(render(one({})))
        for st in SPIN_BUBBLES:
            items = render(one({"bubble": "Hi\nthere", "bubble_style": st}))
            assert len(items) > control, f"bubble {st} drew nothing extra"
            texts = [cv.itemcget(i, "text") for i in items if cv.type(i) == "text"]
            assert any("there" in t for t in texts), f"bubble {st} lost its text"

        for fx in SPIN_FX:                          # every background effect draws
            assert render(one({"char": ("kael", "neutral"), "fx": fx})), f"fx {fx} drew nothing"

        # a page using every border x every bubble draws and stays on the canvas
        n = max(len(SPIN_BORDERS), len(SPIN_BUBBLES))
        assert render({"cols": 1, "rows": n, "panels": [
            {"grid": (0, i, 1, 1), "border": SPIN_BORDERS[i % len(SPIN_BORDERS)],
             "bubble": "Style\ntest!", "bubble_style": SPIN_BUBBLES[i % len(SPIN_BUBBLES)]}
            for i in range(n)]}), "style page drew nothing"
        x1, y1, x2, y2 = cv.bbox("all")            # spikes/clouds may bleed into the
        assert -12 <= x1 and -12 <= y1 and x2 <= 612 and y2 <= 736, (x1, y1, x2, y2)  # gutter, never off-canvas

        assert render(SPIN_COMIC_SAMPLE, 600, 800), "sample drew nothing"

        assert spin_comic_ending(set())            # the no-flag fallback bucket is non-empty
        for nid, node in SPIN_COMIC_STORY.items():
            pg = node["page"]
            if node.get("end"):
                pg = {**pg, "panels": [
                    ({**pp, "bubble": spin_comic_ending(set())} if pp.get("ending_bubble") else pp)
                    for pp in pg["panels"]]}
            assert render(pg), nid
            if node.get("end"):                    # the champion title really got injected
                texts = [cv.itemcget(i, "text") for i in cv.find_all() if cv.type(i) == "text"]
                assert any("BLADE" in t for t in texts), f"{nid}: ending bubble not injected"
        root.update_idletasks()
    finally:
        root.destroy()
    print("comic render styles OK")


def test_comic_quads():
    """spin_comic_quads: identity when flat, tessellating + in-bounds + non-inverting
    trapezoids when slanted; _spin_quad_safe stays inside the quad."""
    from askpet import (spin_comic_quads, spin_comic_rects, _spin_quad_safe,
                        _spin_auto_slants, SPIN_COMIC_STORY as S, SPIN_COMIC_SAMPLE)

    def bbox(q):
        xs = [c[0] for c in q]; ys = [c[1] for c in q]
        return min(xs), min(ys), max(xs), max(ys)

    # (a) IDENTITY + (d) safe-rect: slants=None -> quad bbox == spin_comic_rects rect
    for pg in [n["page"] for n in S.values()] + [SPIN_COMIC_SAMPLE]:
        rects = spin_comic_rects(pg["panels"], pg["cols"], pg["rows"], 600, 724)
        quads = spin_comic_quads(pg["panels"], pg["cols"], pg["rows"], 600, 724)
        for (x, y, w, h), q in zip(rects, quads):
            assert bbox(q) == (x, y, x + w, y + h), (x, y, w, h, q)
            sx, sy, sw, sh = _spin_quad_safe(q)
            assert sw >= 1 and sh >= 1 and sx >= x and sy >= y and sx + sw <= x + w

    # (b)+(c)+(e): a dynamic 3-row page is in-bounds, tessellates, never inverts
    panels = [{"grid": (0, 0, 1, 1)}, {"grid": (0, 1, 1, 1)}, {"grid": (0, 2, 1, 1)}]
    quads = spin_comic_quads(panels, 1, 3, 600, 724, slants=_spin_auto_slants(3))
    for q in quads:
        for (px, py) in q:
            assert 0 <= px <= 600 and 0 <= py <= 724, q          # (b) in bounds
        assert q[3][1] > q[0][1] and q[2][1] > q[1][1]           # (e) bottom below top
    assert quads[0][3] == quads[1][0] and quads[0][2] == quads[1][1]   # (c) shared seam 0
    assert quads[1][3] == quads[2][0] and quads[1][2] == quads[2][1]   # (c) shared seam 1

    # (e) a huge tilt is clamped so no panel inverts
    for q in spin_comic_quads(panels, 1, 3, 600, 724, slants=[("seam", 0, 9999)]):
        assert q[3][1] > q[0][1] and q[2][1] > q[1][1]
    print("comic quads OK")


if __name__ == "__main__":
    test_graph_integrity()
    test_all_nodes_reachable()
    test_branching_playthroughs()
    test_ending_varies_and_choose_guard()
    test_comic_layout()
    test_comic_story()
    test_comic_quads()
    test_comic_render_styles()
    print("SPINSTORY TEST PASSED")
