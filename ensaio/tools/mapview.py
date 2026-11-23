#!/usr/bin/env python3
"""Renderiza o mapa estático do Veredas Farm (cena Godot 4) para PNG.

Lê o .tscn direto (sem Godot): TileMapLayer, TileSet (atlas, texture_origin),
Sprite2D de objetos instanciados, z_index e y_sort. Serve para comparar o
atlas atual com atlas candidatos (`--atlas-override`).

Subcomandos:
  render  desenha o mapa em PNG
  stats   conta o uso de cada célula de atlas por camada + limites do mapa

Limites conhecidos (ver `--help`): a flora (árvores, pedras, arbustos) é
gerada aleatoriamente em runtime por gerador_mapa.gd e NÃO é desenhada; o
jogador, a UI e o ciclo dia/noite também ficam de fora.
"""
import argparse
import base64
import collections
import math
import re
import struct
import sys
from pathlib import Path

from PIL import Image

GAME = Path("/home/chips/git/games/Veredas-Farm")
ASSETS = Path("/home/chips/git/games/Veredas-Assets")
DEFAULT_SCENE = "scenes/mundo/jogo.tscn"

# ---------------------------------------------------------------- parser .tscn

_ATTR = re.compile(r'(\w+)=(\w+\([^)]*\)|"(?:[^"\\]|\\.)*"|[^\s\]]+)')
_NUM = r"-?\d+(?:\.\d+)?(?:e-?\d+)?"


def parse_value(s):
    s = s.strip()
    if s.startswith('"') and s.endswith('"'):
        return s[1:-1]
    if s.startswith('&"'):
        return s[2:-1]
    if s in ("true", "false"):
        return s == "true"
    m = re.fullmatch(r'(ExtResource|SubResource)\("([^"]*)"\)', s)
    if m:
        return (m.group(1), m.group(2))
    m = re.fullmatch(r"(Vector2i?|Rect2i?|Color)\((.*)\)", s)
    if m:
        return tuple(float(v) for v in re.findall(_NUM, m.group(2)))
    if re.fullmatch(_NUM, s):
        f = float(s)
        return int(f) if re.fullmatch(r"-?\d+", s) else f
    return s  # PackedByteArray etc.: valor cru


class Scene:
    def __init__(self, path):
        self.path = Path(path)
        self.ext = {}   # id -> (type, res path)
        self.sub = {}   # id -> {"type":..., props}
        self.nodes = []  # dicts name,type,parent,instance,props
        self._parse(self.path.read_text())

    def _parse(self, text):
        cur = None
        for line in text.splitlines():
            if line.startswith("["):
                attrs = {k: parse_value(v) for k, v in _ATTR.findall(line)}
                kind = re.match(r"\[(\w+)", line).group(1)
                if kind == "ext_resource":
                    self.ext[attrs["id"]] = (attrs.get("type"), attrs["path"])
                    cur = None
                elif kind == "sub_resource":
                    cur = {"type": attrs["type"]}
                    self.sub[attrs["id"]] = cur
                elif kind == "node":
                    cur = {"name": attrs["name"], "type": attrs.get("type"),
                           "parent": attrs.get("parent"),
                           "instance": attrs.get("instance"), "props": {}}
                    self.nodes.append(cur)
                else:
                    cur = None
            elif cur is not None and " = " in line:
                k, v = line.split(" = ", 1)
                (cur["props"] if "props" in cur else cur)[k.strip()] = parse_value(v)


# ----------------------------------------------------------------- recursos

