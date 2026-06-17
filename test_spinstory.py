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


if __name__ == "__main__":
    test_graph_integrity()
    test_all_nodes_reachable()
    test_branching_playthroughs()
    test_ending_varies_and_choose_guard()
    print("SPINSTORY TEST PASSED")
