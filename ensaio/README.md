# Ensaio de assets (noite de 2026-11-19 para 20)

Objetivo: arte do Veredas Farm mais polida e variada, gerada com o `aig` e
reduzida à resolução do jogo, encaixando na grade isométrica do Godot.

## Layout

| Caminho | Conteúdo |
| :-- | :-- |
| `tools/gen.py` | enfileira jobs no aig, espera e copia para `runs/<exp>/` |
| `tools/iso.py`, `tools/isocheck.py` | geometria canônica do bloco, validador, mapa estilo Godot |
| `tools/mapview.py` | renderiza o mapa real (`jogo.tscn`) com atlas trocado |
| `tools/project.py` | textura vista de cima → tiles isométricos, variantes e transições |
| `tools/style.py` | rampa curta por material, limpeza, borda/sombra nas transições |
| `tools/vignette*.py` | vinhetas de teste (grama, trilha, roça) |
| `runs/eNN/` | gerações de terreno (eu); `runs/oNN/` objetos (agente) |
| `objects/` | pipeline e resultados de objetos/itens (agente) |
| `advisor/` | ideias do advisor |
| `out/` | prévias e atlas |

## Geometria (conferida no Godot 4.6 headless)

- TileSet isométrico DIAMOND_DOWN 32x16; `map_to_local(x, y) = (16 + (x-y)*16, 8 + (x+y)*8)`.
- Célula do atlas 32x32: losango de cima nas linhas 8..23 (larguras 4..32..4),
  8 px de altura; silhueta de 544 px.
- O tile é desenhado em `centro - 16 - texture_origin`.

## Log

- e01: grama vista de cima em 3 modelos + bloco isométrico direto. sdxl-pad e
  moss-pixel dão boas texturas; LCM sai ruído; bloco direto não respeita a
  proporção (cubo alto) nem vira tile. Decisão: terreno por projeção.
- Projeção: sem emenda nos mapas. Primeira versão tinha linha escura nas
  arestas (face errada no downsample); corrigido usando as máscaras canônicas.
- Transições por cantos (16 tiles): ruído que some nas arestas, então qualquer
  vizinho casa. Ruído por tile (seed) quebra a repetição.
- e02: texturas de terreno (sdxl-pad). Boas: trilha de areia, arada, capim
  seco, corte de solo (metade de baixo). Ruins: água (virou mapa com ilhas),
  solo vermelho (rachaduras de calçamento).
- Mapa real: o `jogo.tscn` tem `texture_origin` diferente por célula
  ((0,-2), (0,-1), (0,2), (0,0)) nas gramas e na terra; isso desloca tiles
  vizinhos e mostra laterais escuras em degraus. Com tiles canônicos, a origem
  deve ser uniforme (`mapview.py --uniform-origin`).
- Variantes intercambiáveis: borda comum (recorte periódico) + miolo variado;
  mistura aleatória passa no validador (costura 0,96). Funcionam com o sorteio
  por probabilidade do Godot, sem script.
- Estilização (crítica do advisor): 4 tons por material por quantil de
  luminância (base ~57%), sombra fria, luz quente, limpeza de pixel isolado.
  Transições com borda escura e sombra no degrau (`out/e03/v3.png`).
- Mapa real com o kit novo (`tools/remap.py`, `out/maps/`):
  - A: troca de pele, mesmo traçado.
  - B: transições por cantos na trilha (vértice é trilha com >= 2 células
    vizinhas de trilha); terra avulsa vira trilha.
  - C: B + manchas de capim seco por ruído (rampa de palha desenhada à mão),
    flora atual espalhada em grupos e sombras elípticas.
  - Cores travadas nas rampas dos tiles originais (`style.ramp_like`): a
    grama e a trilha novas casam com as construções atuais. Contraste 0,65.
