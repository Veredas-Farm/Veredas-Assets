#!/usr/bin/env python3
"""Img2img isométrico (lotes i01...): bases, redução, recorte pela máscara iso e cenas.

  bases                 monta as bases 1024x1024 em specs/iso/ (tiles do jogo e do kit)
  reduce <png> ...      reduz gerações (folha 4x4 de 8x, ou par de tiles 16x) para 32x32
  scene                 monta as cenas 8x8 e a comparação em out/iso/

Só escreve em ensaio/ (temporários em $TMPDIR).
"""
import argparse, json, random, sys
from pathlib import Path
import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import iso  # noqa: E402

ROOT = HERE.parent
SPECS = ROOT / "specs" / "iso"
OUT = ROOT / "out" / "iso"
GAME_SHEET = Path("/home/chips/git/games/Veredas-Farm/old_assets/Tilemap/spritesheet.png")
KIT = ROOT / "out" / "kit-g" / "terrain_atlas.png"
WHITE = (255, 255, 255, 255)

# folha A: células (linha, coluna) do spritesheet do jogo
SHEET_A = [(0, 0), (0, 3), (0, 7), (0, 9),      # terra
           (1, 0), (1, 2), (1, 6), (1, 8),      # terra com pedras / rachada / broto
           (2, 0), (2, 1), (2, 2), (3, 4),      # grama
           (3, 5), (3, 6), (3, 7), (2, 3)]      # grama clara, grama escura, arada
# folha B: células do kit-g (grama, trilha, seca/úmida, transições)
SHEET_B = [(0, 0), (0, 1), (0, 2), (0, 3),
           (1, 0), (1, 1), (1, 2), (1, 3),
           (2, 0), (2, 1), (3, 0), (3, 1),
           (7, 2), (7, 5), (7, 8), (7, 11)]


def cell(img, r, c):
    return img.crop((c * 32, r * 32, c * 32 + 32, r * 32 + 32))


