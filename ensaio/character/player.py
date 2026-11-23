#!/usr/bin/env python3
"""Folhas finais do fazendeiro nos layouts do jogo (c21+).

out/farmer_Player[_B].png          192x320, mesmo layout de old_assets/Player/Player.png:
    linhas 0-2 parado (frente, lado, costas, 6 quadros), 3-5 andando (6), 6-8 foice (4), 9 desmaio (4)
out/farmer_Player_Actions[_B].png  96x576, mesmo layout de Player_Actions.png (2 x 12 células 48x48):
    picareta, machado, enxada (lado, frente, costas) e regador (frente, costas, lado)
out/farmer_Player[_Actions][_B].gif, out/preview.png, out/preview_actions.png

Corpo: folhas c21-c26 (manequim -> moss img2img 0.55 -> sheet8.py), cores travadas na paleta
do manequim por material (lock). Ferramentas, mãos e rastros: pixels recortados da folha original
(o que difere do quadro parado da mesma vista e não é cor do corpo antigo).
Uso: player.py
"""
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "objects"))
import blockout as BO  # noqa: E402
import pipeline as P  # noqa: E402

OUT = HERE / "out"
OLD = Path("/home/chips/git/games/Veredas-Farm/old_assets/Player")
GRASS = (122, 150, 84, 255)
OUTLINE = np.array(BO.OUTLINE)
VIEWS = ("front", "side", "back")  # down, side, up no jogo

# gerações (out/cells/<nome>.cells.png) por roupa e vista
GEN = {
    "A": {"front": "p6front-055", "side": "p6side-055", "back": "p6back-055"},
    "B": {"front": "p6frontB-055", "side": "p6sideB-055", "back": "p6backB-055"},
}
# frente/costas: folha = [parado, passo A, cruza, passo B] x 3; índice escolhido por pose (à vista)
PICK = {("A", "front"): {"idle": 0, "A": 1, "P": 6, "B": 3}, ("B", "front"): {"idle": 0, "A": 1, "P": 6, "B": 3}}

# seed escolhida quando há mais de uma geração do mesmo nome (c42 refez a frente B das ações)
SEED = {"actfrontB-055": "701942359", "foiceside-055": "1348472654"}
# foice: índice na folha (4 quadros x 3) para cada quadro, quando a 1ª cópia tem defeito
FIDX = {("A", "side"): [0, 1, 6, 3]}

MAT = {"y": "straw", "Y": "straw", "r": "band", "h": "hair", "S": "skin", "s": "skin",
       "R": "shirt", "q": "shirt", "B": "pants", "d": "pants", "k": "boots", "K": "boots"}
MATS = sorted(set(MAT.values()))


def lum(c):
    c = np.asarray(c, float)
    return c[..., 0] * 0.299 + c[..., 1] * 0.587 + c[..., 2] * 0.114


def ramps(col):
    """Rampa de cada material: cores do manequim + 1 tom mais escuro e 1 mais claro."""
    out = {}
    for m in MATS:
        if m.startswith('_'):
            continue
        cs = sorted({col[k] for k, v in MAT.items() if v == m}, key=lum)
        dark = [tuple(int(v * f) for v in cs[0]) for f in (0.5, 0.75)]
        light = tuple(int(v + (255 - v) * 0.3) for v in cs[-1])
        out[m] = np.array(dark + cs + [light], float)
    return out


