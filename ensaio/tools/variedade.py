"""Variedade do terreno: tons em manchas, camada de decoração e sulcos com ruído.

- tone_tiles: versões de um tile puro com a rampa deslocada (quente/fria).
  O peso do tom vem dos 4 cantos (0/1), interpolado no losango e pontilhado
  com Bayer 4x4 em coordenada de tela; vizinhos dividem os cantos, então a
  mancha é contínua (sem treliça).
- decor_atlas: tiles 32x32 transparentes com tufos, flores, trevos, seixos,
  folhas, gravetos, rachaduras, buracos e poças, para uma TileMapLayer de
  decoração por cima do terreno. `decor_extra` anexa no fim capim alto, touceiras,
  moitas, capim-dourado, chuveirinho, flores do cerrado e brotos (posições antigas fixas).
- rut_tile: sulcos de pneu com deslocamento e largura variando ao longo da
  célula (fixos nas bordas, para emendar), falhas e pixels soltos.
"""
import json
import numpy as np
from PIL import Image

import iso
import project

BAYER = np.array([[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]]) / 16 + 1 / 32

# deslocamento multiplicativo da rampa por tom (R, G, B)
TONES = {
    "grass": {"warm": (1.06, 1.02, 0.86), "cool": (0.92, 0.96, 1.01)},
}
CORNER_ORDER = ("top", "right", "bottom", "left")


def _uv():
    ys, xs = np.mgrid[0:32, 0:32]
    return project._uv_top(xs + 0.5, ys + 0.5), xs, ys


def tone_tiles(tile, ramp_cols, mult):
    """15 tiles (cantos != 0000) do tom `mult`. Devolve {bits: Image}."""
    a = np.asarray(tile.convert("RGBA"))
    (u, v), xs, ys = _uv()
    u, v = np.clip(u, 0, 1), np.clip(v, 0, 1)
    top = iso.top_mask()
    cols = np.round(np.asarray(ramp_cols, float)).astype(int)
    shifted = np.clip(np.round(np.asarray(ramp_cols, float) * np.array(mult)), 0, 255).astype(int)
    idx = np.full((32, 32), -1)
    for i, c in enumerate(cols):
        idx[(np.abs(a[..., :3].astype(int) - c).sum(-1) <= 3) & top] = i
    out = {}
    for k in range(1, 16):
        bits = tuple((k >> j) & 1 for j in range(4))  # top, right, bottom, left
        t, r, b, l = bits
        # bilinear: top (0,0), right (1,0), left (0,1), bottom (1,1)
        w = t * (1 - u) * (1 - v) + r * u * (1 - v) + l * (1 - u) * v + b * u * v
        on = (w > BAYER[ys % 4, xs % 4]) & (idx >= 0)
        o = a.copy()
        o[..., :3][on] = shifted[idx[on]]
        out[bits] = Image.fromarray(o)
    return out


# ---------------------------------------------------------------- decoração

def _put(a, spr, bx, by):
    """Cola spr (RGBA array) com a base (meio de baixo) em (bx, by)."""
    h, w = spr.shape[:2]
    x0, y0 = bx - w // 2, by - h + 1
    for j in range(h):
        for i in range(w):
            if spr[j, i, 3] and 0 <= y0 + j < 32 and 0 <= x0 + i < 32:
                a[y0 + j, x0 + i] = spr[j, i]


def _spot(rng, lo=0.22, hi=0.78):
    u, v = rng.uniform(lo, hi, 2)
    return int(round(16 + (u - v) * 16)), int(round(8 + (u + v) * 8))


def tuft(rng, cols, small=False):
    dark, mid, tip = cols[0], (cols[0] + cols[1]) / 2, cols[3]
    a = np.zeros((7, 9, 4), np.uint8)
    n = int(rng.integers(3, 5 if small else 7))
    for b in range(n):
        s = (b - (n - 1) / 2) / max(1, (n - 1) / 2)
        hg = int(rng.integers(2, 4 if small else 7)) - int(abs(s) * 1.5)
        hg = max(2, hg)
        for i in range(hg):
            x = int(round(4 + s * (1 + i * 0.6)))
            c = tip if i == hg - 1 else (dark if i < 1 else mid)
            if 0 <= x < 9:
                a[6 - i, x] = (*np.round(c).astype(int), 255)
    return a