class Resolver:
    """Mapeia res://assets/... para arquivos locais, com overrides."""

    def __init__(self, overrides):
        self.overrides = {}
        for o in overrides or []:
            k, _, v = o.partition("=")
            self.overrides[k.strip()] = Path(v.strip())
        self.cache = {}
        self.missing = set()
        self.used = set()

    def path_for(self, res):
        if res in self.overrides:
            return self.overrides[res]
        rel = res[len("res://"):]
        cands = [GAME / rel]
        if rel.startswith("assets/"):
            sub = rel[len("assets/"):]
            cands += [GAME / "old_assets" / sub, ASSETS / sub,
                      ASSETS / Path(sub).name]
        for c in cands:
            if c.exists():
                return c
        return None

    def image(self, res):
        if res in self.cache:
            return self.cache[res]
        p = self.path_for(res)
        im = None
        if p is None:
            self.missing.add(res)
        else:
            self.used.add((res, str(p)))
            im = Image.open(p).convert("RGBA")
        self.cache[res] = im
        return im


class Tex:
    """Textura (ou região de atlas) já resolvida para uma imagem RGBA."""

    def __init__(self, img):
        self.img = img


def load_texture(scene, value, resolver):
    if not isinstance(value, tuple):
        return None
    kind, ident = value
    if kind == "ExtResource":
        return resolver.image(scene.ext[ident][1])
    sub = scene.sub[ident]
    if sub["type"] == "AtlasTexture":
        base = load_texture(scene, sub.get("atlas"), resolver)
        if base is None:
            return None
        r = sub.get("region")
        if r:
            x, y, w, h = (int(v) for v in r)
            return base.crop((x, y, x + w, y + h))
        return base
    return None


# ------------------------------------------------------------------- TileSet

class TileSet:
    def __init__(self, scene, sub, resolver):
        self.shape = int(sub.get("tile_shape", 0))
        self.layout = int(sub.get("tile_layout", 0))
        self.tile_size = tuple(int(v) for v in sub.get("tile_size", (16, 16)))
        self.sources = {}
        for k, v in sub.items():
            m = re.fullmatch(r"sources/(\d+)", k)
            if m:
                self.sources[int(m.group(1))] = Source(
                    scene, scene.sub[v[1]], resolver, v[1])

    def map_to_local(self, x, y):
        w, h = self.tile_size
        if self.shape == 1 and self.layout == 5:  # DIAMOND_DOWN
            return (w / 2 + (x - y) * w / 2, h / 2 + (x + y) * h / 2)
        if self.shape == 0:  # quadrado
            return (x * w + w / 2, y * h + h / 2)
        raise NotImplementedError(f"tile_shape={self.shape} layout={self.layout}")


class Source:
    def __init__(self, scene, sub, resolver, ident):
        self.id = ident
        self.name = sub.get("resource_name", ident)
        self.region = tuple(int(v) for v in sub.get("texture_region_size", (16, 16)))
        self.tex_ref = sub.get("texture")
        self.res = (scene.ext[self.tex_ref[1]][1]
                    if isinstance(self.tex_ref, tuple) and self.tex_ref[0] == "ExtResource"
                    else None)
        if self.res:  # a branch de teste do jogo aponta para old_assets
            self.res = self.res.replace("res://old_assets/", "res://assets/")
        self.img = load_texture(scene, self.tex_ref, resolver)
        self.origin = {}
        self.tiles = set()
        for k, v in sub.items():
            m = re.fullmatch(r"(\d+):(\d+)/(\d+)(?:/(\w+))?", k)
            if not m:
                continue
            c = (int(m.group(1)), int(m.group(2)))
            self.tiles.add(c)
            if m.group(4) == "texture_origin":
                self.origin[c] = (int(v[0]), int(v[1]))
        self._crops = {}

    def crop(self, ax, ay, alt=0):
        key = (ax, ay, alt)
        if key in self._crops:
            return self._crops[key]
        w, h = self.region
        im = None
        if self.img is not None:
            im = self.img.crop((ax * w, ay * h, ax * w + w, ay * h + h))
            if alt & (1 << 14):  # transpose
                im = im.transpose(Image.TRANSPOSE)
            if alt & (1 << 12):
                im = im.transpose(Image.FLIP_LEFT_RIGHT)
            if alt & (1 << 13):
                im = im.transpose(Image.FLIP_TOP_BOTTOM)
        self._crops[key] = im
        return im


