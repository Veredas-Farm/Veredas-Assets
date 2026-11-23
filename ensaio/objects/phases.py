#!/usr/bin/env python3
"""Fases de árvore por inpaint (o26+): máscara da copa, redução com geometria fixa, tronco colado.

Uso: phases.py mask <arvore>...   grava specs/masks/<arvore>.png (+ prévia em tmp/)
     phases.py build              grava out/objects/arvore_<arvore>_<fase>.png/.json, prévia e gif

A geometria (janela de recorte na geração 1024, fator do unfake, posição na tela) vem
da fase base (o florido) e é aplicada sem mudança às outras fases: mesmo tamanho de
tela, mesmo anchor. Depois, os pixels do tronco (fora da máscara da copa) são copiados
da fase base, para ficarem idênticos.
"""
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

import pipeline as P
from final import ASSETS, OUT, RUNS, palette_of
from final2 import PURPLE, YELLOW

HERE = Path(__file__).resolve().parent
MASKS = HERE / "specs" / "masks"
D = OUT / "objects"
TMP = HERE / "tmp"
CREAM = [[244, 238, 214], [222, 214, 170]]  # flores (como em final.py)
FRUIT_GREEN = [[150, 172, 70], [118, 146, 52], [86, 112, 40]]  # fruto verde (a paleta das árvores puxa para amarelo)

# árvore: geração base (fase "florido"), caixa, cores extras da paleta, fases {fase: geração}
TREES = {
    "ipe_amarelo": {
        "base": "o25/ipe-amarelo2-2946455683.png", "box": (76, 92), "extra": YELLOW, "bark_phases": ("seco",),
        "base_phase": "florido", "phases": {
            "verde": "o27/ipe_amarelo-verde-*.png",
            "seco": "o26/ipeA-seco-inp-2530108259.png",
            "brotando": "o27/ipe_amarelo-brotando-*.png",
        },
    },
    "ipe_roxo": {
        "base": "o23/ipe-roxo-1074356751.png", "box": (76, 92), "extra": PURPLE, "bark_phases": ("seco",),
        "base_phase": "florido", "phases": {
            "verde": "o28/ipe_roxo-verde-*.png",
            "seco": "o27/ipe_roxo-seco-*.png",
            "brotando": "o28/ipe_roxo-brotando-*.png",
        },
    },
    "cagaita": {  # = arvore_cagaita_densa_b (o11); compara com as estações do o15 (img2img 0.6)
        "base": "o11/tree-cagaita3-moss-4133204261.png", "box": (60, 76), "extra": CREAM, "green": True, "phase_extra": {"fruto_verde": FRUIT_GREEN, "folhada": FRUIT_GREEN[1:]},
        "base_phase": "maduro", "phases": {
            "florida": "o29/cagaita-florida-*.png",
            "fruto_verde": "o29/cagaita-fruto_verde-*.png",
            "folhada": "o30/cagaita-folhada-*.png",
        },
    },
    "pequi": {
        "base": "specs/bases/pequi_8x.png", "sprite": "arvore_pequi.png", "green": True, "grow": 16, "extra": CREAM,
        "phase_extra": {"fruto_verde": FRUIT_GREEN},
        "base_phase": "maduro", "phases": {
            "florida": "o33/pequi-florida2-*.png", "fruto_verde": "o35/pequi-fruto_verde3-*.png",
            "folhada": "o30/pequi-folhada-*.png"},
    },
    "baru": {
        "base": "specs/bases/baru_8x.png", "sprite": "arvore_baru.png", "green": True, "grow": 16, "extra": CREAM,
        "phase_extra": {"fruto_verde": FRUIT_GREEN},
        "base_phase": "folhado", "phases": {
            "florida": "o31/baru-florida-*.png", "fruto_verde": "o31/baru-fruto_verde-*.png",
            "maduro": "o31/baru-maduro-*.png"},
    },
}


def hsv(rgb):
    a = np.asarray(Image.fromarray(rgb).convert("HSV")).astype(float)
    return a[..., 0] * 360 / 255, a[..., 1] / 255, a[..., 2] / 255


