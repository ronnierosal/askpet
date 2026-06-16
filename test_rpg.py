#!/usr/bin/env python3
"""Headless tests for the story-driven game layer (Eldermark RPG + profiles +
atomic saves + DDA). No GUI, no Ollama, no network. Profiles are redirected to
a throwaway temp dir so a test run never touches real saves.

Run: python test_rpg.py
"""
import os
import random
import tempfile

# Point AskPet's data dir at a throwaway temp dir BEFORE importing the app, so
# DATA_DIR / GAME_PROFILES_DIR resolve under temp. (AskPet uses LOCALAPPDATA on
# Windows, ~/.local/share or ~/Library elsewhere.)
_TMP = tempfile.mkdtemp()
os.environ["LOCALAPPDATA"] = _TMP
os.environ["HOME"] = _TMP
os.environ["XDG_DATA_HOME"] = os.path.join(_TMP, ".local", "share")

import askpet as pm  # noqa: E402

# Force the profiles dir under temp regardless of how DATA_DIR was computed.
from pathlib import Path  # noqa: E402
pm.GAME_PROFILES_DIR = Path(_TMP) / "askpet-games" / "profiles"
pm.GAME_PROFILES_DIR.mkdir(parents=True, exist_ok=True)


def _files():
    return sorted(p.name for p in pm.GAME_PROFILES_DIR.glob("*"))


# --- every registered game obeys the start()/handle()/is_over contract -------
for name, cls in pm.GAMES.items():
    g = cls()
    opening = g.start()
    assert isinstance(opening, str) and opening.strip(), name
    assert g.is_over is False, name
    assert isinstance(g.handle("hello"), str), name        # never raises on junk
    assert isinstance(g.handle("2"), str), name
print(f"contract OK ({len(set(pm.GAMES.values()))} games, {len(pm.GAMES)} names)")

# the contract sweep must NOT have created any profile files (no write on the
# picker screen or on junk input)
assert _files() == [], f"contract sweep wrote files: {_files()}"
print("no-write-on-contract OK")

# registry resolves the new names/aliases
assert isinstance(pm.start_game("eldermark"), pm.EldermarkRPG)
assert isinstance(pm.start_game("rpg"), pm.EldermarkRPG)
assert isinstance(pm.start_game("math"), pm.MathQuest)
assert pm.start_game("nope") is None
print("registry/aliases OK")

# --- profile create / load roundtrip ----------------------------------------
p = pm.create_game_profile("Test Kid")
p["games"]["eldermark"]["level"] = 4
p["points"] = 120
assert pm.save_game_profile(p)
again = pm.load_game_profile(p["profile_id"])
assert again is not None
assert again["games"]["eldermark"]["level"] == 4 and again["points"] == 120
print("profile roundtrip OK")

# same display name -> unique ids (never clobber another kid)
a = pm.create_game_profile("Sam")
b = pm.create_game_profile("Sam")
assert a["profile_id"] != b["profile_id"]
print("unique profile ids OK")

# --- crash recovery: a corrupt main must NOT destroy the good .bak ----------
p = pm.create_game_profile("Recover Kid")
p["points"] = 42
pm.save_game_profile(p)            # v1 good
p["points"] = 43
pm.save_game_profile(p)            # v2 good; .bak now holds v1 (good)
path = pm.GAME_PROFILES_DIR / f"{p['profile_id']}.json"
bak = path.with_name(path.name + ".bak")
with open(path, "w", encoding="utf-8") as f:
    f.write("{ this is not valid json")   # main is now corrupt
# The fix: because main no longer parses, the next save must leave .bak alone.
p["points"] = 44
pm.save_game_profile(p)            # writes v3 to main; must preserve good .bak
assert pm._read_profile_file(bak) is not None, "good .bak was clobbered by corrupt main"
assert pm.load_game_profile(p["profile_id"])["points"] == 44   # main recovered to v3
# and if main were unreadable, load still falls back to the backup
with open(path, "w", encoding="utf-8") as f:
    f.write("{ broken again")