def decode_cells(raw):
    """PackedByteArray(base64) -> [(x, y, source, ax, ay, alt)] (Godot 4, 12 B/célula)."""
    if isinstance(raw, tuple) or not isinstance(raw, str):
        return []
    m = re.fullmatch(r'PackedByteArray\("([^"]*)"\)', raw)
    if m:
        data = base64.b64decode(m.group(1))
    else:
        m = re.fullmatch(r"PackedByteArray\(([\d,\s]*)\)", raw)
        data = bytes(int(v) for v in m.group(1).split(",")) if m and m.group(1).strip() else b""
    if not data:
        return []
    if (len(data) - 2) % 12:
        raise ValueError("tile_map_data com tamanho inesperado")
    out = []
    for i in range(2, len(data), 12):
        out.append(struct.unpack_from("<hhHHHH", data, i))
    return out


# -------------------------------------------------------------- árvore de nós

class Node:
    def __init__(self, name, type_, props, scene):
        self.name, self.type, self.props, self.scene = name, type_, dict(props), scene
        self.children = []

    def get(self, k, d=None):
        return self.props.get(k, d)

    @property
    def pos(self):
        v = self.get("position", (0, 0))
        return v[0], v[1]


def build_tree(scene, resolver, _stack=()):
    """Monta a árvore de nós, expandindo cenas instanciadas."""
    root = None
    index = {}  # caminho -> Node
    for n in scene.nodes:
        if n["parent"] is None:
            node = Node(n["name"], n["type"], n["props"], scene)
            root, index["."] = node, node
            continue
        parent = index[n["parent"]]
        path = n["name"] if n["parent"] == "." else f'{n["parent"]}/{n["name"]}'
        if n["instance"]:
            sub_path = GAME / scene.ext[n["instance"][1]][1][len("res://"):]
            if not sub_path.exists():
                resolver.missing.add(f"(cena) {scene.ext[n['instance'][1]][1]}")
                continue
            sub = Scene(sub_path)
            node = build_tree(sub, resolver)
            node.name = n["name"]
            node.props.update(n["props"])
        elif n["type"] is None:  # override de nó herdado
            if path in index:
                index[path].props.update(n["props"])
            continue
        else:
            node = Node(n["name"], n["type"], n["props"], scene)
        parent.children.append(node)
        index[path] = node
        for sub_path, sub_node in _walk(node, path):
            index[sub_path] = sub_node
    return root


def _walk(node, path):
    for c in node.children:
        p = f"{path}/{c.name}"
        yield p, c
        yield from _walk(c, p)


# ------------------------------------------------------------------- desenho

Layer = collections.namedtuple("Layer", "path node tileset cells offset")


class Cmd:
    __slots__ = ("img", "x", "y", "mod", "layer")

    def __init__(self, img, x, y, mod=(1, 1, 1, 1), layer=""):
        self.img, self.x, self.y, self.mod, self.layer = img, x, y, mod, layer


