#!/usr/bin/env python3
"""Tema "folha nativa": os blocos das folhas img2img (3e9149 e 83fb90) como desenho, na escala nativa.

Uso: python iso_nativo.py <outdir> [--palette A|B] [--base out/kit-moss-tex]

- Cada folha (1024) tem pixel de arte de 8 px: acha o alinhamento da grade, reduz com `mode_down`
  (cor mais frequente por bloco; sem média nem requantização) e recorta cada célula 32x32 de arte,
  com o cubo encaixado na silhueta do jogo (topo do losango na linha 8, centro na coluna 16;
  `iso.snap_tile`). Lateral = a do próprio cubo (as 8 primeiras linhas), contorno escuro e brilho
  de pedra ficam.
- Cores: A = cores do jogo por quantil de luminância dentro de cada terreno (como --recolor, 6 tons,
  contorno = tom mais escuro); B = cores da própria folha, iguais entre as fontes (paleta de 10 cores
  por terreno por median cut sobre todos os blocos do terreno).
- Mesmo layout do kit base (`terrain_atlas.json` copiado): puros de grama/trilha/rock/lush viram
  os blocos nativos (variantes = original, topo espelhado, topo girado 180); transições = máscara de
  canto sobre dois blocos nativos; sulcos e tons refeitos a partir da trilha/grama nativas;
  seca, água, arado, margem, decor = do kit base.
"""
import argparse
import json
import shutil
import sys
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import iso  # noqa: E402
import style  # noqa: E402
import variedade  # noqa: E402
import remap  # noqa: E402
from iso_texturas import SHEETS  # noqa: E402
from iso_img2img import mode_down  # noqa: E402

ROOT = HERE.parent
TOP, SIDES = iso.top_mask(), iso.left_mask() | iso.right_mask()
# terreno -> blocos (folha, linha, coluna)
SRC = {
    "grass": [("a", 2, c) for c in range(4)] + [("b", 2, c) for c in range(4)],
    "path": [("a", 0, c) for c in range(4)] + [("b", 0, c) for c in range(4)] + [("a", 1, 0)],
    "rock": [("a", 1, 1), ("a", 1, 2), ("a", 1, 3), ("b", 1, 0), ("b", 1, 1), ("b", 1, 2), ("b", 1, 3)],
    "lush": [("a", 3, 0), ("a", 3, 1), ("b", 3, 2), ("a", 3, 2), ("b", 3, 0), ("b", 3, 1)],
}


def align(img, f=8):
    """Deslocamento (dx, dy) da grade de pixel de arte: o que maximiza a diferença entre
    vizinhos que cruzam a grade em relação aos que ficam dentro."""
    a = np.asarray(img.convert("L"), float)
    best = []
    for axis in (0, 1):
        d = np.abs(np.diff(a, axis=axis)).sum(axis=1 - axis)
        score = [d[(np.arange(len(d)) + 1 - o) % f == 0].sum() for o in range(f)]
        best.append(int(np.argmax(score)))
    return best  # (dx, dy): a grade começa em x = dx, y = dy


def small_sheet(path, f=8):
    im = Image.open(path).convert("RGB")
    dx, dy = align(im, f)
    w, h = (im.width - dx) // f, (im.height - dy) // f
    return mode_down(im.crop((dx, dy, dx + w * f, dy + h * f)), f), (dx, dy)


def is_bg(a):
    return (a.min(-1) >= 225) & ((a.max(-1) - a.min(-1)) < 30)


def native_tiles():
    """{(folha, r, c): RGBA 32x32} no encaixe do jogo."""
    out = {}
    for key, path in SHEETS.items():
        sm, _ = small_sheet(path)
        a = np.asarray(sm)
        cw = a.shape[0] // 4  # ~32
        geo = []
        for c in range(4):
            cell = a[0:cw, c * cw:(c + 1) * cw]
            fg = ~is_bg(cell)
            cols = np.nonzero(fg.sum(0) > 1)[0]
            mid = (cols.min() + cols.max()) / 2
            rows = np.nonzero(fg[:, int(mid) - 3:int(mid) + 4].sum(1) > 2)[0]
            geo.append((mid, rows.min()))
        mid, top = np.mean(geo, 0)
        sx, sy = int(round(mid - 15.5)), int(round(top - 8))
        pad = np.full((a.shape[0] + 64, a.shape[1] + 64, 3), 255, np.uint8)
        pad[32:-32, 32:-32] = a
        for r in range(4):
            for c in range(4):
                y0, x0 = 32 + r * cw + sy, 32 + c * cw + sx
                t = pad[y0:y0 + 32, x0:x0 + 32]
                rgba = np.dstack([t, np.where(is_bg(t), 0, 255).astype(np.uint8)])
                out[(key, r, c)] = iso.snap_tile(Image.fromarray(rgba, "RGBA"))
    return out


