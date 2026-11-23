#!/usr/bin/env python3
"""Variantes (b) das árvores com fases, sem gerar: remontagem geométrica do sprite.

Uso: variantes.py [arvore...]    grava out/variantes/arvore_<arvore>_b_<fase>{,_repix}.png/.json
                                 e out/variantes_preview.png (a x b por fase, 3x, sobre grama)
     variantes.py --c-prep [arvore...]  variante c: base 8x (specs/bases/<arvore>_b_8x.png) e máscara
                                 do envelope novo (specs/masks/<arvore>_c.png); depois aig import + gen.py
     variantes.py --c [arvore...]  reduz as gerações (C_RUNS) em out/variantes/arvore_<arvore>_c_<fase>
     variantes.py --objetos      grava out/variantes/<objeto>_{b,c,esp}.png/.json (cupinzeiros, pilão,
                                 carro de boi) e out/variantes_objetos_preview.png
     variantes.py --entrega      copia as árvores para entrega/objetos/fases/ e os objetos para
                                 entrega/objetos/objects/

Entrada: entrega/objetos/fases/arvore_<arvore>_<fase>.png (as fases aprovadas). Todas as fases
de uma árvore têm o mesmo tronco e a mesma tela, então a mesma transformação de coordenadas
aplicada a cada fase dá fases coerentes na variante (mesmo tronco, silhueta, tela e anchor).

Transformação (mapa inverso, vizinho mais próximo, só ampliações: nada some, galho fino
não quebra):
- espelho com reluz: espelha e depois corrige a parte assimétrica da luz (campo de luminância
  borrado, componente esquerda-direita), trocando cada pixel pela cor da própria paleta da
  fase com o brilho corrigido. A luz continua vindo do mesmo lado do original.
- tronco: as linhas entre a base da copa e as raízes são esticadas (+N linhas).
- copa: escala horizontal (>= 1) em torno do eixo do tronco, que cresce de 1 na base da copa
  até `sx` 10 linhas acima (sem degrau na forquilha); escala vertical `sy` (>= 1).
- inclinação: o tronco entorta `lean` px entre o chão e a base da copa; a copa vai inteira.
A base da copa vem das próprias fases: linha mais baixa onde alguma fase difere das outras.
"""
import json
import shutil
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import pipeline as P  # noqa: E402

SRC = HERE.parent / "entrega" / "objetos" / "fases"  # destino (e a das prévias)
A_SRC = HERE / "out" / "objects"  # fases a (saída do phases.py, = entrega sem os frutos pintados)
OUT = HERE / "out" / "variantes"
PREVIEW = HERE / "out" / "variantes_preview.png"

PHASES = {
    "ipe_amarelo": ["florido", "verde", "seco", "brotando"],
    "ipe_roxo": ["florido", "verde", "seco", "brotando"],
    "cagaita": ["maduro", "florida", "fruto_verde", "folhada"],
    "pequi": ["maduro", "florida", "fruto_verde", "folhada"],
    "baru": ["folhado", "florida", "maduro"],
}

# receita da variante b por árvore
RECIPES = {
    "ipe_amarelo": {"mirror": True, "trunk": 7, "sx": 1.12, "sy": 1.0, "lean": 3},
    "ipe_roxo": {"mirror": True, "trunk": 5, "sx": 1.0, "sy": 1.1, "lean": -3},
    "cagaita": {"mirror": True, "trunk": 6, "sx": 1.15, "sy": 1.0, "lean": 2},
    "pequi": {"mirror": True, "trunk": 5, "sx": 1.1, "sy": 1.0, "lean": -2},
    "baru": {"mirror": True, "trunk": 6, "sx": 1.0, "sy": 1.06, "lean": 3},
}
ROOTS = 5  # linhas de raiz (acima do chão) que não esticam


def lum(c):
    return c[..., 0] * 0.3 + c[..., 1] * 0.59 + c[..., 2] * 0.11


def load_phases(tree, suf=""):
    return {ph: np.asarray(Image.open(A_SRC / f"arvore_{tree}_{ph}{suf}.png").convert("RGBA")).copy()
            for ph in PHASES[tree]}


