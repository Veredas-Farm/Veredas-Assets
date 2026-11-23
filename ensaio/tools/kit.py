"""Exporta o kit de terreno como atlas PNG + descrição JSON.

Uso: python kit.py <outdir> [--kit ../kit.json] [--contrast 0.65]

Saída:
  terrain_atlas.png  células 32x32, 16 colunas
  terrain_atlas.json {"cell": [32, 32], "terrains": [...], "tiles": [
      {"atlas": [col, row], "kind": "pure"|"trans", "terrain": nome,
       "corners": {"top": nome, "right": nome, "bottom": nome, "left": nome},
       "probability": p}]}
Cantos seguem o Godot (isométrico): top/right/bottom/left = vértices do losango.
Todos os tiles usam texture_origin (0, 0).
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))
import iso  # noqa: E402
import project  # noqa: E402
import remap  # noqa: E402
import style  # noqa: E402
import variedade  # noqa: E402
from tilled import tilled_texture  # noqa: E402
from vignette import load  # noqa: E402

# terra arada: rampa de 5 tons (sulco escuro .. camalhão claro), puxada da trilha
TILLED_CUTS = (0.15, 0.4, 0.7, 0.92)


def tilled_tiles(cfg, wet):
    """Arado por célula (sem transição): sulcos nos dois eixos, seco/molhado."""
    grain = load(cfg["path"])
    side = load(cfg["side"], crop=0.45)
    out = []
    for axis in ("u", "v"):
        tex = tilled_texture(grain, furrows=2, axis=axis, wet=wet)
        raw = list(project.project_set(tex, side, grid=1, colors=0).values())
        top, sides = iso.top_mask(), iso.left_mask() | iso.right_mask()
        ramp = style.ramp_from(raw, TILLED_CUTS, 0.18, top)
        sramp = style.darken_sides(style.ramp_from(raw, (0.3, 0.75), 0.18, sides), ramp)
        out += [style.apply_ramp(style.apply_ramp(t, *ramp, top), *sramp, sides) for t in raw]
    return out

COLS = 16


def extra_grass_tiles(folder, cells, ramps, gc):
    """Tiles de grama gerados (img2img): cores presas à rampa de grama do kit.

    Os limiares de luminância vêm dos próprios tiles gerados (quantis, como em
    `style.ramp_from`) e as cores, da rampa do kit; topo e lateral separados.
    Passa por `calm_band` como as gramas atuais.
    """
    raw = [Image.open(Path(folder) / f"{int(c):02d}.png").convert("RGBA") for c in cells.split(",")]
    top, sides = iso.top_mask(), iso.left_mask() | iso.right_mask()
    (_, cols), (_, scols) = ramps[0], ramps[1]
    out = []
    for m, cs in ((top, cols), (sides, scols)):
        px = np.concatenate([np.asarray(t, float)[..., :3][m] for t in raw])
        cuts = (0.12, 0.68, 0.92) if len(cs) == 4 else tuple(np.linspace(0, 1, len(cs) + 1)[1:-1])
        th = np.quantile(px @ style.LUM, cuts)
        raw = [style.apply_ramp(t, th, np.asarray(cs, float), m) for t in raw]
    return [variedade.calm_band(t, gc[0], gc[1]) for t in raw]


def export(kit, outdir):
    tiles = []
    imgs = []

    def add(img, kind, terrain, corners, prob=1.0):
        k = len(imgs)
        imgs.append(img)
        tiles.append({"atlas": [k % COLS, k // COLS], "kind": kind, "terrain": terrain,
                      "corners": dict(zip(("top", "right", "bottom", "left"), corners)),
                      "probability": prob})

    def row_break():
        while len(imgs) % COLS:
            imgs.append(None)

    for name in ("grass", "path", "dry", "lush", "rock", "water", "tilled", "tilled_wet", "path_rut_u", "path_rut_v"):
        vs = kit.get(name)
        if not vs:
            continue
        ws = kit.get(name + "_weights") or [1.0] * len(vs)  # peso relativo (padrão: todos iguais)
        for v, w in zip(vs, ws):
            add(v, "pure", name, (name,) * 4, w / sum(ws))
        row_break()
    for other, key in (("path", "trans"), ("dry", "trans_dry"), ("lush", "trans_lush"), ("rock", "trans_rock"), ("water", "trans_water")):
        tr = kit.get(key)
        if not tr:
            continue
        for bits, alts in tr.items():
            if bits in ((0, 0, 0, 0), (1, 1, 1, 1)):
                continue
            corners = tuple(other if b else "grass" for b in bits)
            maj = other if sum(bits) >= 2 else "grass"
            for v in alts:
                add(v, "trans", maj, corners, 1.0 / len(alts))
        row_break()
    for ax, ci, co, vi, im in kit.get("ruts", []):
        add(im, "rut", "path_rut_" + ax, ("path",) * 4, 1.0)
        tiles[-1].update({"cin": ci, "cout": co, "variant": vi})
    row_break()
    for tone, lst in kit.get("tones", {}).items():
        for bits, vi, im in lst:
            add(im, "tone", "grass_tone_" + tone, tuple("tone" if b else "grass" for b in bits), 1.0)
            tiles[-1]["variant"] = vi
        row_break()
    # margem da água: um tile por combinação de vizinhos de terra; escolhido
    # por script (outro critério que o terrain set de cantos)
    shore = []
    for k, (img, land) in enumerate(kit.get("shore", [])):
        shore.append({"atlas": [len(imgs) % COLS, len(imgs) // COLS],
                      "land": dict(zip(("x-1", "x+1", "y-1", "y+1"), land))})
        imgs.append(img)
    row_break()
    rows = (len(imgs) + COLS - 1) // COLS
    atlas = Image.new("RGBA", (COLS * 32, rows * 32), (0, 0, 0, 0))
    for k, im in enumerate(imgs):
        if im is not None:
            atlas.paste(im, ((k % COLS) * 32, (k // COLS) * 32))
    outdir.mkdir(parents=True, exist_ok=True)
    atlas.save(outdir / "terrain_atlas.png")
    terrains = sorted({t["terrain"] for t in tiles} | {c for t in tiles for c in t["corners"].values()})
    (outdir / "terrain_atlas.json").write_text(json.dumps(
        {"cell": [32, 32], "terrains": terrains, "tiles": tiles, "shore": shore}, indent=1))
    return atlas, tiles


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("outdir")
    ap.add_argument("--kit", default=str(remap.HERE.parent / "kit.json"))
    ap.add_argument("--contrast", type=float, default=0.65)
    ap.add_argument("--amp", type=float, default=0.35)
    ap.add_argument("--lock", default="grass,path", help="materiais com cor travada na original ('' = nenhum)")
    ap.add_argument("--recolor", action="store_true",
                    help="cor do jogo por quantil de luminância (6 tons) em vez da trava de 4 tons; a textura de origem aparece mais")
    ap.add_argument("--water-corners", action="store_true",
                    help="água como terreno de canto (variante G), sem tiles de margem")
    ap.add_argument("--extra-grass", metavar="DIR",
                    help="pasta com tiles 32x32 de grama pura (img2img isométrico) acrescentados a kit['grass']")
    ap.add_argument("--extra-grass-cells", default="0,1,2,3", help="nomes (NN.png) das células a usar")
    ap.add_argument("--extra-grass-weight", type=float, default=0.5, help="peso de cada extra (atuais = 1)")
    a = ap.parse_args()
    style.CONTRAST = a.contrast
    cfg = json.loads(Path(a.kit).read_text())
    kit = remap.build(cfg, a.amp, lock=[k for k in a.lock.split(",") if k], water_corners=a.water_corners,
                    recolor=a.recolor)
    # sulcos de pneu: colocados por script no eixo da estrada (fora do terrain set)
    # menos traços escuros repetidos (treliça)
    for k in ("grass", "path"):
        rc = kit["_ramps"][k][0][1]
        kit[k] = [variedade.thin_strokes(t, rc, variedade.STROKE_KEEP[i % 10], i) for i, t in enumerate(kit[k])]
    pr = kit["_ramps"]["path"][0]
    # sulcos de vários carros: (eixo, config de entrada, de saída, variante)
    nc = len(variedade.RUT_CFGS)
    kit["ruts"] = [(ax, ci, co, vi, variedade.rut_multi(kit["path"][(2, 3, 5)[vi]], ax, pr, ci, co, seed=vi))
                   for ax in ("u", "v") for ci in range(nc) for co in range(nc) for vi in range(2)]
    # tons em mancha (fora do terrain set; escolhidos por ruído nos vértices)
    gr = kit["_ramps"]["grass"][0][1]
    kit["tones"] = {}
    for tone, mult in variedade.TONES["grass"].items():
        for vi in range(3):
            base = kit["grass"][(2, 3, 5)[vi]]  # variantes sem traço escuro
            for bits, im in variedade.tone_tiles(base, gr, mult).items():
                kit["tones"].setdefault(tone, []).append((bits, vi, im))
    kit["tilled"] = tilled_tiles(cfg, 0.0)
    kit["tilled_wet"] = tilled_tiles(cfg, 0.6)
    if a.water_corners:
        kit["water"] = kit.pop("water_c")
    else:
        import mapview
        base = remap.original_water(mapview.load())[0]
        kit["water"] = [base]
        kit["shore"] = [(project.shore(base, land), land)
                        for land in __import__("itertools").product((0, 1), repeat=4) if any(land)]
    # faixa de borda sem o tom mais escuro da grama (treliça)
    gc = kit["_ramps"]["grass"][0][1]
    calm = lambda im: variedade.thin_strokes(variedade.calm_band(im, gc[0], gc[1]), gc, 0, 0)
    for k in ("dry", "lush", "rock"):
        if kit.get(k):
            kit[k] = [calm(t) for t in kit[k]]
    kit["grass"] = [variedade.calm_band(t, gc[0], gc[1]) for t in kit["grass"]]
    if a.extra_grass:
        extra = extra_grass_tiles(a.extra_grass, a.extra_grass_cells, kit["_ramps"]["grass"], gc)
        kit["grass_weights"] = (kit.get("grass_weights") or [1.0] * len(kit["grass"])) + [a.extra_grass_weight] * len(extra)
        kit["grass"] = kit["grass"] + extra
        print("grama extra:", len(extra), "variantes, peso", a.extra_grass_weight)
    for k in ("trans", "trans_dry", "trans_lush", "trans_rock", "trans_water"):
        if kit.get(k):
            kit[k] = {b: [calm(t) for t in v] for b, v in kit[k].items()}
    for tone, lst in kit.get("tones", {}).items():
        kit["tones"][tone] = [(b, vi, calm(im)) for b, vi, im in lst]
    atlas, tiles = export(kit, Path(a.outdir))
    print(a.outdir, atlas.size, len(tiles), "tiles")
    # camada de decoração (tufos, flores, seixos, buracos...), TileSet próprio
    ramps = {k: v[0][1] for k, v in kit["_ramps"].items()}
    ramps.setdefault("lush", remap.LUSH_RAMP)
    ramps.setdefault("dry", remap.DRY_RAMP)
    items = variedade.decor_atlas(ramps, remap.WATER_PAL)
    variedade.save_decor(items, Path(a.outdir))
    meta = json.loads((Path(a.outdir) / "decor_atlas.json").read_text())
    (Path(a.outdir) / "decor_tileset.tres").write_text(variedade.decor_tres(meta, "res://decor_atlas.png"))
    print("decoração:", len(items), "tiles")


if __name__ == "__main__":
    main()
