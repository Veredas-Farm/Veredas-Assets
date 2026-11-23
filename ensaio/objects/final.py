#!/usr/bin/env python3
"""Gera os assets finais do ensaio em out/ a partir das gerações escolhidas.

Receita (ver README): moss-pixel -> pipeline (fundo, recorte, redução box,
contorno 'auto', paleta do asset vizinho) -> tela final com ponto de pé.
"""
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

import pipeline as P

HERE = Path(__file__).resolve().parent
RUNS = HERE.parent / "runs"
ASSETS = HERE.parents[1]
OUT = HERE / "out"
TMP = HERE / "tmp"

ICONS = {  # nome: (geração, variante)
    "cagaita": ("o02/cagaita-moss-4006188599.png", "box"),
    "facao": ("o01/facao-moss-1723800330.png", "box"),
    "feijao": ("o04/feijao2-moss-2476511434.png", "box"),
    "arroz": ("o04/arroz-moss-525959464.png", "unfake"),
    "cana": ("o04/cana-moss-3291445309.png", "box"),
    "soja": ("o12/soja3-moss-2925963245.png", "box"),
    "capim": ("o06/capim-moss-1754089777.png", "box"),
    "rapadura": ("o16/rapadura-moss-4170676467.png", "box"),
    "farinha": ("o16/farinha-moss-1366937285.png", "box"),
    "pequi": ("o16/pequi-moss-383514128.png", "box"),
    "melancia": ("o17/melancia-moss-2835249478.png", "box"),
}
CROPS = {  # nome: (geração com estágios em fileira, caixa máx. do maior estágio WxH, célula WxH)
    "cana": ("o14/st-cana-dead-moss-3032294403.png", (30, 64), (32, 72), 6, True),
    "mandioca": ("o14/st-mandioca-dead-moss-980485266.png", (30, 56), (32, 64), 5, True),
    "feijao": ("o12/st-feijao-dead-moss-3838748480.png", (28, 34), (32, 40), 6, True),  # estágio seco gerado
    "arroz": ("o05/st-arroz-moss-3651684016.png", (28, 40), (32, 48)),
    "soja": ("o05/st-soja-moss-2545475733.png", (28, 40), (32, 48)),
    "melancia": ("o11/st-melancia2-moss-3168662100.png", (30, 24), (32, 32)),
    "capim": ("o09/st-capim-moss-2402555158.png", (28, 40), (32, 48)),
}
CROP_PAL_TOL = 0  # 0 = tudo na paleta do milho + itens (verdes mais sóbrios)
TREE_VARIANT = "unfake"  # box borra flores e frutos pequenos; unfake (dominante) mantém
TREES = {  # nome: (geração, caixa, paleta)
    "cagaita": ("o05/tree-cagaita2-moss-2297201831.png", (64, 76)),
    "cagaita_densa": ("o06/tree-cagaita3-moss-748520711.png", (60, 76)),
    "cagaita_densa_b": ("o11/tree-cagaita3-moss-4133204261.png", (60, 76)),
    "cagaita_densa_c": ("o11/tree-cagaita3-moss-4133204262.png", (60, 76)),
    # estações: img2img (denoise 0.6) da cagaita_densa, mesmo desenho
    "cagaita_densa_flor": ("o13/tree-flor-2270833164.png", (60, 76)),
    "cagaita_densa_seca": ("o13/tree-seca-2273473980.png", (60, 76)),
    "cagaita_densa_folhas": ("o13/tree-semfruto-492024785.png", (60, 76)),
    "cagaita_densa_b_flor": ("o15/treeb-flor-3794794350.png", (60, 76)),
    "cagaita_densa_b_seca": ("o15/treeb-seca-1547212519.png", (60, 76)),
}
CARTS = {
    "carro_de_boi": ("o10/carro-boi3-moss-3721099278.png", (60, 44), True),
    "carroca_4rodas": ("o04/carro-boi-moss-954603391.png", (60, 44)),
    "reboque": ("o04/reboque-moss-208193025.png", (56, 42)),
    "carroca_fueiros": ("o06/carro-boi2-moss-81225285.png", (60, 44)),
}


