#!/usr/bin/env python3
"""Pipeline de objetos: geração de 1024 px -> pixel art no tamanho do jogo.

Passos: remove o fundo (flood fill a partir da borda), recorta no bbox do
objeto, reduz com várias variantes (repixelate, PixelOE, unfake, box),
binariza o alfa, quantiza a paleta, põe contorno opcional e encaixa numa
tela final (ícone centrado ou objeto apoiado no chão com ponto de pé).

Uso:
  pipeline.py icon  a.png b.png --size 32 --out DIR      # ícones 32x32
  pipeline.py ground a.png --fit 32x48 --out DIR         # planta/árvore, pé embaixo
  pipeline.py row st.png --fit 30x64 --variants box --gap 6 --dead  # estágios numa fileira, mesma escala
  pipeline.py grow mature.png --fit 30x64 --fracs 0.35,0.6,1.0     # estágios encolhendo o maduro (pior)
  pipeline.py contact a.png b.png --out folha.png                  # folha de contato das gerações
  pipeline.py ... --variants repix,poe --colors 20 --outline auto --palette items_spritesheet.png
Grava DIR/<nome>.<variante>.png, DIR/<nome>.<variante>.json (anchor) e
DIR/sheet.png (original + variantes em 1x e 4x).
"""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy import ndimage

TMP = Path(os.environ.get("TMPDIR", "/tmp")) / "objpipe"
EXT = Path.home() / ".cache/repixelate-ext"
UNFAKE = EXT / "src/unfake.js/target/release/unfake"
PY_POE = EXT / "venv-poe/bin/python"
ERODE = 3
HOLE_MIN = 300  # px (na geração de 1024) para um vão interno virar transparente
PAL_TOL = 28.0  # distância RGB média por canal acima da qual a cor não vai para a paleta
GRASS = (122, 150, 84, 255)  # fundo das prévias, perto da grama do jogo
POE_CODE = """
import sys, numpy as np, torch
from PIL import Image
from pixeloe.torch.pixelize import pixelize
src, dst, p, mode = sys.argv[1], sys.argv[2], int(sys.argv[3]), sys.argv[4]
img = np.asarray(Image.open(src).convert("RGB"), np.float32) / 255
t = torch.from_numpy(img).permute(2, 0, 1)[None]
out = pixelize(t, pixel_size=p, thickness=0, mode=mode, no_post_upscale=True, backend="torch")
a = (out[0].permute(1, 2, 0).clamp(0, 1).numpy() * 255).round().astype(np.uint8)
Image.fromarray(a).save(dst)
"""


# ---------------------------------------------------------------- fundo e recorte

def bg_color(rgb):
    """Cor de fundo: mediana dos pixels da borda (2 px)."""
    b = np.concatenate([rgb[:2].reshape(-1, 3), rgb[-2:].reshape(-1, 3),
                        rgb[:, :2].reshape(-1, 3), rgb[:, -2:].reshape(-1, 3)])
    return np.median(b, 0)


def remove_bg(rgb, tol=38.0, min_part=0.01):
    """Máscara do objeto: tira o que parece fundo e toca a borda.

    O fundo pode ter gradiente (lilás do sdxl-pad); por isso a distância é
    medida contra a cor de fundo local, estimada por um blur grande da borda.
    Componentes pequenos (< min_part do maior) somem.
    """
    f = rgb.astype(float)
    bg = bg_color(f)
    d = np.sqrt(((f - bg) ** 2).sum(-1))
    like = d < tol
    lab, n = ndimage.label(like)
    border = np.unique(np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]]))
    bgmask = np.isin(lab, border[border > 0])
    fg = ~bgmask
    fg = ndimage.binary_opening(fg, iterations=2)
    fg = ndimage.binary_erosion(fg, iterations=ERODE)  # tira o halo claro do antialias
    lab, n = ndimage.label(fg)
    if n:
        sizes = ndimage.sum(fg, lab, range(1, n + 1))
        keep = [i + 1 for i, s in enumerate(sizes) if s >= min_part * sizes.max()]
        fg = np.isin(lab, keep)
    # buracos: fundo preso entre folhas/galhos (grande e bem perto da cor do fundo)
    hole = (~fg) & (d < tol * 0.6)
    lab, n = ndimage.label(hole)
    if n:
        sizes = ndimage.sum(hole, lab, range(1, n + 1))
        big = [i + 1 for i, s in enumerate(sizes) if s >= HOLE_MIN]
        fg &= ~np.isin(lab, big)
    hole = fg & (d < tol * 0.6)  # o mesmo, para regiões que ainda contam como objeto
    lab, n = ndimage.label(hole)
    if n:
        sizes = ndimage.sum(hole, lab, range(1, n + 1))
        big = [i + 1 for i, s in enumerate(sizes) if s >= HOLE_MIN]
        fg &= ~np.isin(lab, big)
    return fg, bg


