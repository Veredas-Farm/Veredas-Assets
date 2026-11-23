"""Compara o print do Godot com o render do iso.py para as mesmas células.

Uso: python godot_diff.py <kitdir> <cells.json> <shot.png> <out.png>
Acha o deslocamento pela borda da silhueta (pixels opacos do render vs.
pixels diferentes do fundo no print) e conta pixels diferentes.
"""
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))
import iso  # noqa: E402

kit, cells_p, shot_p, out = Path(sys.argv[1]), sys.argv[2], sys.argv[3], sys.argv[4]
cells = {tuple(map(int, k.split(","))): tuple(v) for k, v in json.loads(Path(cells_p).read_text()).items()}
sheet = Image.open(kit / "terrain_atlas.png").convert("RGBA")
tiles = {c: sheet.crop((a[0] * 32, a[1] * 32, a[0] * 32 + 32, a[1] * 32 + 32)) for c, a in cells.items()}
mine = np.asarray(iso.render_map(tiles)).astype(int)
shot = np.asarray(Image.open(shot_p).convert("RGB")).astype(int)
bg = shot[0, 0]
fg_shot = np.abs(shot - bg).sum(-1) > 0
op = mine[..., 3] == 255
# deslocamento: alinha os cantos superiores-esquerdos das caixas da silhueta
ys, xs = np.nonzero(fg_shot)
ym, xm = np.nonzero(op)
best = None
for dy in range(ys.min() - ym.min() - 3, ys.min() - ym.min() + 4):
    for dx in range(xs.min() - xm.min() - 3, xs.min() - xm.min() + 4):
        H, W = mine.shape[:2]
        if dy < 0 or dx < 0 or dy + H > shot.shape[0] or dx + W > shot.shape[1]:
            continue
        s = shot[dy:dy + H, dx:dx + W]
        diff = (np.abs(s - mine[..., :3]).sum(-1) > 0) & op
        n = int(diff.sum())
        if best is None or n < best[0]:
            best = (n, dx, dy, diff)
n, dx, dy, diff = best
print(f"deslocamento ({dx}, {dy}); pixels opacos {int(op.sum())}; diferentes {n}")
vis = np.asarray(Image.open(shot_p).convert("RGB")).copy()
H, W = diff.shape
vis[dy:dy + H, dx:dx + W][diff] = (255, 0, 255)
Image.fromarray(vis).save(out)
