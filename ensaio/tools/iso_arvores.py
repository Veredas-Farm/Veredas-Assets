#!/usr/bin/env python3
"""Árvores novas (paineira, jatobá) com fases por inpaint da copa, método de objects/phases.py.

  mask <arvore>...    máscara da copa em specs/iso/masks/ + prévia em $TMPDIR
  build <arvore>...   reduz as fases (geometria fixa da base) -> entrega/objetos/fases/arvore_<nome>_<fase>.png/.json
  preview             out/iso/arvores_novas_fases.png

Reaproveita objects/phases.py (TREES, crown_mask, build_tree) trocando as pastas de saída;
não altera os arquivos do objects/.
"""
import json
import os
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "objects"))
import phases as PH  # noqa: E402
import pipeline as P  # noqa: E402

MASKS = ROOT / "specs" / "iso" / "masks"
DEST = ROOT / "entrega" / "objetos" / "fases"
STAGE = ROOT / "out" / "iso" / "arvores_fases"
PH.MASKS = MASKS
PH.D = STAGE

def flower_colors(path, n=5):
    """Cores da flor tiradas da própria geração (a paleta pequi+baru não tem rosa/coral):
    pixels saturados avermelhados, n quantis de luminância."""
    rgb = np.asarray(Image.open(ROOT / "runs" / path).convert("RGB"))
    h, sat, v = PH.hsv(rgb)
    m = ((h < 25) | (h > 320)) & (sat > 0.45) & (v > 0.5)
    px = rgb[m].astype(float)
    px = px[np.argsort(px @ [0.3, 0.59, 0.11])]
    return [px[int(q * (len(px) - 1))].astype(int).tolist() for q in np.linspace(0.05, 0.95, n)]


PINK = flower_colors("i05/arv-paineira-ipe-d70-2877291051.png")   # flor de paineira
CREAM = PH.CREAM
FRUIT_BROWN = [[120, 80, 48], [88, 58, 36], [150, 104, 64]]                # vagem de jatobá

# base_phase = geração base; phases = {fase: glob em runs/}
PH.TREES.update({
    "paineira": {
        "base": "i05/arv-paineira-ipe-d70-2877291051.png", "box": (90, 96), "extra": PINK,
        "bark_phases": ("seco",), "base_phase": "florida",
        "phases": {"verde": "i07/paineira-verde-3686203867.png", "seco": "i07/paineira-seco-2172913077.png"},
    },
    "jatoba": {
        "base": "i06/arv-jatoba2-pequi-d65-1175281837.png", "box": (84, 90), "extra": CREAM,
        "phase_extra": {"fruto": FRUIT_BROWN, "folhada": FRUIT_BROWN[:1]},
        "grow": 40, "base_phase": "fruto", "phases": {"florida": "i08/jatoba-florida-1749998797.png", "folhada": "i08/jatoba-folhada-1577778837.png"},
    },
})


def _hsv(a):
    x = np.asarray(Image.fromarray(a[..., :3]).convert("HSV")).astype(float)
    return x[..., 0] * 360 / 255, x[..., 1] / 255, x[..., 2] / 255


def _with_hue(a, m, hue, vmul=1.0):
    """Troca o matiz dos pixels de `m` por `hue` (graus), mantendo saturação e brilho (volume e sombra)."""
    x = np.asarray(Image.fromarray(a[..., :3]).convert("HSV")).copy()
    x[..., 0][m] = int(round(hue * 255 / 360))
    x[..., 2][m] = np.clip(x[..., 2][m] * vmul, 0, 255).astype(np.uint8)
    out = a.copy()
    out[..., :3][m] = np.asarray(Image.fromarray(x, "HSV").convert("RGB"))[m]
    return out


def _to_canopy_ramp(a, m, ref, light2=False):
    """Pixels de `m` -> tom da rampa de verdes da própria copa (`ref`: verdes não corrigidos)
    mais próximo em luminância. light2: só os 2 tons mais claros da rampa, +10% de brilho,
    saturação limitada à máxima da copa."""
    L = np.array([0.299, 0.587, 0.114])
    cols = np.unique(a[..., :3][ref].reshape(-1, 3), axis=0)
    cols = cols[np.argsort(cols @ L)]
    if light2:  # só verdes acima da mediana de luminância da copa (ref é por pixel, não por cor)
        pl = a[..., :3][ref].astype(float) @ L
        cols = np.unique(a[..., :3][ref][pl > np.median(pl)].reshape(-1, 3), axis=0)
        cols = cols[np.argsort(cols @ L)][-2:] if len(cols) > 2 else cols
    lum = a[..., :3][m].astype(float) @ L
    if light2:  # os do amarelo ficam entre os 2 tons mais claros, por luminância
        idx = (lum > np.median(lum)).astype(int)
    else:
        idx = np.abs((cols @ L)[None, :] - lum[:, None]).argmin(1)
    new = cols[idx].astype(float)
    if light2:
        new = np.clip(new * 1.2, 0, 255)
        sat_max = _hsv(a)[1][ref].max()
        x = np.asarray(Image.fromarray(new.reshape(-1, 1, 3).astype(np.uint8)).convert("HSV")).astype(float)
        x[..., 1] = np.minimum(x[..., 1], sat_max * 255)
        new = np.asarray(Image.fromarray(x.astype(np.uint8), "HSV").convert("RGB")).reshape(-1, 3)
    out = a.copy()
    out[..., :3][m] = new.astype(np.uint8)
    return out