recovered = pm.load_game_profile(p["profile_id"])
assert recovered is not None, "no recovery from .bak"
print("crash recovery OK (.bak preserved, fallback works)")

# --- deep forward-fill: a save missing a newer field gets the default -------
p = pm.create_game_profile("Old Save")
del p["games"]["eldermark"]["hp_max"]          # simulate a pre-hp_max save
del p["games"]["science"]                       # simulate a missing whole mode
pm.save_game_profile(p)
loaded = pm.load_game_profile(p["profile_id"])
assert loaded["games"]["eldermark"]["hp_max"] == 30   # field back-filled
assert "science" in loaded["games"]                   # whole mode back-filled
print("deep forward-fill OK")

# --- list_profiles skips stray/partial files instead of crashing ------------
import json  # noqa: E402
with open(pm.GAME_PROFILES_DIR / "junk.json", "w", encoding="utf-8") as f:
    f.write("{ not json at all")
with open(pm.GAME_PROFILES_DIR / "noid.json", "w", encoding="utf-8") as f:
    json.dump({"display_name": "no id here"}, f)
rows = pm.list_game_profiles()           # must not raise
assert all(len(r) == 3 and r[0] for r in rows)
print(f"list_profiles robust OK ({len(rows)} valid profiles, junk skipped)")

# --- DDA eases after losses, never goes harder ------------------------------
dda = {"recent": [], "tier": "normal"}
for _ in range(5):
    pm.record_result(dda, won=False)
assert dda["tier"] == "easy" and pm.difficulty_mult(dda) < 1.0
for _ in range(8):                       # a winning streak: caps at normal
    pm.record_result(dda, won=True)
assert dda["tier"] == "normal" and pm.difficulty_mult(dda) == 1.0
print("DDA OK (eases on losses, capped at normal)")

# --- level-up carries the XP remainder (none silently lost) -----------------
g = {"level": 1, "xp": 0, "hp": 30, "hp_max": 30, "abilities": ["strike", "guard"]}
g["xp"] = 72                              # threshold at L1 is 50
msgs = pm._maybe_level_up(g)
assert g["level"] == 2 and g["xp"] == 22, (g["level"], g["xp"])   # 72-50 carried
assert "focus" in g["abilities"]         # learned at level 2
# a huge XP dump levels multiple times without losing the remainder
g2 = {"level": 1, "xp": 0, "hp": 30, "hp_max": 30, "abilities": ["strike", "guard"]}
g2["xp"] = 50 + 100 + 7                   # L1->2 (50), L2->3 (100), 7 left
pm._maybe_level_up(g2)
assert g2["level"] == 3 and g2["xp"] == 7
print("level-up XP carry OK")

# --- combat outcomes are deterministic at the branch level ------------------
rpg = pm.EldermarkRPG()
rpg.prof = pm.create_game_profile("Combat Kid")
gg = rpg.prof["games"]["eldermark"]
# win branch: enemy on its last legs, a Strike finishes it -> xp + cleared flag
rpg.enemy = {"key": "gloomling", "name": "Gloomling", "hp": 1, "hp_max": 16,
             "atk": 4, "xp": 22, "win": "scatters", "boss": False}
rpg.state = "battle"
out = rpg._battle_turn("strike")
assert gg["xp"] == 22 and rpg.state == "play" and "cleared:0" in gg["flags"]
assert any(a["id"] == "brave_heart" for a in rpg.prof["achievements"])
print("combat win branch OK")

# lose branch: a big hit can never knock the player below 1 hp
rpg.enemy = {"key": "mire-warden", "name": "Mire Warden", "hp": 999, "hp_max": 999,
             "atk": 999, "xp": 60, "win": "smiles", "boss": True}
rpg.state = "battle"
gg["hp"] = 1
before = rpg.prof["points"]
out = rpg._battle_turn("strike")          # attack, then take the unwinnable hit
assert gg["hp"] >= 1 and rpg.state == "play"
assert rpg.prof["points"] >= before       # consolation points, never punished
print("combat lose floor OK (knocked down, not out)")

