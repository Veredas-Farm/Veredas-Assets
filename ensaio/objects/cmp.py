"""Compara ícones novos com os itens atuais do jogo, em 1x e 6x, sobre a grama.
Uso: cmp.py OUT.png icon1.png icon2.png ..."""
import sys
from PIL import Image
from pipeline import GRASS
ref = Image.open('/home/chips/git/games/Veredas-Assets/items_spritesheet.png').convert('RGBA')
refs = [ref.crop((c*32, r*32, c*32+32, r*32+32)) for r, c in ((0, 0), (1, 4), (2, 0), (2, 4))]
ims = refs + [Image.open(p).convert('RGBA') for p in sys.argv[2:]]
z = int(__import__('os').environ.get('Z', 5))
W = len(ims) * (32 * z + 4)
s = Image.new('RGBA', (W, 32 * z + 40), GRASS)
for i, im in enumerate(ims):
    s.alpha_composite(im.resize((32 * z, 32 * z), Image.NEAREST), (i * (32 * z + 4), 0))
    s.alpha_composite(im, (i * (32 * z + 4), 32 * z + 4))
s.save(sys.argv[1])
