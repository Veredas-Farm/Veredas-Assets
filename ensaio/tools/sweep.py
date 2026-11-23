#!/usr/bin/env python3
"""Sweep de modelos de pixel art sobre os assets da entrega (img2img + repixelate).

  bases              monta as folhas de entrada em specs/sweep/ (+ layout.json)
  queue [modelo...]  importa as bases no aig e enfileira modelo x base x denoise x seed
                     (grava specs/sweep/jobs.json; precisa rodar fora do sandbox)
  collect            lê o banco do aig (só leitura) e reduz as imagens prontas
  sheets             folhas de comparação out/sweep/<asset>.png e resumo.png

Redução de cada asset: recorte da célula na geração, fundo removido
(pipeline.remove_bg), repixelate --pixel-size = px da geração por px do
original (grade imposta), volta ao tamanho exato do original (mesmo anchor),
alfa pela máscara (terreno: alfa do original). Variante `pal`: cores presas
à paleta do próprio original.
"""
import argparse, json, os, sqlite3, subprocess, sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "objects"))
import pipeline as pl  # noqa: E402

SPECS = ROOT / "specs" / "sweep"
OUT = ROOT / "out" / "sweep"
ENT = ROOT / "entrega"
KIT = ROOT / "out" / "kit-moss-tex" / "terrain_atlas.png"
DB = Path.home() / ".local/share/ai-gallery/gallery.db"
IMAGES = Path.home() / ".local/share/ai-gallery/images"
TMP = Path(os.environ.get("TMPDIR", "/tmp")) / "sweep"
S = 8          # ampliação nearest das bases
MARGIN, GAP = 6, 12
TAIL = ("isometric pixel art, cerrado, muted earthy palette, crisp clean pixels, "
        "plain white background")

# modelo: template do aig, estilo, (denoise baixo, alto), seeds por combinação
MODELS = {
    "moss-pixel":     ("moss-pixel", "moss-pixel-lora", (0.5, 0.7), 2),
    "sdxl-pad":       ("sdxl-pad", "sdxl-pixel-art-diffusion", (0.5, 0.65), 2),
    "sdxl-pixel":     ("sdxl-pixel", "pixel-art-xl", (0.5, 0.65), 2),
    "sdxl-pixel-iso": ("sdxl-pixel", "pixel-art-xl-isometric", (0.5, 0.65), 2),
    "sd15-pixel":     ("sd15-pixel", "sd15-pixel-toolkit", (0.45, 0.6), 2),
    "moss-refiner":   ("moss-refiner", "moss-pixel-refiner", (0.65, 0.8), 2),
    "flux-pixel":     ("flux-pixel", "flux-pixel-lora", (0.45, 0.6), 1),
    "moss-iso":       ("moss", "isometric", (0.65, 0.8), 1),
    "moss-sentence":  ("moss", "moss-pixel-art-sentence", (0.65, 0.8), 1),
    "sdxl-sai":       ("sdxl", "pixel-art-sai", (0.6, 0.75), 1),
    "flux":           ("flux", None, (0.72,), 1),
}
SEED = 1001

