"""Aplica um kit de terreno ao jogo.tscn (TerrainLayer) de uma cópia de trabalho
do Veredas-Farm.

Uso: python aplicar_kit_jogo.py <kitdir> <cells.json> <repo_do_jogo> [--res-dir old_assets/terreno]

1. Pinta as células (JSON de `remap.py --dump-cells`) num projeto Godot
   temporário com `set_cells_terrain_connect`, na ordem grama, palha, úmida,
   água, trilha.
2. Célula que o Godot deixa vazia (borda do mapa, vértice com 3 terrenos)
   recebe o tile puro do próprio terreno.
3. Faixas `track_u`/`track_v` trocam o tile de trilha pelo de sulco de pneu.
4. Copia atlas e .tres para <repo>/<res-dir>, grava o `tile_map_data` da
   TerrainLayer e troca o TileSet dela por esse .tres.

Godot: o mesmo binário dos outros testes (GODOT abaixo), rodado headless.
"""
import argparse
import base64
import json
import os
import re
import shutil
import struct
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from remap import h, value_noise  # noqa: E402

GODOT = Path.home() / ".cache/veredas-godot/Godot_v4.6-stable_linux.x86_64"
HERE = Path(__file__).resolve().parent

PAINT_GD = """extends SceneTree
func arr(l) -> Array[Vector2i]:
	var out: Array[Vector2i] = []
	for c in l:
		out.append(Vector2i(int(c[0]), int(c[1])))
	return out
func _init():
	var ts: TileSet = load("res://terrain_tileset.tres")
	var layer := TileMapLayer.new()
	layer.tile_set = ts
	root.add_child(layer)
	var names := {}
	for i in ts.get_terrains_count(0):
		names[ts.get_terrain_name(0, i)] = i
	var cells: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://cells_in.json"))
	var all: Array[Vector2i] = []
	for k in ["grass", "dry", "lush", "rock", "water", "path"]:
		if cells.has(k):
			all.append_array(arr(cells[k]))
	layer.set_cells_terrain_connect(all, 0, names["grass"])
	for k in ["dry", "lush", "rock", "water", "path"]:
		if cells.has(k) and names.has(k):
			layer.set_cells_terrain_connect(arr(cells[k]), 0, names[k])
	var out := {}
	for c in layer.get_used_cells():
		var a := layer.get_cell_atlas_coords(c)
		out["%d,%d" % [c.x, c.y]] = [a.x, a.y]
	var f := FileAccess.open("res://cells_out.json", FileAccess.WRITE)
	f.store_string(JSON.stringify(out))
	f.close()
	quit()
"""

PROJECT = """config_version=5

[application]
config/name="pinta"
"""


