"""Estilização dos tiles projetados: rampa curta por material e limpeza.

A rampa sai dos quantis de luminância do material inteiro (todas as
variantes juntas), então a emenda continua valendo. Sombra puxa para
roxo/azul, luz para amarelo, como em pixel art feito à mão.
"""

import numpy as np
from PIL import Image

import iso

LUM = np.array([0.299, 0.587, 0.114])
COOL = np.array([70.0, 40.0, 110.0])
WARM = np.array([255.0, 235.0, 150.0])


CONTRAST = 1.0  # < 1 aproxima os tons da base


def ramp_from(tiles, cuts=(0.12, 0.68, 0.92), shift=0.18, mask=None):
    """Cores da rampa: média de cada faixa de luminância, com desvio de matiz.

    tiles: lista de Image RGBA 32x32. mask: bool 32x32 dos pixels considerados.
    Devolve (limiares de luminância, cores).
    """
    m = iso.top_mask() if mask is None else mask
    px = np.concatenate([np.asarray(t.convert("RGB"), float)[m] for t in tiles])
    lum = px @ LUM
    th = np.quantile(lum, cuts)
    idx = np.searchsorted(th, lum)
    cols = []
    n = len(cuts) + 1
    for k in range(n):
        c = px[idx == k].mean(0) if (idx == k).any() else px.mean(0)
        t = k / (n - 1)  # 0 = mais escuro
        if t < 0.5:
            c = c * (1 - shift * (1 - 2 * t)) + COOL * shift * (1 - 2 * t) * 0.5
        else:
            c = c * (1 - shift * (2 * t - 1) * 0.6) + WARM * shift * (2 * t - 1) * 0.6
        cols.append(c)
    cols = np.array(cols)
    if CONTRAST != 1.0:
        b = cols[min(1, len(cols) - 1)]
        cols = b + (cols - b) * CONTRAST
    return th, cols


def apply_ramp(tile, th, cols, mask):
    a = np.asarray(tile.convert("RGBA")).copy()
    rgb = a[..., :3].astype(float)
    idx = np.searchsorted(th, rgb @ LUM)
    out = cols[idx].round().clip(0, 255).astype(np.uint8)
    a[..., :3][mask] = out[mask]
    return Image.fromarray(a)


def clean(tile, mask, margin=2, passes=2):
    """Troca pixel isolado (nenhum vizinho 8 igual) pela cor mais comum ao redor.
    Só no miolo: pixels a menos de `margin` da borda da máscara ficam."""
    a = np.asarray(tile.convert("RGBA")).copy()
    inner = mask.copy()
    for _ in range(margin):
        e = inner.copy()
        e[1:, :] &= inner[:-1, :]
        e[:-1, :] &= inner[1:, :]
        e[:, 1:] &= inner[:, :-1]
        e[:, :-1] &= inner[:, 1:]
        inner = e
    key = (a[..., 0].astype(int) << 16) | (a[..., 1].astype(int) << 8) | a[..., 2]
    for _ in range(passes):
        new = key.copy()
        for y, x in zip(*np.nonzero(inner)):
            nb = key[y - 1:y + 2, x - 1:x + 2].ravel()
            nb = np.delete(nb, 4)
            if (nb == key[y, x]).sum() == 0:
                vals, cnt = np.unique(nb, return_counts=True)
                new[y, x] = vals[cnt.argmax()]
        key = new
    a[..., 0], a[..., 1], a[..., 2] = (key >> 16) & 255, (key >> 8) & 255, key & 255
    return Image.fromarray(a)


def stylize(tiles, cuts=(0.12, 0.68, 0.92), side_cuts=(0.3, 0.75), shift=0.18, cleanup=True):
    """Aplica rampa ao topo e às laterais (rampas separadas) e limpa."""
    top = iso.top_mask()
    sides = iso.left_mask() | iso.right_mask()
    th, cols = ramp_from(tiles, cuts, shift, top)
    ths, colss = darken_sides(ramp_from(tiles, side_cuts, shift, sides), (th, cols))
    out = []
    for t in tiles:
        t = apply_ramp(t, th, cols, top)
        t = apply_ramp(t, ths, colss, sides)
        if cleanup:
            t = clean(t, top)
        out.append(t)
    return out


def stats(tiles):
    """Cores no topo e fração da cor dominante (medida do advisor)."""
    top = iso.top_mask()
    px = np.concatenate([np.asarray(t.convert("RGB"))[top] for t in tiles])
    vals, cnt = np.unique(px, axis=0, return_counts=True)
    return len(vals), cnt.max() / cnt.sum()


