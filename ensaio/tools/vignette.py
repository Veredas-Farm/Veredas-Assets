"""Vinheta de teste: um pedaço de fazenda com terrenos e transições.

Uso: python vignette.py <out.png> grass=<png> path=<png> tilled=<png> [side=<png>]
     [--grid 4] [--colors 12] [--amp 0.35] [--scale 3]
Cada terreno vem de uma textura vista de cima. O mapa de terrenos é fixo
(trilha em cruz, roça retangular, resto grama) para comparar receitas.
"""

import argparse
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))
import iso  # noqa: E402
import project  # noqa: E402

N = 14


def terrain_layout():
    """Terreno por vértice da grade (N+1)^2: 0 grama, 1 trilha, 2 roça."""
    v = np.zeros((N + 1, N + 1), int)
    v[6:9, :] = 1  # trilha ao longo de x
    v[:, 9:12] = 1  # trilha ao longo de y
    v[1:5, 2:7] = 2  # roça
    v[10:14, 1:6] = 2
    return v


def load(p, crop=None):
    im = Image.open(p).convert("RGB")
    if crop:
        w, h = im.size
        im = im.crop((0, int(h * crop), w, h)).resize((w, w))
    return project.make_seamless(im)


def build(tex, side, grid, colors, amp, seed=0):
    """Tiles por (cell_variant, cantos) para os pares grama/trilha e grama/roça."""
    sets = {}
    for name in ("path", "tilled"):
        for cx in range(grid):
            for cy in range(grid):
                sets[(name, cx, cy)] = project.project_transitions(
                    tex["grass"], tex[name], side=side, grid=grid, colors=colors, seed=seed, amp=amp, cell=(cx, cy))
    return sets


def render(tex, side=None, grid=4, colors=12, amp=0.35, shadow=0.0):
    v = terrain_layout()
    # cache por célula da textura: só o necessário
    cache = {}

    def tile(name, cx, cy, corners):
        k = (name, cx, cy)
        if k not in cache:
            cache[k] = project.project_transitions(tex["grass"], tex[name], side=side, grid=grid,
                                                   colors=colors, amp=amp, cell=(cx, cy), shadow=shadow)
        return cache[k][corners]

    cells = {}
    for x in range(N):
        for y in range(N):
            c = (v[y, x], v[y, x + 1], v[y + 1, x + 1], v[y + 1, x])
            other = max(c)
            name = "path" if other == 1 else "tilled"
            # vértice com o outro terreno (roça encostando na trilha vira trilha)
            bits = tuple(int(k != 0) for k in c)
            if 1 in c and 2 in c:
                name = "path"
            cells[(x, y)] = tile(name, x % grid, y % grid, bits)
    return iso.render_map(cells)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("tex", nargs="+")
    ap.add_argument("--grid", type=int, default=4)
    ap.add_argument("--colors", type=int, default=12)
    ap.add_argument("--amp", type=float, default=0.35)
    ap.add_argument("--scale", type=int, default=3)
    ap.add_argument("--shadow", type=float, default=0.0)
    a = ap.parse_args()
    tex, side = {}, None
    for t in a.tex:
        k, p = t.split("=", 1)
        if k == "side":
            side = load(p, crop=0.45)
        else:
            tex[k] = load(p)
    m = render(tex, side, a.grid, a.colors, a.amp, a.shadow)
    m = m.resize((m.width * a.scale, m.height * a.scale), Image.NEAREST)
    m.save(a.out)
    print(a.out, m.size)


if __name__ == "__main__":
    main()