def paint(kitdir, cells_path, work):
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    (work / "project.godot").write_text(PROJECT)
    (work / "paint.gd").write_text(PAINT_GD)
    shutil.copy(kitdir / "terrain_atlas.png", work)
    tres = (kitdir / "terrain_tileset.tres").read_text()
    tres = re.sub(r'path="res://[^"]*terrain_atlas.png"', 'path="res://terrain_atlas.png"', tres)
    (work / "terrain_tileset.tres").write_text(tres)
    shutil.copy(cells_path, work / "cells_in.json")
    env = dict(os.environ, HOME=str(work / "home"))
    subprocess.run([str(GODOT), "--headless", "--import"], cwd=work, env=env, capture_output=True, timeout=300)
    subprocess.run([str(GODOT), "--headless", "-s", "paint.gd"], cwd=work, env=env, capture_output=True, timeout=600,
                   check=True)
    return json.loads((work / "cells_out.json").read_text())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("kitdir")
    ap.add_argument("cells")
    ap.add_argument("repo")
    ap.add_argument("--res-dir", default="old_assets/terreno")
    ap.add_argument("--scene", default="scenes/mundo/jogo.tscn")
    a = ap.parse_args()
    kitdir, repo = Path(a.kitdir), Path(a.repo)
    cells_in = json.loads(Path(a.cells).read_text())
    meta = json.loads((kitdir / "terrain_atlas.json").read_text())
    pure = {}
    for t in meta["tiles"]:
        if t["kind"] == "pure":
            pure.setdefault(t["terrain"], []).append(tuple(t["atlas"]))
    got = paint(kitdir, a.cells, Path(os.environ.get("TMPDIR", "/tmp")) / "aplicar_kit")
    cells, filled = {}, 0
    for k in ("grass", "dry", "lush", "rock", "water", "path"):
        for x, y in cells_in.get(k, []):
            key = f"{x},{y}"
            if key in got:
                cells[(x, y)] = tuple(got[key])
            else:
                cells[(x, y)] = pure[k][(x * 7 + y * 13) % len(pure[k])]
                filled += 1
    # sulco: só onde o Godot pôs tile puro de trilha (mesma variante, com sulco)
    path_pure = pure["path"]
    ruts = 0
    rut_t = {(t["terrain"][-1], t["cin"], t["cout"], t["variant"]): tuple(t["atlas"])
             for t in meta["tiles"] if t["kind"] == "rut"}
    ncfg = 1 + max((k[1] for k in rut_t), default=0)

    def edge_cfg(ax, x, y):
        # ruído suave ao longo da estrada: as marcas derivam para um lado e voltam
        n = value_noise(x * 0.7, y * 0.7, 3.0, 911 + (ax == "v"))
        return max(0, min(ncfg - 1, int((n - 0.2) / 0.6 * ncfg)))

    rut_cfg = {}
    for ax in ("u", "v"):
        for x, y in cells_in.get("track_" + ax, []):
            cur = cells.get((x, y))
            if cur in path_pure:
                nxt = (x + 1, y) if ax == "u" else (x, y + 1)
                ci, co = edge_cfg(ax, x, y), edge_cfg(ax, *nxt)
                cells[(x, y)] = rut_t[(ax, ci, co, h(x, y, 77) % 2)]
                rut_cfg[(x, y)] = (ax, ci, co)
                ruts += 1
    # tons em mancha: vértice com tom se as 4 células em volta são grama pura
    info = {tuple(t["atlas"]): t for t in meta["tiles"]}
    is_pure = lambda c, k: c in cells and info.get(cells[c], {}).get("kind") == "pure" and info[cells[c]]["terrain"] == k
    tone_tiles = {}
    for t in meta["tiles"]:
        if t["kind"] == "tone":
            bits = tuple(int(t["corners"][k] == "tone") for k in ("top", "right", "bottom", "left"))
            tone_tiles[(t["terrain"].split("_tone_")[1], bits, t.get("variant", 0))] = tuple(t["atlas"])
    vt = {}

    def vtone(X, Y):
        if (X, Y) not in vt:
            ok = all(is_pure(c, "grass") for c in ((X, Y), (X - 1, Y), (X, Y - 1), (X - 1, Y - 1)))
            n = 0.65 * value_noise(X, Y, 7.0, 303) + 0.35 * value_noise(X, Y, 2.5, 304)
            vt[(X, Y)] = None if not ok else ("warm" if n > 0.62 else "cool" if n < 0.34 else None)
        return vt[(X, Y)]

    toned = 0
    if tone_tiles:
        for (x, y) in list(cells):
            if not is_pure((x, y), "grass"):
                continue
            cs = [vtone(x, y), vtone(x + 1, y), vtone(x + 1, y + 1), vtone(x, y + 1)]  # top right bottom left
            tones = [c for c in cs if c]
            if not tones:
                continue
            tone = max(set(tones), key=tones.count)
            bits = tuple(int(c == tone) for c in cs)
            cells[(x, y)] = tone_tiles[(tone, bits, (x * 7 + y * 13) % 3)]
            toned += 1
    data = bytearray(struct.pack("<H", 0))
    for (x, y), (ax_, ay_) in sorted(cells.items()):
        data += struct.pack("<hhHHHH", x, y, 0, ax_, ay_, 0)
    # decoração: um tile por célula pura, densidade com ruído (touceiras e clareiras)
    decor = []
    dmeta = kitdir / "decor_atlas.json"
    if dmeta.exists():
        dt = json.loads(dmeta.read_text())["tiles"]
        bank = {}
        for t in dt:
            bank.setdefault(t["on"], []).append(tuple(t["atlas"]))
        track = {tuple(c): ax for ax in ("u", "v") for c in cells_in.get("track_" + ax, [])}
        for (x, y), at in cells.items():
            t = info.get(at, {})
            terr = t.get("terrain", "")
            kind = t.get("kind")
            if (x, y) in rut_cfg:
                ax, ci, co = rut_cfg[(x, y)]
                if ci == co and ci in (0, ncfg - 1) and h(x, y, 503) % 100 < 45:
                    # marcas desviadas: buraco do outro lado
                    on, p = f"trackhole_{ax}_{'dir' if ci == 0 else 'esq'}", 1.0
                else:
                    on, p = "track_" + ax, 0.3
            elif kind in ("pure", "tone") and terr.split("_tone_")[0] in ("grass", "dry", "lush", "path"):
                on = terr.split("_tone_")[0]
                n = value_noise(x, y, 5.0, 41)
                p = {"grass": 0.45 * (0.15 + 1.7 * n * n), "dry": 0.35, "lush": 0.5, "path": 0.14}[on]
            else:
                continue
            if on in bank and h(x, y, 501) % 1000 / 1000 < p:
                decor.append(((x, y), bank[on][h(x, y, 502) % len(bank[on])]))
    ddata = bytearray(struct.pack("<H", 0))
    for (x, y), (ax_, ay_) in sorted(decor):
        ddata += struct.pack("<hhHHHH", x, y, 0, ax_, ay_, 0)
    dst = repo / a.res_dir
    dst.mkdir(parents=True, exist_ok=True)
    shutil.copy(kitdir / "terrain_atlas.png", dst)
    res_atlas = f"res://{a.res_dir}/terrain_atlas.png"
    tres = re.sub(r'path="res://[^"]*terrain_atlas.png"', f'path="{res_atlas}"',
                  (kitdir / "terrain_tileset.tres").read_text())
    (dst / "terrain_tileset.tres").write_text(tres)
    if decor:
        shutil.copy(kitdir / "decor_atlas.png", dst)
        dtres = (kitdir / "decor_tileset.tres").read_text().replace(
            'path="res://decor_atlas.png"', f'path="res://{a.res_dir}/decor_atlas.png"')
        (dst / "decor_tileset.tres").write_text(dtres)
    scene = repo / a.scene
    s = scene.read_text()
    i = s.index('[node name="TerrainLayer"')
    j = s.index("\n[node", i + 10)
    node = re.sub(r'tile_map_data = PackedByteArray\("[^"]*"\)',
                  'tile_map_data = PackedByteArray("%s")' % base64.b64encode(bytes(data)).decode(), s[i:j])
    node = re.sub(r"tile_set = \w+\([^)]*\)", 'tile_set = ExtResource("kit_terreno")', node)
    s = s[:i] + node + s[j:]
    # DecorLayer logo depois da TerrainLayer (mesma posição e z)
    s = re.sub(r'\n\[node name="DecorLayer"[^\[]*', "\n", s)
    if decor:
        i = s.index('[node name="TerrainLayer"')
        j = s.index("\n[node", i + 10)
        pos = re.search(r"position = (Vector2\([^)]*\))", s[i:j]).group(1)
        dnode = ('\n[node name="DecorLayer" type="TileMapLayer" parent="MapLayers"]\nz_index = -2\n'
                 f'position = {pos}\n'
                 'tile_map_data = PackedByteArray("%s")\n' % base64.b64encode(bytes(ddata)).decode()
                 + 'tile_set = ExtResource("kit_decor")\n')
        s = s[:j] + "\n" + dnode.rstrip("\n") + s[j:]
        dext = f'[ext_resource type="TileSet" path="res://{a.res_dir}/decor_tileset.tres" id="kit_decor"]\n'
        if 'id="kit_decor"' not in s:
            k = s.index("\n", s.rindex("[ext_resource")) + 1
            s = s[:k] + dext + s[k:]
    ext = f'[ext_resource type="TileSet" path="res://{a.res_dir}/terrain_tileset.tres" id="kit_terreno"]\n'
    if 'id="kit_terreno"' not in s:
        k = s.index("\n", s.rindex("[ext_resource")) + 1
        s = s[:k] + ext + s[k:]
    scene.write_text(s)
    print(f"{len(cells)} células, {filled} completadas com tile puro, {ruts} sulcos, {toned} com tom, "
          f"{len(decor)} decorações -> {scene}")


if __name__ == "__main__":
    main()
