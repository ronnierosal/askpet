"""Pet store integration test — hits codex-pets.net (network required).
Run: python test_petstore.py
"""
import atexit
import tkinter as tk
import promptmate as pm

# Restore the user's real settings on exit — this test switches pets.
_settings_backup = pm.SETTINGS_FILE.read_bytes() if pm.SETTINGS_FILE.exists() else None
atexit.register(lambda: pm.SETTINGS_FILE.write_bytes(_settings_backup)
                if _settings_backup else None)

# Catalog fetch
pets = pm.fetch_pet_page(1)
assert len(pets) > 0, "empty catalog"
print(f"catalog page 1: {len(pets)} pets, first: "
      f"{pets[0]['id']} by {pm.pet_credit(pets[0])}")

# Pick a pet that isn't kogi and install it
target = next(p for p in pets if p["id"] != "kogi")
print("installing:", target["id"], "-", target.get("displayName"))
pet_dir = pm.install_pet(target["id"], info=target)
manifest = pm.load_json(pet_dir / "manifest.json", None)
meta = pm.load_json(pet_dir / "pet.json", None)
assert manifest and manifest["animations"], "manifest missing animations"
assert meta and meta.get("ownerHandle") is not None or meta.get("ownerName"), "credit missing"
print("animations:", {k: v["frames"] for k, v in manifest["animations"].items()})
print("credit:", pm.pet_credit(meta))

# Live switch in the overlay
root = tk.Tk()
pet = pm.PetOverlay(root)
assert pet.sprites.ok
before = pet.pet_id
pet.switch_pet(target["id"])
assert pet.pet_id == target["id"]
assert pet.sprites.ok, "sprites failed after switch"
print(f"switched {before} -> {pet.pet_id}, size {pet.sprites.w}x{pet.sprites.h}")
for _ in range(5):
    root.update()

# Switch back to kogi (kept as the user's default)
pet.switch_pet("kogi")
assert pet.sprites.ok and pet.pet_id == "kogi"
print("switched back to kogi")
root.destroy()
print("PET STORE TEST PASSED")