FLOWER_COLS = [(240, 220, 90), (245, 245, 235), (190, 120, 210), (235, 120, 70), (250, 170, 200)]


def flower(rng, cols):
    a = np.zeros((5, 3, 4), np.uint8)
    fc = FLOWER_COLS[int(rng.integers(len(FLOWER_COLS)))]
    dark = np.round(cols[0]).astype(int)
    a[3, 1] = a[4, 1] = (*dark, 255)
    if rng.random() < 0.5:
        for dx, dy in ((0, -1), (-1, 0), (1, 0), (0, 1)):
            a[1 + dy, 1 + dx] = (*fc, 255)
        a[1, 1] = (250, 200, 60, 255) if fc != (240, 220, 90) else (200, 120, 40, 255)
    else:  # botão de 1 px
        a[2, 1] = (*fc, 255)
    return a


def clover(rng, cols):
    a = np.zeros((3, 5, 4), np.uint8)
    d, l = np.round(cols[0]).astype(int), np.round(cols[2] * 0.85 + cols[3] * 0.15).astype(int)
    for (x, y) in ((1, 0), (3, 0), (0, 1), (2, 1), (4, 1), (1, 2), (3, 2)):
        if rng.random() < 0.8:
            a[y, x] = (*(l if y < 2 else d), 255)
    return a


def pebble(rng, stone):
    w = int(rng.integers(2, 4))
    a = np.zeros((2, w, 4), np.uint8)
    a[0, :] = (*stone[1], 255)
    a[1, :] = (*stone[0], 255)
    a[0, 0] = (*stone[2], 255)
    return a


def leaf(rng):
    c = [(150, 96, 52), (176, 128, 60), (120, 74, 44)][int(rng.integers(3))]
    a = np.zeros((2, 3, 4), np.uint8)
    a[0, 1] = a[1, 0] = a[1, 1] = (*c, 255)
    if rng.random() < 0.5:
        a[0, 2] = (*c, 255)
    return a


