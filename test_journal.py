"""Headless tests for the Creature Journal data + meet/befriend state."""
from askpet import (EldermarkState, ELDER_CREATURES, ELDER_BATTLERS,
                    ELDER_SLICE, ELDER_STATE)


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
    for npc in ELDER_SLICE["npcs"]:
        cid = npc.get("creature")
        if cid:
            assert cid in ELDER_CREATURES, f"npc creature {cid!r} not in registry"
    print("scene creature keys resolve OK")


def test_global_state_singleton():
    assert isinstance(ELDER_STATE, EldermarkState)
    print("global state singleton OK")


if __name__ == "__main__":
    test_state_meet_befriend()
    test_creatures_wellformed()
    test_battlers_have_journal_entries()
    test_scene_creature_keys_resolve()
    test_global_state_singleton()
    print("JOURNAL TEST PASSED")
