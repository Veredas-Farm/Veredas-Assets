"""Projeta texturas vistas de cima em tiles isométricos 32x32 (bloco de 8 px).

A geometria vem de iso.py, então o tile sempre encaixa na grade do Godot.
A face de cima amostra a textura de topo; as laterais amostram uma textura
de corte (solo) ou, sem ela, a própria textura de topo escurecida.

Uso como biblioteca:
    tiles = project_set(top, side, grid=4, colors=8)  # 16 tiles, tile[(i, j)]
O tile (i, j) amostra o quadrado (i, j) de uma grade grid x grid da textura,
então colocar o tile (x % grid, y % grid) na célula (x, y) não tem emenda se
a textura for contínua nas bordas (wrap).
"""

import numpy as np
from PIL import Image

import iso

SS = 8  # superamostragem
SIZE = 32

# Sombra das laterais: escurece e puxa para roxo, como no atlas atual.
SHADOW = np.array([60.0, 30.0, 70.0])


def _uv_top(px, py):
    """Ponto (px, py) da célula 32x32 -> (u, v) no losango de cima, 0..1.

    Vértices: topo (16, 8), direita (32, 16), esquerda (0, 16), baixo (16, 24).
    u cresce do topo para a direita, v do topo para a esquerda.
    """
    dx, dy = px - 16.0, py - 8.0
    return (dx / 16 + dy / 8) / 2, (dy / 8 - dx / 16) / 2


def _sample(tex, u, v):
    """Bilinear com wrap. tex: float HxWx3; u, v em pixels da textura."""
    h, w = tex.shape[:2]
    u0, v0 = np.floor(u).astype(int), np.floor(v).astype(int)
    fu, fv = (u - u0)[..., None], (v - v0)[..., None]
    a = tex[v0 % h, u0 % w]
    b = tex[v0 % h, (u0 + 1) % w]
    c = tex[(v0 + 1) % h, u0 % w]
    d = tex[(v0 + 1) % h, (u0 + 1) % w]
    return (a * (1 - fu) + b * fu) * (1 - fv) + (c * (1 - fu) + d * fu) * fv


def _faces_ss():
    """Máscaras das faces na resolução superamostrada: cada subpixel herda a
    face do pixel final (máscaras canônicas de iso.py), assim todo pixel do
    topo é amostrado só da textura de topo (u, v podem passar um pouco de
    0..1; a amostragem com wrap continua a textura do vizinho)."""
    n = SIZE * SS
    ys, xs = np.mgrid[0:n, 0:n]
    px, py = (xs + 0.5) / SS, (ys + 0.5) / SS
    u, v = _uv_top(px, py)
    up = lambda m: np.repeat(np.repeat(m, SS, 0), SS, 1)
    top = up(iso.top_mask())
    left = up(iso.left_mask())
    right = up(iso.right_mask())
    return px, py, u, v, top, left, right


_FACES = _faces_ss()