def crown_mask(rgb, grow=28, green=False):
    """Copa = pixels saturados (flor, folha) do objeto, fechados e dilatados.
    O tronco (cinza-marrom, pouco saturado) abaixo da copa fica de fora."""
    obj, _ = P.remove_bg(rgb)
    h, s, v = hsv(rgb)
    sat = obj & (s > 0.45) & (v > 0.25)
    if green:  # sprite do jogo: copa = verdes (o tronco é marrom)
        sat = obj & (h >= 45) & (h <= 170) & (s > 0.2)
    sat = ndimage.binary_opening(sat, iterations=2)
    lab, n = ndimage.label(ndimage.binary_dilation(sat, iterations=10))
    sizes = ndimage.sum(sat, lab, range(1, n + 1))
    cy = ndimage.center_of_mass(sat, lab, range(1, n + 1))
    keep = [i + 1 for i, (sz, c) in enumerate(zip(sizes, cy))
            if sz >= 0.01 * sizes.max() and c[0] < 0.72 * len(rgb)]  # tira pétalas caídas no chão
    crown = np.isin(lab, keep)
    crown = ndimage.binary_closing(crown, iterations=12)
    crown = ndimage.binary_fill_holes(crown)
    m = ndimage.binary_dilation(crown, iterations=grow)
    # o tronco abaixo da base da copa (sem dilatar) fica fixo
    ys = np.nonzero(crown.any(1))[0]
    trunk = obj & ~crown
    trunk[: ys.min()] = False
    m &= ~(trunk & (np.arange(len(m))[:, None] > ys.max() - 0.1 * (ys.max() - ys.min())))
    return m


def make_mask(name):
    t = TREES[name]
    rgb = load(t["base"])
    m = crown_mask(rgb, t.get("grow", 28), t.get("green", False))
    MASKS.mkdir(parents=True, exist_ok=True)
    Image.fromarray((m * 255).astype(np.uint8)).save(MASKS / f"{name}.png")
    vis = rgb.copy()
    vis[m] = (vis[m] * 0.5 + np.array([255, 0, 0]) * 0.5).astype(np.uint8)
    TMP.mkdir(exist_ok=True)
    Image.fromarray(vis).resize((512, 512)).save(TMP / f"mask_{name}.png")
    print(name, m.mean())


VARS = {"": "unfake", "_repix": "repix"}  # sufixo do arquivo: variante de redução
COLORS = 24


def find(path):
    """Caminho da geração; aceita glob (a seed só se sabe depois) e pega a mais nova."""
    for root in (RUNS, HERE):
        hits = sorted(root.glob(path), key=lambda p: p.stat().st_mtime)
        if hits:
            return hits[-1]
    return None


def load(path):
    p = find(path)
    return np.asarray(Image.open(p).convert("RGB"))


def geometry(rgb, box):
    """Janela de recorte (na 1024) e fator, da fase base. Igual ao P.prepare + P.process."""
    obj, _ = P.remove_bg(rgb)
    ys, xs = np.nonzero(obj)
    win = (max(ys.min() - 4, 0), min(ys.max() + 5, obj.shape[0]), max(xs.min() - 4, 0), min(xs.max() + 5, obj.shape[1]))
    return win, P.target_scale(obj, box)


def reduce_fixed(rgb, win, scale, variant, pal):
    """Reduz a janela fixa sem recortar no bbox: devolve RGBA do tamanho da grade."""
    obj, _ = P.remove_bg(rgb)
    y0, y1, x0, x1 = win
    small, m = P.VARIANTS[variant](rgb[y0:y1, x0:x1], obj[y0:y1, x0:x1], scale, COLORS)
    m = P.clean_mask(m)
    small = P.quantize(small, m, COLORS)
    small = P.map_palette(small, m, pal, P.PAL_TOL)
    return np.asarray(P.to_rgba(small, m)).copy()


def register(s, b, fixed, r=6):
    """Põe a fase `s` (RGBA) na grade da base `b`: o unfake e o repixelate aparam bordas
    conforme o conteúdo, então o tamanho varia. Acha o deslocamento que mais casa o
    tronco (área `fixed`) e devolve a fase no formato de `b`."""
    H, W = b.shape[:2]
    big = np.zeros((H + 2 * r, W + 2 * r, 4), np.uint8)
    best = None
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            c = big.copy()
            hh, ww = min(s.shape[0], H + r - dy), min(s.shape[1], W + r - dx)
            c[r + dy:r + dy + hh, r + dx:r + dx + ww] = s[:hh, :ww]
            c = c[r:r + H, r:r + W]
            d = np.abs(c[fixed].astype(int) - b[fixed].astype(int)).sum()
            if best is None or d < best[0]:
                best = (d, c)
    return best[1]


def blend_phase(base, phase, mask, feather=16):
    """Fase sobre a base pela máscara suave da copa (img2img muda tudo; aqui só a copa)."""
    soft = np.asarray(Image.fromarray((mask * 255).astype(np.uint8)).filter(
        __import__("PIL.ImageFilter", fromlist=["x"]).GaussianBlur(feather / 2))).astype(float)[..., None] / 255
    return (phase * soft + base * (1 - soft)).astype(np.uint8)