def crop(rgb, mask, pad=4):
    ys, xs = np.nonzero(mask)
    y0, y1 = max(ys.min() - pad, 0), min(ys.max() + pad + 1, mask.shape[0])
    x0, x1 = max(xs.min() - pad, 0), min(xs.max() + pad + 1, mask.shape[1])
    return rgb[y0:y1, x0:x1], mask[y0:y1, x0:x1]


def flat_bg(rgb, mask, color=None):
    """Preenche o fundo. Sem cor: estende a cor do pixel do objeto mais perto,
    para que nenhuma redução misture a cor do fundo na borda."""
    out = rgb.copy()
    if color is not None:
        out[~mask] = np.array(color, np.uint8)
        return out
    _, (iy, ix) = ndimage.distance_transform_edt(~mask, return_indices=True)
    return out[iy, ix]


def mask_like(mask, a):
    return down_mask(mask, (a.shape[1], a.shape[0]))


# ---------------------------------------------------------------- redução

def target_scale(mask, box):
    """Fator (px de entrada por px de saída) para caber o bbox em box=(w, h)."""
    ys, xs = np.nonzero(mask)
    h, w = np.ptp(ys) + 1, np.ptp(xs) + 1
    return max(w / box[0], h / box[1])


def down_mask(mask, out_wh):
    m = Image.fromarray((mask * 255).astype(np.uint8)).resize(out_wh, Image.BOX)
    return np.asarray(m) >= 128


def premult_box(rgb, mask, out_wh):
    a = mask.astype(float)
    num = np.stack([np.asarray(Image.fromarray((rgb[..., c] * a).astype(np.float32), "F")
                               .resize(out_wh, Image.BOX)) for c in range(3)], -1)
    den = np.asarray(Image.fromarray(a.astype(np.float32), "F").resize(out_wh, Image.BOX))
    out = num / np.maximum(den, 1e-6)[..., None]
    return np.clip(out, 0, 255).astype(np.uint8), den >= 0.5


