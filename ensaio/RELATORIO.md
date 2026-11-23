# Relatório do ensaio de assets (noite de 19 para 20/11/2026)

Detalhes de cada passo em `README.md` (log), `objects/README.md` (objetos) e
`character/README.md` (personagem). Material pronto para o jogo em
`entrega/` (ver `entrega/LEIAME.md`).

## Resumo

- A grade isométrica está resolvida e provada no Godot: o mapa pintado pelo
  próprio Godot com o TileSet novo bate pixel a pixel com o render do ensaio.
- Terreno novo: grama, trilha, palha e grama úmida com 6 variantes cada,
  transições orgânicas por canto (terrain set do Godot), água com espuma,
  terra arada. As cores ficam presas à paleta dos tiles atuais, para casar
  com as construções que já existem.
- Objetos (agente): 7 cultivos com estágios, cagaita com estações, carro de
  boi e carroças, 11 ícones.
- Personagem (agente): fazendeiro 32x32 nas 3 vistas, parado e andando (4 quadros),
  2 roupas. Receita: manequim de pixel desenhado à mão, ampliado 8x, img2img
  no moss-pixel com denoise 0.55, redução por bloco. Gerar do zero vira
  borrão ao reduzir. Faltam 6 quadros por
  direção como no `Player.png`.
- Personagem nos layouts do jogo (2ª rodada): `Player.png` (parado, andando
  6 quadros, foice, desmaio) e `Player_Actions.png` (48x48, 4 ferramentas),
  roupas A e B, cores travadas por material. Ações usam o corpo parado com a
  ferramenta recortada do sprite atual (mãos com a pele antiga).
- 3 NPCs (dona da venda, vaqueiro, criança), parado e andando nas 3 vistas.
  Vaqueiro com chapéu de couro pintado à mão sobre a geração.
- Cupinzeiros (alto e baixo) espalhados na palha da variante G; ícone de
  melancia.
- Sete variantes do mapa real (A a G); a G junta tudo com água por canto.
- O `jogo.tscn` tem um bug de `texture_origin` que desenha linhas escuras em
  degrau na grama; aparece no print do Godot.

## Mapas (`entrega/mapas/`, metade do tamanho)

| Variante | O que muda | Julgamento |
| :-- | :-- | :-- |
| A | troca de pele, mesmo traçado | limpa, mas a trilha continua em degrau |
| B | trilha com borda orgânica (transições por canto) | base mínima recomendada |
| C | B + manchas de palha, flora atual espalhada, sombras, tufos, pedras | opção segura |
| D | C na seca (grama oliva, mais palha) | boa como estação do ano, não como padrão |
| E | C + vereda: córrego do lago até uma nascente, grama úmida, buritis | a mais "cerrado"; recomendada |
| F | E + roça com cultivos, carro de boi, cagaitas | vitrine de tudo junto |
| G | F com água como terreno de canto: margem orgânica com espuma no lago e no córrego | resolve a serrilha da margem; recomendada como base da água |

`compare.png` mostra o mesmo recorte no original e em A a E;
`compare-G.png`, original, E e G lado a lado. Na G a água fica no nível da
grama (sem o barranco de terra da E): margem mais natural, menos relevo.

## Como foi feito

- Terreno por projeção: textura vista de cima (IA) → emenda periódica →
  projeção no bloco isométrico canônico com superamostragem 8x → redução por
  face com as máscaras canônicas → rampa curta de 4 tons por material
  (sombra fria, luz quente) → limpeza de pixel isolado.
- Variantes intercambiáveis: faixa de borda igual em todas, miolo variado;
  qualquer arranjo emenda.
- Transições: ruído que some nas arestas, por canto (16 casos), 3 variantes.
- Validador (`tools/isocheck.py`): silhueta, semitransparência, cores,
  costura (e "treliça", quando a borda fica lisa demais).
- Godot: TileSet gerado (`tools/godot_tileset.py`), pintura com
  `set_cells_terrain_connect`, print com Xvfb, diff por pixel
  (`tools/godot_diff.py`).
- Decals: tufos e flores procedurais (melhores que os da IA nesse tamanho);
  pedras recortadas de uma folha do sdxl-pad.

## Modelos

- sdxl-pad: as melhores texturas de terreno vistas de cima. Ruim para água
  (ilhas, vitórias-régias) e solo vermelho (vira calçamento).
- moss-pixel: o melhor para objetos, cultivos e ícones (agente); texturas
  boas também.
- sdxl-pixel-lcm: ruído. Flux: lento e errou as carroças.

## Crítica do advisor (2ª rodada)

- Aplicado: grama úmida mais sutil, clareiras no espalhamento, menos pedras e
  troncos, buritis em touceiras, lago mais escuro longe da margem.
- Margem em serrilha: resolvida na G (água por canto, testada no Godot).
- Ponte de tábuas onde o córrego cruza a trilha (G) e roça com carreadores
  entre as fileiras (F e G).
- Em aberto: copas das árvores atuais escuras demais (sprites do jogo).

## Bugs e riscos

- Licença: o sdxl-pad (texturas do kit `terreno/` e pedras) proíbe vender
  imagens sem consentimento do autor. O jogo não é comercial: os dois kits
  (`terreno/` e `terreno-moss/`) ficam à escolha.
- `jogo.tscn`: `texture_origin` misto nas gramas e na terra (ver LEIAME).
- Godot não tem tile para três terrenos no mesmo vértice: manchas precisam
  de folga da trilha (o gerador do mapa já respeita).

## Decisões pendentes

Ver a mensagem final da sessão.