TREE = "game object sprites for an isometric farming game, three-quarter top-down view, each tree standing on the ground"
BASES = {
    "t1": dict(kind="row", assets=["fases/arvore_ipe_amarelo_florido", "fases/arvore_pequi_maduro"],
               prompt=f"two separate small brazilian cerrado trees side by side, {TREE}. left: yellow ipe tree, "
                      "crown covered in bright yellow flowers, thin dark trunk. right: pequi tree, rounded dense "
                      "dark green crown with small yellow-green fruits, short thick trunk"),
    "t2": dict(kind="row", assets=["fases/arvore_paineira_florida", "fases/arvore_ipe_amarelo_seco"],
               prompt=f"two separate small brazilian cerrado trees side by side, {TREE}. left: paineira tree with "
                      "a swollen bottle shaped grey trunk and a crown of pink flowers. right: leafless dry ipe "
                      "tree in the dry season, bare twisted brown branches"),
    "t3": dict(kind="row", assets=["fases/arvore_baru_maduro", "fases/arvore_cagaita_florida"],
               prompt=f"two separate small brazilian cerrado trees side by side, {TREE}. left: large baru tree, "
                      "wide dark green crown with brown fruits, crooked trunk. right: small cagaita tree with a "
                      "rounded crown dotted with white flowers"),
    "obj": dict(kind="grid", cols=2, assets=["objects/carro_de_boi", "objects/moinho",
                                              "objects/carroca_4rodas", "objects/moinho_agua"],
                prompt="2 by 2 grid of separate farm objects for an isometric farming game, three-quarter "
                       "top-down view. top row: wooden ox cart with two big spoked wheels, small wooden "
                       "water mill hut with a side wheel on dirt. bottom row: four-wheeled wooden wagon, wooden water mill with a "
                       "paddle wheel over a small pond"),
    "small": dict(kind="grid", cols=4, cell=44, assets=[
        "objects/cupinzeiro_alto", "objects/cupinzeiro_baixo", "objects/pilao", "objects/cerca_aroeira",
        "objects/cupinzeiro_alto_c", "objects/cupinzeiro_baixo_c", "objects/pilao_b", "objects/cerca_aroeira_esp",
        "icons/arroz", "icons/cagaita", "icons/cana", "icons/facao",
        "icons/farinha", "icons/melancia", "icons/pequi", "icons/rapadura",
        "personagem/farmer_idle#0", "icons/feijao", "icons/soja", "icons/capim"],
        prompt="sprite sheet of small game items in a 4 by 5 grid, isometric farming game, each item "
               "separate. row 1: tall termite mound, low termite mound, wooden mortar and pestle, wooden "
               "fence post section. row 2: termite mound, termite mound, wooden mortar, fence section. "
               "row 3 item icons: rice sheaf, small yellow fruit, sugar cane, machete. row 4 item icons: "
               "sack of manioc flour, watermelon, pequi fruit, brown sugar block. row 5: small farmer "
               "with straw hat standing, beans, soybeans, grass bundle"),
    "crops": dict(kind="grid", cols=1, assets=["crops/arroz", "crops/feijao"],
                  prompt="two rows of crop growth stages for a farming game, six stages each from sprout "
                         "to ripe to dry, left to right. top row: rice plants. bottom row: bean plants"),
    "terrain": dict(kind="terrain", cells=[  # (coluna, linha) no atlas do kit-moss-tex
        (0, 0), (1, 0), (2, 0), (3, 0), (0, 2), (1, 2), (2, 2), (3, 2),
        (0, 3), (1, 3), (0, 4), (1, 4), (0, 5), (1, 5), (0, 7), (0, 8)],
        names=["grama"] * 4 + ["trilha"] * 4 + ["palha"] * 2 + ["umida"] * 2 + ["cascalho"] * 2 + ["arado", "arado_molhado"],
        prompt="isometric pixel art tileset sheet, 4 by 4 grid of isometric cube blocks, every block a "
               "small slab with a flat 2:1 diamond top and dark brown soil sides, same light from the top "
               "left, rows: green grass blocks, brown dirt path blocks, dry straw yellow grass and dark "
               "green damp grass blocks, grey gravel blocks and tilled soil blocks"),
}


def load_asset(a):
    """`dir/nome` em entrega/objetos (ou personagem/...#quadro) -> RGBA."""
    name, _, frame = a.partition("#")
    p = ENT / ("objetos/" + name if not name.startswith("personagem") else name)
    im = Image.open(p.with_suffix(".png")).convert("RGBA")
    if frame:
        f = int(frame)
        im = im.crop((f * 32, 0, f * 32 + 32, 32))
    return im


def akey(a):
    d, n = a.split("/")[-2:]
    pre = {"icons": "icone_", "crops": "cultivo_"}.get(d, "")
    return pre + n.replace("#", "_")


