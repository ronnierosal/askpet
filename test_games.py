#!/usr/bin/env python3
"""Game-engine tests for the AskPet arcade — pure logic, no GUI, no Ollama.
Run: python test_games.py"""
import random

import askpet as pm

# every registered game obeys the start()/handle()/is_over contract
for name, cls in pm.GAMES.items():
    g = cls()
    opening = g.start()
    assert isinstance(opening, str) and opening.strip(), name
    assert g.is_over is False, name
    assert isinstance(g.handle("hello"), str), name      # never raises on junk
print(f"contract OK ({len(set(pm.GAMES.values()))} games, {len(pm.GAMES)} names)")

# start_game resolves names/aliases and rejects junk
assert isinstance(pm.start_game("hangman"), pm.Hangman)
assert isinstance(pm.start_game("20q"), pm.TwentyQuestions)
assert isinstance(pm.start_game("quiz"), pm.Trivia)
assert pm.start_game("nope") is None and pm.start_game("") is None
print("registry/aliases OK")

# --- Number Guess: higher/lower + win ---------------------------------------
g = pm.NumberGuess(rng=random.Random(1))
secret = g.secret
assert 1 <= secret <= 100
if secret > 1:
    assert "higher" in g.handle(str(secret - 1))
if secret < 100:
    assert "lower" in g.handle(str(secret + 1))
assert not g.is_over
assert "YES" in g.handle(str(secret)) and g.is_over
# a non-number before winning is tolerated, doesn't end the game
g2 = pm.NumberGuess(rng=random.Random(2))
assert isinstance(g2.handle("banana"), str) and not g2.is_over
print("number guess OK")

# --- Word Scramble: same letters, hint, case-insensitive win ----------------
g = pm.WordScramble(rng=random.Random(3))
assert sorted(g.scrambled) == sorted(g.word)         # only the order changed
assert g.word[0].upper() in g.handle("hint")
assert not g.is_over
assert "YES" in g.handle(g.word.upper()) and g.is_over
print("word scramble OK")

# --- Hangman: reveal, wrong, win, loss, word-guess --------------------------
g = pm.Hangman()
g.word, g.guessed, g.wrong, g.over, g.won = "cat", set(), 0, False, False
assert "_" in g._mask()
g.handle("c"); assert "C" in g._mask()
g.handle("z"); assert g.wrong == 1
g.handle("a"); g.handle("t")
assert g.is_over and g.won
# loss after MAX_WRONG misses
g = pm.Hangman()
g.word, g.guessed, g.wrong, g.over, g.won = "dog", set(), 0, False, False
for ch in "xqkwjv":
    g.handle(ch)
assert g.is_over and not g.won
# a wrong whole-word guess costs a life and is NOT echoed back (safety)
g = pm.Hangman()
g.word, g.guessed, g.wrong, g.over, g.won = "tiger", set(), 0, False, False
bad = g.handle("zzzzz"); assert g.wrong == 1 and "zzzzz" not in bad
assert "YES" in g.handle("tiger") and g.is_over and g.won
print("hangman OK")

# --- 20 Questions: tag yes/no + correct guess + run-out ----------------------
g = pm.TwentyQuestions()
g.secret, g.tags, g.left, g.over, g.won = "dog", {"animal", "pet", "furry"}, 20, False, False
assert "Yes" in g.handle("is it an animal?")
assert "Nope" in g.handle("is it a plant?")
assert "DOG" in g.handle("is it a dog?").upper() and g.is_over and g.won
g = pm.TwentyQuestions()
g.secret, g.tags, g.left, g.over, g.won = "cat", {"animal"}, 1, False, False
assert "CAT" in g.handle("is it big?").upper() and g.is_over   # last question reveals
print("20 questions OK")

# --- Trivia: scoring by letter + by text, finish + grade --------------------
g = pm.Trivia(rng=random.Random(5), pack="space", n=3)
assert len(g.questions) == 3
while not g.is_over:                                   # answer all correctly by letter
    q = g.questions[g.i]
    g.handle(chr(97 + q["answer"]))
assert g.score == 3 and g.is_over
g = pm.Trivia(rng=random.Random(6), pack="animals", n=2)
first = g.questions[0]
g.handle(first["options"][first["answer"]])           # type the answer text
assert g.score == 1
# every pack's answer index is valid and content is non-empty
for packname, qs in pm.TRIVIA_PACKS.items():
    for q in qs:
        assert q["q"].strip() and len(q["options"]) >= 2, packname
        assert 0 <= q["answer"] < len(q["options"]), (packname, q["q"])
print(f"trivia OK ({sum(len(v) for v in pm.TRIVIA_PACKS.values())} questions)")

# 20Q tags are self-consistent: the secret name isn't accidentally a tag
for thing, tags in pm.TWENTYQ_THINGS:
    assert thing not in tags, thing
print("20Q content OK")

