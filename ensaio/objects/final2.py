#!/usr/bin/env python3
"""Lote 2 de objetos (o19-o24): ipê, cerca, pilão, moinho. Uso: final2.py [ipe cerca pilao moinho preview]"""
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

import pipeline as P
from final import ASSETS, OUT, RUNS, palette_of

D = OUT / "objects"
YELLOW = [[244, 206, 52], [214, 164, 28], [170, 120, 24], [250, 232, 120]]
PURPLE = [[190, 120, 180], [140, 78, 140], [100, 56, 108], [226, 178, 214]]

SRC = {
    "ipe_amarelo_aberta": "o19/ipe-amarelo-3968838110.png",
    "ipe_amarelo": "o25/ipe-amarelo2-2946455683.png",
    "ipe_roxo": "o23/ipe-roxo-1074356751.png",
    "cerca": "o20/cerca-787005736.png",
    "pilao": "o21/pilao-2261883068.png",
    "moinho_agua": "o22/moinho-255086748.png",
    "moinho": "o24/moinho2-3670353958.png",
}


def save(name, im, meta):
    D.mkdir(parents=True, exist_ok=True)
    im.save(D / f"{name}.png")
    (D / f"{name}.json").write_text(json.dumps(meta))
    print(name, im.size, meta)


def tree_pal(extra):
    p = palette_of(ASSETS / "arvore_pequi.png", ASSETS / "arvore_baru.png")
    return np.concatenate([p, extra]).astype(np.uint8)


def ipe():
    P.HOLE_MIN, P.PAL_TOL = 300, 0
    for name, extra in (("ipe_amarelo", YELLOW), ("ipe_amarelo_aberta", YELLOW), ("ipe_roxo", PURPLE)):
        if name not in SRC:
            continue
        im, meta = P.process(RUNS / SRC[name], "unfake", (76, 92), (76, 92), "bottom", 24, "none", pal=tree_pal(extra))
        save("arvore_" + name, im, meta)


def cerca(period=(32, 16), top=(205, 823)):
    """Peça repetível: corta entre vãos de poste (só arame), encosta a inclinação em 1:2 e reduz.
    Tela 32 px de largura; a peça seguinte vai em (+32, -16)."""
    P.HOLE_MIN, P.PAL_TOL = 300, 30.0
    rgb = np.asarray(Image.open(RUNS / SRC["cerca"]).convert("RGB"))
    mask, _ = P.remove_bg(rgb, 38.0)
    a, b = top
    k = 0.5 - 0.286  # sobe mais 0,214 px por coluna para chegar a 1:2
    H, W = mask.shape
    # cisalha: linha y' = y - k*(x-a), com padding vertical
    pad = int(k * (b - a)) + 40
    out_rgb = np.full((H + pad, b - a, 3), 255, np.uint8)
    out_m = np.zeros((H + pad, b - a), bool)
    for x in range(a, b):
        s = int(round(k * (x - a)))
        # sobe s: linha y vai para y + pad - s
        out_rgb[pad - s:pad - s + H, x - a] = rgb[:, x]
        out_m[pad - s:pad - s + H, x - a] = mask[:, x]
    ys = np.nonzero(out_m.any(1))[0]
    out_rgb, out_m = out_rgb[ys.min():ys.max() + 1], out_m[ys.min():ys.max() + 1]
    out_rgb = P.flat_bg(out_rgb, out_m)
    scale = (b - a) / period[0]
    h = int(round(out_m.shape[0] / scale))
    small, m = P.premult_box(out_rgb, out_m, (period[0], h))
    m = P.clean_mask(m)
    small = P.quantize(small, m, 20)
    pal = palette_of(ASSETS / "carreta.png", ASSETS / "arvore_pequi.png", ASSETS / "arvore_baru.png")
    small = P.map_palette(small, m, pal, P.PAL_TOL)
    im = P.to_rgba(small, m)
    meta = {"anchor": None, "tile": list(period), "next": [period[0], -period[1]]}
    # pé: base do poste do meio (última linha opaca do meio da tela)
    col = np.asarray(im)[..., 3] > 0
    meta["anchor"] = [period[0] // 2, int(np.nonzero(col[:, period[0] // 2])[0].max())]
    save("cerca_aroeira", im, meta)
    save("cerca_aroeira_esp", im.transpose(Image.FLIP_LEFT_RIGHT),
         {**meta, "anchor": [period[0] - 1 - meta["anchor"][0], meta["anchor"][1]], "next": [-period[0], -period[1]]})


def small(name, box, foot=0.2):
    """Objeto pequeno/médio: receita da carreta (box, contorno auto, paleta carreta+árvores). Pé no meio da base."""
    P.HOLE_MIN, P.PAL_TOL = 300, 30.0
    pal = palette_of(ASSETS / "carreta.png", ASSETS / "arvore_pequi.png", ASSETS / "arvore_baru.png")
    im, meta = P.process(RUNS / SRC[name], "box", box, (box[0] + 2, box[1] + 2), "bottom", 20, "auto", pal=pal)
    meta["anchor"] = [im.width // 2, im.height - 1 - int(box[1] * foot)]
    save(name, im, meta)


def pilao():
    small("pilao", (24, 26), 0.2)


def moinho():
    small("moinho", (56, 54), 0.15)  # o24: seco, roda legível
    small("moinho_agua", (60, 56), 0.2)  # o22: com poça e pedras de margem


def preview():
    """out/objects2_preview.png: 3x, sobre grama, pequi atual à esquerda para escala."""
    names = ["arvore_ipe_amarelo", "arvore_ipe_roxo", "moinho", "moinho_agua", "pilao"]
    items = [(Image.open(ASSETS / "arvore_pequi.png").convert("RGBA"), None)]
    items += [(Image.open(D / f"{n}.png"), None) for n in names]
    fence = Image.open(D / "cerca_aroeira.png")
    fw, fh = 32 * 4, fence.height + 16 * 3
    fimg = Image.new("RGBA", (fw, fh))
    for i in range(4):
        fimg.alpha_composite(fence, (i * 32, (3 - i) * 16))
    items.append((fimg, None))
    W = sum(i.width + 10 for i, _ in items) + 10
    H = max(i.height for i, _ in items) + 12
    prev = Image.new("RGBA", (W, H), P.GRASS)
    x = 10
    for im, _ in items:
        prev.alpha_composite(im, (x, H - 6 - im.height))
        x += im.width + 10
    prev.resize((W * 3, H * 3), Image.NEAREST).save(OUT / "objects2_preview.png")


if __name__ == "__main__":
    for w in sys.argv[1:] or ["ipe", "cerca"]:
        globals()[w]()