- Kit exportável (`tools/kit.py out/kit`): `terrain_atlas.png` + JSON com
  cantos por tile (terrain set "match corners" do Godot), origem (0,0).
  - Bug achado pelo validador: tile repetido mostrava pontilhado diagonal nas
    arestas (costura 2..5). Causa: os tons extremos da rampa caíam na faixa de
    borda comum, que é igual em todo tile, e viravam padrão. Correção:
    `style.calm_edges` troca os extremos pela base a < 2 px da aresta. Todos
    os tiles puros passam (costura <= 0,8; mistura 0,06..0,19).
  - Correção da correção: o achatamento da faixa de borda (`BAND_FLAT`)
    deixava a borda mais lisa que o miolo e desenhava uma treliça de losangos
    no mapa (costura 0,3..0,5). Desligado; `calm_edges` com 1 px basta. O
    validador agora avisa "treliça" com costura < 0,6.
- Água: `project.shore` põe espuma e raso nas arestas que tocam terra (16
  casos por vizinho; nas arestas de baixo a borda visível é a do losango sem
  rebaixo, porque o bloco vizinho cobre a faixa rebaixada).
- D (seca, M4 do advisor): C com a rampa da grama trocada por oliva apagado
  (`remap.recolor`, troca exata de cores) e mais manchas de palha.
- E (vereda, M3 do advisor): córrego de 2 células saindo do lago, sinuoso,
  cruzando a trilha (passagem molhada: a trilha continua) até uma lagoa de
  nascente; faixa de grama úmida (rampa escura sobre o capim seco recolorido)
  colada na água e buritis nas margens (`remap.vereda`, `remap.buritis`).
- TileSet do Godot (`tools/godot_tileset.py out/kit` → `terrain_tileset.tres`):
  terrain set "match corners", peering bits nos 4 cantos, probabilidade por
  variante, origem (0,0). Testado no Godot 4.6 headless: script pinta grama,
  trilha em cruz e mancha seca com `set_cells_terrain_connect`;
  `tools/godot_check.py` confere os vértices e desenha (`out/kit/godot-test.png`).
  Interior sem conflito; o anel da borda conflita porque o vizinho de fora é
  vazio. No jogo: pintar uma volta além da área visível.
- Decals procedurais (`remap.decals`): tufo em leque 9x7 com a rampa do
  terreno do vértice (grama, palha, úmida) e flores em cruz 3x3 em manchas
  (ruído). Primeira versão com tons médio/claro sumia no chão: a lâmina
  precisa do tom mais escuro da rampa. Ligados nas variantes C, D, E.
- e03: grass2 (sdxl-pad, grama escura com margaridas) virou a grama úmida
  (`lush`, rampa puxada para verde escuro, 15% da cor própria). grass3
  (moss) tem tufos em grade, repetição visível. Solo vermelho de novo saiu
  calçamento; água saiu cheia de vitórias-régias azul-escuro. Ambos
  descartados; a água segue sendo o tile original rebaixado com espuma.
- e04 (decals, sdxl-pad): pedras com líquen em fundo branco recortam bem
  (`tools/decals.py`: componentes conexos, bloco 8x8 -> 1 px pela mediana) →
  `out/decals/stones`. A folha "cerrado" vem com cada item sobre um bloco de
  terra (inútil como decal; cupinzeiros seriam bons como objeto). A folha de
  tufos saiu em canteiros com fundo lilás: descartada, ficam os procedurais.
  Pedras entram em C/D/E em grupos por ruído; seixos pequenos na trilha.
- Print no Godot de verdade (Xvfb + OpenGL, fora do sandbox por causa do
  socket X): o mapa de teste pintado com o TileSet novo (`out/kit/godot-shot.png`)
  bate pixel a pixel com o `iso.render_map` (0 de 130.240 pixels diferentes,
  `tools/godot_diff.py`). O encaixe na grade está provado no motor.
- Print do `jogo.tscn` original no Godot (cópia do projeto em $TMPDIR, só as
  TileMapLayer, `out/mapview/godot-shot.png`) contra `mapview.render(objects=False)`:
  as únicas diferenças (1%) são os buritis, que o mapview trata como objeto.
  Terreno, trilha, cerca, estrada e água batem pixel a pixel, inclusive as
  linhas em degrau do `texture_origin` misto (o bug aparece no motor).
