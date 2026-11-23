#!/usr/bin/env python3
"""Redução alinhada à grade da base do img2img.

A base é o manequim ampliado 16x; a geração volta para a grade do manequim
(mesma escala e posição de cada pixel). Cor de cada célula: moda (cor mais
frequente após quantizar) ou média. Fundo: célula com maioria branca.

Uso: grid.py gen.png --cells 84x36 --out DIR [--mode dom|mean] [--palette p.png]
"""
import argparse
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "objects"))
import pipeline as P  # noqa: E402
import char as C  # noqa: E402


def to_grid(rgb, cw, ch, mode="dom", q=24):
    H, W = rgb.shape[:2]
    fg, _ = P.remove_bg(rgb, 38.0)
    # sem erosão: P.remove_bg erode 3 px; a borda volta pela dilatação
    fg = ndimage.binary_dilation(fg, iterations=3)
    qimg = np.asarray(Image.fromarray(rgb).quantize(q, method=Image.Quantize.MEDIANCUT,
                                                   dither=Image.Dither.NONE).convert("RGB"))
    out = np.zeros((ch, cw, 3), np.uint8)
    m = np.zeros((ch, cw), bool)
    ys = np.linspace(0, H, ch + 1).round().astype(int)
    xs = np.linspace(0, W, cw + 1).round().astype(int)
    for j in range(ch):
        for i in range(cw):
            cf = fg[ys[j]:ys[j + 1], xs[i]:xs[i + 1]]
            if cf.mean() < 0.5:
                continue
            m[j, i] = True
            if mode == "dom":
                c = qimg[ys[j]:ys[j + 1], xs[i]:xs[i + 1]][cf]
                vals, cnt = np.unique(c, axis=0, return_counts=True)
                out[j, i] = vals[cnt.argmax()]
            else:
                out[j, i] = rgb[ys[j]:ys[j + 1], xs[i]:xs[i + 1]][cf].mean(0)
    return out, m


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("inputs", nargs="+")
    ap.add_argument("--cells", default="84x36")
    ap.add_argument("--out", required=True)
    ap.add_argument("--mode", default="dom,mean")
    ap.add_argument("--palette", default=None)
    ap.add_argument("--tag", default="")
    a = ap.parse_args()
    cw, ch = map(int, a.cells.split("x"))
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    pal = None
    if a.palette:
        pal = np.unique(np.concatenate([P.load_palette(p) for p in a.palette.split(",")]), axis=0)
    rows = [("atual", C.player_ref())]
    for path in a.inputs:
        rgb = np.asarray(Image.open(path).convert("RGB"))
        name = Path(path).stem
        for mode in a.mode.split(","):
            g, m = to_grid(rgb, cw, ch, mode)
            m = P.clean_mask(m)
            if pal is not None:
                g = P.map_palette(g, m, pal, 0)
            # contorno do modelo vira o nosso: borda escura -> (14,7,27)
            f = g.astype(int)
            edge = m & ~ndimage.binary_erosion(m)
            g[edge & (f.sum(-1) < 200)] = C.OUTLINE
            g, m = C.outline(g, m)
            figs = C.figures(m, 0, 0.15, dil=0)
            cells = [C.cell(g * (fm[..., None]), fm) for _, _, fm in figs]
            sheet = Image.new("RGBA", (32 * len(cells), 32))
            for i, c in enumerate(cells):
                sheet.alpha_composite(c, (32 * i, 0))
            sheet.save(out / f"{name}.grid-{mode}{a.tag}.png")
            rows.append((f"{name[:14]}\ngrid-{mode}{a.tag}", sheet))
    C.preview(rows, out / f"sheet-grid{a.tag}.png", zoom=6)
    print(out / f"sheet-grid{a.tag}.png")


if __name__ == "__main__":
    main()
