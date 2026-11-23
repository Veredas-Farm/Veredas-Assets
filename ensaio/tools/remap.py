"""Variantes do mapa real com o kit de terreno novo.

Uso: python remap.py <out.png> [--variant A|B] [--crop x0,y0,x1,y1] [--scale 2]
     [--kit kit.json]

A: troca de pele. Cada célula de grama/trilha/água recebe um tile novo do
   mesmo terreno, sem mudar o traçado (transições em degrau como hoje).
B: mesmo traçado, mas com transições por cantos: o vértice é trilha se
   qualquer célula vizinha for trilha (a trilha alarga meio tile para cada
   lado e as bordas ficam orgânicas). Água rebaixada com margem.

O kit (texturas de cada terreno) vem de kit.json: {"grass": png, "path": png,
"side": png, "water": png|null}.
"""

import argparse
import json
import sys
import zlib
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))
import iso  # noqa: E402
import mapview  # noqa: E402
import project  # noqa: E402
import style  # noqa: E402
from vignette import load  # noqa: E402
from vignette3 import material  # noqa: E402

SHEET = "res://assets/Tilemap/spritesheet.png"
HERE = Path(__file__).resolve().parent


DRY_KEEP = 0.15  # quanto da cor própria o capim seco mantém
# palha de cerrado, do escuro ao claro (desenhada à mão)
DRY_RAMP = [(124, 122, 60), (184, 176, 92), (208, 196, 110), (230, 218, 146)]
VTX_MIN = 2  # células vizinhas de trilha para o vértice virar trilha


def h(x, y, k=0):
    return zlib.crc32(f"{x},{y},{k}".encode())


REF = {"grass": [(0, 2), (1, 2), (2, 2)], "path": [(9, 0)]}


def ref_tiles(cells):
    sheet = Image.open(HERE.parents[1] / "spritesheet.png").convert("RGBA")
    return [sheet.crop((x * 32, y * 32, x * 32 + 32, y * 32 + 32)) for x, y in cells]


ROCK_RAMP = [(70, 64, 62), (118, 111, 104), (150, 143, 134), (184, 177, 166)]  # cascalho/rocha rachada
EXTRA_W = 0.6  # peso de cada variante extra (as do kit base pesam 1)


def build(kitcfg, amp=0.35, tvars=3, lock=None, water_corners=False, recolor=False):
    """recolor: cor das rampas de grama/trilha vem do jogo por quantil (`vignette3.material`),
    com 6 tons, em vez da trava (`lock`) de 4 tons. kitcfg pode ter `grass_extra`/`path_extra`
    (listas de PNG: variantes a mais, mesma rampa do terreno, peso EXTRA_W) e `rock` (terreno novo)."""
    side = load(kitcfg["side"], crop=0.45)
    tex = {k: load(kitcfg[k]) for k in ("grass", "path")}
    mats = {k: material(tex[k], side, 10, i, lock=ref_tiles(REF[k]) if lock and k in lock else None,
                        recolor=ref_tiles(REF[k]) if recolor else None)
            for i, k in enumerate(tex)}
    weights = {}
    for k, ex_seed in (("grass", 40), ("path", 60)):
        paths = kitcfg.get(k + "_extra") or []
        if not paths:
            continue
        tiles = list(mats[k][0])
        for j, pth in enumerate(paths):
            ex = material(load(pth), side, 3, ex_seed + j, recolor=ref_tiles(REF[k]) if recolor else None,
                          lock=ref_tiles(REF[k]) if lock and k in lock and not recolor else None)
            tiles += ex[0]
        weights[k] = [1.0] * len(mats[k][0]) + [EXTRA_W] * (len(tiles) - len(mats[k][0]))
        mats[k] = (tiles, mats[k][1], mats[k][2])
    trans = {}
    trans_x = {}
    for tv in range(tvars):
        raw = project.banded_transitions(tex["grass"], tex["path"], side, seed=7 + tv, amp=amp)
        for c, (t, sd) in raw.items():
            mb = style.material_mask(c, sd, amp)
            g, p = mats["grass"], mats["path"]
            trans.setdefault(c, []).append(style.stylize_transition(t, mb, g[1], p[1], g[2], p[2]))
    for extra in ("dry", "lush", "rock"):
        if not kitcfg.get(extra):
            continue
        tx = load(kitcfg[extra])
        mx = material(tx, side, 6, 5 + len(extra))
        if extra in ("dry", "lush", "rock"):
            # rampa desenhada à mão, com um pouco da cor própria da textura
            target = {"dry": DRY_RAMP, "lush": LUSH_RAMP, "rock": ROCK_RAMP}[extra]
            keep = 0.3 if extra == "rock" else DRY_KEEP
            r = (mx[1][0], np.array(target, float) * (1 - keep) + mx[1][1] * keep)
            vs = [style.clean(style.apply_ramp(t, *r, iso.top_mask()), iso.top_mask()) for t in mx[0]]
            mx = (vs, r, mx[2])
        mats[extra] = mx
        tr = {}
        for tv in range(tvars):
            raw = project.banded_transitions(tex["grass"], tx, side, seed=17 + tv, amp=amp * 1.4)
            for c, (t, sd) in raw.items():
                mb = style.material_mask(c, sd, amp * 1.4)
                g = mats["grass"]
                tr.setdefault(c, []).append(style.stylize_transition(t, mb, g[1], mx[1], g[2], mx[2], edge=False))
        trans_x[extra] = tr
    water = None
    if kitcfg.get("water"):
        wt = load(kitcfg["water"])
        wv, wr, ws = material(wt, None, 4, 9)
        water = [project.lowered(t) for t in wv]
    kit = {"grass": mats["grass"][0], "path": mats["path"][0], "trans": trans, "water": water}
    for k, tr in trans_x.items():
        kit[k] = mats[k][0]
        kit["trans_" + k] = tr
    kit["_ramps"] = {k: (m[1], m[2]) for k, m in mats.items()}
    for k, w in weights.items():
        kit[k + "_weights"] = w
    if water_corners:
        kit["water_c"], kit["trans_water"] = water_kit(kitcfg, mats, side, amp)
    return kit


