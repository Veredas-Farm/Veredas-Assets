#!/usr/bin/env python3
"""Manequim das ações com braço e mão (c36+).

Para cada quadro de Player_Actions.png (2 x 12 células 48x48), a mão vai para onde está a mão do
sprite original (blocos de pele do recorte de `player.tool_layer`), e o braço sai do ombro mais
próximo: manga (camisa) até a metade, pele no resto, mão 2x2. O corpo é o parado da vista sem as
mãos. O modelo polia o braço como o resto; a ferramenta continua recortada do original.

Uso: arms.py bases     -> bases/act{front,side,back}[B]_1568x672.png + out/blockout[B]_act_*.png
"""
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "objects"))
import blockout as BO  # noqa: E402

VIEWS = ("front", "side", "back")
ACT_VIEW = ["side", "front", "back"] * 3 + ["front", "back", "side"]  # linha de Player_Actions -> vista
SKIN = [(246, 202, 159), (210, 159, 112)]


def _hands(a, idle, body, off):
    """Centros dos blocos de pele (mãos) que o quadro de ação tem e o parado não; off = margem da célula."""
    import player as PL
    lay = PL.tool_layer(a, idle, body)
    skin = np.zeros(lay.shape[:2], bool)
    for s in SKIN:
        skin |= (lay[..., :3] == s).all(-1) & (lay[..., 3] == 255)
    if not skin.any():  # mão encostada no corpo antigo: o recorte descartou; pega a pele que mudou
        diff = (a != idle).any(-1) & (a[..., 3] == 255)
        for s in SKIN:
            skin |= diff & (a[..., :3] == s).all(-1)
        lab, n = ndimage.label(skin, np.ones((3, 3), bool))
        sizes = ndimage.sum(skin, lab, range(1, n + 1))
        skin = np.isin(lab, [i + 1 for i, z in enumerate(sizes) if z <= 8])
    lab, n = ndimage.label(skin, np.ones((3, 3), bool))
    hs = []
    for i in range(1, n + 1):
        ys, xs = np.nonzero(lab == i)
        hs.append((int(round(ys.mean())) - off, int(round(xs.mean())) - off))
    if not hs and (lay[..., 3] == 255).any():  # sem pele: mão no pixel da ferramenta mais perto do corpo
        ys, xs = np.nonzero(lay[..., 3] == 255)
        k = int(np.argmin((ys - 16 - off) ** 2 + (xs - 16 - off) ** 2))
        hs = [(int(ys[k]) - off, int(xs[k]) - off)]
    return hs


def old_hands():
    """{(linha, coluna): [(y, x) em coordenadas da célula 32]} das mãos do original (Player_Actions)."""
    import player as PL
    pl, ac = PL.old_sheets()
    body = PL._body_colors(pl)
    out = {}
    for r, v in enumerate(ACT_VIEW):
        vi = VIEWS.index(v)
        idle = PL.pad48(pl[32 * vi:32 * vi + 32, 0:32])
        for c in range(2):
            out[(r, c)] = _hands(ac[48 * r:48 * r + 48, 48 * c:48 * c + 48], idle, body, 8)
    return out


def foice_grids():
    """Foice (Player.png linhas 6-8, 4 quadros): {vista: [(linha, coluna, grade, dx)]}."""
    import player as PL
    pl, _ = PL.old_sheets()
    body = PL._body_colors(pl)
    out = {}
    for vi, v in enumerate(VIEWS):
        idle = pl[32 * vi:32 * vi + 32, 0:32]
        out[v] = []
        for c in range(4):
            hs = _hands(pl[32 * (6 + vi):32 * (7 + vi), 32 * c:32 * c + 32], idle, body, 0)
            hs, dx = clear_hat(v, hs)
            out[v].append((6 + vi, c, draw_arms(v, hs), dx))
    return out


def foice_bases():
    """1 folha por vista e roupa: os 4 quadros da foice x 3."""
    G = foice_grids()
    for o, col in (("", BO.COL), ("B", BO.COL_B)):
        for v in VIEWS:
            g3 = G[v] * 3
            sheet(g3, col, HERE / "bases" / f"foice{v}{o}_1568x672.png")
            s = Image.new("RGBA", (32 * 4, 32))
            for i, (_, _, g, _) in enumerate(G[v]):
                s.alpha_composite(Image.fromarray(grid_frame(g, col)), (32 * i, 0))
            s.save(HERE / "out" / f"blockout{o}_foice_{v}_32.png")


def base_grid(view):
    """Rótulos 32x32 do parado da vista, sem as mãos e sem o contorno."""
    rows = BO.VIEWS[view]
    g = BO.frame_labels(rows).copy()
    g[g == "o"] = " "
    ys = np.nonzero(np.isin(g, list("Rq")).any(1))[0]
    torso0 = ys.min()
    hand = np.isin(g, list("Ss"))
    hand[:torso0 + 1] = False
    g[hand] = "q"  # mão no tronco vira manga
    return g, torso0