class Renderer:
    def __init__(self, scene, resolver, objects=True):
        self.scene, self.res, self.objects = scene, resolver, objects
        self.tilesets = {}
        self.layers = []   # [Layer]: path, node, tileset, cells, offset
        self.sprites = []  # [Cmd] de cada Sprite2D (objetos/estruturas), sem ordenar
        self.warnings = set()
        self.object_count = collections.Counter()
        # ganchos da API (preenchidos por render())
        self.tile_fn = None
        self.extra_cells = {}
        self.extra_objects = []
        self.uniform_origin = None
        self.root = build_tree(scene, resolver)
        self.scan(self.root, 0, 0, self.root.name)

    def scan(self, node, ox, oy, path):
        """Percorre a árvore uma vez: registra camadas de tiles e Sprite2D."""
        if node.get("visible", True) is False:
            return
        if node.type == "TileMapLayer":
            ts = self.tileset_of(node)
            if ts is not None:
                self.layers.append(Layer(path, node, ts,
                                         decode_cells(node.get("tile_map_data")),
                                         (ox, oy)))
        elif node.type == "Sprite2D":
            c = self.sprite_cmd(node, ox, oy, path)
            if c:
                self.sprites.append(c)
                self.object_count[path.rsplit("/", 1)[0]] += 1
        for ch in node.children:
            cx, cy = ch.pos
            self.scan(ch, ox + cx, oy + cy, f"{path}/{ch.name}")

    def layer(self, name):
        """Camada pelo caminho completo ou pelo último segmento."""
        for L in self.layers:
            if L.path == name or L.path.rsplit("/", 1)[-1] == name:
                return L
        raise KeyError(name)

    def tileset_of(self, node):
        ref = node.get("tile_set")
        if not ref:
            return None
        if ref[1] not in self.tilesets:
            self.tilesets[ref[1]] = TileSet(node.scene, node.scene.sub[ref[1]], self.res)
        return self.tilesets[ref[1]]

    # --- comandos próprios de um nó (sem filhos)
    def own_items(self, node, ox, oy, path):
        """Devolve lista de (ykey, [Cmd]) do que o nó desenha por si só."""
        if node.get("visible", True) is False:
            return []
        if node.type == "Sprite2D" and self.objects:
            c = self.sprite_cmd(node, ox, oy, path)
            return [(oy, [c])] if c else []
        if node.type == "TileMapLayer":
            return self.tile_items(node, ox, oy, path)
        return []

    def sprite_cmd(self, node, ox, oy, path):
        tex = load_texture(node.scene, node.get("texture"), self.res)
        if tex is None:
            return None
        if node.get("scale") or node.get("rotation") or node.get("flip_h") or node.get("flip_v"):
            self.warnings.add(f"{path}: escala/rotação/flip ignorados")
        if node.get("region_enabled"):
            x, y, w, h = node.get("region_rect")
            ix, iy = round(x), round(y)
            iw, ih = round(w), round(h)  # frações do Godot: arredondado
            tex = tex.crop((ix, iy, ix + iw, iy + ih))
        w, h = tex.size
        ofs = node.get("offset", (0, 0))
        px, py = ox + ofs[0], oy + ofs[1]
        if node.get("centered", True):
            px, py = px - w / 2, py - h / 2
        return Cmd(tex, round(px), round(py), self.mod_of(node), path)

    def mod_of(self, node):
        m = node.get("modulate")
        return tuple(m) if m else (1, 1, 1, 1)

    def tile_items(self, node, ox, oy, path):
        L = next((l for l in self.layers if l.path == path), None)
        if L is None:
            return []
        ts, cells = L.tileset, L.cells
        extra = {}
        for k, v in self.extra_cells.items():
            if k == path or k == path.rsplit("/", 1)[-1]:
                extra.update(v)
        mod = self.mod_of(node)
        uo = tuple(self.uniform_origin) if self.uniform_origin else (0, 0)
        items = []

        def add(im, x, y, org, w, h):
            lx, ly = ts.map_to_local(x, y)
            px = ox + lx - w / 2 - org[0]
            py = oy + ly - h / 2 - org[1]
            items.append((oy + ly, lx, [Cmd(im, round(px), round(py), mod, path)]))

        for (x, y, src, ax, ay, alt) in cells:
            if (x, y) in extra:
                continue
            s = ts.sources.get(src)
            if s is None:
                continue
            rep_im = (self.tile_fn(path, x, y, s.res, ax, ay)
                      if self.tile_fn else None)
            if rep_im is not None:
                add(rep_im.convert("RGBA"), x, y, uo, *rep_im.size)
                continue
            im = s.crop(ax, ay, alt)
            if im is None:
                continue
            org = UNIFORM_ORIGIN.get(s.res) or s.origin.get((ax, ay), (0, 0))
            add(im, x, y, org, *s.region)
        for (x, y), im in extra.items():
            add(im.convert("RGBA"), x, y, uo, *im.size)
        if node.get("y_sort_enabled"):
            return [(k, c) for k, _, c in items]
        items.sort(key=lambda t: (t[0], t[1]))  # y de tela e depois x
        return [(None, c) for _, _, c in items]

    # --- ordem de desenho
    def unit(self, node, ox, oy, z, path):
        """Comandos (z, Cmd) de um nó e subárvore, na ordem de desenho."""
        out = []
        if node.get("visible", True) is False:
            return out
        if node.get("y_sort_enabled"):
            items = []
            self.gather(node, ox, oy, z, path, items, own=True)
            if node is self.root:
                for e in self.extra_objects:
                    im, fx, fy = e[:3]
                    key = e[3] if len(e) > 3 else fy  # 4º campo opcional: chave do y-sort
                    im = im.convert("RGBA")
                    c = Cmd(im, round(fx - im.width / 2), round(fy - im.height), layer="extra")
                    items.append((key, [(z, c)]))
            items.sort(key=lambda t: t[0])  # estável: empate = ordem da árvore
            for _, cmds in items:
                out.extend(cmds)
            return out
        for _, cmds in self.own_items(node, ox, oy, path):
            out.extend((z, c) for c in cmds)
        for ch in node.children:
            cx, cy = ch.pos
            out.extend(self.unit(ch, ox + cx, oy + cy, z + int(ch.get("z_index", 0)),
                                 f"{path}/{ch.name}"))
        return out

    def gather(self, node, ox, oy, z, path, items, own):
        """Coleta itens do grupo y-sort de `node` (filhos y-sort são achatados)."""
        if node.get("visible", True) is False:
            return
        if own:
            for k, cmds in self.own_items(node, ox, oy, path):
                items.append((oy if k is None else k, [(z, c) for c in cmds]))
        for ch in node.children:
            cx, cy = ch.pos
            cz = z + int(ch.get("z_index", 0))
            cpath = f"{path}/{ch.name}"
            if ch.get("y_sort_enabled"):
                self.gather(ch, ox + cx, oy + cy, cz, cpath, items, own=True)
            else:
                cmds = self.unit(ch, ox + cx, oy + cy, cz, cpath)
                if cmds:
                    items.append((oy + cy, cmds))

    def commands(self):
        cmds = self.unit(self.root, 0, 0, 0, self.root.name)
        if not self.root.get("y_sort_enabled"):
            for e in self.extra_objects:
                im, fx, fy = e[:3]
                im = im.convert("RGBA")
                cmds.append((0, Cmd(im, round(fx - im.width / 2), round(fy - im.height))))
        cmds = sorted(cmds, key=lambda t: t[0])  # estável por z
        return [c for _, c in cmds]


