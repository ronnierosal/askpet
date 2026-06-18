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


def test_comic_story():
    from askpet import SPIN_COMIC_STORY as S, spin_comic_rects, spin_comic_ending
    for nid, n in S.items():
        assert n["page"]["panels"], f"{nid} empty page"
        assert ("next" in n) or ("choices" in n) or n.get("end"), f"{nid} dead-ends"
        if "next" in n:
            assert n["next"] in S
        for ch in n.get("choices", []):
            assert ch["to"] in S and ch["label"]
        for (x, y, w, h) in spin_comic_rects(n["page"]["panels"], n["page"]["cols"],
                                             n["page"]["rows"], 600, 724):
            assert w >= 1 and h >= 1 and 0 <= x and 0 <= y and x + w <= 600 and y + h <= 724, nid
    seen, stack = set(), ["open"]
    while stack:
        nid = stack.pop()
        if nid in seen:
            continue
        seen.add(nid)
        n = S[nid]
        if "next" in n:
            stack.append(n["next"])
        for ch in n.get("choices", []):
            stack.append(ch["to"])
    assert seen == set(S), set(S) - seen
    L = SpinStoryLogic(S, start="open")
    L.choose(1); L.advance(); L.choose(0); L.advance()   # bold -> clash -> power -> end
    assert L.over and "bold" in L.flags
    assert spin_comic_ending({"bold"}) != spin_comic_ending({"calm"})
    print("comic story OK")


if __name__ == "__main__":
    test_graph_integrity()
    test_all_nodes_reachable()
    test_branching_playthroughs()
    test_ending_varies_and_choose_guard()
    test_comic_layout()
    test_comic_story()
    print("SPINSTORY TEST PASSED")
