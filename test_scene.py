"""Headless tests for the Eldermark painted-scene logic (no tkinter)."""
from askpet import EldermarkSceneLogic, ELDER_SLICE, SCENE_W, SCENE_H


def _overlaps(x, y, pw, ph, rect):
    rx, ry, rw, rh = rect
    return x < rx + rw and x + pw > rx and y < ry + rh and y + ph > ry


def test_scene_wellformed():
    s = ELDER_SLICE
    assert s["bg"].endswith(".png")
    L = EldermarkSceneLogic(s)
    sx, sy = s["spawn"]
    assert 0 <= sx and sx + L.PW <= SCENE_W
    assert 0 <= sy and sy + L.PH <= SCENE_H
    assert not L._blocked(sx, sy), "spawn sits inside a solid"
    for (rx, ry, rw, rh) in s["solids"]:
        assert rw > 0 and rh > 0
        assert 0 <= rx and 0 <= ry and rx + rw <= SCENE_W and ry + rh <= SCENE_H
    for npc in s["npcs"]:
        assert npc["pages"] and all(isinstance(p, str) and p for p in npc["pages"])
        bx, by = npc["pos"]
        assert 0 <= bx <= SCENE_W and 0 <= by <= SCENE_H
    print("scene well-formed OK")


def test_collision_and_bounds():
    L = EldermarkSceneLogic()
    for dirs in (["up"], ["down"], ["left"], ["right"], ["up", "left"],
                 ["up", "right"], ["down", "left"], ["down", "right"]):
        for _ in range(400):
            L.step(set(dirs))
            assert 0 <= L.x <= SCENE_W - L.PW, (L.x, dirs)
            assert 0 <= L.y <= SCENE_H - L.PH, (L.y, dirs)
            for r in L.solids:
                assert not _overlaps(L.x, L.y, L.PW, L.PH, r), (L.x, L.y, r, dirs)
    print("collision + bounds OK")


def test_determinism():
    seq = [["right"], ["right", "down"], ["down"], ["left"], ["up"], []] * 50
    a, b = EldermarkSceneLogic(), EldermarkSceneLogic()
    for s in seq:
        a.step(set(s))
        b.step(set(s))
    assert (a.x, a.y, a.facing) == (b.x, b.y, b.facing)
    print("determinism OK")


def test_npc_interaction():
    L = EldermarkSceneLogic()
    assert L.npc_in_range() is None, "should not be talking at spawn"
    target = next(n for n in L.npcs if n["id"] == "mossback")
    bx, by = target["pos"]
    for _ in range(800):                     # walk the player toward the NPC
        dirs = set()
        fx, fy = L.x + L.PW / 2, L.y + L.PH / 2
        if fx < bx - 2:
            dirs.add("right")
        elif fx > bx + 2:
            dirs.add("left")
        if fy < by - 2:
            dirs.add("down")
        elif fy > by + 2:
            dirs.add("up")
        if not dirs:
            break
        L.step(dirs)
    near = L.npc_in_range()
    assert near is not None and near["id"] == "mossback", (L.x, L.y, bx, by)
    print("npc interaction OK")


if __name__ == "__main__":
    test_scene_wellformed()
    test_collision_and_bounds()
    test_determinism()
    test_npc_interaction()
    print("SCENE TEST PASSED")