def palette_of(*files):
    cols = [P.load_palette(f) for f in files]
    return np.unique(np.concatenate(cols), axis=0)


def icons():
    pal = P.load_palette(ASSETS / "items_spritesheet.png")
    d = OUT / "icons"
    d.mkdir(parents=True, exist_ok=True)
    ims = []
    for name, (src, v) in ICONS.items():
        im, _ = P.process(RUNS / src, v, (28, 28), (32, 32), "center", 20, "auto", pal=pal)
        im.save(d / f"{name}.png")
        ims.append(im)
    sheet = Image.new("RGBA", (32 * len(ims), 32))
    for i, im in enumerate(ims):
        sheet.alpha_composite(im, (32 * i, 0))
    sheet.save(OUT / "icons_sheet.png")
    # prévia: itens atuais (linha de cima) e novos (embaixo), 4x
    ref = Image.open(ASSETS / "items_spritesheet.png").convert("RGBA")
    refs = [ref.crop((c * 32, r * 32, c * 32 + 32, r * 32 + 32)) for r, c in ((0, 0), (1, 4), (2, 0), (2, 1), (2, 2))]
    prev = Image.new("RGBA", (max(len(ims), 5) * 128 + 32, 32 * 2 * 4 + 40), P.GRASS)
    # a linha de 1x precisa caber: 34 px por ícone
    if (len(refs) + len(ims)) * 34 + 8 > prev.width:
        prev = Image.new("RGBA", ((len(refs) + len(ims)) * 34 + 8, prev.height), P.GRASS)
    for i, im in enumerate(refs):
        prev.alpha_composite(im.resize((128, 128), Image.NEAREST), (i * 128 + 16, 0))
    for i, im in enumerate(ims):
        prev.alpha_composite(im.resize((128, 128), Image.NEAREST), (i * 128 + 16, 128))
    for i, im in enumerate(refs + ims):
        prev.alpha_composite(im, (i * 34 + 4, 260))
    prev.save(OUT / "icons_preview.png")


def crops():
    pal = palette_of(ASSETS / "corn_spritesheet.png", ASSETS / "items_spritesheet.png")
    d = OUT / "crops"
    d.mkdir(parents=True, exist_ok=True)
    strips = []
    for name, (src, box, cell, *n) in CROPS.items():
        P.PAL_TOL, P.HOLE_MIN = CROP_PAL_TOL, 80
        expect, has_dead = (n[0], n[1]) if n else (5, False)
        res = P.stages_from_row(RUNS / src, "box", box, cell, 20, "auto", 38.0, pal, 6, nosoil=True, expect=expect)
        if not has_dead:  # sem estágio seco na geração: recolore o maduro
            res.append((P.wither(res[-1][0]), res[-1][1]))
        else:  # o seco gerado tem a forma certa; a cor vai para o palha do milho seco
            res[-1] = (P.wither(res[-1][0]), res[-1][1])
        sheet = Image.new("RGBA", (cell[0] * len(res), cell[1]))
        meta = []
        for i, (im, m) in enumerate(res):
            sheet.alpha_composite(im, (cell[0] * i, 0))
            meta.append({"stage": i, "rect": [cell[0] * i, 0, cell[0], cell[1]],
                         "anchor": m["anchor"]})
        sheet.save(d / f"{name}.png")
        (d / f"{name}.json").write_text(json.dumps({"cell": cell, "stages": meta}, indent=1))
        strips.append((name, sheet, cell))
    # prévia com o milho atual em cima, tudo em 4x
    corn = Image.open(ASSETS / "corn_spritesheet.png").convert("RGBA").crop((15, 70, 250, 160))
    rows = [corn] + [s for _, s, _ in strips]
    W = max(r.width for r in rows) * 4
    H = sum(r.height * 4 + 8 for r in rows)
    prev = Image.new("RGBA", (W, H), P.GRASS)
    y = 0
    for r in rows:
        prev.alpha_composite(r.resize((r.width * 4, r.height * 4), Image.NEAREST), (0, y))
        y += r.height * 4 + 8
    prev.save(OUT / "crops_preview.png")