def render_ss(top_tex, side_tex, region, side_region=None, depth_px=None, lip=0.0, lip_seed=0):
    """Renderiza o tile superamostrado (SIZE*SS)^2 x 3 e as máscaras.

    region: (x0, y0, s) quadrado da textura de topo que vira a face de cima.
    """
    px, py, u, v, top, left, right = _FACES
    x0, y0, s = region
    out = np.zeros((SIZE * SS, SIZE * SS, 3))
    out[top] = _sample(top_tex, x0 + u[top] * s, y0 + v[top] * s)
    st = side_tex if side_tex is not None else top_tex
    sx0, sy0, ss = side_region or region
    dpx = depth_px or ss / 4  # 8 px de altura = 1/4 da aresta de 32
    # esquerda: parâmetro ao longo da aresta (0..1) e profundidade (0..8 px)
    sl = px[left] / 16
    tl = (py[left] - (16 + px[left] / 2)) / 8
    cl = _sample(st, sx0 + sl * ss, sy0 + tl * dpx)
    sr = (px[right] - 16) / 16
    tr = (py[right] - (24 - (px[right] - 16) / 2)) / 8
    cr = _sample(st, sx0 + ss + sr * ss, sy0 + tr * dpx)
    if side_tex is None:
        cl, cr = cl * 0.55 + SHADOW * 0.2, cr * 0.4 + SHADOW * 0.25
    else:
        cl, cr = cl * 0.85, cl.mean() * 0 + cr * 0.65
    if lip > 0:
        # borda do terreno de cima descendo pela lateral, com contorno irregular
        # (periódico na aresta: igual para todos os tiles)
        rng = np.random.default_rng(lip_seed)
        def lipdepth(t):
            n = sum(a * np.sin(2 * np.pi * (f * t) + rng.uniform(0, 6.3)) for f, a in ((2, .5), (5, .35), (9, .25)))
            return lip * (1 + 0.6 * n)
        ml = tl * 8 < lipdepth(sl)
        mr = tr * 8 < lipdepth(sr + 1)
        # cor: textura de cima na aresta correspondente, escurecida
        el = _sample(top_tex, x0 + sl * s, y0 + s - 1e-3 + 0 * sl)
        er = _sample(top_tex, x0 + s - 1e-3 + 0 * sr, y0 + (1 - sr) * s)
        cl[ml] = el[ml] * 0.78
        cr[mr] = er[mr] * 0.62
    out[left], out[right] = cl, cr
    return out


def downsample(ss_img, mode="kcentroid"):
    """(SIZE*SS)^2 -> SIZE^2, uma cor por célula, sem misturar faces."""
    _, _, _, _, top, left, right = _FACES
    face = np.zeros(top.shape, int)
    face[left], face[right] = 1, 2
    face[~(top | left | right)] = -1
    # a face de cada pixel final vem das máscaras canônicas (iso.py)
    lo = np.full((SIZE, SIZE), -1)
    lo[iso.top_mask()] = 0
    lo[iso.left_mask()] = 1
    lo[iso.right_mask()] = 2
    res = np.zeros((SIZE, SIZE, 3))
    for y in range(SIZE):
        for x in range(SIZE):
            blk = ss_img[y * SS:(y + 1) * SS, x * SS:(x + 1) * SS].reshape(-1, 3)
            fb = face[y * SS:(y + 1) * SS, x * SS:(x + 1) * SS].reshape(-1)
            f = lo[y, x]
            if f < 0:
                continue
            if (fb == f).any():
                blk = blk[fb == f]
            elif (fb >= 0).any():
                blk = blk[fb >= 0]
            if mode == "mean":
                res[y, x] = blk.mean(0)
            else:  # k-centroid: cor do maior grupo de um 2-means
                lum = blk.mean(1)
                m = lum >= np.median(lum)
                a, b = blk[m], blk[~m]
                if len(b) == 0 or len(a) == 0:
                    res[y, x] = blk.mean(0)
                else:
                    res[y, x] = (a if len(a) >= len(b) else b).mean(0)
    return res


def quantize(imgs, colors):
    """Paleta comum de `colors` cores para uma lista de RGB float (median cut)."""
    stack = np.concatenate([i.reshape(-1, 3) for i in imgs])[None].clip(0, 255).astype(np.uint8)
    pal_img = Image.fromarray(stack).quantize(colors, method=Image.Quantize.MEDIANCUT, dither=0)
    out = []
    for i in imgs:
        q = Image.fromarray(i.clip(0, 255).astype(np.uint8)).quantize(palette=pal_img, dither=0)
        out.append(np.asarray(q.convert("RGB")).astype(float))
    return out


def to_rgba(rgb):
    a = np.zeros((SIZE, SIZE, 4), np.uint8)
    a[..., :3] = rgb.clip(0, 255).astype(np.uint8)
    a[..., 3] = np.where(iso.block_mask(), 255, 0)
    return iso.snap_tile(Image.fromarray(a, "RGBA"))


