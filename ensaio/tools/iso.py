"""Biblioteca de geometria isométrica para tiles 32x32 do Godot 4.

Silhueta canônica ("bloco"), em células de 32x32:
  - face de cima: losango nas linhas 8..23, larguras 4,8,...,32 (linhas 8..15)
    e 32,...,4 (linhas 16..23), centrado em x;
  - o bloco tem 8 px de profundidade: união do losango com ele mesmo
    deslocado 8 px para baixo (e tudo entre os dois).
"""
import numpy as np
from PIL import Image

N = 32
DEPTH = 8


def _top_widths():
    w = np.zeros(N, int)
    for r in range(8, 16):
        w[r] = 4 * (r - 7)
    for r in range(16, 24):
        w[r] = 4 * (24 - r)
    return w


def _rows_to_mask(widths):
    m = np.zeros((N, N), bool)
    for r, w in enumerate(widths):
        if w:
            m[r, 16 - w // 2:16 + w // 2] = True
    return m


def top_mask():
    """Face de cima (losango, linhas 8..23)."""
    return _rows_to_mask(_top_widths())


def block_mask():
    """Silhueta completa: losango U losango deslocado 8 px, e o que há entre."""
    top = top_mask()
    shifted = np.zeros_like(top)
    shifted[DEPTH:] = top[:-DEPTH]
    m = top | shifted
    # preenche entre os dois losangos (por coluna, do primeiro ao último pixel)
    for x in range(N):
        ys = np.nonzero(m[:, x])[0]
        m[ys.min():ys.max() + 1, x] = True
    return m


def left_mask():
    """Face esquerda: abaixo da aresta inferior-esquerda da face de cima."""
    m = block_mask() & ~top_mask()
    m[:, 16:] = False
    return m


def right_mask():
    """Face direita: abaixo da aresta inferior-direita da face de cima."""
    m = block_mask() & ~top_mask()
    m[:, :16] = False
    return m


def snap_tile(img):
    """Força um RGBA 32x32 à silhueta canônica.

    Binariza o alfa (>=128), apaga o que está fora e preenche os buracos com
    o pixel opaco mais próximo da mesma face.
    """
    a = np.array(img.convert("RGBA"))
    if a.shape[:2] != (N, N):
        raise ValueError("o tile precisa ter 32x32 pixels")
    opaque = a[..., 3] >= 128
    block = block_mask()
    a[~block] = 0
    for face in (top_mask(), left_mask(), right_mask()):
        have = face & opaque
        miss = face & ~opaque
        src = np.argwhere(have)
        if not len(src):  # face vazia: usa qualquer pixel opaco do bloco
            src = np.argwhere(block & opaque)
        if not len(src):
            continue
        for y, x in np.argwhere(miss):
            d = ((src - (y, x)) ** 2).sum(1)
            sy, sx = src[d.argmin()]
            a[y, x, :3] = a[sy, sx, :3]
    a[block, 3] = 255
    a[~block, 3] = 0
    return Image.fromarray(a, "RGBA")


# Godot DIAMOND_DOWN (tile_layout = 5), tile_size 32x16: o eixo X da célula
# aponta para baixo-direita e o eixo Y para baixo-esquerda:
#   centro_tela = ((x - y) * 16, (x + y) * 8)
# Vizinhos ficam em (+-16, +8) (e (0, +16) na diagonal). Ordem de desenho de
# trás para frente: por y de tela (x + y) e depois por x de tela (x - y).
def cell_center(cell):
    x, y = cell
    return (x - y) * 16, (x + y) * 8


def render_map(cells, tiles=None, origin=(0, 4), pad=0):
    """Desenha {(x, y): imagem} como o Godot (canto sup. esq. = centro - 16 - origin).

    `tiles` é opcional: se dado, os valores de `cells` podem ser chaves de `tiles`.
    A imagem devolvida leva em .info["cell0"] a posição do centro da célula (0,0).
    """
    def get(v):
        return tiles[v] if tiles is not None and not isinstance(v, Image.Image) else v

    items = sorted(cells.items(), key=lambda kv: (sum(kv[0]), kv[0][0] - kv[0][1]))
    pos = []
    for c, v in items:
        cx, cy = cell_center(c)
        pos.append((c, get(v), cx - N // 2 - origin[0], cy - N // 2 - origin[1]))
    x0 = min(p[2] for p in pos) - pad
    y0 = min(p[3] for p in pos) - pad
    x1 = max(p[2] + p[1].width for p in pos) + pad
    y1 = max(p[3] + p[1].height for p in pos) + pad
    canvas = Image.new("RGBA", (x1 - x0, y1 - y0), (0, 0, 0, 0))
    for _, im, px, py in pos:
        canvas.alpha_composite(im.convert("RGBA"), (px - x0, py - y0))
    canvas.info["cell0"] = (-x0, -y0)
    return canvas


def place_object(canvas, sprite, anchor, cell):
    """Cola `sprite` com o ponto de pé `anchor` (px no sprite) no centro de `cell`.

    `canvas` deve vir de render_map (usa canvas.info["cell0"]); use `pad` lá
    para objetos altos.
    """
    ox, oy = canvas.info["cell0"]
    cx, cy = cell_center(cell)
    layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    layer.paste(sprite.convert("RGBA"), (ox + cx - anchor[0], oy + cy - anchor[1]))  # corta o que sai
    canvas.alpha_composite(layer)
    return canvas