def tint(img, mod):
    if mod == (1, 1, 1, 1):
        return img
    r, g, b, a = (int(v * 255) for v in (list(mod) + [1, 1, 1, 1])[:4])
    ov = Image.new("RGBA", img.size, (r, g, b, a))
    from PIL import ImageChops
    return ImageChops.multiply(img, ov)


def bounds_of(cmds):
    x0 = min(c.x for c in cmds)
    y0 = min(c.y for c in cmds)
    x1 = max(c.x + c.img.width for c in cmds)
    y1 = max(c.y + c.img.height for c in cmds)
    return x0, y0, x1, y1


def draw(cmds, box):
    x0, y0, x1, y1 = box
    canvas = Image.new("RGBA", (x1 - x0, y1 - y0), (0, 0, 0, 0))
    for c in cmds:
        dx, dy = c.x - x0, c.y - y0
        w, h = c.img.size
        if dx >= canvas.width or dy >= canvas.height or dx + w <= 0 or dy + h <= 0:
            continue
        sx, sy = max(0, -dx), max(0, -dy)
        canvas.alpha_composite(tint(c.img, c.mod), (max(dx, 0), max(dy, 0)), (sx, sy))
    return canvas


# ----------------------------------------------------------------------- CLI

def _load_cli(args):
    resolver = Resolver(getattr(args, "atlas_override", None))
    scene = Scene(GAME / args.scene)
    return Renderer(scene, resolver, objects=not getattr(args, "no_objects", False)), resolver