def run(cmd):
    r = subprocess.run([str(c) for c in cmd], capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(f"{cmd[0]}: {r.stderr[-400:]}")
    return r.stdout


def v_box(rgb, mask, scale, colors):
    out_wh = (max(1, round(rgb.shape[1] / scale)), max(1, round(rgb.shape[0] / scale)))
    return premult_box(rgb, mask, out_wh)


def v_repix(rgb, mask, scale, colors, blend=0.5):
    """repixelate com --pixel-size = escala alvo (grade imposta, não detectada)."""
    TMP.mkdir(parents=True, exist_ok=True)
    src, dst = TMP / "rp-in.png", TMP / "rp-out.png"
    Image.fromarray(flat_bg(rgb, mask)).save(src)
    run(["repixelate", src, "-o", dst, "--pixel-size", max(2, round(scale)), "--colors", 0,
         "--blend", blend, "--no-bg"])
    a = np.asarray(Image.open(dst).convert("RGB"))
    return a, mask_like(mask, a)


def v_repix2(rgb, mask, scale, colors):
    """Dois passos: repixelate acha a grade nativa (~8 px), depois box até o alvo."""
    TMP.mkdir(parents=True, exist_ok=True)
    src, dst = TMP / "rp2-in.png", TMP / "rp2-out.png"
    Image.fromarray(flat_bg(rgb, mask)).save(src)
    run(["repixelate", src, "-o", dst, "--colors", 0, "--no-bg"])
    a = np.asarray(Image.open(dst).convert("RGB"))
    m = mask_like(mask, a)
    pitch = rgb.shape[1] / a.shape[1]
    rest = scale / pitch
    if rest <= 1.05:
        return a, m
    out_wh = (max(1, round(a.shape[1] / rest)), max(1, round(a.shape[0] / rest)))
    return premult_box(a, m, out_wh)


def v_poe(rgb, mask, scale, colors, mode="contrast"):
    TMP.mkdir(parents=True, exist_ok=True)
    src, dst = TMP / "poe-in.png", TMP / "poe-out.png"
    p = max(2, round(scale))
    # PixelOE corta a imagem em múltiplos do pixel_size; ajusto antes
    h, w = (rgb.shape[0] // p) * p, (rgb.shape[1] // p) * p
    rgb, mask = rgb[:h, :w], mask[:h, :w]
    Image.fromarray(flat_bg(rgb, mask)).save(src)
    run([PY_POE, "-I", "-c", POE_CODE, src, dst, p, mode])
    a = np.asarray(Image.open(dst).convert("RGB"))
    return a, down_mask(mask, (a.shape[1], a.shape[0]))


def v_unfake(rgb, mask, scale, colors):
    TMP.mkdir(parents=True, exist_ok=True)
    src, dst = TMP / "uf-in.png", TMP / "uf-out.png"
    p = max(2, round(scale))
    h, w = (rgb.shape[0] // p) * p, (rgb.shape[1] // p) * p
    rgb, mask = rgb[:h, :w], mask[:h, :w]
    Image.fromarray(flat_bg(rgb, mask)).save(src)
    run([UNFAKE, "downscale", "-s", p, "-m", "dominant", "-o", dst, src])
    a = np.asarray(Image.open(dst).convert("RGB"))
    return a, down_mask(mask, (a.shape[1], a.shape[0]))


VARIANTS = {"box": v_box, "repix": v_repix, "repix2": v_repix2, "poe": v_poe, "unfake": v_unfake}


# ---------------------------------------------------------------- acabamento

def clean_mask(m):
    """Tira pixels soltos (sem vizinho 4-conexo) e fecha furos de 1 px."""
    k = np.array([[0, 1, 0], [1, 0, 1], [0, 1, 0]])
    nb = ndimage.convolve(m.astype(int), k, mode="constant")
    m = m & (nb > 0)
    m = m | ((~m) & (nb >= 4))
    return m


def quantize(rgb, mask, colors):
    if not colors or not mask.any():
        return rgb
    px = rgb[mask]
    img = Image.fromarray(px.reshape(1, -1, 3))
    q = img.quantize(colors=colors, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
    out = rgb.copy()
    out[mask] = np.asarray(q.convert("RGB")).reshape(-1, 3)
    return out


def load_palette(path):
    a = np.asarray(Image.open(path).convert("RGBA"))
    return np.unique(a[a[..., 3] > 128][:, :3], axis=0)


def map_palette(rgb, mask, pal, tol=None):
    """Troca cada cor pela mais próxima da paleta (RGB com pesos 2,4,3).
    Com tol, cores mais longe que tol de toda a paleta ficam como estão
    (a paleta dos itens não tem, por exemplo, amarelo-limão)."""
    if pal is None or not mask.any():
        return rgb
    w = np.array([2.0, 4.0, 3.0])
    cols, inv = np.unique(rgb[mask], axis=0, return_inverse=True)
    d = (((cols[:, None, :].astype(float) - pal[None].astype(float)) ** 2) * w).sum(-1)
    new = pal[d.argmin(1)]
    if tol:
        far = np.sqrt(d.min(1) / w.sum()) > tol
        new[far] = cols[far]
    out = rgb.copy()
    out[mask] = new[inv.ravel()]
    return out


def add_outline(rgb, mask, mode):
    """Contorno de 1 px por fora: 'auto' = cor do vizinho escurecida e puxada
    para roxo-marrom (como os itens do jogo); 'dark' = uma cor só."""
    if mode in (None, "none"):
        return rgb, mask
    ring = ndimage.binary_dilation(mask, structure=np.array([[0, 1, 0], [1, 1, 1], [0, 1, 0]])) & ~mask
    out = rgb.copy()
    dark = np.array([21, 29, 40], float)  # contorno dos itens atuais
    if mode == "dark":
        out[ring] = dark.astype(np.uint8)
    else:
        f = rgb.astype(float)
        acc = np.zeros_like(f)
        cnt = np.zeros(mask.shape)
        for dy, dx in ((0, 1), (0, -1), (1, 0), (-1, 0)):
            sm = np.roll(mask, (dy, dx), (0, 1))
            sf = np.roll(f, (dy, dx), (0, 1))
            acc += sf * sm[..., None]
            cnt += sm
        nbc = acc / np.maximum(cnt, 1)[..., None]
        col = nbc * 0.12 + dark * 0.88
        out[ring] = col[ring].astype(np.uint8)
    return out, mask | ring


def to_rgba(rgb, mask):
    a = np.dstack([rgb, (mask * 255).astype(np.uint8)])
    return Image.fromarray(a, "RGBA")


def place(sprite, size, align):
    """Encaixa o sprite na tela final. align 'center' (ícone) ou 'bottom' (chão)."""
    bb = sprite.getbbox()
    sprite = sprite.crop(bb) if bb else sprite
    W, H = size
    canvas = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    x = (W - sprite.width) // 2
    y = (H - sprite.height) // 2 if align == "center" else H - sprite.height
    canvas.alpha_composite(sprite, (max(x, 0), max(y, 0)))
    return canvas


def anchor(img):
    """Ponto de pé: x médio das 2 linhas opacas mais baixas, y da última linha."""
    a = np.asarray(img)[..., 3] > 0
    ys = np.nonzero(a.any(1))[0]
    if not len(ys):
        return None
    y = ys.max()
    xs = np.nonzero(a[max(y - 1, 0):y + 1].any(0))[0]
    return [int(round(xs.mean())), int(y)]


def prepare(path, tol=38.0, largest=False):
    """Lê a geração, tira o fundo e recorta. largest: só o maior objeto."""
    rgb = np.asarray(Image.open(path).convert("RGB"))
    mask, _ = remove_bg(rgb, tol)
    if largest:
        lab, n = ndimage.label(ndimage.binary_dilation(mask, iterations=6))
        if n > 1:
            sizes = ndimage.sum(mask, lab, range(1, n + 1))
            mask = mask & (lab == 1 + int(np.argmax(sizes)))
    return crop(rgb, mask)


def render(rgb, mask, scale, variant, colors, outline, pal=None, lim=None):
    """Reduz por `scale` e faz o acabamento. Devolve RGBA recortado no bbox."""
    small, m = VARIANTS[variant](rgb, mask, scale, colors)
    m = clean_mask(m)
    small = quantize(small, m, colors)
    small, m = add_outline(small, m, outline)
    small = map_palette(small, m, pal, PAL_TOL)
    img = to_rgba(small, m)
    bb = img.getbbox()
    if bb:
        img = img.crop(bb)
        # se passou do limite (arredondamento), reduz com nearest
        if lim and (img.width > lim[0] or img.height > lim[1]):
            f = min(lim[0] / img.width, lim[1] / img.height)
            img = img.resize((max(1, int(img.width * f)), max(1, int(img.height * f))), Image.NEAREST)
    return img


def meta_of(out, align, scale):
    a = np.asarray(out)
    return {"anchor": anchor(out) if align == "bottom" else None, "scale": round(scale, 2),
            "colors": len({tuple(c) for c in a[a[..., 3] > 0][:, :3].tolist()})}


def process(path, variant, box, canvas, align, colors, outline, tol=38.0, pal=None, largest=False):
    rgb, mask = prepare(path, tol, largest)
    scale = target_scale(mask, box)
    extra = 0 if outline in (None, "none") else 2
    img = render(rgb, mask, scale, variant, colors, outline, pal, (box[0] + extra, box[1] + extra))
    out = place(img, canvas, align)
    return out, meta_of(out, align, scale)


def split_row(mask, min_gap=12, band=0.12, expect=0):
    """Divide uma geração com vários estágios em fatias de colunas (x0, x1).

    As bases (faixa de baixo, `band` da altura) ficam separadas mesmo quando
    as folhas de cima se tocam; o corte entre duas bases vizinhas é a coluna
    com menos pixels do objeto entre elas."""
    ys = np.nonzero(mask.any(1))[0]
    y1 = ys.max() + 1
    h = y1 - ys.min()
    low = mask[max(y1 - int(h * band), 0):y1].any(0)
    segs, x, W = [], 0, len(low)
    while x < W:
        if not low[x]:
            x += 1
            continue
        x0 = x
        gap = 0
        while x < W and gap < min_gap:
            gap = gap + 1 if not low[x] else 0
            x += 1
        segs.append((x0, x - gap))
    segs = [sg for sg in segs if sg[1] - sg[0] > 4]
    if not segs:
        return []
    count = mask.sum(0)
    # menos estágios que o pedido no prompt: supõe estágios igualmente espaçados
    # e corta perto de cada divisa esperada, na coluna mais vazia (+-8% da largura)
    if expect and len(segs) < expect:
        x0, x1 = segs[0][0], segs[-1][1]
        step = (x1 - x0) / expect
        cuts = [0]
        for k in range(1, expect):
            t = int(x0 + k * step)
            r = int(step * 0.4)
            cuts.append(t - r + int(np.argmin(count[t - r:t + r])))
        cuts.append(W)
        out = []
        for c0, c1 in zip(cuts, cuts[1:]):
            xs = np.nonzero(mask[:, c0:c1].any(0))[0]
            if len(xs):
                out.append((c0 + xs.min(), c0 + xs.max() + 1))
        return out
    cuts = [0]
    for (_, e0), (s1, _) in zip(segs, segs[1:]):
        cuts.append(e0 + int(np.argmin(count[e0:s1])))
    cuts.append(W)
    out = []
    for c0, c1 in zip(cuts, cuts[1:]):
        xs = np.nonzero(mask[:, c0:c1].any(0))[0]
        if len(xs):
            out.append((c0 + xs.min(), c0 + xs.max() + 1))
    return out


def strip_soil(rgb, mask, band=0.12):
    """Apaga a terra marrom na base (o tile arado já é a terra)."""
    ys = np.nonzero(mask.any(1))[0]
    y0 = ys.max() + 1 - max(int((ys.max() - ys.min()) * band), 24)
    f = rgb.astype(int)
    r, g, b = f[..., 0], f[..., 1], f[..., 2]
    brown = (r > g + 8) & (g >= b - 10)
    m = mask.copy()
    m[y0:] &= ~brown[y0:]
    m = ndimage.binary_opening(m, iterations=2)
    return m


def stages_from_row(path, variant, box, canvas, colors, outline, tol, pal, min_gap=12, nosoil=False, expect=0):
    """Estágios lado a lado numa geração -> sprites com a MESMA escala
    (a do estágio que exige mais redução), apoiados no chão."""
    rgb, mask = prepare(path, tol)
    out = []
    parts = []
    for x0, x1 in split_row(mask, min_gap, expect=expect):
        m = mask[:, x0:x1]
        ys = np.nonzero(m.any(1))[0]
        r, m = rgb[ys.min():ys.max() + 1, x0:x1], m[ys.min():ys.max() + 1]
        if nosoil:
            m = strip_soil(r, m)
            ys = np.nonzero(m.any(1))[0]
            xs = np.nonzero(m.any(0))[0]
            r, m = r[ys.min():ys.max() + 1, xs.min():xs.max() + 1], m[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
        parts.append((r, m))
    if not parts:
        return out
    scale = max(target_scale(m, box) for _, m in parts)
    for r, m in parts:
        img = render(r, m, scale, variant, colors, outline, pal)
        o = place(img, canvas, "bottom")
        out.append((o, meta_of(o, "bottom", scale)))
    return out


def stages_from_one(path, variant, box, canvas, colors, outline, tol, pal, fracs):
    """Um sprite maduro -> estágios menores reduzindo o mesmo desenho
    (fração da altura final em `fracs`)."""
    rgb, mask = prepare(path, tol, largest=True)
    base = target_scale(mask, box)
    out = []
    for f in fracs:
        img = render(rgb, mask, base / f, variant, colors, outline, pal)
        o = place(img, canvas, "bottom")
        out.append((o, meta_of(o, "bottom", base / f)))
    return out


def wither(img, pal=None):
    """Estágio morto: puxa as cores para marrom-palha mantendo a luminância."""
    a = np.asarray(img).astype(float)
    lum = (a[..., :3] * [0.3, 0.55, 0.15]).sum(-1, keepdims=True) / 255
    dark, light = np.array([70, 45, 35.0]), np.array([196, 150, 96.0])
    a[..., :3] = dark + (light - dark) * np.clip(lum * 1.4, 0, 1)
    return Image.fromarray(a.astype(np.uint8), "RGBA")


def strip(ims, path, zoom=4, bg=GRASS, gap=4):
    """Fileira de sprites (1x embaixo, zoom em cima) com o pé marcado."""
    W = sum(i.width for i in ims) * zoom + gap * zoom * len(ims)
    H = max(i.height for i in ims) * (zoom + 1) + 8
    s = Image.new("RGBA", (W, H), bg)
    x = 0
    for im in ims:
        s.alpha_composite(im.resize((im.width * zoom, im.height * zoom), Image.NEAREST), (x, 0))
        s.alpha_composite(im, (x, max(i.height for i in ims) * zoom + 6))
        x += (im.width + gap) * zoom
    s.save(path)


# ---------------------------------------------------------------- prévias

def font(size=12):
    try:
        return ImageFont.truetype("/usr/share/fonts/TTF/DejaVuSansCondensed.ttf", size)
    except OSError:
        return ImageFont.load_default()


def sheet(rows, cols, path, zoom=4, thumb=128, bg=GRASS):
    """rows: [(nome, original_path, [img por coluna])]. Cada célula: 1x e zoom x."""
    if not rows:
        return
    cw = max(max((im.width for _, _, ims in rows for im in ims if im), default=32) * (zoom + 1) + 12, thumb + 8)
    ch = max(max((im.height for _, _, ims in rows for im in ims if im), default=32) * zoom + 4, thumb) + 18
    W = (len(cols) + 1) * cw
    H = 20 + len(rows) * ch
    s = Image.new("RGBA", (W, H), (40, 36, 44, 255))
    d = ImageDraw.Draw(s)
    f = font(12)
    for i, c in enumerate(["original"] + cols):
        d.text((i * cw + 4, 3), c, fill=(230, 230, 230), font=f)
    for r, (name, orig, ims) in enumerate(rows):
        y = 20 + r * ch
        d.text((4, y + ch - 16), name[:22], fill=(230, 230, 230), font=f)
        o = Image.open(orig).convert("RGBA")
        o.thumbnail((thumb, thumb))
        s.alpha_composite(o, (4, y))
        for i, im in enumerate(ims):
            if im is None:
                continue
            x = (i + 1) * cw
            cell = Image.new("RGBA", (cw - 6, ch - 4), bg)
            big = im.resize((im.width * zoom, im.height * zoom), Image.NEAREST)
            cell.alpha_composite(im, (2, 2))
            cell.alpha_composite(big, (im.width + 8, 2))
            s.alpha_composite(cell, (x, y))
    s.save(path)


def contact(paths, out, cell=256, cols=4):
    """Folha de contato das gerações (miniaturas com nome)."""
    rows = (len(paths) + cols - 1) // cols
    s = Image.new("RGB", (cols * cell, rows * (cell + 14)), (40, 36, 44))
    d = ImageDraw.Draw(s)
    for i, p in enumerate(paths):
        im = Image.open(p).convert("RGB")
        im.thumbnail((cell, cell))
        x, y = (i % cols) * cell, (i // cols) * (cell + 14)
        s.paste(im, (x, y))
        d.text((x + 2, y + cell), Path(p).stem[:40], fill=(230, 230, 230), font=font(11))
    s.save(out)


def main():
    if sys.argv[1] == "contact":
        ap = argparse.ArgumentParser()
        ap.add_argument("kind")
        ap.add_argument("inputs", nargs="+")
        ap.add_argument("--out", required=True)
        ap.add_argument("--cell", type=int, default=256)
        ap.add_argument("--cols", type=int, default=4)
        a = ap.parse_args()
        return contact(a.inputs, a.out, a.cell, a.cols)
    ap = argparse.ArgumentParser()
    ap.add_argument("kind", choices=["icon", "ground", "row", "grow"])
    ap.add_argument("inputs", nargs="+")
    ap.add_argument("--out", required=True)
    ap.add_argument("--size", type=int, default=32, help="ícone: lado da tela")
    ap.add_argument("--box", type=int, default=28, help="ícone: lado máximo do objeto sem contorno")
    ap.add_argument("--fit", default="32x64", help="ground: WxH máximo do objeto")
    ap.add_argument("--canvas", default=None, help="ground: WxH da tela (padrão = fit)")
    ap.add_argument("--variants", default="box,repix,repix2,poe,unfake")
    ap.add_argument("--colors", type=int, default=20)
    ap.add_argument("--outline", default="auto", help="none, auto, dark, ou lista: none,auto")
    ap.add_argument("--tol", type=float, default=38.0)
    ap.add_argument("--sheet", default="sheet.png")
    ap.add_argument("--palette", default=None, help="PNG cujas cores viram a paleta (ex.: items_spritesheet.png)")
    ap.add_argument("--palette-tol", type=float, default=28.0, help="0 = força tudo na paleta")
    ap.add_argument("--hole", type=int, default=None, help="área mínima (px) de vão interno a apagar; padrão 300, 80 em row/grow")
    ap.add_argument("--largest", action="store_true", help="só o maior objeto da geração")
    ap.add_argument("--fracs", default="0.35,0.6,0.8,1.0", help="grow: alturas relativas dos estágios")
    ap.add_argument("--dead", action="store_true", help="row/grow: acrescenta estágio seco")
    ap.add_argument("--gap", type=int, default=12, help="row: vão mínimo entre estágios (px)")
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    if a.kind == "icon":
        box, canvas, align = (a.box, a.box), (a.size, a.size), "center"
    else:
        box = tuple(int(v) for v in a.fit.split("x"))
        canvas = tuple(int(v) for v in (a.canvas or a.fit).split("x"))
        align = "bottom"
    pal = load_palette(a.palette) if a.palette else None
    global PAL_TOL
    PAL_TOL = a.palette_tol
    global HOLE_MIN
    HOLE_MIN = a.hole if a.hole is not None else (80 if a.kind in ("row", "grow") else 300)
    if a.kind in ("row", "grow"):
        v, o = a.variants.split(",")[0], a.outline.split(",")[0]
        for p in a.inputs:
            name = Path(p).stem
            if a.kind == "row":
                res = stages_from_row(p, v, box, canvas, a.colors, o, a.tol, pal, a.gap)
            else:
                fr = [float(f) for f in a.fracs.split(",")]
                res = stages_from_one(p, v, box, canvas, a.colors, o, a.tol, pal, fr)
            if a.dead and res:
                res.append((wither(res[-1][0]), res[-1][1]))
            for i, (im, meta) in enumerate(res):
                im.save(out / f"{name}.s{i}.png")
                (out / f"{name}.s{i}.json").write_text(json.dumps(meta))
            if res:
                strip([r[0] for r in res], out / f"{name}.strip.png")
            print(name, len(res), "estágios", flush=True)
        return
    combos = [(v, o) for v in a.variants.split(",") for o in a.outline.split(",")]
    cols = [f"{v}/{o}" for v, o in combos]
    rows = []
    for p in a.inputs:
        name = Path(p).stem
        ims = []
        for v, o in combos:
            try:
                im, meta = process(p, v, box, canvas, align, a.colors, o, a.tol, pal, a.largest)
            except Exception as e:  # noqa: BLE001 - prévia segue com as outras
                print(name, v, "falhou:", e, file=sys.stderr)
                ims.append(None)
                continue
            tag = f"{v}" + ("" if o == "none" else f"-{o}")
            im.save(out / f"{name}.{tag}.png")
            (out / f"{name}.{tag}.json").write_text(json.dumps(meta))
            ims.append(im)
        rows.append((name, p, ims))
        print(name, "ok", flush=True)
    sheet(rows, cols, out / a.sheet)


if __name__ == "__main__":
    main()
