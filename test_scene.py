"""Headless tests for the Eldermark painted-scene logic + transitions (no tk)."""
from askpet import EldermarkSceneLogic, ELDER_SCENES, SCENE_W, SCENE_H


def _overlaps(x, y, pw, ph, rect):
    rx, ry, rw, rh = rect
    return x < rx + rw and x + pw > rx and y < ry + rh and y + ph > ry


def test_scenes_wellformed():
    assert "mosslight_gate" in ELDER_SCENES and "whisperwood" in ELDER_SCENES
    for sid, s in ELDER_SCENES.items():
        assert s["bg"].endswith(".png")
        L = EldermarkSceneLogic(s)
        sx, sy = s["spawn"]
        assert 0 <= sx and sx + L.PW <= SCENE_W
        assert 0 <= sy and sy + L.PH <= SCENE_H
        assert not L._blocked(sx, sy), f"{sid} spawn sits inside a solid"
        for (rx, ry, rw, rh) in s["solids"]:
            assert rw > 0 and rh > 0
            assert 0 <= rx and 0 <= ry and rx + rw <= SCENE_W and ry + rh <= SCENE_H
        for npc in s["npcs"]:
            assert npc["pages"] and all(isinstance(p, str) and p for p in npc["pages"])
            bx, by = npc["pos"]
            assert 0 <= bx <= SCENE_W and 0 <= by <= SCENE_H
    print("scenes well-formed OK")


def test_collision_and_bounds():
    for sid, s in ELDER_SCENES.items():
        L = EldermarkSceneLogic(s)
        for dirs in (["up"], ["down"], ["left"], ["right"], ["up", "left"],
                     ["up", "right"], ["down", "left"], ["down", "right"]):
            for _ in range(400):
                L.step(set(dirs))
                assert 0 <= L.x <= SCENE_W - L.PW, (sid, L.x, dirs)
                assert 0 <= L.y <= SCENE_H - L.PH, (sid, L.y, dirs)
                for r in L.solids:
                    assert not _overlaps(L.x, L.y, L.PW, L.PH, r), (sid, L.x, L.y, r)
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
    npc = next(n for n in L.npcs if n["id"] == "mossback")
    bx, by = npc["pos"]
    L.x, L.y = bx - L.PW // 2, by - L.PH // 2
    assert not L._blocked(L.x, L.y), "NPC base sits inside a solid"
    near = L.npc_in_range()
    assert near is not None and near["id"] == "mossback", (L.x, L.y, bx, by)
    L.x, L.y = L.scene["spawn"]
    assert L.npc_in_range() is None
    print("npc interaction OK")


def test_exits_resolve_and_dont_bounce():
    for sid, s in ELDER_SCENES.items():
        for ex in s.get("exits", []):
            to = ex["to"]
            assert to in ELDER_SCENES, f"{sid} exit -> unknown scene {to!r}"
            rx, ry, rw, rh = ex["at"]
            assert 0 <= rx and 0 <= ry and rx + rw <= SCENE_W and ry + rh <= SCENE_H
            spawn = ex.get("spawn")
            assert spawn, f"{sid} exit to {to} has no spawn"
            target = EldermarkSceneLogic(ELDER_SCENES[to], spawn=spawn)
            assert not target._blocked(*spawn), f"{to} arrival spawn in a solid"
            assert target.exit_at() is None, f"{to} arrival re-triggers an exit"
    print("exits resolve + don't bounce OK")


def test_exit_fires_when_walked_into():
    # walk up through the Mosslight Gate arch -> the Whisperwood exit should fire
    L = EldermarkSceneLogic(ELDER_SCENES["mosslight_gate"])
    fired = None
    for _ in range(400):
        L.step({"up"})
        fired = L.exit_at()
        if fired:
            break
    assert fired and fired["to"] == "whisperwood", (L.x, L.y)
    print("exit fires when walked into OK")


if __name__ == "__main__":
    test_scenes_wellformed()
    test_collision_and_bounds()
    test_determinism()
    test_npc_interaction()
    test_exits_resolve_and_dont_bounce()
    test_exit_fires_when_walked_into()
    print("SCENE TEST PASSED")
