#!/usr/bin/env python3
"""Sombras projetadas dos objetos (estudo). Luz fixa: vem de cima-esquerda da tela;
a sombra cai para baixo-direita, ao longo do eixo +x do grid iso (vetor de tela 2:1).

Uso: sombras.py proc            sombras procedurais (B projeção, C proxy) em out/sombras/
     sombras.py bases           bases 8x + máscaras para o inpaint (A) em specs/{bases,masks}/sombra_*
     sombras.py extract         sombras do inpaint (A), lidas de runs/ (ver A_RUNS)
     sombras.py preview         out/sombras/comparacao.png (3x sobre a grama do kit)
     sombras.py overlap         out/sombras/sobreposicao.png (alfa por sprite x camada única x embutida)
     sombras.py phases          out/sombras/fases.png (fases das árvores com a sombra de cada fase)
     sombras.py all             proc + extract + preview + overlap + phases
     sombras.py dbases [w] [obj] bases D (objeto sobre branco, máscara = sombra B de sol alto; w = máscara larga)
     sombras.py dsheet          tmp/sombras/candidatos.png (todas as seeds D sobre a grama)
     sombras.py dfinal          <obj>_sombraD.png/.json das seeds em D_PICK + out/sombras/comparacao_D.png
Sol alto (LEN 0.18), sombra preta com alfa máx. 100/255, como a do jogador.
Gerações do inpaint: specs/o39.json (D, sol alto, 2 seeds por objeto), specs/o36.json (ipê A1/A2), specs/o37.json (A1 dos outros), specs/o38.json (A3,
objeto sobre branco; `sombras.py bases A3` refaz só essas bases), ids das bases em
specs/bases/sombra_ids.json (aig import das specs/bases/sombra_*.png).

Cada sombra sai como PNG de cor única opaca (1 ou 2 tons) + .json com:
  anchor: pixel da sombra que vai no centro da célula (mesma regra do objeto);
  offset: canto sup. esq. da sombra menos o anchor do objeto (em px);
  alpha:  opacidade sugerida (aplicada por um CanvasGroup no Godot, não no PNG).
"""
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage

import pipeline as P

HERE = Path(__file__).resolve().parent
ENSAIO = HERE.parent
OBJ = HERE / "out" / "objects"
OUT = HERE / "out" / "sombras"
RUNS = ENSAIO / "runs"
KIT = ENSAIO / "out" / "kit-g" / "terrain_atlas.png"
OLD = Path("/home/chips/git/games/Veredas-Farm/old_assets")

# luz: de cima-esquerda. Sombra: deslocamento na tela por px de altura acima do chão.
DIR = np.array([2.0, 1.0]) / np.hypot(2, 1)  # eixo +x do grid iso (baixo-direita)
# Sol perto do meio-dia, como a sombra do jogador (elipse preta alfa 100/255 sob os pés,
# old_assets/Player/farmer_Player.png): sombra curta, quase embaixo da copa.
# (o estudo da 1a rodada usou LEN 0.5, cor (22,34,46) e alfa 0.38: sombra longa para baixo-direita)
LEN = 0.18  # comprimento da sombra por px de altura
SHRINK = 0.85  # copa/volume: a sombra usa 85% da largura e da profundidade
SHADE = (0, 0, 0)  # cor da sombra = a do jogador
CORE = (0, 0, 0)  # 2o tom: contato no pé (com uma cor só, o 2o tom some no CanvasGroup)
ALPHA = 100 / 255  # opacidade da camada de sombra = a do jogador

SPARSE = ("seco",)  # fases sem copa
PHASES = {  # árvore: fases (a 1a é a base)
    "ipe_amarelo": ["florido", "verde", "brotando", "seco"],
    "pequi": ["maduro", "florida", "fruto_verde", "folhada"],
    "cagaita": ["maduro", "florida", "fruto_verde", "folhada"],
}
# objeto de teste: (png, anchor ou None = .json ao lado, tipo)
OBJECTS = {
    "arvore_ipe_amarelo": (OBJ / "arvore_ipe_amarelo_florido.png", None, "tree"),
    "arvore_pequi": (OBJ / "arvore_pequi_maduro.png", None, "tree"),
    "arvore_cagaita": (OBJ / "arvore_cagaita_maduro.png", None, "tree"),
    "cupinzeiro_alto": (OBJ / "cupinzeiro_alto.png", None, "blob"),
    "cupinzeiro_baixo": (OBJ / "cupinzeiro_baixo.png", None, "blob"),
    "pilao": (OBJ / "pilao.png", None, "blob"),
    "carro_de_boi": (OBJ / "carro_de_boi.png", None, "box"),
    "moinho": (OBJ / "moinho.png", None, "box"),
    "casa": (OLD / "house.png", (66, 104), "box"),  # anchor medido à mão (centro da base)
    # sprites do jogo (D); pequi e baru do jogo = arvore_pequi_maduro / arvore_baru_folhado do ensaio
    "arvore_baru": (OLD / "Green trees" / "arvore_baru.png", None, "tree"),
    "arvore_seca_caida": (OLD / "Green trees" / "arvore_seca_caida.png", None, "box"),
    "house": (OLD / "house.png", (66, 104), "box"),
    "arvore_ipe_roxo": (OBJ / "arvore_ipe_roxo_florido.png", None, "tree"),
}


# ---------------------------------------------------------------- base

def load_obj(name, phase=None):
    path, anc, kind = OBJECTS[name]
    if phase:
        path = OBJ / f"{name}_{phase}.png"
    im = Image.open(path).convert("RGBA")
    if anc is None and path.with_suffix(".json").exists():
        anc = json.loads(path.with_suffix(".json").read_text())["anchor"]
    if anc is None:  # sprite do jogo sem .json: pé do tronco (como sombras_jogo.trunk_base)
        a = np.asarray(im)[..., 3] > 0
        y1 = np.nonzero(a.any(1))[0].max()
        anc = (int(round(np.nonzero(a[y1 - 2: y1 + 1].any(0))[0].mean())), int(y1))
    return im, tuple(anc), kind


def alpha_of(im):
    return np.asarray(im)[..., 3] > 0


def ground_line(a, anc):
    """y do chão de cada coluna. Base larga (carreta, casa): a última linha opaca da
    coluna, se estiver dentro do losango do pé; senão (copa que sobra para o lado) o
    y do anchor, como num cartaz em pé sobre o ponto de pé."""
    H, W = a.shape
    ax, ay = anc
    g = np.full(W, ay, float)
    for x in range(W):
        ys = np.nonzero(a[:, x])[0]
        if len(ys) and ys.max() >= ay - abs(x - ax) / 2 - 3:
            g[x] = max(ys.max(), ay - abs(x - ax) / 2) if ys.max() < ay else ys.max()
    return g