def material_mask(corners, seed, amp):
    """Máscara 32x32 (True = terreno B) no centro de cada pixel do topo, e nas
    laterais o terreno do ponto da aresta logo acima."""
    import project
    ys, xs = np.mgrid[0:32, 0:32]
    px, py = xs + 0.5, ys + 0.5
    u, v = project._uv_top(px, py)
    top = iso.top_mask()
    m = np.zeros((32, 32), bool)
    m[top] = project.corner_mask(np.clip(u[top], 0, 1), np.clip(v[top], 0, 1), corners, seed, amp)
    for face, edge_y in ((iso.left_mask(), lambda x: 16 + x / 2 - 0.01),
                         (iso.right_mask(), lambda x: 24 - (x - 16) / 2 - 0.01)):
        uu, vv = project._uv_top(px[face], edge_y(px[face]))
        m[face] = project.corner_mask(np.clip(uu, 0, 1), np.clip(vv, 0, 1), corners, seed, amp)
    return m


def stylize_transition(tile, mb, ramp_a, ramp_b, side_a, side_b, edge=True, margin=1):
    """Rampa de cada material conforme a máscara; A (grama) é o mais alto.
    edge: pixel de A com B logo abaixo vira tom escuro de A, e o B embaixo
    dele vira o tom mais escuro de B (sombra do degrau)."""
    top = iso.top_mask()
    sides = iso.left_mask() | iso.right_mask()
    t = tile
    t = apply_ramp(t, *ramp_a, top & ~mb)
    t = apply_ramp(t, *ramp_b, top & mb)
    t = apply_ramp(t, *side_a, sides & ~mb)
    t = apply_ramp(t, *side_b, sides & mb)
    a = np.asarray(t).copy()
    if edge:
        ca, cb = ramp_a[1], ramp_b[1]
        for y in range(8, 23):
            for x in range(32):
                if not top[y, x] or mb[y, x] or not top[y + 1, x] or not mb[y + 1, x]:
                    continue
                a[y, x, :3] = ca[1].round()  # borda da grama: um tom abaixo da base
                a[y + 1, x, :3] = cb[0].round()  # sombra na terra
    return Image.fromarray(a)


def darken_sides(sramp, ramp, factor=0.62):
    """Escala a rampa lateral para a média dela ficar em `factor` da base do topo."""
    th, cols = sramp
    base = ramp[1][1] @ LUM
    mean = cols.mean(0) @ LUM
    k = min(1.0, factor * base / max(mean, 1))
    return th, cols * k + COOL * (1 - k) * 0.25


def ramp_like(ramp, ref_tiles, mask=None, keep=0.25):
    """Troca as cores da rampa pelas dos quantis equivalentes de tiles de
    referência (ex.: a grama original), mantendo `keep` da cor própria."""
    th, cols = ramp
    n = len(cols)
    m = iso.top_mask() if mask is None else mask
    px = np.concatenate([np.asarray(t.convert("RGB"), float)[m] for t in ref_tiles])
    lum = px @ LUM
    order = np.argsort(lum)
    chunks = np.array_split(px[order], n)
    ref = np.array([c.mean(0) for c in chunks])
    return th, ref * (1 - keep) + cols * keep


def edge_dist():
    """Distância (px de tela, aprox.) de cada pixel do topo à aresta do losango."""
    import project
    ys, xs = np.mgrid[0:32, 0:32]
    u, v = project._uv_top(xs + 0.5, ys + 0.5)
    d = np.minimum.reduce([u, 1 - u, v, 1 - v])
    return d * 16  # aresta de 32 px na tela ~ 16 px de "altura" do losango


def calm_edges(tile, ramp, px=1.0):
    """Na faixa de `px` da aresta, troca os tons extremos da rampa pela base:
    a faixa é igual em todos os tiles e qualquer marca nela vira padrão."""
    th, cols = ramp
    a = np.asarray(tile.convert("RGBA")).copy()
    band = iso.top_mask() & (edge_dist() < px)
    rgb = a[..., :3].astype(int)
    c = cols.round().astype(int)
    for extreme in (0, len(c) - 1):
        hit = band & (np.abs(rgb - c[extreme]).sum(-1) == 0)
        a[..., :3][hit] = c[min(1, len(c) - 1)]
    return Image.fromarray(a)