def report_missing(resolver):
    if resolver.missing:
        print("Assets ausentes:", file=sys.stderr)
        for m in sorted(resolver.missing):
            print(f"  {m}", file=sys.stderr)


def cmd_render(args):
    r, resolver = _load_cli(args)
    cmds = r.commands()
    if not cmds:
        sys.exit("nada para desenhar")
    for o, p in resolver.overrides.items():
        if not p.exists():
            sys.exit(f"override inexistente: {p}")
        orig = Resolver([]).path_for(o)
        if orig and Image.open(orig).size != Image.open(p).size:
            print(f"aviso: {o}: tamanho {Image.open(p).size} difere do original "
                  f"{Image.open(orig).size}", file=sys.stderr)
    box = bounds_of(cmds)
    print(f"limites do mundo (px): {box}", file=sys.stderr)
    if args.crop:
        box = tuple(int(v) for v in args.crop.split(","))
    img = draw(cmds, box)
    if args.scale != 1:
        img = img.resize((img.width * args.scale, img.height * args.scale), Image.NEAREST)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    img.save(args.out)
    print(f"{args.out}: {img.size[0]}x{img.size[1]} (origem do mundo em {box[0]},{box[1]})")
    for w in sorted(r.warnings):
        print("aviso:", w, file=sys.stderr)
    report_missing(resolver)


def cmd_stats(args):
    r, resolver = _load_cli(args)
    r.commands()
    for path, node, ts, cells, (ox, oy) in r.layers:
        print(f"\n== {path}  ({len(cells)} células, pos=({ox},{oy}), "
              f"z={node.get('z_index', 0)}, y_sort={bool(node.get('y_sort_enabled'))}, "
              f"shape={ts.shape}/layout={ts.layout})")
        if not cells:
            continue
        xs = [c[0] for c in cells]
        ys = [c[1] for c in cells]
        print(f"   limites de célula: x {min(xs)}..{max(xs)}, y {min(ys)}..{max(ys)}")
        cnt = collections.Counter((c[2], c[3], c[4], c[5]) for c in cells)
        for (s, ax, ay, alt), n in sorted(cnt.items(), key=lambda t: -t[1]):
            src = ts.sources.get(s)
            nm = Path(src.res).name if src and src.res else "?"
            print(f"   src {s} ({nm}) atlas ({ax},{ay}) alt {alt}: {n}")
    print("\n== objetos (Sprite2D) por grupo:")
    for k, n in sorted(r.object_count.items()):
        print(f"   {k}: {n}")
    cmds = r.commands()
    print("limites do mundo (px):", bounds_of(cmds))
    print("\nTexturas usadas (res -> arquivo):")
    for res, p in sorted(resolver.used):
        print(f"   {res} -> {p}")
    report_missing(resolver)


# res:// -> origem forçada para todas as células da fonte (--uniform-origin)
UNIFORM_ORIGIN = {}


# ------------------------------------------------------------------- API

def load(scene=DEFAULT_SCENE, overrides=None):
    """Interpreta a cena sem desenhar.

    `overrides`: dict ou lista de "res://...=arquivo". Devolve um Renderer com
    `.layers` (Layer: path, node, tileset, cells[(x, y, src, ax, ay, alt)], offset),
    `tileset.sources[id].res` e `.sprites` (Cmd de cada Sprite2D de objetos).
    """
    if isinstance(overrides, dict):
        overrides = [f"{k}={v}" for k, v in overrides.items()]
    path = GAME / scene
    # o repositório do jogo pode estar numa branch de teste com o kit já
    # aplicado; o ensaio parte sempre da cena da main (cópia em ensaio/cena)
    pinned = Path(__file__).resolve().parents[1] / "cena" / "jogo-main.tscn"
    if scene == DEFAULT_SCENE and pinned.exists():
        path = pinned
    return Renderer(Scene(path), Resolver(overrides))


