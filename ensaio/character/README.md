# Ensaio de personagem (fazendeiro jogável)

Objetivo: ver se o `aig` gera um personagem jogável no estilo e escala do `Player.png`
(quadros 32x32, figura ~13x18 px + sombra, contorno (14,7,27), 11 cores).

- `blockout.py`: manequim do fazendeiro desenhado à mão em pixel (3 vistas) -> `out/blockout_32.png`
  e bases ampliadas para img2img em `bases/` (importadas no aig: front `cca5b17ef555`, side `a1dc1e3d5bd3`,
  back `51332d5a197a`, fileira `8bff580e758b`).
- `sheet8.py`: **redução da receita final** (geração sobre folha alinhada -> quadros 32x32 1:1).
- `arms.py`: manequim das ações com braço e mão (c36+), bases `bases/act*_1568x672.png`.
- `player.py`: **folhas no layout do jogo** (c21+): `farmer_Player*.png`, `farmer_Player_Actions*.png`, gifs e prévias.
- `npc.py`: **NPCs** (c27+): manequins, bases e folhas `out/npc_<nome>.png` (`npc.py bases`, `npc.py build`).
- `final.py`: escolhas e saídas antigas (c09-c20) em `out/` (rodar `python3 -c "import final; final.blockout_cells()"` antes, se `out/cells/blockout*.cells.png` faltar).
- `grid.py`: tentativa de voltar a geração 16x à grade do manequim (pior, ver c02).
- `char.py split`: geração -> quadros 32x32 (fundo, figuras, mesma escala, redução, contorno, sombra, pé na linha 22).
- Lotes: `ensaio/runs/cNN.json`, gerações em `ensaio/runs/cNN/`.

## Medidas do Player.png

- figura: 13 px de largura, linhas 5-22 (18 px), sombra (0,0,0,100) nas linhas 21-24, 13x2.
- cabeça 9 linhas (5-13), corpo 9; contorno (14,7,27) por fora e nos detalhes; 10 cores + sombra.
- aig: só o template `sdxl` (base, sem LoRA de pixel) tem canny (`--contours`). moss-pixel tem img2img e inpaint, sem canny.

## Receita que funcionou (folha alinhada à grade)

1. Manequim à mão em pixel no tamanho final (`blockout.py`): mesmo esqueleto do Player.png, cores
   chapadas, contorno (14,7,27), pé na linha 22. Caminhada = poses desenhadas no manequim (o modelo não anima).
2. Folha de **uma vista só** (12 quadros 32x32 em 196x84 células) ampliada **8x** com nearest ->
   1568x672 (`blockout.sheet_base`, `per_view_bases`). 8x = 1 pixel do manequim é 1 pixel nativo da
   LoRA do moss, e 1568x672 é a área em que o img2img do moss trabalha sem reamostrar.
3. `aig import` da base; `moss-pixel` img2img com **denoise 0.55**, prompt:
   `pixel art character sprite sheet of a tiny chibi farmer boy, every frame is the <front view facing the camera |
   side view facing right, standing and walking frames | back view, seen from behind, face not visible, only the back
   of the hat and shirt>, same character in every frame, big head, wide straw hat, red plaid shirt, blue jeans, brown
   boots, simple flat colors, 16-bit RPG farming game sprites, dark outline, plain white background` (~3,5 min/job).
4. `sheet8.py`: reduz por 8 (cor dominante por bloco 8x8, fase da grade pela menor variância), fundo branco
   ligado à borda sai, borda escura vira (14,7,27), quadros saem nas mesmas posições da base (sem recentrar:
   a caminhada não treme), sombra (0,0,0,100) como no Player.png.
5. `final.py`: escolhe os quadros (`PICKS`, `WALK`) e grava `out/`.

Variante de roupa = trocar as cores do manequim (`COL_B`), mesmo prompt com as cores novas.

Comparado com os outros caminhos: txt2img de fileira (c01, c03, c06) dá 3 vistas coerentes, mas o desenho
tem 50-65 px nativos de altura e a redução para 20 px suja (rosto e mãos somem). img2img de 1 vista em 16x
(c04, c07, c08) idem. A folha alinhada evita a redução: o modelo já desenha no tamanho do jogo.

