#!/usr/bin/env python3
"""Monta as saídas finais em out/ a partir das folhas escolhidas.

out/farmer_idle.png       96x32: frente, lado (direita), costas, como as linhas 0-2 do Player.png
out/farmer_walk_side.png  128x32: 4 quadros de caminhada de lado (passo, cruza, passo, cruza) + .gif 4x
out/farmer_idle_B.png, out/farmer_walk_side_B.png: variante B (camisa lisa creme, calça marrom)
out/preview_candidatos.png prévia: Player atual x candidatos, 1x e 4x, sobre grama
Uso: final.py  (as escolhas estão em PICKS abaixo)
"""
import sys
from pathlib import Path

from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "objects"))
import pipeline as P  # noqa: E402
import char as C  # noqa: E402

OUT = HERE / "out"
GRASS = (122, 150, 84, 255)

def pick(label, *refs):
    """refs: (arquivo .cells.png de out/cells, índice 0-11 na grade 6x2[, 'flip'])."""
    s = Image.new("RGBA", (32 * len(refs), 32))
    for i, ref in enumerate(refs):
        name, k = ref[0], ref[1]
        im = Image.open(OUT / "cells" / f"{name}.cells.png").convert("RGBA")
        c = im.crop((32 * (k % 6), 32 * (k // 6), 32 * (k % 6) + 32, 32 * (k // 6) + 32))
        if len(ref) > 2 and ref[2] == "flip":
            c = c.transpose(Image.FLIP_LEFT_RIGHT)
        s.alpha_composite(c, (32 * i, 0))
    return label, s


# escolhas: (rótulo, folha 32*k x 32); a primeira vira out/farmer_idle.png
C05 = "sheet8-055-3996712582"
F11, S10, B09 = "sheet8-front-055-796353212", "sheet8-side-055-4026927410", "sheet8-back-055-4269801764"
FB, SB, BB = "B-front-055-163824725", "B-side-055-1748130926", "B-back-055-3623460487"
PICKS = [
    pick("c09-c11 folhas por vista 0.55", (F11, 0), (S10, 5), (B09, 0)),
    pick("B: c13-c14 por vista 0.55", (FB, 0), (SB, 0), (BB, 0)),
    pick("c05 folha mista 0.55", (C05, 0), (C05, 1), (C05, 9)),
    pick("manequim (à mão)", ("blockout", 0), ("blockout", 1), ("blockout", 2)),
]
WALK = [
    pick("c10 andando lado", (S10, 6), (S10, 7), (S10, 8), (S10, 9)),
    pick("B: c13 andando lado", (SB, 6), (SB, 7), (SB, 8), (SB, 9)),
    pick("c10 andando lado (2)", (S10, 1), (S10, 2), (S10, 3), (S10, 4)),
    pick("manequim andando", ("blockout_walk", 0), ("blockout_walk", 1), ("blockout_walk", 2), ("blockout_walk", 3)),
]
# frente/costas: folhas com 4 quadros x 3 (passo A, cruza, passo B, cruza); índices escolhidos à vista
WALK_FB = [
    ("farmer_walk_front", "c17 andando frente", "walkfront-055-3045408954", (0, 1, 2, 3)),
    ("farmer_walk_back", "c18 andando costas", "walkback-055-1747901418", (0, 1, 2, 3)),
    ("farmer_walk_front_B", "B: c19 andando frente", "B-walkfront-055-2065120677", (0, 1, 2, 3)),
    ("farmer_walk_back_B", "B: c20 andando costas", "B-walkback-055-454990527", (0, 1, 2, 3)),
]


def preview(rows, path):
    """Cada linha: rótulo, a folha em 1x (escala do jogo) e em 4x."""
    font = P.font(12)
    lab = 150
    w1 = max(r.width for _, r in rows)
    W = lab + w1 + 16 + w1 * 4
    H = sum(32 * 4 + 8 for _ in rows)
    out = Image.new("RGBA", (W, H), GRASS)
    d = ImageDraw.Draw(out)
    y = 0
    for name, r in rows:
        d.text((4, y + 4), name, fill=(0, 0, 0, 255), font=font)
        out.alpha_composite(r, (lab, y + 48))
        out.alpha_composite(r.resize((r.width * 4, r.height * 4), Image.NEAREST), (lab + w1 + 16, y))
        y += 32 * 4 + 8
    out.save(path)


def blockout_cells():
    """Os manequins no formato de out/cells (192x64), para entrarem na prévia."""
    for src, dst in (("blockout_32.png", "blockout"), ("blockout_walk_side_32.png", "blockout_walk")):
        s = Image.new("RGBA", (192, 64))
        s.alpha_composite(Image.open(OUT / src).convert("RGBA"))
        s.save(OUT / "cells" / f"{dst}.cells.png")


def gif(sheet, path):
    frames = []
    for i in range(sheet.width // 32):
        f = Image.new("RGBA", (32, 32), GRASS)
        f.alpha_composite(sheet.crop((32 * i, 0, 32 * i + 32, 32)))
        frames.append(f.convert("RGB").resize((128, 128), Image.NEAREST))
    frames[0].save(path, save_all=True, append_images=frames[1:], duration=150, loop=0)


def cells_exist(name):
    return (OUT / "cells" / f"{name}.cells.png").exists()


def main():
    PICKS[0][1].save(OUT / "farmer_idle.png")
    PICKS[1][1].save(OUT / "farmer_idle_B.png")
    # caminhadas: (arquivo de saída, rótulo, geração, índices na folha)
    walks = [("farmer_walk_side", WALK[0]), ("farmer_walk_side_B", WALK[1])]
    for out, label, gen, idx in WALK_FB:
        if cells_exist(gen):
            walks.append((out, pick(label, *[(gen, k) for k in idx])))
    for out, (_, w) in walks:
        w.save(OUT / f"{out}.png")
        gif(w, OUT / f"{out}.gif")
    rows = [("atual (Player.png)", C.player_ref())] + PICKS
    rows += [("atual andando frente", C.player_ref_row(3)), ("atual andando lado", C.player_ref_row(4)),
             ("atual andando costas", C.player_ref_row(5))]
    rows += [w for _, w in walks] + WALK[2:]
    preview(rows, OUT / "preview_candidatos.png")
    print(OUT / "preview_candidatos.png")


if __name__ == "__main__":
    main()