# --- a full scripted playthrough never raises and reaches the Wayshrine -----
rpg = pm.EldermarkRPG()
rpg.start()
# pick "New scout" (last option), then name, then play
new_n = len(rpg._profiles) + 1
assert "name" in rpg.handle(str(new_n)).lower()
rpg.handle("Hero")
assert rpg.state == "play" and rpg.prof is not None

random.seed(7)
steps, won = 0, False
while steps < 400 and not won:
    steps += 1
    if rpg.state == "play":
        # prefer "Look around" (gifts) then always "Press onward" (== option 1)
        labels = [lbl.lower() for _, lbl in rpg._opts]
        pick = next((i + 1 for i, l in enumerate(labels) if "look" in l), 1)
        rpg.handle(str(pick))
    elif rpg.state == "battle":
        labels = [lbl.lower() for _, lbl in rpg._opts]
        # heal if hurt and a berry is offered, else hit with the strongest move
        hurt = rpg.prof["games"]["eldermark"]["hp"] <= 8
        heal = next((i + 1 for i, l in enumerate(labels) if "berry" in l), None)
        if hurt and heal:
            rpg.handle(str(heal))
        else:
            atk = next((i + 1 for i, l in enumerate(labels)
                        if "guard" not in l and "slip" not in l and "berry" not in l), 1)
            rpg.handle(str(atk))
    won = any(a["id"] == "wayshrine_relit" for a in rpg.prof["achievements"])
assert won, f"did not finish in {steps} steps (state={rpg.state})"
assert rpg.prof["games"]["eldermark"]["level"] >= 2
# progress persisted to disk
reloaded = pm.load_game_profile(rpg.prof["profile_id"])
assert any(a["id"] == "wayshrine_relit" for a in reloaded["achievements"])
print(f"full playthrough OK (won in {steps} steps, level "
      f"{rpg.prof['games']['eldermark']['level']})")

# --- the four built-out games: contract + fuzz (no crash, no echo, endless) --
_RUDE = "you are a zzqxrude meanie"
_FUZZ = ["", "hello", "1", "2", "3", "4", "5", "6", "0", "-1", "99", "abc",
         "a", "b", "c", "A", "yes", "  ", "1000000", _RUDE, "3.5", "🙂"]
for key, cls in (("critters", pm.CritterKeepers), ("spin", pm.SpinLeague),
                 ("wild", pm.WildTrails), ("science", pm.ScienceLab)):
    assert isinstance(pm.start_game(key), cls)            # registry resolves it
    for seed in range(40):
        random.seed(seed)                                 # vary each game's RNG
        ir = random.Random(seed * 7 + 1)                  # independent input picker
        g = cls()
        assert isinstance(g.start(), str) and g.is_over is False
        for _ in range(100):
            out = g.handle(ir.choice(_FUZZ))
            assert isinstance(out, str)
            assert "zzqxrude" not in out.lower()          # never echoes kid input
            assert g.is_over is False                     # always-progress, never ends
print("built-out games OK (contract + fuzz + no-echo + endless)")

# --- age band + unlock gating -----------------------------------------------
pm.save_games_state({"age_band": None, "rpg_completed": 0})     # reset (determinism)
assert pm.games_age_band() is None and pm.age_difficulty() == 1.0
pm.set_games_age_band("little")
assert pm.games_age_band() == "little" and pm.age_difficulty() < 1.0   # younger=easier
pm.save_games_state({"age_band": "little", "rpg_completed": 0})
for _ in range(pm.RPG_UNLOCK_THRESHOLD):
    assert pm.games_unlocked() is False                        # locked until enough
    pm.record_rpg_completion()
assert pm.games_unlocked() is True                             # unlocked at threshold
print("age + unlock gating OK")