- Objetos do agente (`objects/README.md`): moss-pixel venceu para objetos;
  redução por média de área (`box`) com alfa pré-multiplicado; árvores com
  cor dominante; contorno 1 px azul-marinho dos itens atuais.
- F (vitrine): E + roça arada 6x4 perto da casa (`remap.farm_plot`, terra
  arada molhada), cultivos do agente por fileira (mandioca, feijão, cana,
  melancia) com estágio variando, carro de boi na beira da roça, cagaitas
  misturadas à flora.
- Crítica do advisor (2ª rodada) aplicada no que cabe em tiles: grama úmida
  só 1 tom abaixo e faixa mais estreita; densidade de tufos modulada por
  ruído (clareiras); menos pedras e arbustos; buritis em touceiras; lago
  mais escuro longe da margem (2 níveis). Não aplicado: máscara de água em
  espaço de mundo (não vira tile), estrada mais estreita (traçado do jogo),
  copas escuras (sprites atuais do jogo).
- e05 (licença): o sdxl-pad exige consentimento escrito do autor para vender
  imagens. Refiz as 4 texturas no moss-pixel (`kit-moss.json`; úmida =
  grama moss com a rampa úmida). Resultado no mesmo nível
  (`out/maps/compare-moss.png`); kit exportado em `out/kit-moss`, todos os
  tiles passam. Capim seco moss tem costura 0,01 (aviso de treliça), sem
  efeito visível no mapa. Licença do moss ainda não conferida.
- Variante G: água como terreno de canto (como trilha/palha), com espuma
  e raso na transição, paleta presa às 2 cores da água do jogo. Margem
  orgânica em vez de serrilha. Kit em `out/kit-g` (`kit.py --water-corners`),
  água entra no terrain set. Teste no Godot: corpos d'água com 2+ células de
  largura ficam contínuos; canal de 1 célula e saliências isoladas viram
  poças soltas (regra de pintura). 3 vértices em conflito na borda do lago
  do teste, mesmo tipo de caso da palha.
- Roça com carreador: fileiras alternadas sem planta (canteiro 6x7), os
  cultivos deixam de virar uma massa verde.
- Ponte (G): o vau do córrego na trilha vira água com uma ponte de tábuas
  procedural (`remap.bridge`), tábuas cruzando o sentido da trilha e
  guarda-corpo dos lados da correnteza. No Godot seria um objeto; as células
  sob a ponte precisam de `set_cell` com água (não há transição
  trilha/água no kit).
- Copa escura (crítica C5): `--copa` clareia os tons escuros das árvores do
  espalhamento, mas as árvores mais escuras são as do próprio mapa do jogo
  (cena), que o render não altera. Efeito pequeno; fica como decisão sobre
  os sprites do jogo, não do kit.
- Kit moss com água por canto: `out/kit-moss-g`, entrega em `terreno-moss-agua/`, mapa `G-moss`.
- Cupinzeiros (o18) no mapa G: na palha, longe de trilha/água (`remap.cupinzeiros`).
- Estrada (pedido do usuário): sulcos de pneu em tiles de trilha (`remap.rut_tile`,
  linhas de v/u constante, contínuas entre células) colocados no eixo das
  estradas retas (`track_cells`); buracos e poças como decals (`holes`);
  borda irregular por célula (`ragged_road`, só com 3+ células de trilha
  atrás, senão estrada estreita se parte).
- Jogo: branch local `ensaio/assets-novos` no Veredas-Farm (sem push), cenas
  em `old_assets/`, fazendeiro novo e terreno G aplicado por
  `tools/aplicar_kit_jogo.py` (Godot pinta num projeto à parte, o script
  grava o `tile_map_data`). O ensaio lê a cena da main em `cena/jogo-main.tscn`.
