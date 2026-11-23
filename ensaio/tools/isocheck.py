#!/usr/bin/env python3
"""Valida tiles isométricos (silhueta, costuras) e gera mapas de pré-visualização."""
import argparse, html, json, random
from pathlib import Path
import numpy as np
from PIL import Image
import iso

# Limiares de aprovação (um tile só passa se atender a todos)
MAX_SEMI = 0          # pixels semitransparentes (alfa 1..254)
MAX_OUTSIDE = 4       # pixels opacos fora da silhueta
MAX_MISSING = 4       # pixels faltando dentro da silhueta
MIN_IOU = 0.98
MAX_COLORS = 64
MAX_SEAM_RATIO = 1.5  # diferença nas fronteiras / diferença interna (face de cima)
MIN_SEAM_RATIO = 0.6  # abaixo disso a borda é lisa demais e a grade aparece (treliça); só aviso
SCALE = 4
PLAYER = Path("/home/chips/git/games/Veredas-Farm/old_assets/Player/Player.png")
GRID = [(x, y) for x in range(8) for y in range(8)]


def seam_score(tile_list, seed=0):
    """Razão entre a diferença média de cor nas fronteiras de tiles e dentro deles.

    Mapa 8x8 só com a face de cima (sem sobreposição); cada pixel guarda o id do
    tile. Pares vizinhos (horizontal/vertical) do mesmo id contam como 'dentro',
    de ids diferentes como 'fronteira'. ~1 = sem costura visível.
    """
    rng = random.Random(seed)
    top = iso.top_mask()
    layers = []
    for t in tile_list:
        a = np.array(t.convert("RGBA"))
        a[~top] = 0
        layers.append(Image.fromarray(a, "RGBA"))
    cells = {c: rng.randrange(len(layers)) for c in GRID}
    img = np.array(iso.render_map({c: layers[i] for c, i in cells.items()})).astype(float)
    def id_tile(i):
        t = np.zeros((32, 32, 4), np.uint8)
        t[top] = (i % 256, i // 256, 0, 255)
        return Image.fromarray(t, "RGBA")
    idm = np.array(iso.render_map({c: id_tile(k) for k, c in enumerate(GRID)}))
    ids = np.where(idm[..., 3] > 0, idm[..., 0].astype(int) + 256 * idm[..., 1].astype(int), -1)
    inside, border = [], []
    for sl_a, sl_b in (((slice(None), slice(0, -1)), (slice(None), slice(1, None))),
                       ((slice(0, -1), slice(None)), (slice(1, None), slice(None)))):
        ia, ib = ids[sl_a], ids[sl_b]
        ok = (ia >= 0) & (ib >= 0)
        d = np.abs(img[sl_a][..., :3] - img[sl_b][..., :3]).mean(-1)
        inside.append(d[ok & (ia == ib)])
        border.append(d[ok & (ia != ib)])
    inside, border = np.concatenate(inside), np.concatenate(border)
    if not len(border) or not len(inside):
        return None
    return round(float(border.mean() / max(inside.mean(), 1e-6)), 3)


def metrics(img, name):
    m = {"name": name, "size": list(img.size), "size_ok": img.size == (32, 32)}
    if not m["size_ok"]:
        m["pass"], m["fails"] = False, ["tamanho"]
        return m
    a = np.array(img.convert("RGBA"))
    al, block = a[..., 3], iso.block_mask()
    opaque = al > 0
    m["semi_transparent"] = int(((al > 0) & (al < 255)).sum())
    m["outside"] = int((opaque & ~block).sum())
    m["missing"] = int((block & ~opaque).sum())
    m["iou"] = round(float((opaque & block).sum() / (opaque | block).sum()), 4)
    m["colors"] = len({tuple(p) for p in a[opaque & block][:, :3]})
    m["seam_ratio"] = seam_score([img])
    fails = []
    if m["semi_transparent"] > MAX_SEMI: fails.append("semitransparentes")
    if m["outside"] > MAX_OUTSIDE: fails.append("fora da silhueta")
    if m["missing"] > MAX_MISSING: fails.append("buracos na silhueta")
    if m["iou"] < MIN_IOU: fails.append("IoU")
    if m["colors"] > MAX_COLORS: fails.append("muitas cores")
    if m["seam_ratio"] is not None and m["seam_ratio"] > MAX_SEAM_RATIO: fails.append("costura")
    m["fails"], m["pass"] = fails, not fails
    m["warns"] = ["treliça"] if m["seam_ratio"] is not None and m["seam_ratio"] < MIN_SEAM_RATIO else []
    return m


def save4x(img, path):
    img.resize((img.width * SCALE, img.height * SCALE), Image.NEAREST).save(path)


def load_inputs(args):
    tiles = []  # (nome, imagem)
    for p in args.png:
        tiles.append((Path(p).stem, Image.open(p).convert("RGBA")))
    if args.atlas:
        sheet = Image.open(args.atlas).convert("RGBA")
        for rc in args.cells or []:
            r, c = map(int, rc.split(","))
            tiles.append((f"atlas_r{r}c{c}", sheet.crop((c * 32, r * 32, c * 32 + 32, r * 32 + 32))))
    return tiles


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("tiles", help="valida tiles e gera previews")
    t.add_argument("png", nargs="*", help="PNGs 32x32")
    t.add_argument("--atlas", help="atlas PNG (células de 32x32)")
    t.add_argument("--cells", nargs="+", metavar="r,c", help="células do atlas (linha,coluna)")
    t.add_argument("--group", action="store_true", help="variantes do mesmo terreno: mede costura em mistura aleatória")
    t.add_argument("--context", default="/home/chips/git/games/Veredas-Assets/spritesheet.png",
                   help="atlas de contexto para o mapa misto")
    t.add_argument("--object", help="PNG de objeto para o mapa (c)")
    t.add_argument("--anchor", default="16,28", help="ponto de pé do objeto, x,y")
    t.add_argument("--out", required=True)
    args = ap.parse_args()

    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    tiles = load_inputs(args)
    if not tiles:
        ap.error("nenhum tile informado")
    ctx = Image.open(args.context).convert("RGBA")
    cell = lambda r, c: ctx.crop((c * 32, r * 32, c * 32 + 32, r * 32 + 32))
    grass, soil = cell(2, 0), cell(0, 0)

    report = {"limiares": {"semi": MAX_SEMI, "fora": MAX_OUTSIDE, "faltando": MAX_MISSING, "iou_min": MIN_IOU,
                           "cores_max": MAX_COLORS, "costura_max": MAX_SEAM_RATIO}, "tiles": [], "grupo": None}
    for name, img in tiles:
        m = metrics(img, name)
        if m["size_ok"]:
            m["preview_map"] = f"{name}_map.png"
            save4x(iso.render_map({c: img for c in GRID}), out / m["preview_map"])
            # (b) tile novo em um remendo 4x4 no meio de grama, ao lado de uma faixa de terra
            cells = {c: grass for c in GRID}
            cells.update({(x, y): soil for x in range(8) for y in range(8) if y >= 6})
            cells.update({(x, y): img for x in range(2, 6) for y in range(2, 6)})
            m["preview_mixed"] = f"{name}_mixed.png"
            save4x(iso.render_map(cells), out / m["preview_mixed"])
            if args.object:
                ax, ay = map(int, args.anchor.split(","))
                obj = Image.open(args.object).convert("RGBA")
                cv = iso.render_map({c: img for c in GRID}, pad=64)
                iso.place_object(cv, obj, (ax, ay), (4, 4))
                if PLAYER.exists():
                    iso.place_object(cv, Image.open(PLAYER).convert("RGBA").crop((0, 0, 32, 32)), (16, 28), (6, 4))
                m["preview_object"] = f"{name}_object.png"
                save4x(cv, out / m["preview_object"])
        report["tiles"].append(m)

    if args.group and len(tiles) > 1:
        imgs = [i for _, i in tiles if i.size == (32, 32)]
        scores = [seam_score(imgs, seed=s) for s in range(5)]
        scores = [s for s in scores if s is not None]
        report["grupo"] = {"seam_ratio_mistura": round(float(np.mean(scores)), 3) if scores else None,
                           "pass": bool(scores) and float(np.mean(scores)) <= MAX_SEAM_RATIO}
        save4x(iso.render_map({c: imgs[(c[0] * 7 + c[1] * 3) % len(imgs)] for c in GRID}), out / "grupo_mix.png")

    (out / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False))
    write_html(out, report)
    for m in report["tiles"]:
        print(("OK   " if m["pass"] else "FALHA"), m["name"], m.get("iou"), m.get("seam_ratio"), ", ".join(m["fails"] + [f"aviso: {w}" for w in m.get("warns", [])]))
    if report["grupo"]:
        print("grupo:", report["grupo"])


def write_html(out, report):
    rows = []
    for m in report["tiles"]:
        imgs = "".join(f'<img src="{m[k]}">' for k in ("preview_map", "preview_mixed", "preview_object") if k in m)
        rows.append(f'<section class="{"ok" if m["pass"] else "bad"}"><h3>{html.escape(m["name"])} '
                    f'{"passou" if m["pass"] else "falhou: " + html.escape(", ".join(m["fails"]))}</h3>'
                    f'<pre>{html.escape(json.dumps({k: v for k, v in m.items() if not k.startswith("preview")}, ensure_ascii=False))}</pre>{imgs}</section>')
    g = ""
    if report["grupo"]:
        g = f'<h2>Grupo</h2><pre>{report["grupo"]}</pre><img src="grupo_mix.png">'
    (out / "index.html").write_text(
        '<meta charset="utf-8"><style>body{background:#222;color:#ddd;font:14px monospace}'
        '.bad h3{color:#f77}.ok h3{color:#7f7}img{image-rendering:pixelated;max-width:48%;background:#f0f}</style>'
        f'<h1>isocheck</h1><pre>{html.escape(json.dumps(report["limiares"]))}</pre>{g}{"".join(rows)}')


if __name__ == "__main__":
    main()
