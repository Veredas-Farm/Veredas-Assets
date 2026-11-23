#!/usr/bin/env python3
"""Manequim do fazendeiro desenhado à mão em pixel (3 vistas, escala do Player.png).

Serve de base para img2img (ampliado com nearest, fundo branco) e de
referência de proporção. Mesmo esqueleto do sprite atual: cabeça ~11 px,
corpo ~8 px, 13 px de largura no corpo; o chapéu tem aba de 17 px.

Uso: blockout.py  -> out/blockout_32.png (96x32, frente/lado/costas),
                     out/blockout_4x.png, bases/*.png (ampliadas para img2img)
"""
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

HERE = Path(__file__).resolve().parent
OUTLINE = (14, 7, 27)  # contorno do Player.png
SHADOW = (0, 0, 0, 100)  # sombra do Player.png
COL = {
    "y": (226, 190, 112),  # palha clara
    "Y": (178, 134, 72),  # palha escura
    "r": (120, 52, 40),  # fita do chapéu
    "h": (93, 44, 40),  # cabelo (do Player.png)
    "S": (246, 202, 159),  # pele (do Player.png)
    "s": (210, 159, 112),  # pele sombra (do Player.png)
    "R": (186, 62, 52),  # camisa xadrez clara
    "q": (128, 38, 44),  # camisa xadrez escura
    "B": (0, 105, 170),  # calça (azul escuro do Player.png)
    "d": (19, 70, 120),  # calça sombra
    "k": (112, 70, 67),  # botina (marrom do cabelo do Player.png)
    "K": (74, 40, 38),  # botina escura
    "#": OUTLINE,  # detalhe interno (olho)
}

HAT = [
    "       yyyyyyy       ",
    "       yYyyyYy       ",
    "       rrrrrrr       ",
    "    yyyyyyyyyyyyy    ",
    "  YyyyyyyyyyyyyyyyY  ",
    "    YYYYYYYYYYYYY    ",
]
VIEWS = {
    "front": HAT + [
        "      hhSSSSShh      ",
        "      hS#SSS#Sh      ",
        "       sSSSSSs       ",
        "        sSSSs        ",
        "       RqRRRqR       ",
        "      RRqRRRqRR      ",
        "      SqRRqRRqS      ",
        "       BBBBBBB       ",
        "       BBdBdBB       ",
        "       Bd   dB       ",
        "       kK   Kk       ",
    ],
    "side": [
        "        yyyyyyy      ",
        "        yYyyyYy      ",
        "        rrrrrrr      ",
        "     yyyyyyyyyyyyy   ",
        "   YyyyyyyyyyyyyyyyY ",
        "     YYYYYYYYYYYYY   ",
        "        hhhhSSSS     ",
        "        hhhSS#SS     ",
        "        hhsSSSSS     ",
        "         hsSSSs      ",
        "         RqRRqR      ",
        "         RqRSRq      ",
        "         qRqSqR      ",
        "         BBBBBB      ",
        "         BdBBBB      ",
        "         dB  dB      ",
        "         Kkk Kkk     ",
    ],
    "back": HAT + [
        "      hhhhhhhhh      ",
        "      hhhhhhhhh      ",
        "       hhhhhhh       ",
        "        sSSSs        ",
        "       RqRRRqR       ",
        "      RRqRRRqRR      ",
        "      SqRRqRRqS      ",
        "       BBBBBBB       ",
        "       BBdBdBB       ",
        "       Bd   dB       ",
        "       Kk   kK       ",
    ],
}
# caminhada de lado (4 quadros): passo A, cruzando (corpo sobe 1 px), passo B, cruzando.
# Troca só o braço (linhas 11-12 do lado) e as pernas (últimas 4 linhas).
_SIDE_TOP = VIEWS["side"][:11]
WALK_SIDE = [
    _SIDE_TOP + [
        "        SRqRRqR      ",
        "         qRqRqR      ",
        "         BBBBBB      ",
        "       dBdBBBBBB     ",
        "      KKk     Kkk    ",
    ],
    _SIDE_TOP + [
        "         RqRSRq      ",
        "         qRqSqR      ",
        "         BBBBBB      ",
        "          BdBB       ",
        "          dBBB       ",
        "          Kkkk       ",
    ],
    _SIDE_TOP + [
        "         RqRRqRS     ",
        "         qRqRqR      ",
        "         BBBBBB      ",
        "       BBBBBdBdB     ",
        "      kkk     KKk    ",
    ],
    _SIDE_TOP + [
        "         RqRSRq      ",
        "         qRqSqR      ",
        "         BBBBBB      ",
        "          BBdB       ",
        "          BBBd       ",
        "          kkKK       ",
    ],
]