def shoulders(g, torso0, view):
    xs = np.nonzero(np.isin(g[torso0 + 1], list("Rq")))[0]
    if view == "side":
        x = int(round(xs.mean()))
        return [(torso0 + 1, x)]
    return [(torso0 + 1, xs.min()), (torso0 + 1, xs.max())]


def line(p, q):
    (y0, x0), (y1, x1) = p, q
    n = max(abs(y1 - y0), abs(x1 - x0), 1)
    return [(int(round(y0 + (y1 - y0) * t / n)), int(round(x0 + (x1 - x0) * t / n))) for t in range(n + 1)]


def draw_arms(view, hands):
    g, torso0 = base_grid(view)
    body = g != " "
    for hy, hx in hands:
        hy, hx = int(np.clip(hy, 1, 29)), int(np.clip(hx, 1, 29))
        sh = min(shoulders(g, torso0, view), key=lambda s: (s[0] - hy) ** 2 + (s[1] - hx) ** 2)
        pts = line(sh, (hy, hx))
        for k, (y, x) in enumerate(pts):
            if body[y, x] and k < len(pts) - 2:
                continue  # braço por dentro do corpo: não pinta
            g[y, x] = "R" if k < len(pts) * 0.5 else "S"
        for dy in (0, 1):
            for dx in (0, 1):
                y, x = min(hy + dy, 30), min(hx + dx, 30)
                g[y, x] = "S" if (dy, dx) != (1, 1) else "s"
    return g


def grid_frame(g, col):
    """Como blockout.frame, mas a partir da grade 32x32 de rótulos."""
    m = g != " "
    rgb = np.zeros((32, 32, 3), np.uint8)
    for k, c in col.items():
        rgb[g == k] = c
    ring = ndimage.binary_dilation(m, np.array([[0, 1, 0], [1, 1, 1], [0, 1, 0]])) & ~m
    rgb[ring] = BO.OUTLINE
    img = np.zeros((32, 32, 4), np.uint8)
    mm = m | ring
    img[mm, :3] = rgb[mm]
    img[mm, 3] = 255
    return img


def grid_labels(g):
    lab = g.copy()
    m = g != " "
    ring = ndimage.binary_dilation(m, np.array([[0, 1, 0], [1, 1, 1], [0, 1, 0]])) & ~m
    lab[ring] = "o"
    return lab


def clear_hat(view, hands):
    """Mão que cairia dentro do chapéu largo vai para fora da aba (mesmo dx para as duas mãos);
    a ferramenta anda o mesmo dx. Devolve (mãos, dx)."""
    g, _ = base_grid(view)
    hat = ndimage.binary_dilation(np.isin(g, list("yYr")))
    if not any(hat[min(max(y, 0), 31), min(max(x, 0), 31)] for y, x in hands):
        return hands, 0
    xs = np.nonzero(np.isin(g, list("yYr")).any(0))[0]
    cx = (xs.min() + xs.max()) / 2
    hx = np.mean([x for _, x in hands])
    if hx <= cx:
        dx = (xs.min() - 2) - max(x for _, x in hands)
    else:
        dx = (xs.max() + 2) - min(x for _, x in hands)
    if abs(dx) > 10:  # longe demais: deixa a mão onde está (o braço passa por trás da aba)
        return hands, 0
    return [(y, x + dx) for y, x in hands], int(dx)


def act_grids():
    """{vista: [(linha, coluna, grade, dx)]} na ordem das folhas (8 quadros por vista)."""
    H = old_hands()
    out = {v: [] for v in VIEWS}
    for (r, c), hs in sorted(H.items()):
        v = ACT_VIEW[r]
        hs, dx = clear_hat(v, hs)
        out[v].append((r, c, draw_arms(v, hs), dx))
    return out


def sheet(grids, col, path):
    """Folha alinhada 8x como blockout.sheet_base: 12 células, os 8 quadros + os 4 primeiros de novo."""
    order = [g for _, _, g, _ in grids]
    order = (order + order)[:12]
    W, H = 196, 84
    im = Image.new("RGBA", (W, H))
    ox, oy = (W - 192) // 2, (H - 64) // 2
    for k, g in enumerate(order):
        im.alpha_composite(Image.fromarray(grid_frame(g, col)), (ox + 32 * (k % 6), oy + 32 * (k // 6)))
    BO.on_white(im, 8).save(path)


def bases():
    G = act_grids()
    for o, col in (("", BO.COL), ("B", BO.COL_B)):
        for v in VIEWS:
            sheet(G[v], col, HERE / "bases" / f"act{v}{o}_1568x672.png")
            s = Image.new("RGBA", (32 * len(G[v]), 32))
            for i, (_, _, g, _) in enumerate(G[v]):
                s.alpha_composite(Image.fromarray(grid_frame(g, col)), (32 * i, 0))
            s.save(HERE / "out" / f"blockout{o}_act_{v}_32.png")


if __name__ == "__main__":
    if sys.argv[1:] == ["bases"]:
        bases()
    if sys.argv[1:] == ["foice"]:
        foice_bases()
