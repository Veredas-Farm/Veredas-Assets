"""Gera um TileSet do Godot 4 (.tres) a partir do kit exportado por kit.py.

Uso: python godot_tileset.py <kitdir> [--res-path res://assets/terreno/terrain_atlas.png]

Escreve <kitdir>/terrain_tileset.tres:
  - isométrico DIAMOND_DOWN 32x16, igual ao jogo;
  - um terrain set em modo "match corners" com os terrenos do kit;
  - cada tile com terrain, peering bits nos 4 cantos e probabilidade
    (variantes do mesmo terreno dividem o sorteio);
  - texture_origin (0, 0) em todos (o jogo atual mistura origens; ver README).
"""

import argparse
import json
from pathlib import Path

COLORS = {"grass": "Color(0.35, 0.7, 0.25, 1)", "path": "Color(0.7, 0.45, 0.3, 1)",
          "dry": "Color(0.85, 0.8, 0.4, 1)", "water": "Color(0.3, 0.6, 0.9, 1)",
          "lush": "Color(0.15, 0.45, 0.2, 1)", "rock": "Color(0.55, 0.52, 0.48, 1)"}
CORNER_PROP = {"top": "top_corner", "right": "right_corner", "bottom": "bottom_corner", "left": "left_corner"}


# custom data "a" do jogo (gerador_mapa.gd só espalha flora onde a == "grama")
GAME_A = {"grass": "grama", "dry": "grama", "lush": "grama", "rock": "terra", "path": "terra",
          "water": "agua", "tilled": "terra", "tilled_wet": "terra",
          "path_rut_u": "terra", "path_rut_v": "terra"}

# sem transição com a grama: ficam fora do terrain set (colocados com set_cell)
NO_TERRAIN = {"water", "tilled", "tilled_wet", "path_rut_u", "path_rut_v"}


def tres(meta, res_path):
    # água entra no terrain set quando o kit tem transições com ela (variante G)
    no_terrain = NO_TERRAIN - ({"water"} if any("water" in t["corners"].values() and t["kind"] == "trans"
                                               for t in meta["tiles"]) else set())
    terrains = [t for t in meta["terrains"] if t not in no_terrain and "_tone_" not in t and t != "tone"]
    tid = {t: i for i, t in enumerate(terrains)}
    lines = [f'[gd_resource type="TileSet" load_steps=3 format=3]', "",
             f'[ext_resource type="Texture2D" path="{res_path}" id="1_atlas"]', "",
             '[sub_resource type="TileSetAtlasSource" id="TileSetAtlasSource_kit"]',
             'texture = ExtResource("1_atlas")',
             "texture_region_size = Vector2i(32, 32)"]
    for t in meta["tiles"]:
        c, r = t["atlas"]
        k = f"{c}:{r}/0"
        lines.append(f"{k} = 0")
        # tile de transição: o "a" é o do terreno do miolo (maioria dos cantos)
        lines.append(f'{k}/custom_data_0 = "{GAME_A.get(t["terrain"], GAME_A.get(t["terrain"].split("_")[0], "grama"))}"')
        if t["terrain"] in no_terrain or "_tone_" in t["terrain"]:
            continue
        lines.append(f"{k}/terrain_set = 0")
        lines.append(f"{k}/terrain = {tid[t['terrain']]}")
        if abs(t["probability"] - 1.0) > 1e-9:
            lines.append(f"{k}/probability = {t['probability']:.4f}")
        for corner, name in t["corners"].items():
            lines.append(f"{k}/terrains_peering_bit/{CORNER_PROP[corner]} = {tid[name]}")
    lines += ["", "[resource]", "tile_shape = 1", "tile_layout = 5", "tile_size = Vector2i(32, 16)",
              "terrain_set_0/mode = 1", 'custom_data_layer_0/name = "a"', "custom_data_layer_0/type = 4"]
    for name, i in tid.items():
        lines.append(f'terrain_set_0/terrain_{i}/name = "{name}"')
        lines.append(f"terrain_set_0/terrain_{i}/color = {COLORS.get(name, 'Color(1, 0, 1, 1)')}")
    lines.append('sources/0 = SubResource("TileSetAtlasSource_kit")')
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("kitdir")
    ap.add_argument("--res-path", default="res://terrain_atlas.png")
    a = ap.parse_args()
    d = Path(a.kitdir)
    meta = json.loads((d / "terrain_atlas.json").read_text())
    extra = [f'{s["atlas"][0]}:{s["atlas"][1]}/0 = 0' for s in meta.get("shore", [])]
    txt = tres(meta, a.res_path)
    if extra:
        txt = txt.replace("\n\n[resource]", "\n" + "\n".join(extra) + "\n\n[resource]")
    (d / "terrain_tileset.tres").write_text(txt)
    print(d / "terrain_tileset.tres", len(meta["tiles"]) + len(extra), "tiles")


if __name__ == "__main__":
    main()