def variants(tile):
    """original, topo espelhado, topo girado 180 (a lateral fica a do bloco)."""
    a = np.asarray(tile).copy()
    out = [tile]
    for fn in (lambda t: t[:, ::-1], lambda t: t[::-1, ::-1]):
        b = a.copy()
        # losango 32x16 simétrico: recorta as linhas 8..23 e transforma
        t = fn(a[8:24].copy())
        b[8:24][TOP[8:24]] = t[TOP[8:24]]
        out.append(Image.fromarray(b))
    return out


def lum(c):
    return np.asarray(c, float) @ style.LUM


def palette_A(group, ref):
    """th, cols do terreno: quantis de luminância da folha, cores do jogo (referência)."""
    tops = style.ramp_from(group, (0.08, 0.25, 0.5, 0.75, 0.92), 0.0, TOP)
    ramp = style.ramp_like(tops, ref, keep=0.0)
    sramp = style.darken_sides(style.ramp_from(group, (0.3, 0.75), 0.0, SIDES), ramp)
    return ramp, sramp


def apply_A(t, ramp, sramp):
    return style.apply_ramp(style.apply_ramp(t, *ramp, TOP), *sramp, SIDES)


def palette_B(group, n=10):
    """Paleta comum do terreno (median cut sobre topo+lateral de todos os blocos)."""
    px = np.concatenate([np.asarray(t.convert("RGB"))[TOP | SIDES] for t in group])
    q = Image.fromarray(px.reshape(-1, 1, 3)).quantize(n, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
    pal = np.array(q.getpalette()[:n * 3], float).reshape(-1, 3)
    return pal[np.argsort(pal @ style.LUM)]


def apply_B(t, pal):
    a = np.asarray(t.convert("RGBA")).copy()
    rgb = a[..., :3].astype(float)
    d = ((rgb[:, :, None, :] - pal[None, None]) ** 2 * style.LUM).sum(-1)
    m = a[..., 3] > 0
    a[..., :3][m] = pal[d.argmin(-1)].round().astype(np.uint8)[m]
    return Image.fromarray(a)


def calm(tile, px=1.2):
    """Tira o contorno do losango: pixels do topo a menos de `px` da aresta ganham a cor mais
    comum do miolo do próprio bloco (o contorno de pedra e de cobertura continua dentro)."""
    a = np.asarray(tile.convert("RGBA")).copy()
    band = TOP & (style.edge_dist() < px)
    inner = TOP & ~(style.edge_dist() < px + 2)
    vals, cnt = np.unique(a[..., :3][inner], axis=0, return_counts=True)
    # só troca o que é escuro (o contorno); o resto da faixa fica
    dark = band & (a[..., :3].astype(float) @ style.LUM < np.median(a[..., :3][inner].astype(float) @ style.LUM) * 0.7)
    a[..., :3][dark] = vals[cnt.argmax()]
    return Image.fromarray(a)


def compose(a, b, mb):
    """Topo e lateral: pixel de B onde mb, senão de A."""
    x, y = np.asarray(a).copy(), np.asarray(b)
    x[mb] = y[mb]
    return Image.fromarray(x)


def build(outdir, mode, base, calm_edge=False):
    nat = native_tiles()
    refs = {"grass": remap.ref_tiles(remap.REF["grass"]), "path": remap.ref_tiles(remap.REF["path"])}
    # rampas de referência de rock/lush: as mãos de remap
    hand = {"rock": remap.ROCK_RAMP, "lush": remap.LUSH_RAMP}
    pure, ramps = {}, {}
    for name, src in SRC.items():
        raw = [nat[k] for k in src]
        if mode == "A":
            if name in refs:
                ref = refs[name]
            else:  # tile chapado com a rampa desenhada à mão (4 cores em faixas iguais)
                ref = [Image.fromarray(np.dstack([np.tile(np.array(c, np.uint8), (32, 32, 1)), np.full((32, 32), 255, np.uint8)]))
                       for c in hand[name]]
            ramp, sramp = palette_A(raw, ref)
            tiles = [apply_A(t, ramp, sramp) for t in raw]
            ramps[name] = ramp
        else:
            pal = palette_B(raw)
            tiles = [apply_B(t, pal) for t in raw]
            ramps[name] = (None, pal)
        if calm_edge:
            tiles = [calm(t) for t in tiles]
        vs = [t for t in tiles]
        for t in tiles:
            vs += variants(t)[1:]
        # originais primeiro (peso maior no kit base), depois espelhados e girados
        pure[name] = vs[:len(tiles)] + vs[len(tiles):]
    meta = json.loads((base / "terrain_atlas.json").read_text())
    atlas = Image.open(base / "terrain_atlas.png").convert("RGBA")
    new = atlas.copy()
    cell = lambda c, r: atlas.crop((c * 32, r * 32, c * 32 + 32, r * 32 + 32))
    seen = {}
    trans_n = {}
    old_pure = {}
    for t in meta["tiles"]:
        if t["kind"] == "pure":
            old_pure.setdefault(t["terrain"], []).append(cell(*t["atlas"]))
    amp_of = {"path": 0.7, "dry": 0.98, "lush": 0.98, "rock": 0.98, "water": 0.98}
    path_ramp = ramps["path"] if mode == "A" else (None, ramps["path"][1])
    pr_cols = ramps["path"][1] if mode == "A" else ramps["path"][1]
    gr_cols = ramps["grass"][1] if mode == "A" else ramps["grass"][1]
    tone_cache = {}
    stats = {"pure": 0, "trans": 0, "rut": 0, "tone": 0, "keep": 0}
    for t in meta["tiles"]:
        c, r = t["atlas"]
        kind, terr = t["kind"], t["terrain"]
        img = None
        if kind == "pure" and terr in pure:
            i = seen.get(terr, 0); seen[terr] = i + 1
            img = pure[terr][i % len(pure[terr])]
            stats["pure"] += 1
        elif kind == "trans":
            cs = t["corners"]
            others = {v for v in cs.values() if v != "grass"}
            other = others.pop() if others else None
            if other in ("path", "rock", "lush", "dry"):
                bits = tuple(int(cs[k] != "grass") for k in ("top", "right", "bottom", "left"))
                key = (other, bits)
                j = trans_n.get(key, 0); trans_n[key] = j + 1
                rng = np.random.default_rng(100 * j + sum(b << i for i, b in enumerate(bits)) + len(other))
                A = pure["grass"][int(rng.integers(len(pure["grass"])))]
                B = pure[other][int(rng.integers(len(pure[other])))] if other in pure else \
                    old_pure[other][int(rng.integers(len(old_pure[other])))]
                mb = style.material_mask(bits, 7 + j, amp_of[other] * (1 if other == "path" else 1) if False else 0.7 * (1.4 if other != "path" else 1))
                img = compose(A, B, mb)
                stats["trans"] += 1
        elif kind == "rut":
            ax = terr[-1]
            vi = t["variant"]
            img = variedade.rut_multi(pure["path"][(2, 3, 5)[vi]], ax, (None, pr_cols), t["cin"], t["cout"], seed=vi)
            stats["rut"] += 1
        elif kind == "tone":
            tone = terr.split("grass_tone_")[1]
            vi = t["variant"]
            key = (tone, vi)
            if key not in tone_cache:
                tone_cache[key] = variedade.tone_tiles(pure["grass"][(2, 3, 5)[vi]], gr_cols, variedade.TONES["grass"][tone])
            bits = tuple(int(t["corners"][k] != "grass") for k in ("top", "right", "bottom", "left"))
            img = tone_cache[key][bits]
            stats["tone"] += 1
        if img is None:
            stats["keep"] += 1
            continue
        new.paste(img, (c * 32, r * 32))
    outdir.mkdir(parents=True, exist_ok=True)
    new.save(outdir / "terrain_atlas.png")
    (outdir / "terrain_atlas.json").write_text(json.dumps(meta, indent=1))
    for f in ("decor_atlas.png", "decor_atlas.json", "decor_tileset.tres"):
        shutil.copy(base / f, outdir / f)
    print(outdir, stats)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("outdir")
    ap.add_argument("--palette", choices=["A", "B"], default="A")
    ap.add_argument("--calm", action="store_true", help="apaga o contorno escuro da aresta do losango (menos grade)")
    ap.add_argument("--base", default=str(ROOT / "out/kit-moss-tex"))
    a = ap.parse_args()
    build(Path(a.outdir), a.palette, Path(a.base), a.calm)
