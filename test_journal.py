"""Headless tests for the Creature Journal data + meet/befriend state."""
from askpet import (EldermarkState, ELDER_CREATURES, ELDER_BATTLERS,
                    ELDER_SCENES, ELDER_STATE)


def test_state_meet_befriend():
    s = EldermarkState()
    assert not s.met and not s.friends
    s.meet("mossback")
    assert "mossback" in s.met and "mossback" not in s.friends
    s.befriend("gloomling")
    assert "gloomling" in s.met and "gloomling" in s.friends
    print("state meet/befriend OK")


def test_creatures_wellformed():
    assert ELDER_CREATURES
    for cid, c in ELDER_CREATURES.items():
        assert c["name"] and c["lore"]
        assert c["sprite"].endswith(".png")
    print("creatures well-formed OK")


def test_battlers_have_journal_entries():
    # winning a battle befriends by enemy_key, so every battler needs an entry
    for k in ELDER_BATTLERS:
        assert k in ELDER_CREATURES, f"battler {k!r} has no journal entry"
    print("battlers have journal entries OK")


def test_scene_creature_keys_resolve():
    for s in ELDER_SCENES.values():
        for npc in s["npcs"]:
            cid = npc.get("creature")
            if cid:
                assert cid in ELDER_CREATURES, f"npc creature {cid!r} not in registry"
    print("scene creature keys resolve OK")


def test_global_state_singleton():
    assert isinstance(ELDER_STATE, EldermarkState)
    print("global state singleton OK")


def test_scene_battle_keys_resolve_fully():
    # every scene battle key must be both a battler AND a journal creature, so a
    # win can open the battle and befriend a real, displayable creature
    for s in ELDER_SCENES.values():
        for npc in s["npcs"]:
            bk = npc.get("battle")
            if bk:
                assert bk in ELDER_BATTLERS, f"battle {bk!r} not a battler"
                assert bk in ELDER_CREATURES, f"battle {bk!r} has no journal entry"
    print("scene battle keys resolve fully OK")


def test_state_rejects_unknown_ids():
    s = EldermarkState()
    s.meet("not_a_creature")
    s.befriend("also_fake")
    assert not s.met and not s.friends        # phantom ids never recorded
    print("state rejects unknown ids OK")


def test_persistence_roundtrip():
    s = EldermarkState()
    s.befriend("mossback")
    s.meet("gloomling")
    disk = {}
    s.save_into(disk)
    assert disk["eldermark_friends"] == ["mossback"]
    assert disk["eldermark_met"] == ["gloomling", "mossback"]
    s2 = EldermarkState()
    s2.load(disk)
    assert s2.friends == {"mossback"} and s2.met == {"gloomling", "mossback"}
    # junk ids in stored settings are dropped on load
    s3 = EldermarkState()
    s3.load({"eldermark_met": ["mossback", "junk"], "eldermark_friends": ["junk"]})
    assert s3.met == {"mossback"} and s3.friends == set()
    print("persistence round-trip OK")


if __name__ == "__main__":
    test_state_meet_befriend()
    test_creatures_wellformed()
    test_battlers_have_journal_entries()
    test_scene_creature_keys_resolve()
    test_global_state_singleton()
    test_scene_battle_keys_resolve_fully()
    test_state_rejects_unknown_ids()
    print("JOURNAL TEST PASSED")
