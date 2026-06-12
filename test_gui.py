"""GUI smoke test: build the full window, simulate an ask/generate cycle, close.
Run: python test_gui.py
"""
import tkinter as tk
import askpet as pm

root = tk.Tk()
root.withdraw()  # don't flash a window during the test
app = pm.AskPetApp(root)

app.input_text.insert("1.0", "need a powershel scirpt to deply an intune app pakage")
app._recheck_spelling()
misspelled = app.input_text.tag_ranges("misspelled")
print("misspelled tag ranges:", len(misspelled) // 2)

app._ask()
print("destination:", app.rec["destination"])
print("template:", app.rec["template"])
app._generate()
out = app.output_text.get("1.0", "end-1c")
print("generated chars:", len(out))
assert out.startswith("# "), "prompt output missing"

app._copy()
clip = root.clipboard_get()
assert clip == out, "clipboard mismatch"
print("clipboard OK")

app._save()
print("history file exists:", pm.HISTORY_FILE.exists())

root.update_idletasks()
root.destroy()
print("GUI SMOKE TEST PASSED")