# grama de fim de seca: verde-oliva apagado
SEASON_DRY = [(92, 104, 52), (150, 156, 78), (176, 176, 96), (204, 198, 128)]


def recolor(kit, src, dst, mix=1.0):
    """Troca exata de cores da rampa `src` pela `dst` em todos os tiles do kit."""
    lut = {tuple(int(round(c)) for c in a): tuple(int(round(ca * (1 - mix) + cb * mix)) for ca, cb in zip(a, b))
           for a, b in zip(src, dst)}

    def one(im):
        arr = np.asarray(im.convert("RGBA")).copy()
        rgb = arr[..., :3]
        for a, b in lut.items():
            rgb[(rgb == a).all(-1)] = b
        return Image.fromarray(arr)

    def walk(v):
        if isinstance(v, Image.Image):
            return one(v)
        if isinstance(v, list):
            return [walk(x) for x in v]
        if isinstance(v, dict):
            return {k: walk(x) for k, x in v.items()}
        return v
    return {k: (walk(v) if k != "_ramps" else v) for k, v in kit.items()}


WATER_PAL = np.array([(79, 143, 186), (115, 190, 211), (134, 204, 222), (176, 226, 236)], float)


def water_texture(size=256, seed=0):
    """Água como a do jogo: cor base lisa com traços curtos mais escuros
    (periódica, sem emenda)."""
    rng = np.random.default_rng(seed)
    out = np.tile(WATER_PAL[1], (size, size, 1))
    for _ in range(90):
        x, y, w = rng.integers(0, size), rng.integers(0, size), rng.integers(10, 20)
        for i in range(w):
            for dy in range(6):
                out[(y + dy + (i // 6)) % size, (x + i) % size] = WATER_PAL[0]
    return Image.fromarray(out.clip(0, 255).astype(np.uint8))


def palettize(tile, mask, pal=WATER_PAL):
    a = np.asarray(tile.convert("RGBA")).copy()
    px = a[..., :3][mask].astype(float)
    d = ((px[:, None, :] - pal[None]) ** 2).sum(-1)
    a[..., :3][mask] = pal[d.argmin(1)].round().astype(np.uint8)
    return Image.fromarray(a)


def foam(tile, mb, ramp_w, width=2):
    """Na transição grama/água: água colada na grama vira espuma; a faixa
    seguinte, raso."""
    from scipy import ndimage
    a = np.asarray(tile.convert("RGBA")).copy()
    top = iso.top_mask()
    grass = top & ~mb
    near1 = ndimage.binary_dilation(grass, iterations=1) & mb & top
    near2 = ndimage.binary_dilation(grass, iterations=width + 1) & mb & top & ~near1
    lightc = WATER_PAL[-1]
    a[..., :3][near1] = (lightc * 0.4 + 255 * 0.6).round()
    a[..., :3][near2] = (a[..., :3][near2] * 0.5 + (lightc * 0.8 + 40) * 0.5).clip(0, 255).round()
    return Image.fromarray(a)


def water_kit(kitcfg, mats, side, amp, tvars=3):
    """Água como terreno de canto: tiles puros e transições com a grama."""
    wt = water_texture()
    mw = material(wt, side, 6, 23)
    top = iso.top_mask()
    mw = ([palettize(t, top) for t in mw[0]], mw[1], mw[2])
    g = mats["grass"]
    tex_g = load(kitcfg["grass"])
    tr = {}
    for tv in range(tvars):
        raw = project.banded_transitions(tex_g, wt, side, seed=31 + tv, amp=amp * 1.2)
        for c, (t, sd) in raw.items():
            mb = style.material_mask(c, sd, amp * 1.2)
            t2 = style.stylize_transition(t, mb, g[1], mw[1], g[2], g[2], edge=False)
            t2 = palettize(t2, iso.top_mask() & mb)
            tr.setdefault(c, []).append(foam(t2, mb, mw[1]))
    return mw[0], tr


def value_noise(x, y, scale, seed):
    """Ruído de valor suave no mundo (células), 0..1."""
    rng = np.random.default_rng(seed)
    g = rng.random((64, 64))
    fx, fy = x / scale, y / scale
    x0, y0 = int(np.floor(fx)), int(np.floor(fy))
    tx, ty = fx - x0, fy - y0
    tx, ty = tx * tx * (3 - 2 * tx), ty * ty * (3 - 2 * ty)
    a, b = g[y0 % 64, x0 % 64], g[y0 % 64, (x0 + 1) % 64]
    c, d = g[(y0 + 1) % 64, x0 % 64], g[(y0 + 1) % 64, (x0 + 1) % 64]
    return (a * (1 - tx) + b * tx) * (1 - ty) + (c * (1 - tx) + d * tx) * ty


def patches(grid, kit, dry_cut=0.66, rock_cut=0.72):
    """Vértice -> 'dry' | 'lush' | None. Seco no campo aberto, longe da água;
    úmido colado na água (faixa de 1..3 células, borda irregular). Nada a
    menos de 2 células de trilha/estrada/outros."""
    blocked = set()
    near_water = set()
    wet = {}
    for (x, y), t in grid.items():
        if t not in ("grass", "water"):
            for dx in range(-2, 4):
                for dy in range(-2, 4):
                    blocked.add((x + dx, y + dy))
        if t == "water":
            for dx in range(-6, 8):
                for dy in range(-6, 8):
                    near_water.add((x + dx, y + dy))
            for dx in range(-3, 5):
                for dy in range(-3, 5):
                    d = max(abs(dx - 0.5), abs(dy - 0.5))
                    k = (x + dx, y + dy)
                    wet[k] = min(wet.get(k, 9), d)
    out = {}
    xs = [k[0] for k in grid]
    ys = [k[1] for k in grid]
    for vx in range(min(xs), max(xs) + 2):
        for vy in range(min(ys), max(ys) + 2):
            v = (vx, vy)
            if v in blocked:
                continue
            n = value_noise(vx, vy, 7.0, 3) * 0.7 + value_noise(vx, vy, 2.5, 4) * 0.3
            if "lush" in kit and v in wet and wet[v] + (value_noise(vx, vy, 2.0, 8) - 0.5) * 2.0 < 1.5:
                out[v] = "lush"
            elif "rock" in kit and v not in near_water and \
                    value_noise(vx, vy, 6.0, 11) * 0.7 + value_noise(vx, vy, 2.2, 12) * 0.3 > rock_cut:
                out[v] = "rock"  # cascalho: manchas esparsas no campo aberto (kit com terreno "rock")
            elif "dry" in kit and v not in near_water and n > dry_cut:
                out[v] = "dry"
    return out


# um tom abaixo da grama (crítica do advisor: o salto de 3 tons lia como arbusto)
LUSH_RAMP = [(60, 108, 50), (112, 160, 66), (126, 172, 70), (144, 186, 78)]


def vereda(grid, scene, seed=3, max_len=60, ymin=-30, ford=None):
    """Córrego saindo do lago no sentido +x, sinuoso em y, até uma nascente
    (lagoa pequena). Evita trilha, estrada, outros e cerca. Devolve as células
    de água novas."""
    bad = set()
    for (x, y), t in grid.items():
        if t not in ("grass", "water", "path", "dirt"):
            for dx in range(-2, 3):
                for dy in range(-2, 3):
                    bad.add((x + dx, y + dy))
    shore_x = {}
    for (x, y), t in grid.items():
        if t == "water":
            shore_x[y] = max(shore_x.get(y, -999), x)

    def walk(y0):
        x, y = shore_x[y0] + 1, y0
        cells = []
        for i in range(max_len):
            if (x, y) in bad or grid.get((x, y)) not in ("grass", "path", "dirt"):
                break
            cells.append((x, y))
            n = value_noise(i, y0, 4.0, seed) - 0.5
            dy = 1 if n > 0.12 else (-1 if n < -0.12 else 0)
            if dy and (x, y + dy) not in bad and grid.get((x, y + dy)) == "grass":
                y += dy
                cells.append((x, y))
            ok = lambda c: c not in bad and grid.get(c) in ("grass", "path", "dirt")
            if not ok((x + 1, y)):
                for side in (1, -1):
                    path = [(x, y + side * k) for k in range(1, 4)]
                    good = [c for c in path if ok(c)]
                    if len(good) == 3 and ok((x + 1, y + 3 * side)):
                        cells += path
                        y += 3 * side
                        break
            x += 1
        return cells
    starts = [y0 for y0 in shore_x if y0 - 2 in shore_x and y0 + 2 in shore_x and y0 >= ymin]
    best = max((walk(y0) for y0 in starts), key=len)
    best = best[: max(8, len(best) - 3)]
    ex, ey = best[-1]
    for dx in range(-2, 3):
        for dy in range(-2, 3):
            c = (ex + dx, ey + dy)
            if dx * dx + dy * dy <= 5 + (h(*c, 13) % 3) - 1 and c not in bad and grid.get(c) == "grass":
                best.append(c)
    wide = set(best)
    for (x, y) in best:
        wide.add((x, y + 1))
    # passagem molhada: trilha continua trilha (ou vira ponte, se `ford`)
    if ford is not None:
        ford.update(c for c in wide if grid.get(c) in ("path", "dirt"))
    return {c for c in wide if grid.get(c) == "grass" and c not in bad}


WOOD = np.array([(58, 36, 26), (96, 62, 40), (128, 86, 52), (154, 108, 64)], float)
OUTLINE = (21, 29, 40)


def bridge(ford, scene, lift=3, rail=6):
    """Ponte de tábuas sobre as células de vau: tabuleiro no plano do chão
    elevado `lift` px, tábuas cruzando o sentido da trilha, guarda-corpo nas
    duas laterais. Devolve um extra_object (ordenado como chão)."""
    ox, oy = scene.layer("TerrainLayer").offset
    xs = [c[0] for c in ford]; ys = [c[1] for c in ford]
    # sentido da passagem: o eixo em que o vau é mais estreito é o do córrego
    along_y = (max(ys) - min(ys)) <= (max(xs) - min(xs))
    u0, u1 = min(xs), max(xs) + 1
    v0, v1 = min(ys) - 0.35, max(ys) + 1.35
    if not along_y:
        u0, u1, v0, v1 = min(xs) - 0.35, max(xs) + 1.35, min(ys), max(ys) + 1
    W2 = lambda u, v: (16 + (u - v) * 16, (u + v) * 8)
    pts = [W2(u, v) for u in (u0, u1) for v in (v0, v1)]
    X0 = int(min(p[0] for p in pts)) - 2; X1 = int(max(p[0] for p in pts)) + 3
    Y0 = int(min(p[1] for p in pts)) - lift - rail - 3; Y1 = int(max(p[1] for p in pts)) + 4
    w, hh = X1 - X0, Y1 - Y0
    img = np.zeros((hh, w, 4), np.uint8)
    yy, xx = np.mgrid[0:hh, 0:w]
    X = xx + X0 + 0.5; Y = yy + Y0 + 0.5 + lift
    a = (X - 16) / 16; b = Y / 8
    u, v = (a + b) / 2, (b - a) / 2
    deck = (u >= u0) & (u < u1) & (v >= v0) & (v < v1)
    t = (v - v0) if along_y else (u - u0)
    k = np.floor(t * 4)
    frac = t * 4 - k
    tone = np.where(frac < 0.18, 0, np.where(k % 3 == 0, 3, 2))
    tone = np.where((tone > 0) & (np.floor((u if along_y else v) * 2 + k * 0.5) % 2 == 0) & (frac > 0.85), 1, tone)
    img[deck, :3] = WOOD[tone[deck]].round()
    img[deck, 3] = 255
    # espessura do tabuleiro nas bordas de baixo
    for d in (1, 2):
        sh = np.zeros_like(deck); sh[d:] = deck[:-d]
        side = sh & ~deck & (img[..., 3] == 0)
        img[side, :3] = WOOD[0] if d == 1 else OUTLINE
        img[side, 3] = 255
    # guarda-corpo: postes e corrimão nas laterais
    def put(xw, yw, c):
        i, j = int(round(yw - Y0)), int(round(xw - X0))
        if 0 <= i < hh and 0 <= j < w:
            img[i, j, :3] = c; img[i, j, 3] = 255
    sides = ((u0 + 0.06, None), (u1 - 0.06, None)) if along_y else ((None, v0 + 0.06), (None, v1 - 0.06))
    for su, sv in sides:
        n = 200
        for i in range(n + 1):
            f = i / n
            uu = su if su is not None else u0 + (u1 - u0) * f
            vv = sv if sv is not None else v0 + (v1 - v0) * f
            xw, yw = W2(uu, vv)
            yw -= lift
            put(xw, yw - rail, WOOD[3]); put(xw, yw - rail + 1, WOOD[1])
        span = (v0, v1) if along_y else (u0, u1)
        npost = max(2, int(round(span[1] - span[0])) + 1)
        for i in range(npost):
            f = span[0] + 0.1 + (span[1] - span[0] - 0.2) * i / (npost - 1)
            uu, vv = (su, f) if along_y else (f, sv)
            xw, yw = W2(uu, vv)
            yw -= lift
            for dy in range(0, rail + 2):
                put(xw, yw - dy, WOOD[1] if dy < rail else WOOD[2])
                put(xw + 1, yw - dy, WOOD[0])
    im = Image.fromarray(img)
    return (im, ox + X0 + w / 2, oy + Y0 + hh, -1e9 + 2)


def buritis(grid, stream, scene):
    """Buritis nas margens do córrego (células de grama vizinhas)."""
    sprites = [_sprite(HERE.parents[1] / f) for f in ("arvore_buruti.png", "arvore_buriti2.png")]
    ox, oy = scene.layer("TerrainLayer").offset
    out = []
    seen = set()
    for (x, y) in sorted(stream):
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (-1, -1)):
            c = (x + dx, y + dy)
            if c in seen or grid.get(c) != "grass":
                continue
            seen.add(c)
            if value_noise(c[0], c[1], 3.0, 21) > 0.5 and h(*c, 21) % 100 < 28:
                lx, ly = 16 + (c[0] - c[1]) * 16, 8 + (c[0] + c[1]) * 8
                im = sprites[h(*c, 22) % len(sprites)]
                out.append((im, ox + lx + (h(*c, 23) % 7) - 3, oy + ly + 4))
    sh = [(shadow_sprite(im.width // 2), fx, fy + 2, -1e9) for im, fx, fy in out]
    return sh + out


FLOWERS = [(240, 220, 90), (245, 245, 235), (190, 120, 210), (235, 120, 70)]


def tuft_sprite(cols, k):
    """Tufo de capim 9x7 em leque: lâminas escuras, ponta clara."""
    rng = np.random.default_rng(k)
    a = np.zeros((7, 9, 4), np.uint8)
    dark = np.round(cols[0]).astype(int)
    mid = np.round(cols[0] * 0.5 + cols[1] * 0.5).astype(int)
    tip = np.round(cols[3]).astype(int)
    n = int(rng.integers(4, 7))
    for b in range(n):
        spread = (b - (n - 1) / 2) / max(1, (n - 1) / 2)  # -1..1
        hgt = int(rng.integers(3, 7)) - int(abs(spread) * 2)
        for i in range(max(2, hgt)):
            xx = int(round(4 + spread * (1 + i * 0.7)))
            yy = 6 - i
            if 0 <= xx < 9:
                c = tip if i == max(2, hgt) - 1 else (dark if i < 2 else mid)
                a[yy, xx] = (*c, 255)
    return Image.fromarray(a)


def flower_sprite(cols, k):
    """1..2 flores em cruz (3x3) com caule escuro."""
    rng = np.random.default_rng(k)
    a = np.zeros((6, 7, 4), np.uint8)
    dark = np.round(cols[0]).astype(int)
    fc = np.array(FLOWERS[k % len(FLOWERS)])
    center = np.array((250, 200, 60)) if k % len(FLOWERS) != 0 else np.array((200, 120, 40))
    for _ in range(int(rng.integers(1, 3))):
        x, y = int(rng.integers(1, 6)), int(rng.integers(1, 3))
        a[y + 2, x] = a[y + 3, x] = (*dark, 255)
        for dx, dy in ((0, -1), (-1, 0), (1, 0), (0, 1)):
            a[y + dy, x + dx] = (*fc, 255)
        a[y, x] = (*center, 255)
    return Image.fromarray(a)


def rock_sprites():
    """Pedras recortadas do e04 (tools/decals.py): sem verde, 4..16 px."""
    out = []
    for f in sorted((HERE.parent / "out/decals/stones").glob("d*.png")):
        im = Image.open(f).convert("RGBA")
        a = np.asarray(im).astype(int)
        op = a[..., 3] > 0
        green = ((a[..., 1] > a[..., 0] + 8) & (a[..., 1] > a[..., 2]))[op].mean()
        if green < 0.15 and 4 <= im.width <= 16 and im.height <= 12 and op.sum() >= 8:
            out.append(im)
    return out


def rocks(grid, scene, density=0.022):
    """Pedras em grupos (ruído) na grama; seixos pequenos na trilha."""
    rs = rock_sprites()
    small = [r for r in rs if r.width <= 7] or rs
    ox, oy = scene.layer("TerrainLayer").offset
    out = []
    for (x, y), t in grid.items():
        if t not in ("grass", "path", "dirt"):
            continue
        n = value_noise(x, y, 6.0, 77)
        p = density * (3 if n > 0.7 else 0.3) if t == "grass" else density * 0.6
        if (h(x, y, 100) % 1000) / 1000 >= p:
            continue
        u, v = (h(x, y, 101) % 100) / 100, (h(x, y, 102) % 100) / 100
        lx, ly = 16 + (x + u - y - v) * 16, 8 + (x + u + y + v) * 8 - 8
        bank = rs if t == "grass" else small
        out.append((bank[h(x, y, 103) % len(bank)], ox + lx, oy + ly + 2, -1e9 + 2))
    return out


def cupinzeiros(grid, patch, scene, density=0.022):
    """Cupinzeiros na palha (campo seco) e raros na grama aberta, longe de
    tudo que não é grama/palha."""
    sp = [(Image.open(OBJ / "objects" / f"{n}.png").convert("RGBA"),
           tuple(json.loads((OBJ / "objects" / f"{n}.json").read_text())["anchor"]))
          for n in ("cupinzeiro_alto", "cupinzeiro_baixo")]
    ox, oy = scene.layer("TerrainLayer").offset
    out = []
    for (x, y), t in grid.items():
        if t != "grass" or any(grid.get((x + i, y + j)) != "grass" for i in range(-2, 3) for j in range(-2, 3)):
            continue
        dry = patch.get((x, y)) == "dry" or patch.get((x + 1, y + 1)) == "dry"
        if (h(x, y, 120) % 1000) / 1000 >= (density if dry else density * 0.08):
            continue
        im, anc = sp[h(x, y, 121) % len(sp)]
        lx, ly = 16 + (x - y) * 16, 8 + (x + y) * 8
        out.append(at_anchor(im, anc, ox + lx, oy + ly + 2))
        sw = shadow_sprite(im.width)
        out.append((sw, ox + lx, oy + ly + 4, -1e9))
    return out


def decals(grid, patch, kit, scene, density=0.35):
    """Tufos e flores procedurais na grama, por hash da célula. Cor do
    terreno do vértice mais próximo (grama, palha ou úmida)."""
    ramps = {k: v[0][1] for k, v in kit["_ramps"].items()}
    if "lush" in kit:
        ramps["lush"] = np.array(LUSH_RAMP, float)
    bank = {k: [tuft_sprite(r, i) for i in range(8)] for k, r in ramps.items()}
    flowers = [flower_sprite(ramps["grass"], i) for i in range(8)]
    ox, oy = scene.layer("TerrainLayer").offset
    out = []
    for (x, y), t in grid.items():
        if t != "grass":
            continue
        for j in range(3):
            r = h(x, y, 40 + j) % 1000 / 1000
            # clareiras e touceiras: densidade varia com ruído de baixa frequência
            if r > density * (0.15 + 1.7 * value_noise(x, y, 5.0, 41) ** 2):
                continue
            u, v = (h(x, y, 50 + j) % 100) / 100, (h(x, y, 60 + j) % 100) / 100
            kind = patch.get((x + round(u), y + round(v))) or "grass"
            lx = 16 + (x + u - y - v) * 16
            ly = 8 + (x + u + y + v) * 8 - 8
            if kind == "grass" and h(x, y, 70 + j) % 7 == 0 and value_noise(x, y, 4.0, 31) > 0.55:
                im = flowers[h(x, y, 80 + j) % len(flowers)]
            else:
                im = bank.get(kind, bank["grass"])[h(x, y, 90 + j) % 8]
            out.append((im, ox + lx, oy + ly + 2, -1e9 + 1))
    return out


OBJ = HERE.parent / "objects/out"
HOUSE, SHED = (-29, -20), (-38, -19)
CROPS = ["mandioca", "feijao", "cana", "melancia"]


def farm_plot(grid, w=6, hgt=4):
    """Retângulo de grama w x hgt mais perto da casa, com 2 células de folga
    de qualquer coisa que não seja grama."""
    best = None
    for x0 in range(HOUSE[0] - 14, HOUSE[0] + 10):
        for y0 in range(HOUSE[1] - 14, HOUSE[1] + 10):
            ok = all(grid.get((x0 + dx, y0 + dy)) == "grass"
                     for dx in range(-2, w + 2) for dy in range(-2, hgt + 2))
            if ok:
                d = abs(x0 + w / 2 - HOUSE[0]) + abs(y0 + hgt / 2 - HOUSE[1])
                if best is None or d < best[0]:
                    best = (d, x0, y0)
    if best is None:
        return None
    _, x0, y0 = best
    return [(x0 + dx, y0 + dy) for dx in range(w) for dy in range(hgt)]


def crop_stage(name, k):
    meta = json.loads((OBJ / "crops" / f"{name}.json").read_text())
    sheet = Image.open(OBJ / "crops" / f"{name}.png").convert("RGBA")
    st = meta["stages"][k]
    x, y, w, hh = st["rect"]
    return sheet.crop((x, y, x + w, y + hh)), tuple(st["anchor"]), len(meta["stages"])


def at_anchor(im, anchor, px, py):
    """extra_object com o ponto `anchor` do sprite em (px, py) do mundo."""
    return (im, px - anchor[0] + im.width / 2, py - anchor[1] + im.height, py)


def farm(grid, plot, scene):
    """Cultivos por fileira (um tipo por linha y), estágio variando ao longo
    da fileira; carro de boi perto do paiol; cagaitas em volta da casa."""
    ox, oy = scene.layer("TerrainLayer").offset
    out = []
    ys = sorted({c[1] for c in plot})
    for (x, y) in plot:
        # fileiras alternadas com um carreador de terra arada sem planta
        if ys.index(y) % 2:
            continue
        name = CROPS[ys.index(y) // 2 % len(CROPS)]
        _, _, n = crop_stage(name, 0)
        k = min(n - 2, max(1, (x - plot[0][0]) * (n - 2) // 5 + (h(x, y, 31) % 2)))
        im, anc, _ = crop_stage(name, k)
        lx, ly = 16 + (x - y) * 16, 8 + (x + y) * 8
        out.append(at_anchor(im, anc, ox + lx, oy + ly + 2))
    # carro de boi parado na beira da roça (lado de cima/esquerda do canteiro)
    cart = Image.open(OBJ / "objects/carro_de_boi.png").convert("RGBA")
    ca = tuple(json.loads((OBJ / "objects/carro_de_boi.json").read_text())["anchor"])
    x0, y0 = min(c[0] for c in plot), max(c[1] for c in plot)
    cx, cy = x0 - 2, y0
    out.append(at_anchor(cart, ca, ox + 16 + (cx - cy) * 16, oy + 8 + (cx + cy) * 8 + 4))
    taken = {(cx, cy)}
    return out, taken


def cagaitas():
    names = ["arvore_cagaita_densa", "arvore_cagaita_densa_b", "arvore_cagaita_densa_c", "arvore_cagaita",
             "arvore_ipe_amarelo", "arvore_ipe_roxo"]
    out = []
    for n in names:
        im = Image.open(OBJ / "objects" / f"{n}.png").convert("RGBA")
        out.append((im, tuple(json.loads((OBJ / "objects" / f"{n}.json").read_text())["anchor"])))
    return out


def original_water(scene):
    src = next(s for layer in scene.layers for s in layer.tileset.sources.values() if s.res == SHEET)
    return [project.lowered(src.crop(0, 10, 0))]


GAME = HERE.parents[2] / "Veredas-Farm"


def _sprite(p):
    im = Image.open(p).convert("RGBA")
    return im.crop(im.getbbox())


LIFT_CANOPY = False


def lift_canopy(im, lo=15, hi=120, gain=1.65):
    """Clareia os tons escuros da copa (crítica: copa escura demais contra a
    grama clara). Contorno (muito escuro) e tronco (marrom) ficam."""
    a = np.asarray(im).astype(float)
    rgb = a[..., :3]
    lum = rgb @ [0.3, 0.59, 0.11]
    green = (rgb[..., 1] >= rgb[..., 0]) & (rgb[..., 1] >= rgb[..., 2])
    m = (a[..., 3] > 0) & green & (lum > lo) & (lum < hi)
    k = gain - (gain - 1) * (lum[m] - lo) / (hi - lo)
    rgb[m] = rgb[m] * k[:, None] + np.array([6, 4, -4])
    a[..., :3] = rgb.clip(0, 255)
    return Image.fromarray(a.astype(np.uint8))


def flora(scene, grid, patch, seed=5, extra_trees=None):
    """Árvores e arbustos atuais espalhados em grupos (como o gerador_mapa.gd),
    longe de trilha, água, cerca e construções. Devolve extra_objects."""
    sep = GAME / "old_assets/Tilemap/separated images"
    trees = [_sprite(HERE.parents[1] / f) for f in ("arvore_baru.png", "arvore_pequi.png")]
    if LIFT_CANOPY:
        trees = [lift_canopy(t) for t in trees]
        extra_trees = [(lift_canopy(t), anc) for t, anc in extra_trees or []]
    bushes = [_sprite(sep / f"tile_{k:03d}.png") for k in (45, 46, 47, 48)]
    layer = scene.layer("TerrainLayer")
    ox, oy = layer.offset
    blocked = set()
    for (x, y), t in grid.items():
        if t != "grass":
            for dx in range(-2, 3):
                for dy in range(-2, 3):
                    blocked.add((x + dx, y + dy))
    fence = scene.layer("FenceLayer")
    for c in fence.cells:
        for dx in range(-1, 2):
            for dy in range(-1, 2):
                blocked.add((c[0] + dx, c[1] + dy))
    out = []
    for (x, y), t in grid.items():
        if t != "grass" or (x, y) in blocked:
            continue
        n = value_noise(x, y, 5.0, 11)
        r = (h(x, y, 9) % 1000) / 1000
        lx, ly = 16 + (x - y) * 16, 8 + (x + y) * 8
        jx = (h(x, y, 3) % 9) - 4
        if n > 0.72 and r < 0.10:
            if extra_trees and h(x, y, 6) % 2 == 0:
                im, anc = extra_trees[h(x, y, 7) % len(extra_trees)]
                out.append(at_anchor(im, anc, ox + lx + jx, oy + ly + 4)[:3])
            else:
                out.append((trees[h(x, y, 4) % len(trees)], ox + lx + jx, oy + ly + 4))
        elif n > 0.55 and r < 0.07:
            out.append((bushes[h(x, y, 5) % len(bushes)], ox + lx + jx, oy + ly + 2))
    shadows = []
    for img, fx, fy in out:
        sh = shadow_sprite(img.width)
        shadows.append((sh, fx, fy + sh.height // 2, -1e9))  # desenhada antes de todos
    return shadows + out


def shadow_sprite(w, color=(40, 32, 70, 80)):
    """Elipse de sombra em pixel art (borda dura, alfa fixo)."""
    sw = max(8, int(w * 0.75)) // 2 * 2
    shh = max(4, sw // 3) // 2 * 2
    ys, xs = np.mgrid[0:shh, 0:sw]
    m = ((xs + 0.5 - sw / 2) / (sw / 2)) ** 2 + ((ys + 0.5 - shh / 2) / (shh / 2)) ** 2 <= 1
    a = np.zeros((shh, sw, 4), np.uint8)
    a[m] = color
    return Image.fromarray(a)


def track_cells(grid, min_run=6, max_width=7):
    """Faixa central das estradas retas: {célula: eixo} ('u' = estrada ao
    longo de x, 'v' = ao longo de y). Cruzamentos ficam de fora."""
    road = {c for c, t in grid.items() if t in ("path", "dirt")}

    def run(c, d):
        n, (x, y) = 0, c
        while (x + d[0], y + d[1]) in road:
            x, y = x + d[0], y + d[1]
            n += 1
        return n

    out = {}
    for c in road:
        rx = run(c, (1, 0)) + run(c, (-1, 0)) + 1
        ry = run(c, (0, 1)) + run(c, (0, -1)) + 1
        if rx >= min_run and ry <= max_width and rx > ry:
            lo = c[1] - run(c, (0, -1))
            if c[1] == lo + (ry - 1) // 2:
                out[c] = "u"
        elif ry >= min_run and rx <= max_width and ry > rx:
            lo = c[0] - run(c, (-1, 0))
            if c[0] == lo + (rx - 1) // 2:
                out[c] = "v"
    return out


def rut_tile(tile, axis, ramp, lanes=(0.27, 0.73), half=0.09):
    """Sulcos de pneu: duas linhas de v (ou u) constante, escuras, com a borda
    de fora 1 tom mais clara (terra empurrada). Contínuo entre células."""
    a = np.asarray(tile.convert("RGBA")).copy()
    ys, xs = np.mgrid[0:32, 0:32]
    u, v = project._uv_top(xs + 0.5, ys + 0.5)
    w = v if axis == "u" else u
    top = iso.top_mask()
    cols = ramp[1]
    for c in lanes:
        d = np.abs(w - c)
        rut = top & (d < half)
        rim = top & (d >= half) & (d < half * 2)
        a[..., :3][rut] = cols[0].round()
        a[..., :3][rim] = cols[-1].round()
    return Image.fromarray(a)


def holes(grid, track, scene, ramp, density=0.04, puddle=0.3):
    """Buracos (e alguns com poça) na estrada, fora das trilhas de pneu:
    elipse escura com a borda de cima em sombra e a de baixo clara."""
    ox, oy = scene.layer("TerrainLayer").offset
    cols = [np.asarray(c, float) for c in ramp[1]]
    out = []
    for (x, y), t in grid.items():
        if t not in ("path", "dirt") or (x, y) in track:
            continue
        if (h(x, y, 130) % 1000) / 1000 >= density:
            continue
        wet = h(x, y, 131) % 100 < puddle * 100
        w = 9 + h(x, y, 132) % 4
        hh = 4 + (w > 10)
        im = np.zeros((hh + 1, w, 4), np.uint8)
        for j in range(hh + 1):
            for i in range(w):
                e = ((i + 0.5 - w / 2) / (w / 2)) ** 2 + ((j + 0.5 - hh / 2) / (hh / 2)) ** 2
                if j < hh and e <= 1.0:
                    if wet:
                        c = WATER_PAL[0] if j == 0 else (WATER_PAL[2] if (i + j) % 5 == 0 else WATER_PAL[1])
                    else:
                        c = cols[0] * (0.62 if j <= hh // 2 else 0.8)
                    im[j, i] = (*np.asarray(c).round().astype(int), 255)
                elif j == hh and abs(i + 0.5 - w / 2) < w / 2 - 1.5:
                    im[j, i] = (*cols[-1].round().astype(int), 255)
        u, v = (h(x, y, 133) % 60) / 100 + 0.2, (h(x, y, 134) % 60) / 100 + 0.2
        lx, ly = 16 + (x + u - y - v) * 16, 8 + (x + u + y + v) * 8 - 8
        out.append((Image.fromarray(im), ox + lx, oy + ly + hh, -1e9 + 1))
    return out


def ragged_road(grid, seed=9, bite=0.72, bulge=0.78, depth=3):
    """Borda da estrada irregular no nível da célula: algumas células da
    borda viram grama (mordida) e algumas de grama ao lado viram terra.
    Ruído de baixa frequência, para as mordidas virem em trechos. Mordida só
    onde há `depth` células de trilha atrás (estrada estreita não se parte),
    longe de construções."""
    D = ((1, 0), (-1, 0), (0, 1), (0, -1))

    def calm(c):
        return all(grid.get((c[0] + i, c[1] + j)) in ("grass", "path") for i in range(-2, 3) for j in range(-2, 3))

    flips = {}
    for c, t in grid.items():
        n = value_noise(c[0], c[1], 3.0, seed)
        r = h(*c, seed + 1) % 100 / 100
        if r >= 0.7 or not calm(c):
            continue
        if t == "path" and n > bite:
            faces = [d for d in D if grid.get((c[0] + d[0], c[1] + d[1])) == "grass"]
            if len(faces) == 1:
                d = faces[0]
                if all(grid.get((c[0] - d[0] * k, c[1] - d[1] * k)) == "path" for k in range(1, depth + 1)):
                    flips[c] = "grass"
        elif t == "grass" and n < 1 - bulge:
            if sum(grid.get((c[0] + d[0], c[1] + d[1])) == "path" for d in D) == 1:
                flips[c] = "path"
    grid.update(flips)
    return len(flips)


def dump_cells(grid, patch, ford, path, track=None):
    """Células por terreno do kit: manchas (por vértice) viram célula quando
    3+ vértices concordam; vau da ponte volta a ser trilha; arado fica grama
    (a roça do jogo é do sistema de plantio)."""
    out = {}
    for (x, y), t in grid.items():
        if ford and (x, y) in ford:
            t = "path"
        elif t in ("dirt",):
            t = "path"
        elif t == "tilled":
            t = "grass"
        if t == "grass" and patch:
            vs = [patch.get(v) for v in ((x, y), (x + 1, y), (x + 1, y + 1), (x, y + 1))]
            for k in ("dry", "lush", "rock"):
                if vs.count(k) >= 3:
                    t = k
        if t in ("grass", "path", "dry", "lush", "rock", "water"):
            out.setdefault(t, []).append([x, y])
    for c, ax_ in (track or {}).items():
        if ford and c in ford:
            continue
        out.setdefault("track_" + ax_, []).append(list(c))
    Path(path).write_text(json.dumps(out))
    print("células:", {k: len(v) for k, v in out.items()})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--variant", default="B")
    ap.add_argument("--crop")
    ap.add_argument("--scale", type=int, default=1)
    ap.add_argument("--kit", default=str(HERE.parent / "kit.json"))
    ap.add_argument("--amp", type=float, default=0.35)
    ap.add_argument("--contrast", type=float, default=0.65)
    ap.add_argument("--dump-cells", help="grava JSON {terreno: [[x, y], ...]} para pintar no Godot")
    ap.add_argument("--copa", action="store_true", help="clareia a copa das árvores atuais")
    ap.add_argument("--no-decals", action="store_true")
    ap.add_argument("--lock", default="grass,path", help="materiais com cor travada na original")
    ap.add_argument("--recolor", action="store_true", help="cor do jogo por quantil (6 tons), como em kit.py")
    a = ap.parse_args()
    global LIFT_CANOPY
    LIFT_CANOPY = a.copa
    kitcfg = json.loads(Path(a.kit).read_text())
    style.CONTRAST = a.contrast
    kit = build(kitcfg, a.amp, lock=[k for k in a.lock.split(",") if k], water_corners=a.variant == "G",
                recolor=a.recolor)
    if a.variant == "D":
        kit = recolor(kit, kit["_ramps"]["grass"][0][1], SEASON_DRY)
    mapview.UNIFORM_ORIGIN[SHEET] = (0, 0)
    scene = mapview.load()
    grid = mapview.terrain_grid(scene)
    # terra avulsa (células "other" do atlas) conta como trilha no B
    grid = {k: ("dirt" if v.startswith("other:") and a.variant in ("B", "C", "D", "E", "F", "G") else v) for k, v in grid.items()}
    stream = set()
    ford = None
    plot = []
    if a.variant in ("F", "G"):
        plot = farm_plot(grid, hgt=7) or farm_plot(grid)
        grid.update({c: "tilled" for c in plot})
    if a.variant in ("E", "F", "G"):
        ford = set() if a.variant == "G" else None
        stream = vereda(grid, scene, ford=ford)
        grid.update({c: "water" for c in stream})
        if ford:
            grid.update({c: "water" for c in ford})
    if a.variant in ("E", "F", "G") and "lush" not in kit:
        dr = kit["_ramps"]["dry"][0][1]
        lush = recolor({"lush": kit["dry"], "trans_lush": kit["trans_dry"]}, dr, LUSH_RAMP)
        kit["lush"], kit["trans_lush"] = lush["lush"], lush["trans_lush"]
    if stream:
        print("vereda:", len(stream), "células")
    water = kit["water"] or original_water(scene)
    patch = patches(grid, kit, dry_cut=0.55 if a.variant == "D" else 0.66) if a.variant in ("C", "D", "E", "F", "G") else {}

    if a.variant == "G":
        print("borda irregular:", ragged_road(grid), "células")
    shore_cache = {}
    rut_cache = {}
    track = track_cells(grid) if a.variant == "G" else {}
    tilled = []
    if plot:
        from kit import tilled_tiles
        tilled = tilled_tiles(kitcfg, 0.6)[:1] + tilled_tiles(kitcfg, 0.6)[:1]

    def pick(lst, x, y, k=0):
        return lst[h(x, y, k) % len(lst)]

    def vtx(vx, vy):
        cs = [grid.get((vx - 1, vy - 1)), grid.get((vx, vy - 1)), grid.get((vx - 1, vy)), grid.get((vx, vy))]
        n = sum(c in ("path", "road", "dirt") for c in cs)
        return 1 if n >= VTX_MIN else 0

    def wvtx(vx, vy):
        cs = [grid.get((vx - 1, vy - 1)), grid.get((vx, vy - 1)), grid.get((vx - 1, vy)), grid.get((vx, vy))]
        return 1 if sum(c == "water" for c in cs) >= VTX_MIN else 0

    def tile_fn(layer, x, y, res, ax, ay):
        if not layer.endswith("TerrainLayer"):
            return None
        t = grid.get((x, y))
        if a.variant == "G" and t in ("grass", "water"):
            wc = (wvtx(x, y), wvtx(x + 1, y), wvtx(x + 1, y + 1), wvtx(x, y + 1))
            if wc == (1, 1, 1, 1):
                return pick(kit["water_c"], x, y)
            if any(wc):
                return pick(kit["trans_water"][wc], x, y, 3)
            if t == "water":
                return pick(kit["grass"], x, y)
        if t == "dirt":
            t = "path"
        if t == "tilled":
            return pick(tilled, x, y)
        if t == "water":
            land = tuple(int(grid.get(n, "water") != "water")
                         for n in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)))
            base = pick(water, x, y)
            if a.variant != "A" and not any(land):
                # profundidade: escurece longe da margem (Chebyshev até 3)
                d = next((r for r in (1, 2, 3) if any(grid.get((x + i, y + j), "water") != "water"
                                                       for i in range(-r, r + 1) for j in range(-r, r + 1))), 4)
                if d >= 3:
                    key = (id(base), "deep", d)
                    if key not in shore_cache:
                        arr = np.asarray(base.convert("RGBA")).astype(float)
                        arr[..., :3] *= 0.95 if d == 3 else 0.9
                        shore_cache[key] = Image.fromarray(arr.clip(0, 255).astype(np.uint8))
                    return shore_cache[key]
            if not any(land) or a.variant == "A":
                return base
            key = (id(base), land, h(x, y, 7) % 3)
            if key not in shore_cache:
                shore_cache[key] = project.shore(base, land, seed=key[2])
            return shore_cache[key]
        if t not in ("grass", "path"):
            return None
        if a.variant in ("C", "D", "E", "F", "G") and t == "grass":
            vs = [patch.get(v) for v in ((x, y), (x + 1, y), (x + 1, y + 1), (x, y + 1))]
            kinds = {k for k in vs if k}
            if len(kinds) == 1:
                k = kinds.pop()
                bits = tuple(int(v == k) for v in vs)
                if bits == (1, 1, 1, 1):
                    return pick(kit[k], x, y)
                return pick(kit["trans_" + k][bits], x, y, 2)
        if a.variant == "A":
            return pick(kit[t], x, y)
        if t == "path":
            if (x, y) in track:
                ax_ = track[(x, y)]
                key = (ax_, id(pick(kit["path"], x, y)))
                if key not in rut_cache:
                    rut_cache[key] = rut_tile(pick(kit["path"], x, y), ax_, kit["_ramps"]["path"][0])
                return rut_cache[key]
            return pick(kit["path"], x, y)
        c = (vtx(x, y), vtx(x + 1, y), vtx(x + 1, y + 1), vtx(x, y + 1))
        if c == (0, 0, 0, 0):
            return pick(kit["grass"], x, y)
        if c == (1, 1, 1, 1):
            return pick(kit["path"], x, y)
        return pick(kit["trans"][c], x, y, 1)

    extra = flora(scene, grid, patch, extra_trees=cagaitas() if a.variant in ("F", "G") else None) if a.variant in ("C", "D", "E", "F", "G") else None
    if stream:
        extra += buritis(grid, stream, scene)
        if ford:
            extra.append(bridge(ford, scene))
    if plot:
        fo, _ = farm(grid, plot, scene)
        extra += fo
    if a.variant == "G" and extra is not None:
        extra += cupinzeiros(grid, patch, scene)
        extra += holes(grid, track, scene, kit["_ramps"]["path"][0])
    if extra is not None and not a.no_decals:
        extra = decals(grid, patch, kit, scene) + rocks(grid, scene) + extra
    if a.dump_cells:
        dump_cells(grid, patch, ford, a.dump_cells, track)
    crop = tuple(int(v) for v in a.crop.split(",")) if a.crop else None
    img = mapview.render(scene, tile_fn=tile_fn, crop=crop, scale=a.scale,
                         uniform_origin=(0, 0), extra_objects=extra)
    img.save(a.out)
    print(a.out, img.size)


if __name__ == "__main__":
    main()
