"""Vinheta v3: variantes intercambiáveis + transições estilizadas.

Uso: python vignette3.py <out.png> grass=.. path=.. tilled=.. side=.. [--amp .35] [--edge]
Mesmo layout de vignette.py. Tudo encaixa em qualquer ordem (sem x%g).
"""
import argparse
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))
import iso  # noqa: E402
import project  # noqa: E402
import style  # noqa: E402
from vignette import N, load, terrain_layout  # noqa: E402


RECOLOR_CUTS = (0.08, 0.25, 0.5, 0.75, 0.92)  # 6 tons, mais parelhos: a textura de origem aparece


def material(tex, side, n, seed, lock=None, recolor=None):
    """recolor: tiles de referência (grama/trilha do jogo). Em vez de travar a rampa de 4 tons
    na cor original, usa 6 tons com os quantis de luminância da própria textura (a variação
    de luz e o desenho da fonte ficam) e põe nesses 6 tons as cores equivalentes da referência
    (cor média e saturação do jogo)."""
    raw = project.project_variants(tex, side, n=n, seed=seed, colors=0)
    top, sides = iso.top_mask(), iso.left_mask() | iso.right_mask()
    if recolor:
        ramp = style.ramp_like(style.ramp_from(raw, RECOLOR_CUTS, 0.18, top), recolor, keep=0.1)
        cols = np.vstack([(ramp[1][0] + ramp[1][1]) / 2, ramp[1][1:]])  # tom mais escuro menos fundo (manchas)
        # referência chapada (um tile de terra do jogo, quase um tom só): abre os tons do meio em torno
        # da mediana, até ~28 de luminância entre o 2º e o 5º tom (matiz e saturação seguem os do jogo)
        lum = cols @ style.LUM
        k = min(5.0, max(1.0, 28.0 / max(lum[4] - lum[1], 1.0)))
        mid = cols[2:4].mean(0)
        ramp = (ramp[0], np.clip(np.maximum(mid + (cols - mid) * k, mid * 0.55), 0, 255))  # sem preto no degrau da transição
    else:
        ramp = style.ramp_from(raw, (0.12, 0.68, 0.92), 0.18, top)
    if lock and not recolor:
        ramp = style.ramp_like(ramp, lock)
    sramp = style.darken_sides(style.ramp_from(raw, (0.3, 0.75), 0.18, sides), ramp)
    tiles = [style.calm_edges(style.clean(style.apply_ramp(style.apply_ramp(t, *ramp, top), *sramp, sides), top), ramp)
             for t in raw]
    return tiles, ramp, sramp


def build_kit(tex, side, amp=0.35, edge=True, n=6, tvars=2):
    kit = {}
    mats = {k: material(tex[k], side, n, i) for i, k in enumerate(tex)}
    kit["pure"] = {k: v[0] for k, v in mats.items()}
    kit["trans"] = {}
    for b in [k for k in tex if k != "grass"]:
        ts = {}
        for tv in range(tvars):
            raw = project.banded_transitions(tex["grass"], tex[b], side, seed=7 + tv, amp=amp)
            for c, (t, sd) in raw.items():
                mb = style.material_mask(c, sd, amp)
                ga, gb = mats["grass"], mats[b]
                ts.setdefault(c, []).append(style.stylize_transition(t, mb, ga[1], gb[1], ga[2], gb[2], edge=edge))
        kit["trans"][b] = ts
    return kit


def render(kit, seed=1):
    v = terrain_layout()
    rng = np.random.default_rng(seed)
    cells = {}
    for x in range(N):
        for y in range(N):
            c = (v[y, x], v[y, x + 1], v[y + 1, x + 1], v[y + 1, x])
            if len(set(c)) == 1:
                name = {0: "grass", 1: "path", 2: "tilled"}[c[0]]
                vs = kit["pure"][name]
                cells[(x, y)] = vs[rng.integers(len(vs))]
                continue
            b = "path" if 1 in c else "tilled"
            bits = tuple(int(k != 0) for k in c)
            alts = kit["trans"][b][bits]
            cells[(x, y)] = alts[rng.integers(len(alts))]
    return iso.render_map(cells)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("tex", nargs="+")
    ap.add_argument("--amp", type=float, default=0.35)
    ap.add_argument("--scale", type=int, default=2)
    ap.add_argument("--no-edge", action="store_true")
    a = ap.parse_args()
    tex, side = {}, None
    for t in a.tex:
        k, p = t.split("=", 1)
        if k == "side":
            side = load(p, crop=0.45)
        else:
            tex[k] = load(p)
    kit = build_kit(tex, side, a.amp, not a.no_edge)
    m = render(kit)
    m.resize((m.width * a.scale, m.height * a.scale), Image.NEAREST).save(a.out)
    print(a.out)
