"""Pet overlay + chat smoke test (window flashes briefly). Run: python test_pet.py"""
import atexit
import tkinter as tk
import askpet as pm

# This test drives a real PetOverlay, which saves to the REAL settings
# file. Snapshot it and restore on exit (even on assert failure) so a
# test run never changes the user's pet, size, position, or toggles.
_settings_backup = pm.SETTINGS_FILE.read_bytes() if pm.SETTINGS_FILE.exists() else None
atexit.register(lambda: pm.SETTINGS_FILE.write_bytes(_settings_backup)
                if _settings_backup else None)

# Same for the chat-history file: the chat persists its transcript on close, so
# snapshot + clear it (deterministic, and the user's real chat isn't touched).
_chat_backup = pm.CHAT_HISTORY_FILE.read_bytes() if pm.CHAT_HISTORY_FILE.exists() else None
def _restore_chat():
    if _chat_backup is not None:
        pm.CHAT_HISTORY_FILE.write_bytes(_chat_backup)
    elif pm.CHAT_HISTORY_FILE.exists():
        pm.CHAT_HISTORY_FILE.unlink()
atexit.register(_restore_chat)
pm.clear_chat_history()

# ...and the long-term pet-memory file (persona reads it; tests write it).
_mem_backup = pm.PET_MEMORY_FILE.read_bytes() if pm.PET_MEMORY_FILE.exists() else None
def _restore_mem():
    if _mem_backup is not None:
        pm.PET_MEMORY_FILE.write_bytes(_mem_backup)
    elif pm.PET_MEMORY_FILE.exists():
        pm.PET_MEMORY_FILE.unlink()
atexit.register(_restore_mem)
pm.clear_pet_memory()

# ...and the games-state file (the picker persists the age band + RPG progress).
_games_backup = pm.GAMES_STATE_FILE.read_bytes() if pm.GAMES_STATE_FILE.exists() else None
def _restore_games():
    if _games_backup is not None:
        pm.GAMES_STATE_FILE.write_bytes(_games_backup)
    elif pm.GAMES_STATE_FILE.exists():
        pm.GAMES_STATE_FILE.unlink()
atexit.register(_restore_games)

root = tk.Tk()
pet = pm.PetOverlay(root)
# The chat default is now general chat (local AI). Disable local AI so the
# prompt-builder assertions below exercise the deterministic no-Ollama
# fall-back path instead of making live model calls.
pet.local_ai_enabled = False
assert pet.sprites.ok, "spritesheet failed to load"
print("sprites loaded:", sorted(pet.sprites.frames))
print("frame counts:", {k: len(v) for k, v in sorted(pet.sprites.frames.items())})
print("pet size:", pet.sprites.w, "x", pet.sprites.h)

# Run a handful of animation ticks
for _ in range(8):
    root.update()
    root.after(10)
print("anim after ticks:", pet.anim, "frame", pet.frame_i)

# General-chat-by-default routing: local_ai_lane() returns a lane for
# everything (general chat = "answer"), with specialized lanes still winning.
def _lane(msg):
    return pm.local_ai_lane(msg, pm.recommend(pm.clean_text(msg, pet.spell)))
assert _lane("what's the capital of France?") == "answer"
assert _lane("tell me a joke") == "answer"
# execution-flavored tasks are NO LONGER auto-routed to the prompt builder
assert _lane("write a powershell script to deploy an intune app") == "answer"
assert _lane("summarize this: the migration ran long and we rolled back twice") == "summarize"
assert _lane("review this draft: Dear team, the rollout is on track this week") == "review"
assert _lane("rewrite this to be more professional: hey can u send the file") == "rewrite"
assert _lane("write an email to the vendor about the late shipment") == "email"
print("general-chat routing OK (default=answer; specialized lanes still win)")

# the general-chat persona is built from the LOADED pet and switches with it
class _FakePet:
    def __init__(self, name, desc):
        self._name, self.pet_meta = name, {"description": desc}
    def pet_name(self):
        return self._name