# --- Cozy Critter Dungeon: explore, puzzles, befriend, win (deterministic) --
d = pm.CozyDungeon()
assert "DUNGEON" in d.start().upper() and not d.is_over and d.loc == "entrance"
d.handle("go north")                                  # -> hall
assert d.loc == "hall"
assert "lock" in d.handle("go north").lower() and d.loc == "hall"   # door locked
d.handle("go east")                                   # -> library
assert d.loc == "library"
assert "key" in d.handle("talk to mole").lower() and "key" in d.inventory
d.handle("take berry"); assert "berry" in d.inventory
d.handle("go west")                                   # -> hall
unlock = d.handle("use key").lower()
assert "open" in unlock or "click" in unlock or "unlock" in unlock
d.handle("go north")                                  # -> garden (dark, no lantern)
assert d.loc == "garden"
assert "hedgehog" in d.handle("go north").lower() and d.loc == "garden"  # blocked
d.handle("give berry")
assert "berry" not in d.inventory                     # the berry was shared
d.handle("go north")                                  # -> burrow
assert d.loc == "burrow"
win = d.handle("take sunstone")
assert d.is_over and d.won and "WIN" in win.upper()
print("dungeon solve-path OK")

# courage never drops below 0; unknown verbs and inventory are handled kindly
d2 = pm.CozyDungeon(); d2.courage = 0
d2.handle("go north"); assert d2.courage >= 0
unk = d2.handle("flibber the wozzle").lower()
assert "try" in unk or "not sure" in unk
assert "bag" in d2.handle("inventory").lower()
# you cannot win by walking past the puzzles (locked + blocked both hold)
d3 = pm.CozyDungeon()
for cmd in ("go north", "go north", "go north", "go north"):
    d3.handle(cmd)
assert not d3.is_over, "dungeon must not be winnable without solving the puzzle"
print("dungeon guards OK")

# the optional narrator adds one flavor line on a new room and never breaks
d4 = pm.CozyDungeon(narrator=lambda room: "A gentle breeze drifts by.")
assert "gentle breeze" in d4.start()
def _boom(room):
    raise ValueError("nope")
assert isinstance(pm.CozyDungeon(narrator=_boom).start(), str)   # error ignored
print("dungeon narrator hook OK")

# === kid-safety review fixes ================================================
assert pm._strip_article("The Sun") == "sun"
assert pm._strip_article("a dog") == "dog" and pm._strip_article("Milky Way") == "milky way"

# (safety) the dungeon NEVER echoes the kid's raw word back into a reply
d = pm.CozyDungeon()
assert "pizzaface" not in d.handle("go pizzaface").lower()
assert "pizzaface" not in d.handle("take pizzaface").lower()
assert "xyzzy" not in pm.CozyDungeon().handle("take xyzzy").lower()
print("dungeon no-echo OK (safety)")

# trivia: a key word counts ('sun' for 'The Sun'); a digit substring does not
tq = pm.Trivia(rng=random.Random(0))
tq.questions = [{"q": "Closest star?", "options": ["Mars", "The Sun"], "answer": 1},
                {"q": "Spider legs?", "options": ["6", "8"], "answer": 1}]
tq.i, tq.score, tq.over = 0, 0, False
tq.handle("sun");  assert tq.score == 1, "'sun' should count for 'The Sun'"
tq.handle("18");   assert tq.score == 1, "'18' must NOT count as '8'"
assert tq.is_over
# the instructed letter path stays exact
tq2 = pm.Trivia(rng=random.Random(0))
tq2.questions = [{"q": "x", "options": ["A1", "B2"], "answer": 0}]
tq2.i, tq2.score, tq2.over = 0, 0, False
tq2.handle("a"); assert tq2.score == 1
print("trivia matching OK (key-word accept, digit-substring reject)")

# 20Q: negation inverts the yes/no; a guess with trailing words still wins
q = pm.TwentyQuestions()
q.secret, q.tags, q.left, q.over, q.won = "dog", {"animal", "pet"}, 20, False, False
assert "Nope" in q.handle("is it not an animal?")    # was wrongly 'Yes!' before
assert "Yes" in q.handle("is it an animal?")          # plain question still right
q = pm.TwentyQuestions()
q.secret, q.tags, q.left, q.over, q.won = "dog", {"animal"}, 20, False, False
win = q.handle("is it a dog by any chance?")
assert q.is_over and q.won and "DOG" in win.upper()
print("20 questions fixes OK (negation + lenient guess)")

# dungeon _use: a named-but-absent item isn't silently swapped for the lone item
dd = pm.CozyDungeon(); dd.inventory, dd.loc = ["key"], "garden"
r = dd.handle("give berry")
assert "berry" not in dd.inventory and ("don't have" in r.lower() or "bag" in r.lower())
dd2 = pm.CozyDungeon(); dd2.inventory, dd2.loc = ["key"], "hall"
assert any(w in dd2.handle("use").lower() for w in ("open", "click", "unlock"))
print("dungeon use-fallback OK")

print("GAMES TEST PASSED")