def project(a, anc, kind, ss=2, revolve=None):
    """(B) Silhueta projetada no chão: cada pixel a altura h do chão da sua coluna
    vai para (x, chão) + h * LEN * DIR. Supersample ss x ss para não abrir furos.
    revolve (árvore, cupinzeiro, pilão): o sprite é tratado como sólido de revolução,
    cada linha tem profundidade = sua largura; a profundidade no chão vira +-d/2 em y
    (losango 2:1). Sem isso a copa vira uma fita fina. Carreta/casa ('box'): a base
    larga já vem da linha de chão por coluna.
    Devolve máscara no quadro do sprite (origem igual) com margem à direita/embaixo."""
    H, W = a.shape
    revolve = kind != "box" if revolve is None else revolve
    g = ground_line(a, anc) if kind == "box" else np.full(W, anc[1], float)
    pad_x, pad_y = int(H * LEN * DIR[0]) + 4, int(H * LEN * DIR[1]) + W // 4 + 4
    out = np.zeros((H + pad_y + 4, W + pad_x + 4), bool)
    ys, xs = np.nonzero(a)
    depth = np.zeros(len(ys))
    rowc = xs + 0.5  # centro do trecho da linha (para encolher a copa em torno dele)
    if revolve:  # meia profundidade de cada pixel: círculo da linha (largura do trecho contínuo)
        for y in np.unique(ys):
            row = a[y]
            lab, n = ndimage.label(row)
            for i in range(1, n + 1):
                seg = np.nonzero(lab == i)[0]
                cx, r = (seg[0] + seg[-1] + 1) / 2, (seg[-1] - seg[0] + 1) / 2
                sel = (ys == y) & (xs >= seg[0]) & (xs <= seg[-1])
                depth[sel] = np.sqrt(np.clip(r ** 2 - (xs[sel] + 0.5 - cx) ** 2, 0, None)) * SHRINK
                rowc[sel] = cx
    for oy in (np.arange(ss) + 0.5) / ss:
        for ox in (np.arange(ss) + 0.5) / ss:
            px, py = xs + ox, ys + oy
            gy = g[xs] + 1
            h = np.clip(gy - py, 0, None)
            sx = px + h * LEN * DIR[0]
            if revolve:  # copa um pouco menor que a real (sombra de copa rala, leitura melhor)
                sx = np.where(h > 4, rowc + (px - rowc) * SHRINK + h * LEN * DIR[0], sx)
            sy = np.where(py >= gy, py, gy + h * LEN * DIR[1])  # abaixo do chão (terra do sprite) fica
            for t in np.linspace(-1, 1, 9):
                yy = sy + t * depth / 2
                out[np.clip(yy.astype(int), 0, out.shape[0] - 1), np.clip(sx.astype(int), 0, out.shape[1] - 1)] = True
    out = ndimage.binary_closing(out, iterations=1)
    return out, anc


def tidy(m, fill=True, open_=True):
    """Pixel art: fecha vãos de 1 px, preenche buracos, tira pixel solto."""
    m = ndimage.binary_closing(m, iterations=2) | m
    if fill:
        m = ndimage.binary_fill_holes(m)
    if open_:
        o = ndimage.binary_opening(m, structure=np.ones((2, 2)))
        lab, n = ndimage.label(o)
        if n:
            sizes = ndimage.sum(o, lab, range(1, n + 1))
            m = np.isin(lab, [i + 1 for i, s in enumerate(sizes) if s >= 6])
    return m


def ellipse(shape, cx, cy, rx, ry):
    yy, xx = np.mgrid[: shape[0], : shape[1]]
    return ((xx + 0.5 - cx) / rx) ** 2 + ((yy + 0.5 - cy) / ry) ** 2 <= 1


def contact(shape, a, anc, kind):
    """Sombra de contato (oclusão no pé): elipse 2:1 da largura da base."""
    ax, ay = anc
    H, W = a.shape
    if kind == "tree":  # largura do tronco nas 6 linhas de baixo
        xs = np.nonzero(a[max(ay - 6, 0): ay + 1].any(0))[0]
        w = max(6, (xs.max() - xs.min() + 1) if len(xs) else 6)
    else:
        xs = np.nonzero(a[max(ay - 3, 0): min(ay + 3, H)].any(0))[0]
        w = max(6, (xs.max() - xs.min() + 1) * 0.8 if len(xs) else 6)
    return ellipse(shape, ax + 1.5, ay + 0.5, w / 2 + 1, w / 4 + 1)


