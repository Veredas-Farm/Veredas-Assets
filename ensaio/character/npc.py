#!/usr/bin/env python3
"""NPCs no estilo do fazendeiro (c27+): dona da venda, vaqueiro, criança.

Mesma receita do fazendeiro: manequim à mão (mesmo esqueleto, pé na linha 21, contorno automático)
-> folha de 1 vista com 12 quadros ampliada 8x -> moss-pixel img2img 0.55 -> sheet8.py -> trava de cores.

Uso:
  npc.py bases            -> bases/npc_<nome>_<vista>_1568x672.png e out/npc_<nome>_blockout.png
  npc.py build            -> out/npc_<nome>.png (192x192, linhas 0-5 do Player.png), .gif, out/preview_npcs.png
Gerações: out/cells/npc_<nome>_<vista>-*.cells.png (mais nova vence; GEN fixa uma específica).
"""
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "objects"))
import blockout as BO  # noqa: E402
import player as PL  # noqa: E402

OUT = HERE / "out"
VIEWS = ("front", "side", "back")


def sub(rows, i, j, s):
    """Troca as colunas a partir de j da linha i por s."""
    r = list(rows[i].ljust(21))
    r[j:j + len(s)] = s
    rows[i] = "".join(r)


# ---------------------------------------------------------------- dona da venda
LADY_COL = {
    "h": (150, 146, 156), "H": (108, 104, 118),  # cabelo grisalho
    "S": (240, 196, 152), "s": (204, 154, 110),
    "D": (186, 74, 96), "f": (246, 222, 150),  # vestido rosa com florzinhas creme
    "A": (222, 216, 198), "a": (184, 176, 156),  # avental
    "k": (104, 66, 52), "K": (72, 44, 36),  # sapato
    "#": BO.OUTLINE,
}
LADY_MAT = {"h": "hair", "H": "hair", "S": "skin", "s": "skin", "D": "dress", "f": "dress",
            "A": "apron", "a": "apron", "k": "shoes", "K": "shoes"}
LADY = {
    "front": [
        "         hhh         ",
        "        hHhHh        ",
        "       hhhhhhh       ",
        "      hhhhHhhhh      ",
        "      hhSSSSShh      ",
        "      hS#SSS#Sh      ",
        "       sSSSSSs       ",
        "        sSSSs        ",
        "       DfDDDfD       ",
        "      DAAAAAAAD      ",
        "      SAAAAAAAS      ",
        "      DAAAAAAAD      ",
        "      DfaAAAaDD      ",
        "      DDDfDDDfD      ",
        "      DfDDDfDDD      ",
        "       sS   Ss       ",
        "       kK   Kk       ",
    ],
    "back": [
        "         hhh         ",
        "        hHhHh        ",
        "       hhhhhhh       ",
        "      hhhhHhhhh      ",
        "      hhhhhhhhh      ",
        "      hhhhhhhhh      ",
        "       hhhhhhh       ",
        "        sSSSs        ",
        "       DfDDDfD       ",
        "      DDDAAADDD      ",
        "      SDfDADfDS      ",
        "      DDDDDDDDD      ",
        "      DfDDDfDDD      ",
        "      DDDfDDDfD      ",
        "      DfDDDDDfD      ",
        "       sS   Ss       ",
        "       Kk   kK       ",
    ],
    "side": [
        "       hh hhhh       ",
        "      hhHhhhhhhh     ",
        "       hhhhhhhhh     ",
        "        hhhhSSSS     ",
        "        hhhSS#SS     ",
        "        hhsSSSSS     ",
        "         hsSSSs      ",
        "          sSS        ",
        "         DfDDDA      ",
        "         DDfDAA      ",
        "         DfDSAA      ",
        "         DDDDAA      ",
        "        DfDDDAa      ",
        "        DDDfDAa      ",
        "        DfDDDDD      ",
        "         sS  sS      ",
        "         Kkk Kkk     ",
    ],
}
LADY_WALK = {
    "nleg": 2, "hand": 10,
    "front_hands": {"A": "      SAAAAAAAD      ", "B": "      DAAAAAAAS      "},
    "front_legs": {"A": ["       sS   kK       ", "       kK            "],
                   "P": ["        sS Ss        ", "        sS Ss        ", "        kK Kk        "],
                   "B": ["       kK   Ss       ", "            Kk       "]},
    "back_hands": {"A": "      SDfDADfDD      ", "B": "      DDfDADfDS      "},
    "back_legs": {"A": ["       sS   kK       ", "       Kk            "],
                  "P": ["        sS Ss        ", "        sS Ss        ", "        Kk kK        "],
                  "B": ["       kK   Ss       ", "            kK       "]},
    "side_hands": {"A": "        SDfDDAA      ", "P": "         DfDSAA      ", "B": "         DfDDAAS     "},
    "side_legs": {"A": ["       sS     sS     ", "      KKk     Kkk    "],
                  "Ah": ["        sS   sS      ", "       KKk   Kkk     "],
                  "P": ["          sS         ", "          sS         ", "          Kkkk       "],
                  "B": ["       sS     sS     ", "      kkk     KKk    "],
                  "Bh": ["        sS   sS      ", "       kkk   KKk     "],
                  "P2": ["          sS         ", "          sS         ", "          kkKK       "]},
}