godz = pm.persona_system_prompt(_FakePet("Godzilla Blue", "A chibi Godzilla with a blue flame."))
corgi = pm.persona_system_prompt(_FakePet("Biscuit", "A cheerful chibi corgi."))
assert "Godzilla Blue" in godz and "blue flame" in godz
assert "Biscuit" in corgi and "chibi corgi" in corgi
assert godz != corgi, "persona should change with the pet"
assert "you are an ai" in godz.lower(), "persona must keep the no-AI rule"
assert "family-friendly" in godz.lower(), "persona must stay kid-safe"
# the real loaded pet's name is in its persona
assert pet.pet_name() in pm.persona_system_prompt(pet)
print("pet persona OK (in-character, switches with the loaded pet)")

# sprite flipping: the pet faces its direction of travel (move_dx)
pet.sprites.frames["__fliptest"] = ["N"]
pet.sprites.flipped["__fliptest"] = ["F"]
pet.sprites.facing["__fliptest"] = 1          # native facing: right
pet.anim = "__fliptest"
pet.move_dx = 5;  assert pet._display_frames() == ["N"]   # moving right, native right
pet.move_dx = -5; assert pet._display_frames() == ["F"]   # moving left  -> mirror
pet.move_dx = 0;  assert pet._display_frames() == ["N"]   # stationary   -> no mirror
pet.sprites.facing["__fliptest"] = -1         # native facing: left
pet.move_dx = -5; assert pet._display_frames() == ["N"]
pet.move_dx = 5;  assert pet._display_frames() == ["F"]
del pet.sprites.frames["__fliptest"]
pet.sprites.flipped.pop("__fliptest"); pet.sprites.facing.pop("__fliptest")
pet.anim = "idle"; pet.move_dx = 0
# every real animation has a mirrored set of equal length + a known facing
assert pet.sprites.flipped, "no mirrored frame sets were built (PIL missing?)"
for _n, _fr in pet.sprites.frames.items():
    assert _n in pet.sprites.flipped and len(pet.sprites.flipped[_n]) == len(_fr), _n
    assert pet.sprites.facing.get(_n) in (1, -1), _n
# manifest "facing" override is honored (Godzilla Blue's walk_right art faces left)
if pet.pet_id == "godzilla-blue":
    assert pet.sprites.facing.get("walk_right") == -1
    assert pet.sprites.facing.get("walk_left") == 1
print("sprite flip OK (faces travel direction; mirrored sets built)")

# install_pet stamps known per-pet facing corrections into the manifest so a
# re-download keeps Godzilla Blue facing the right way (its walk_right/run art
# is drawn facing left). This is the write-side fix; PetSprites already reads it.
_anims = {"idle": {"row": 0, "frames": 6}, "walk_right": {"row": 1, "frames": 8},
          "walk_left": {"row": 2, "frames": 8}, "run": {"row": 4, "frames": 5}}
pm.apply_facing_overrides("godzilla-blue", _anims)
assert _anims["walk_right"]["facing"] == "left"
assert _anims["walk_left"]["facing"] == "right"
assert _anims["run"]["facing"] == "left"
assert "facing" not in _anims["idle"], "untouched animations should stay as-is"
# a pet with no override entry is left exactly as built; missing rows are skipped
_plain = {"walk_right": {"row": 1, "frames": 8}}
pm.apply_facing_overrides("some-other-pet", _plain)
assert "facing" not in _plain["walk_right"]
_partial = {"idle": {"row": 0, "frames": 6}}   # godzilla sheet missing walk/run rows
pm.apply_facing_overrides("godzilla-blue", _partial)
assert _partial == {"idle": {"row": 0, "frames": 6}}, "absent rows must not be invented"
print("facing override OK (install_pet stamps known corrections)")

# Open chat and run a full send cycle
pet.toggle_chat()
assert pet.chat.is_open()
pet.chat.entry.insert("1.0", "write a jirra ticket for the o365 license cleanup")
pet.chat.send()
raw, cleaned, rec, prompt = pet.chat.last
print("cleaned:", cleaned)
print("destination label:", pm.DEST_LABELS[rec["destination"]])
assert "Jira" in cleaned and "Microsoft 365" in cleaned
assert prompt.startswith("# ")
assert "ChatGPT or Claude" in prompt

