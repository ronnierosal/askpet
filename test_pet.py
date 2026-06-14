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

root = tk.Tk()
pet = pm.PetOverlay(root)
assert pet.sprites.ok, "spritesheet failed to load"
print("sprites loaded:", sorted(pet.sprites.frames))
print("frame counts:", {k: len(v) for k, v in sorted(pet.sprites.frames.items())})
print("pet size:", pet.sprites.w, "x", pet.sprites.h)

# Run a handful of animation ticks
for _ in range(8):
    root.update()
    root.after(10)
print("anim after ticks:", pet.anim, "frame", pet.frame_i)

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

# Click-outside-closes must NOT fire while the pet's right-click menu is up
pet._menu_open = True
chat._check_close()
assert chat.is_open(), "chat auto-closed while the context menu was open"
pet._menu_open = False
print("click-outside-close menu guard OK")

chat.close()

root.destroy()
print("PET SMOKE TEST PASSED")