# ---------------------------------------------------------------- vaqueiro
# corpo e poses do fazendeiro; troca chapéu (couro, aba virada em meia-lua), gibão aberto, bigode
COW_COL = dict(BO.COL,
               y=(158, 100, 54), Y=(104, 62, 36), r=(222, 186, 112),  # couro do chapéu, enfeite
               h=(44, 32, 32), S=(232, 180, 132), s=(192, 138, 96), m=(58, 40, 34),
               R=(150, 92, 48), q=(104, 60, 34), c=(226, 214, 178),  # gibão, camisa por baixo
               B=(84, 60, 48), d=(60, 42, 34),  # perneira de couro escuro
               k=(52, 36, 32), K=(36, 24, 22))
COW_MAT = {"y": "hat", "Y": "hat", "r": "band", "h": "hair", "m": "hair", "S": "skin", "s": "skin",
           "R": "jacket", "q": "jacket", "c": "shirt", "B": "pants", "d": "pants", "k": "boots", "K": "boots"}
COW_HAT_F = [  # aba da frente virada para cima: meia-lua sobre a testa, com estrela
    "       yyyyyyy       ",
    "     yyyyyyyyyyy     ",
    "    yyyyyyryyyyyy    ",
    "    YyyyyrrryyyyY    ",
    "    YYyyyyryyyyYY    ",
    "      YYYYYYYYY      ",
]
COW_HAT_B = [
    "       yyyyyyy       ",
    "      yyyyyyyyy      ",
    "      yyyyyyyyy      ",
    "     YyyyyyyyyyY     ",
    "    YYYYYYYYYYYYY    ",
    "     YYYYYYYYYYY     ",
]
COW_HAT_S = [
    "           yyyy      ",
    "         yyyyyyyy    ",
    "       yyyyyyyyyyY   ",
    "      yyyyyyyrrrYY   ",
    "    YYYYYYYYYYYYY    ",
    "      YYYYYYYYY      ",
]


def cowboy(rows, view):
    rows = list(rows)
    rows[:6] = {"front": COW_HAT_F, "back": COW_HAT_B, "side": COW_HAT_S}[view]
    if view == "front":
        sub(rows, 8, 8, "SmmmS")  # bigode
        for i in (10, 11, 12):  # gibão aberto: camisa creme no meio
            if i < len(rows) and rows[i][10] in "Rq":
                sub(rows, i, 9, "qcq")
    if view == "side" and rows[8][13] == "S":
        sub(rows, 8, 14, "m")
    return rows