pet.chat._copy_last()
assert root.clipboard_get() == prompt
print("clipboard OK, prompt chars:", len(prompt))

# Behavior while chat open should settle to sit
pet._choose_behavior()
assert pet.anim == "sit", pet.anim
pet.chat.close()
root.update()
pet._choose_behavior()
print("behavior after close:", pet.anim)

# Editor opens prefilled
pet.open_editor(prefill=raw)
assert pet.editor.rec is not None
print("editor destination:", pet.editor.rec["destination"])

# Pet resize via scale (default is medium = scale 2)
pet.set_scale(1)
assert pet.sprites.w == 192 and pet.sprites.h == 208, (pet.sprites.w, pet.sprites.h)
pet.set_scale(2)  # leave settings at the medium default
assert pet.sprites.w == 96
print("pet resize OK")

# Saving settings must derive scale from live state, not the launch dict
pet.settings["pet_scale"] = 1  # simulate stale in-memory value
pet._save_settings()
saved = pm.load_json(pm.SETTINGS_FILE, {})
assert saved["pet_scale"] == pet.scale == 2, saved.get("pet_scale")
print("settings save uses live state OK")

# the once-per-version update nudge must persist across launches (it lives in
# the _save_settings allowlist, else the prompt re-fires on every startup)
pet.settings["update_seen"] = "v9.9.9"
pet._save_settings()
assert pm.load_json(pm.SETTINGS_FILE, {}).get("update_seen") == "v9.9.9"
print("update_seen persists OK")

# Sleepy animation must crawl, not cycle (distinct poses, not a loop)
assert pet.FRAME_HOLD.get("sleepy", 1) >= 10
print("sleepy frame hold OK")

# Nap when ignored, wake on interaction
pet.chat and pet.chat.close()
pet.idle_ticks = pet.NAP_AFTER_TICKS + 1
pet._choose_behavior()
assert pet.anim == "sleepy", pet.anim
class FakeEvent: x_root = 0; y_root = 0
pet._on_press(FakeEvent())
assert pet.anim == "wave" and pet.idle_ticks == 0
pet._press_xy = None
print("nap/wake OK")

# Celebrate resets idle and emotes
pet.idle_ticks = 500
pet.celebrate()
assert pet.anim == "emote" and pet.idle_ticks == 0
print("celebrate OK")

# Follow-up question flow: short fix-it message triggers questions
pet.toggle_chat()
chat = pet.chat
chat.entry.insert("1.0", "outlok keeps crashing")
chat.send()
assert chat.pending is not None, "expected clarifying questions for short fix-it"
assert chat.last is None
chat.entry.insert("1.0", "just one user, since yesterday")
chat.send()
assert chat.pending is not None and chat.pending["qi"] == 1
chat.entry.insert("1.0", "no error message, nothing changed recently")
chat.send()
assert chat.pending is None, "Q&A should be finished"
assert chat.last is not None
raw2, cleaned2, rec2, prompt2 = chat.last
assert "fixit" in rec2["topics"], rec2["topics"]
assert rec2["template"] == "troubleshoot", rec2["template"]
assert "one user" in prompt2, "answer context missing from prompt"
print("follow-up Q&A OK -> template:", rec2["template"])

# "skip" bails out of questioning and still generates
chat.entry.insert("1.0", "printer help")
chat.send()
assert chat.pending is not None
chat.entry.insert("1.0", "skip")
chat.send()
assert chat.pending is None and chat.last is not None
print("skip flow OK")

