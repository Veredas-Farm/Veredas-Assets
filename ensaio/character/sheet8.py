#!/usr/bin/env python3
"""Redução 1:1 de uma geração feita sobre `bases/sheet_1568x672.png`.

A base tem 1 pixel do manequim = 8 px = 1 pixel nativo da LoRA do moss, então
a geração volta ao tamanho do jogo reduzindo por 8 (cor dominante de cada bloco
8x8, com a fase da grade escolhida pela menor variância). Os quadros saem das
mesmas posições da base (2 fileiras de 6 células 32x32, a partir de (2, 10)).

Uso: sheet8.py gen.png [...] --out DIR   -> DIR/<nome>.cells.png (192x64) e DIR/<nome>.8x.png
"""
import argparse
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "objects"))
import char as C  # noqa: E402

OX, OY = 2, 10  # canto da primeira célula na base (em pixels do manequim)
LABELS = ["frente", "lado", "costas", "passo A", "cruza", "passo B",
          "cruza", "frente", "lado", "costas", "passo A", "passo B"]


def best_phase(rgb, k=8):
    f = rgb.astype(float)
    best = None
    for py in range(k):
        for px in range(k):
            h = (f.shape[0] - py) // k * k
            w = (f.shape[1] - px) // k * k
            b = f[py:py + h, px:px + w].reshape(h // k, k, w // k, k, 3)
            v = b.var(axis=(1, 3)).mean()
            if best is None or v < best[0]:
                best = (v, py, px)
    return best[1], best[2]


def reduce8(rgb, k=8):
    py, px = best_phase(rgb, k)
    # recoloca a fase para que o bloco (0,0) comece em (py - k se py>k/2...) -> mantém alinhado à base
    if py > k // 2:
        py -= k
    if px > k // 2:
        px -= k
    pad = ((max(-py, 0), k), (max(-px, 0), k), (0, 0))
    a = np.pad(rgb, pad, mode="edge")[max(py, 0):, max(px, 0):]
    H, W = rgb.shape[0] // k, rgb.shape[1] // k
    a = a[:H * k, :W * k].reshape(H, k, W, k, 3).transpose(0, 2, 1, 3, 4).reshape(H, W, k * k, 3)
    out = np.zeros((H, W, 3), np.uint8)
    q = (a // 8).astype(np.int32)
    key = q[..., 0] * 1024 + q[..., 1] * 32 + q[..., 2]
    for j in range(H):
        for i in range(W):
            vals, inv, cnt = np.unique(key[j, i], return_inverse=True, return_counts=True)
            sel = inv == cnt.argmax()
            out[j, i] = a[j, i][sel].mean(0)
    return out, (py, px)


def to_cells(small):
    small = small.copy()
    f = small.astype(int)
    white = (f.min(-1) > 225)
    lab, n = ndimage.label(white)
    border = np.unique(np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]]))
    bg = np.isin(lab, border[border > 0])
    m = ~bg
    m = C.P.clean_mask(m)
    # pixel branco solto dentro da figura (fundo que vazou entre as pernas): cor do vizinho mais escuro
    lone = white & m
    for y, x in zip(*np.nonzero(lone)):
        nb = [small[yy, xx] for yy, xx in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1))
              if 0 <= yy < small.shape[0] and 0 <= xx < small.shape[1] and not white[yy, xx]]
        if nb:
            small[y, x] = min(nb, key=lambda c: int(c.astype(int).sum()))
    f = small.astype(int)
    edge = m & ~ndimage.binary_erosion(m)
    dark = f.sum(-1) < 200
    out = small.copy()
    out[edge & dark] = C.OUTLINE
    out[(~edge) & m & (f.sum(-1) < 90)] = C.OUTLINE  # pretos internos (olho, fita) = cor do contorno
    cells = []
    for k in range(12):
        x0, y0 = OX + 32 * (k % 6), OY + 32 * (k // 6)
        cm = m[y0:y0 + 32, x0:x0 + 32].copy()
        lab, n = ndimage.label(cm)
        if n > 1:
            sizes = ndimage.sum(cm, lab, range(1, n + 1))
            cm = lab == 1 + int(np.argmax(sizes))
        if not cm.any():
            cells.append(Image.new("RGBA", (32, 32)))
            continue
        cr = out[y0:y0 + 32, x0:x0 + 32]
        # contorno onde faltar (borda clara que encostou no fundo)
        cr, cm = close_outline(cr, cm)
        cells.append(in_place(cr, cm))
    return cells


def in_place(rgb, m):
    """Quadro 32x32 sem recentrar: a posição vem da base (pé na linha 22, mesmo x
    em todos os quadros), então a caminhada não treme. Sombra como no Player.png."""
    img = np.zeros((32, 32, 4), np.uint8)
    yy, xx = np.mgrid[0:32, 0:32]
    ell = ((xx - 15.5) / 6.5) ** 2 + ((yy - C.FOOT_Y - 0.5) / 1.6) ** 2 <= 1
    img[ell] = C.SHADOW
    img[m, :3] = rgb[m]
    img[m, 3] = 255
    return Image.fromarray(img, "RGBA")


def close_outline(rgb, m):
    """Garante que a borda externa é contorno: se o pixel de borda não é escuro, põe 1 px por fora."""
    f = rgb.astype(int)
    edge = m & ~ndimage.binary_erosion(m)
    light = edge & (np.abs(f - C.OUTLINE.astype(int)).sum(-1) > 0)
    if not light.any():
        return rgb, m
    ring = ndimage.binary_dilation(light, np.array([[0, 1, 0], [1, 1, 1], [0, 1, 0]])) & ~m
    out = rgb.copy()
    out[ring] = C.OUTLINE
    return out, m | ring


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("inputs", nargs="+")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    for path in a.inputs:
        name = Path(path).stem
        rgb = np.asarray(Image.open(path).convert("RGB"))
        small, ph = reduce8(rgb)
        print(name, "fase", ph)
        Image.fromarray(small).save(out / f"{name}.small.png")
        cells = to_cells(small)
        sheet = Image.new("RGBA", (192, 64))
        for k, c in enumerate(cells):
            sheet.alpha_composite(c, (32 * (k % 6), 32 * (k // 6)))
        sheet.save(out / f"{name}.cells.png")
        rows.append((name[:14] + " 1", sheet.crop((0, 0, 192, 32))))
        rows.append((name[:14] + " 2", sheet.crop((0, 32, 192, 64))))
    C.preview([("atual", C.player_ref())] + rows, out / "sheet8.png", zoom=4)
    print(out / "sheet8.png")


if __name__ == "__main__":
    main()
