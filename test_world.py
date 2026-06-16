#!/usr/bin/env python3
"""Headless tests for the Eldermark walkable world LOGIC (no tkinter/GUI).
Run: python test_world.py"""
import os
import random
import tempfile
from collections import deque

_T = tempfile.mkdtemp()
os.environ["LOCALAPPDATA"] = _T
os.environ["HOME"] = _T
os.environ["XDG_DATA_HOME"] = os.path.join(_T, ".local", "share")

import askpet as pm  # noqa: E402

# --- map is well-formed (no drifting row lengths) ---------------------------
assert len(pm.WORLD_MAP) == pm.WORLD_ROWS
for r in pm.WORLD_MAP:
    assert len(r) == pm.WORLD_COLS, r
# the path connects the bottom gate up to the shrine columns
assert pm.WORLD_MAP[pm.WORLD_ROWS - 1][8] == "p"      # gate
assert pm.WORLD_MAP[1][8] == "S" and pm.WORLD_MAP[1][9] == "S"   # shrine caps path
assert pm.WORLD_MAP[3][8] == "b"                       # bridge over the stream
print("map shape OK")

# --- tile/sprite art uses only the palette and the right dimensions ---------
tiles = pm._world_tile_grids()
for k, grid in tiles.items():
    assert len(grid) == pm.WORLD_TILE and all(len(row) == pm.WORLD_TILE for row in grid), k
    assert all(ch in pm.WORLD_PAL for row in grid for ch in row), k
# every tile id used in the map has art (fall back is only grass)
for row in pm.WORLD_MAP:
    for ch in row:
        assert ch in tiles, ch
spr = pm._world_sprite_grids()
for k, grid in spr.items():
    assert grid and all(len(row) == len(grid[0]) for row in grid), k
    assert all(ch == "." or ch in pm.WORLD_PAL for row in grid for ch in row), k
for need in ("hero", "fly", "orb0", "orb1", "critter"):
    assert need in spr, need
print("tile/sprite art OK")

L = pm.EldermarkWorldLogic

# --- start state ------------------------------------------------------------
g = L()
assert g.tile_at(g.x + g.PW // 2, g.y + g.PH // 2) not in L.SOLID   # on a path tile
assert g.at_shrine is False
assert g.relit is False
# classification: walls/water/trees/cottage/shrine block; ground does not
for ch in "WwTRHS":
    assert ch in L.SOLID, ch
for ch in "gfpb":
    assert ch not in L.SOLID, ch
print("start + classification OK")

# --- walking up crosses the BRIDGE and reaches the Wayshrine ----------------
g = L()
for _ in range(120):
    g.step({"up"})
    if g.at_shrine:
        break
assert g.at_shrine, (g.x, g.y)
for cx in (g.x, g.x + g.PW - 1):                    # never standing in a solid tile
    for cy in (g.y, g.y + g.PH - 1):
        assert g.tile_at(cx, cy) not in L.SOLID
print("reach shrine via bridge OK")

# --- collision + bounds: hammering each direction never escapes or clips ----
for d in ("left", "right", "up", "down"):
    g = L()
    for _ in range(400):
        g.step({d})
    assert 0 <= g.x <= g.base_w - g.PW and 0 <= g.y <= g.base_h - g.PH, (d, g.x, g.y)
    for cx in (g.x, g.x + g.PW - 1):
        for cy in (g.y, g.y + g.PH - 1):
            assert g.tile_at(cx, cy) not in L.SOLID, (d, cx, cy)
# water is NOT crossable off the bridge: aim up from a non-bridge path column
g = L()
g.x = 1 * pm.WORLD_TILE + 3            # left side, away from the bridge
g.y = 4 * pm.WORLD_TILE                # just below the stream
y0 = g.y
for _ in range(20):
    g.step({"up"})
assert g.y >= pm.WORLD_TILE * 3, "player walked through the stream off the bridge"
print("collision + bounds OK")

# --- determinism: identical inputs -> identical final position --------------
rng = random.Random(4)
seq = [rng.choice(("up", "down", "left", "right", "up")) for _ in range(200)]
a, b = L(), L()
for d in seq:
    a.step({d})
for d in seq:
    b.step({d})
assert (a.x, a.y) == (b.x, b.y)
print("determinism OK")

# --- relight is idempotent --------------------------------------------------
g = L()
g.relight()
g.relight()
assert g.relit is True
print("relight OK")

# --- the level is SOLVABLE: BFS over walkable tiles to a shrine-adjacent tile
walk = lambda ch: ch not in L.SOLID
goal = set()
for (sx, sy) in L.SHRINE:
    for ax in range(sx - 1, sx + 2):
        for ay in range(sy - 1, sy + 2):
            if 0 <= ax < pm.WORLD_COLS and 0 <= ay < pm.WORLD_ROWS and walk(pm.WORLD_MAP[ay][ax]):
                goal.add((ax, ay))
start = (8, pm.WORLD_ROWS - 2)
assert walk(pm.WORLD_MAP[start[1]][start[0]])
seen, q, reached = {start}, deque([start]), False
while q:
    x, y = q.popleft()
    if (x, y) in goal:
        reached = True
        break
    for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
        if 0 <= nx < pm.WORLD_COLS and 0 <= ny < pm.WORLD_ROWS and (nx, ny) not in seen \
                and walk(pm.WORLD_MAP[ny][nx]):
            seen.add((nx, ny))
            q.append((nx, ny))
assert reached, "the Wayshrine is not reachable from the start over walkable tiles"
print("level solvable OK")

print("WORLD TEST PASSED")