def fix_colors(name, ph, img):
    """Recolore sem GPU: amarelos soltos da paineira, laranjas soltos do tronco e o amarelo-limão da folhada."""
    a = np.asarray(img.convert("RGBA")).copy()
    h, s, v = _hsv(a)
    op = a[..., 3] > 0
    H = a.shape[0]
    if name == "paineira":
        low = np.arange(H)[:, None] >= int(0.62 * H)
        trunk = op & low & (h >= 12) & (h <= 48) & (s > 0.45) & (v > 0.55)  # pontos laranja do tronco: vão para o oliva da casca
        a = _with_hue(a, trunk, 68, 0.8)
        a[..., :3][trunk] = (a[..., :3][trunk] * [0.85, 0.85, 0.7]).astype(np.uint8)
        a = _with_hue(a, trunk, 62, 0.85) if False else a
        if ph == "verde":
            yel = op & (h >= 38) & (h <= 75) & (s > 0.5) & (v > 0.55)
            ref = op & (h >= 70) & (h <= 170) & ~yel
            a = _to_canopy_ramp(a, yel, ref)
    if name == "jatoba" and ph == "folhada":
        yel = op & (h >= 40) & (h <= 80) & (s > 0.45) & (v > 0.5)
        ref = op & (h >= 70) & (h <= 170) & ~yel
        a = _to_canopy_ramp(a, yel, ref, light2=True)
    return Image.fromarray(a, "RGBA")


def cmd_preview(names):
    zoom = 3
    rows = []
    for n in names:
        r = [(ph, Image.open(STAGE / f"arvore_{n}_{ph}.png")) for ph in PH.phase_list(n)
             if (STAGE / f"arvore_{n}_{ph}.png").exists()]
        rows.append((n, r))
    cw = max(im.width for _, r in rows for _, im in r) + 8
    h = max(im.height for _, r in rows for _, im in r) + 16
    W = 8 + cw * max(len(r) for _, r in rows)
    prev = Image.new("RGBA", (W, h * len(rows)), P.GRASS)
    for i, (_, r) in enumerate(rows):
        for k, (_, im) in enumerate(r):
            prev.alpha_composite(im, (8 + k * cw + (cw - 8 - im.width) // 2, i * h + h - 2 - im.height))
    big = prev.resize((W * zoom, prev.height * zoom), Image.NEAREST)
    d = ImageDraw.Draw(big)
    for i, (n, r) in enumerate(rows):
        for k, (ph, _) in enumerate(r):
            d.text(((8 + k * cw) * zoom, i * h * zoom + 2), f"{n} {ph}", fill=(255, 255, 255))
    out = ROOT / "out" / "iso" / "arvores_novas_fases.png"
    big.save(out)
    print(out)


def main():
    cmd, *names = sys.argv[1:]
    STAGE.mkdir(parents=True, exist_ok=True)
    names = names or ["paineira", "jatoba"]
    if cmd == "mask":
        os.environ.setdefault("TMPDIR", "/tmp")
        PH.TMP = Path(os.environ["TMPDIR"]) / "iso_mask"
        for n in names:
            PH.make_mask(n)
    elif cmd == "build":
        DEST.mkdir(parents=True, exist_ok=True)
        for n in names:
            PH.build_tree(n)
            for f in STAGE.glob(f"arvore_{n}_*.png"):
                if "_repix" not in f.name:
                    ph = f.stem[len(f"arvore_{n}_"):]
                    fix_colors(n, ph, Image.open(f)).save(f)
            for f in STAGE.glob(f"arvore_{n}_*"):
                if "_repix" not in f.name:
                    (DEST / f.name).write_bytes(f.read_bytes())
        cmd_preview(names)
    elif cmd == "preview":
        cmd_preview(names)


if __name__ == "__main__":
    main()
