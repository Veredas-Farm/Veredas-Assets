# Entrega do ensaio de assets (2026-11-20)

Material pronto para testar no Veredas Farm. Nada foi copiado para o
repositório do jogo; os caminhos `res://` abaixo são sugestões.

## Conteúdo

| Caminho | O que é |
| :-- | :-- |
| `terreno/terrain_atlas.png` | tiles 32x32: grama, trilha, palha, grama úmida (6 variantes cada), água, arado seco/molhado (2 cada), transições por canto da grama com trilha, palha e úmida (14 casos x 3 variantes cada), 15 margens de água, sulcos de pneu (2 eixos, colocar por script no meio da estrada) |
| `terreno/terrain_tileset.tres` | TileSet isométrico 32x16 com terrain set "match corners" (grama, trilha, palha, úmida) e probabilidades por variante; espera o atlas em `res://assets/terreno/terrain_atlas.png` |
| `terreno/terrain_atlas.json` | descrição de cada tile (cantos, terreno, probabilidade, margens) |
| `terreno/margem.gd` | `Margem.aplicar(layer, celulas_de_agua)`: escolhe o tile de água pelos vizinhos |
| `terreno-moss/` | o mesmo kit refeito com texturas do moss-pixel (plano B de licença); mesma disposição do atlas |
| `terreno-agua/` | kit da variante G: água como terreno de canto (margem orgânica com espuma), dentro do terrain set; dispensa `margem.gd`. Pintar água com 2+ células de largura |
| `terreno-agua/decor_*` | camada de decoração (TileMapLayer por cima do terreno, mesmo z): tufos, flores, trevo, seixos, folhas, rachaduras, buracos, poças, capim entre sulcos. O atlas do terreno também tem tons quente/frio (`grass_tone_*`, fora do terrain set; escolhidos por ruído nos vértices em `tools/aplicar_kit_jogo.py`) |
| `terreno-moss-agua/` | o mesmo, com as texturas do moss-pixel |
| `objetos/crops/` | 7 cultivos com estágios (último = seco) e `.json` com retângulo e pé de cada estágio |
| `objetos/objects/` | cagaita (3 formas, florida, seca, só folhas), cupinzeiro (alto e baixo), ipê amarelo e roxo, cerca de aroeira (peça repetível na diagonal, `next` no .json), pilão, moinho d'água, carro de boi, carroças, reboque; `.json` com o pé |
| `objetos/fases/` | árvores em fases com tronco, tela e pé idênticos (inpaint só na copa): ipê amarelo e roxo (florido, verde, seco, brotando), cagaita, pequi e baru (florida, fruto verde, maduro, folhada); `_repix` = mesma fase reduzida com repixelate, para comparar. Prévia em `objetos/fases_preview.png` e `objetos/fases.gif` |
| `objetos/icons/` | 11 ícones 32x32 (inclui melancia) no estilo dos itens atuais |
| `personagem/` | fazendeiro (chapéu de palha), roupas A e B, nos layouts do jogo: `farmer_Player*.png` substitui `Player.png` (parado, andando, foice, desmaio) e `farmer_Player_Actions*.png` substitui `Player_Actions.png` (48x48: picareta, machado, enxada, regador). Mesmos nomes de animação e regiões do `jogo.tscn`; `preview*.png` compara com o atual |
| `personagem/npc_*.png` | 3 NPCs no layout das linhas 0-5 do `Player.png` (parado e andando, 3 vistas): dona da venda, vaqueiro, criança |
| `decals/pedras/` | pedras e seixos pequenos para espalhar no chão |
| `mapas/` | variantes do mapa (A a G, metade do tamanho), comparativo e prints do Godot |

## Teste no jogo (branch local `ensaio/assets-novos` do Veredas-Farm, sem push)

- As cenas apontam para `res://assets/...` (submódulo vazio); na branch elas
  apontam para `res://old_assets/...`, que tem os arquivos.
- Fazendeiro: `old_assets/Player/farmer_Player*.png`, trocado no `jogo.tscn` e
  no `veredas_farm.tscn`.
- Terreno: `tools/aplicar_kit_jogo.py out/kit-g out/kit-g/cells_G.json
  ../../Veredas-Farm` repinta a `TerrainLayer` com o kit G (mapa da variante G:
  lago e córrego por canto, palha, grama úmida, estrada com borda irregular e
  sulcos de pneu) e grava o kit em `old_assets/terreno/`.
- O TileSet novo tem o custom data `a` (`grama`/`terra`/`agua`) que o
  `gerador_mapa.gd` usa para espalhar flora.
- Prints: `mapas/godot-jogo-kit-G.png` (mapa inteiro no Godot) e
  `mapas/godot-jogo-fazendeiro.png` (jogo rodando).
- Fora do jogo por enquanto: ponte, buracos/poças, cupinzeiros (objetos do
  render, o jogo não tem sistema de decal).

## Como ligar no jogo

1. Corrigir a origem dos tiles atuais: no `jogo.tscn`, as gramas e a terra do
   `spritesheet.png` têm `texture_origin` diferentes por célula ((0,-2),
   (0,-1), (0,2), (0,0)). Isso desloca vizinhos e desenha as linhas escuras em
   degrau na grama (confirmado num print do próprio Godot). Os tiles novos
   usam todos (0,0).
2. Copiar o atlas para `res://assets/terreno/` e o `.tres` para onde ficam os
   recursos; trocar o TileSet da `TerrainLayer`.
3. Pintar grama, trilha, palha e grama úmida com
   `set_cells_terrain_connect(celulas, 0, terreno)`. O Godot escolhe a
   transição e sorteia a variante. Pintar uma volta além da área visível: a
   borda sem vizinho não tem tile que case.
4. Água e arado ficam fora do terrain set (não têm transição): usar
   `set_cell`. Água: depois de pintar, `Margem.aplicar(layer, agua)`.
5. Manchas (palha, úmida) precisam de 1 célula de folga da trilha: não há
   tile com três terrenos no mesmo vértice.

## Validação

- Validador de geometria e costura (`tools/isocheck.py`): todos os tiles
  puros passam (silhueta canônica, sem semitransparência, costura ≈ 1).
- Godot 4.6: mapa de teste pintado pelo próprio Godot com o `.tres`; o print
  (Xvfb + OpenGL) bate pixel a pixel com o render do ensaio (0 de 130.240
  pixels diferentes). Os mapas A a F são renders do ensaio, e o render do
  mapa original bate com o print do Godot (só os buritis diferem, por serem
  objeto no render).

## Limites conhecidos

- A água é o tile original rebaixado com espuma; as texturas de água da IA
  saíram ruins (ilhas, vitórias-régias).
- Arroz e cana dos `items_spritesheet.png` atuais são melhores que os novos.
- Rodas do carro de boi saem raiadas (a real é maciça).
- Licenças: o sdxl-pad (texturas de `terreno/` e as pedras) proíbe vender
  imagens sem consentimento escrito do autor; o jogo não é comercial, então
  os dois kits ficam à escolha. `terreno-moss/` evita isso, se a
  licença do moss-pixel (não conferida, civitai 3024672) permitir. Objetos,
  cultivos e ícones são do moss-pixel.
