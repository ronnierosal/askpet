"""Visual check of the chat: drive a follow-up Q&A conversation, screenshot. Dev only (uses Pillow)."""
import tkinter as tk
import askpet as pm
from PIL import ImageGrab

root = tk.Tk()
pet = pm.PetOverlay(root)
pet.toggle_chat()
chat = pet.chat


def step(text, delay, then):
    def go():
        chat.entry.insert("1.0", text)
        chat.send()
        root.after(delay, then)
    return go


def grab():
    root.update()
    chat.canvas.yview_moveto(0.0)  # show the conversation from the top
    root.update()
    w = chat.win
    x, y = w.winfo_rootx(), w.winfo_rooty()
    img = ImageGrab.grab((x, y, x + w.winfo_width(), y + w.winfo_height()))
    img.save("chat-screenshot.png")
    print("screenshot saved")
    root.destroy()


# short fix-it message -> question -> answer -> question -> answer -> prompt
s3 = step("no error message, but we got a windows update last night", 1500, grab)
s2 = step("just one user, started this morning", 1200, s3)
s1 = step("outlok keeps crashing", 1200, s2)
root.after(400, s1)
root.mainloop()