def crown_bottom(imgs):
    a = list(imgs.values())
    d = np.zeros(a[0].shape[:2], bool)
    for x in a[1:]:
        d |= np.abs(x.astype(int) - a[0].astype(int)).sum(-1) > 0
    return int(np.nonzero(d.any(1))[0].max())


def light_asym(a):
    """Componente antissimétrica (esquerda-direita) da luminância borrada, no quadro de `a`."""
    H, W = a.shape[:2]
    m = a[..., 3] > 0
    L = lum(a[..., :3].astype(float))
    sig = max(W, H) / 8
    S = ndimage.gaussian_filter(L * m, sig) / np.maximum(ndimage.gaussian_filter(m.astype(float), sig), 1e-3)
    return (S - S[:, ::-1]) / 2


def relight_mirror(a, k=1.0, thr=3.0, A=None):
    """Espelha `a` e devolve a luz esquerda-direita do original (ver docstring do módulo).
    `A`: campo de luz a usar (o da fase base, para todas as fases saírem iguais)."""
    m = a[..., 3] > 0
    A = light_asym(a) if A is None else A
    b = a[:, ::-1].copy()
    mb = b[..., 3] > 0
    delta = 2 * k * A
    pal = np.unique(a[m][:, :3], axis=0).astype(float)
    sel = mb & (np.abs(delta) >= thr)
    c = b[sel][:, :3].astype(float)
    Lc = np.maximum(lum(c), 1.0)
    tgt = np.clip(c * ((Lc + delta[sel]) / Lc)[:, None], 0, 255)
    idx = ((tgt[:, None, :] - pal[None]) ** 2).sum(-1).argmin(1)
    b[sel, :3] = pal[idx].astype(np.uint8)
    return b


def make_map(shape, cb, ground, anchor, r):
    """Mapa inverso (ys, xs) da tela nova para a original e o anchor novo."""
    H, W = shape
    sx, sy, add, lean = r["sx"], r["sy"], r["trunk"], r["lean"]
    t0, t1 = cb + 1, ground - ROOTS + 1  # trecho do tronco que estica: [t0, t1)
    hc = int(round(t0 * sy))  # copa (linhas 0..t0-1) -> 0..hc-1
    ht = (t1 - t0) + add
    Hn = hc + ht + (H - t1)
    src_y = np.empty(Hn, int)
    for Y in range(Hn):
        if Y < hc:
            src_y[Y] = t0 - 1 - int((hc - 1 - Y) / sy)
        elif Y < hc + ht:
            src_y[Y] = t0 + int((Y - hc) * (t1 - t0) / ht)
        else:
            src_y[Y] = t1 + Y - hc - ht
    ground_n = ground + (Hn - H)
    cb_n = hc - 1
    # eixo do tronco na base da copa
    cx = anchor[0]
    extra_w = int(np.ceil((W / 2) * (sx - 1))) + abs(lean) + 1
    Wn = W + 2 * extra_w
    ys = np.repeat(src_y[:, None], Wn, 1)
    xs = np.empty((Hn, Wn), float)
    X = np.arange(Wn) - extra_w
    for Y in range(Hn):
        f = np.clip((ground_n - Y) / max(ground_n - cb_n, 1), 0, 1)
        shift = int(round(lean * f))
        s = 1 + (sx - 1) * np.clip((cb_n - Y) / 10, 0, 1)
        xs[Y] = cx + (X - shift - cx) / s
    xs = np.floor(xs + 0.5).astype(int)
    return ys, xs, (anchor[0] + extra_w, anchor[1] + (Hn - H)), extra_w


def apply_map(a, ys, xs):
    H, W = a.shape[:2]
    ok = (xs >= 0) & (xs < W) & (ys >= 0) & (ys < H)
    out = np.zeros((*ys.shape, 4), np.uint8)
    out[ok] = a[ys[ok], xs[ok]]
    return out


def trim_w(imgs, anchor):
    """Corta colunas vazias (iguais em todas as fases) dos lados, mantendo o anchor."""
    occ = np.zeros(next(iter(imgs.values())).shape[1], bool)
    for a in imgs.values():
        occ |= (a[..., 3] > 0).any(0)
    xs = np.nonzero(occ)[0]
    x0, x1 = max(xs.min() - 1, 0), xs.max() + 2
    return {k: a[:, x0:x1] for k, a in imgs.items()}, (anchor[0] - x0, anchor[1])

