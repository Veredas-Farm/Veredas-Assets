#!/usr/bin/env python3
"""Geração (fileira de vistas ou figura única) -> quadros 32x32 no estilo do Player.png.

Passos: fundo (pipeline.remove_bg) -> figuras = componentes grandes, da
esquerda para a direita -> mesma escala para todas (a figura mais alta cabe em
--height) -> redução (box/unfake/repix do pipeline de objetos) -> quantização
-> contorno 1 px (14,7,27) do Player.png -> paleta opcional -> célula 32x32
com o pé na linha 22 e sombra cinza (0,0,0,100) como no Player.png.

Uso:
  char.py split gen.png [gen2.png ...] --out DIR [--height 20] [--variants box,unfake]
      grava DIR/<nome>.<variante>.png (folha 32*k x 32) e DIR/sheet.png (prévia 4x)
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

OUTLINE = np.array([14, 7, 27], np.uint8)
SHADOW = (0, 0, 0, 100)
FOOT_Y = 22  # última linha da botina na célula (Player.png: 22)
PLAYER = Path("/home/chips/git/games/Veredas-Farm/old_assets/Player/Player.png")
GRASS = (122, 150, 84, 255)


def figures(mask, k=0, min_frac=0.15, dil=6):
    """Fatias (x0, x1) das figuras: componentes (dilatados) com área >= min_frac do maior."""
    lab, n = ndimage.label(ndimage.binary_dilation(mask, iterations=dil) if dil else mask)
    if not n:
        return []
    sizes = ndimage.sum(mask, lab, range(1, n + 1))
    keep = [i + 1 for i, s in enumerate(sizes) if s >= min_frac * sizes.max()]
    if k:
        keep = sorted(keep, key=lambda i: -sizes[i - 1])[:k]
    out = []
    for i in keep:
        m = mask & (lab == i)
        xs = np.nonzero(m.any(0))[0]
        out.append((xs.min(), xs.max() + 1, m))
    return sorted(out, key=lambda t: t[0])


def drop_ground_shadow(rgb, m):
    """Tira a sombra cinza que o modelo às vezes desenha sob os pés (baixa saturação, faixa de baixo)."""
    ys = np.nonzero(m.any(1))[0]
    y0 = ys.max() - int((ys.max() - ys.min()) * 0.10)
    f = rgb.astype(int)
    sat = f.max(-1) - f.min(-1)
    grey = (sat < 18) & (f.mean(-1) > 90)
    out = m.copy()
    out[y0:] &= ~grey[y0:]
    lab, n = ndimage.label(out)
    if n > 1:
        sizes = ndimage.sum(out, lab, range(1, n + 1))
        out = lab == 1 + int(np.argmax(sizes))
    return out


def outline(rgb, m):
    ring = ndimage.binary_dilation(m, np.array([[0, 1, 0], [1, 1, 1], [0, 1, 0]])) & ~m
    out = rgb.copy()
    out[ring] = OUTLINE
    return out, m | ring


def reduce_fig(rgb, m, scale, variant, colors, pal, pal_tol, darken_edge, strip=0):
    rgb, m = P.crop(rgb, m, pad=8)
    if strip:
        # tira o contorno grosso do modelo (anel de `strip` px escuros na borda): a redução
        # não mistura o preto nas cores de dentro, e o contorno de 1 px é refeito depois
        f = rgb.astype(int)
        dark = f.sum(-1) < 180
        ring = m & ~ndimage.binary_erosion(m, iterations=strip)
        m = m & ~(ring & dark)
        m = ndimage.binary_opening(m, iterations=2)
    rgb = P.flat_bg(rgb, m)
    small, sm = P.VARIANTS[variant](rgb, m, scale, colors)
    sm = P.clean_mask(sm)
    small = P.quantize(small, sm, colors)
    if pal is not None:
        small = P.map_palette(small, sm, pal, pal_tol)
    if darken_edge:
        # o próprio contorno escuro do modelo, já na borda: vira a cor do contorno
        f = small.astype(int)
        dark = (f.sum(-1) < 150) & sm
        edge = sm & ~ndimage.binary_erosion(sm)
        small[dark & edge] = OUTLINE
    small, sm = outline(small, sm)
    return small, sm


def cell(rgb, m, shadow=True):
    ys, xs = np.nonzero(m)
    y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
    h, w = y1 - y0, x1 - x0
    img = np.zeros((32, 32, 4), np.uint8)
    oy = FOOT_Y + 1 - h
    ox = (32 - w) // 2
    if shadow:
        yy, xx = np.mgrid[0:32, 0:32]
        ell = ((xx - 15.5) / 6.5) ** 2 + ((yy - FOOT_Y - 0.5) / 1.6) ** 2 <= 1
        img[ell] = SHADOW
    sub = m[y0:y1, x0:x1]
    oy0 = max(oy, 0)
    cut = oy0 - oy
    tgt = img[oy0:oy0 + h - cut, ox:ox + w]
    s = sub[cut:]
    tgt[s, :3] = rgb[y0 + cut:y1, x0:x1][s]
    tgt[s, 3] = 255
    return Image.fromarray(img, "RGBA")


def process(path, height, variant, colors, pal, pal_tol, k, darken_edge, shadow_fix, strip=0, fixed_scale=0):
    rgb = np.asarray(Image.open(path).convert("RGB"))
    mask, _ = P.remove_bg(rgb, 38.0)
    figs = figures(mask, k)
    if shadow_fix:
        figs = [(a, b, drop_ground_shadow(rgb, m)) for a, b, m in figs]
    hmax = max(np.ptp(np.nonzero(m.any(1))[0]) + 1 for _, _, m in figs)
    scale = fixed_scale or hmax / (height - 2)  # -2: contorno em cima e embaixo
    cells = []
    for _, _, m in figs:
        small, sm = reduce_fig(rgb, m, scale, variant, colors, pal, pal_tol, darken_edge, strip)
        cells.append(cell(small, sm))
    sheet = Image.new("RGBA", (32 * len(cells), 32))
    for i, c in enumerate(cells):
        sheet.alpha_composite(c, (32 * i, 0))
    return sheet


def preview(rows, path, zoom=4):
    """rows: lista de (rótulo, folha RGBA). Fundo de grama, zoom nearest."""
    W = max(r.width for _, r in rows)
    lab = 120
    out = Image.new("RGBA", (lab + W * zoom, 32 * zoom * len(rows)), GRASS)
    from PIL import ImageDraw
    d = ImageDraw.Draw(out)
    font = P.font(12)
    for i, (name, r) in enumerate(rows):
        out.alpha_composite(r.resize((r.width * zoom, r.height * zoom), Image.NEAREST), (lab, i * 32 * zoom))
        d.text((4, i * 32 * zoom + 4), name, fill=(0, 0, 0, 255), font=font)
    out.save(path)


def player_ref(rows=(0, 1, 2)):
    im = Image.open(PLAYER).convert("RGBA")
    s = Image.new("RGBA", (32 * len(rows), 32))
    for i, r in enumerate(rows):
        s.alpha_composite(im.crop((0, r * 32, 32, r * 32 + 32)), (32 * i, 0))
    return s


def player_ref_row(row, n=4):
    im = Image.open(PLAYER).convert("RGBA")
    return im.crop((0, row * 32, 32 * n, row * 32 + 32))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("kind", choices=["split"])
    ap.add_argument("inputs", nargs="+")
    ap.add_argument("--out", required=True)
    ap.add_argument("--height", type=int, default=20)
    ap.add_argument("--variants", default="box,unfake")
    ap.add_argument("--colors", type=int, default=14)
    ap.add_argument("--palette", default=None, help="PNG(s) separados por vírgula")
    ap.add_argument("--palette-tol", type=float, default=0)
    ap.add_argument("--k", type=int, default=0, help="quantas figuras manter (as maiores)")
    ap.add_argument("--no-darken", action="store_true")
    ap.add_argument("--no-shadow-fix", action="store_true")
    ap.add_argument("--strip", type=int, default=0, help="px do contorno do modelo a tirar antes de reduzir")
    ap.add_argument("--tag", default="", help="sufixo do nome de saída")
    ap.add_argument("--scale", type=float, default=0, help="px da geração por px do jogo (fixo, ignora --height)")
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    pal = None
    if a.palette:
        pal = np.unique(np.concatenate([P.load_palette(p) for p in a.palette.split(",")]), axis=0)
    rows = [("atual", player_ref())]
    for path in a.inputs:
        name = Path(path).stem
        for v in a.variants.split(","):
            try:
                s = process(path, a.height, v, a.colors, pal, a.palette_tol, a.k, not a.no_darken,
                            not a.no_shadow_fix, a.strip, a.scale)
            except Exception as e:  # noqa: BLE001
                print("falhou", name, v, e)
                continue
            s.save(out / f"{name}.{v}{a.tag}.png")
            rows.append((f"{name[:14]}\n{v}{a.tag}", s))
    preview(rows, out / f"sheet{a.tag}.png")
    print(out / f"sheet{a.tag}.png")


if __name__ == "__main__":
    main()