# ---------------------------------------------------------------- criança
KID_COL = {
    "h": (92, 52, 36), "H": (64, 36, 28),
    "S": (226, 172, 124), "s": (186, 130, 88),
    "T": (236, 196, 64), "t": (196, 150, 40),  # camiseta amarela
    "B": (52, 104, 168), "d": (32, 70, 124),  # short azul
    "#": BO.OUTLINE,
}
KID_MAT = {"h": "hair", "H": "hair", "S": "skin", "s": "skin", "T": "tee", "t": "tee", "B": "shorts", "d": "shorts"}
KID = {
    "front": [
        "        hhhhh        ",
        "      hhhHhhhhh      ",
        "     hhhhhhhhhhh     ",
        "     hhhShhhShhh     ",
        "      hSSSSSSSh      ",
        "      hS#SSS#Sh      ",
        "       sSSSSSs       ",
        "        sSSSs        ",
        "      TTTtTtTTT      ",
        "      STTtTtTTS      ",
        "       BBBBBBB       ",
        "       Bd   dB       ",
        "       SS   SS       ",
        "       ss   ss       ",
    ],
    "back": [
        "        hhhhh        ",
        "      hhhHhhhhh      ",
        "     hhhhhhhhhhh     ",
        "     hhhhhHhhhhh     ",
        "      hhhhhhhhh      ",
        "      hhhhhhhhh      ",
        "       hhhhhhh       ",
        "        sSSSs        ",
        "      TTTTTTTTT      ",
        "      STTtTtTTS      ",
        "       BBBBBBB       ",
        "       Bd   dB       ",
        "       SS   SS       ",
        "       ss   ss       ",
    ],
    "side": [
        "         hhhhh       ",
        "       hhhhHhhhh     ",
        "       hhhhhhhhhS    ",
        "       hhhhhhhSSS    ",
        "        hhhhSSSS     ",
        "        hhhSS#SS     ",
        "        hhsSSSSS     ",
        "         hsSSSs      ",
        "         TtTTTT      ",
        "         tTTSTT      ",
        "         BBBBBB      ",
        "         Bd  dB      ",
        "         SS  SS      ",
        "         sSS sSS     ",
    ],
}
KID_WALK = {
    "nleg": 3, "hand": 9,
    "front_hands": {"A": "      STTtTtTTT      ", "B": "      TTTtTtTTS      "},
    "front_legs": {"A": ["       Bd   dB       ", "       SS   ss       ", "       ss            "],
                   "P": ["        Bd dB        ", "        SS SS        ", "        SS SS        ", "        ss ss        "],
                   "B": ["       Bd   dB       ", "       ss   SS       ", "            ss       "]},
    "side_hands": {"A": "        StTTTTT      ", "P": "         tTTSTT      ", "B": "         tTTTTTS     "},
    "side_legs": {"A": ["        dB   BB      ", "       sS     SS     ", "      ssS     SSs    "],
                  "Ah": ["         dB  BB      ", "        sS   SS      ", "       ssS   SSs     "],
                  "P": ["          BdB        ", "          SS         ", "          SS         ", "          sSSs       "],
                  "B": ["        BB   dB      ", "       SS     sS     ", "      SSs     ssS    "],
                  "Bh": ["         BB  dB      ", "        SS   sS      ", "       SSs   ssS     "],
                  "P2": ["          BBd        ", "          SS         ", "          SS         ", "          ssSS       "]},
}
KID_WALK["back_hands"] = KID_WALK["front_hands"]
KID_WALK["back_legs"] = KID_WALK["front_legs"]


# vaqueiro mais claro (pedido depois do c32): gibão caramelo, calça azul desbotado; rampas do escuro ao claro
COW_RECOLOR = {
    "jacket": [(104, 60, 30), (146, 90, 46), (184, 122, 64), (214, 158, 94)],
    "pants": [(50, 62, 90), (74, 94, 130), (104, 128, 164)],
}


def _ramp_like(new, k):
    """Rampa nova com k tons (interpola se a k-means deu outro número de tons)."""
    new = np.array(new, float)
    if len(new) == k:
        return new
    t = np.linspace(0, len(new) - 1, k)
    return np.array([new[int(np.floor(x))] * (1 - x % 1) + new[min(int(np.floor(x)) + 1, len(new) - 1)] * (x % 1) for x in t])