- Variedade (pedido do usuário, `tools/variedade.py`): 10 variantes de grama e
  trilha; parte dos tiles sem o traço escuro (`thin_strokes`) e faixa de borda
  sem o tom mais escuro (`calm_band`): o mesmo traço em todo tile de
  transição/tom virava treliça na grade. Tons quente/frio em mancha
  (`tone_tiles`, 15 combinações de canto, Bayer 4x4, contínuo entre células).
  Camada `DecorLayer` (TileMapLayer, 74 tiles): tufos, flores, trevo, seixos,
  folhas, gravetos, rachaduras, buracos, poças e capim entre os sulcos.
  Sulcos com ruído (`variedade.rut_tile`): posição e largura oscilam no meio
  da célula, fixas nas bordas; trechos rasos e pixels soltos.
- Sulcos de vários carros (`variedade.rut_multi`, `RUT_CFGS`): 4 marcas
  (2 carros) por célula; cada aresta da estrada tem uma configuração
  (desviada p/ um lado .. p/ o outro) escolhida por ruído suave ao longo da
  estrada, e o tile liga a de entrada à de saída com curva. Onde as marcas
  estão desviadas, buraco ou poça do outro lado (`trackhole_*` na DecorLayer).
- Sombras no jogo (`objects/sombras_jogo.py <repo>`): sombra B (projeção da
  silhueta, luz de cima-esquerda) para baru, pequi, árvore seca e casa;
  PNG em `old_assets/sombras/`, nó "Sombra" (Sprite2D filho do sprite, z -1,
  alfa 0.38) em `arvore_5/6/grande/seca_caida.tscn` e na casa do `jogo.tscn`.

## Img2img isométrico

Objetivo: gerar tiles e árvores já em pixel art isométrico no ângulo do jogo (32x16, bloco com lateral),
em vez de projetar textura vista de cima. Script `tools/iso_img2img.py` (`bases`, `reduce`, `tree`, `scene`),
specs em `specs/iso/` (`mk.py` gera os JSON; bases 1024 ampliadas em nearest), gerações em `runs/i01`-`i05`,
saídas em `out/iso/` (`comparacao.png`, `arvores_iso.png`, tiles por geração em `out/iso/<geração>-gp/NN.png`).