# Help questions get knowledge-base answers, not generated prompts
n_before = len(chat.messages)
chat.entry.insert("1.0", "what makes a good prompt?")
chat.send()
chat._deliver_help(pm.answer_help_question("what makes a good prompt?"))
assert chat.pending is None, "help question should not trigger Q&A"
assert any("GOAL" in (m[1] or "") for m in chat.messages[n_before:]), "expected best-practices answer"
assert pm.answer_help_question("how do i do a handoff to a new chat?") is not None
assert pm.answer_help_question("when should i clear context and start fresh?") is not None
assert pm.answer_help_question("what can you do?") is not None
# Task requests must NOT be hijacked by the help KB
assert pm.answer_help_question("write a prompt for an intune deployment") is None
assert pm.answer_help_question("explain how conditional access works in simple terms") is None
print("help knowledge base OK")

# Clickable module/skill chips appear after the reply and show their text
chat._deliver_reply(chat.last[1], chat.last[2], chat.last[3])
chip_msgs = [m for m in chat.messages if m[0] == "chips"]
assert chip_msgs, "no chips message in reply"
chips = chip_msgs[-1][1]
assert any(c["kind"] == "module" for c in chips)
n_before = len(chat.messages)
chat._show_item(chips[0])
assert len(chat.messages) == n_before + 1, "clicking a chip should add a bubble"
assert chat.messages[-1][1].startswith(pm.AGENT_MODULES[chips[0]["key"]]["name"])
print(f"chips OK ({len(chips)} chips, click shows text)")

# Chat re-flow on width change
n_msgs = len(chat.messages)
chat._cw = 600
chat._render_all()
assert len(chat.messages) == n_msgs, "re-flow lost messages"
print(f"chat re-flow OK ({n_msgs} messages redrawn at new width)")

# Theme switching: resolve, live apply, and persistence
assert pm.resolve_chat_theme("light") is pm.CHAT_THEMES["light"]
assert pm.resolve_chat_theme("dark") is pm.CHAT_THEMES["dark"]
assert pm.resolve_chat_theme("auto") in (pm.CHAT_THEMES["light"], pm.CHAT_THEMES["dark"])
assert pm._lerp_color("#101820", "#ffffff", 0.0) == "#101820"
assert pm._lerp_color("#101820", "#ffffff", 1.0) == "#ffffff"
n_msgs = len(chat.messages)
pet.set_chat_theme("dark")
assert chat.t is pm.CHAT_THEMES["dark"], "live theme apply did not swap palette"
assert len(chat.messages) == n_msgs, "theme re-flow lost messages"
assert pm.load_json(pm.SETTINGS_FILE, {}).get("chat_theme") == "dark"
pet.set_chat_theme("light")
assert chat.t is pm.CHAT_THEMES["light"]
print("chat theme switch OK (resolve + live apply + persist)")

# Chat text size: persists, clamps, and live-applies (font accessor + reflow)
n_msgs = len(chat.messages)
pet.set_chat_text_size(16)
assert pm.load_json(pm.SETTINGS_FILE, {}).get("chat_text_size") == 16
assert chat.chat_text_size == 16 and chat._bubble_font() == ("Segoe UI", 16)
assert chat._caption_font() == ("Segoe UI", 14)
assert len(chat.messages) == n_msgs, "text-size reflow lost messages"
pet.set_chat_text_size(999)   # clamps to the max
assert chat.chat_text_size == 18
pet.set_chat_text_size(10)    # restore default
print("chat text size OK (persist + clamp + live reflow)")