def cowboy_post(c, lab, R, rows):
    """Depois da trava: troca gibão e calça pela cor nova (mesmo índice na rampa) e pinta por cima
    o chapéu de couro do manequim (o modelo trocou a meia-lua por chapéu de caubói)."""
    a = c.copy()
    mi = PL._own(lab)
    from scipy import ndimage
    _, (iy, ix) = ndimage.distance_transform_edt(mi < 0, return_indices=True)
    own = np.where(mi >= 0, mi, mi[iy, ix])
    fig = (a[..., 3] == 255) & ~(a[..., :3] == PL.OUTLINE).all(-1)
    for m, new in COW_RECOLOR.items():
        j = PL.MATS.index(m)
        ramp = R[m]
        nr = _ramp_like(new, len(ramp))
        sel = fig & (own == j)
        for y, x in zip(*np.nonzero(sel)):
            d = np.abs(ramp - a[y, x, :3]).sum(1)
            if d.min() < 1:  # pixel da rampa deste material (não pega pele ou cabelo vizinho)
                a[y, x, :3] = nr[d.argmin()].round()
    # chapéu: linhas do manequim até a última linha de aba, copiadas por inteiro (cor + contorno + vazio)
    hat = np.isin(lab, list("yYr"))
    last = np.nonzero(hat.any(1))[0].max()
    man = np.asarray(with_col(COW_COL, BO.frame, rows, shadow=False))
    keep_body = ~hat & (lab != "o") & (lab != " ")  # rosto/cabelo do manequim nas linhas da aba (lado)
    rr = slice(0, last + 1)
    blk = a[rr].copy()
    mh = man[rr]
    take = ~keep_body[rr]
    blk[take] = mh[take]
    # contorno da aba: o anel do manequim nessas linhas; fora dele e do chapéu, vazio (a geração tinha aba maior)
    # tom claro no alto da copa (o manequim tem só 2 tons de couro)
    top = np.nonzero(hat.any(1))[0].min()
    lit = (lab[rr] == "y") & take & (np.arange(last + 1)[:, None] <= top + 1)
    blk[lit, :3] = (192, 134, 80)
    a[rr] = blk
    # 1 linha abaixo da aba: some o que a aba gerada deixou fora da silhueta do manequim
    y = last + 1
    out = (lab[y] == " ") & (a[y, :, 3] == 255)
    a[y, out] = 0
    # sombra no chão continua a da geração (linhas de baixo intocadas)
    return a


def walk_frames(views, W):
    """Poses de caminhada a partir do parado: troca a linha das mãos e as nleg linhas de baixo."""
    n = W["nleg"]
    out = {}
    for v in ("front", "back"):
        top = views[v][:-n]
        fr = {"idle": views[v]}
        for k in "APB":
            rows = list(top)
            if k in W[f"{v}_hands"]:
                rows[W["hand"]] = W[f"{v}_hands"][k]
            fr[k] = rows + W[f"{v}_legs"][k]
        out[v] = fr
    top = views["side"][:-n]
    fr = {"idle": views["side"]}
    for k in ("A", "Ah", "P", "B", "Bh", "P2"):
        rows = list(top)
        rows[W["hand"]] = W["side_hands"][k[0] if k[0] in "AB" else "P"]
        fr[k] = rows + W["side_legs"][k]
    out["side"] = fr
    return out


def farmer_like(f):
    """Vaqueiro: poses do fazendeiro (blockout) com chapéu, gibão e bigode trocados."""
    out = {
        "front": {"idle": BO.VIEWS["front"], "A": BO.WALK_FRONT[0], "P": BO.WALK_FRONT[1], "B": BO.WALK_FRONT[2]},
        "back": {"idle": BO.VIEWS["back"], "A": BO.WALK_BACK[0], "P": BO.WALK_BACK[1], "B": BO.WALK_BACK[2]},
        "side": {"idle": BO.VIEWS["side"], "A": BO.WALK_SIDE[0], "Ah": BO.SIDE_HALF["A"], "P": BO.WALK_SIDE[1],
                 "B": BO.WALK_SIDE[2], "Bh": BO.SIDE_HALF["B"], "P2": BO.WALK_SIDE[3]},
    }
    return {v: {k: f(r, v) for k, r in fr.items()} for v, fr in out.items()}


NPCS = {
    "dona": {"col": LADY_COL, "mat": LADY_MAT, "torso": "DfA",
             "poses": walk_frames(LADY, LADY_WALK),
             "desc": "a tiny chibi old brazilian shopkeeper lady, big head, grey hair tied in a bun, "
                     "pink floral dress, white apron, brown shoes"},
    "vaqueiro": {"col": COW_COL, "mat": COW_MAT, "torso": "Rqc", "hair_light": False, "post": None,
                 "poses": farmer_like(cowboy),
                 "desc": "a tiny chibi brazilian cowboy, big head, brown leather hat with the brim turned up "
                         "like a half moon, black mustache, brown leather jacket, dark leather trousers, black boots"},
    "crianca": {"col": KID_COL, "mat": KID_MAT, "torso": "Tt",
                "poses": walk_frames(KID, KID_WALK),
                "desc": "a tiny chibi little boy child, big head, messy brown hair, yellow t-shirt, blue shorts, "
                        "barefoot"},
}
VIEW_TXT = {
    "front": "the front view facing the camera, standing and walking frames",
    "side": "the side view facing right, standing and walking frames",
    "back": "the back view, seen from behind, face not visible, standing and walking frames",
}
# ordem dos 12 quadros de cada folha
ORDER = {"front": ["idle", "A", "P", "B"] * 3, "back": ["idle", "A", "P", "B"] * 3,
         "side": ["idle", "A", "Ah", "P", "B", "Bh", "P2", "idle", "A", "Ah", "P", "B"]}