# --- game picker: age-first, RPG group on top, locks, number-pick -----------
pm.save_games_state({"age_band": None, "rpg_completed": 0})     # fresh player
gp = pm.GamePicker()
op = gp.start()
assert "How old" in op and gp.pick is None                     # asks age first
assert gp.handle("nope") and gp.pick is None                   # junk on age -> reprompt
menu = gp.handle("2")                                          # choose an age band
assert "RPG ADVENTURES" in menu and gp.pick is None
gp.handle("1")
assert gp.pick == "eldermark"                                  # 1 = first RPG adventure
# a locked (non-RPG) game won't start while RPG quests are unfinished
gp2 = pm.GamePicker(); gp2.start()
locked_n = next(i + 1 for i, (_k, _c, lk) in enumerate(gp2._order) if lk)
out = gp2.handle(str(locked_n))
assert gp2.pick is None and "lock" in out.lower()
# once enough RPG quests are done, nothing is locked
pm.save_games_state({"age_band": "kid", "rpg_completed": pm.RPG_UNLOCK_THRESHOLD})
gp3 = pm.GamePicker(); gp3.start()
assert all(lk is False for (_k, _c, lk) in gp3._order)
print("game picker OK (age-first + RPG group + locks)")

# --- the 3 new RPG quests: contract + fuzz + winnable + records completion ----
pm.save_games_state({"age_band": "kid", "rpg_completed": 0})
for cls in (pm.TideHollowRPG, pm.EmberPeakRPG, pm.FrostfallRPG):
    assert getattr(cls, "rpg", False) is True
    for seed in range(30):
        random.seed(seed)
        ir = random.Random(seed * 5 + 1)
        g = cls()
        assert isinstance(g.start(), str) and g.is_over is False
        for _ in range(80):
            out = g.handle(ir.choice(_FUZZ))
            assert isinstance(out, str) and "zzqxrude" not in out.lower()
            assert g.is_over is False
    random.seed(1)
    g = cls(); g.start()
    won, steps = False, 0
    while steps < 400 and not won:
        steps += 1
        labels = [l.lower() for _, l in g._opts]
        if g.state == "battle":
            pick = next((i + 1 for i, l in enumerate(labels) if "guard" not in l
                         and "slip" not in l and "heal" not in l), 1)
        else:
            pick = next((i + 1 for i, l in enumerate(labels) if "look" in l), 1)
        g.handle(str(pick))
        won = "won" in g.flags
    assert won, f"{cls.__name__} not winnable"
assert pm.rpg_completed_count() == 3                           # each win counted once
print("RPG quests OK (fuzz + winnable + completion recorded)")

# --- Math Quest: tiers, every generated problem is correct, always-progress --
import random as _rnd  # noqa: E402
for tier in ("sprouts", "saplings", "oaks"):
    rng = _rnd.Random(99)
    for _ in range(400):
        q, a = pm._make_math_problem(tier, rng)
        assert isinstance(a, int) and a >= 0, (tier, q, a)
        expr = q.replace("−", "-").replace("×", "*").replace("÷", "//")
        assert eval(expr) == a, (tier, q, a)            # the answer is correct
mq = pm.MathQuest()
assert "Pick your level" in mq.start() and mq.is_over is False
assert mq.handle("nope") and mq.tier is None            # junk -> reprompt, no tier
mq.handle("1")
assert mq.tier == "sprouts" and mq.state == "play" and mq.weeds > 0
# a correct answer zaps a weed and scores; a wrong answer still scores, no crash
q, a = mq.prob
w0, s0 = mq.weeds, mq.score
mq.handle(str(a))
assert mq.score > s0 and mq.weeds == w0 - 1
q, a = mq.prob
s1, f1 = mq.score, mq.flowers
out = mq.handle(str(a + 1))                              # deliberately wrong
assert isinstance(out, str) and mq.score > s1 and mq.flowers == f1 - 1
assert mq.is_over is False                               # never ends on a miss
# flowers never get stuck at 0 (a depleted meadow replants)
mq.flowers = 1
q, a = mq.prob
mq.handle(str(a + 1))
assert mq.flowers == 5
print("math quest OK")

print("RPG TEST PASSED")