# Games: /games opens the interactive picker, /play starts a game, in-game
# moves route to the game, quit returns to chat, and a win clears the game.
# Pin an age band so the picker skips its first-run age screen (deterministic).
pm.set_games_age_band("kid")
chat.active_game = None
chat.entry.insert("1.0", "/games"); chat.send()
assert isinstance(chat.active_game, pm.GamePicker), "/games should open the picker"
assert chat.messages[-1][0] == "game", "the picker screen is a 'game'-role message"
assert "Type a number to pick" in (chat.messages[-1][1] or ""), "picker menu not shown"
chat.entry.insert("1.0", "/play hangman"); chat.send()   # a /command still routes mid-picker
assert isinstance(chat.active_game, pm.Hangman), "hangman didn't start"
assert chat.messages[-1][0] == "game", "the game's opening screen replies as 'game'"
_g = chat.active_game
chat.entry.insert("1.0", "e"); chat.send()        # a plain move routes to the game
assert chat.active_game is _g, "a move shouldn't end the game"
assert chat.messages[-1][0] == "game", "an in-game move replies as 'game', not 'pet'"
chat.entry.insert("1.0", "quit"); chat.send()     # 'quit' returns to normal chat
assert chat.active_game is None, "quit should end the game"
assert chat.messages[-1][0] == "pet", "quitting says goodbye as the pet"
chat.entry.insert("1.0", "/play dragons"); chat.send()   # unknown name -> picker, not None
assert isinstance(chat.active_game, pm.GamePicker), "an unknown game should open the picker"
chat.active_game = pm.NumberGuess(); chat.active_game.secret = 42
chat.entry.insert("1.0", "42"); chat.send()       # winning clears the game
assert chat.active_game is None, "a finished game should clear itself"
assert chat.messages[-1][0] == "caption", "a finished game leaves a 'play again' caption"
print("games integration OK (/games picker, /play, moves, quit, win clears)")

# Slim custom scrollbar replaced the ttk one and speaks the scrollbar protocol
assert isinstance(chat._scroll, pm.SlimScrollbar), type(chat._scroll)
chat._scroll.set(0.0, 0.5)   # partial view -> thumb drawn
chat._scroll.set(0.0, 1.0)   # everything fits -> no thumb
print("slim scrollbar OK")

# Click-outside-closes must NOT fire while the pet's right-click menu is up
pet._menu_open = True
chat._check_close()
assert chat.is_open(), "chat auto-closed while the context menu was open"
pet._menu_open = False
print("click-outside-close menu guard OK")

# ...and must NOT fire while a local-AI answer is still streaming (else a
# focus blip during a 20s gemma generation would discard the in-progress reply)
chat._ai_busy = True
chat._check_close()
assert chat.is_open(), "chat auto-closed mid local-AI answer"
chat._ai_busy = False
print("click-outside-close ai-busy guard OK")

chat.close()

# --- chat history: persist on close, restore on open, clearable -------------
pm.clear_chat_history()
assert pm.load_chat_history() == []
pm.append_chat_messages([("user", "hello there"),
                         ("pet", "hi! how can i help?"),
                         ("prompt", "# A previously built prompt")])
assert pm.load_chat_history() == [("user", "hello there"),
                                  ("pet", "hi! how can i help?"),
                                  ("prompt", "# A previously built prompt")]
# a fresh open shows the saved transcript above a "new chat" divider + greeting
pet.toggle_chat()
ch = pet.chat
assert ("user", "hello there") in ch.messages
assert ("histprompt", "# A previously built prompt") in ch.messages, \
    "a saved prompt should load read-only as 'histprompt' (no action buttons)"
assert any(k == "caption" and "new chat" in (t or "") for k, t in ch.messages)
assert ch._session_start == len(ch.messages), "session starts after the greeting"
# loaded history is NOT re-persisted; a new message IS, on close
before = len(pm.load_chat_history())
ch._add("user", "a brand new question")
ch.close()
after = pm.load_chat_history()
assert len(after) == before + 1, (before, len(after))
assert after[-1] == ("user", "a brand new question")
# clear wipes it; clear_view resets an open window to a fresh chat
pet.toggle_chat()
ch = pet.chat
pm.clear_chat_history()
ch.clear_view()
assert pm.load_chat_history() == []
assert not any(t == "hello there" for _, t in ch.messages), "view not reset"
assert ch.messages[-1] == ("pet", pm.CHAT_GREETING)
ch.close()
pm.clear_chat_history()
print("chat history OK (persist on close, restore on open, clear)")

# age-pruning drops messages older than the retention window
pm.clear_chat_history()
pm.save_json(pm.CHAT_HISTORY_FILE, [
    {"ts": "2000-01-01T00:00:00", "kind": "user", "text": "ancient"},
    {"ts": pm.datetime.now().isoformat(timespec="seconds"), "kind": "user", "text": "recent"},
])
assert pm.prune_chat_history(24) == 1
assert pm.load_chat_history() == [("user", "recent")]
print("chat history age-prune OK")

