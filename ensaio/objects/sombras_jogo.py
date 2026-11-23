"""Sombra B (sombras.py) para os sprites que o jogo usa, plugada nas cenas.

Uso: python sombras_jogo.py <repo_do_jogo> [--tech B|D]

--tech B (padrão): sombra procedural, PNG de cor única, alfa no nó (modulate).
--tech D: usa out/sombras/<nome>_sombraD.png (difusão + gradiente, `sombras.py dfinal`);
          o alfa já está no PNG, então modulate alfa 1.0. Grava <nome>_sombraD.png no jogo.

Para cada sprite: calcula a sombra projetada (luz de cima-esquerda), grava em
<repo>/old_assets/sombras/<nome>_sombra.png e acrescenta à cena um Sprite2D
"Sombra" com a mesma posição/offset do sprite do objeto, deslocado pelo
quadro da sombra, z_index -1 (acima do chão, abaixo dos objetos) e alfa 0.38.
Rodar de novo substitui o nó "Sombra" anterior.
"""
import re
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))
import sombras  # noqa: E402

# cena, nó do sprite, png (relativo ao repo), tipo, anchor (None = pé do tronco),
# y do region_rect (house usa região)
ALVOS = [
    ("scenes/natureza/arvore_5.tscn", "Sprite2D", "old_assets/Green trees/arvore_baru.png", "tree", None, 0),
    ("scenes/natureza/arvore_grande.tscn", "Sprite2D", "old_assets/Green trees/arvore_baru.png", "tree", None, 0),
    ("scenes/natureza/arvore_6.tscn", "Sprite2D", "old_assets/Green trees/arvore_pequi.png", "tree", None, 0),
    ("scenes/natureza/arvore_seca_caida.tscn", "Sprite2D", "old_assets/Green trees/arvore_seca_caida.png", "box", None, 0),
    ("scenes/mundo/jogo.tscn", "Structures/House/Sprite2D", "old_assets/house.png", "box", (66, 104), 8.5),
]


def trunk_base(im):
    """Pé do tronco: centro dos pixels opacos nas 3 últimas linhas."""
    a = np.asarray(im)[..., 3] > 0
    ys = np.nonzero(a.any(1))[0]
    y1 = ys.max()
    xs = np.nonzero(a[y1 - 2: y1 + 1].any(0))[0]
    return int(round(xs.mean())), int(y1)


def shadow_for(png, kind, anc):
    im = Image.open(png).convert("RGBA")
    anc = anc or trunk_base(im)
    sombras.OBJECTS["_tmp"] = (png, anc, kind)
    m, c, _ = sombras.shadow_layers("_tmp")
    sh = sombras.to_png(m, c)
    bb = sh.getbbox()
    return sh.crop(bb), (bb[0], bb[1])  # canto do quadro da sombra em coordenadas da imagem


D_NAME = {"arvore_baru": "arvore_baru", "arvore_pequi": "arvore_pequi",
          "arvore_seca_caida": "arvore_seca_caida", "house": "house"}  # stem do png -> nome em out/sombras


def shadow_d(png):
    """Sombra D pronta: PNG com alfa + canto do quadro em coordenadas da imagem do objeto."""
    import json
    name = D_NAME[Path(png).stem]
    p = sombras.OUT / f"{name}_sombraD.png"
    meta = json.loads(p.with_suffix(".json").read_text())
    ax, ay = meta["obj_anchor"]
    return Image.open(p).convert("RGBA"), (ax + meta["offset"][0], ay + meta["offset"][1])


def node_block(s, path):
    name = path.rsplit("/", 1)[-1]
    par = path.rsplit("/", 1)[0] if "/" in path else None
    pat = f'[node name="{name}"' + (f' type="Sprite2D" parent="{par}"' if par else "")
    i = s.index(pat)
    j = s.find("\n[node", i + 10)
    return i, (len(s) if j < 0 else j)


def patch(scene, node, res_png, origin, region_y, suffix="_sombra", alpha=None):
    s = scene.read_text()
    # tira Sombra anterior
    s = re.sub(r'\n\[node name="Sombra" type="Sprite2D" parent="[^"]*"\][^\[]*', "\n", s)
    i, j = node_block(s, node)
    blk = s[i:j]
    head = blk.split("\n", 1)[0]
    parent = re.search(r'parent="([^"]*)"', head)
    par = parent.group(1) if parent else None
    name = node.rsplit("/", 1)[-1]
    sh_parent = name if par in (None, ".") else f"{par}/{name}"
    centered = "centered = false" not in blk
    off = re.search(r"offset = Vector2\(([-\d.]+), ([-\d.]+)\)", blk)
    ox, oy = (float(off.group(1)), float(off.group(2))) if off else (0.0, 0.0)
    tex = Image.open(scene.parents[2] / res_png if False else REPO / res_png)
    w, h = tex.size
    if centered:
        ox, oy = ox - w / 2, oy - h / 2
    # Sombra é filha do nó do sprite: mesma origem; quadro da imagem começa em (ox, oy - region_y)
    sx, sy = ox + origin[0], oy + origin[1] - region_y
    alpha = sombras.ALPHA if alpha is None else alpha
    ext_id = "sombra_" + Path(res_png).stem + suffix
    shadow_res = f"res://old_assets/sombras/{Path(res_png).stem}{suffix}.png"
    ext = f'[ext_resource type="Texture2D" path="{shadow_res}" id="{ext_id}"]\n'
    if f'id="{ext_id}"' not in s:
        k = s.index("\n", s.rindex("[ext_resource")) + 1
        s = s[:k] + ext + s[k:]
        i, j = node_block(s, node)
    nodetxt = (f'\n[node name="Sombra" type="Sprite2D" parent="{sh_parent}"]\n'
               f"z_index = -1\nmodulate = Color(1, 1, 1, {alpha:.3g})\ntexture_filter = 1\n"
               f'texture = ExtResource("{ext_id}")\ncentered = false\noffset = Vector2({sx:g}, {sy:g})\n')
    s = s[:j] + nodetxt.rstrip("\n") + "\n" + s[j:]
    scene.write_text(s)


def main():
    global REPO
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("repo")
    ap.add_argument("--tech", choices=("B", "D"), default="B")
    args = ap.parse_args()
    REPO = Path(args.repo).resolve()
    out = REPO / "old_assets/sombras"
    out.mkdir(parents=True, exist_ok=True)
    suffix, alpha = ("_sombraD", 1.0) if args.tech == "D" else ("_sombra", None)
    done = {}
    for scene, node, png, kind, anc, ry in ALVOS:
        if png not in done:
            sh, origin = shadow_d(REPO / png) if args.tech == "D" else shadow_for(REPO / png, kind, anc)
            sh.save(out / f"{Path(png).stem}{suffix}.png")
            done[png] = origin
        patch(REPO / scene, node, png, done[png], ry, suffix, alpha)
        print(scene, node, done[png])


if __name__ == "__main__":
    main()