def proxy(a, anc, kind):
    """(C) Proxy 3D simples: copa = elipse do tamanho da copa, projetada do centro dela;
    tronco = faixa do pé até a copa. Objeto baixo (blob) = elipse da base esticada na
    direção da luz. Mesma forma para todas as fases se a copa for a mesma."""
    H, W = a.shape
    ax, ay = anc
    pad_x, pad_y = int(H * LEN * DIR[0]) + 4, int(H * LEN * DIR[1]) + W // 4 + 4
    shape = (H + pad_y + 4, W + pad_x + 4)
    ys, xs = np.nonzero(a)
    m = np.zeros(shape, bool)
    if kind == "tree":
        rows = a.sum(1)
        top = ys.min()
        wide = np.nonzero(rows > 0.35 * rows.max())[0]
        cy0, cy1 = top, wide.max()  # copa: do topo até a última linha larga
        cx = xs[ys <= cy1].mean()
        cxs = xs[(ys >= cy0) & (ys <= cy1)]
        rx = (np.percentile(cxs, 97) - np.percentile(cxs, 3)) / 2
        hc = ay - (cy0 + cy1) / 2
        px, py = cx + hc * LEN * DIR[0], ay + hc * LEN * DIR[1]
        # esfera -> elipse no chão, achatada 2:1 pelo iso e um pouco alongada na direção da luz
        m |= ellipse(shape, px + 0.5, py, rx * 0.9, rx * 0.9 / 2 * 1.15)
        # tronco: faixa do pé até a base da copa projetada
        tw = 3
        hb = ay - cy1
        for t in np.linspace(0, 1, 60):
            h = t * (hb + (cy1 - cy0) / 2)
            x, y = ax + h * LEN * DIR[0], ay + h * LEN * DIR[1]
            m[int(y) - 1: int(y) + 1, int(x) - tw // 2: int(x) + tw - tw // 2] = True
    else:
        h = ay - ys.min()
        bw = (xs.max() - xs.min() + 1) * 0.5
        L = h * LEN
        n = 24
        for t in np.linspace(0, 1, n):  # base varrida ao longo da sombra, afinando
            r = bw * (1 - 0.45 * t)
            m |= ellipse(shape, ax + 0.5 + t * L * DIR[0], ay + 0.5 + t * L * DIR[1], r, r / 2)
    return m


def shadow_layers(name, phase=None, tech="B"):
    """Máscaras (forma, contato) no quadro da sombra, e o anchor nesse quadro."""
    im, anc, kind = load_obj(name, phase)
    a = alpha_of(im)
    if tech == "B":
        if phase in SPARSE:  # galhos sem folha: sombra de galhos finos, sem volume nem preenchimento
            m, _ = project(a, anc, kind, revolve=False)
            yy, xx = np.mgrid[: m.shape[0], : m.shape[1]]
            m &= (yy + xx) % 2 == 0  # xadrez: meia sombra, galho deixa passar luz
        else:
            m, _ = project(a, anc, kind)
            m = tidy(m)
    else:
        m = proxy(a, anc, kind)
    c = contact(m.shape, a, anc, kind)
    return m | c, c, anc


def to_png(m, core=None, two_tone=True):
    rgba = np.zeros(m.shape + (4,), np.uint8)
    rgba[m] = SHADE + (255,)
    if two_tone and core is not None:
        rgba[core & m] = CORE + (255,)
    return Image.fromarray(rgba)


def crop_meta(img, anc, name_anchor):
    """Recorta no bbox e calcula anchor/offset. O quadro da sombra começa em (0,0)
    do sprite do objeto (mesma origem), então offset = bbox - anchor do objeto."""
    bb = img.getbbox()
    sh = img.crop(bb)
    ax, ay = name_anchor
    return sh, {"anchor": [ax - bb[0], ay - bb[1]], "offset": [bb[0] - ax, bb[1] - ay], "alpha": ALPHA,
                "light": "cima-esquerda", "dir": [2, 1], "len": LEN}


def save(sh, meta, fn):
    OUT.mkdir(parents=True, exist_ok=True)
    sh.save(OUT / f"{fn}.png")
    (OUT / f"{fn}.json").write_text(json.dumps(meta))


def phase_frame(name):
    """Fases da árvore: um quadro comum (união dos bboxes) para todas as fases ->
    mesmo anchor e offset; só a textura da sombra troca com a fase."""
    tree = name.removeprefix("arvore_")
    return [(ph, f"{name}_{ph}") for ph in PHASES.get(tree, [None])]


# ---------------------------------------------------------------- auto-sombra

def palette_darker(colors):
    """Para cada cor do sprite, a cor do próprio sprite que mais se parece com ela
    escurecida (~70%) e é mais escura. Sem cores novas."""
    cols = np.unique(colors.reshape(-1, 3), axis=0).astype(float)
    lum = cols @ [0.3, 0.59, 0.11]
    out = {}
    for c, l in zip(cols, lum):
        target = c * 0.7
        cand = cols[lum < l - 6]
        if not len(cand):
            out[tuple(c.astype(int))] = c
            continue
        d = ((cand - target) ** 2).sum(1)
        out[tuple(c.astype(int))] = cand[d.argmin()]
    return out


def self_shade(im, r=3):
    """Sombra própria: pixels do lado oposto à luz (cujo vizinho a r px para
    baixo-direita é transparente) descem um degrau na rampa do próprio sprite."""
    s = np.asarray(im).copy()
    a = s[..., 3] > 0
    dx, dy = int(round(r * DIR[0])), int(round(r * DIR[1]))
    shifted = np.zeros_like(a)
    shifted[: a.shape[0] - dy, : a.shape[1] - dx] = a[dy:, dx:]
    edge = a & ~shifted
    edge &= ~ndimage.binary_erosion(a, iterations=1, border_value=0) | edge  # inclui contorno
    # não escurece a base (o pé já encosta na sombra)
    ys = np.nonzero(a.any(1))[0]
    edge[ys.max() - 1:] = False
    dk = palette_darker(s[a][:, :3])
    for y, x in zip(*np.nonzero(edge)):
        s[y, x, :3] = dk[tuple(int(v) for v in s[y, x, :3])]
    return Image.fromarray(s)


def bake(name, tech="B"):
    """Alternativa 'embutida': sombra (alfa único) + objeto num PNG só. A tela cresce
    para a direita/embaixo e o anchor muda; gravado em <nome>_embutida.png/.json."""
    kind = kind_of(name)
    im, anc, _ = load_obj(name, phase_frame(name)[0][0] if kind == "tree" else None)
    fn = phase_frame(name)[0][1] if kind == "tree" else name
    sh, meta = shadow_of(fn, tech)
    ox, oy = meta["offset"]
    x0, y0 = min(0, anc[0] + ox), min(0, anc[1] + oy)
    W = max(im.width, anc[0] + ox + sh.width) - x0
    H = max(im.height, anc[1] + oy + sh.height) - y0
    c = Image.new("RGBA", (W, H))
    s = np.asarray(sh).copy()
    s[..., 3] = (s[..., 3] > 0) * int(ALPHA * 255)
    c.alpha_composite(Image.fromarray(s), (anc[0] + ox - x0, anc[1] + oy - y0))
    c.alpha_composite(im, (-x0, -y0))
    c.save(OUT / f"{name}_embutida.png")
    (OUT / f"{name}_embutida.json").write_text(json.dumps({"anchor": [anc[0] - x0, anc[1] - y0]}))


# ---------------------------------------------------------------- comandos

def cmd_proc():
    for name in OBJECTS:
        for tech in ("B", "C") if kind_of(name) != "box" else ("B",):
            frames = phase_frame(name) if OBJECTS[name][2] == "tree" else [(None, name)]
            layers = [(fn, shadow_layers(name, ph, tech)) for ph, fn in frames]
            # quadro comum entre fases
            Hm = max(m.shape[0] for _, (m, _, _) in layers)
            Wm = max(m.shape[1] for _, (m, _, _) in layers)
            imgs = []
            for fn, (m, c, anc) in layers:
                big = np.zeros((Hm, Wm), bool); bc = big.copy()
                big[: m.shape[0], : m.shape[1]] = m
                bc[: c.shape[0], : c.shape[1]] = c
                imgs.append((fn, to_png(big, bc), anc))
            bbs = [im.getbbox() for _, im, _ in imgs]
            bb = (min(b[0] for b in bbs), min(b[1] for b in bbs), max(b[2] for b in bbs), max(b[3] for b in bbs))
            for fn, im, anc in imgs:
                ax, ay = anc
                meta = {"anchor": [ax - bb[0], ay - bb[1]], "offset": [bb[0] - ax, bb[1] - ay], "alpha": ALPHA,
                        "light": "cima-esquerda", "dir": [2, 1], "len": LEN, "tech": tech}
                save(im.crop(bb), meta, f"{fn}_sombra{tech}")
        im, anc, kind = load_obj(name)
        self_shade(im).save(OUT / f"{name}_autosombra.png")
        bake(name)
    print("ok", OUT)


def grass(w, h, seed=3):
    """Chão de grama do kit (tiles 'grass' puros) em losangos 32x16, cobrindo w x h."""
    atlas = Image.open(KIT).convert("RGBA")
    d = json.loads(KIT.with_suffix(".json").read_text())
    tiles = [atlas.crop((x * 32, y * 32, x * 32 + 32, y * 32 + 32)) for x, y in
             (t["atlas"] for t in d["tiles"] if t["kind"] == "pure" and t["terrain"] == "grass")]
    rng = np.random.default_rng(seed)
    c = Image.new("RGBA", (w + 64, h + 64), (0, 0, 0, 255))
    n = (w + h) // 16 + 4
    for s in range(-n, 2 * n):  # de trás para frente
        for i in range(-n, n + 1):
            j = s - i
            x, y = (i - j) * 16 + w // 2, (i + j) * 8 - 8
            if -32 <= x <= w + 32 and -32 <= y <= h + 32:
                c.alpha_composite(tiles[rng.integers(len(tiles))], (x + 32, y + 32))
    return c.crop((32, 32, 32 + w, 32 + h))


def shadow_of(fn, tech):
    p = OUT / f"{fn}_sombra{tech}.png"
    if not p.exists():
        return None
    return Image.open(p).convert("RGBA"), json.loads(p.with_suffix(".json").read_text())


def compose(cell, obj, anc, pos, sh=None, alpha=ALPHA):
    """Cena de uma célula: grama, camada de sombra com alfa único (como um
    CanvasGroup com modulate), objeto em pos."""
    out = cell.copy()
    if sh is not None:
        m = place_shadow(cell.size, sh, anc, pos)
        la = np.zeros(m.shape + (4,), np.uint8)
        im, meta = sh
        layer = Image.new("RGBA", cell.size)
        layer.alpha_composite(im, (pos[0] + anc[0] + meta["offset"][0], pos[1] + anc[1] + meta["offset"][1]))
        la = np.asarray(layer).copy()
        la[..., 3] = (la[..., 3] > 0) * int(alpha * 255)
        out.alpha_composite(Image.fromarray(la))
    out.alpha_composite(obj, pos)
    return out


def ellipse_old(obj, anc):
    """O que o mapa usa hoje (remap.shadow_sprite): elipse sem forma sob o pé."""
    sys.path.insert(0, str(ENSAIO / "tools"))
    from remap import shadow_sprite
    w = obj.getbbox()[2] - obj.getbbox()[0]
    e = shadow_sprite(min(w, 40))
    return e, {"offset": [-e.width // 2, -e.height // 2]}


# ---------------------------------------------------------------- (A) inpaint

INPAINT = ["arvore_ipe_amarelo", "arvore_pequi", "cupinzeiro_alto", "carro_de_boi", "moinho", "casa"]


def factor(size):
    """Ampliação da cena 1x para a base: a maior de 16/8/4 que cabe em 1280 px."""
    return next(s for s in (16, 8, 4) if max(size) * s <= 1280)
A_RUNS = {  # (objeto, modo): glob da geração em runs/
    **{(n, "A3"): f"o38/sombra-{n}-A3-*.png" for n in ("arvore_ipe_amarelo", "arvore_pequi", "carro_de_boi", "moinho", "casa")},
    ("arvore_ipe_amarelo", "A1"): "o36/sombra-arvore_ipe_amarelo-A1-*.png",
    ("arvore_ipe_amarelo", "A2"): "o36/sombra-arvore_ipe_amarelo-A2-*.png",
    **{(n, "A1"): f"o37/sombra-{n}-A1-*.png" for n in ("arvore_pequi", "carro_de_boi", "moinho", "cupinzeiro_alto", "casa")},
}
A_PROMPT = ("pixel art, isometric farming game ground tile, bright green grass with small grass tufts, "
            "the soft flat dark shadow of {what} cast on the grass, shadow falling toward the lower right, "
            "simple shadow shape with clean pixel edges, no objects, top-down view")
A3_PROMPT = ("pixel art, plain flat white background, the flat grey shadow of {what} cast on the white ground, "
             "shadow falling toward the lower right, simple solid shadow shape with clean hard pixel edges, "
             "no grass, no other objects")
WHAT = {"arvore_ipe_amarelo": "a round tree crown and trunk", "arvore_pequi": "a round tree crown and trunk",
        "cupinzeiro_alto": "a small termite mound", "carro_de_boi": "a wooden ox cart",
        "moinho": "a small wooden water mill hut", "casa": "a small farm house",
        "arvore_baru": "a round leafy tree crown and trunk", "arvore_cagaita": "a round leafy tree crown and trunk",
        "arvore_ipe_roxo": "a round tree crown and trunk", "arvore_seca_caida": "a fallen dead tree trunk with bare branches",
        "house": "a small farm house"}


def layout(name):
    """Célula 1x da cena (grama + objeto), igual na prévia e nas bases do inpaint.
    Devolve grama, objeto, anchor, posição (ox, oy) do objeto na célula."""
    obj, anc, kind = load_obj(name, phase_frame(name)[0][0] if kind_of(name) == "tree" else None)
    below = int(obj.height * LEN * DIR[1]) + obj.width // 4 + 6  # sombra abaixo do pé
    W = 8 + obj.width + int(obj.height * LEN * DIR[0]) + 12
    H = 6 + max(anc[1] + below, obj.height + 4)
    W, H = -(-W // 16) * 16, -(-H // 16) * 16  # x4/x8/x16 = múltiplo de 64
    return grass(W, H), obj, anc, (8, 6)


def kind_of(name):
    return OBJECTS[name][2]


def place_shadow(size, sh, anc, pos):
    im, meta = sh
    layer = Image.new("RGBA", size)
    layer.alpha_composite(im, (pos[0] + anc[0] + meta["offset"][0], pos[1] + anc[1] + meta["offset"][1]))
    return np.asarray(layer)[..., 3] > 0


def cmd_bases(modes=("A1", "A2", "A3")):
    """Para cada objeto: base A1 (grama + objeto), A2 (grama + objeto + sombra B
    escurecida, guia para denoise < 1) e A3 (objeto sobre branco liso; a sombra sai por
    transparência), máscaras = região da sombra B dilatada, sem o objeto.
    `sombras.py bases A3` grava só as do A3 (as A1/A2 do o36/o37 usaram a B antiga)."""
    bases, masks = HERE / "specs" / "bases", HERE / "specs" / "masks"
    spec = []
    for name in INPAINT:
        g, obj, anc, pos = layout(name)
        S = factor(g.size)
        fn = phase_frame(name)[0][1] if kind_of(name) == "tree" else name
        sh = shadow_of(fn, "B")
        m = place_shadow(g.size, sh, anc, pos)
        ob = Image.new("RGBA", g.size)
        ob.alpha_composite(obj, pos)
        oa = np.asarray(ob)[..., 3] > 0
        a1 = g.copy(); a1.alpha_composite(ob)
        lay = np.zeros(g.size[::-1] + (4,), np.uint8); lay[m] = SHADE + (int(ALPHA * 255),)
        a2 = g.copy(); a2.alpha_composite(Image.fromarray(lay)); a2.alpha_composite(ob)
        a3 = Image.new("RGBA", g.size, (255, 255, 255, 255)); a3.alpha_composite(ob)
        for mode, im, grow in (("A1", a1, 2), ("A2", a2, 3), ("A3", a3, 4)):
            if mode not in modes:
                continue
            mk = ndimage.binary_dilation(m, iterations=grow) & ~oa
            big = im.convert("RGB").resize((g.width * S, g.height * S), Image.NEAREST)
            big.save(bases / f"sombra_{name}_{mode}_{S}x.png")
            Image.fromarray((mk * 255).astype(np.uint8)).resize(big.size, Image.NEAREST).save(
                masks / f"sombra_{name}_{mode}.png")
        print(name, g.size, "->", big.size)
    print("bases em", bases)


def base_of(name, mode):
    """Base do inpaint e o tamanho 1x da célula (o fator está no nome do arquivo)."""
    bp = next((HERE / "specs" / "bases").glob(f"sombra_{name}_{mode}_*x.png"))
    S = int(bp.stem.rsplit("_", 1)[1][:-1])
    w, h = Image.open(bp).size
    return bp, (w // S, h // S)


def a_result(name, mode):
    """Sombra extraída da geração A: pixels da região da máscara cuja luminância
    caiu >= 12% em relação à grama original (reduzida pelo fator, box)."""
    from phases import find
    src = A_RUNS.get((name, mode))
    p = find(src) if src else None
    if p is None:
        return None
    g, obj, anc, pos = layout(name)
    bp, size = base_of(name, mode)  # tamanho da célula de quando a base foi feita
    out = Image.open(p).convert("RGB")
    small = np.asarray(out.resize(size, Image.BOX)).astype(float)
    raw = np.asarray(out.resize(size, Image.NEAREST))
    base = np.asarray(Image.open(bp).convert("RGB").resize(size, Image.NEAREST)).astype(float)
    mk = np.asarray(Image.open(HERE / "specs" / "masks" / f"sombra_{name}_{mode}.png").resize(size, Image.NEAREST)) > 127
    lum = lambda c: c @ [0.3, 0.59, 0.11]
    ratio = lum(small) / np.maximum(lum(base), 1)
    m = mk & (ratio < 0.88)
    core = mk & (ratio < 0.62)
    m = tidy(m)
    return m, core & m, raw, mk, (g, obj, anc, pos)


A3_LEVELS = (0.10, 0.22, 0.36)  # cortes do escurecimento (1 - lum/255) -> 3 níveis de alfa
A3_ALPHA = (0.22, 0.36, 0.50)  # alfa de cada nível (o mais claro é a penumbra)


def a3_result(name):
    """A3: sombra sobre branco -> alfa = 1 - lum/255 na região da máscara (reduzida por box),
    quantizado em 3 níveis; cor fixa SHADE. PNG RGBA só da sombra, no quadro da célula."""
    from phases import find
    src = A_RUNS.get((name, "A3"))
    p = find(src) if src else None
    if p is None:
        return None
    g, obj, anc, pos = layout(name)
    _, size = base_of(name, "A3")
    out = np.asarray(Image.open(p).convert("RGB").resize(size, Image.BOX)).astype(float)
    mk = np.asarray(Image.open(HERE / "specs" / "masks" / f"sombra_{name}_A3.png").resize(size, Image.NEAREST)) > 127
    dark = 1 - (out @ [0.3, 0.59, 0.11]) / 255
    dark[(out.max(-1) - out.min(-1)) > 40] = 0  # cor saturada = objeto que o modelo inventou, não sombra
    lvl = np.zeros(dark.shape, int)
    for k, t in enumerate(A3_LEVELS):
        lvl[mk & (dark >= t)] = k + 1
    lab, n = ndimage.label(lvl > 0)  # sem mancha solta (< 6 px); os furos (luz entre as folhas) ficam
    sizes = ndimage.sum(lvl > 0, lab, range(1, n + 1))
    keep = np.isin(lab, [i + 1 for i, sz in enumerate(sizes) if sz >= 6])
    lvl[~keep] = 0
    # contato no pé (o modelo deixa um vão entre o tronco e a sombra): elipse da B, nível 2
    a_obj = alpha_of(obj)
    c = d_contact((a_obj.shape[0] + 8, a_obj.shape[1] + 8), a_obj, anc, kind_of(name))
    cc = np.zeros(lvl.shape, bool)
    h, w = min(c.shape[0], lvl.shape[0] - pos[1]), min(c.shape[1], lvl.shape[1] - pos[0])
    cc[pos[1]:pos[1] + h, pos[0]:pos[0] + w] = c[:h, :w]
    lvl[cc] = np.maximum(lvl[cc], 2)
    rgba = np.zeros(dark.shape + (4,), np.uint8)
    for k, a in enumerate(A3_ALPHA):
        rgba[lvl == k + 1] = SHADE + (int(a * 255),)
    return Image.fromarray(rgba), (g, obj, anc, pos)


def cmd_extract():
    for name in INPAINT:
        r = a3_result(name)
        if r is None:
            continue
        img, (g, obj, anc, pos) = r
        bb = img.getbbox()
        ax, ay = pos[0] + anc[0], pos[1] + anc[1]
        meta = {"anchor": [ax - bb[0], ay - bb[1]], "offset": [bb[0] - ax, bb[1] - ay], "alpha": None,
                "levels": A3_ALPHA, "light": "cima-esquerda", "dir": [2, 1], "tech": "A3", "src": A_RUNS[(name, "A3")],
                "nota": "alfa já no PNG (3 níveis); não aplicar o alfa do CanvasGroup por cima"}
        fn = phase_frame(name)[0][1] if kind_of(name) == "tree" else name
        save(img.crop(bb), meta, f"{fn}_sombraA3")
    for (name, mode) in A_RUNS:
        if mode == "A3":
            continue
        r = a_result(name, mode)
        if r is None:
            print("sem geração", name, mode)
            continue
        m, core, raw, mk, (g, obj, anc, pos) = r
        img = to_png(m, core)
        bb = img.getbbox()
        ax, ay = pos[0] + anc[0], pos[1] + anc[1]
        meta = {"anchor": [ax - bb[0], ay - bb[1]], "offset": [bb[0] - ax, bb[1] - ay], "alpha": ALPHA,
                "light": "cima-esquerda", "dir": [2, 1], "len": LEN, "tech": mode, "src": A_RUNS[(name, mode)]}
        fn = phase_frame(name)[0][1] if kind_of(name) == "tree" else name
        save(img.crop(bb), meta, f"{fn}_sombra{mode}")
        # bruto: os pixels da geração na região da máscara, sobre transparente (para a prévia)
        rgba = np.zeros(raw.shape[:2] + (4,), np.uint8)
        rgba[mk] = np.dstack([raw, np.full(raw.shape[:2], 255, np.uint8)])[mk]
        Image.fromarray(rgba).save(OUT / f"{fn}_sombra{mode}_bruto.png")
    print("ok")


COLS = [("hoje (elipse)", "old"), ("B projeção", "B"), ("B + autosombra", "Bs"), ("C proxy", "C"),
        ("A1 inpaint grama", "A1"), ("A2 guiado", "A2"), ("A3 inpaint branco", "A3")]


# ---------------------------------------------------------------- (D) difusão + gradiente

D_OBJECTS = ["arvore_baru", "arvore_pequi", "arvore_seca_caida", "house", "arvore_cagaita", "arvore_ipe_roxo",
             "arvore_ipe_amarelo", "carro_de_boi", "moinho", "cupinzeiro_alto"]
D_PROMPT = ("pixel art, plain flat white background, sun high overhead at noon, the soft medium grey shadow of {what} "
            "on the white ground directly beneath it, short shadow slightly toward the lower right, "
            "clearly visible solid shadow shape with clean hard pixel edges, no grass, no other objects")
D_GROW = {"": 3, "w": 7}  # dilatação da máscara (px 1x): normal e larga (se a sombra sair fraca)
D_RUNS = {}  # objeto: glob da seed escolhida (preenchido em D_PICK abaixo)
D_LEVELS = (24, 48, 72, 100)  # alfa (0-255) dos 4 níveis; 100 = sombra do jogador
D_CUT = 0.07  # escurecimento mínimo (1 - lum/255) para o pixel ser sombra
BAYER4 = np.array([[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]]) / 16


def d_bases(names=None, variant=""):
    """Bases D: objeto sobre branco, máscara = sombra B (sol alto) dilatada, sem o objeto.
    variant 'w': máscara larga para a 2a tentativa."""
    bases, masks = HERE / "specs" / "bases", HERE / "specs" / "masks"
    for name in names or D_OBJECTS:
        g, obj, anc, pos = layout(name)
        S = factor(g.size)
        m, c, _ = shadow_layers(name, phase_frame(name)[0][0] if kind_of(name) == "tree" else None, "B")
        mm = np.zeros(g.size[::-1], bool)
        h, w = min(m.shape[0], g.height - pos[1]), min(m.shape[1], g.width - pos[0])
        mm[pos[1]:pos[1] + h, pos[0]:pos[0] + w] = m[:h, :w]
        ob = Image.new("RGBA", g.size); ob.alpha_composite(obj, pos)
        oa = np.asarray(ob)[..., 3] > 0
        mk = ndimage.binary_dilation(mm, iterations=D_GROW[variant]) & ~oa
        im = Image.new("RGBA", g.size, (255, 255, 255, 255)); im.alpha_composite(ob)
        big = im.convert("RGB").resize((g.width * S, g.height * S), Image.NEAREST)
        big.save(bases / f"sombra_{name}_D{variant}_{S}x.png")
        Image.fromarray((mk * 255).astype(np.uint8)).resize(big.size, Image.NEAREST).save(masks / f"sombra_{name}_D{variant}.png")
        print(name, variant, g.size, "->", big.size)


D_W = (0.45, 0.25, 0.30)  # pesos: escurecimento da difusão, profundidade na forma, proximidade do pé
D_BIAS = 0.25              # desloca os níveis (+ = mais escuro)


def d_contact(shape, a, anc, kind):
    """Contato no pé. Árvore: elipse pequena da largura do tronco acima das raízes (máx. 14 px).
    Resto: faixa de 2 px sob o contorno de baixo do objeto, só nas colunas que tocam o chão
    (fundo a até 6 px da linha do anchor), para seguir a silhueta e não virar um oval."""
    ax, ay = anc
    if kind == "tree":
        xs = np.nonzero(a[max(ay - 12, 0): max(ay - 7, 1)].any(0))[0]
        w = int(np.clip((xs.max() - xs.min() + 1) if len(xs) else 6, 6, 14))
        return ellipse(shape, ax + 0.5, ay + 0.5, w / 2 + 1, w / 4 + 1)
    out = np.zeros(shape, bool)
    H = a.shape[0]
    for x in range(a.shape[1]):
        ys = np.nonzero(a[:, x])[0]
        if len(ys) and ys.max() >= ay - 6:
            b = ys.max()
            out[b - 1: min(b + 3, shape[0]), x] = True
    return out & ~np.pad(a, ((0, shape[0] - H), (0, shape[1] - a.shape[1])))


def d_extract(name, src, variant=""):
    """Sombra D: forma e textura vêm da difusão (escurecimento sobre o branco); o alfa é um
    gradiente: mais forte no centro e no pé, esmaecendo para as bordas e para baixo-direita,
    em 4 níveis com pontilhado Bayer 4x4 nas transições. Contato no pé no nível máximo."""
    g, obj, anc, pos = layout(name)
    bp = next((HERE / "specs" / "bases").glob(f"sombra_{name}_D{variant}_*x.png"))
    S = int(bp.stem.rsplit("_", 1)[1][:-1])
    size = (Image.open(bp).width // S, Image.open(bp).height // S)
    out = np.asarray(Image.open(src).convert("RGB").resize(size, Image.BOX)).astype(float)
    mk = np.asarray(Image.open(HERE / "specs" / "masks" / f"sombra_{name}_D{variant}.png").resize(size, Image.NEAREST)) > 127
    dark = 1 - (out @ [0.3, 0.59, 0.11]) / 255
    dark[(out.max(-1) - out.min(-1)) > 40] = 0  # cor saturada = coisa inventada
    m = mk & (dark >= D_CUT)
    lab, n = ndimage.label(m)
    if n:
        sizes = ndimage.sum(m, lab, range(1, n + 1))
        m = np.isin(lab, [i + 1 for i, sz in enumerate(sizes) if sz >= 6])
    # contato no pé
    a_obj = alpha_of(obj)
    c = d_contact((a_obj.shape[0] + 8, a_obj.shape[1] + 8), a_obj, anc, kind_of(name))
    cc = np.zeros(m.shape, bool)
    h, w = min(c.shape[0], m.shape[0] - pos[1]), min(c.shape[1], m.shape[1] - pos[0])
    cc[pos[1]:pos[1] + h, pos[0]:pos[0] + w] = c[:h, :w]
    m |= cc
    # gradiente: profundidade dentro da forma (borda = 0, miolo = 1) e distância ao pé, mais
    # longa na direção baixo-direita (a sombra esmaece mais para lá)
    inner = ndimage.distance_transform_edt(m)
    inner = np.clip(inner / max(np.percentile(inner[m], 90), 1), 0, 1)
    yy, xx = np.mgrid[: m.shape[0], : m.shape[1]]
    fx, fy = pos[0] + anc[0] + 0.5, pos[1] + anc[1] + 0.5
    dx, dy = xx - fx, (yy - fy) * 2  # losango 2:1 -> círculo
    along = np.clip((dx * DIR[0] + dy * DIR[1] / 2), 0, None)
    dist = np.hypot(dx, dy) + 0.6 * along
    dist = dist / max(np.percentile(dist[m], 95), 1)
    dk = np.clip(dark / max(np.percentile(dark[m & ~cc], 90) if (m & ~cc).any() else 1, 1e-3), 0, 1)
    score = D_W[0] * dk + D_W[1] * inner + D_W[2] * (1 - np.clip(dist, 0, 1))
    score[cc] = 1
    lv = np.floor(score * len(D_LEVELS) + BAYER4[yy % 4, xx % 4] + D_BIAS).astype(int)
    lv = np.clip(lv, 1, len(D_LEVELS))
    lv[cc] = len(D_LEVELS)
    rgba = np.zeros(m.shape + (4,), np.uint8)
    for k, a in enumerate(D_LEVELS):
        rgba[m & (lv == k + 1)] = SHADE + (a,)
    img = Image.fromarray(rgba)
    bb = img.getbbox()
    ax, ay = pos[0] + anc[0], pos[1] + anc[1]
    meta = {"anchor": [ax - bb[0], ay - bb[1]], "offset": [bb[0] - ax, bb[1] - ay], "obj_anchor": list(anc),
            "alpha": 1.0, "levels": list(D_LEVELS), "dir": [2, 1], "len": LEN, "tech": "D",
            "src": str(Path(src).relative_to(RUNS)), "nota": "alfa já no PNG; modulate 1.0"}
    save(img.crop(bb), meta, f"{name}_sombraD")
    return img


def d_candidates(name):
    return sorted(RUNS.glob(f"o*/sombraD-{name}-*.png"))


def cmd_dsheet(zoom=3):
    """tmp/sombras/candidatos.png: todas as seeds de cada objeto (extraídas como D) sobre a
    grama, para escolher à mão. Rótulo = arquivo."""
    from PIL import ImageDraw
    rows = []
    for name in D_OBJECTS:
        g, obj, anc, pos = layout(name)
        row = []
        for p in d_candidates(name):
            var = "w" if "-Dw-" in p.name else ""
            img = d_extract(name, p, var)
            c = g.copy(); c.alpha_composite(img); c.alpha_composite(obj, pos)
            row.append((p.parent.name + "/" + p.name.split("-")[-1][:-4] + var, c))
        if row:
            rows.append((name, row))
    if not rows:
        return
    W = max(sum(c.width + 4 for _, c in r) for _, r in rows)
    H = sum(max(c.height for _, c in r) + 16 for _, r in rows)
    sheet = Image.new("RGBA", (W, H), (36, 34, 40, 255))
    labels = []
    y = 0
    for name, r in rows:
        x = 0
        for lab, c in r:
            sheet.alpha_composite(c, (x, y + 14)); labels.append((x, y, f"{name} {lab}")); x += c.width + 4
        y += max(c.height for _, c in r) + 16
    big = sheet.resize((W * zoom, H * zoom), Image.NEAREST)
    dr = ImageDraw.Draw(big)
    for x, y, t in labels:
        dr.text((x * zoom + 2, y * zoom + 4), t, fill=(240, 240, 220), font=P.font(14))
    (HERE / "tmp" / "sombras").mkdir(parents=True, exist_ok=True)
    big.convert("RGB").save(HERE / "tmp" / "sombras" / "candidatos.png")
    print("ok candidatos")


PLAYER = OLD / "Player" / "farmer_Player.png"


def cmd_dfinal(zoom=3):
    """Grava as D escolhidas (D_PICK) e out/sombras/comparacao_D.png: B (sol alto), A3 (o38,
    sol baixo, só onde existe) e D, com o jogador ao lado para casar a sombra."""
    from PIL import ImageDraw
    pl = Image.open(PLAYER).convert("RGBA").crop((0, 0, 32, 32))
    rows = []
    for name in D_OBJECTS:
        g0, obj, anc, pos = layout(name)
        g = grass(g0.width + 28, g0.height)
        fn = phase_frame(name)[0][1] if kind_of(name) == "tree" else name
        cells = []
        for t in ("B", "A3", "D"):
            c = g.copy()
            if t == "D":
                if name not in D_PICK:
                    cells.append(None); continue
                src = next(RUNS.glob(D_PICK[name][0]))
                img = d_extract(name, src, D_PICK[name][1])
                c.alpha_composite(img)
            elif t == "A3":
                p = OUT / f"{fn}_sombraA3.png"
                if not p.exists():
                    cells.append(None); continue
                meta = json.loads(p.with_suffix(".json").read_text())
                c.alpha_composite(Image.open(p), (pos[0] + anc[0] + meta["offset"][0], pos[1] + anc[1] + meta["offset"][1]))
            else:
                sh = shadow_of(fn, "B")
                if sh is None:
                    cells.append(None); continue
                m = place_shadow(c.size, sh, anc, pos)
                la = np.zeros(m.shape + (4,), np.uint8); la[m] = SHADE + (int(ALPHA * 255),)
                c.alpha_composite(Image.fromarray(la))
            c.alpha_composite(obj, pos)
            c.alpha_composite(pl, (g.width - 30, pos[1] + anc[1] - 24))  # pé do jogador na linha do pé
            cells.append(c)
        rows.append((name, cells))
    cw = max(c.width for _, r in rows for c in r if c) + 4
    hs = [max(c.height for c in r if c) + 4 for _, r in rows]
    sheet = Image.new("RGBA", (cw * 3 + 4, sum(hs) + 12), (36, 34, 40, 255))
    y = 12
    for (_, r), h in zip(rows, hs):
        for k, c in enumerate(r):
            if c:
                sheet.alpha_composite(c, (4 + k * cw, y))
        y += h
    big = sheet.resize((sheet.width * zoom, sheet.height * zoom), Image.NEAREST)
    dr = ImageDraw.Draw(big)
    for k, t in enumerate(("B projeção (sol alto)", "A3 difusão (1a rodada, sol baixo)", "D difusão + gradiente")):
        dr.text(((4 + k * cw) * zoom + 4, 6), t, fill=(240, 240, 220), font=P.font(15))
    y = 12
    for (name, _), h in zip(rows, hs):
        dr.text((8, y * zoom + 4), name, fill=(255, 255, 255), font=P.font(15))
        y += h
    big.convert("RGB").save(OUT / "comparacao_D.png")
    print("ok", OUT / "comparacao_D.png", big.size)


D_PICK = {  # objeto: (glob da seed escolhida em runs/, variante da máscara "" ou "w")
    "arvore_baru": ("o39/sombraD-arvore_baru-D-3850272067.png", ""),
    "arvore_pequi": ("o40/sombraD-arvore_pequi-Dw-3604111450.png", "w"),
    "arvore_seca_caida": ("o39/sombraD-arvore_seca_caida-D-2088095666.png", ""),
    "house": ("o39/sombraD-house-D-3951061832.png", ""),
    "arvore_cagaita": ("o39/sombraD-arvore_cagaita-D-1943974942.png", ""),
    "arvore_ipe_roxo": ("o39/sombraD-arvore_ipe_roxo-D-3651387416.png", ""),
    "arvore_ipe_amarelo": ("o39/sombraD-arvore_ipe_amarelo-D-3849256815.png", ""),
    "carro_de_boi": ("o39/sombraD-carro_de_boi-D-657644687.png", ""),
    "moinho": ("o40/sombraD-moinho-Dw-510054581.png", "w"),
    "cupinzeiro_alto": ("o39/sombraD-cupinzeiro_alto-D-157285820.png", ""),
}


def cmd_preview(zoom=3):
    rows = []
    for name in OBJECTS:
        fn = phase_frame(name)[0][1] if kind_of(name) == "tree" else name
        g, obj, anc, pos = layout(name)
        row = []
        for label, t in COLS:
            if t == "old":
                row.append(compose(g, obj, anc, pos, ellipse_old(obj, anc), alpha=80 / 255))
            elif t == "A3":
                p = OUT / f"{fn}_sombraA3.png"
                if p.exists():
                    meta = json.loads(p.with_suffix(".json").read_text())
                    c = g.copy()
                    c.alpha_composite(Image.open(p), (pos[0] + anc[0] + meta["offset"][0], pos[1] + anc[1] + meta["offset"][1]))
                    c.alpha_composite(obj, pos)
                    row.append(c)
                else:
                    row.append(None)
            elif t.endswith("raw"):
                p = OUT / f"{fn}_sombra{t[:-3]}_bruto.png"
                if p.exists():
                    c = g.copy(); c.alpha_composite(Image.open(p)); c.alpha_composite(obj, pos)
                    row.append(c)
                else:
                    row.append(None)
            else:
                sh = shadow_of(fn, t.rstrip("s"))
                o = Image.open(OUT / f"{name}_autosombra.png") if t == "Bs" else obj
                row.append(compose(g, o, anc, pos, sh) if sh else None)
        rows.append((name, row))
    cw = max(c.width for _, r in rows for c in r if c) + 4
    W = cw * len(COLS) + 4
    hs = [max(c.height for c in r if c) + 4 for _, r in rows]
    sheet = Image.new("RGBA", (W, sum(hs) + 12), (36, 34, 40, 255))
    y = 12
    for (_, r), h in zip(rows, hs):
        for k, c in enumerate(r):
            if c:
                sheet.alpha_composite(c, (4 + k * cw, y))
        y += h
    big = sheet.resize((sheet.width * zoom, sheet.height * zoom), Image.NEAREST)
    dr = ImageDraw.Draw(big)
    f = P.font(15)
    for k, (label, _) in enumerate(COLS):
        dr.text(((4 + k * cw) * zoom + 4, 6), label, fill=(240, 240, 220), font=f)
    y = 12
    for (name, _), h in zip(rows, hs):
        dr.text((8, y * zoom + 4), name, fill=(255, 255, 255), font=f)
        y += h
    big.convert("RGB").save(OUT / "comparacao.png")
    print("ok", OUT / "comparacao.png", big.size)


def cmd_phases(zoom=3):
    """out/sombras/fases.png: as fases de cada árvore com a sombra B da própria fase
    (mesmo offset em todas; só a copa da sombra muda)."""
    rows = []
    for name in OBJECTS:
        if kind_of(name) != "tree":
            continue
        g, obj0, anc, pos = layout(name)
        row = []
        for ph, fn in phase_frame(name):
            obj, _, _ = load_obj(name, ph)
            row.append(compose(g, obj, anc, pos, shadow_of(fn, "B")))
        rows.append(row)
    W = max(sum(c.width + 4 for c in r) for r in rows)
    H = sum(r[0].height + 4 for r in rows)
    sheet = Image.new("RGBA", (W, H), (36, 34, 40, 255))
    y = 0
    for r in rows:
        x = 0
        for c in r:
            sheet.alpha_composite(c, (x, y)); x += c.width + 4
        y += r[0].height + 4
    sheet.resize((W * zoom, H * zoom), Image.NEAREST).convert("RGB").save(OUT / "fases.png")
    print("ok", OUT / "fases.png")


def cmd_overlap(zoom=3):
    """out/sombras/sobreposicao.png: 3 árvores e o carro perto, em 3 montagens:
    (1) sombra por sprite com alfa próprio (dobra onde cruza), (2) todas as sombras numa
    camada com alfa único (CanvasGroup), (3) sombra embutida no PNG do objeto (dobra onde
    cruza e, desenhada na ordem y, a sombra de um objeto cobre o pé do vizinho de trás)."""
    items = [("arvore_pequi", (10, 4)), ("arvore_ipe_amarelo", (78, 20)), ("carro_de_boi", (100, 92)),
             ("arvore_cagaita", (40, 70))]
    W, H = 240, 190
    g = grass(W, H, seed=5)
    loaded = []
    for name, (x, y) in items:
        fn = phase_frame(name)[0][1] if kind_of(name) == "tree" else name
        obj, anc, _ = load_obj(name, phase_frame(name)[0][0] if kind_of(name) == "tree" else None)
        loaded.append((name, fn, obj, anc, (x, y)))
    loaded.sort(key=lambda t: t[4][1] + t[3][1])  # ordem y do pé
    panels = []
    for mode in ("sprite", "grupo", "embutida"):
        c = g.copy()
        if mode != "embutida":
            union = np.zeros((H, W), bool)
            for name, fn, obj, anc, pos in loaded:
                m = place_shadow((W, H), shadow_of(fn, "B"), anc, pos)
                if mode == "sprite":
                    la = np.zeros((H, W, 4), np.uint8); la[m] = SHADE + (int(ALPHA * 255),)
                    c.alpha_composite(Image.fromarray(la))
                union |= m
            if mode == "grupo":
                la = np.zeros((H, W, 4), np.uint8); la[union] = SHADE + (int(ALPHA * 255),)
                c.alpha_composite(Image.fromarray(la))
            for name, fn, obj, anc, pos in loaded:
                c.alpha_composite(obj, pos)
        else:
            for name, fn, obj, anc, pos in loaded:
                e = Image.open(OUT / f"{name}_embutida.png")
                ea = json.loads((OUT / f"{name}_embutida.json").read_text())["anchor"]
                c.alpha_composite(e, (pos[0] + anc[0] - ea[0], pos[1] + anc[1] - ea[1]))
        panels.append(c)
    sheet = Image.new("RGBA", (W * 3 + 8, H + 14), (36, 34, 40, 255))
    for k, p in enumerate(panels):
        sheet.alpha_composite(p, (k * (W + 4), 14))
    big = sheet.resize((sheet.width * zoom, sheet.height * zoom), Image.NEAREST)
    dr = ImageDraw.Draw(big)
    for k, t in enumerate(("1 alfa por sprite (dobra no cruzamento)", "2 camada única / CanvasGroup", "3 embutida no PNG")):
        dr.text((k * (W + 4) * zoom + 6, 8), t, fill=(240, 240, 220), font=P.font(16))
    big.convert("RGB").save(OUT / "sobreposicao.png")
    print("ok", OUT / "sobreposicao.png")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "all"
    if cmd == "dbases":  # sombras.py dbases [w] [objeto ...]
        args = sys.argv[2:]
        var = "w" if args[:1] == ["w"] else ""
        d_bases(args[1:] if var else args or None, var); sys.exit()
    if cmd in ("dsheet", "dfinal"):
        {"dsheet": cmd_dsheet, "dfinal": cmd_dfinal}[cmd](); sys.exit()
    if cmd == "bases" and len(sys.argv) > 2:
        cmd_bases(tuple(sys.argv[2:])); sys.exit()
    cmds = {"phases": cmd_phases, "overlap": cmd_overlap, "proc": cmd_proc, "bases": cmd_bases, "extract": cmd_extract, "preview": cmd_preview}
    if cmd == "all":
        cmd_proc(); cmd_extract(); cmd_preview(); cmd_overlap(); cmd_phases()
    else:
        cmds[cmd]()
