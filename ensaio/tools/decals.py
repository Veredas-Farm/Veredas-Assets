"""Recorta decals de uma folha de sprites (fundo liso) e reduz à escala do jogo.

Uso: python decals.py <folha.png> <outdir> [--px 8] [--min 200] [--tol 38]

Cada componente conexo vira um PNG: bloco px x px -> 1 pixel (cor mediana dos
pixels de objeto do bloco; bloco é objeto se >= 50% dele for objeto). Gera
também <outdir>/sheet.png com todos lado a lado (4x).
"""
import argparse
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "objects"))
from pipeline import remove_bg  # noqa: E402


def reduce(rgb, mask, px):
    h, w = mask.shape
    H, W = (h + px - 1) // px, (w + px - 1) // px
    out = np.zeros((H, W, 4), np.uint8)
    for j in range(H):
        for i in range(W):
            m = mask[j * px:(j + 1) * px, i * px:(i + 1) * px]
            if m.mean() >= 0.5:
                c = rgb[j * px:(j + 1) * px, i * px:(i + 1) * px][m]
                out[j, i] = (*np.median(c, 0).astype(int), 255)
    return Image.fromarray(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("sheet")
    ap.add_argument("outdir")
    ap.add_argument("--px", type=int, default=8)
    ap.add_argument("--min", type=int, default=200, help="área mínima do componente (px da folha)")
    ap.add_argument("--tol", type=float, default=38.0)
    a = ap.parse_args()
    rgb = np.asarray(Image.open(a.sheet).convert("RGB"))
    mask, _ = remove_bg(rgb, tol=a.tol, min_part=0.0)
    lab, n = ndimage.label(mask)
    out = Path(a.outdir)
    out.mkdir(parents=True, exist_ok=True)
    sprites = []
    for k, sl in enumerate(ndimage.find_objects(lab)):
        m = lab[sl] == k + 1
        if m.sum() < a.min:
            continue
        sp = reduce(rgb[sl], m, a.px)
        bb = sp.getbbox()
        if not bb:
            continue
        sp = sp.crop(bb)
        sp.save(out / f"d{len(sprites):02d}.png")
        sprites.append(sp)
    W = sum(s.width + 2 for s in sprites)
    H = max(s.height for s in sprites)
    sheet = Image.new("RGBA", (W, H), (60, 120, 50, 255))
    x = 0
    for s in sprites:
        sheet.alpha_composite(s, (x, H - s.height))
        x += s.width + 2
    sheet.resize((W * 4, H * 4), Image.NEAREST).save(out / "sheet.png")
    print(out, len(sprites), "decals")


if __name__ == "__main__":
    main()