Receita que funcionou (moss-pixel img2img, 1024, 8 passos, CFG 1):
- Folha 4x4 de blocos do jogo ou do kit-g, cada célula 32x32 ampliada **8x** (= a grade de 8 px da LoRA), fundo branco
  (`bases`). Denoise **0.45-0.5**, 2 seeds. O prompt descreve a folha por linhas ("4 by 4 grid of isometric cube blocks,
  flat 2:1 diamond top, dark brown soil sides left and right ... plain white background").
- Redução: cada bloco 8x8 vira a cor mais frequente (`mode_down`, não borra), cores presas à paleta dos blocos
  do jogo (`reduce --palette game`), recorte por `iso.snap_tile` (máscara do bloco). Sem a paleta o verde sai
  saturado demais (verde-limão).
- Árvore: img2img da árvore 8x do jogo/ipê, denoise 0.7, depois `tree` (recorte, moda por bloco, paleta pequi+baru).

| lote | base | denoise | veredito |
| :-- | :-- | :-- | :-- |
| i01 | par grama+terra, 16x (1 tile = 512 px) | 0.6 | **ruim**: os blocos viram cubos altos (não 2:1), grama verde-limão. Tile único ampliado perde o ângulo. Só 1 seed e 1 denoise (0.45 e 0.75 não rodados: a fila do aig custou ~50 min por job) |
| i02 | folha 4x4 do jogo (terra, pedras, grama, arada), 8x | 0.45, 2 seeds | **bom**: as 16 células mantêm losango 2:1 e lateral; mesma luz e paleta; grama ganha tufos mais altos. Com a paleta do jogo fica parecida com a original, mas as arestas escuras de cada bloco desenham uma **grade** no mapa 8x8 (costura 6.6) |
| i03 | folha 4x4 do kit-g, prompt "cube blocks, dark outline", 8x | 0.5, 2 seeds | **melhor**: grama/trilha/seca/úmida/transições coerentes entre si, lateral de terra marcada, tiles emendam; seed 1 quase lisa (costura 0.0, treliça como o kit), seed 2 com textura de manchas (2.2) |
| i04 | pequi 8x | 0.7, 2 seeds | jatobá: copa larga, vagens, tronco grosso; estilo mais "limpo" que o pequi, folhas grandes |
| i05 | ipê-amarelo florido 8x | 0.7, 2 seeds | paineira (tronco-garrafa com espinhos, flores rosa): ótima; a paleta pequi+baru transforma o rosa em laranja (falta rosa na paleta) |

Conclusões:
- Ângulo: bate quando a base é uma folha 8x (a LoRA reconhece a grade de 8 px e o desenho de bloco). Tile solto em 16x não.
- Folha coerente: sim, mesma luz e paleta nas 16 células; o modelo respeita linha a linha o que cada linha contém.
- Borda explícita (lateral marcada): ajuda e emenda por construção, pois o modelo repete a mesma lateral. O custo é
  a grade escura nos blocos do jogo (i02); no kit (i03) a face de cima sai lisa e a costura some.
- Vale levar: folha do kit-g a 0.5 com 2-3 seeds como fonte de variantes de grama/trilha (já com lateral),
  paleta do jogo no fim, `mode_down` no lugar de box. Árvores por img2img 0.7 sobre as do jogo servem como espécies novas.
- Problemas: fila do aig longa (esperas de 30-50 min), arestas dos blocos gerados não são periódicas (a emenda entre
  tiles do mesmo tipo vem do nível de ruído, não de borda comum), transições (linha 4 do i03) trazem tons diferentes da grama pura.

### Img2img isométrico: árvores com fases e grama extra no kit

- Árvores (`tools/iso_arvores.py`, reaproveita `objects/phases.py` sem alterá-lo; gerações `runs/i06`-`i08`):
  - paineira: base = i05 (seed ...051); inpaint da copa (template `moss`, máscara fixa, `specs/iso/masks/`) `verde` e `seco` (i07, 2 seeds cada, escolhida a de copa mais cheia / galhos mais completos). Rosa/coral: cores da flor tiradas da própria geração e somadas à paleta pequi+baru (sem isso a flor vira laranja-areia).
  - jatobá: o i04 lembrava cacau (vagens grandes penduradas); refeito em i06 (img2img 0.65 do pequi, 3 seeds, "vagens curtas e duras entre as folhas"). Base = seed ...837 (`fruto`); inpaint `florida` (i08, flores miúdas creme) e `folhada` (folhas novas, saem amarelo-limão pela paleta).
  - Saída: `entrega/objetos/fases/arvore_{paineira_{florida,verde,seco},jatoba_{fruto,florida,folhada}}.png/.json` (`anchor` igual em todas as fases), prévia `out/iso/arvores_novas_fases.png`. Só a redução atual (sem `_repix`).
  - Problemas: tronco da paineira com pixels laranja soltos (paleta do pequi); verde da paineira com pontos amarelos; 6 jobs (i06-i08) + 5 anteriores.
- Grama extra no kit: `python3 tools/kit.py out/kit-g-iso --water-corners --extra-grass out/iso/folha-kit-borda-d50-3689004583`
  (células 0-3 da folha i03 seed 2 reduzidas sem paleta; opções `--extra-grass-cells`, `--extra-grass-weight 0.5`).
  As cores vão para a rampa de grama do kit por quantil de luminância (topo e lateral), depois `variedade.calm_band`;
  as 4 variantes entram no fim de `kit["grass"]` com peso 0,5 (probabilidade 0,042 contra 0,083). O resto do atlas é idêntico ao `out/kit-g`.
  Sem a opção o `kit.py` se comporta como antes. Cena `out/iso/cena_kit_iso.png` (`iso_img2img.py kitscene`): costura das gramas 0,44 -> 0,22 (as duas abaixo de 0,6: aviso de treliça, que já existia).

### Texturas das folhas img2img no kit (`out/kit-moss-tex`)

- `tools/iso_texturas.py`: topo de cada cubo das folhas 3e9149 (a) e 83fb90 (b) -> textura 192x192 (mapa afim inverso do losango 2:1; geometria média da linha 0 da folha, margem 12%). `out/iso/tex/` (`contato.png`).
- `kit-moss-tex.json`: base = `kit-moss.json` + `grass_extra` (a_20, a_22, b_20, b_22), `path_extra` (a_00 terra, a_10 rachada), `lush` = mosaico das gramas com solo/capim alto, `rock` = mosaico de pedra/rachada (terreno novo, transição por canto com a grama, rampa cinza `remap.ROCK_RAMP`).
- `--recolor` (kit.py, remap.py): em vez de travar a rampa de 4 tons, usa 6 tons nos quantis de luminância da própria textura e põe neles as cores do tile do jogo (cor média e saturação do jogo); o tom mais escuro é suavizado e a rampa de referência chapada (trilha) é aberta, sem preto no degrau. Padrão antigo intacto sem a flag.
- Extras entram com peso 0,6 (`remap.EXTRA_W`). Colocação do cascalho no mapa: `remap.patches` (manchas por ruído no campo aberto, fora de 2 células de trilha/água e longe da água), `dump_cells` grava `rock`, `aplicar_kit_jogo.py` pinta `rock` depois de `lush`.
- Comparação: `out/maps/compare-moss-tex.png` (kit-g, moss livre -c, moss-tex); mapa real: `out/maps/G-moss-tex-full.png`.

### Tema "folha nativa" (`out/kit-folha-nativa`, `tools/iso_nativo.py`)

- Blocos das folhas 3e9149/83fb90 como desenho: grade de 8 px alinhada (deslocamento 0,0), `mode_down` 8x8, célula 32x32 com o cubo encaixado no bloco do jogo (topo na linha 8), `iso.snap_tile`; lateral do próprio cubo. Sem média, sem requantização por tile.
- Mesmo `terrain_atlas.json` do `kit-moss-tex` (copiado, idêntico); puros de grama (22), trilha (16), rock (6), lush (6) = blocos nativos (original, topo espelhado, topo girado 180); transições = máscara de canto sobre dois blocos nativos (grama x trilha/rock/lush/seca; água mantida do kit base); sulcos e tons refeitos a partir da trilha/grama nativas.
- `--palette A`: 6 tons do jogo por quantil por terreno. `--palette B`: 10 cores da própria folha, medianas iguais entre fontes. `--calm`: apaga o contorno escuro da aresta do losango.
- Cena `out/maps/compare-folha-nativa.png` (costura da grama: kit-moss-tex 1,70; nativa A 6,21; B 3,11; A + calma 1,48). O contorno de cada bloco desenha uma grade visível no mapa (mais forte em A, e em B a grama neon e a trilha em "tijolos" destoam do jogo); `--calm` tira a grade mas deixa o miolo liso.

## Sweep de modelos (`out/sweep/`, `tools/sweep.py`)

- Img2img de 11 combinações (moss-pixel, moss-refiner, moss + isometric, moss + sentence, flux-pixel, flux,
  sdxl-pad, sdxl-pixel, sdxl-pixel + isometric, sdxl + sai, sd15-pixel) sobre 7 folhas 8x (árvores em pares,
  objetos 2x2, itens e ícones 4x5, cultivos, 16 blocos do `kit-moss-tex`), 2 forças, 1-2 seeds; 104 jobs,
  156 imagens, 7,5 h de fila. Redução: repixelate com a grade imposta para o tamanho e anchor do original,
  variante `_pal` presa à paleta do original.
- Ranking: flux-pixel 0.45 (fiel e limpo, lento) > moss-pixel 0.5 (redesenha bem, cor saturada, usar `_pal`)
  > sdxl-pad 0.5-0.65 > moss-refiner 0.65 (bom para objetos de madeira) > sdxl-pixel = sdxl-pixel-iso > sdxl-sai,
  moss-iso, moss-sentence, flux sem LoRA > sd15-pixel.
- Nenhum supera o conjunto atual de forma geral; servem para variantes e redesenho pontual.
  Tabela, receitas e ids em `out/sweep/RELATORIO.md`; folhas por asset em `out/sweep/<asset>.png`, visão geral `out/sweep/resumo.png`.