def objects():
    """Árvore e carretas, com o ponto de pé no .json."""
    d = OUT / "objects"
    d.mkdir(parents=True, exist_ok=True)
    P.HOLE_MIN = 300
    tree_pal = palette_of(ASSETS / "arvore_pequi.png", ASSETS / "arvore_baru.png")
    # as árvores atuais não têm branco: duas cores creme para as flores da cagaita
    tree_pal = np.concatenate([tree_pal, [[244, 238, 214], [222, 214, 170]]]).astype(np.uint8)
    cart_pal = palette_of(ASSETS / "carreta.png", ASSETS / "arvore_pequi.png", ASSETS / "arvore_baru.png")
    made = {}
    for name, (src, box) in TREES.items():
        P.PAL_TOL = 0
        im, meta = P.process(RUNS / src, TREE_VARIANT, box, box, "bottom", 24, "none", pal=tree_pal)
        made[f"arvore_{name}"] = (im, meta)
    for name, (src, box, *flip) in CARTS.items():
        P.PAL_TOL = 30.0
        im, meta = P.process(RUNS / src, "box", box, (box[0] + 2, box[1] + 2), "bottom", 24, "auto", pal=cart_pal)
        if flip and flip[0]:  # espelha para ficar no mesmo sentido da caminhonete
            im = im.transpose(Image.FLIP_LEFT_RIGHT)
        # veículo em 3/4: o pé fica no meio da área que ele ocupa no chão, não na roda mais baixa
        meta["anchor"] = [im.width // 2, im.height - 1 - box[1] // 5]
        made[name] = (im, meta)
    for name, (im, meta) in made.items():
        im.save(d / f"{name}.png")
        (d / f"{name}.json").write_text(json.dumps(meta))
    # prévia das árvores e carretas em 3x
    ims = [im for im, _ in made.values()]
    W = sum(i.width + 6 for i in ims)
    H = max(i.height for i in ims)
    prev = Image.new("RGBA", (W, H), P.GRASS)
    x = 0
    for im in ims:
        prev.alpha_composite(im, (x, H - im.height))
        x += im.width + 6
    prev.resize((W * 3, H * 3), Image.NEAREST).save(OUT / "objects_preview.png")


def scene():
    """Cena isométrica de conferência (out/scene.png), com árvores, plantas e carretas atuais."""
    import subprocess

    def stage(crop, i, cell):
        meta = json.loads((OUT / "crops" / f"{crop}.json").read_text())
        w, h = meta["cell"]
        return f"{OUT}/crops/{crop}.png[crop={i * w},0,{(i + 1) * w},{h}]@{cell}"

    o = OUT / "objects"
    objs = [f"{ASSETS}/arvore_pequi.png@1,1", f"{o}/arvore_cagaita_densa.png@4,0",
            f"{o}/arvore_cagaita_densa_flor.png@6,0", f"{o}/arvore_cagaita.png@0,4",
            f"{ASSETS}/arvore_buriti2.png@0,7",
            f"{o}/carro_de_boi.png@9,1", f"{o}/reboque.png@10,4",
            f"{ASSETS}/carreta.png[crop=36,75,121,117]@10,8"]
    tilled = []
    for row, (crop, n) in enumerate([("cana", 6), ("mandioca", 5), ("feijao", 6)]):
        for i in range(n):
            cell = f"{2 + i},{6 + row}"
            objs.append(stage(crop, i, cell))
            tilled.append(cell)
    for i, crop in enumerate(["arroz", "soja", "melancia", "capim"]):
        cell = f"{2 + i},9"
        objs.append(stage(crop, 4, cell))
        tilled.append(cell)
    subprocess.run([sys.executable, str(HERE / "scene.py"), str(OUT / "scene.png"), *objs,
                    "--tilled", ";".join(tilled), "--size", "11", "--zoom", "2", "--player", "5,3"], check=True)


def main():
    what = sys.argv[1:] or ["icons", "crops", "objects", "scene"]
    for w in what:
        globals()[w]()
        print(w, "ok")


if __name__ == "__main__":
    main()
