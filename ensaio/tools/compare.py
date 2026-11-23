"""Folha comparativa: mesmo recorte do mapa original e das variantes.

Uso: python compare.py <out.png> --crop x0,y0,x1,y1 [--scale 2] img1 img2 ...
O rótulo de cada painel é o nome do arquivo sem extensão.
"""
import argparse
from pathlib import Path

from PIL import Image, ImageDraw

ap = argparse.ArgumentParser()
ap.add_argument("out")
ap.add_argument("imgs", nargs="+")
ap.add_argument("--crop", required=True)
ap.add_argument("--scale", type=int, default=2)
ap.add_argument("--cols", type=int, default=2)
a = ap.parse_args()
box = tuple(int(v) for v in a.crop.split(","))
w, h = (box[2] - box[0]) * a.scale, (box[3] - box[1]) * a.scale
rows = (len(a.imgs) + a.cols - 1) // a.cols
sheet = Image.new("RGB", (a.cols * (w + 8) + 8, rows * (h + 30) + 8), (24, 24, 28))
d = ImageDraw.Draw(sheet)
for k, p in enumerate(a.imgs):
    im = Image.open(p).convert("RGBA").crop(box).resize((w, h), Image.NEAREST)
    x, y = 8 + (k % a.cols) * (w + 8), 8 + (k // a.cols) * (h + 30)
    bg = Image.new("RGBA", im.size, (24, 24, 28, 255))
    sheet.paste(Image.alpha_composite(bg, im).convert("RGB"), (x, y + 22))
    d.text((x, y + 4), Path(p).stem, fill=(230, 230, 230))
sheet.save(a.out)
print(a.out, sheet.size)
