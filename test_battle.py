"""Headless tests for the gentle Eldermark battle logic (no tkinter)."""
from askpet import EldermarkBattleLogic, ELDER_BATTLERS, ELDER_MOVES


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


if __name__ == "__main__":
    test_meet_and_contract()
    test_win_by_fight()
    test_item_heals_and_caps()
    test_run_ends()
    test_lose_path_is_gentle()
    test_determinism()
    test_hp_never_negative()
    print("BATTLE TEST PASSED")
