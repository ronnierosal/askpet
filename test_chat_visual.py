"""Visual check of the iMessage-style chat: render, send, screenshot. Dev only (uses Pillow)."""
import tkinter as tk
import promptmate as pm
from PIL import ImageGrab

root = tk.Tk()
pet = pm.PetOverlay(root)
pet.toggle_chat()
chat = pet.chat
chat.entry.insert("1.0", "need a powershel scirpt to deply an intune app to pilot grp")
chat.send()

def grab():
    chat.canvas.yview_moveto(0.0)  # show the top of the conversation
    root.update()
    w = chat.win
    x, y = w.winfo_rootx(), w.winfo_rooty()
    img = ImageGrab.grab((x, y, x + w.winfo_width(), y + w.winfo_height()))
    img.save("chat-screenshot.png")
    print("screenshot saved")
    root.destroy()

root.after(1600, grab)  # let the typing indicator resolve into the reply
root.mainloop()