def lock(rgba, lab, col, R=None, weighted=False):
    """Troca cada pixel da figura pela cor mais próxima da rampa do seu material.

    O material vem do manequim (rótulo no mesmo lugar ou num vizinho 3x3, a geração anda até 1 px).
    Antes de comparar, o brilho da geração é normalizado por material e quadro: cabelo preto de
    uma seed e castanho de outra caem no mesmo tom do manequim."""
    a = rgba.copy()
    rgb = a[..., :3].astype(float)
    fig = a[..., 3] == 255
    line = fig & (a[..., :3] == OUTLINE).all(-1)
    mi = np.full(lab.shape, -1)
    for k, v in MAT.items():
        mi[lab == k] = MATS.index(v)
    _, (iy, ix) = ndimage.distance_transform_edt(mi < 0, return_indices=True)
    own = np.where(mi >= 0, mi, mi[iy, ix])
    R = R or ramps(col)
    T = R.get("_t", {})
    L = lum(rgb)
    fac = {}
    for j, m in enumerate(MATS):
        sel = fig & ~line & (own == j)
        target = np.mean([lum(col[k]) for k in MAT if MAT[k] == m and (lab == k).any()] or [lum(R[m][1])])
        if weighted and np.isin(lab, [k for k in MAT if MAT[k] == m]).any():  # média por pixel do manequim (npc.py)
            target = float(np.mean([lum(col[c]) for c in lab[np.isin(lab, [k for k in MAT if MAT[k] == m])]]))
        # só o cabelo varia de cor entre seeds; nos outros materiais a geração já segue o manequim
        # cabelo: sempre ao brilho do manequim. Outros materiais: ao brilho mediano da roupa nas 3 vistas,
        # só quando o quadro foge mais de 20% (ex.: calça quase preta no lado B, c24)
        fac[j] = 1.0
        if sel.sum() >= 3:
            med = max(np.median(L[sel]), 1)
            if m == "hair":
                fac[j] = float(np.clip(target / med, 0.6, 2.5))
            elif m in T and not 0.8 <= T[m] / med <= 1.25:
                fac[j] = float(np.clip(T[m] / med, 0.6, 2.5))
    # material pintado de preto pela seed (cabelo ou calça escuros): o sheet8 já trocou por contorno.
    # Se mais de 30% do material dentro da figura é contorno, esses pixels voltam a ser o material.
    inner = fig  # o contorno do manequim é o anel 'o', fora dos rótulos de material
    for j, m in enumerate(MATS):
        zone = inner & (mi == j)
        dark = zone & line
        if zone.sum() >= 4 and dark.sum() > 0.3 * zone.sum():
            a[dark, :3] = R[m][len(R[m]) // 2]
            rgb[dark] = R[m][len(R[m]) // 2] / fac[j]
            L[dark] = lum(rgb[dark])
            line = line & ~dark
    H, W = lab.shape
    for y, x in zip(*np.nonzero(fig & ~line)):
        cand = {own[y, x]}
        for yy in range(max(y - 1, 0), min(y + 2, H)):
            for xx in range(max(x - 1, 0), min(x + 2, W)):
                if mi[yy, xx] >= 0:
                    cand.add(mi[yy, xx])
        if L[y, x] < 40 and MATS.index("hair") not in cand:  # olho, vinco escuro: cor do contorno
            a[y, x, :3] = OUTLINE
            continue
        best = None
        for j in cand:
            ramp = R[MATS[j]]
            px = np.clip(rgb[y, x] * fac[j], 0, 255)
            d = np.abs(ramp - px).sum(1) + (0 if j == own[y, x] else 40)
            k = int(d.argmin())
            if best is None or d[k] < best[0]:
                best = (d[k], ramp[k])
        a[y, x, :3] = best[1]
    return a


def load_cells(name):
    hits = sorted((OUT / "cells").glob(f"{name}-*.cells.png"))
    if name in SEED and (OUT / "cells" / f"{name}-{SEED[name]}.cells.png").exists():
        hits = [OUT / "cells" / f"{name}-{SEED[name]}.cells.png"]
    if not hits:
        return None
    im = np.asarray(Image.open(hits[-1]).convert("RGBA"))
    return [im[32 * (k // 6):32 * (k // 6) + 32, 32 * (k % 6):32 * (k % 6) + 32] for k in range(12)]


def view_frames(outfit, view):
    """Quadros travados de uma vista: dict nome -> (rgba 32x32, rótulos)."""
    col = BO.COL_B if outfit == "B" else BO.COL
    key = "p6" + view
    rows = BO.SHEETS6[key]
    cells = load_cells(GEN[outfit][view])
    if cells is None:  # sem geração: usa o manequim (para testar o fluxo)
        old = BO.COL
        BO.COL = col
        cells = [np.asarray(BO.frame(r)) for r in rows]
        BO.COL = old
    if view == "side":
        idx = {"idle": 10, "A": 1, "Ah": 2, "P": 3, "B": 4, "Bh": 5, "P2": 6, "F1": 7, "F2": 8, "F3": 9}
    else:
        idx = PICK.get((outfit, view), {"idle": 0, "A": 1, "P": 2, "B": 3})
    out = {}
    for n, k in idx.items():
        lab = BO.frame_labels(rows[k])
        out[n] = (cells[k], lab)
    return out


def _own(lab):
    mi = np.full(lab.shape, -1)
    for k, v in MAT.items():
        mi[lab == k] = MATS.index(v)
    return mi


def kmeans(x, k, it=20):
    x = np.asarray(x, float)
    c = np.quantile(x, np.linspace(0.1, 0.9, k), axis=0, method="nearest") if len(x) >= k else x
    c = x[np.argsort(lum(x))][np.linspace(0, len(x) - 1, k).astype(int)]
    for _ in range(it):
        a = np.abs(x[:, None] - c[None]).sum(-1).argmin(1)
        c = np.array([x[a == i].mean(0) if (a == i).any() else c[i] for i in range(k)])
    return c[np.argsort(lum(c))]


def pooled_ramps(raw, col):
    """Paleta única por roupa: para cada material, k-means das cores da geração em todos os quadros
    das 3 vistas (pixels com o mesmo rótulo no manequim). O cabelo fica com a rampa do manequim
    (é o que muda de cor entre seeds)."""
    R = ramps(col)
    R0 = {m: v.copy() for m, v in R.items()}
    K = {"straw": 4, "band": 2, "skin": 3, "shirt": 4, "pants": 3, "boots": 3}
    pix = {m: [] for m in MATS}
    for fr in raw.values():
        for c, lab in fr.values():
            mi = _own(lab)
            ok = (c[..., 3] == 255) & ~(c[..., :3] == OUTLINE).all(-1) & (lum(c[..., :3]) >= 40)
            # só pixels cuja cor está mais perto da rampa do próprio material (a geração anda 1 px)
            rgb = c[..., :3].astype(float)
            d = np.stack([np.abs(rgb[..., None, :] - R0[m][None, None]).sum(-1).min(-1) for m in MATS], -1)
            ok &= d.argmin(-1) == mi
            for j, m in enumerate(MATS):
                pix[m].append(c[ok & (mi == j)][:, :3])
    R["_t"] = {m: float(np.median(lum(np.concatenate(pix[m])))) for m in K if sum(len(p) for p in pix[m])}
    for m, k in K.items():
        x = np.concatenate(pix[m])
        if len(x) > 4 * k:
            R[m] = kmeans(x, k).round()
    return R


def bob(rgba, lab):
    """Respiração do parado: cabeça e ombros descem 1 px (some a 1ª linha do tronco)."""
    ys = np.nonzero(np.isin(lab, list("Rq")).any(1))[0]
    t = ys.min()  # 1ª linha do tronco
    a = rgba.copy()
    a[1:t + 1] = rgba[0:t]
    a[0] = 0
    return a


def handless(rgba, lab):
    """Tira as mãos do tronco (a ferramenta traz as mãos do sprite original)."""
    ys = np.nonzero(np.isin(lab, list("Rq")).any(1))[0]
    hand = np.isin(lab, list("Ss"))
    hand[:ys.min() + 1] = False
    shirt = np.isin(lab, list("Rq")) & (rgba[..., 3] == 255) & ~(rgba[..., :3] == OUTLINE).all(-1)
    _, (iy, ix) = ndimage.distance_transform_edt(~shirt, return_indices=True)
    a = rgba.copy()
    sel = hand & (a[..., 3] == 255) & ~(a[..., :3] == OUTLINE).all(-1)
    a[sel] = rgba[iy[sel], ix[sel]]
    return a


# --- ferramentas recortadas do original ---
def old_sheets():
    return (np.asarray(Image.open(OLD / "Player.png").convert("RGBA")),
            np.asarray(Image.open(OLD / "Player_Actions.png").convert("RGBA")))


def _body_colors(pl):
    cs = {tuple(c) for c in pl[:96].reshape(-1, 4) if c[3] == 255}
    cs -= {(246, 202, 159, 255), (210, 159, 112, 255), tuple(OUTLINE) + (255,)}
    return cs


def tool_layer(act, idle, body_cols, hands=True):
    """Pixels da ação que não são do corpo antigo: ferramenta, mãos, rastro, água (+ contorno vizinho)."""
    op = act[..., 3] == 255
    diff = (act != idle).any(-1) & op
    isline = op & (act[..., :3] == OUTLINE).all(-1)
    isbody = np.array([[tuple(p) in body_cols for p in row] for row in act]) & op
    keep = diff & ~isbody & ~isline
    # pele = mãos, mas também o rosto antigo quando o corpo da ação anda 1 px: só fica a pele fora
    # da silhueta parada antiga ou o bloco pequeno encostado na ferramenta
    skin = keep & np.isin(act[..., :3].reshape(-1, 3).view([("", act.dtype)] * 3).ravel(),
                          np.array([(246, 202, 159), (210, 159, 112)], act.dtype).view([("", act.dtype)] * 3).ravel()
                          ).reshape(keep.shape)
    tool = keep & ~skin
    sil = ndimage.binary_dilation(idle[..., 3] == 255)
    lab, n = ndimage.label(skin, np.ones((3, 3), bool))
    near = ndimage.binary_dilation(tool, np.ones((3, 3), bool))
    for i in range(1, n + 1):
        c = lab == i
        if not ((~sil[c]).mean() >= 0.5 or (c.sum() <= 8 and (near & c).any())):
            keep &= ~c
    if not hands:  # só a ferramenta: sai a pele e o contorno que só encostava nela
        keep &= ~skin
        line = isline & ndimage.binary_dilation(keep, np.ones((3, 3), bool)) & diff
        line &= ~ndimage.binary_dilation(skin, np.ones((3, 3), bool)) | ndimage.binary_dilation(
            keep, np.array([[0, 1, 0], [1, 1, 1], [0, 1, 0]], bool))
    else:
        line = isline & ndimage.binary_dilation(keep, np.ones((3, 3), bool)) & diff
    lay = np.zeros_like(act)
    m = keep | line
    lay[m] = act[m]
    return lay


def over(base, lay):
    a = Image.fromarray(base)
    a.alpha_composite(Image.fromarray(lay))
    return np.asarray(a)


def pad48(c32):
    a = np.zeros((48, 48, 4), np.uint8)
    a[8:40, 8:40] = c32
    return a


def shift(a, dx):
    out = np.zeros_like(a)
    if dx >= 0:
        out[:, dx:] = a[:, :a.shape[1] - dx]
    else:
        out[:, :dx] = a[:, -dx:]
    return out


def build_actions(outfit, F, R, col, pl, ac, body_cols):
    """Ações 48x48 (c36+): corpo com braço e mão gerados (arms.py, folhas act*), cores travadas;
    só a ferramenta vem do original, deslocada junto com a mão quando a mão saiu de dentro do chapéu,
    e por trás do chapéu (aba e copa cobrem a ferramenta)."""
    import arms
    G = arms.act_grids()
    acts = np.zeros((576, 96, 4), np.uint8)
    for v in VIEWS:
        cells = load_cells(f"act{v}{'' if outfit == 'A' else 'B'}-055")
        vi = VIEWS.index(v)
        old_idle = pad48(pl[32 * vi:32 * vi + 32, 0:32])
        for k, (r, c, g, dx) in enumerate(G[v]):
            lab = arms.grid_labels(g)
            # pose igual à de um quadro anterior (enxada = picareta): usa o mesmo quadro gerado
            k0 = next(i for i, (_, _, g2, _) in enumerate(G[v]) if (g2 == g).all())
            raw = cells[k0] if cells is not None else arms.grid_frame(g, col)
            body = pad48(lock(raw, lab, col, R))
            lay = shift(tool_layer(ac[48 * r:48 * r + 48, 48 * c:48 * c + 48], old_idle, body_cols, hands=False), dx)
            hat = np.zeros((48, 48), bool)
            hat[8:40, 8:40] = ndimage.binary_dilation(np.isin(lab, list("yYr")))
            lay[hat & (body[..., 3] == 255)] = 0
            acts[48 * r:48 * r + 48, 48 * c:48 * c + 48] = over(body, lay)
    return acts


def build(outfit):
    raw = {v: view_frames(outfit, v) for v in VIEWS}
    col = BO.COL_B if outfit == "B" else BO.COL
    R = pooled_ramps(raw, col)
    F = {v: {n: (lock(c, lab, col, R), lab) for n, (c, lab) in fr.items()} for v, fr in raw.items()}
    import arms
    FG = arms.foice_grids()
    pl, ac = old_sheets()
    body_cols = _body_colors(pl)
    sheet = np.zeros((320, 192, 4), np.uint8)

    def put(r, c, f):
        sheet[32 * r:32 * r + 32, 32 * c:32 * c + 32] = f

    for vi, v in enumerate(VIEWS):
        idle, lab = F[v]["idle"]
        b = bob(idle, lab)
        for c, f in enumerate([idle, idle, b, b, idle, idle]):
            put(vi, c, f)
        order = ["A", "Ah", "P", "B", "Bh", "P2"] if v == "side" else ["A", "idle", "P", "B", "idle", "P"]
        for c, n in enumerate(order):
            put(3 + vi, c, F[v][n][0])
        # foice (c43+): corpo com braço gerado (arms.foice_grids) + só a foice e o rastro do original;
        # sem geração, cai no corpo sem mãos + mãos antigas
        cells = load_cells(f"foice{v}{'' if outfit == 'A' else 'B'}-055")
        old_idle = pl[32 * vi:32 * vi + 32, 0:32]
        hl = handless(idle, lab)
        for c, (_, _, g, dx) in enumerate(FG[v]):
            src = pl[32 * (6 + vi):32 * (7 + vi), 32 * c:32 * c + 32]
            if cells is None:
                lay = tool_layer(src, old_idle, body_cols)
                has_hand = (lay[..., :3] == (246, 202, 159)).all(-1).any()
                put(6 + vi, c, over(hl if has_hand else idle, lay))
                continue
            lay = shift(tool_layer(src, old_idle, body_cols, hands=False), dx)
            if not (lay[..., 3] > 0).any():  # quadro de volta ao parado
                put(6 + vi, c, idle)
                continue
            glab = arms.grid_labels(g)
            body = lock(cells[FIDX.get((outfit, v), [0, 1, 2, 3])[c]], glab, col, R)
            hat = ndimage.binary_dilation(np.isin(glab, list("yYr")))
            lay[hat & (body[..., 3] == 255)] = 0
            put(6 + vi, c, over(body, lay))
    for c, n in enumerate(["idle", "F1", "F2", "F3"]):
        put(9, c, F["side"][n][0])
    acts = build_actions(outfit, F, R, col, pl, ac, body_cols)
    return Image.fromarray(sheet), Image.fromarray(acts)


# --- prévias ---
P_ROWS = ["parado frente", "parado lado", "parado costas", "andando frente", "andando lado",
          "andando costas", "foice frente", "foice lado", "foice costas", "desmaio"]
A_ROWS = ["picareta lado", "picareta frente", "picareta costas", "machado lado", "machado frente",
          "machado costas", "enxada lado", "enxada frente", "enxada costas", "regador frente",
          "regador costas", "regador lado"]


def preview(sheets, cell, labels, path, zoom=4):
    """sheets: [(nome, folha)]; cada linha da folha vira uma faixa com as versões empilhadas, 1x e 4x."""
    font = P.font(12)
    lab = 170
    w = sheets[0][1].width
    band = cell * zoom * len(sheets) + 8
    out = Image.new("RGBA", (lab + w + 16 + w * zoom, band * len(labels)), GRASS)
    d = ImageDraw.Draw(out)
    for r, name in enumerate(labels):
        y0 = r * band
        for i, (sn, sh) in enumerate(sheets):
            row = sh.crop((0, cell * r, w, cell * r + cell))
            y = y0 + i * cell * zoom
            d.text((4, y + 4), f"{name} ({sn})", fill=(0, 0, 0, 255), font=font)
            out.alpha_composite(row, (lab, y + (cell * zoom - cell) // 2))
            out.alpha_composite(row.resize((w * zoom, cell * zoom), Image.NEAREST), (lab + w + 16, y))
    out.save(path)


def anim_gif(sheet, cell, anims, path, zoom=4, ms=333):
    """Grade de animações tocando juntas. anims: lista de linhas de (linha, n quadros)."""
    ncol = max(len(r) for r in anims)
    frames = []
    for t in range(12):
        im = Image.new("RGBA", (cell * ncol, cell * len(anims)), GRASS)
        for j, row in enumerate(anims):
            for i, (r, n) in enumerate(row):
                c = t % n
                im.alpha_composite(sheet.crop((cell * c, cell * r, cell * c + cell, cell * r + cell)), (cell * i, cell * j))
        frames.append(im.convert("RGB").resize((im.width * zoom, im.height * zoom), Image.NEAREST))
    frames[0].save(path, save_all=True, append_images=frames[1:], duration=ms, loop=0)


P_ANIMS = [[(0, 6), (1, 6), (2, 6)], [(3, 6), (4, 6), (5, 6)], [(6, 4), (7, 4), (8, 4)], [(9, 4)]]
A_ANIMS = [[(0, 2), (1, 2), (2, 2)], [(3, 2), (4, 2), (5, 2)], [(6, 2), (7, 2), (8, 2)], [(11, 2), (9, 2), (10, 2)]]


def main():
    pl_old = Image.open(OLD / "Player.png").convert("RGBA")
    ac_old = Image.open(OLD / "Player_Actions.png").convert("RGBA")
    ps, acs = [("atual", pl_old)], [("atual", ac_old)]
    for o in "AB":
        p, a = build(o)
        sfx = "" if o == "A" else "_B"
        p.save(OUT / f"farmer_Player{sfx}.png")
        a.save(OUT / f"farmer_Player_Actions{sfx}.png")
        anim_gif(p, 32, P_ANIMS, OUT / f"farmer_Player{sfx}.gif")
        anim_gif(a, 48, A_ANIMS, OUT / f"farmer_Player_Actions{sfx}.gif", ms=500)
        ps.append((o, p))
        acs.append((o, a))
    preview(ps, 32, P_ROWS, OUT / "preview.png")
    preview(acs, 48, A_ROWS, OUT / "preview_actions.png", zoom=3)
    print(OUT / "preview.png")


if __name__ == "__main__":
    main()