## Layout das folhas do jogo (`scenes/mundo/jogo.tscn`)

- `Player.png` 192x320, células 32x32. Linhas: 0-2 `idle_down/side/up` (6 quadros, 3 fps, laço), 3-5
  `walk_down/side/up` (6, 3 fps), 6-8 `foice_down/side/up` (4, 2 fps, com rastro branco), 9 `desmaiar` (4, de lado).
  O lado olha para a direita; o jogo espelha (`flip_h`) para a esquerda.
- `Player_Actions.png` 96x576 = **2 x 12 células 48x48** (não 2 x 18 de 32): `picareta`, `machado`, `enxada`
  (linhas side, down, up) e `regador` (down, up, side), 2 quadros, 2 fps. Personagem no mesmo lugar da
  célula 32 com 8 px de margem (pé na linha 30).
- Parado original: quadros 2-3 com cabeça e tronco 1 px abaixo (respiração). Ações originais: corpo
  igual ao parado, só a ferramenta e as mãos (2x2 de pele) mudam.

## Saídas no layout do jogo (`out/`, `player.py`)

- `farmer_Player.png`, `farmer_Player_B.png`: mesmo layout do `Player.png`.
  - parado: quadro parado da folha da vista + respiração (`player.bob`: tudo acima do tronco desce 1 px nos quadros 2-3).
  - andando: 6 quadros. Lado: passo A, meio A, cruza, passo B, meio B, cruza (poses novas no manequim:
    `blockout.SIDE_HALF`). Frente e costas: passo A, parado, cruza, passo B, parado, cruza.
  - foice (c43+): corpo com braço gerado (`arms.foice_grids`) + foice e rastro recortados do original, por trás do chapéu.
  - desmaio: parado de lado, agacha, curvado, deitado com o chapéu caído (`blockout.FAINT`).
- `farmer_Player_Actions.png`, `_B` (c36+): corpo gerado com braço e mão (`arms.py`): para cada quadro, a mão vai
  para onde está a mão do original e o braço sai do ombro mais próximo (manga até a metade, pele no resto, mão 2x2),
  sem pintar por cima do corpo. Folha de 1 vista com os 8 quadros de ação + 4 repetidos, receita de sempre.
  Só a ferramenta (sem as mãos antigas) vem do original (`tool_layer(hands=False)`).
  - Chapéu: mão que cairia dentro da aba vai para fora dela e a ferramenta anda junto (`arms.clear_hat`, dx de
    -9 a +9 px; picareta/enxada erguidas de frente e de costas, machado erguido de costas). A ferramenta é
    desenhada por trás do chapéu (aba e copa cobrem).
- Cores travadas por roupa (`player.lock`, `pooled_ramps`): cada pixel recebe a cor mais próxima da rampa
  do seu material (rótulo do manequim no lugar ou vizinho 3x3). Rampa = k-means das cores da geração do
  material nas 3 vistas juntas; cabelo usa a rampa do manequim com o brilho normalizado por quadro
  (resolve preto x castanho). Outros materiais só são normalizados se o quadro foge mais de 20% do brilho
  mediano da roupa. Material que a seed pintou de preto (o `sheet8` troca por contorno: cabelo e calça do lado B, c24)
  volta a ser o material quando mais de 30% dos seus pixels são contorno. Pixel muito escuro fora do cabelo vira contorno (olho).
- Escolhas: `player.PICK` (frente A e B: parado 0, passo A 1, cruza 6, passo B 3), lado: parado = quadro 10.
- Manequins das folhas de lado: `blockout_p6side_32.png`, `blockoutB_p6side_32.png`; bases em `bases/p6*_1568x672.png`
  (aig: lado `5ec7cfc2f82c`, frente `e44ca10c0e9e`, costas `7d1fb12488d7`; B: `6c5f2f78d992`, `1273f108d4bc`, `9a0bd21db7b4`).
