#!/usr/bin/env python3
"""Topos dos blocos das folhas 4x4 (img2img moss) -> texturas quadradas (vista de cima) para o kit.

Uso: python iso_texturas.py [--out out/iso/tex]

Cada célula (256 px na folha de 1024) tem um cubo alto em 2:1. O losango de cima tem
vértices T (topo), L, R e B = L + R - T. T.y e L/R.x saem da caixa do objeto na célula
(L/R ficam a T.y + W/4, inclinação 2:1). A face é desfeita por mapeamento afim inverso
(quadrado -> losango), com margem para tirar o contorno preto e a franja das bordas.
Saída: <fonte>_<linha>_<coluna>.png 192x192 e os grupos usados pelo kit.
"""
import argparse
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
GAL = Path("/home/chips/.local/share/ai-gallery/images")
SHEETS = {"a": GAL / "3e/3e91493dbdfd35a6d9aa5df50fc5cf45d86944050ea6aa423b8579b27394419c.png",
          "b": GAL / "83/83fb90686fca8c6836ecadbfdd8ee58c835be7a804fba502be2a75524895606f.png"}
N = 192          # lado da textura
MARGIN = 0.12    # fração tirada de cada borda do losango


def diamond(cell):
    a = np.asarray(cell.convert("RGB")).astype(int)
    obj = (a.min(-1) < 225) | ((a.max(-1) - a.min(-1)) > 30)
    cols = np.nonzero(obj.sum(0) > 3)[0]
    x0, x1 = cols.min(), cols.max() + 1
    mid = (x0 + x1) // 2
    sl = obj[:, max(mid - 20, 0):mid + 20]
    # topo do losango: primeira linha com mais de 12 px de objeto no centro (ignora tufos finos)
    ty = int(np.nonzero(sl.sum(1) > 12)[0].min())
    W = x1 - x0
    return (mid, ty), (x0, ty + W / 4), (x1, ty + W / 4)


def sheet_geometry(sheet):
    """Losango médio das células da linha 0 (cubos limpos): vale para a folha toda, porque
    pedras e tufos têm silhueta irregular e enganam a detecção por célula."""
    g = np.array([diamond(sheet.crop((c * 256, 0, c * 256 + 256, 256))) for c in range(4)], float)
    return tuple(map(tuple, g.mean(0)))


def unwarp(cell, geo):
    (tx, ty), (lx, ly), (rx, ry) = geo
    bx, by = lx + rx - tx, ly + ry - ty
    src = np.asarray(cell.convert("RGB"), float)
    h, w = src.shape[:2]
    u = (np.arange(N) + 0.5) / N
    u = MARGIN + u * (1 - 2 * MARGIN)
    U, V = np.meshgrid(u, u)
    # u ao longo de T->R, v ao longo de T->L
    X = tx + U * (rx - tx) + V * (lx - tx)
    Y = ty + U * (ry - ty) + V * (ly - ty)
    xi, yi = np.clip(X.round().astype(int), 0, w - 1), np.clip(Y.round().astype(int), 0, h - 1)
    return Image.fromarray(src[yi, xi].astype(np.uint8))


def extract(out):
    out.mkdir(parents=True, exist_ok=True)
    res = {}
    for key, path in SHEETS.items():
        sheet = Image.open(path).convert("RGB")
        geo = sheet_geometry(sheet)
        for r in range(4):
            for c in range(4):
                cell = sheet.crop((c * 256, r * 256, c * 256 + 256, r * 256 + 256))
                t = unwarp(cell, geo)
                f = out / f"{key}_{r}{c}.png"
                t.save(f)
                res[(key, r, c)] = f
    return res


def contact(out):
    names = sorted(out.glob("[ab]_??.png"))
    sh = Image.new("RGB", (8 * 100, 4 * 100), (30, 30, 30))
    for i, n in enumerate(names):
        k = 0 if n.name[0] == "a" else 4
        r, c = int(n.name[2]), int(n.name[3])
        sh.paste(Image.open(n).resize((96, 96)), ((c + k) * 100, r * 100))
    sh.save(out / "contato.png")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "out/iso/tex"))
    a = ap.parse_args()
    extract(Path(a.out))
    contact(Path(a.out))
    print("texturas em", a.out)
