# Escolhe o tile de água de cada célula pelos 4 vizinhos: aresta que toca
# terra ganha espuma e raso. Gerado por ensaio/tools (kit + godot_tileset).
# Uso: Margem.aplicar($TerrainLayer, celulas_de_agua)
class_name Margem

const AGUA := Vector2i(0, 4)
# chave: vizinhos (x-1, x+1, y-1, y+1); 1 = terra
const MARGEM := {
	"0001": Vector2i(0, 16),
	"0010": Vector2i(1, 16),
	"0011": Vector2i(2, 16),
	"0100": Vector2i(3, 16),
	"0101": Vector2i(4, 16),
	"0110": Vector2i(5, 16),
	"0111": Vector2i(6, 16),
	"1000": Vector2i(7, 16),
	"1001": Vector2i(8, 16),
	"1010": Vector2i(9, 16),
	"1011": Vector2i(10, 16),
	"1100": Vector2i(11, 16),
	"1101": Vector2i(12, 16),
	"1110": Vector2i(13, 16),
	"1111": Vector2i(14, 16),
}


static func aplicar(layer: TileMapLayer, agua: Array[Vector2i], fonte: int = 0) -> void:
	var conj := {}
	for c in agua:
		conj[c] = true
	for c in agua:
		var k := ""
		for d in [Vector2i(-1, 0), Vector2i(1, 0), Vector2i(0, -1), Vector2i(0, 1)]:
			k += "0" if conj.has(c + d) else "1"
		layer.set_cell(c, fonte, MARGEM.get(k, AGUA))