- `farmer_Player[_B].gif`, `farmer_Player_Actions[_B].gif`: todas as animações tocando juntas, 4x
  (linhas: parado, andando, foice, desmaio; ações: picareta, machado, enxada, regador; colunas frente/lado/costas).
- `preview.png` (Player: atual, A, B por linha, 1x e 4x) e `preview_actions.png` (ações, 1x e 3x), sobre grama.

## NPCs (c27+, `npc.py`)

- Manequins em `npc.py` com o mesmo esqueleto (pé na linha 21, contorno automático do `blockout.frame`):
  `LADY` (dona da venda, 17 linhas, coque), vaqueiro = poses do fazendeiro com chapéu, gibão e bigode trocados
  (`cowboy`), `KID` (14 linhas: cabeça sem chapéu, corpo 6 linhas). Caminhada: troca a linha das mãos e as
  linhas das pernas (`walk_frames`). Manequins em `out/npc_<nome>_blockout[_4x].png` (parado + poses por vista).
- Bases `bases/npc_<nome>_<vista>_1568x672.png` (aig: dona `6d31beb58346` `d5d72e22aec8` `85a4bf093b01`,
  vaqueiro `b58ed21b8488` `5a46ad986c4b` `533062aa1aad`, criança `5364f1fc953d` `4f94234f4d49` `8e76201babac`;
  frente, lado, costas). Lotes `runs/c27.json`-`c35.json`, um por folha.
- `out/npc_<nome>.png` (192x192, linhas 0-5 do `Player.png`: parado frente/lado/costas com respiração, andando
  frente/lado/costas em 6 quadros como o fazendeiro), `out/npc_<nome>.gif` (4x),
  `out/preview_npcs.png` (fila com fazendeiro e NPCs 1x e 4x em cima; embaixo, linha a linha 1x e 4x).
- Escolhas em `npc.PICK`; cores travadas por material como no `player.py` (`npc.pooled` + `player.lock`).

## Saídas antigas (c09-c20, `final.py`)

- `farmer_idle.png` (96x32: frente, lado direito, costas; layout das linhas 0-2 do Player.png, coluna 0) e
  `farmer_idle_B.png` (camisa lisa creme, calça marrom).
- `farmer_walk_side.png`, `farmer_walk_front.png`, `farmer_walk_back.png` e `_B` (128x32: passo, cruza, passo, cruza) e `.gif` (4x, 150 ms).
- `preview_candidatos.png` (`final.py`): candidatos c05-c20, 1x e 4x. A `preview.png` agora é a do `player.py`.
- `cells/<geração>.cells.png`: os 12 quadros de cada folha gerada (192x64), para escolher outros; `.small.png` = folha inteira reduzida.
- `blockout_32.png`, `blockoutB_32.png`, `blockout_walk_side_32.png`: manequins; `views16/`: tentativa por vista em 16x (pior).

## Log