def cmd_bases(_):
    SPECS.mkdir(parents=True, exist_ok=True)
    layout = {}
    for b, spec in BASES.items():
        cells = []
        if spec["kind"] == "terrain":
            kit = Image.open(KIT).convert("RGBA")
            W = H = 4 * 32
            canvas = Image.new("RGBA", (W, H), (255, 255, 255, 255))
            for i, ((c, r), nm) in enumerate(zip(spec["cells"], spec["names"])):
                t = kit.crop((c * 32, r * 32, c * 32 + 32, r * 32 + 32))
                x, y = (i % 4) * 32, (i // 4) * 32
                canvas.alpha_composite(t, (x, y))
                key = f"terreno_{i:02d}_{nm}"
                SPECS.joinpath("orig").mkdir(exist_ok=True)
                t.save(SPECS / "orig" / f"{key}.png")
                cells.append(dict(asset=key, rect=[x, y, 32, 32], terrain=True))
        else:
            ims = [load_asset(a) for a in spec["assets"]]
            if spec["kind"] == "row":
                hmax = max(i.height for i in ims)
                W = 2 * MARGIN + sum(i.width for i in ims) + GAP * (len(ims) - 1)
                H = 2 * MARGIN + hmax
                pos, x = [], MARGIN
                for i in ims:
                    pos.append((x, MARGIN + hmax - i.height))
                    x += i.width + GAP
            else:
                cols = spec["cols"]
                rows = (len(ims) + cols - 1) // cols
                cw = spec.get("cell") or max(i.width for i in ims) + GAP
                ch = spec.get("cell") or max(i.height for i in ims) + GAP
                W, H = cols * cw + 2 * MARGIN, rows * ch + 2 * MARGIN
                pos = []
                for k, i in enumerate(ims):
                    c, r = k % cols, k // cols
                    pos.append((MARGIN + c * cw + (cw - i.width) // 2, MARGIN + r * ch + (ch - i.height) // 2))
            canvas = Image.new("RGBA", (W, H), (255, 255, 255, 255))
            for a, i, (x, y) in zip(spec["assets"], ims, pos):
                canvas.alpha_composite(i, (x, y))
                SPECS.joinpath("orig").mkdir(exist_ok=True)
                i.save(SPECS / "orig" / f"{akey(a)}.png")
                cells.append(dict(asset=akey(a), rect=[x, y, i.width, i.height]))
        big = canvas.convert("RGB").resize((canvas.width * S, canvas.height * S), Image.NEAREST)
        big.save(SPECS / f"{b}.png")
        layout[b] = dict(size=[canvas.width, canvas.height], cells=cells, prompt=spec["prompt"] + ", " + TAIL)
        print(b, canvas.size, "->", big.size, f"{big.width * big.height / 1e6:.2f} MP")
    (SPECS / "layout.json").write_text(json.dumps(layout, indent=1, ensure_ascii=False))


def aig(*args):
    r = subprocess.run(["aig", *args, "--json"], capture_output=True, text=True, cwd=ROOT.parent)
    if r.returncode != 0:
        raise RuntimeError(r.stderr[-1500:] + r.stdout[-1500:])
    return json.loads(r.stdout)


def cmd_queue(a):
    layout = json.loads((SPECS / "layout.json").read_text())
    jf = SPECS / "jobs.json"
    jobs = json.loads(jf.read_text()) if jf.exists() else {}
    ids = jobs.get("_bases", {})
    for b in layout:
        if b not in ids:
            res = aig("import", str(SPECS / f"{b}.png"))
            ids[b] = (res["added"] + res["existing"])[0]
            ids[b] = ids[b]["id"] if isinstance(ids[b], dict) else ids[b]
    jobs["_bases"] = ids
    bases = a.bases or list(layout)
    for m in a.models or list(MODELS):
        tpl, style, dns, n = MODELS[m]
        for b in bases:
            for dn in dns:
                key = f"{m}|{b}|{dn}"
                if key in jobs:
                    continue
                args = ["job", "add", tpl, "-n", str(n), "--tag", "sweep", "--tag", f"sweep-{m}",
                        "--base", ids[b], "--set", f"denoise={dn}", "--set", f"seed={SEED}"]
                prompt = layout[b]["prompt"]
                if style:
                    args += ["--set", f"style={style}"]
                else:
                    prompt = "pixel art, " + prompt
                args += ["--set", f"prompt={prompt}"]
                res = aig(*args)
                jobs[key] = res["jobs"][0]
                print("queued", key, jobs[key], flush=True)
                jf.write_text(json.dumps(jobs, indent=1))
    jf.write_text(json.dumps(jobs, indent=1))


# ---------------------------------------------------------------- redução

def images_of(job_ids):
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    q = ("select i.id, coalesce(i.location, i.hash), i.seed, i.job, i.width, i.height, i.duration_ms, j.state, j.error "
         "from job j left join image i on i.job = j.id where j.id in (%s)" % ",".join("?" * len(job_ids)))
    rows = con.execute(q, job_ids).fetchall()
    con.close()
    return rows


def repix(rgb, mask, px):
    TMP.mkdir(parents=True, exist_ok=True)
    src, dst = TMP / "in.png", TMP / "out.png"
    Image.fromarray(pl.flat_bg(rgb, mask)).save(src)
    pl.run(["repixelate", src, "-o", dst, "--pixel-size", max(2, round(px)), "--colors", 0,
            "--blend", 0.5, "--no-bg"])
    return np.asarray(Image.open(dst).convert("RGB"))


def reduce_cell(gen, sx, sy, rect, orig, terrain):
    """Recorte da célula (com folga para achar o fundo) -> RGBA do tamanho do original."""
    x, y, w, h = rect
    pad = GAP // 2 if not terrain else 0
    X0, Y0 = round((x - pad) * sx), round((y - pad) * sy)
    X1, Y1 = round((x + w + pad) * sx), round((y + h + pad) * sy)
    X0, Y0 = max(X0, 0), max(Y0, 0)
    X1, Y1 = min(X1, gen.shape[1]), min(Y1, gen.shape[0])
    rgb = gen[Y0:Y1, X0:X1]
    oa = np.asarray(orig)[..., 3] > 0
    if terrain:
        mask = np.ones(rgb.shape[:2], bool)
    else:
        mask, _ = pl.remove_bg(rgb)
    if not mask.any():
        return None
    small = repix(rgb, mask, (sx + sy) / 2)
    # volta à grade do original: a célula inteira (com folga) tem (w+2pad)x(h+2pad) px
    full = (w + 2 * pad, h + 2 * pad)
    small = np.asarray(Image.fromarray(small).resize(full, Image.NEAREST))
    m = pl.down_mask(mask, full)
    small, m = small[pad:pad + h, pad:pad + w], m[pad:pad + h, pad:pad + w]
    if terrain:
        m = oa
    if not terrain:
        from scipy import ndimage
        for _ in range(2):
            edge = m & ~ndimage.binary_erosion(m)
            m = m & ~(edge & (small.min(-1) > 215))
        o = np.asarray(orig)
        if (o[..., :3].min(-1)[oa] > 215).mean() < 0.02:  # original sem branco: branco é resto do fundo
            m = m & ~(small.min(-1) > 225)
    m = pl.clean_mask(m)
    return np.dstack([small, (m * 255).astype(np.uint8)])


def palette_of(orig):
    a = np.asarray(orig)
    return np.unique(a[a[..., 3] > 0][:, :3], axis=0)


def score(red, orig):
    """IoU da silhueta - distância média de cor (0..1) nos pixels comuns."""
    ra, oa = red[..., 3] > 0, np.asarray(orig)[..., 3] > 0
    inter = (ra & oa).sum()
    iou = inter / max((ra | oa).sum(), 1)
    if not inter:
        return iou - 1
    d = np.abs(red[..., :3][ra & oa].astype(float) - np.asarray(orig)[..., :3][ra & oa]).mean() / 255
    return iou - d


def cmd_collect(a):
    layout = json.loads((SPECS / "layout.json").read_text())
    jobs = json.loads((SPECS / "jobs.json").read_text())
    keys = {v: k for k, v in jobs.items() if k != "_bases"}
    done_f = OUT / "cells" / "index.json"
    index = json.loads(done_f.read_text()) if done_f.exists() else {}
    states = {}
    for iid, hsh, seed, job, W, H, ms, state, err in images_of(list(keys)):
        states[state] = states.get(state, 0) + (1 if iid or state != "done" else 0)
        if state == "failed":
            index.setdefault("_failed", {})[keys[job]] = (err or "")[:300]
        if not iid or iid in index:
            continue
        m, b, dn = keys[job].split("|")
        src = Path(hsh) if "/" in hsh else IMAGES / hsh[:2] / f"{hsh}.png"
        gen = np.asarray(Image.open(src).convert("RGB"))
        bw, bh = layout[b]["size"]
        sx, sy = W / bw, H / bh
        rec = dict(model=m, base=b, dn=float(dn), seed=seed, ms=ms, sx=sx, cells={})
        for c in layout[b]["cells"]:
            orig = Image.open(SPECS / "orig" / f"{c['asset']}.png").convert("RGBA")
            try:
                red = reduce_cell(gen, sx, sy, c["rect"], orig, c.get("terrain", False))
            except Exception as e:  # noqa: BLE001
                print("falhou", m, b, c["asset"], e)
                red = None
            if red is None:
                continue
            d = OUT / "cells" / c["asset"]
            d.mkdir(parents=True, exist_ok=True)
            stem = f"{m}_d{int(round(float(dn) * 100))}_{seed}"
            Image.fromarray(red, "RGBA").save(d / f"{stem}.png")
            m2 = red[..., 3] > 0
            pal = pl.map_palette(red[..., :3], m2, palette_of(orig))
            Image.fromarray(np.dstack([pal, red[..., 3]]), "RGBA").save(d / f"{stem}_pal.png")
            rec["cells"][c["asset"]] = dict(file=stem, score=round(float(score(red, orig)), 4))
        index[iid] = rec
        print("ok", m, b, dn, seed, len(rec["cells"]), flush=True)
    done_f.parent.mkdir(parents=True, exist_ok=True)
    done_f.write_text(json.dumps(index, indent=1))
    print("estados:", states)


# ---------------------------------------------------------------- folhas

_GRASS = None


def grass_bg(w, h):
    """Plano de grama do kit (blocos 32x16 em losango), recortado em w x h."""
    global _GRASS
    if _GRASS is None:
        kit = Image.open(KIT).convert("RGBA")
        tiles = [kit.crop((c * 32, 0, c * 32 + 32, 32)) for c in range(4)]
        big = Image.new("RGBA", (640, 640), (90, 110, 70, 255))
        for j in range(0, 84):
            for i in range(0, 21):
                big.alpha_composite(tiles[(i * 7 + j * 3) % 4], (i * 32 + (16 if j % 2 else 0), j * 8))
        _GRASS = big.crop((48, 48, 640 - 48, 640 - 48))
    return _GRASS.crop((0, 0, w, h)).copy()


def paste_on(bg, im, x, y):
    if x < 0 or y < 0:
        return
    bg.alpha_composite(im, (x, y))


def label(img, xy, text, fill=(255, 255, 255, 255)):
    d = ImageDraw.Draw(img)
    x, y = xy
    d.text((x + 1, y + 1), text, fill=(0, 0, 0, 255))
    d.text((x, y), text, fill=fill)


def best_by(index):
    """(asset, modelo, dn) -> (score, stem) da melhor seed."""
    best = {}
    for iid, r in index.items():
        if iid.startswith("_"):
            continue
        for asset, c in r["cells"].items():
            k = (asset, r["model"], r["dn"])
            if k not in best or c["score"] > best[k][0]:
                best[k] = (c["score"], c["file"])
    return best


def cmd_sheets(a):
    index = json.loads((OUT / "cells" / "index.json").read_text())
    best = best_by(index)
    assets = sorted({k[0] for k in best})
    models = [m for m in MODELS if any(k[1] == m for k in best)]
    Z = 3
    for asset in assets:
        orig = Image.open(SPECS / "orig" / f"{asset}.png").convert("RGBA")
        w, h = orig.size
        cw, ch = w + 8, h + 8
        cols = ["original", "baixo", "alto", "baixo pal", "alto pal"]
        rows = [m for m in models if any(k[0] == asset and k[1] == m for k in best)]
        LW = 110
        sheet = Image.new("RGBA", (LW + len(cols) * cw * Z, 14 + len(rows) * (ch * Z + 12)), (30, 30, 30, 255))
        for ci, cn in enumerate(cols):
            label(sheet, (LW + ci * cw * Z + 4, 2), cn)
        for ri, m in enumerate(rows):
            y0 = 14 + ri * (ch * Z + 12)
            dns = sorted({k[2] for k in best if k[0] == asset and k[1] == m})
            label(sheet, (4, y0 + 4), m)
            for di, dn in enumerate(dns):
                label(sheet, (4, y0 + 18 + di * 14), f"dn {dn}: {best[(asset, m, dn)][0]:.2f}")
            tiles = [orig]
            for suf in ("", "_pal"):
                for dn in (dns + dns)[:2] if len(dns) == 1 else dns:
                    p = OUT / "cells" / asset / f"{best[(asset, m, dn)][1]}{suf}.png"
                    tiles.append(Image.open(p))
            tiles = [tiles[0], tiles[1], tiles[2], tiles[3], tiles[4]] if len(tiles) == 5 else tiles
            for ci, t in enumerate(tiles):
                cell = grass_bg(cw, ch)
                cell.alpha_composite(t, (4, 4))
                cell = cell.resize((cw * Z, ch * Z), Image.NEAREST)
                sheet.alpha_composite(cell, (LW + ci * cw * Z, y0))
        sheet.convert("RGB").save(OUT / f"{asset}.png")
    print("folhas:", len(assets))
    resumo(best, assets, models)


RESUMO = ["arvore_ipe_amarelo_florido", "arvore_pequi_maduro", "arvore_paineira_florida",
          "arvore_ipe_amarelo_seco", "carro_de_boi", "moinho_agua", "cupinzeiro_alto", "pilao",
          "icone_pequi", "icone_melancia", "farmer_idle_0", "terreno_00_grama", "terreno_04_trilha",
          "terreno_12_cascalho"]


def resumo(best, assets, models):
    """Uma linha por modelo, uma coluna por asset do RESUMO: melhor dn por score, 2x, sobre grama."""
    Z = 2
    sel = [x for x in RESUMO if x in assets]
    origs = {x: Image.open(SPECS / "orig" / f"{x}.png").convert("RGBA") for x in sel}
    widths = [origs[x].width + 6 for x in sel]
    hmax = max(o.height for o in origs.values()) + 6
    LW = 100
    W = LW + sum(widths) * Z
    rows = ["original"] + models
    sheet = Image.new("RGBA", (W, len(rows) * (hmax * Z + 4) + 4), (30, 30, 30, 255))
    for ri, m in enumerate(rows):
        y0 = 4 + ri * (hmax * Z + 4)
        label(sheet, (4, y0 + 4), m)
        x0 = LW
        for x, wd in zip(sel, widths):
            o = origs[x]
            if m == "original":
                t = o
            else:
                cand = [(best[k][0], k) for k in best if k[0] == x and k[1] == m]
                t = None
                if cand:
                    _, k = max(cand)
                    t = Image.open(OUT / "cells" / x / f"{best[k][1]}.png")
            cell = grass_bg(wd, hmax)
            if t is not None:
                cell.alpha_composite(t, (3, hmax - 3 - t.height))
            sheet.alpha_composite(cell.resize((wd * Z, hmax * Z), Image.NEAREST), (x0, y0))
            x0 += wd * Z
    sheet.convert("RGB").save(OUT / "resumo.png")
    print("resumo:", OUT / "resumo.png")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("bases")
    q = sub.add_parser("queue")
    q.add_argument("models", nargs="*")
    q.add_argument("--bases", nargs="*")
    sub.add_parser("collect")
    sub.add_parser("sheets")
    a = ap.parse_args()
    {"bases": cmd_bases, "queue": cmd_queue, "collect": cmd_collect, "sheets": cmd_sheets}[a.cmd](a)


if __name__ == "__main__":
    main()