def twig(rng):
    c = (96, 66, 44)
    n = int(rng.integers(4, 7))
    a = np.zeros((2, n, 4), np.uint8)
    for i in range(n):
        a[1 if i < n // 2 else 0, i] = (*c, 255)
    return a


def crack(a, rng, dark):
    x, y = _spot(rng, 0.3, 0.7)
    for _ in range(int(rng.integers(4, 8))):
        if 0 <= x < 32 and 0 <= y < 32 and iso.top_mask()[y, x]:
            a[y, x] = (*dark, 255)
        x += int(rng.choice([-1, 1]))
        y += int(rng.integers(0, 2)) * int(rng.choice([-1, 1]))


def hole(a, rng, pcols, wet, water):
    w = int(rng.integers(8, 12))
    hh = 4 + (w > 9)
    cx, cy = 16 + int(rng.integers(-3, 4)), 16 + int(rng.integers(-1, 2))
    for j in range(hh + 1):
        for i in range(w):
            e = ((i + 0.5 - w / 2) / (w / 2)) ** 2 + ((j + 0.5 - hh / 2) / (hh / 2)) ** 2
            x, y = cx - w // 2 + i, cy - hh // 2 + j
            if j < hh and e <= 1.0:
                if wet:
                    c = water[0] if j == 0 else (water[2] if (i + j) % 5 == 0 else water[1])
                else:
                    c = pcols[0] * (0.62 if j <= hh // 2 else 0.8)
                a[y, x] = (*np.round(c).astype(int), 255)
            elif e <= 1.5 and j >= hh // 2:
                a[y, x] = (*np.round(pcols[3]).astype(int), 255)


# ---- variedade extra (anexada no fim do atlas; os tiles antigos não mudam de posição)

STRAW = [(110, 96, 48), (150, 122, 60), (214, 180, 96)]  # haste seca / capim-dourado
GOLD = [(222, 170, 52), (246, 206, 88)]  # capítulo do capim-dourado (sombra, luz)
CERRADO_FLOWERS = [(178, 104, 206), (232, 128, 168), (240, 214, 84), (226, 104, 58), (245, 245, 235)]


def _px(a, x, y, c):
    if 0 <= y < a.shape[0] and 0 <= x < a.shape[1]:
        a[y, x] = (*np.round(c).astype(int), 255)


def tuft_tall(rng, cols, seeds=True):
    """Capim alto: 5-7 folhas finas de 6-10 px, pontas abrindo para fora; algumas com
    espiga (ponta palha)."""
    dark, mid, tip = cols[0], (cols[0] + cols[1]) / 2, cols[3]
    a = np.zeros((11, 11, 4), np.uint8)
    n = int(rng.integers(5, 8))
    for b in range(n):
        s = (b - (n - 1) / 2) / max(1, (n - 1) / 2)
        hg = max(4, int(rng.integers(6, 11)) - int(abs(s) * 3))
        bend = s * rng.uniform(1.5, 3.0)
        for i in range(hg):
            t = i / max(hg - 1, 1)
            x = int(round(5 + s * 1.2 + bend * t * t))
            c = dark if i < 2 else (tip if i >= hg - 2 else mid)
            if seeds and i == hg - 1 and rng.random() < 0.35:
                c = np.array(STRAW[2], float)
            _px(a, x, 10 - i, c)
    return a


def tuft_fan(rng, cols):
    """Tufo deitado para um lado (vento): folhas curvas na mesma direção."""
    dark, mid, tip = cols[0], (cols[0] + cols[1]) / 2, cols[3]
    a = np.zeros((8, 11, 4), np.uint8)
    side = 1 if rng.random() < 0.5 else -1
    n = int(rng.integers(4, 7))
    for b in range(n):
        hg = int(rng.integers(3, 7))
        x0 = 5 + int(rng.integers(-2, 2))
        k = rng.uniform(0.3, 0.9)
        for i in range(hg):
            x = int(round(x0 + side * k * i * i / 3))
            c = dark if i < 1 else (tip if i == hg - 1 else mid)
            _px(a, x, 7 - i, c)
    return a


def moita(rng, cols):
    """Moita baixa: monte denso (elipse) com luz em cima à esquerda, base escura e
    algumas pontas de folha saindo do contorno."""
    w, h = int(rng.integers(7, 11)), int(rng.integers(4, 6))
    a = np.zeros((h + 3, w + 2, 4), np.uint8)
    cx, cy = (w + 2) / 2, 3 + h / 2
    light, mid = cols[3], (cols[0] + cols[1]) / 2
    for y in range(a.shape[0]):
        for x in range(a.shape[1]):
            e = ((x + 0.5 - cx) / (w / 2)) ** 2 + ((y + 0.5 - cy) / (h / 2)) ** 2
            if e > 1.0 or (e > 0.75 and rng.random() < 0.35):
                continue
            ny, nx = (y + 0.5 - cy) / (h / 2), (x + 0.5 - cx) / (w / 2)
            sh = -0.7 * ny - 0.3 * nx + rng.uniform(-0.35, 0.35)  # luz de cima, um pouco da esquerda
            # corpo no tom escuro (o tom médio é o do chão e some); luz só no topo
            c = cols[0] * 0.8 if (sh < -0.5 or e > 0.8 and ny > 0) else (cols[0] if sh < 0.15 else (mid if sh < 0.55 else light))
            _px(a, x, y, c)
    for _ in range(int(rng.integers(2, 5))):  # pontas
        x = int(rng.integers(1, w + 1))
        ys = np.nonzero(a[:, x, 3])[0]
        if len(ys):
            _px(a, x, ys.min() - 1, mid)
            if rng.random() < 0.5:
                _px(a, x + int(rng.choice([-1, 1])), ys.min() - 2, cols[3])
    return a


def capim_dourado(rng):
    """Capim-dourado: hastes finas cor de palha saindo de uma roseta verde, cada uma
    com um capítulo dourado de 1-2 px."""
    a = np.zeros((11, 11, 4), np.uint8)
    n = int(rng.integers(3, 6))
    for b in range(n):
        s = (b - (n - 1) / 2) / max(1, (n - 1) / 2) + rng.uniform(-0.15, 0.15)
        hg = int(rng.integers(5, 10))
        for i in range(hg):
            t = i / max(hg - 1, 1)
            x = int(round(5 + s * (0.3 + 4.0 * t * t)))
            _px(a, x, 10 - i, STRAW[0] if i < hg // 2 else STRAW[1])
        x = int(round(5 + s * 4.3))
        _px(a, x, 10 - hg, GOLD[1])
        if rng.random() < 0.5:
            _px(a, x, 10 - hg + 1, GOLD[0])
    for x in (4, 5, 6):  # roseta
        _px(a, x, 10, (60, 96, 44))
    return a


def chuveirinho(rng, cols):
    """Chuveirinho / sempre-viva: 2-4 hastes verdes com pompom branco de 2x2."""
    a = np.zeros((10, 9, 4), np.uint8)
    n = int(rng.integers(2, 5))
    for b in range(n):
        s = (b - (n - 1) / 2) / max(1, (n - 1) / 2)
        hg = int(rng.integers(4, 8))
        for i in range(hg):
            x = int(round(4 + s * (0.5 + 2.0 * i / hg)))
            _px(a, x, 9 - i, cols[0] if i < 2 else cols[1])
        x, y = int(round(4 + s * 2.5)), 9 - hg
        _px(a, x, y, (246, 246, 236))
        _px(a, x + 1, y, (226, 226, 214))
        _px(a, x, y - 1, (255, 255, 248))
        if rng.random() < 0.5:
            _px(a, x + 1, y - 1, (246, 246, 236))
    return a


def flor_cerrado(rng, cols):
    """Roseta de folhas com 1-3 flores em hastes curtas (roxo, rosa, amarelo, laranja, branco)."""
    a = np.zeros((9, 9, 4), np.uint8)
    for x, y, c in ((2, 8, 0), (3, 7, 1), (4, 8, 0), (5, 7, 1), (6, 8, 0), (3, 8, 1), (5, 8, 1), (4, 7, 2)):
        if rng.random() < 0.85:
            _px(a, x, y, cols[c])
    fc = np.array(CERRADO_FLOWERS[int(rng.integers(len(CERRADO_FLOWERS)))], float)
    for _ in range(int(rng.integers(1, 4))):
        x, hg = int(rng.integers(2, 7)), int(rng.integers(2, 5))
        for i in range(hg):
            _px(a, x, 7 - i, cols[1])
        y = 7 - hg
        _px(a, x, y, fc)
        if rng.random() < 0.6:
            _px(a, x - 1, y, fc * 0.82)
            _px(a, x + 1, y, fc)
            _px(a, x, y - 1, np.minimum(fc * 1.12, 255))
    return a


def broto(rng, cols):
    """Broto: haste de 1-3 px com um par (ou dois) de folhinhas claras."""
    a = np.zeros((6, 5, 4), np.uint8)
    hg = int(rng.integers(1, 4))
    for i in range(hg):
        _px(a, 2, 5 - i, cols[0] if i == 0 else cols[1])
    y = 5 - hg
    light = (cols[2] + cols[3]) / 2
    _px(a, 1, y, cols[3]); _px(a, 3, y, light)
    if rng.random() < 0.5:
        _px(a, 0, y - 1, cols[3]); _px(a, 4, y - 1, light)
    if hg >= 2 and rng.random() < 0.4:
        _px(a, 1, y + 1, cols[2]); _px(a, 3, y + 1, cols[2])
    return a


def touceira(a, rng, cols, n=None):
    """2-3 tufos juntos; os de trás um tom mais escuros, desenhados primeiro."""
    bx, by = _spot(rng, 0.35, 0.65)
    n = n or int(rng.integers(2, 4))
    parts = []
    for k in range(n):
        dx, dy = (0, 0) if k == 0 else (int(rng.integers(-5, 6)), int(rng.integers(-2, 2)))
        parts.append((by + dy, bx + dx))
    for y, x in sorted(parts):
        back = y < by
        c = np.asarray(cols, float) * (0.9 if back else 1.0)
        r = rng.random()
        spr = tuft_tall(rng, c) if r < 0.4 else (tuft_fan(rng, c) if r < 0.6 else tuft(rng, c))
        _put(a, spr, x, y)


def decor_extra(g, d, lu, rng):
    """Tiles novos (capim alto, touceiras, moitas, capim-dourado, chuveirinho, flores, brotos)."""
    out = []

    def new():
        return np.zeros((32, 32, 4), np.uint8)

    def add(on, kind, fill):
        a = new()
        fill(a)
        out.append((Image.fromarray(a), {"on": on, "kind": kind}))

    for on, cols, plan in (
        ("grass", g, [("touceira", 6), ("capim_alto", 4), ("tufo_vento", 3), ("moita", 4), ("capim_dourado", 4),
                      ("chuveirinho", 3), ("flores_cerrado", 5), ("brotos", 4)]),
        ("dry", d, [("touceira", 3), ("capim_alto", 3), ("capim_dourado", 3)]),
        ("lush", lu, [("moita", 3), ("touceira", 3), ("brotos", 2), ("flores_cerrado", 2)]),
    ):
        for kind, n in plan:
            for i in range(n):
                if kind == "touceira":
                    add(on, kind, lambda a: touceira(a, rng, cols))
                elif kind == "capim_alto":
                    def f(a):
                        _put(a, tuft_tall(rng, cols), *_spot(rng, 0.3, 0.7))
                        if rng.random() < 0.5:
                            _put(a, tuft(rng, cols, True), *_spot(rng))
                    add(on, kind, f)
                elif kind == "tufo_vento":
                    add(on, kind, lambda a: [_put(a, tuft_fan(rng, cols), *_spot(rng)) for _ in range(int(rng.integers(1, 3)))])
                elif kind == "moita":
                    def f(a):
                        _put(a, moita(rng, cols), *_spot(rng, 0.35, 0.65))
                        if rng.random() < 0.5:
                            _put(a, (flor_cerrado if rng.random() < 0.5 else broto)(rng, cols), *_spot(rng))
                    add(on, kind, f)
                elif kind == "capim_dourado":
                    def f(a):
                        pts = sorted([_spot(rng, 0.3, 0.7) for _ in range(int(rng.integers(1, 4)))], key=lambda p: p[1])
                        for x, y in pts:
                            _put(a, capim_dourado(rng), x, y)
                        if on != "dry" and rng.random() < 0.5:
                            _put(a, tuft(rng, cols, True), *_spot(rng))
                    add(on, kind, f)
                elif kind == "chuveirinho":
                    def f(a):
                        for x, y in sorted([_spot(rng, 0.3, 0.7) for _ in range(int(rng.integers(1, 3)))], key=lambda p: p[1]):
                            _put(a, chuveirinho(rng, cols), x, y)
                    add(on, kind, f)
                elif kind == "flores_cerrado":
                    def f(a):
                        for x, y in sorted([_spot(rng) for _ in range(int(rng.integers(1, 3)))], key=lambda p: p[1]):
                            _put(a, flor_cerrado(rng, cols), x, y)
                    add(on, kind, f)
                elif kind == "brotos":
                    def f(a):
                        for x, y in sorted([_spot(rng) for _ in range(int(rng.integers(2, 5)))], key=lambda p: p[1]):
                            _put(a, broto(rng, cols), x, y)
                    add(on, kind, f)
    return out


def decor_atlas(ramps, water_pal, n_grass=28, n_dry=10, n_lush=10, n_path=14, n_track=6, extra=True):
    """Devolve (lista de (Image, meta)), meta = {"on": terreno, "kind": ...}."""
    g, d, lu, p = (np.asarray(ramps[k], float) for k in ("grass", "dry", "lush", "path"))
    stone = [tuple(np.round(p[0] * 0.75).astype(int)), tuple(np.round(p[2] * 0.95).astype(int)),
             tuple(np.round(p[3]).astype(int))]
    out = []
    rng = np.random.default_rng(2024)

    def new():
        return np.zeros((32, 32, 4), np.uint8)

    kinds = ["tufos", "tufos", "flores", "trevo", "seixos", "folhas", "misto"]
    for i in range(n_grass):
        k = kinds[i % len(kinds)]
        a = new()
        if k == "tufos":
            for _ in range(int(rng.integers(1, 3))):
                _put(a, tuft(rng, g, small=rng.random() < 0.5), *_spot(rng))
        elif k == "flores":
            for _ in range(int(rng.integers(2, 5))):
                _put(a, flower(rng, g), *_spot(rng))
        elif k == "trevo":
            _put(a, clover(rng, g), *_spot(rng))
            if rng.random() < 0.5:
                _put(a, tuft(rng, g, True), *_spot(rng))
        elif k == "seixos":
            for _ in range(int(rng.integers(1, 4))):
                _put(a, pebble(rng, stone), *_spot(rng))
        elif k == "folhas":
            for _ in range(int(rng.integers(1, 3))):
                _put(a, leaf(rng), *_spot(rng))
            if rng.random() < 0.4:
                _put(a, twig(rng), *_spot(rng))
        else:
            _put(a, tuft(rng, g, True), *_spot(rng))
            _put(a, flower(rng, g), *_spot(rng))
            _put(a, pebble(rng, stone), *_spot(rng))
        out.append((Image.fromarray(a), {"on": "grass", "kind": k}))
    for i in range(n_dry):
        a = new()
        for _ in range(int(rng.integers(1, 3))):
            _put(a, tuft(rng, d, small=rng.random() < 0.4), *_spot(rng))
        if i % 3 == 0:
            _put(a, twig(rng), *_spot(rng))
        out.append((Image.fromarray(a), {"on": "dry", "kind": "tufos"}))
    for i in range(n_lush):
        a = new()
        _put(a, tuft(rng, lu), *_spot(rng))
        if i % 2 == 0:
            _put(a, flower(rng, lu), *_spot(rng))
        else:
            _put(a, clover(rng, lu), *_spot(rng))
        out.append((Image.fromarray(a), {"on": "lush", "kind": "misto"}))
    dark = tuple(np.round(p[0] * 0.8).astype(int))
    for i in range(n_path):
        a = new()
        k = ["seixos", "racha", "folhas", "buraco", "seixos", "poca", "racha"][i % 7]
        if k == "seixos":
            for _ in range(int(rng.integers(2, 5))):
                _put(a, pebble(rng, stone), *_spot(rng))
        elif k == "racha":
            crack(a, rng, dark)
            if rng.random() < 0.5:
                _put(a, pebble(rng, stone), *_spot(rng))
        elif k == "folhas":
            _put(a, leaf(rng), *_spot(rng))
            _put(a, twig(rng), *_spot(rng))
        else:
            hole(a, rng, p, k == "poca", water_pal)
        out.append((Image.fromarray(a), {"on": "path", "kind": k}))
    # capim no meio da estrada (entre os sulcos), ao longo do eixo
    for axis in ("u", "v"):
        for i in range(n_track):
            a = new()
            for _ in range(int(rng.integers(1, 3))):
                s = rng.uniform(0.15, 0.85)
                u, v = (s, 0.5) if axis == "u" else (0.5, s)
                _put(a, tuft(rng, g, small=True), int(round(16 + (u - v) * 16)), int(round(8 + (u + v) * 8)))
            out.append((Image.fromarray(a), {"on": "track_" + axis, "kind": "capim"}))
    # buraco ao lado da marca (os carros desviam dele)
    hr = np.random.default_rng(77)
    for axis in ("u", "v"):
        for side in ("esq", "dir"):
            for wet in (False, True, False):
                out.append((Image.fromarray(rut_hole_decor(axis, side, p, water_pal, wet, hr)),
                            {"on": f"trackhole_{axis}_{side}", "kind": "poca" if wet else "buraco"}))
    if extra:  # rng próprio: não muda os tiles acima
        out += decor_extra(g, d, lu, np.random.default_rng(2025))
    return out


def save_decor(items, outdir):
    cols = 16
    rows = (len(items) + cols - 1) // cols
    atlas = Image.new("RGBA", (cols * 32, rows * 32), (0, 0, 0, 0))
    meta = []
    for k, (im, m) in enumerate(items):
        atlas.paste(im, ((k % cols) * 32, (k // cols) * 32))
        meta.append({"atlas": [k % cols, k // cols], **m})
    atlas.save(outdir / "decor_atlas.png")
    (outdir / "decor_atlas.json").write_text(json.dumps({"tiles": meta}, indent=1))
    return atlas


def decor_tres(meta, res_path):
    lines = ['[gd_resource type="TileSet" load_steps=3 format=3]', "",
             f'[ext_resource type="Texture2D" path="{res_path}" id="1_decor"]', "",
             '[sub_resource type="TileSetAtlasSource" id="TileSetAtlasSource_decor"]',
             'texture = ExtResource("1_decor")', "texture_region_size = Vector2i(32, 32)"]
    lines += [f"{t['atlas'][0]}:{t['atlas'][1]}/0 = 0" for t in meta["tiles"]]
    lines += ["", "[resource]", "tile_shape = 1", "tile_layout = 5", "tile_size = Vector2i(32, 16)",
              'sources/0 = SubResource("TileSetAtlasSource_decor")']
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------- sulcos

def rut_tile(tile, axis, ramp, seed=0, lanes=(0.27, 0.73), half=0.09):
    """Sulcos de pneu com ruído. Posição e largura nas bordas da célula são as
    nominais (emenda com qualquer vizinho); no meio oscilam. Falhas: trecho
    onde o sulco fica raso (tom médio, sem borda clara)."""
    rng = np.random.default_rng(1000 + seed * 7 + (axis == "v"))
    a = np.asarray(tile.convert("RGBA")).copy()
    (u, v), xs, ys = _uv()
    s, w = (u, v) if axis == "u" else (v, u)
    top = iso.top_mask()
    cols = np.round(np.asarray(ramp[1], float)).astype(int)
    for c in lanes:
        a1, a2 = rng.uniform(-0.05, 0.05, 2)
        b1, b2 = rng.uniform(-0.45, 0.45, 2)
        off = a1 * np.sin(np.pi * s) + a2 * np.sin(2 * np.pi * s)
        hw = half * (1 + b1 * np.sin(np.pi * s) + b2 * np.sin(2 * np.pi * s))
        d = np.abs(w - c - off)
        shallow = np.zeros_like(s, bool)
        if rng.random() < 0.45:
            g0 = rng.uniform(0.2, 0.6)
            shallow = (s > g0) & (s < g0 + rng.uniform(0.12, 0.25))
        jit = rng.random((32, 32))
        rut = top & (d < hw)
        rim = top & (d >= hw) & (d < hw * 2) & ~shallow & (jit < 0.7)
        deep = rut & ~shallow & (jit > 0.12)
        soft = rut & (shallow | (jit <= 0.12))
        a[..., :3][deep] = cols[0]
        a[..., :3][soft & (jit < 0.6)] = cols[1]
        # borda de fora: só do lado de fora (terra empurrada)
        outside = (w - c - off) * (1 if c > 0.5 else -1) > 0
        a[..., :3][rim & outside] = cols[-1]
    return Image.fromarray(a)


def thin_strokes(tile, cols, keep, seed, margin=2):
    """Apaga (tom 0 -> tom 1) traços escuros inteiros do miolo com chance
    1-keep. Um traço por tile no mesmo lugar vira treliça na grade; com parte
    dos tiles sem traço, a repetição some."""
    if keep >= 1:
        return tile
    a = np.asarray(tile.convert("RGBA")).copy()
    top = iso.top_mask()
    inner = top.copy()
    for _ in range(margin):
        e = inner.copy()
        e[1:, :] &= inner[:-1, :]; e[:-1, :] &= inner[1:, :]
        e[:, 1:] &= inner[:, :-1]; e[:, :-1] &= inner[:, 1:]
        inner = e
    c0, c1 = np.round(cols[0]).astype(int), np.round(cols[1]).astype(int)
    dark = top & (np.abs(a[..., :3].astype(int) - c0).sum(-1) <= 3)
    seen = np.zeros_like(dark)
    rng = np.random.default_rng(seed)
    for y0, x0 in zip(*np.nonzero(dark)):
        if seen[y0, x0]:
            continue
        comp, st = [], [(y0, x0)]
        seen[y0, x0] = True
        while st:
            y, x = st.pop()
            comp.append((y, x))
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    yy, xx = y + dy, x + dx
                    if 0 <= yy < 32 and 0 <= xx < 32 and dark[yy, xx] and not seen[yy, xx]:
                        seen[yy, xx] = True
                        st.append((yy, xx))
        if all(inner[p] for p in comp) and rng.random() > keep:
            for p in comp:
                a[p][:3] = c1
    return Image.fromarray(a)


STROKE_KEEP = [1, 0.5, 0, 0, 1, 0, 0.5, 0, 0.3, 0]


def calm_band(tile, c_from, c_to, margin=4):
    """Troca a cor c_from por c_to na faixa de borda do losango (igual em todo
    tile, então a emenda continua igual). A faixa repete o mesmo traço escuro
    em todo tile, e na grade isso vira treliça."""
    a = np.asarray(tile.convert("RGBA")).copy()
    top = iso.top_mask()
    inner = top.copy()
    for _ in range(margin):
        e = inner.copy()
        e[1:, :] &= inner[:-1, :]; e[:-1, :] &= inner[1:, :]
        e[:, 1:] &= inner[:, :-1]; e[:, :-1] &= inner[:, 1:]
        inner = e
    band = top & ~inner
    m = band & (np.abs(a[..., :3].astype(int) - np.round(c_from).astype(int)).sum(-1) <= 3)
    a[..., :3][m] = np.round(c_to).astype(int)
    return Image.fromarray(a)


# ------------------------------------------------- sulcos de vários carros
# Cada aresta da estrada tem uma "configuração" de marcas (posição na
# largura, força). O tile liga a configuração de entrada (s=0) à de saída
# (s=1) com curva suave: as marcas desviam e voltam ao longo da estrada.
# Ordem: deslocada à esquerda .. à direita (ruído suave escolhe vizinhas).
RUT_CFGS = [
    ((0.14, 0.6), (0.24, 1.0), (0.58, 0.6), (0.68, 1.0)),   # desviou p/ um lado
    ((0.20, 1.0), (0.29, 0.45), (0.68, 1.0), (0.77, 0.45)),
    ((0.26, 1.0), (0.35, 0.7), (0.73, 1.0), (0.82, 0.7)),
    ((0.32, 0.9), (0.42, 0.55), (0.78, 0.9), (0.88, 0.55)),  # p/ o outro
]


def rut_multi(tile, axis, ramp, cin, cout, seed=0, half=0.055):
    rng = np.random.default_rng(5000 + seed * 31 + cin * 7 + cout + (axis == "v") * 977)
    a = np.asarray(tile.convert("RGBA")).copy()
    (u, v), xs, ys = _uv()
    s, w = (u, v) if axis == "u" else (v, u)
    sc = np.clip(s, 0, 1)
    t = sc * sc * (3 - 2 * sc)
    top = iso.top_mask()
    cols = np.round(np.asarray(ramp[1], float)).astype(int)
    jit = rng.random((32, 32))
    dark = np.zeros((32, 32)); rim = np.zeros((32, 32), bool)
    for (p0, f0), (p1, f1) in zip(RUT_CFGS[cin], RUT_CFGS[cout]):
        wob = rng.uniform(-0.025, 0.025) * np.sin(np.pi * sc) + rng.uniform(-0.015, 0.015) * np.sin(2 * np.pi * sc)
        c = p0 + (p1 - p0) * t + wob
        f = f0 + (f1 - f0) * t
        hw = half * (0.7 + 0.5 * f) * (1 + rng.uniform(-0.3, 0.3) * np.sin(np.pi * sc))
        d = np.abs(w - c)
        if rng.random() < 0.4:  # trecho raso
            g0 = rng.uniform(0.2, 0.6)
            f = np.where((sc > g0) & (sc < g0 + 0.2), f * 0.4, f)
        on = top & (d < hw)
        dark = np.maximum(dark, np.where(on, f, 0))
        rim |= top & (d >= hw) & (d < hw + 0.04) & (jit < 0.5 * f)
    deep = (dark > 0.75) & (jit > 0.1)
    mid = (dark > 0) & ~deep & (jit < 0.35 + 0.6 * dark)
    a[..., :3][rim & (dark == 0)] = cols[-1]
    a[..., :3][mid] = cols[1]
    a[..., :3][deep] = cols[0]
    return Image.fromarray(a)


def rut_hole_decor(axis, side, pcols, water_pal, wet, rng):
    """Buraco no meio do tile de sulco, do lado oposto ao desvio."""
    a = np.zeros((32, 32, 4), np.uint8)
    w = 0.83 if side == "dir" else 0.17
    s = 0.5
    u, v = (s, w) if axis == "u" else (w, s)
    cx, cy = int(round(16 + (u - v) * 16)), int(round(8 + (u + v) * 8))
    sub = np.zeros((32, 32, 4), np.uint8)
    hole(sub, rng, pcols, wet, water_pal)
    # hole() centra em (16,16) +- jitter: desloca para (cx, cy)
    ys, xs = np.nonzero(sub[..., 3])
    dy, dx = cy - int(ys.mean()), cx - int(xs.mean())
    for y, x in zip(ys, xs):
        if 0 <= y + dy < 32 and 0 <= x + dx < 32:
            a[y + dy, x + dx] = sub[y, x]
    a[~iso.top_mask()] = 0
    return a