| lote | modelo | prompt (resumo) | veredito |
|---|---|---|---|
| c01 | moss-pixel 1344x576 n=2 | fileira "front view, side view facing right, back view, the same character", chapéu de palha, xadrez vermelho, jeans, botina | **3 vistas coerentes nas 2 seeds** (mesmo chapéu, camisa, calça; lado olha para a direita). Mas é adulto barbudo, cabeça ~1/3 da altura: reduzido a 20 px vira borrão (rosto some) |
| c01 | moss-pixel 512 | 1 figura de frente | mais cabeçudo que a fileira, ainda barbudo |
| c01 | sdxl-pad 1344x576 | fileira de 3 vistas | folha de sprites com 1 menina anime grande + 7 figurinhas de costas, borda cinza. Vistas erradas, descartado |
| c01 | moss-pixel 1344x576 | fileira "walk cycle, four frames ... side view" | 4 cópias do **mesmo** passo (pernas abertas iguais): personagem consistente, mas sem ciclo. txt2img não faz animação |
| c02 | moss-pixel img2img 0.75, base = manequim (fileira 3 vistas, 16x) | "chibi farmer boy ... super deformed, very big head, tiny body ..." | **melhor geração**: segue a proporção chibi do manequim, menino sem barba, 3 vistas coerentes (pôs suspensório/macacão). Redução para 20 px: box/unfake escurecem (o contorno grosso do modelo mistura), repix guarda o rosto mas fica sujo. Também testei `grid.py` (volta à grade do manequim): ainda escuro, o contorno do modelo tem meia célula |
| c03 | moss-pixel 1344x576 txt2img | fileira de 3 vistas + "super deformed, head as big as the whole body, young beardless face with two black dot eyes, simple flat colors" | **chibi de verdade sem manequim**: menino, olhos de ponto, 3 vistas coerentes (macacão de novo). Com `--strip 10` (tira o contorno grosso antes de reduzir) + repix, a frente fica legível em 21 px |
| c04 | moss-pixel img2img 0.85, fileira | idem c02 | 0.85 já ignora o manequim (figuras grandes, enchem a tela, olhos de anime). Coerente, mas igual a txt2img |
| c04 | moss-pixel img2img 0.7, base = manequim de frente (512, 16x) | "a single chibi farmer boy standing, front view ..." | **melhor frente até aqui**: desenho simples e limpo, proporção do manequim; repix em 21 px fica perto do estilo do Player.png. Próximo: lado e costas com a mesma seed (c07, c08) |
| c05 | moss-pixel img2img sobre **folha alinhada à grade** (`bases/sheet_1568x672.png`: 12 quadros do manequim, 1 px do manequim = 8 px = 1 px nativo da LoRA), denoise 0.55 e 0.7 | "pixel art character sprite sheet of a tiny chibi farmer boy, front/side/back and walking frames ..." | **descoberta da noite**: o modelo redesenha cada pixel do manequim no próprio pixel nativo, e a redução por 8 (`sheet8.py`, cor dominante por bloco) dá pixel art 1:1 no tamanho do jogo, sem borrão. 0.55 mantém posição e silhueta; 0.7 enche de detalhe (chapéu maior, rosto escuro). Problema: na folha mista o modelo troca vistas (costas vira lado e vice-versa) |
| c06 | moss-pixel 1344x576 n=2 | mesmo prompt do c03 | 2 de 2 seeds dão 3 vistas coerentes (receita de fileira repete, como nas plantas). Reduzidas com strip+repix: legíveis, mas mais sujas que a folha alinhada do c05 |
| c07, c08 | moss-pixel img2img 0.7, manequim de lado e de costas (512, 16x), mesma seed do c04 | idem c04 com "side view facing right" / "back view, seen from behind" | gerações bonitas e coerentes com a frente do c04 (costas sem suspensório). Mas reduzir de 32 px da geração para 1 do jogo (4 px nativos por pixel) suja: pior que a folha alinhada. 16x por pixel é ampliação demais (`out/views16/`) |
| c09 | moss-pixel img2img 0.55, folha alinhada só de costas | "... every frame is the back view, seen from behind ..." | 12 de 12 quadros de costas, todos quase iguais ao manequim com acabamento de pixel art (palha com 3 tons, xadrez em faixas). Folha de uma vista só resolve a troca de vistas. Em 0.55 o modelo funciona como "polidor" do manequim |
| c10 | moss-pixel img2img 0.55, folha alinhada só de lado (2 parado + 4 de caminhada, repetidos) | "... every frame is the side view facing right, standing and walking frames ..." | 12 de 12 de lado, olhando para a direita; quadros de passo saem com pernas abertas e os de cruzar com pernas juntas, como no manequim. **Caminhada só sai porque o manequim já tem as poses**: o modelo não anima, só acabamento. Cabelo saiu preto (frente do c05 era castanho) |
| c11 | moss-pixel img2img 0.55, folha alinhada só de frente | "... every frame is the front view facing the camera ..." | 12 de 12 de frente, iguais entre si. Com c09 e c10: **conjunto coerente nas 3 vistas** (mesmo chapéu, cabelo preto, xadrez, jeans). Escolhido para `out/farmer_idle.png` |
| c12 | moss-pixel img2img **0.65**, folhas de frente e de lado | idem c10/c11 | piora: rosto de frente fica franzido (olho de traço), copa do chapéu cresce; na folha de lado o modelo iguala todos os quadros numa pose parada e **perde a caminhada**. 0.55 é o ponto certo |
| c13 | moss-pixel img2img 0.55, folhas de frente e de lado do **manequim B** (só troca de cores: camisa lisa creme, calça marrom, cabelo castanho) | idem, "plain cream shirt, brown trousers, brown hair" | funciona igual: 12/12 na vista pedida, cores do manequim respeitadas (cabelo castanho ficou castanho). Caminhada de lado mais legível que a do A (calça marrom contrasta com a botina). Variante = trocar a paleta do manequim, sem prompt novo |
| c15 | moss-pixel img2img 0.55, folha de lado, 2ª seed | idem c10 | 12/12 de lado e coerentes entre si, mas o cabelo saiu castanho (no c10, preto) e o quadro 0 (parado) ganhou pernas de passo. **A cor de detalhe pequeno varia com a seed**: escolher as 3 vistas com a mesma cor de cabelo ou travar com paleta |
| c16 | moss-pixel img2img **0.45**, folha de lado | idem c10 | quase o manequim com cores mais saturadas (vermelho vivo); guarda cabelo castanho e as poses. Pouco ganho sobre o desenho à mão. Faixa útil: 0.5-0.55 |
| c17-c20 | moss-pixel img2img 0.55, folhas alinhadas de caminhada de frente e de costas (4 poses x 3: passo A, cruza, passo B, cruza; `blockout.WALK_FRONT/WALK_BACK`), roupa A e B | "... every frame is the front view facing the camera, walking frames" / "back view, seen from behind, face not visible, walking frames" | 4 de 4 folhas certas na primeira: 12/12 na vista pedida, poses do manequim mantidas, quadros 0-3 usados. Frente A saiu com cabelo castanho (parado A tem preto). Costas: passo A e B quase simétricos em 18 px |
| c21-c26 | moss-pixel img2img 0.55, folhas alinhadas de 1 vista no layout do jogo (`blockout.SHEETS6`): lado = parado + 6 de caminhada + 3 de desmaio + parado + passo; frente e costas = [parado, passo A, cruza, passo B] x 3; roupa A (c21-c23) e B (c24-c26) | prompts do c10/c17/c18 e c13/c19/c20, lado com "standing, walking and falling frames" | 6/6 folhas na vista pedida, poses do manequim mantidas, incluindo meio-passo e desmaio (o deitado vira deitado com chapéu ao lado). Quadro 0 do lado (A) ganhou pernas de passo: uso o parado do quadro 10. Frente A: cruza do 1º grupo saiu de suspensório, uso o do quadro 6. Cabelo voltou a variar (lado B: cabelo e calça pretos): travado com `player.lock`. Travar na paleta pura do manequim (13 cores) apagava o xadrez e o rosto; a rampa por material tirada das 3 vistas juntas guarda o acabamento e iguala as vistas |
| c27-c35 | moss-pixel img2img 0.55, folhas alinhadas de 1 vista dos **NPCs** (`npc.py`): frente/costas = [parado, passo A, cruza, passo B] x 3; lado = parado + 6 de caminhada + parado + 4 | "pixel art character sprite sheet of <desc>, every frame is the <vista>, standing and walking frames, ..." com desc da dona (grisalha de coque, vestido florido rosa, avental), do vaqueiro (chapéu de couro de aba virada em meia-lua, gibão, bigode) e do menino (camiseta amarela, short azul, descalço) | 9/9 folhas na vista pedida, 1 seed cada, poses mantidas. **Dona** (c27-c29): boa; no lado o avental saiu escuro (a trava devolve), nas costas as florzinhas viraram manchas maiores. **Vaqueiro** (c30-c32): o modelo trocou a meia-lua por chapéu de caubói comum e escureceu tudo; quadro 0 das costas saiu de frente (uso o 4). Cabelo preto vira contorno no `sheet8` e a trava jogava no tom claro da rampa (mancha cinza na nuca): rampa do cabelo sem o tom claro. **Criança** (c33-c35): boa na primeira, 3 px mais baixa que o fazendeiro. Trava: `player.lock(weighted=True)` normaliza o cabelo pela média por pixel do manequim (com a média das cores distintas o grisalho caía todo no tom escuro) |
| c36-c41 | moss-pixel img2img 0.55, folhas alinhadas de 1 vista com os 8 quadros de ação do manequim com braço (`arms.py`), roupa A (c36-c38) e B (c39-c41) | prompts de sempre + "action poses with one or both arms raised or stretched out, empty hands" | o modelo segue o braço de 1 px e o engrossa em manga + mão (de frente, braço erguido fica bem legível). Montagem: corpo gerado travado + ferramenta do original por trás do chapéu. Resolve as mãos com a pele antiga e a ferramenta por cima da aba. B (c40): enxada erguida de frente ganhou um 2º braço esticado para a direita (o modelo inventou) |
| c42 | idem c40 (ações de frente, roupa B), 2ª seed | idem | a 2ª seed também pôs braço extra nos quadros da enxada (índices 4-5). Solução na montagem: enxada e picareta têm a mesma pose (mesmas mãos no original), então o quadro gerado da picareta serve para as duas em todas as vistas e roupas (`build_actions`, grade igual -> mesmo quadro). Fica a seed do c42 (`player.SEED`) |
| c43-c48 | moss-pixel img2img 0.55, foice (Player.png linhas 6-8) com braço no manequim (`arms.foice_grids`, mesma regra das ações), 1 folha por vista (4 quadros x 3), A (c43-c45) e B (c46-c48) | prompt das ações | braços seguidos como nas ações. c43 rodou 2x por engano (2 cadeias de jobs; a 2ª foi morta, 1 job extra de c44 rodou sem ser copiado): seed 1875635193 pôs braço extra no quadro 1, uso a 1348472654 com o quadro 2 da 2ª cópia (`player.FIDX`). Montagem: corpo gerado + só a foice e o rastro do original, foice por trás do chapéu; quadro 4 (sem foice) = parado |

