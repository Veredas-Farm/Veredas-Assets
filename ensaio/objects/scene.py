#!/usr/bin/env python3
"""Cena isométrica de teste: mapa de grama/terra com objetos novos ao lado dos
antigos (árvores, milho, caminhonete) e o jogador, para conferir escala.

Uso: scene.py OUT.png sprite.png@x,y [sprite2.png@x,y ...] [--zoom 3] [--size 9]
O ponto de pé vem de <sprite>.json ("anchor") se existir; senão é o centro
da última linha opaca. Objetos são desenhados de trás para frente (x+y).
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import iso  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
PLAYER = Path("/home/chips/git/games/Veredas-Farm/old_assets/Player/Player.png")
GRASS = [(2, 0), (2, 1), (2, 2), (3, 4), (3, 5), (3, 6)]
TILLED = (2, 3)


def tile(r, c):
    return Image.open(ROOT / "spritesheet.png").convert("RGBA").crop((c * 32, r * 32, c * 32 + 32, r * 32 + 32))


def foot(img):
    a = np.asarray(img)[..., 3] > 0
    y = np.nonzero(a.any(1))[0].max()
    xs = np.nonzero(a[max(y - 1, 0):y + 1].any(0))[0]
    return int(round(xs.mean())), int(y)


def load(spec):
    """'arquivo.png@x,y' ou 'arquivo.png[crop=x0,y0,x1,y1]@x,y'."""
    path, cell = spec.rsplit("@", 1)
    box = None
    if "[" in path:
        path, b = path[:-1].split("[")
        box = tuple(int(v) for v in b.split("=")[1].split(","))
    img = Image.open(path).convert("RGBA")
    if box:
        img = img.crop(box)
    meta = Path(path).with_suffix(".json")
    anc = json.loads(meta.read_text()).get("anchor") if meta.exists() and not box else None
    bb = img.getbbox()
    if anc is None:
        img = img.crop(bb)
        anc = foot(img)
    return img, tuple(anc), tuple(int(v) for v in cell.split(","))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("objs", nargs="*")
    ap.add_argument("--size", type=int, default=9)
    ap.add_argument("--zoom", type=int, default=3)
    ap.add_argument("--tilled", default="", help="células de terra arada: 'x,y;x,y'")
    ap.add_argument("--player", default="4,4")
    a = ap.parse_args()
    rng = np.random.default_rng(1)
    tilled = {tuple(int(v) for v in s.split(",")) for s in a.tilled.split(";") if s}
    tiles = {k: tile(*k) for k in GRASS + [TILLED]}
    cells = {(x, y): (TILLED if (x, y) in tilled else GRASS[rng.integers(len(GRASS))])
             for x in range(a.size) for y in range(a.size)}
    canvas = iso.render_map(cells, tiles, pad=110)
    objs = [load(s) for s in a.objs]
    if a.player:
        p = Image.open(PLAYER).convert("RGBA").crop((0, 0, 32, 32))
        objs.append((p, foot(p), tuple(int(v) for v in a.player.split(","))))
    for img, anc, cell in sorted(objs, key=lambda o: (sum(o[2]), o[2][0] - o[2][1])):
        iso.place_object(canvas, img, anc, cell)
    bb = canvas.getbbox()
    canvas = canvas.crop(bb)
    bg = Image.new("RGBA", canvas.size, (40, 36, 44, 255))
    bg.alpha_composite(canvas)
    bg.resize((bg.width * a.zoom, bg.height * a.zoom), Image.NEAREST).save(a.out)


if __name__ == "__main__":
    main()