def sheet(src, cells, scale):
    """Grade 4x4 de células 32x32 ampliadas por `scale` (nearest) sobre branco."""
    n = 32 * scale
    out = Image.new("RGBA", (4 * n, 4 * n), WHITE)
    for i, (r, c) in enumerate(cells):
        t = cell(src, r, c).resize((n, n), Image.NEAREST)
        out.alpha_composite(t, ((i % 4) * n, (i // 4) * n))
    return out


def cmd_bases(a):
    SPECS.mkdir(parents=True, exist_ok=True)
    game = Image.open(GAME_SHEET).convert("RGBA")
    kit = Image.open(KIT).convert("RGBA")
    # par grama + terra a 16x (cada tile 512x512) no meio de uma tela 1024
    par = Image.new("RGBA", (1024, 1024), WHITE)
    par.alpha_composite(cell(game, 2, 0).resize((512, 512), Image.NEAREST), (0, 256))
    par.alpha_composite(cell(game, 0, 0).resize((512, 512), Image.NEAREST), (512, 256))
    par.convert("RGB").save(SPECS / "par_grama_terra_16x.png")
    sheet(game, SHEET_A, 8).convert("RGB").save(SPECS / "folha_jogo_8x.png")
    sheet(kit, SHEET_B, 8).convert("RGB").save(SPECS / "folha_kit_8x.png")
    ipe = Image.open(ROOT / "objects/out/objects/arvore_ipe_amarelo_florido.png").convert("RGBA")
    big = ipe.resize((ipe.width * 8, ipe.height * 8), Image.NEAREST)
    cv = Image.new("RGBA", (1024, 1024), WHITE)
    cv.alpha_composite(big, ((1024 - big.width) // 2, 1024 - big.height - 40))
    cv.convert("RGB").save(SPECS / "ipe_florido_8x.png")
    print("bases em", SPECS)


# ---------------------------------------------------------------- redução

def mode_down(img, f, ncolors=None):
    """Cada bloco f x f vira a cor mais frequente (mantém os tons, sem borrar)."""
    a = np.array(img.convert("RGB"))
    h, w = a.shape[0] // f, a.shape[1] // f
    out = np.zeros((h, w, 3), np.uint8)
    q = (a // 8).astype(np.int32)  # tolera ruído de 8 níveis para achar a moda
    key = (q[..., 0] << 10) | (q[..., 1] << 5) | q[..., 2]
    for y in range(h):
        for x in range(w):
            blk = key[y * f:(y + 1) * f, x * f:(x + 1) * f].ravel()
            vals, cnt = np.unique(blk, return_counts=True)
            k = vals[cnt.argmax()]
            sel = (key[y * f:(y + 1) * f, x * f:(x + 1) * f] == k)
            out[y, x] = a[y * f:(y + 1) * f, x * f:(x + 1) * f][sel].mean(0)
    return Image.fromarray(out, "RGB")


def box_down(img, f):
    return img.convert("RGB").resize((img.width // f, img.height // f), Image.BOX)


def quant(img, n):
    return img.quantize(n, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE).convert("RGB")


def game_palette():
    """Cores dos blocos de terra e grama do jogo (linhas 0..3 do spritesheet)."""
    a = np.array(Image.open(GAME_SHEET).convert("RGBA"))[:128]
    px = a[a[..., 3] > 0][:, :3]
    return np.unique(px, axis=0)


def snap_palette(img, pal):
    """Cada pixel vai para a cor mais próxima da paleta (distância RGB ponderada)."""
    a = np.array(img.convert("RGB")).astype(float)
    w = np.array([0.30, 0.59, 0.11])
    d = (((a[:, :, None, :] - pal[None, None].astype(float)) ** 2) * w).sum(-1)
    return Image.fromarray(pal[d.argmin(-1)].astype(np.uint8), "RGB")


def reduce_sheet(path, tag, how="mode", colors=24, f=8, palette=None):
    """Folha 4x4 (cada célula 256 px) -> 16 tiles 32x32 recortados pela máscara iso."""
    im = Image.open(path).convert("RGB")
    small = mode_down(im, f) if how == "mode" else box_down(im, f)
    small = snap_palette(small, game_palette()) if palette == "game" else quant(small, colors)
    tiles = []
    for i in range(16):
        r, c = divmod(i, 4)
        t = small.crop((c * 32, r * 32, c * 32 + 32, r * 32 + 32)).convert("RGBA")
        tiles.append(iso.snap_tile(t))
    d = OUT / tag
    d.mkdir(parents=True, exist_ok=True)
    for i, t in enumerate(tiles):
        t.save(d / f"{i:02d}.png")
    return tiles


def reduce_pair(path, tag, how="mode", colors=24, palette=None):
    """Par grama+terra a 16x: tiles nas células (0..511, 256..767) e (512.., 256..)."""
    im = Image.open(path).convert("RGB")
    small = mode_down(im, 16) if how == "mode" else box_down(im, 16)
    small = snap_palette(small, game_palette()) if palette == "game" else quant(small, colors)
    tiles = [iso.snap_tile(small.crop((x, 16, x + 32, 48)).convert("RGBA")) for x in (0, 32)]
    d = OUT / tag
    d.mkdir(parents=True, exist_ok=True)
    for i, t in enumerate(tiles):
        t.save(d / f"{i:02d}.png")
    return tiles


def cmd_reduce(a):
    for p in a.png:
        tag = Path(p).stem + ("-gp" if a.palette else "")
        if a.kind == "sheet":
            reduce_sheet(p, tag, a.how, a.colors, palette=a.palette)
        else:
            reduce_pair(p, tag, a.how, a.colors, palette=a.palette)
        print("ok", tag)


def cmd_tree(a):
    """Árvore gerada (fundo branco) -> sprite com a paleta do pequi+baru (tol 0)."""
    tr = Path("/home/chips/git/games/Veredas-Farm/old_assets/Green trees")
    pal = np.unique(np.concatenate([np.array(Image.open(tr / n).convert("RGBA"))[
        np.array(Image.open(tr / n).convert("RGBA"))[..., 3] > 0][:, :3]
        for n in ("arvore_pequi.png", "arvore_baru.png")]), axis=0)
    OUT.mkdir(parents=True, exist_ok=True)
    for p in a.png:
        im = Image.open(p).convert("RGB")
        arr = np.array(im).astype(int)
        fg = (arr.min(-1) < 235) | ((arr.max(-1) - arr.min(-1)) > 28)
        # tira o halo claro da borda: erosão de 3 px
        from PIL import ImageFilter
        m = Image.fromarray((fg * 255).astype(np.uint8)).filter(ImageFilter.MinFilter(7))
        ys, xs = np.nonzero(np.array(m) > 0)
        box = (xs.min(), ys.min(), xs.max() + 1, ys.max() + 1)
        crop, mc = im.crop(box), m.crop(box)
        f = max(1, round(max(crop.size) / a.fit))
        w, h = crop.width // f, crop.height // f
        small = mode_down(crop.crop((0, 0, w * f, h * f)), f)
        alpha = np.array(mc.crop((0, 0, w * f, h * f)).resize((w, h), Image.BOX)) > 127
        small = snap_palette(small, pal)
        out = np.array(small.convert("RGBA"))
        out[~alpha] = 0
        name = Path(p).stem + "_arv.png"
        Image.fromarray(out, "RGBA").save(OUT / name)
        print(name, (w, h), "fator", f)


# ---------------------------------------------------------------- cenas

def scene(tiles, n=8, seed=1, ids=None):
    rng = random.Random(seed)
    cells = {(x, y): tiles[rng.randrange(len(tiles))] for x in range(n) for y in range(n)}
    return iso.render_map(cells)


def cmd_scene(a):
    from PIL import ImageDraw
    game = Image.open(GAME_SHEET).convert("RGBA")
    kit = Image.open(KIT).convert("RGBA")
    sets = {"jogo (original)": [cell(game, 2, c) for c in (0, 1, 2)],
            "kit-g atual": [cell(kit, 0, c) for c in range(10)]}
    for p in a.sets:
        name, _, pat = p.partition("=")
        files = []
        for g in pat.split("+"):
            files += sorted(Path(g).parent.glob(Path(g).name))
        sets[name] = [Image.open(f).convert("RGBA") for f in files]
    panels = []
    import isocheck
    for name, ts in sets.items():
        try:
            print(name, "costura", isocheck.seam_score(ts), "tiles", len(ts))
        except Exception as e:
            print(name, "costura n/d", e)
        s = scene(ts, 8, a.seed)
        panels.append((name, s))
    z = a.zoom
    w = max(s.width for _, s in panels) * z
    h = max(s.height for _, s in panels) * z + 14
    cols = 2
    rows = (len(panels) + cols - 1) // cols
    sheet_ = Image.new("RGBA", (cols * (w + 8), rows * (h + 8)), (28, 28, 34, 255))
    d = ImageDraw.Draw(sheet_)
    for i, (name, s) in enumerate(panels):
        x, y = (i % cols) * (w + 8) + 4, (i // cols) * (h + 8) + 4
        d.text((x, y), name, fill=(240, 240, 240, 255))
        sheet_.alpha_composite(s.resize((s.width * z, s.height * z), Image.NEAREST), (x, y + 14))
    OUT.mkdir(parents=True, exist_ok=True)
    sheet_.save(a.out)
    print("cena", a.out)


def kit_scene(kitdir, n=12, seed=3, rock=False, road=(5, 6, 7)):
    """n x n de grama com uma estrada de trilha (2 células) ao longo de x, tiles por cantos do kit."""
    meta = json.loads((Path(kitdir) / "terrain_atlas.json").read_text())
    atlas = Image.open(Path(kitdir) / "terrain_atlas.png").convert("RGBA")
    by = {}
    for t in meta["tiles"]:
        if t["kind"] not in ("pure", "trans"):
            continue
        c = t["corners"]
        if set(c.values()) - {"grass", "path", "rock"}:
            continue
        by.setdefault((c["top"], c["right"], c["bottom"], c["left"]), []).append(t)
    has_rock = any("rock" in k for k in by)
    # vértice (x, y): estrada ao longo de x; mancha de cascalho (se o kit tem) no campo, longe da estrada
    patch = lambda x, y: rock and has_rock and y >= max(road) + 2 and (x - 4) ** 2 + (y - 9.2) ** 2 < 5.5
    kind = lambda x, y: "path" if y in road else ("rock" if patch(x, y) else "grass")
    rng = random.Random(seed)
    cells = {}
    for x in range(n):
        for y in range(n):
            key = (kind(x, y), kind(x + 1, y), kind(x + 1, y + 1), kind(x, y + 1))
            alts = by[key]
            t = rng.choices(alts, [a["probability"] for a in alts])[0]
            c, r = t["atlas"]
            cells[(x, y)] = atlas.crop((c * 32, r * 32, c * 32 + 32, r * 32 + 32))
    return iso.render_map(cells)


def cmd_kitscene(a):
    from PIL import ImageDraw
    import isocheck
    names = ["kit-g (atual)", "kit-g-iso (+4 gramas i03)"]
    scenes = [kit_scene(d, 12, a.seed) for d in (ROOT / "out/kit-g", ROOT / "out/kit-g-iso")]
    z = a.zoom
    w, h = scenes[0].width * z, scenes[0].height * z
    out = Image.new("RGBA", (2 * w + 12, h + 22), (28, 28, 34, 255))
    d = ImageDraw.Draw(out)
    for i, (nm, s) in enumerate(zip(names, scenes)):
        d.text((4 + i * (w + 4), 4), nm, fill=(240, 240, 240, 255))
        out.alpha_composite(s.resize((w, h), Image.NEAREST), (i * (w + 4), 18))
    out.save(a.out)
    # costura: gramas atuais x gramas atuais + extras
    for dd in ("out/kit-g", "out/kit-g-iso"):
        meta = json.loads((ROOT / dd / "terrain_atlas.json").read_text())
        at = Image.open(ROOT / dd / "terrain_atlas.png").convert("RGBA")
        g = [t for t in meta["tiles"] if t["kind"] == "pure" and t["terrain"] == "grass"]
        ts = [at.crop((t["atlas"][0] * 32, t["atlas"][1] * 32, t["atlas"][0] * 32 + 32, t["atlas"][1] * 32 + 32)) for t in g]
        print(dd, "gramas", len(ts), "costura", isocheck.seam_score(ts), "probs", [round(t["probability"], 3) for t in g])
    print("cena", a.out)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("bases").set_defaults(fn=cmd_bases)
    r = sub.add_parser("reduce")
    r.add_argument("png", nargs="+")
    r.add_argument("--kind", choices=["sheet", "pair"], default="sheet")
    r.add_argument("--how", choices=["mode", "box"], default="mode")
    r.add_argument("--colors", type=int, default=24)
    r.add_argument("--palette", choices=["game"], help="prende as cores à paleta dos blocos do jogo")
    r.set_defaults(fn=cmd_reduce)
    k = sub.add_parser("kitscene")
    k.add_argument("--out", default=str(OUT / "cena_kit_iso.png"))
    k.add_argument("--zoom", type=int, default=2)
    k.add_argument("--seed", type=int, default=3)
    k.set_defaults(fn=cmd_kitscene)
    t = sub.add_parser("tree")
    t.add_argument("png", nargs="+")
    t.add_argument("--fit", type=int, default=100, help="maior lado alvo em px")
    t.set_defaults(fn=cmd_tree)
    s = sub.add_parser("scene")
    s.add_argument("sets", nargs="*", help="nome=glob de PNGs 32x32")
    s.add_argument("--out", default=str(OUT / "cena.png"))
    s.add_argument("--zoom", type=int, default=2)
    s.add_argument("--seed", type=int, default=1)
    s.set_defaults(fn=cmd_scene)
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