FOOT = 21  # última linha da botina (sem contorno); o contorno fica na 22, como no Player.png


def frame(rows, shadow=True):
    """Célula 32x32 RGBA com contorno automático e sombra no chão; pé na linha FOOT."""
    h, w = len(rows), max(len(r) for r in rows)
    top = FOOT - h + 1
    rgb = np.zeros((32, 32, 3), np.uint8)
    m = np.zeros((32, 32), bool)
    x0 = 5
    for j, row in enumerate(rows):
        for i, c in enumerate(row):
            if c != " ":
                rgb[top + j, x0 + i] = COL[c]
                m[top + j, x0 + i] = True
    ring = ndimage.binary_dilation(m, np.array([[0, 1, 0], [1, 1, 1], [0, 1, 0]])) & ~m
    rgb[ring] = OUTLINE
    m |= ring
    img = np.zeros((32, 32, 4), np.uint8)
    if shadow:
        foot = np.nonzero(m.any(1))[0].max()
        xs = np.nonzero(m.any(0))[0]
        cx = (xs.min() + xs.max()) / 2
        yy, xx = np.mgrid[0:32, 0:32]
        ell = ((xx - cx) / 6.5) ** 2 + ((yy - foot + 0.5) / 1.6) ** 2 <= 1
        img[ell] = SHADOW
    img[m, :3] = rgb[m]
    img[m, 3] = 255
    return Image.fromarray(img, "RGBA")


def on_white(im, scale):
    bg = Image.new("RGBA", im.size, (255, 255, 255, 255))
    bg.alpha_composite(im)
    return bg.convert("RGB").resize((im.width * scale, im.height * scale), Image.NEAREST)


def main():
    out = HERE / "out"
    bases = HERE / "bases"
    out.mkdir(exist_ok=True)
    bases.mkdir(exist_ok=True)
    frames = [frame(VIEWS[v]) for v in ("front", "side", "back")]
    sheet = Image.new("RGBA", (96, 32))
    for i, f in enumerate(frames):
        sheet.alpha_composite(f, (i * 32, 0))
    sheet.save(out / "blockout_32.png")
    sheet.resize((96 * 8, 32 * 8), Image.NEAREST).save(out / "blockout_8x.png")
    walk = Image.new("RGBA", (32 * len(WALK_SIDE), 32))
    for i, rows in enumerate(WALK_SIDE):
        walk.alpha_composite(frame(rows), (32 * i, 0))
    walk.save(out / "blockout_walk_side_32.png")
    walk.resize((walk.width * 8, 256), Image.NEAREST).save(out / "blockout_walk_side_8x.png")
    for i, rows in enumerate(WALK_SIDE):
        on_white(frame(rows, shadow=False), 16).save(bases / f"walk_side{i}_512.png")
    # bases para img2img, sem sombra: 1 vista em 512x512 (figura ~16x) e as 3 numa fileira 1344x576
    for v in VIEWS:
        f = frame(VIEWS[v], shadow=False).crop((0, 0, 32, 32))
        on_white(f, 16).save(bases / f"{v}_512.png")
    row = Image.new("RGBA", (84, 36))
    for i, v in enumerate(("front", "side", "back")):
        row.alpha_composite(frame(VIEWS[v], shadow=False), (-3 + i * 28, 2))
    on_white(row, 16).save(bases / "row_1344x576.png")


if __name__ == "__main__":
    main()


