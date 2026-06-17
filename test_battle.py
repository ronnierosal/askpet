"""Headless tests for the gentle Eldermark battle logic (no tkinter)."""
from askpet import EldermarkBattleLogic, ELDER_BATTLERS, ELDER_MOVES, ELDER_SCENES


def test_meet_and_contract():
    assert "gloomling" in ELDER_BATTLERS
    assert len(ELDER_MOVES) == 2
    L = EldermarkBattleLogic("gloomling")
    assert not L.over and L.won is None
    assert L.log == ELDER_BATTLERS["gloomling"]["meet"]
    print("meet + contract OK")


def test_win_by_fight():
    L = EldermarkBattleLogic("gloomling")
    guard = 0
    while not L.over and guard < 50:
        L.act("fight")
        guard += 1
    assert L.over and L.won is True
    assert L.e_hp == 0 and L.h_hp >= 0
    assert L.log == ELDER_BATTLERS["gloomling"]["win"]
    print("win by fight OK")


def test_item_heals_and_caps():
    L = EldermarkBattleLogic("gloomling", hero_hp=26)
    L.h_hp = 5
    before = L.items
    L.act("item")
    assert L.items == before - 1
    assert 5 < L.h_hp <= L.h_max
    L.h_hp = L.h_max                 # at full HP an item never exceeds max
    L.act("item")
    assert L.h_hp <= L.h_max
    # empty pack: spamming item does nothing harmful and never goes negative
    L.items = 0
    msg = L.act("item")
    assert "empty" in msg.lower() and L.items == 0
    print("item heal + cap OK")


def test_run_ends():
    L = EldermarkBattleLogic("gloomling")
    L.act("run")
    assert L.over and L.won is None
    # acting after over is a no-op (idempotent)
    snap = (L.e_hp, L.h_hp)
    L.act("fight")
    assert (L.e_hp, L.h_hp) == snap
    print("run ends OK")


def test_lose_path_is_gentle():
    L = EldermarkBattleLogic("gloomling", hero_hp=2)
    L.act("fight")                   # enemy survives, then its response -> hero rests
    assert L.over and L.won is False
    assert L.h_hp == 0
    assert L.log == ELDER_BATTLERS["gloomling"]["lose"]
    print("lose path OK")


def test_determinism():
    a = EldermarkBattleLogic("gloomling")
    b = EldermarkBattleLogic("gloomling")
    for action in ["fight", "item", "skill", "fight", "skill"]:
        a.act(action)
        b.act(action)
    assert (a.e_hp, a.h_hp, a.items, a.over, a.won) == \
           (b.e_hp, b.h_hp, b.items, b.over, b.won)
    print("determinism OK")


def test_hp_never_negative():
    L = EldermarkBattleLogic("gloomling", hero_hp=4)
    for _ in range(30):
        if L.over:
            break
        L.act("fight")
    assert L.h_hp >= 0 and L.e_hp >= 0
    print("hp never negative OK")


def test_item_at_full_hp_is_free():
    L = EldermarkBattleLogic("gloomling")        # constructed at full HP
    items = L.items
    L.act("item")
    assert not L.over
    assert L.h_hp == L.h_max          # no wasted heal and no retaliation
    assert L.items == items           # berry kept
    print("item at full HP is free OK")


def test_killing_blow_wins_cleanly():
    L = EldermarkBattleLogic("gloomling")
    L.e_hp = 1
    hp = L.h_hp
    L.act("fight")
    assert L.over and L.won is True
    assert L.e_hp == 0 and L.h_hp == hp   # winning turn -> no retaliation
    print("killing blow wins cleanly OK")


def test_unknown_action_is_noop():
    L = EldermarkBattleLogic("gloomling")
    snap = (L.e_hp, L.h_hp, L.turn, L.over)
    L.act("wiggle")
    assert (L.e_hp, L.h_hp, L.turn, L.over) == snap
    print("unknown action no-op OK")


def test_scene_battle_keys_resolve():
    for s in ELDER_SCENES.values():
        for npc in s["npcs"]:
            key = npc.get("battle")
            if key:
                assert key in ELDER_BATTLERS, f"unknown battler {key!r}"
    print("scene battle keys resolve OK")


def test_all_battlers_winnable():
    # every battler can be befriended (won) via FIGHT and leaves the hero standing
    for key in ELDER_BATTLERS:
        L = EldermarkBattleLogic(key)
        guard = 0
        while not L.over and guard < 60:
            L.act("fight")
            guard += 1
        assert L.over and L.won is True, f"{key} not winnable"
        assert L.h_hp >= 0
        for field in ("meet", "poke", "win", "lose"):
            assert ELDER_BATTLERS[key][field], f"{key} missing {field}"
    print("all battlers winnable OK")


if __name__ == "__main__":
    test_meet_and_contract()
    test_win_by_fight()
    test_item_heals_and_caps()
    test_item_at_full_hp_is_free()
    test_killing_blow_wins_cleanly()
    test_unknown_action_is_noop()
    test_run_ends()
    test_lose_path_is_gentle()
    test_determinism()
    test_hp_never_negative()
    test_scene_battle_keys_resolve()
    test_all_battlers_winnable()
    print("BATTLE TEST PASSED")