def project_set(top, side=None, grid=4, colors=8, mode="kcentroid", side_scale=None, lip=0.0):
    """Tiles {(i, j): Image} de uma grade grid x grid da textura de topo."""
    t = np.asarray(top.convert("RGB"), float)
    s = np.asarray(side.convert("RGB"), float) if side is not None else None
    step = t.shape[1] / grid
    raws = {}
    for j in range(grid):
        for i in range(grid):
            # i anda no eixo u (x do Godot), j no eixo v (y do Godot)
            ss_img = render_ss(t, s, (i * step, j * step, step),
                               side_region=(i * step, 0, side_scale or step) if s is not None else None, lip=lip)
            raws[(i, j)] = downsample(ss_img, mode)
    keys = list(raws)
    q = quantize([raws[k] for k in keys], colors) if colors else [raws[k] for k in keys]
    return {k: to_rgba(v) for k, v in zip(keys, q)}


def make_seamless(img, band=0.15):
    """Deixa a textura contínua nas bordas: mistura com a cópia deslocada meia volta."""
    a = np.asarray(img.convert("RGB"), float)
    h, w = a.shape[:2]
    sh = np.roll(a, (h // 2, w // 2), (0, 1))
    y = np.minimum(np.arange(h), h - 1 - np.arange(h)) / (h * band)
    x = np.minimum(np.arange(w), w - 1 - np.arange(w)) / (w * band)
    wgt = np.clip(np.minimum(y[:, None], x[None, :]), 0, 1)[..., None]
    return Image.fromarray((a * wgt + sh * (1 - wgt)).astype(np.uint8))


# --- transições (terreno por cantos, 16 tiles) ---------------------------

def periodic_noise(u, v, seed=0, octaves=((1, 1.0), (2, 0.5), (3, 0.35), (5, 0.2))):
    """Ruído suave com período 1 em u e v: igual nas bordas opostas do tile,
    então vizinhos com os mesmos cantos casam na aresta."""
    rng = np.random.default_rng(seed)
    n = np.zeros_like(u)
    for f, amp in octaves:
        for _ in range(3):
            a, b = rng.integers(-f, f + 1, 2)
            if a == 0 and b == 0:
                continue
            ph = rng.uniform(0, 2 * np.pi)
            n += amp * np.sin(2 * np.pi * (a * u + b * v) + ph)
    return n / 3


def edge_noise(u, v, seed=0):
    """Ruído que some nas quatro arestas: a fronteira entre terrenos cruza a
    aresta exatamente no meio, igual para qualquer vizinho."""
    w = np.sin(np.pi * u) * np.sin(np.pi * v)
    return periodic_noise(u, v, seed) * w


def corner_mask(u, v, corners, seed=0, amp=0.35):
    """corners = (topo, direita, baixo, esquerda) do losango, 1 = terreno B.

    No espaço (u, v): topo = (0,0), direita = (1,0), baixo = (1,1), esquerda = (0,1).
    """
    t, r, b, l = corners
    f = t * (1 - u) * (1 - v) + r * u * (1 - v) + b * u * v + l * (1 - u) * v
    return f + amp * edge_noise(u, v, seed) > 0.5


def project_transition(tex_a, tex_b, corners, region, side=None, seed=0, amp=0.35, shadow=0.0):
    """Tile superamostrado misturando dois terrenos pela máscara dos cantos.
    As laterais usam o terreno do ponto da aresta logo acima.
    shadow > 0: B fica mais baixo; escurece B logo abaixo da borda de A (em px)."""
    px, py, u, v, top, left, right = _FACES
    a = render_ss(tex_a, side, region)
    b = render_ss(tex_b, side, region)
    m = np.zeros(top.shape, bool)
    m[top] = corner_mask(u[top], v[top], corners, seed, amp)
    ul, vl = _uv_top(px[left], 16 + px[left] / 2 - 0.01)
    m[left] = corner_mask(np.clip(ul, 0, 1), np.clip(vl, 0, 1), corners, seed, amp)
    ur, vr = _uv_top(px[right], 24 - (px[right] - 16) / 2 - 0.01)
    m[right] = corner_mask(np.clip(ur, 0, 1), np.clip(vr, 0, 1), corners, seed, amp)
    out = np.where(m[..., None], b, a)
    if shadow > 0:
        # ponto um pouco acima na tela; se for A, a borda de A faz sombra aqui
        us, vs = _uv_top(px[top], py[top] - shadow)
        above_a = ~corner_mask(np.clip(us, 0, 1), np.clip(vs, 0, 1), corners, seed, amp)
        sh = np.zeros(top.shape, bool)
        sh[top] = above_a & m[top]
        out[sh] = out[sh] * 0.72 + SHADOW * 0.12
    return out


CORNER_SETS = [tuple(int(c) for c in f"{k:04b}") for k in range(16)]


def project_transitions(tex_a, tex_b, side=None, grid=4, colors=10, seed=0, amp=0.35, cell=(0, 0), shadow=0.0):
    """16 tiles {corners: Image} de A->B. `cell` escolhe a região da textura.
    O ruído da fronteira muda por tile (some nas arestas, então casa igual)."""
    ta = np.asarray(tex_a.convert("RGB"), float)
    tb = np.asarray(tex_b.convert("RGB"), float)
    s = np.asarray(side.convert("RGB"), float) if side is not None else None
    step = ta.shape[1] / grid
    region = (cell[0] * step, cell[1] * step, step)
    raws = {}
    for k, c in enumerate(CORNER_SETS):
        sd = seed * 1000 + cell[0] * 97 + cell[1] * 31 + k
        raws[c] = downsample(project_transition(ta, tb, c, region, s, sd, amp, shadow))
    keys = list(raws)
    q = quantize([raws[k] for k in keys], colors) if colors else [raws[k] for k in keys]
    return {k: to_rgba(v) for k, v in zip(keys, q)}


# --- variantes intercambiáveis (borda comum) ------------------------------

def _periodic_patch(tex, x0, y0, s):
    """Recorte s x s da textura tornado periódico (casa consigo nas bordas)."""
    im = Image.fromarray(tex[int(y0):int(y0 + s), int(x0):int(x0 + s)].astype(np.uint8))
    return np.asarray(make_seamless(im, band=0.25), float)


BAND_FLAT = 1.0  # quanto do detalhe a faixa de borda comum mantém (1 = todo)


def _flatten(patch, keep):
    """Suaviza o recorte periódico e puxa para a média (wrap: continua periódico)."""
    from PIL import ImageFilter
    if keep >= 1:
        return patch
    h, w = patch.shape[:2]
    big = np.tile(patch, (3, 3, 1)).clip(0, 255).astype(np.uint8)
    b = np.asarray(Image.fromarray(big).filter(ImageFilter.GaussianBlur(w / 24)), float)[h:2 * h, w:2 * w]
    mean = patch.reshape(-1, 3).mean(0)
    return mean + (b - mean) * keep + (patch - b) * keep * 0.5


def project_variants(top, side=None, n=8, band=0.3, colors=12, seed=0, grid=4):
    """n tiles do mesmo terreno que encaixam em qualquer arranjo.

    Perto das arestas todos amostram o mesmo recorte periódico (borda comum);
    no miolo, cada variante amostra um recorte diferente da textura.
    """
    t = np.asarray(top.convert("RGB"), float)
    step = t.shape[1] / grid
    edge = _flatten(_periodic_patch(t, 0, 0, step), BAND_FLAT)
    sd = None
    if side is not None:
        sv = np.asarray(side.convert("RGB"), float)
        sd = _periodic_patch(sv, 0, 0, min(step, sv.shape[0]))
    px, py, u, v, top_m, left, right = _FACES
    d = np.minimum.reduce([u, 1 - u, v, 1 - v])
    w = np.clip(1 - d / band, 0, 1)[..., None]  # 1 na aresta, 0 no miolo
    base = render_ss(edge, sd, (0, 0, edge.shape[0]))
    rng = np.random.default_rng(seed)
    raws = []
    for k in range(n):
        if k == 0:
            raws.append(downsample(base))
            continue
        x0, y0 = rng.uniform(0, t.shape[1] - step, 2)
        inner = render_ss(_periodic_patch(t, x0, y0, step), sd, (0, 0, step))
        mix = base.copy()
        mix[top_m] = (base * w + inner * (1 - w))[top_m]
        raws.append(downsample(mix))
    q = quantize(raws, colors) if colors else raws
    return [to_rgba(r) for r in q]


def banded_transitions(top_a, top_b, side=None, grid=4, seed=0, amp=0.35):
    """16 transições (sem quantizar) que usam o mesmo recorte periódico das
    bordas de project_variants: casam com as variantes puras em qualquer ordem."""
    ta = np.asarray(top_a.convert("RGB"), float)
    tb = np.asarray(top_b.convert("RGB"), float)
    step = ta.shape[1] / grid
    ea = _flatten(_periodic_patch(ta, 0, 0, step), BAND_FLAT)
    eb = _flatten(_periodic_patch(tb, 0, 0, step), BAND_FLAT)
    sd = None
    if side is not None:
        sv = np.asarray(side.convert("RGB"), float)
        sd = _periodic_patch(sv, 0, 0, min(step, sv.shape[0]))
    out = {}
    for k, c in enumerate(CORNER_SETS):
        s = seed * 1000 + k
        raw = downsample(project_transition(ea, eb, c, (0, 0, ea.shape[0]), sd, s, amp))
        out[c] = (to_rgba(raw), s)
    return out


# --- água: bloco rebaixado -------------------------------------------------

def lowered(tile, drop=4, side_keep=4):
    """Desce a face de cima `drop` px (o topo do bloco fica mais baixo que o
    vizinho) e encurta a lateral para `side_keep` px. Os vizinhos atrás
    mostram a própria lateral acima da água: vira margem."""
    a = np.asarray(tile.convert("RGBA"))
    out = np.zeros_like(a)
    top = iso.top_mask()
    sides = iso.left_mask() | iso.right_mask()
    # topo deslocado para baixo
    ys, xs = np.nonzero(top)
    out[ys + drop, xs] = a[ys, xs]
    # laterais: só as `side_keep` primeiras linhas abaixo da aresta, deslocadas
    for y, x in zip(*np.nonzero(sides)):
        edge = 16 + x / 2 if x < 16 else 24 - (x - 16) / 2
        d = y - edge
        if d < side_keep and y + drop < 32 and not out[y + drop, x, 3]:
            out[y + drop, x] = a[y, x]
    return Image.fromarray(out)


def shore(tile, land, drop=4, foam=1.6, shallow=5.0, seed=0):
    """Tile de água rebaixada (saída de `lowered`) com espuma e raso nas
    arestas que tocam terra. land = (u0, u1, v0, v1): vizinhos (x-1, y),
    (x+1, y), (x, y-1), (x, y+1). Distâncias em px de tela; a ondulação some
    nos vértices, então tiles vizinhos da mesma margem casam."""
    a = np.asarray(tile.convert("RGBA")).astype(float)
    top = np.zeros((SIZE, SIZE), bool)
    top[drop:] = iso.top_mask()[:SIZE - drop]
    ys, xs = np.mgrid[0:SIZE, 0:SIZE]
    u, v = _uv_top(xs + 0.5, ys - drop + 0.5)
    # arestas de baixo: o bloco vizinho (desenhado depois) cobre a faixa
    # rebaixada; a borda visível é a do losango sem deslocamento
    uo, vo = _uv_top(xs + 0.5, ys + 0.5)
    rng = np.random.default_rng(seed)
    d = np.full((SIZE, SIZE), 99.0)
    for on, dist, along in ((land[0], u, v), (land[1], 1 - uo, vo), (land[2], v, u), (land[3], 1 - vo, uo)):
        if on:
            k, ph = rng.integers(1, 3), rng.random() * 0.0
            wob = np.sin(np.pi * along) * (1.0 + 1.0 * np.sin(2 * np.pi * k * along + ph))
            d = np.minimum(d, dist * 16 - wob)
    rgb = a[..., :3]
    lum = rgb @ [0.3, 0.59, 0.11]
    light = rgb[top][lum[top].argmax()]
    foam_c = light * 0.4 + 255 * 0.6
    shal_c = light * 0.75 + np.array([210, 235, 225]) * 0.25
    f = top & (d < foam)
    s = top & (d >= foam) & (d < shallow)
    rgb[s] = rgb[s] * 0.45 + shal_c * 0.55
    rgb[f] = foam_c
    a[..., :3] = rgb
    return Image.fromarray(a.clip(0, 255).astype(np.uint8))
