import time

import askpet as pm

t0 = time.perf_counter()
s = pm.SpellHelper()
n = len(pm.english_words())
t1 = time.perf_counter()
print(f"dictionary: {n} words, loaded in {t1 - t0:.2f}s")

good = ["meeting", "notes", "calendar", "boss", "tomorrow", "please",
        "soccer", "games", "manage", "budget", "doesn't", "it's",
        "kogi's", "users'", "intune", "powershell", "Meeting", "chatgpt"]
bad = ["tommorow", "organiz", "definately", "recieve", "xyzzyq"]
ok = True
for w in good:
    if not s.known(w):
        print(f"** {w!r} should be known"); ok = False
for w in bad:
    if s.known(w):
        print(f"** {w!r} should be flagged"); ok = False

t2 = time.perf_counter()
sugg = s.suggestions("tommorow")
t3 = time.perf_counter()
print(f"suggestions('tommorow') = {sugg} in {t3 - t2:.2f}s")
sugg2 = s.suggestions("calender")
print(f"suggestions('calender') = {sugg2}")
sugg3 = s.suggestions("definately")
print(f"suggestions('definately') = {sugg3}")
print("SPELL CHECK TEST", "PASSED" if ok else "FAILED")