def build_sprite(name, t, only=None):
    """Árvore do jogo (sprite pronto ampliado 8x): reduz a janela do sprite por 8 e
    copia o sprite original fora da copa. Mesmo tamanho e anchor do sprite."""
    P.HOLE_MIN, P.PAL_TOL = 300, 0
    spr = Image.open(ASSETS / t["sprite"]).convert("RGBA")
    sw, sh = spr.size
    ox, oy = (1024 - sw * 8) // 2, (1024 - sh * 8) // 2  # como em specs/bases/*_8x.png
    win = (oy, oy + sh * 8, ox, ox + sw * 8)
    tree = P.load_palette(ASSETS / t["sprite"])
    pal_ext = np.concatenate([tree, np.array(t.get("extra", []), np.uint8).reshape(-1, 3)]).astype(np.uint8)
    base = load(t["base"])
    cmask = np.asarray(Image.open(MASKS / f"{name}.png")) > 127
    sa = np.asarray(spr).copy()
    fixed = ~P.down_mask(cmask[oy:oy + sh * 8, ox:ox + sw * 8], (sw, sh))
    fixed = ndimage.binary_erosion(fixed, iterations=1, border_value=1)
    meta0 = {"anchor": P.anchor(spr), "scale": 8}
    out = {}
    for suf, var in {"": "box", "_repix": "repix"}.items():
        out[(t["base_phase"], suf)] = (spr, {**meta0, "variant": "original"})
        for ph, src in t["phases"].items():
            if (only and ph not in only) or not find(src):
                continue
            rgb = blend_phase(base, load(src), cmask)
            obj, _ = P.remove_bg(rgb)
            y0, y1, x0, x1 = win
            small, m = P.VARIANTS[var](rgb[y0:y1, x0:x1], obj[y0:y1, x0:x1], 8, COLORS)
            if small.shape[:2] != (sh, sw):
                small = np.asarray(Image.fromarray(small).resize((sw, sh), Image.NEAREST))
                m = P.down_mask(m, (sw, sh))
            m = P.clean_mask(m)
            small = P.quantize(small, m, COLORS)
            pal = pal_ext if ph in t.get("extra_phases", ("florida", "brotando")) else tree
            if ph in t.get("phase_extra", {}):
                pal = np.concatenate([pal, t["phase_extra"][ph]]).astype(np.uint8)
            small = P.map_palette(small, m, pal, P.PAL_TOL)
            a = np.asarray(P.to_rgba(small, m)).copy()
            a[fixed] = sa[fixed]
            out[(ph, suf)] = (Image.fromarray(a), {**meta0, "variant": var})
    for (ph, suf), (im, meta) in out.items():
        fn = f"arvore_{name}_{ph}{suf}"
        im.save(D / f"{fn}.png")
        (D / f"{fn}.json").write_text(json.dumps(meta))
    return out


def lum(c):
    return c[..., 0] * 0.3 + c[..., 1] * 0.59 + c[..., 2] * 0.11


def bark_ramp(s, fixed, top=0.75, light=0.6):
    """Galhos da copa na rampa de cor do tronco (o inpaint pinta os galhos secos de
    marrom-avermelhado e o tronco é oliva: emenda na forquilha). Mapeia por quantil
    de luminância, até o quantil `top` da rampa (galho fino um pouco mais escuro que
    o tronco). Pixels claros e pouco saturados (resto do fundo na borda da máscara) saem."""
    s = s.copy()
    a = s[..., 3] > 0
    crown = a & ~fixed
    trunk = s[a & fixed][:, :3].astype(float)
    ramp = trunk[np.argsort(lum(trunk))]
    c = s[..., :3].astype(float)
    mx, mn = c.max(-1), c.min(-1)
    ghost = crown & (lum(c) > 255 * light) & ((mx - mn) < 40)
    s[ghost] = 0
    crown &= ~ghost
    L = lum(c[crown])
    q = np.argsort(np.argsort(L)) / max(len(L) - 1, 1)
    s[crown, :3] = ramp[(q * top * (len(ramp) - 1)).astype(int)].astype(np.uint8)
    return s