## Problemas em aberto

- NPCs: no c30-c32 o modelo trocou o chapéu de couro sertanejo por um de caubói. Resolvido sem GPU em `npc.cowboy_post`:
  depois da trava, as linhas do chapéu vêm do manequim (com 1 tom claro no alto) e gibão/calça trocam de rampa pelo
  mesmo índice (`COW_RECOLOR`: gibão caramelo, calça azul desbotado). O chapéu fica mais chapado que o resto
  (desenho à mão, sem acabamento do modelo) e o gibão caramelo fica perto do tom de pele.

- Rosto: em 0.55 o rosto é o do manequim (2 olhos de 1 px); o modelo não melhora detalhe de 1 px. Mãos somem às vezes no lado.
- Cor de cabelo varia com a seed (preto em c09-c11, castanho em c15/c16, preto no lado B c24): travada por `player.lock` nas folhas do jogo.
- Caminhada: 6 quadros (c21+), mas frente e costas repetem o parado como meio-passo; passo A e B quase iguais nas costas.
- Ações (c36+): só 1 mão por quadro quando o original só mostra 1; o braço é um traço de 1 px engrossado pelo modelo
  e nem sempre encosta no cabo.
- Rosto de frente quase sem olhos na geração (c22); o travamento não inventa olho.
- Foice/desmaio não têm sombra própria diferente; desmaio deitado: rosto para baixo (rotação do manequim de lado).
- Canny (ideia P10 do advisor): só o template `sdxl` base tem `--contours`, sem LoRA de pixel; não testei porque a folha
  alinhada já prende a pose e o canny não resolveria a escala.
- A fileira importada `8bff580e758b` (c02, c04) é anterior à troca de âncora do manequim (pé na linha 21): 1 px acima do `bases/row_1344x576.png` atual.
- Licença: moss-pixel (LoRA do Civitai) não conferida (mesma pendência dos objetos).