def prompt(name, view):
    return (f"pixel art character sprite sheet of {NPCS[name]['desc']}, every frame is {VIEW_TXT[view]}, "
            "same character in every frame, simple flat colors, 16-bit RPG farming game sprites, "
            "dark outline, plain white background")


def with_col(col, fn, *a, **k):
    old = BO.COL
    BO.COL = col
    try:
        return fn(*a, **k)
    finally:
        BO.COL = old


def bases():
    for name, n in NPCS.items():
        im = Image.new("RGBA", (32 * 7, 32 * 3))
        for vi, v in enumerate(VIEWS):
            P = n["poses"][v]
            order = [P[k] for k in ORDER[v]]
            with_col(n["col"], BO.sheet_base, HERE / "bases" / f"npc_{name}_{v}_1568x672.png", order=order)
            for i, k in enumerate(["idle", "A", "Ah", "P", "B", "Bh", "P2"] if v == "side" else ["idle", "A", "P", "B"]):
                im.alpha_composite(with_col(n["col"], BO.frame, P[k]), (32 * i, 32 * vi))
        im.save(OUT / f"npc_{name}_blockout.png")
        im.resize((im.width * 4, im.height * 4), Image.NEAREST).save(OUT / f"npc_{name}_blockout_4x.png")
        print(name, [prompt(name, v) for v in VIEWS][:1])


# ---------------------------------------------------------------- montagem
GEN = {}  # (nome, vista) -> prefixo exato da geração em out/cells, se quiser fixar uma