# ---------------------------------------------------------------- frutos do pequi pintados
#
# Nas gerações os frutos do pequi saem com 2-3 px (maduro) ou somem no verde (fruto_verde).
# Pinta frutos redondos de 6-7 px, com luz em cima à esquerda e contorno embaixo/direita, nas
# MESMAS posições no maduro e no fruto_verde de cada variante (o fruto verde amadurece no lugar).

FRUIT = {  # contorno, sombra, meio, luz
    "maduro": [(104, 56, 22), (206, 120, 30), (238, 166, 40), (252, 214, 100)],
    "fruto_verde": [(58, 50, 22), (172, 170, 72), (214, 212, 112), (242, 240, 176)],
}
FRUIT_N = {"a": 6, "b": 6, "c": 7}


def fruit_sprite(d, cols):
    r = d / 2
    a = np.zeros((d + 1, d, 4), np.uint8)
    for y in range(d):
        for x in range(d):
            dx, dy = x + 0.5 - r, y + 0.5 - r
            e = (dx * dx + dy * dy) / (r * r)
            if e > 1.0:
                continue
            k = -(dx + dy) / r  # luz de cima à esquerda
            edge = e > 0.62 and (dx + dy) > 0.3 * r
            c = cols[0] if edge else (cols[3] if k > 0.75 else (cols[2] if k > -0.45 else cols[1]))
            a[y + 1, x] = (*c, 255)
    a[0, d // 2] = (*cols[0], 255)  # pedúnculo
    return a


def fruit_spots(imgs, n, seed, d):
    """Posições (y, x) do canto do fruto: dentro da copa (janela quase toda opaca na fase de
    referência), metade de baixo da copa, afastadas entre si."""
    ref = imgs["maduro"]
    cb = crown_bottom(imgs)
    op = ref[..., 3] > 0
    ys = np.nonzero(op[: cb + 1].any(1))[0]
    top = ys.min()
    cov = ndimage.uniform_filter(op.astype(float), d + 2)
    cand = np.argwhere(cov > 0.93)
    cand = cand[(cand[:, 0] > top + 0.3 * (cb - top)) & (cand[:, 0] < cb - d)]
    rng = np.random.default_rng(seed)
    rng.shuffle(cand)
    out = []
    for y, x in cand:
        if all((y - py) ** 2 + (x - px) ** 2 > (2.2 * d) ** 2 for py, px in out):
            out.append((y, x))
        if len(out) == n:
            break
    return [(y - d // 2, x - d // 2) for y, x in out]


def paint_fruits(imgs, tag, seed=7):
    """imgs: {fase: RGBA} de uma variante do pequi; pinta maduro e fruto_verde."""
    d = 7 if tag == "c" else 6
    spots = fruit_spots(imgs, FRUIT_N[tag], seed, d)
    for ph in ("maduro", "fruto_verde"):
        spr = fruit_sprite(d, FRUIT[ph])
        a = imgs[ph]
        for y, x in spots:
            m = spr[..., 3] > 0
            sub = a[y - 1:y - 1 + spr.shape[0], x:x + d]
            sub[m[: sub.shape[0], : sub.shape[1]]] = spr[: sub.shape[0], : sub.shape[1]][m[: sub.shape[0], : sub.shape[1]]]
    return imgs


def frutos_a():
    """Variante a do pequi com frutos: lê out/objects, grava out/variantes/arvore_pequi_<fase>."""
    for suf in ("", "_repix"):
        imgs = load_phases("pequi", suf)
        imgs = paint_fruits(imgs, "a")
        for ph in ("maduro", "fruto_verde"):
            Image.fromarray(imgs[ph]).save(OUT / f"arvore_pequi_{ph}{suf}.png")
            shutil.copy(A_SRC / f"arvore_pequi_{ph}{suf}.json", OUT / f"arvore_pequi_{ph}{suf}.json")



def build(tree, suf=""):
    r = RECIPES[tree]
    imgs = load_phases(tree, suf)
    meta0 = json.loads((A_SRC / f"arvore_{tree}_{PHASES[tree][0]}{suf}.json").read_text())
    anchor = list(meta0["anchor"])
    H, W = next(iter(imgs.values())).shape[:2]
    cb = crown_bottom(imgs)
    ground = max(int(np.nonzero((a[..., 3] > 0).any(1))[0].max()) for a in imgs.values())
    if r["mirror"]:
        # mesmo campo de luz (da fase base) em todas as fases; o que é igual em todas as fases
        # (tronco) vem da fase base reluzida, para continuar idêntico
        same = np.ones((H, W), bool)
        first = imgs[PHASES[tree][0]]
        for a in imgs.values():
            same &= (a == first).all(-1)
        A = light_asym(first)
        imgs = {k: relight_mirror(a, A=A) for k, a in imgs.items()}
        same = same[:, ::-1]
        for k in imgs:
            imgs[k][same] = imgs[PHASES[tree][0]][same]
        anchor[0] = W - 1 - anchor[0]
    ys, xs, anc, _ = make_map((H, W), cb, ground, anchor, r)
    out = {k: apply_map(a, ys, xs) for k, a in imgs.items()}
    out, anc = trim_w(out, anc)
    if tree == "pequi":
        out = paint_fruits(out, "b")
    OUT.mkdir(parents=True, exist_ok=True)
    for ph, a in out.items():
        fn = f"arvore_{tree}_b_{ph}{suf}"
        Image.fromarray(a).save(OUT / f"{fn}.png")
        meta = {"anchor": [int(anc[0]), int(anc[1])], "variant": meta0.get("variant"),
                "from": f"arvore_{tree}_{ph}{suf}.png", "recipe": r}
        (OUT / f"{fn}.json").write_text(json.dumps(meta))
    return out


# ---------------------------------------------------------------- variante c (copa nova por inpaint)
#
# Base: a fase base da b ampliada 8x (nearest) numa tela branca 1024 (specs/bases/<arvore>_b_8x.png,
# `aig import`). Máscara: um envelope de copa NOVO (superelipse mais larga/baixa/deslocada que a
# copa da b), acima da base da copa; o tronco abaixo fica fora. A copa da b fora do envelope é
# apagada da base. Cada fase: 1 inpaint (template moss) com a mesma base e máscara, outra seed.
# Redução como em phases.build_sprite: box 8x8 na janela da tela c, paleta da fase b
# correspondente, tronco da b colado fora da máscara. Mesma tela e anchor em todas as fases.

BASES = HERE / "specs" / "bases"
MASKS = HERE / "specs" / "masks"
RUNS = HERE.parent / "runs"
TMP = HERE / "tmp"

C_ENV = {  # envelope: escala da largura e da altura da copa b, deslocamento x (px do sprite), expoente
    "pequi": {"w": 1.18, "h": 0.82, "dx": 3, "n": 3.0, "pad": 8},
    "ipe_amarelo": {"w": 1.0, "h": 1.0, "dx": -4, "n": 2.2, "pad": 6},
    "baru": {"w": 1.0, "h": 0.8, "dx": 0, "n": 3.2, "pad": 6},
    "cagaita": {"w": 1.2, "h": 0.85, "dx": -2, "n": 3.0, "pad": 8},
    "ipe_roxo": {"w": 1.22, "h": 0.8, "dx": 3, "n": 3.0, "pad": 10},
}
C_RUNS = {  # fase -> geração (glob em runs/)
    "pequi": {"maduro": "o50/pequi_c-maduro-*.png", "florida": "o51/pequi_c-florida-*.png",
              "fruto_verde": "o66/pequi_c-fruto_verde-*.png", "folhada": "o53/pequi_c-folhada-*.png"},
    "ipe_amarelo": {"florido": "o65/ipe_amarelo_c-florido2-*.png", "verde": "o55/ipe_amarelo_c-verde-*.png",
                    "seco": "o56/ipe_amarelo_c-seco-*.png", "brotando": "o57/ipe_amarelo_c-brotando-*.png"},
    "baru": {"folhado": "o58/baru_c-folhado-*.png", "florida": "o59/baru_c-florida-*.png",
             "maduro": "o60/baru_c-maduro-*.png"},
    "cagaita": {"maduro": "o61/cagaita_c-maduro-*.png", "florida": "o62/cagaita_c-florida-*.png",
                "fruto_verde": "o67/cagaita_c-fruto_verde2-*.png", "folhada": "o68/cagaita_c-folhada2-*.png"},
}


def c_geometry(tree):
    """Tela c (b com margem), posição na 1024, base da copa e envelope (máscara no sprite)."""
    b = {ph: np.asarray(Image.open(OUT / f"arvore_{tree}_b_{ph}.png").convert("RGBA")) for ph in PHASES[tree]}
    e = C_ENV[tree]
    pad = e["pad"]
    b = {k: np.pad(a, ((pad, 0), (pad, pad), (0, 0))) for k, a in b.items()}
    H, W = next(iter(b.values())).shape[:2]
    cb = crown_bottom(b)
    occ = np.zeros((H, W), bool)
    for a in b.values():
        occ |= a[..., 3] > 0
    ys, xs = np.nonzero(occ[: cb + 1])
    y0, x0, x1 = ys.min(), xs.min(), xs.max()
    cx = (x0 + x1) / 2 + e["dx"]
    hw = (x1 - x0 + 1) / 2 * e["w"]
    bot = cb + 1 - e.get("lift", 0)
    top = bot - (cb + 1 - y0) * e["h"]
    yy, xx = np.mgrid[0:H, 0:W]
    yc, hh = (top + bot) / 2, (bot - top) / 2
    env = (np.abs((xx + 0.5 - cx) / hw) ** e["n"] + np.abs((yy + 0.5 - yc) / hh) ** e["n"]) <= 1
    env[cb + 1:] = False
    # o que muda entre fases (copa, pétalas caídas) e fica fora do envelope é apagado
    diff = np.zeros((H, W), bool)
    first = next(iter(b.values()))
    for a in b.values():
        diff |= (a != first).any(-1)
    b = {k: a.copy() for k, a in b.items()}
    for a in b.values():
        a[diff & ~env] = 0
    ox, oy = (1024 - W * 8) // 2, (1024 - H * 8) // 2
    meta = json.loads((OUT / f"arvore_{tree}_b_{PHASES[tree][0]}.json").read_text())
    anc = [meta["anchor"][0] + pad, meta["anchor"][1] + pad]
    return b, env, cb, (ox, oy), anc


def _hsv(rgb):
    return np.asarray(Image.fromarray(rgb.reshape(1, -1, 3).astype(np.uint8)).convert("HSV")).reshape(-1, 3).astype(float)


def _leaf(h):
    return (h[:, 0] >= 40) & (h[:, 0] <= 120) & (h[:, 1] > 60)  # verdes (escala 0-255 do PIL)


def match_crown(rgb, region, ref, env):
    """Folhas da copa gerada (verdes, saturadas) com média e desvio de H, S e V das folhas da
    fase b. Fruto, flor e vagem (fora da faixa de verde) ficam como estão e a paleta resolve."""
    rm = (ref[..., 3] > 128) & env
    if not region.any() or not rm.any():
        return rgb
    r = _hsv(ref[..., :3][rm])
    r = r[_leaf(r)]
    src = _hsv(rgb[region])
    lf = _leaf(src)
    if len(r) < 20 or lf.sum() < 20:
        return rgb
    x = src[lf]
    src[lf] = np.clip((x - x.mean(0)) / (x.std(0) + 1e-6) * r.std(0) + r.mean(0), 0, 255)
    out = Image.fromarray(src.reshape(1, -1, 3).astype(np.uint8), "HSV").convert("RGB")
    res = rgb.copy()
    res[region] = np.asarray(out).reshape(-1, 3)
    return res


def bark_partial(a, fixed):
    """Como phases.bark_ramp, só nos galhos (pixels marrons/pouco saturados) da copa: folhas e
    flores ficam. O inpaint pinta os galhos de marrom-rosado e o tronco é oliva."""
    s = a.copy()
    op = s[..., 3] > 0
    h = _hsv(s[..., :3].reshape(-1, 3)).reshape(*s.shape[:2], 3)
    branch = op & ~fixed & ((h[..., 0] < 25) | (h[..., 0] > 200) | (h[..., 1] < 70))
    trunk = s[op & fixed][:, :3].astype(float)
    ramp = trunk[np.argsort(lum(trunk))]
    L = lum(s[branch][:, :3].astype(float))
    q = np.argsort(np.argsort(L)) / max(len(L) - 1, 1)
    s[branch, :3] = ramp[(q * 0.75 * (len(ramp) - 1)).astype(int)].astype(np.uint8)
    return s


def c_prepare(tree):
    b, env, cb, (ox, oy), _ = c_geometry(tree)
    base = b[PHASES[tree][0]].copy()
    H, W = base.shape[:2]
    keep = np.ones((H, W), bool)
    keep[: cb + 1] = env[: cb + 1]  # apaga a copa da b fora do envelope
    base[~keep] = 0
    canvas = Image.new("RGB", (1024, 1024), (255, 255, 255))
    spr = Image.fromarray(base).resize((W * 8, H * 8), Image.NEAREST)
    canvas.paste(spr, (ox, oy), spr)
    BASES.mkdir(parents=True, exist_ok=True)
    canvas.save(BASES / f"{tree}_b_8x.png")
    m = np.zeros((1024, 1024), bool)
    m[oy:oy + H * 8, ox:ox + W * 8] = np.kron(env, np.ones((8, 8), bool))
    m = ndimage.binary_dilation(m, iterations=8)
    m[oy + (cb + 1) * 8:] = False
    Image.fromarray((m * 255).astype(np.uint8)).save(MASKS / f"{tree}_c.png")
    vis = np.asarray(canvas).copy()
    vis[m] = (vis[m] * 0.5 + np.array([255, 0, 0]) * 0.5).astype(np.uint8)
    TMP.mkdir(exist_ok=True)
    Image.fromarray(vis).resize((512, 512)).save(TMP / f"mask_{tree}_c.png")


def _find(pat):
    hits = sorted(RUNS.glob(pat), key=lambda p: p.stat().st_mtime)
    return hits[-1] if hits else None


def c_build(tree):
    P.HOLE_MIN, P.PAL_TOL = 300, 0
    b, env, cb, (ox, oy), anc = c_geometry(tree)
    H, W = next(iter(b.values())).shape[:2]
    base_img = np.asarray(Image.open(BASES / f"{tree}_b_8x.png").convert("RGB"))
    cmask = np.asarray(Image.open(MASKS / f"{tree}_c.png")) > 127
    win = (oy, oy + H * 8, ox, ox + W * 8)
    fixed = ~P.down_mask(cmask[win[0]:win[1], win[2]:win[3]], (W, H))
    fixed = ndimage.binary_erosion(fixed, iterations=1, border_value=1)
    trunk = b[PHASES[tree][0]].copy()
    trunk[: cb + 1][~env[: cb + 1]] = 0
    import phases as PH
    OUT.mkdir(parents=True, exist_ok=True)
    for suf, var in {"": "box", "_repix": "repix"}.items():
        res = {}
        for ph in PHASES[tree]:
            src = _find(C_RUNS[tree].get(ph, "-"))
            if not src:
                continue
            rgb = PH.blend_phase(base_img, np.asarray(Image.open(src).convert("RGB")), cmask, 8)
            obj, _ = P.remove_bg(rgb)
            y0, y1, x0, x1 = win
            small, m = P.VARIANTS[var](rgb[y0:y1, x0:x1], obj[y0:y1, x0:x1], 8, 24)
            if small.shape[:2] != (H, W):
                small = np.asarray(Image.fromarray(small).resize((W, H), Image.NEAREST))
                m = P.down_mask(m, (W, H))
            m = P.clean_mask(m)
            # o inpaint sai mais claro e amarelado que o sprite: casa as folhas com as da fase b
            # antes da paleta (sem isso o verde vira amarelo)
            a_ph = b[ph]
            small = match_crown(small, m & ~fixed, a_ph, env)
            small = P.quantize(small, m, 24)
            pal = np.unique(a_ph[a_ph[..., 3] > 128][:, :3], axis=0)
            small = P.map_palette(small, m, pal, 0)
            a = np.asarray(P.to_rgba(small, m)).copy()
            a[fixed] = trunk[fixed]
            lab, n = ndimage.label(a[..., 3] > 0, np.ones((3, 3)))  # tira pedaços soltos (folha pendurada fora do envelope)
            if n > 1:
                sz = ndimage.sum(np.ones(lab.shape), lab, range(1, n + 1))
                a[np.isin(lab, [i + 1 for i, z in enumerate(sz) if z < 12])] = 0
            if tree.startswith("ipe") and ph == "seco":
                a = PH.bark_ramp(a, fixed)
            elif tree.startswith("ipe") and ph == "brotando":
                a = bark_partial(a, fixed)
            res[ph] = a
        if not res:
            continue
        res, anc2 = trim_w(res, anc)
        if tree == "pequi" and {"maduro", "fruto_verde"} <= set(res):
            res = paint_fruits(res, "c")
        for ph, a in res.items():
            fn = f"arvore_{tree}_c_{ph}{suf}"
            Image.fromarray(a).save(OUT / f"{fn}.png")
            (OUT / f"{fn}.json").write_text(json.dumps({
                "anchor": [int(anc2[0]), int(anc2[1])], "variant": var,
                "from": f"inpaint {_find(C_RUNS[tree][ph]).relative_to(RUNS)} sobre arvore_{tree}_b_{PHASES[tree][0]}",
                "scale": 8}))


# ---------------------------------------------------------------- objetos de 1 sprite

OBJ_SRC = HERE.parent / "entrega" / "objetos" / "objects"
# nome da variante: (sprite de origem, espelho com reluz, sx, sy). Só ampliação (>= 1).
OBJECTS = {
    "cupinzeiro_alto_b": ("cupinzeiro_alto", True, 1.0, 1.25),
    "cupinzeiro_alto_c": ("cupinzeiro_alto", False, 1.2, 1.0),
    "cupinzeiro_baixo_b": ("cupinzeiro_baixo", True, 1.25, 1.0),
    "cupinzeiro_baixo_c": ("cupinzeiro_baixo", False, 1.0, 1.3),
    "pilao_b": ("pilao", True, 1.0, 1.0),
    "carro_de_boi_esp": ("carro_de_boi", True, 1.0, 1.0),
}


def obj_variant(src, mirror, sx, sy):
    a = np.asarray(Image.open(OBJ_SRC / f"{src}.png").convert("RGBA")).copy()
    anc = list(json.loads((OBJ_SRC / f"{src}.json").read_text())["anchor"])
    H, W = a.shape[:2]
    if mirror:
        a = relight_mirror(a)
        anc[0] = W - 1 - anc[0]
    Hn, Wn = int(round(H * sy)), int(round(W * sx))
    ys = (H - 1 - np.floor((Hn - 1 - np.arange(Hn)) / sy)).astype(int)  # base fixa
    xs = np.floor(anc[0] + (np.arange(Wn) - anc[0] * sx) / sx + 0.5).astype(int)
    out = a[np.clip(ys, 0, H - 1)][:, np.clip(xs, 0, W - 1)]
    out[:, (xs < 0) | (xs >= W)] = 0
    return out, [int(round(anc[0] * sx)), anc[1] + Hn - H]


def cupinzeiro_duplo():
    """Alto na frente, baixo espelhado atrás e à esquerda (mesma luz)."""
    alto, aa = obj_variant("cupinzeiro_alto", False, 1.0, 1.0)
    baixo, ab = obj_variant("cupinzeiro_baixo", True, 1.0, 1.0)
    dx, dy = -13, -3  # pé do baixo em relação ao pé do alto
    x0 = min(0, aa[0] + dx - ab[0])
    y0 = min(0, aa[1] + dy - ab[1])
    W = max(alto.shape[1], aa[0] + dx - ab[0] + baixo.shape[1]) - x0
    H = max(alto.shape[0], aa[1] + dy - ab[1] + baixo.shape[0]) - y0
    c = Image.new("RGBA", (W, H))
    bimg = Image.fromarray(baixo)
    c.alpha_composite(bimg, (aa[0] + dx - ab[0] - x0, aa[1] + dy - ab[1] - y0))
    c.alpha_composite(Image.fromarray(alto), (-x0, -y0))
    return np.asarray(c), [aa[0] - x0, aa[1] - y0]


def build_objects():
    OUT.mkdir(parents=True, exist_ok=True)
    res = {}
    for name, (src, mir, sx, sy) in OBJECTS.items():
        res[name] = (src, *obj_variant(src, mir, sx, sy), {"mirror": mir, "sx": sx, "sy": sy})
    res["cupinzeiro_duplo"] = ("cupinzeiro_alto+cupinzeiro_baixo", *cupinzeiro_duplo(), {"compose": True})
    for name, (src, a, anc, r) in res.items():
        Image.fromarray(a).save(OUT / f"{name}.png")
        (OUT / f"{name}.json").write_text(json.dumps({"anchor": anc, "from": src, "recipe": r}))
    # prévia: original e variantes, 4x
    groups = {}
    for name, (src, *_rest) in res.items():
        groups.setdefault(src.split("+")[0], []).append(name)
    ims = []
    for src, names in groups.items():
        ims.append(Image.open(OBJ_SRC / f"{src}.png"))
        ims += [Image.open(OUT / f"{n}.png") for n in names]
        ims.append(None)
    W = sum((i.width if i else 8) + 4 for i in ims)
    H = max(i.height for i in ims if i) + 8
    c = Image.new("RGBA", (W, H), P.GRASS)
    x = 4
    for i in ims:
        if i:
            c.alpha_composite(i, (x, H - 4 - i.height))
        x += (i.width if i else 8) + 4
    c.resize((W * 4, H * 4), Image.NEAREST).save(HERE / "out" / "variantes_objetos_preview.png")
    return res


def preview(trees, zoom=3):
    rows = []
    for t in trees:
        for tag, pat in (("a", f"arvore_{t}_{{}}.png"), ("b", f"arvore_{t}_b_{{}}.png"),
                         ("c", f"arvore_{t}_c_{{}}.png")):
            def pick(ph):
                if tag == "a":
                    return OUT / pat.format(ph) if (OUT / pat.format(ph)).exists() else A_SRC / pat.format(ph)
                return OUT / pat.format(ph)
            r = [(ph, Image.open(pick(ph))) for ph in PHASES[t] if pick(ph).exists()]
            if r:
                rows.append((f"{t} {tag}", r))
    cw = max(im.width for _, r in rows for _, im in r) + 8
    W = 8 + cw * max(len(r) for _, r in rows)
    hs = [max(im.height for _, im in r) + 14 for _, r in rows]
    prev = Image.new("RGBA", (W, sum(hs)), P.GRASS)
    y = 0
    for (_, r), h in zip(rows, hs):
        for k, (_, im) in enumerate(r):
            prev.alpha_composite(im, (8 + k * cw + (cw - 8 - im.width) // 2, y + h - 2 - im.height))
        y += h
    big = prev.resize((W * zoom, prev.height * zoom), Image.NEAREST)
    dr = ImageDraw.Draw(big)
    f = P.font(14)
    y = 0
    for (label, r), h in zip(rows, hs):
        dr.text((6, y * zoom + 2), label, fill=(255, 255, 255), font=f)
        for k, (ph, _) in enumerate(r):
            dr.text(((8 + k * cw) * zoom, y * zoom + 18), ph, fill=(240, 240, 200), font=f)
        y += h
    big.save(PREVIEW)


def entrega(trees):
    for p in OUT.glob("arvore_pequi_[mf]*"):  # a do pequi com frutos pintados
        shutil.copy(p, SRC / p.name)
    for t in trees:
        for ph in PHASES[t]:
            for suf, tag in ((s, g) for s in ("", "_repix") for g in ("b", "c")):
                for ext in ("png", "json"):
                    p = OUT / f"arvore_{t}_{tag}_{ph}{suf}.{ext}"
                    if p.exists():
                        shutil.copy(p, SRC / p.name)


if __name__ == "__main__":
    args = sys.argv[1:]
    if args and args[0] == "--entrega":
        entrega(args[1:] or list(PHASES))
        for n in [*OBJECTS, "cupinzeiro_duplo"]:
            for ext in ("png", "json"):
                shutil.copy(OUT / f"{n}.{ext}", OBJ_SRC / f"{n}.{ext}")
    elif args and args[0] == "--c-prep":  # base 8x + máscara do envelope (depois: aig import)
        for t in args[1:] or list(C_ENV):
            c_prepare(t)
    elif args and args[0] == "--c":  # reduz as gerações da c (C_RUNS) e refaz a prévia
        for t in args[1:] or list(C_RUNS):
            c_build(t)
        preview(list(PHASES))
    elif args and args[0] == "--objetos":
        build_objects()
    else:
        trees = args or list(PHASES)
        for t in trees:
            build(t)
            build(t, "_repix")
        if "pequi" in trees:
            frutos_a()
        preview(trees)
