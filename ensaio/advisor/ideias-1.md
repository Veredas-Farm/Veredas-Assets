# Ideias 1 (advisor)

## Medição que muda a prioridade

- B1. `out/e02/v2-sh1.5.png`: 276 cores no total, 69 só na grama, cor dominante cobre 5% da grama. `out/mapview/original-crop.png`: 105 no total, 12 na grama, dominante 83%. A "paleta compartilhada" não está travando nada, e a grama virou camuflagem. O original erra na emenda, mas acerta na leitura (base chapada + tufos). O novo acerta a emenda e perde a leitura.

## 1. Terreno com cara de feito à mão (quase tudo CPU)

- P1. Paleta mestre antes de qualquer geração nova: ~32 cores, rampas de 4-5 por material, sombra puxando para azul/roxo e luz para amarelo. Quantizar tudo nela em OKLab, sem dithering. Sucesso: <= 6 cores por material, <= 40 no mapa. GPU: 0.
- P2. Separar base e detalhe: posterizar a textura em 2-3 níveis, apagar ilhas < 3 px, exigir dominante >= 60% do topo. Sucesso: fração de pixels com vizinho horizontal diferente perto de 0,10 (hoje 0,27; original 0,08). GPU: 0.
- P3. Tufos, flores, pedras e cupinzeiro como sobreposição em espaço de tela, numa segunda `TileMapLayer`. Textura projetada achata 2:1 tudo que deveria ficar em pé; é isso que denuncia "textura projetada". Folha com sdxl-pad em fundo liso, recorte, redução. ~6 imagens, 15 min.
- P4. Borda da grama desenhada em espaço de tela: lâminas em pé pendendo nas arestas SE/SO + linha escura de 1 px embaixo. Substitui o ruído projetado e a sombra borrada de `v2-sh1.5`. GPU: 0.
- P5. Água: 4 quadros deslocando a textura sem emenda (deslocamento = período/4) + linha de espuma na margem. Tile animado do Godot. GPU: 0.
- Rejeito: dithering em tile 32x16 (vira chuvisco com a câmera andando); AA nas arestas do losango (quebra a emenda); falésias agora (exige ordenação e colisão no jogo, o mapa é plano).

## 2. Variedade sem quebrar a grade

- P6. Variedade em baixa frequência: terrenos-mancha (capim seco, grama escura, terra batida) com as mesmas 16 transições, pintados por ruído num script gerador. Variante aleatória por tile de textura ruidosa só soma ruído.
- P7. Decalques por hash da célula (ruído azul, densidade por terreno), determinístico.
- Armadilha: probabilidade de terreno do Godot sorteia por célula e destrói a coordenação `(x%g, y%g)`. Com g > 1 o mapa precisa ser escrito por script (EditorScript) ou g = 1 com alternativas. Decidir isso antes de gerar mais tiles.
- Limitar pares de transição a uma cadeia (água < terra < grama < mancha): 3 pares x 16, não N².

## 3. Objetos, plantações, personagem

- P8. Blockout + canny: renderizar caixas/cilindros com `tools/iso.py` em 1024, canny, sdxl-pad. Garante ângulo e pegada no losango para carreta, árvore e plantas. 2 sementes por objeto, ~1 h para o lote.
- P9. Estágios de crescimento: gerar só o maduro; os anteriores por img2img (denoise 0,4-0,5) sobre silhuetas reduzidas do próprio maduro. Mesma semente e paleta. ~4 imagens por cultura.
- P10. Personagem: não há sprite base em `Veredas-Assets/`. SDXL não entrega ciclo de caminhada coerente. Caminho defensável: manequim de blocos em 4 direções (canny) para o desenho, quadros de caminhada por img2img de baixo denoise sobre manequim animado à mão, limpeza manual. É o item mais caro e mais incerto, deixar por último.
- P11. Ícones: 4 sementes x 11 itens em sdxl-pad (~1,5 h), redução, paleta mestre, contorno escuro colorido de 1 px por regra.
- Rejeito: flux (8 min por imagem não paga a noite); folha de giro sem ControlNet (pose e proporção variam). O ControlNet tile do xinsir serviria para repintar asset próprio ampliado, mas pede template novo na config do lab.

## 4. Variantes de mapa para propor

- M1. Mesmo traçado, só troca de pele (comparação justa).
- M2. Caminhos orgânicos com as transições de canto + manchas + decalques.
- M3. Uma vereda de verdade: córrego, faixa de grama úmida escura, buritis na margem. É o nome do jogo e hoje não aparece.
- M4. Troca de paleta para a seca (grátis depois de P1).

## 5. Riscos

- R1. `isocheck` mede validade, não beleza. Juiz final: `tools/mapview.py` no mapa real, no zoom do jogo, lado a lado com o original, com construções por cima.
- R2. Terreno com mais contraste local que os sprites engole personagem e plantação. Exigir contraste do terreno menor que o dos objetos.
- R3. Construções e árvores atuais têm contorno e sombreado próprios; terreno novo com elas pode ficar pior que o conjunto atual. Testar cedo.
- R4. Sulcos da terra arada só num eixo: conferir se o jogo gira canteiros.

## Ordem sugerida

- P1 -> P2 -> P4 -> mapview lado a lado (0 GPU). Só depois P3, P8, P11. P10 por último.