def cells(name, view):
    key = GEN.get((name, view), f"npc_{name}_{view}-")
    hits = sorted((OUT / "cells").glob(f"{key}*.cells.png"), key=lambda p: p.stat().st_mtime)
    if not hits:
        return None
    im = np.asarray(Image.open(hits[-1]).convert("RGBA"))
    return [im[32 * (k // 6):32 * (k // 6) + 32, 32 * (k % 6):32 * (k % 6) + 32] for k in range(12)]


# quadro escolhido por pose: índice na folha de 12 (o 1º de cada pose, a menos que PICK diga outro)
PICK = {("vaqueiro", "back", "idle"): 4}  # c32: quadro 0 saiu de frente


def pooled(raw, col, mat):
    """Rampa por material: k-means das cores da geração nas 3 vistas (como player.pooled_ramps);
    o cabelo fica com a rampa do manequim."""
    R = PL.ramps(col)
    R0 = {m: v.copy() for m, v in R.items()}
    pix = {m: [] for m in PL.MATS}
    for fr in raw.values():
        for c, lab in fr.values():
            mi = PL._own(lab)
            ok = (c[..., 3] == 255) & ~(c[..., :3] == PL.OUTLINE).all(-1) & (PL.lum(c[..., :3]) >= 40)
            rgb = c[..., :3].astype(float)
            d = np.stack([np.abs(rgb[..., None, :] - R0[m][None, None]).sum(-1).min(-1) for m in PL.MATS], -1)
            ok &= d.argmin(-1) == mi
            for j, m in enumerate(PL.MATS):
                pix[m].append(c[ok & (mi == j)][:, :3])
    R["_t"] = {}
    if not NPCS[CUR]["hair_light"] if "hair_light" in NPCS[CUR] else False:
        R["hair"] = R["hair"][:-1]  # cabelo preto: sem o tom claro (o fator de brilho jogava nele)
    for m in PL.MATS:
        x = np.concatenate(pix[m])
        if m == "hair" or not len(x):
            continue
        R["_t"][m] = float(np.median(PL.lum(x)))
        k = 4 if m in ("dress", "jacket", "hat") else 3
        if len(x) > 4 * k:
            R[m] = PL.kmeans(x, k).round()
    return R


def bob(rgba, lab, torso):
    ys = np.nonzero(np.isin(lab, list(torso)).any(1))[0]
    t = ys.min()
    a = rgba.copy()
    a[1:t + 1] = rgba[0:t]
    a[0] = 0
    return a


CUR = None


def build(name):
    global CUR
    CUR = name
    n = NPCS[name]
    PL.MAT = n["mat"]
    PL.MATS = sorted(set(n["mat"].values()))
    raw = {}
    for v in VIEWS:
        cs = cells(name, v)
        P = n["poses"][v]
        if cs is None:
            cs = [np.asarray(with_col(n["col"], BO.frame, P[k])) for k in ORDER[v]]
        fr = {}
        for k in P:
            i = PICK.get((name, v, k), ORDER[v].index(k))
            fr[k] = (cs[i], BO.frame_labels(P[k]))
        raw[v] = fr
    R = pooled(raw, n["col"], n["mat"])
    F = {v: {k: (PL.lock(c, lab, n["col"], R, weighted=True), lab) for k, (c, lab) in fr.items()} for v, fr in raw.items()}
    if "post" in n:
        F = {v: {k: (n["post"](c, lab, R, n["poses"][v][k]), lab) for k, (c, lab) in fr.items()} for v, fr in F.items()}
    sheet = np.zeros((192, 192, 4), np.uint8)
    for vi, v in enumerate(VIEWS):
        idle, lab = F[v]["idle"]
        b = bob(idle, lab, n["torso"])
        for c, f in enumerate([idle, idle, b, b, idle, idle]):
            sheet[32 * vi:32 * vi + 32, 32 * c:32 * c + 32] = f
        order = ["A", "Ah", "P", "B", "Bh", "P2"] if v == "side" else ["A", "idle", "P", "B", "idle", "P"]
        for c, k in enumerate(order):
            sheet[32 * (3 + vi):32 * (4 + vi), 32 * c:32 * c + 32] = F[v][k][0]
    return Image.fromarray(sheet)


ROWS = ["parado frente", "parado lado", "parado costas", "andando frente", "andando lado", "andando costas"]


def main_build():
    sheets = [("fazendeiro", Image.open(OUT / "farmer_Player.png").convert("RGBA").crop((0, 0, 192, 192)))]
    for name in NPCS:
        im = build(name)
        im.save(OUT / f"npc_{name}.png")
        PL.anim_gif(im, 32, [[(0, 6), (1, 6), (2, 6)], [(3, 6), (4, 6), (5, 6)]], OUT / f"npc_{name}.gif")
        sheets.append((name, im))
    PL.preview(sheets, 32, ROWS, OUT / "preview_npcs.png")
    # fila: frente, lado, costas parados + 4 quadros de caminhada, por personagem; 1x em cima, 4x embaixo
    cols = [(0, 0), (1, 0), (2, 0), (3, 0), (4, 0), (4, 3), (5, 0)]
    row = Image.new("RGBA", (32 * len(cols) * len(sheets), 32))
    for i, (sn, sh) in enumerate(sheets):
        for j, (r, c) in enumerate(cols):
            row.alpha_composite(sh.crop((32 * c, 32 * r, 32 * c + 32, 32 * r + 32)), (32 * (i * len(cols) + j), 0))
    big = row.resize((row.width * 4, 128), Image.NEAREST)
    side = Image.new("RGBA", (big.width + 16, 32 + 128 + 40), PL.GRASS)
    side.alpha_composite(row, (8, 8))
    side.alpha_composite(big, (8, 48))
    d = ImageDraw.Draw(side)
    for i, (sn, _) in enumerate(sheets):
        d.text((8 + 4 * 32 * len(cols) * i, 48 + 128 + 2), sn, fill=(0, 0, 0, 255), font=PL.P.font(14))
    # junta a fila lado a lado com a prévia por linha
    pv = Image.open(OUT / "preview_npcs.png").convert("RGBA")
    out = Image.new("RGBA", (max(pv.width, side.width), pv.height + side.height), PL.GRASS)
    out.alpha_composite(side, (0, 0))
    out.alpha_composite(pv, (0, side.height))
    out.save(OUT / "preview_npcs.png")
    print(OUT / "preview_npcs.png")


NPCS["vaqueiro"]["post"] = cowboy_post


if __name__ == "__main__":
    {"bases": bases, "build": main_build}[sys.argv[1]]()