def build_tree(name, only=None):
    t = TREES[name]
    if t.get("sprite"):
        return build_sprite(name, t, only)
    P.HOLE_MIN, P.PAL_TOL = 300, 0
    tree = palette_of(ASSETS / "arvore_pequi.png", ASSETS / "arvore_baru.png")
    pal_ext = np.concatenate([tree, t["extra"]]).astype(np.uint8)
    base = load(t["base"])
    cmask = np.asarray(Image.open(MASKS / f"{name}.png")) > 127
    win, scale = geometry(base, t["box"])
    y0, y1, x0, x1 = win
    out = {}
    for suf, var in VARS.items():
        b = reduce_fixed(base, win, scale, var, pal_ext)
        # tronco com a paleta das árvores sem as cores de flor: senão as manchas
        # claras da casca viram roxo/amarelo (o "tufo roxo" da forquilha do ipê-roxo)
        bt = reduce_fixed(base, win, scale, var, tree)
        a = b[..., 3] > 0
        ys, xs = np.nonzero(a)
        W, H = max(t["box"][0], np.ptp(xs) + 1), max(t["box"][1], np.ptp(ys) + 1)  # sem cortar nem reamostrar
        # posição do bbox da base na tela (como P.place 'bottom'), aplicada a todas as fases
        ox = (W - (xs.max() - xs.min() + 1)) // 2 - xs.min()
        oy = H - (ys.max() + 1)
        gh, gw = a.shape
        fixed = ~P.down_mask(cmask[y0:y1, x0:x1], (gw, gh))  # fora da copa: tronco e chão
        fixed = ndimage.binary_erosion(fixed, iterations=1, border_value=1)
        phases = {t["base_phase"]: base}
        for ph, src in t["phases"].items():
            if (only and ph not in only) or not find(src):
                continue
            phases[ph] = blend_phase(base, load(src), cmask)
        for ph, rgb in phases.items():
            pal = pal_ext if ph in t.get("extra_phases", (t["base_phase"], "brotando", "florida")) else tree
            if ph in t.get("phase_extra", {}):
                pal = np.concatenate([pal, t["phase_extra"][ph]]).astype(np.uint8)
            s = b.copy() if rgb is base else register(reduce_fixed(rgb, win, scale, var, pal), b, fixed)
            s[fixed] = bt[fixed]  # tronco idêntico ao da base
            if ph in t.get("bark_phases", ()):
                s = bark_ramp(s, fixed)
            canvas = Image.new("RGBA", (W, H))
            canvas.paste(Image.fromarray(s), (ox, oy), Image.fromarray(s))
            meta = {"anchor": P.anchor(canvas) if ph == t["base_phase"] else None, "scale": round(scale, 2), "variant": var}
            out[(ph, suf)] = (canvas, meta)
    for (ph, suf), (im, meta) in out.items():
        meta["anchor"] = out[(t["base_phase"], suf)][1]["anchor"]
        fn = f"arvore_{name}_{ph}{suf}"
        im.save(D / f"{fn}.png")
        (D / f"{fn}.json").write_text(json.dumps(meta))
    return out


def phase_list(name):
    t = TREES[name]
    return [t["base_phase"], *t["phases"]]


def preview(names=None, zoom=3):
    """out/fases_preview.png: por árvore, linha da redução atual (unfake nos ipês e na
    cagaita, box no pequi e no baru) e linha repix, fases lado a lado, com rótulos.
    out/fases.gif: as fases em ciclo (redução atual), árvores lado a lado."""
    from PIL import ImageDraw
    names = [n for n in (names or TREES) if (D / f"arvore_{n}_{TREES[n]['base_phase']}.png").exists()]
    rows = []
    for n in names:
        for suf in VARS:
            r = [(ph, Image.open(D / f"arvore_{n}_{ph}{suf}.png")) for ph in phase_list(n)
                 if (D / f"arvore_{n}_{ph}{suf}.png").exists()]
            var = json.loads((D / f"arvore_{n}_{r[0][0]}{suf}.json").read_text())["variant"] if r else ""
            rows.append((f"{n} {'repix' if suf else 'atual'}", r))
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
    big.save(OUT / "fases_preview.png")
    n_frames = max(len(phase_list(n)) for n in names)
    names = [n for n in names if len([p for p in phase_list(n) if (D / f"arvore_{n}_{p}.png").exists()]) > 1] or names
    trees = [[Image.open(D / f"arvore_{n}_{ph}.png") for ph in phase_list(n)
              if (D / f"arvore_{n}_{ph}.png").exists()] for n in names]
    W = sum(t[0].width + 8 for t in trees) + 8
    H = max(t[0].height for t in trees) + 8
    frames = []
    for k in range(n_frames):
        f = Image.new("RGBA", (W, H), P.GRASS)
        x = 8
        for t in trees:
            im = t[k % len(t)]
            f.alpha_composite(im, (x, H - 4 - im.height))
            x += t[0].width + 8
        frames.append(f.convert("RGB").resize((W * zoom, H * zoom), Image.NEAREST))
    frames[0].save(OUT / "fases.gif", save_all=True, append_images=frames[1:], duration=900, loop=0)


if __name__ == "__main__":
    cmd, *args = sys.argv[1:]
    if cmd == "mask":
        for n in args or TREES:
            make_mask(n)
    elif cmd == "build":
        for n in args or TREES:
            build_tree(n)
        preview()