# a still-streaming answer and the pet-switch greeting are NOT persisted
pm.clear_chat_history()
pet.toggle_chat()
ch = pet.chat
ch._add("user", "a real question")
ch._add("pet", pm.PETSWITCH_GREETING)   # synthetic UI greeting
ch._add("pet", "partial answ")           # pretend this is a live stream buffer
ch._ai_busy = True
ch._ai_req = {"msg_index": len(ch.messages) - 1}
ch._persist_session()
ch._ai_busy = False
ch._ai_req = None
saved = pm.load_chat_history()
assert ("user", "a real question") in saved
assert ("pet", pm.PETSWITCH_GREETING) not in saved, "pet-switch greeting persisted"
assert ("pet", "partial answ") not in saved, "mid-stream partial persisted"
ch.close()
pm.clear_chat_history()
print("chat history exclusions OK (mid-stream + pet-switch greeting)")

# --- pet memory: long-term (remembers you) + short-term (conversation) ------
# capture intent: explicit marker OR personal lead; reject casual/ambiguous
assert pm.remember_fact("remember that my name is Mia") == "my name is Mia"
assert pm.remember_fact("remember I have a cat") == "I have a cat"
assert pm.remember_fact("don't forget my dog is named Rex") == "my dog is named Rex"
assert pm.remember_fact("remember: we live in Ohio") == "we live in Ohio"
assert pm.remember_fact("remember the good old days") is None   # casual, no intent
assert pm.remember_fact("remember to call mom") is None         # a task
assert pm.remember_fact("remember whatever you want") is None   # not personal/marked
assert pm.remember_fact("what's your favorite food?") is None   # normal chat
# the canned confirmations are ephemeral (won't persist or feed back as memory)
assert pm.REMEMBER_ACK in pm.EPHEMERAL_PET_TEXTS
assert pm.REMEMBER_DUP in pm.EPHEMERAL_PET_TEXTS
# facts are normalized: internal newlines/whitespace collapsed
pm.clear_pet_memory()
pm.add_pet_memory("I like\n  swimming")
assert pm.load_pet_memory() == ["I like swimming"]
pm.clear_pet_memory()
assert pm.add_pet_memory("my name is Mia") is True
assert pm.add_pet_memory("My name is Mia.") is False        # dedup (case/punct)
assert pm.add_pet_memory("I love dinosaurs") is True
assert pm.load_pet_memory() == ["my name is Mia", "I love dinosaurs"]
sysp = pm.persona_system_prompt(pet)
assert "my name is Mia" in sysp and "I love dinosaurs" in sysp, "facts not in persona"
pm.clear_pet_memory()
assert pm.load_pet_memory() == []
assert "I love dinosaurs" not in pm.persona_system_prompt(pet)
# a "remember …" message is captured (stored + confirmed), not sent to the model
pet.toggle_chat()
ch = pet.chat
ch.entry.insert("1.0", "remember that my favorite color is blue")
ch.send()
assert "my favorite color is blue" in pm.load_pet_memory()
assert ch.last is None and ch.pending is None
assert ch.messages[-1][0] == "pet" and "remember" in ch.messages[-1][1].lower()
# short-term: recent turns map to roles; the current message is excluded
ch._add("user", "what's 2+2?"); ch._add("pet", "Four!")
ch._add("user", "and 3+3?")  # current (last) message
hist = ch._recent_history()
assert {"role": "user", "content": "what's 2+2?"} in hist
assert {"role": "assistant", "content": "Four!"} in hist
assert all(h["content"] != "and 3+3?" for h in hist), "current msg leaked into history"
assert all(h["role"] in ("user", "assistant") for h in hist)
ch.close()
pm.clear_pet_memory()
print("pet memory OK (remember/recall + conversation history)")

root.destroy()
print("PET SMOKE TEST PASSED")