def render(scene_obj, tile_fn=None, crop=None, scale=1, objects=True,
           uniform_origin=None, extra_cells=None, extra_objects=None):
    """Desenha e devolve uma Image RGBA.

    tile_fn(layer_path, x, y, src_res, ax, ay) -> Image|None: troca o tile da
      célula (None mantém o original). Trocas e extra_cells usam origem (0,0),
      ou `uniform_origin` (x, y).
    extra_cells: {layer_path (completo ou último segmento): {(x, y): Image}}
      adiciona células (ou troca as existentes).
    extra_objects: [(Image, pé_x, pé_y)] em px do mundo; o pé é o centro da
      borda inferior; entram no y-sort com os objetos. Desenhados mesmo com
      objects=False (que só desliga os Sprite2D da cena).
    crop: (x0, y0, x1, y1) em px do mundo; None = mundo inteiro.
    """
    r = scene_obj
    r.objects = objects
    r.tile_fn, r.uniform_origin = tile_fn, uniform_origin
    r.extra_cells, r.extra_objects = extra_cells or {}, extra_objects or []
    cmds = r.commands()
    if not cmds:
        raise ValueError("nada para desenhar")
    if isinstance(crop, str):
        crop = tuple(int(v) for v in crop.split(","))
    img = draw(cmds, tuple(crop) if crop else bounds_of(cmds))
    if scale != 1:
        img = img.resize((img.width * scale, img.height * scale), Image.NEAREST)
    return img


_GRASS = {(0, 2), (1, 2), (2, 2), (4, 3), (5, 3), (6, 3)}
_WATER = {(0, 10), (3, 10), (6, 10), (8, 10)}


def default_classify(src_res, ax, ay):
    name = Path(src_res or "").name
    if name == "road.png":
        return "road"  # asfalto (confirmado no render)
    if name == "spritesheet.png":
        if (ax, ay) in _GRASS:
            return "grass"
        if (ax, ay) == (9, 0):
            return "path"
        if (ax, ay) in _WATER:
            return "water"
    return None


def terrain_grid(scene_obj, layer="TerrainLayer", classify=None):
    """{(x, y): nome do terreno}; classify(src_res, ax, ay) -> str|None."""
    classify = classify or default_classify
    L = scene_obj.layer(layer)
    out = {}
    for x, y, src, ax, ay, _ in L.cells:
        s = L.tileset.sources.get(src)
        out[(x, y)] = classify(s.res if s else None, ax, ay) or f"other:{src}:{ax},{ay}"
    return out


def main():
    ap = argparse.ArgumentParser(
        description="Renderiza o mapa estático do Veredas Farm. A flora gerada em "
                    "runtime (gerador_mapa.gd) não é desenhada.")
    ap.add_argument("--scene", default=DEFAULT_SCENE,
                    help="cena relativa ao repo do jogo (padrão: %(default)s)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    rp = sub.add_parser("render", help="desenha o mapa em PNG")
    rp.add_argument("--out", required=True)
    rp.add_argument("--atlas-override", action="append", metavar="RES=ARQUIVO",
                    help="ex.: res://assets/Tilemap/spritesheet.png=novo.png (repetível)")
    rp.add_argument("--scale", type=int, default=1)
    rp.add_argument("--crop", help="x0,y0,x1,y1 em pixels do mundo (como em stats)")
    rp.add_argument("--no-objects", action="store_true",
                    help="só as camadas de tiles, sem Sprite2D de objetos")
    rp.add_argument("--uniform-origin", action="append", metavar="RES=X,Y",
                    help="força a mesma texture_origin em todas as células da fonte")
    rp.set_defaults(fn=cmd_render)
    sp = sub.add_parser("stats", help="uso de células de atlas por camada")
    sp.add_argument("--no-objects", action="store_true")
    sp.set_defaults(fn=cmd_stats)
    args = ap.parse_args()
    for u in getattr(args, "uniform_origin", None) or []:
        r, xy = u.rsplit("=", 1)
        UNIFORM_ORIGIN[r] = tuple(int(c) for c in xy.split(","))
    args.fn(args)


if __name__ == "__main__":
    main()
