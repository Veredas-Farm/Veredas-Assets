"""Confere a saída do teste do Godot (cells.json: "x,y" -> [col, row]).

Uso: python godot_check.py <kitdir> <cells.json> <out.png>
Para cada vértice da grade, os até 4 tiles que o compartilham devem concordar
no terreno do canto. Desenha o mapa com as células escolhidas pelo Godot.
"""
import json
import sys
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))
import iso  # noqa: E402

kit, cells_p, out = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
meta = json.loads((kit / "terrain_atlas.json").read_text())
by_atlas = {tuple(t["atlas"]): t for t in meta["tiles"]}
cells = {tuple(map(int, k.split(","))): tuple(v) for k, v in json.loads(Path(cells_p).read_text()).items()}
xs = [c[0] for c in cells]; ys = [c[1] for c in cells]
missing = [(x, y) for x in range(min(xs), max(xs) + 1) for y in range(min(ys), max(ys) + 1) if (x, y) not in cells]
vtx = {}
bad = []
for (x, y), a in cells.items():
    t = by_atlas[a]["corners"]
    for name, v in (("top", (x, y)), ("right", (x + 1, y)), ("bottom", (x + 1, y + 1)), ("left", (x, y + 1))):
        if v in vtx and vtx[v] != t[name]:
            bad.append(v)
        vtx.setdefault(v, t[name])
print(f"células {len(cells)}, vazias {len(missing)}, vértices em conflito {len(set(bad))}")
if missing:
    print("vazias (amostra):", missing[:12])
sheet = Image.open(kit / "terrain_atlas.png").convert("RGBA")
tiles = {c: sheet.crop((a[0] * 32, a[1] * 32, a[0] * 32 + 32, a[1] * 32 + 32)) for c, a in cells.items()}
m = iso.render_map(tiles)
m.resize((m.width * 2, m.height * 2), Image.NEAREST).save(out)