def sheet_base(path, cells=(196, 84), zoom=8, order=None):
    """Folha 196x84 células (x8 = 1568x672, a área que o img2img do moss usa sem
    reamostrar): 2 fileiras de 6 quadros 32x32. Cada pixel do manequim = 1 pixel
    nativo da LoRA (grade de 8 px), para a geração voltar 1:1 com redução por 8."""
    order = order or [VIEWS["front"], VIEWS["side"], VIEWS["back"], WALK_SIDE[0], WALK_SIDE[1], WALK_SIDE[2],
             WALK_SIDE[3], VIEWS["front"], VIEWS["side"], VIEWS["back"], WALK_SIDE[0], WALK_SIDE[2]]
    W, H = cells
    im = Image.new("RGBA", (W, H))
    ox, oy = (W - 6 * 32) // 2, (H - 64) // 2
    for k, rows in enumerate(order):
        im.alpha_composite(frame(rows, shadow=False), (ox + 32 * (k % 6), oy + 32 * (k // 6)))
    on_white(im, zoom).save(path)
    return ox, oy


def per_view_bases():
    """Folhas de uma vista só (o modelo troca as vistas numa folha mista)."""
    W = WALK_SIDE
    sheets = {
        "front": [VIEWS["front"]] * 12,
        "back": [VIEWS["back"]] * 12,
        "side": [VIEWS["side"], W[0], W[1], W[2], W[3], VIEWS["side"],
                 W[0], W[1], W[2], W[3], VIEWS["side"], W[0]],
    }
    for k, order in sheets.items():
        sheet_base(HERE / "bases" / f"sheet_{k}_1568x672.png", order=order)


# variante B: camisa lisa creme, calça marrom, cabelo castanho mais claro (troca de cores do manequim)
COL_B = dict(COL, R=(226, 214, 178), q=(176, 160, 124), B=(122, 86, 56), d=(92, 62, 42),
             h=(132, 82, 50), k=(70, 44, 36), K=(50, 30, 28))


def variant_b():
    global COL
    old = COL
    COL = COL_B
    try:
        W = WALK_SIDE
        for k, order in {"front": [VIEWS["front"]] * 12, "back": [VIEWS["back"]] * 12,
                         "side": [VIEWS["side"], W[0], W[1], W[2], W[3], VIEWS["side"],
                                  W[0], W[1], W[2], W[3], VIEWS["side"], W[0]]}.items():
            sheet_base(HERE / "bases" / f"sheetB_{k}_1568x672.png", order=order)
        im = Image.new("RGBA", (96, 32))
        for i, v in enumerate(("front", "side", "back")):
            im.alpha_composite(frame(VIEWS[v]), (32 * i, 0))
        im.save(HERE / "out" / "blockoutB_32.png")
    finally:
        COL = old


# caminhada de frente e de costas (4 quadros, mesmo esqueleto da de lado): passo A (perna da
# esquerda embaixo, a outra 1 px acima), cruza (pernas juntas, corpo 1 px acima), passo B, cruza.
_LEGS = {
    "A": ["       BBBBBBB       ",
          "       BBdBdBB       ",
          "       Bd   kK       ",
          "       kK            "],
    "P": ["       BBBBBBB       ",
          "       BBdBdBB       ",
          "        Bd dB        ",
          "        Bd dB        ",
          "        kK Kk        "],
    "B": ["       BBBBBBB       ",
          "       BBdBdBB       ",
          "       kK   dB       ",
          "            Kk       "],
}
# braço: no passo A a mão da direita vai para trás (some atrás do corpo), no B a da esquerda
_HANDS = {"A": "      SqRRqRRqR      ", "P": "      SqRRqRRqS      ", "B": "      RqRRqRRqS      "}


def _walk(view):
    top = VIEWS[view][:-4]  # tudo menos as 4 linhas de perna
    out = []
    for k in "APBP":
        rows = list(top)
        rows[-1] = _HANDS[k]  # última linha do tronco = mãos
        out.append(rows + _LEGS[k])
    return out


WALK_FRONT = _walk("front")
WALK_BACK = _walk("back")


def walk_bases(prefix="sheet"):
    """Folhas alinhadas (8x) de caminhada de frente e de costas: 4 quadros x 3."""
    for k, w in (("walkfront", WALK_FRONT), ("walkback", WALK_BACK)):
        sheet_base(HERE / "bases" / f"{prefix}_{k}_1568x672.png", order=w * 3)
    for k, w in (("front", WALK_FRONT), ("back", WALK_BACK)):
        im = Image.new("RGBA", (128, 32))
        for i, rows in enumerate(w):
            im.alpha_composite(frame(rows), (32 * i, 0))
        im.save(HERE / "out" / f"{'blockout' if prefix == 'sheet' else 'blockoutB'}_walk_{k}_32.png")


def walk_bases_b():
    global COL
    old = COL
    COL = COL_B
    try:
        walk_bases("sheetB")
    finally:
        COL = old


# --- c21+: ciclos de 6 quadros (layout do Player.png), desmaio e mapa de rótulos ---
# lado: passo A, meio A (pés no chão, pernas meio abertas), cruza, passo B, meio B, cruza
_SIDE_ARMS = VIEWS["side"][11:13]
SIDE_HALF = {
    "A": _SIDE_TOP + _SIDE_ARMS + [
        "         BBBBBB      ",
        "        dBBBBBBB     ",
        "        dB    BB     ",
        "       KKk    kkk    ",
    ],
    "B": _SIDE_TOP + _SIDE_ARMS + [
        "         BBBBBB      ",
        "        BBBBBBdB     ",
        "        BB    dB     ",
        "       kkk    KKk    ",
    ],
}
WALK6_SIDE = [WALK_SIDE[0], SIDE_HALF["A"], WALK_SIDE[1], WALK_SIDE[2], SIDE_HALF["B"], WALK_SIDE[3]]
# frente/costas: passo A, parado, cruza, passo B, parado, cruza
WALK6_FRONT = [WALK_FRONT[0], VIEWS["front"], WALK_FRONT[1], WALK_FRONT[2], VIEWS["front"], WALK_FRONT[3]]
WALK6_BACK = [WALK_BACK[0], VIEWS["back"], WALK_BACK[1], WALK_BACK[2], VIEWS["back"], WALK_BACK[3]]

# desmaio (linha 9 do Player.png, de lado): agacha, ajoelha curvado, deitado com o chapéu caído
_S = VIEWS["side"]
FAINT = [
    [" " + r for r in _S[:13]] + [
        "          BBBBBB     ",
        "        KkkBBdBB     ",
    ],
    ["   " + r for r in _S[:10]] + [
        "            RqRRqRS  ",
        "        KkkBBBqRqR   ",
    ],
]


def _lying():
    body = np.array([list(r[8:17].ljust(9)) for r in _S[6:]])  # cabeça + corpo, sem chapéu
    rot = np.rot90(body, -1)  # cabeça para a direita, rosto para baixo
    rows = ["".join(r).rstrip() for r in rot]
    rows = [r for r in rows if r.strip()]
    w = max(len(r) for r in rows)
    hat = ["  yyyyyyy  ", "  rrrrrrr  ", "YyyyyyyyyyY", " YYYYYYYYY "]  # chapéu caído, de lado
    n = max(len(rows), len(hat))
    rows = [""] * (n - len(rows)) + rows
    hat = [""] * (n - len(hat)) + hat
    return ["  " + r.ljust(w + 1) + h for r, h in zip(rows, hat)]


FAINT.append(_lying())


def frame_labels(rows):
    """Mapa 32x32 de rótulos do manequim na mesma posição de frame(): letra de COL, 'o' = contorno, ' ' = vazio."""
    h = len(rows)
    top = FOOT - h + 1
    lab = np.full((32, 32), " ")
    for j, row in enumerate(rows):
        for i, c in enumerate(row):
            if c != " ":
                lab[top + j, 5 + i] = c
    m = lab != " "
    ring = ndimage.binary_dilation(m, np.array([[0, 1, 0], [1, 1, 1], [0, 1, 0]])) & ~m
    lab[ring] = "o"
    return lab


# folhas de 12 quadros por vista (índices usados em player.py)
SHEETS6 = {
    "p6front": [VIEWS["front"], WALK_FRONT[0], WALK_FRONT[1], WALK_FRONT[2]] * 3,
    "p6back": [VIEWS["back"], WALK_BACK[0], WALK_BACK[1], WALK_BACK[2]] * 3,
    "p6side": [VIEWS["side"]] + WALK6_SIDE + FAINT + [VIEWS["side"], WALK_SIDE[0]],
}
# rows de cada quadro de cada folha, para os rótulos
SHEET_ROWS = SHEETS6


def p6_bases(outfit="A"):
    global COL
    old = COL
    COL = COL_B if outfit == "B" else COL
    try:
        for k, order in SHEETS6.items():
            sheet_base(HERE / "bases" / f"{k}{'' if outfit == 'A' else 'B'}_1568x672.png", order=order)
        im = Image.new("RGBA", (32 * 12, 32))
        for i, rows in enumerate(SHEETS6["p6side"]):
            im.alpha_composite(frame(rows), (32 * i, 0))
        im.save(HERE / "out" / f"blockout{'' if outfit == 'A' else 'B'}_p6side_32.png")
    finally:
        COL = old
