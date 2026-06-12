"""Pet overlay + chat smoke test (window flashes briefly). Run: python test_pet.py"""
import tkinter as tk
import promptmate as pm

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

# Pet resize via scale
pet.set_scale(2)
assert pet.sprites.w == 96 and pet.sprites.h == 104, (pet.sprites.w, pet.sprites.h)
pet.set_scale(1)
assert pet.sprites.w == 192
print("pet resize OK")

# Chat re-flow on width change
pet.toggle_chat()
chat = pet.chat
chat.entry.insert("1.0", "test message for reflow")
chat.send()
chat._deliver_reply(*[chat.last[1], chat.last[2], chat.last[3]])
n_msgs = len(chat.messages)
chat._cw = 600
chat._render_all()
assert len(chat.messages) == n_msgs, "re-flow lost messages"
print(f"chat re-flow OK ({n_msgs} messages redrawn at new width)")
chat.close()

root.destroy()
print("PET SMOKE TEST PASSED")
