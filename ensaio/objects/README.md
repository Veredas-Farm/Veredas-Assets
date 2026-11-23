# Ensaio de objetos (itens, plantações, árvore, carreta)

Objetivo: achar modelo + prompt + redução que dão pixel art no tamanho do jogo
(ícone 32x32, planta num tile 32x16, árvore 48-100 px, carreta ~ caminhonete).

- `pipeline.py`: fundo -> recorte -> variantes de redução -> paleta -> contorno -> tela final + anchor.
- `specs/oNN.json`: lotes enviados ao `tools/gen.py`; gerações em `ensaio/runs/oNN/`.
- `out/`: folhas de prévia finais.

## Medidas dos assets atuais

- itens: 32x32, objeto ocupa ~26-30 px, contorno escuro colorido (marrom/roxo), sombra interna.
- milho (`corn_spritesheet.png`): 6 estágios, pé em y~155, larguras 17-38, maduro ~34x77.
- caminhonete (`carreta.png`): 2 vistas 3/4, cada uma ~80x60 px.
- árvores: 35-110 px de largura, 88-107 de altura.

## Receita atual (melhor até agora)

Modelo: **moss-pixel** (MOSS Turbo + LoRA pxl8x) para tudo. sdxl-pad, sdxl-pokemon, sd15-* e
flux ficaram atrás (ver log). Licença do moss: conferir no `aig style show moss-pixel-lora`
(a do sdxl-pad proíbe vender imagens sem consentimento do autor).

| tipo | prompt (molde) | tamanho | redução |
|---|---|---|---|
| ícone 32x32 | `game inventory item icon, simple bold shapes, few large elements, cozy farming game item, thick dark outline, centered, plain white background: <1 a 3 objetos grandes>` | 512x512 (64 px nativo, ~2 min) ou 1024 | `pipeline.py icon --variants box --outline auto --palette items_spritesheet.png` (caixa 28, tela 32) |
| plantação (estágios) | `sprite sheet of <planta> growth stages in one horizontal row, five stages from a small sprout to <maduro>, each stage standing on a small patch of soil, side view, farming game crop sprites, evenly spaced, plain white background` | 1344x576 | `pipeline.py row --variants box --outline auto --gap 6` + paleta milho+itens tol 0 + `strip_soil` + estágio seco (`wither`) — ver `final.py crops` |
| árvore | `a single small brazilian cerrado <árvore> tree: short crooked twisted trunk with corky bark, irregular rounded crown made of several dense clumps of small olive green leaves, <frutos>, muted colors, game object sprite for an isometric farming game, three-quarter view, centered, plain white background` | 1024 | `pipeline.py ground --fit 60x76 --variants box --outline none --palette pequi+baru --palette-tol 0` |
| veículo/carreta | `<objeto>, farming game object sprite, three-quarter isometric view from above, dark outline, centered, plain white background` | 1024 | `ground --fit 60x44 --variants box --outline auto` + paleta caminhonete+árvores tol 30; pé = centro da área no chão (`final.py`) |

Pipeline (`pipeline.py`): fundo (flood fill da borda com tolerância + vãos internos grandes) ->
erosão de 3 px (tira o halo do antialias) -> recorte -> fundo preenchido com a cor do pixel
do objeto mais perto -> redução (box = média com alfa pré-multiplicado) -> alfa binário e
limpeza de pixel solto -> quantização (20 cores) -> contorno 1 px (88% marinho (21,29,40) +
12% da cor vizinha) -> paleta do asset vizinho -> tela final (centro ou pé embaixo) + `.json`
com `anchor`.

Arquivos finais: `python final.py` regrava `out/` (ícones, plantações, árvore, carretas);
`scene.py` monta a cena isométrica de conferência (`out/scene.png`).

## Log

| lote | modelo | prompt (resumo) | veredito |
|---|---|---|---|
| o01 | sdxl-pad | cagaita (3 frutos), facão | cagaita vira folha de sprites (vários objetos), fundo lilás; facão ok mas parece faca |
| o01 | moss-pixel | idem | **melhor**: 1 objeto, fundo branco, contorno escuro, cara de Stardew; cagaita parece limão |
| o01 | sdxl-pokemon | cagaita | errou o objeto (flores) |
| o01 | sd15-survivors | cagaita | lixo (bolo de folhas) |
| o02 | moss-pixel | cagaita (amarelo-claro, coroinha seca), feijão carioca (monte + vagem), soja (ramo com vagens) | cagaita boa; feijão/soja com muitos elementos pequenos viram ruído em 32 px |
| o02 | moss-pixel | **estágios numa fileira** (cana, feijão, mandioca) | **funciona muito bem**: 5 estágios coerentes, mesma luz e paleta, base de terra separada |

Notas da redução (ícone 32x32):
- variantes testadas: box (média), repix (`repixelate --pixel-size N`, grade imposta), repix2 (grade nativa e depois box), PixelOE contrast, unfake dominant.
  repix e unfake ficam mais nítidos; box e repix2 borram; PixelOE estoura os claros (lâmina branca).
- fundo: preencher o fundo com a cor do pixel do objeto mais perto (não magenta), senão a borda pega a cor do fundo.
- contorno: os itens atuais usam quase só o azul-marinho (21,29,40)/(16,20,31) por fora. `--outline auto` = 25% vizinho + 75% marinho.
- paleta: os itens usam 29 cores no total (10-16 por item). `--palette items_spritesheet.png` com tolerância
  28 aproxima as cores sem matar matizes novas (o amarelo da cagaita fica).
| o03 | sd15-pixel | cagaita, facão (n=2) | rápido (10 s), mas facão virou guerreiro com espada; cagaita vira maçã. Descartado |
| o03 | moss-pixel | cana e mandioca maduras (1 planta) | bonitas; mas o modo `grow` (estágios = a planta madura encolhida) fica pior que a fileira: broto vira moita miniatura |
| o03 | moss-pixel | árvore cagaita (copa redonda) | "pirulito" de pomar, verde saturado; com a paleta das árvores (tol 0) encaixa na cor, mas a forma não é de cerrado |
| o04 | moss-pixel | carro de boi, reboque com feno (3/4 de cima) | ambos bons e no ângulo da caminhonete; carro de boi saiu com 4 rodas (o real tem 2 rodas maciças) |
| o04 | sdxl-pad | carro de boi | virou diorama (bloco isométrico com boi e árvores). pad não serve para objeto isolado |
| o04 | moss-pixel | ícones com "simple bold shapes, few large elements": feijão (1 vagem), arroz (feixe), cana (2 gomos cruzados) | bem melhores em 32 px que o monte de feijão/soja do o02; arroz ainda fino demais |
| o05 | moss-pixel | árvore cagaita v2 ("tronco torto com casca de cortiça, copa irregular em tufos, muted colors") | **boa**: cara de cerrado, tronco retorcido; copa meio rala |
| o05 | sdxl-pad | idem | árvore grande com chão de areia embaixo; descartada |
| o05 | moss-pixel | fileira de estágios: arroz, melancia, soja | todas boas; melancia saiu com 4 estágios |

Notas (continuação):
- ícones: **box + contorno auto + paleta dos itens** ficou mais limpo; repix fica serrilhado em coisas finas (arroz, cana); unfake fica no meio.
- plantas: box também; `--palette corn+items` com tol 0 deixa os verdes sóbrios como o milho. A terra marrom da base sai (`strip_soil`), o tile arado é a terra.
- árvore: paleta pequi+baru com tol 0, sem contorno extra (as árvores atuais não têm contorno marinho).
| o06 | moss-pixel | carro de boi v2 ("two very large solid disc wheels", fueiros) n=2 | ainda 4 rodas raiadas; os fueiros (estacas) saíram. O modelo não conhece carro de boi |
| o06 | moss-pixel | árvore cagaita v3 (copa em tufos densos) | **melhor árvore**: tronco torto + copa cheia; frutos esverdeados |
| o06 | moss-pixel | ícones soja (1 vagem) e capim (feixe amarrado) | capim bom; soja parece ervilha (igual ao ícone de ervilha que já existe) |
| o07 | moss-pixel 512x512 | ícones cagaita, facão | **512 serve para ícone**: grade de 8 px -> asset de 64 px, metade do tempo (~2 min); cagaita ótima, facão virou faca/espada |
| o07 | moss-pixel 1344x576 | fileira de cana (formato largo) | boa, mais "moita de cana"; o formato largo combina com a fileira |
| o07 | moss-pixel | fileira de mandioca, outra seed | consistente com a do o02: a receita da fileira se repete entre seeds |
| o08 | flux-pixel | carro de boi de 2 rodas | entende 2 rodas e o ângulo iso, paleta sóbria, mas pôs um boi junto (CFG 1 ignora negativo); 9 min. ComfyUI caiu no job moss deste lote |
| o09 | sdxl-pad 1344x576 | fileira de cana | campo de colmos iguais, sem estágios. pad não faz folha de estágios |
| o09 | sd15-pixel 768x384 (n=2) | fileira de cana | lixo (vasos de planta, bonecos verdes) |
| o09 | moss-pixel 1344x576 | fileira de cana (3ª seed), capim | as duas boas: moss é o único que faz estágios; 3 de 3 seeds de cana deram certo |
| o10 | moss-pixel n=2 | carro de boi v3 ("one single axle in the middle with exactly two huge ... wheels", "bed balanced on that axle") | **2 rodas nas duas seeds**; rodas raiadas (não maciças), timão para a direita: espelhado no `final.py` para casar com a caminhonete |
| o10 | flux-pixel | carroça vazia ("unhitched, nothing attached") | 4 rodinhas e sombra no chão; flux não compensa os 8-9 min |
| o11 | moss-pixel | árvore v3 (2 seeds a mais), fileira de melancia larga | árvore: 3 de 3 seeds no mesmo estilo -> 3 variações para o mapa. Melancia: 5 estágios, os 2 últimos encostados (resolvido no corte: `expect`, divisas igualmente espaçadas) |
| o12 | moss-pixel n=2 | carro de boi com "solid wooden wheels made of three thick planks, no spokes" | 1 de 2 com 2 rodas; as rodas continuam com raios. Solução boa o bastante: o10 espelhado |
| o12 | moss-pixel 512 | soja: monte de grãos + 1 vagem seca | **bom**, não confunde com ervilha |
| o12 | moss-pixel 1344x576 | fileira de feijão com 6 estágios, "the last stage a dried withered brown plant" | **funciona**: o estágio seco gerado é melhor que recolorir o maduro |
| o13 | moss-pixel img2img (base = árvore v3, denoise 0.6) | mesma árvore: florida, seca, só folhas | **funciona muito bem**: mesmo tronco e silhueta, só muda a copa -> estados por estação. (moss não tem variante canny; `--contours` falha) |

Notas (continuação 2):
- árvore com flores/frutos pequenos: `box` borra os pontos claros; `unfake` (cor dominante) mantém. Árvores usam unfake.
- a paleta das árvores atuais não tem branco; `final.py` acrescenta 2 cremes para as flores.
| o14 | moss-pixel 1344x576 | fileiras de cana e mandioca com estágio seco no fim | cana: 6 estágios certos; mandioca: 5 (4 + seco). O seco gerado vai para o palha do milho com `wither` (a paleta deixava vinho escuro) |
| o15 | moss-pixel 512 n=2 | facão "wide flat blade that gets wider toward the rounded tip" | facão grande com ponta em gancho, lê como facão; o do o01 continua mais clássico |
| o15 | moss-pixel img2img 0.6 | estações para a 2ª seed da árvore | florida boa; "seca" manteve frutos marrons nesta seed || o16 | moss-pixel 512 | ícones novos de produto: rapadura, farinha de mandioca (saco), pequi | 3 de 3 bons na primeira tentativa: a receita de ícone em 512 generaliza |

## Saídas (`out/`)

- `icons/*.png` (32x32), `icons_sheet.png`, `icons_preview.png` (itens atuais em cima, novos embaixo, 4x).
- `crops/<planta>.png` + `.json`: estágios lado a lado em células iguais (cana 32x72, mandioca 32x64,
  feijão 32x40, arroz/soja/capim 32x48, melancia 32x32); o `.json` traz `rect` e `anchor` (pé) de cada estágio.
  O último estágio é o seco. `crops_preview.png` mostra o milho atual em cima para comparar.
- `objects/*.png` + `.json` (`anchor`): árvores cagaita (3 formas + estações florida/seca/só folhas), carro de boi
  (2 rodas), carroça de 4 rodas, carroça com fueiros, reboque com feno. `objects_preview.png`.
- `scene.png`: mapa isométrico com os tiles de `spritesheet.png`, árvores e caminhonete atuais, jogador e os novos.

Godot: o `anchor` é o pixel do sprite que vai no centro da célula. Com `Sprite2D.centered = false`,
`offset = -anchor`; com `centered = true`, `offset = (w/2, h/2) - anchor`.

## Problemas em aberto

- Ícone em 32 px perde coisas finas (feixe de arroz, folhas de cana): prompt com poucas formas grandes ajuda; o arroz e a cana
  que já existem no `items_spritesheet.png` são melhores que os novos.
- Carro de boi: o moss não conhece; "single axle ... exactly two wheels" dá 2 rodas em ~3 de 4, mas sempre com raios (o real tem roda maciça).
  Inpaint (`aig job add --mask`) nas rodas não foi testado.
- Estágios: a quantidade nem sempre bate com o prompt (pedi 5/6, veio 4/5 às vezes). O corte `expect` resolve quando
  os estágios estão igualmente espaçados; conferir a folha antes de usar.
- O primeiro estágio às vezes guarda um pouco de terra (o `strip_soil` usa uma faixa fixa na base).
- Escala: plantas e carretas seguem o milho e a caminhonete atuais, que já são grandes perto do jogador (16x24).
- Licença: moss-pixel (LoRA no Civitai) não foi conferida; sdxl-pad não permite vender imagens sem consentimento.
- O ComfyUI caiu uma vez (job do o08); o job foi refeito no o10.
| o17 | moss-pixel 512 | ícone melancia (faltava; mandioca já existe no jogo) | bom na 1ª |
| o18 | moss-pixel 1024 | cupinzeiros (alto cônico, baixo em domo) | 2 de 2 bons; reduzidos a 24x28 e 28x18 com a receita de carreta |
| o19 | moss-pixel 1024 | ipê-amarelo florido (receita de árvore, copa de flores amarelas) | árvore boa, mas flores grandes e copa aberta com folhas verdes; vira `ipe_amarelo_aberta` |
| o20 | moss-pixel 1024 | cerca de mourões com arame farpado, 5 postes em diagonal | **boa**: postes e arame legíveis; não saiu torta, mas serve |
| o21 | moss-pixel 1024 | pilão de madeira com mão de pilão | **boa na 1ª**, lê bem em 26x28 |
| o22 | moss-pixel 1024 | moinho d'água na beira do córrego | roda e casinha ok, mas vem com poça, pedras e grama colados (água fixa no sprite); vira `moinho_agua` |
| o23 | moss-pixel 1024 | ipê-roxo florido | **boa na 1ª**, copa densa e roxa |
| o24 | moss-pixel 1024 | moinho "dry brown ground, no water, no stones" | **melhor**: roda legível, só um chão de terra irregular; vira `moinho` |
| o25 | moss-pixel 1024 | ipê-amarelo "tiny flowers, no green leaves" | **melhor**: copa cheia de flores miúdas, lê como ipê; vira `ipe_amarelo` |

Lote 2 (`final2.py`, prévia `out/objects2_preview.png` com o pequi ao lado, 3x):
- ipês: `unfake` + paleta pequi/baru com 4 tons de amarelo ou roxo acrescentados, tol 0, caixa 76x92 (pequi 84x102).
  Para flores miúdas o prompt "tiny flowers, no green leaves" ganha do "dense clumps of flowers" (o19 deu flores enormes).
- cerca (`cerca_aroeira.png`, `_esp.png` espelhada): peça de 32 px de largura que **emenda**; a peça seguinte vai em
  `next` do .json (+32,-16 na diagonal para cima; a espelhada em -32,-16). Feita cortando a geração em vãos de poste
  (só arame), cisalhando a inclinação de 0,29 para 0,5 (2:1 do grid) e reduzindo (box, sem contorno extra; o contorno da geração basta).
  3 postes por peça (~10 px entre eles). Arame some em parte (fino demais em 1x).
- pilão 26x28, moinho 58x56 (pé em y=47, no meio da base), `moinho_agua` 62x58. Pequenos/médios: receita da carreta (box, contorno auto, paleta carreta+árvores tol 30).
- Pé do moinho e do pilão = centro da base. Moinho: a roda fica à esquerda, o chão de terra do sprite não casa com o tile.

## Fases por inpaint

Objetivo: o mesmo objeto em várias fases (estação, flor, fruto) com tronco, silhueta de base e
ponto de pé estáveis. Script: `phases.py` (`mask`, `build`); gerações em `runs/o26`-`o32`.

Receita:
- O `moss-pixel` não tem variante de inpaint (`moss-pixel` -> `moss-pixel-img2img`, sem `inpaint:`).
  Usei o template `moss` com `--base <id> --mask <png>` (vira `moss-inpaint`: MOSS Turbo **sem a LoRA
  pixel**, denoise 1.0, 8 passos, `--feather 16`; 8 nos sprites do jogo). Prompt começa com
  `pixel art, ...` no lugar do gatilho `pxl8x`. O contexto em pixel art em volta da máscara basta:
  a copa nova sai na mesma grade e no mesmo estilo.
- `tools/gen.py` aceita `"mask"` (caminho relativo a `ensaio/`) e `"feather"` no spec.
- Máscara (`specs/masks/<arvore>.png`, 1024): pixels saturados do objeto (flor/folha; nos sprites do
  jogo, os verdes), sem as pétalas caídas, fechados (12), buracos preenchidos e dilatados 28 px
  (16 nos sprites). O tronco abaixo da base da copa fica de fora.
- Redução com geometria fixa: a janela de recorte (1024) e o fator vêm da fase base; as outras fases
  usam a mesma janela e o mesmo fator. O `unfake` e o `repixelate` aparam bordas conforme o conteúdo,
  então a fase reduzida é encaixada na grade da base pelo deslocamento que mais casa o tronco
  (`register`) e os pixels fora da copa são copiados da base: tronco idêntico, mesma tela, mesmo `anchor`.
- Paleta: árvores (pequi+baru) tol 0; cores extras de flor só nas fases com flor (amarelo/roxo/creme);
  `fruto_verde` e `folhada` da cagaita ganham 2-3 verdes (sem eles o verde-limão vira amarelo e o
  fruto verde parece maduro).
- Sprites do jogo (pequi, baru): ampliados 8x (nearest) numa tela branca 1024 (`specs/bases/*_8x.png`,
  `aig import`), inpaint da copa, redução por box 8x8 na janela exata do sprite, paleta do próprio
  sprite (+ extras), sprite original colado fora da copa. Mesmo tamanho e `anchor` do original.
- Duas reduções por fase: `<arvore>_<fase>.png` (unfake nos ipês e na cagaita, como os finais;
  box nos sprites do jogo) e `<arvore>_<fase>_repix.png` (`repixelate --pixel-size <fator>`).

| lote | modelo | o quê | veredito |
|---|---|---|---|
| o26 | moss inpaint vs moss-pixel img2img 0.7 | ipê-amarelo seco | **inpaint ganha**: tronco intacto, galhos saem dele; img2img redesenhou o tronco (outra cor e forma) |
| o27 | moss inpaint | ipê-amarelo verde e brotando, ipê-roxo seco | 3 de 3 bons na 1ª; verde saturado (a paleta acerta) |
| o28 | moss inpaint | ipê-roxo verde e brotando | bons; o verde fica escuro depois da paleta |
| o29 | moss inpaint | cagaita (base o11, maduro) florida e fruto verde | florida ótima; fruto verde com bolas demais. A copa fica mais redonda que a base (o img2img 0.6 do o15 guarda melhor os tufos) |
| o29/o30 | moss inpaint | cagaita folhada | ComfyUI caiu no 1º; refeita no o30: copa mais aberta, boa |
| o30 | moss inpaint (base = sprite 8x) | pequi florido, fruto verde, folhado | funcionam; a copa perde o desenho em camadas do sprite original e as folhas saem maiores |
| o31 | moss inpaint (base = sprite 8x) | baru florido, fruto verde, maduro | florido e maduro (vagens marrons) bons; no fruto verde os frutos somem no verde da copa em 1x |
| o32 | moss inpaint | cagaita fruto verde v2 ("a few ... pale green fruits half hidden") | frutos somem na redução; fica a v1 (o29) |
| o33 | moss inpaint (sprite 8x) | pequi florido v2: "tiny cream-white ... small fluffy pompoms of stamens in small clusters, much smaller than the leaves" | **boa na 1ª**: flores miúdas e numerosas; substitui a do o30 (estrelas grandes) |
| o34 | moss inpaint (sprite 8x) | pequi fruto verde v2: "four or five small round dark olive green fruits partly hidden" | frutos existem na geração mas somem na redução (mesmo tom das folhas) |
| o35 | moss inpaint (sprite 8x) | pequi fruto verde v3: "dark green leaves ... small round dull greyish olive fruits with a pale highlight, clearly visible" | **usada**: 7 frutos oliva, legíveis; saem com ~4-5 px no sprite (o pedido era 2-3) e a copa fica mais rala |

Correções sem gerar (no sprite reduzido, `phases.py`):
- Tronco de todas as fases reduzido com a paleta das árvores **sem** as cores de flor (`bt`): as manchas claras da casca
  viravam roxo (ipê-roxo, inclusive o "tufo" da forquilha) ou amarelo. Some em todas as fases porque o tronco é o mesmo patch.
- Ipê seco (`bark_phases`): os galhos da copa vão para a rampa de cor do tronco por quantil de luminância (até 75% da rampa,
  galho um pouco mais escuro que o tronco); pixels claros e pouco saturados (resto do fundo na borda da máscara) saem.
  Acaba a emenda marrom-avermelhado x oliva na forquilha.

Saídas (`out/objects/`, `python phases.py build`):
- `arvore_ipe_amarelo_{florido,verde,seco,brotando}`, `arvore_ipe_roxo_{...}` (76-78x92),
  `arvore_cagaita_{maduro,florida,fruto_verde,folhada}` (60x76), `arvore_pequi_{maduro,florida,fruto_verde,folhada}`
  (84x102, = sprite do jogo), `arvore_baru_{folhado,florida,fruto_verde,maduro}` (113x107, = sprite do jogo).
  Cada um em `.png` + `.json` e em `_repix.png` + `.json`; o `anchor` é igual em todas as fases de uma árvore
  (por variante de redução).
- `out/fases_preview.png` (3x, linha atual e linha repix por árvore) e `out/fases.gif` (ciclo das fases).
- O `_florido` do ipê-amarelo é um re-render da o25 sem o encolhimento por nearest do `final2.py`
  (78x92 em vez de 76x92); não é pixel a pixel igual ao `arvore_ipe_amarelo.png`.

unfake/box x repix: a redução atual ganha. O repix (grade imposta de 12-13 px) deixa mais pixels pretos
soltos e contorno serrilhado nas copas finas (cagaita, galhos secos); o unfake (cor dominante) mantém
flores e frutos e limpa a borda. Nos sprites do jogo a diferença é pequena (fator 8 = grade nativa),
o box fica um pouco mais suave e o repix um pouco mais contrastado.

Problemas:
- (corrigido) emenda da forquilha no seco e roxo no tronco do ipê-roxo: ver "Correções sem gerar".
- Ipê-roxo brotando: fica uma mancha escura na forquilha vinda da geração.
- O inpaint arredonda a copa (cagaita, pequi): a silhueta da copa não é a mesma da base, só o tronco.
  Para manter os tufos, combinar: img2img 0.6 do moss-pixel (o15) + a mesma composição por máscara.
- Fruto verde em 1x: verde sobre verde some; precisa de fruto com contraste (pequi: o35) ou de cor extra na paleta. Baru fruto verde continua sem fruto visível.
- Planta de lavoura em estágios por inpaint: não feito.

## Variantes

Objetivo: mais de uma forma de cada objeto no mapa, no mesmo estilo. Script: `variantes.py`
(sem geração: 0 jobs). Saídas em `out/variantes/`, cópia em `entrega/objetos/fases/` (árvores) e
`entrega/objetos/objects/` (objetos).

Receita das árvores (`python3 variantes.py`; `--entrega` copia):
- Entrada: as fases aprovadas em `entrega/objetos/fases/`. Como todas as fases de uma árvore têm a
  mesma tela e o mesmo tronco, **uma só transformação de coordenadas** aplicada a cada fase dá
  fases coerentes na variante (mesmo tronco, silhueta, tela e `anchor`).
- Base da copa: a linha mais baixa onde alguma fase difere das outras (o tronco é idêntico entre fases).
- Transformação (mapa inverso, vizinho mais próximo, só ampliações para galho fino não quebrar):
  espelho com reluz, tronco esticado (+5 a +7 linhas entre a copa e as raízes), copa mais larga
  (`sx`, rampa de 10 linhas a partir da forquilha) ou mais alta (`sy`), inclinação do tronco
  (`lean`, a copa vai inteira). Parâmetros por árvore em `RECIPES`.
- Espelho com reluz: a luz das árvores vem de cima e um pouco da esquerda (gradiente médio
  horizontal pequeno perto do vertical). Depois de espelhar, a parte esquerda-direita da luz
  (luminância borrada, componente antissimétrica) é devolvida: cada pixel vai para a cor da
  própria paleta da fase com o brilho corrigido (6-30% dos pixels mudam). A luz continua do mesmo
  lado do original; só o desenho fino dos tufos fica espelhado.
- Nomes: `arvore_<arvore>_b_<fase>.png` + `.json` (`anchor`, `from`, `recipe`), também `_repix`.
  Prévia: `out/variantes_preview.png` (a x b por fase, 3x, sobre grama).

| árvore | receita b | tela a -> b |
|---|---|---|
| ipe_amarelo | espelho, tronco +7, copa 1.12x larga, inclina 3 | 78x92 -> 89x99 |
| ipe_roxo | espelho, tronco +5, copa 1.1x alta, inclina -3 | 76x92 -> 75x103 |
| cagaita | espelho, tronco +6, copa 1.15x larga, inclina 2 | 60x76 -> 67x82 |
| pequi | espelho, tronco +5, copa 1.1x larga, inclina -2 | 84x102 -> 90x107 |
| baru | espelho, tronco +6, copa 1.06x alta, inclina 3 (só florida, folhado, maduro) | 113x107 -> 109x117 |

Objetos de 1 sprite (`python3 variantes.py --objetos`, prévia `out/variantes_objetos_preview.png`):
- `cupinzeiro_alto_{b,c}`, `cupinzeiro_baixo_{b,c}`: espelho com reluz e/ou ampliação vertical
  (1.25-1.3x) ou horizontal (1.2-1.25x), base fixa, `anchor` levado junto.
- `cupinzeiro_duplo`: o alto na frente e o baixo espelhado atrás à esquerda; `anchor` = o do alto.
- `pilao_b`: espelhado (mão de pilão para o outro lado).
- `carro_de_boi_esp`: espelhado com reluz; é a outra direção (como a caminhonete), não variedade.
- Pedras: já há 29 decalques em `entrega/decals/pedras`; nada feito.

Decoração do terreno (`tools/variedade.py`, `decor_extra`): 52 tiles novos anexados no fim do atlas
(rng próprio, os 74 antigos ficam nas mesmas posições e iguais pixel a pixel): capim alto (folhas
de 6-10 px com espiga palha), tufo ao vento, touceira de 2-3 tufos (os de trás um tom mais
escuros), moita baixa (corpo no tom escuro, luz em cima à esquerda), capim-dourado (hastes palha
+ capítulo dourado), chuveirinho (pompom branco), flores do cerrado (roseta + 1-3 flores roxo, rosa,
amarelo, laranja, branco) e brotos. Em `grass` (33), `dry` (9) e `lush` (10). Total: 126 tiles.
Prévia dos novos sobre o tile puro de cada terreno: `out/decor_preview.png` (5x).

### Variante c (copa nova por inpaint, o50-o68)

Receita (`variantes.py --c-prep <arvore>`, `aig import`, `gen.py oNN`, `variantes.py --c <arvore>`):
- Base: a fase base da **b** ampliada 8x numa tela branca 1024 (`specs/bases/<arvore>_b_8x.png`, com
  margem lateral `pad`). Máscara `specs/masks/<arvore>_c.png`: envelope novo da copa (superelipse a
  partir do bbox da copa b: mais larga/baixa, deslocada, topo mais chato; `C_ENV`), só acima da base
  da copa; o que muda entre fases e cai fora do envelope é apagado da base.
- 1 inpaint por fase (template `moss`, feather 8, outra seed), mesma base e mesma máscara para todas
  as fases: mesmo tronco (o da b), mesmo envelope, mesma tela e `anchor`.
- Redução: box 8x8 (e `_repix`) na janela da tela c, folhas da copa gerada casadas em H/S/V com as
  folhas da fase b correspondente (`match_crown`; o inpaint sai amarelado e sem isso o verde vira
  oliva-amarelo), paleta da fase b correspondente (tol 0), tronco da b colado fora da máscara,
  pedaços soltos < 12 px apagados; ipê seco passa pelo `bark_ramp`.

| lote | o quê | veredito |
|---|---|---|
| o50-o53 | pequi c: maduro, florida, fruto_verde, folhada (envelope 1.18x largo, 0.82x alto, topo chato) | copa em guarda-chuva, bem diferente da a/b; florida e folhada boas; maduro: frutos amarelos somem no box (aparecem no `_repix`) |
| o52 | pequi c fruto_verde | job cancelado na fila (não fui eu); refeito no o66 |
| o54 | ipê-amarelo c florido | **fraca**: bolinhas amarelas regulares sobre verde escuro, parece laranjeira |
| o55-o57 | ipê-amarelo c verde, seco, brotando | verde e seco bons (galhos mais abertos que a b); brotando com galho marrom-rosado, corrigido por `bark_partial` (só os galhos vão para a rampa do tronco) |
| o58-o60 | baru c folhado, florida, maduro (envelope 0.8x alto, topo chato) | **bons**: copa em tufos-pompom e guarda-chuva, nada a ver com a a/b |
| o65 | ipê-amarelo c florido v2: "one solid dense mass of countless tiny golden yellow flowers packed together, no green leaves visible, no gaps" | **boa**: massa de flor como o ipê a; substitui o o54 |
| o66 | pequi c fruto_verde (= o52, outra seed) | copa boa; frutos somem no verde em 1x (resolvido pintando os frutos, abaixo) |

| o61-o64 | cagaita c: maduro, florida, fruto_verde, folhada (envelope 1.2x largo, 0.85x alto) | maduro e florida bons (copa larga em tufos); fruto_verde saiu bola densa de frutos amarelos (parece maduro) e folhada saiu rala (parece brotando) |
| o67 | cagaita c fruto_verde v2: "several separate dense clumps ... a few small round pale lime green unripe fruits half hidden ..., no yellow fruits" | **boa**: tufos separados como as outras fases, frutos verde-limão |
| o68 | cagaita c folhada v2: "wide spreading crown ... separate dense clumps of small dark olive green leaves, full foliage" | **boa**: copa cheia em tufos |

Frutos do pequi pintados (sem gerar; `paint_fruits` em `variantes.py`): nas variantes a, b e c, 6-7 frutos
redondos de 6 px (a, b) ou 7 px (c), luz em cima à esquerda, contorno escuro embaixo/direita e pedúnculo,
na metade de baixo da copa, nas **mesmas posições** no maduro (amarelo-alaranjado) e no fruto_verde
(verde-amarelado claro, contrasta com a folha). A variante a pintada sai em `out/variantes/arvore_pequi_{maduro,fruto_verde}*`
e substitui a da entrega; o original continua em `out/objects/` (o `variantes.py` lê as fases a de lá,
para não pintar duas vezes).

Resultado: pequi (4 fases), ipê-amarelo (4), baru (3) e cagaita (4) com variante c; 19 jobs enviados
(o50-o68, 18 rodaram). Ipê-roxo ficou sem c.
O ipê-roxo só tem a máscara (`--c-prep` feito, sem import nem specs).

Problemas:
- A variante b é a mesma árvore espelhada e esticada: de perto lê como "parente" da a. Para uma
  forma de copa realmente nova, o caminho é o inpaint da copa com outra seed sobre o tronco b
  (1 job por fase: 4 por árvore, 3 no baru) e o resto como no `phases.py`. Não feito.
- O desenho fino dos tufos fica espelhado (realce no lado direito de cada tufo); a reluz corrige só
  a luz em grande escala. Em 1x não aparece.
- `cupinzeiro_duplo` ocupa ~38 px de largura (mais de uma célula visualmente).
- Na grama `lush` (textura carregada) moita e touceira quase somem, como os tufos antigos.
- c: o `_repix` deixa franja bege (resto do fundo branco) em volta dos tufos do baru; o box fica limpo.
  No pequi maduro o box apagava os frutos gerados; agora os frutos são pintados depois da redução.
- c: a silhueta varia um pouco entre fases (cada fase é um inpaint); o envelope, o tronco e o anchor
  são os mesmos, como nas fases da a.
- c: o anchor é o da b levado junto (o do baru fica num pontinho caído abaixo das raízes, como no
  sprite original; na c esse pontinho é apagado, mas o anchor continua no mesmo lugar).
- Corrigido nesta rodada: a reluz do espelho da b usava paleta e campo de luz por fase, e o tronco
  ficava diferente entre fases da b. Agora o campo é o da fase base e o que é igual em todas as
  fases vem da fase base. As b foram regeradas e copiadas de novo.

## Sombras

Objetivo: sombra projetada no chão para cada objeto, com a **mesma luz** em todos. Hoje o mapa usa uma
elipse sem forma (`tools/remap.py` `shadow_sprite`) e o jogo não tem sombra. Script: `sombras.py`;
saídas em `out/sombras/`; gerações em `runs/o36`-`o38`.

Luz escolhida (fixa): **de cima-esquerda da tela; a sombra cai para baixo-direita, no eixo +x do grid
iso** (vetor de tela 2:1, mesma inclinação das bordas do losango 32x16). Por quê:
- as árvores do jogo (`old_assets/Green trees/arvore_pequi.png`, `arvore_baru.png`) e as geradas (ipê,
  cagaita) têm a copa mais clara em cima e à esquerda (centro da luminância deslocado para cima-esquerda);
  o telhado da `house.png` e do moinho tem o plano voltado para a esquerda claro.
- 2:1 é linha limpa em pixel art e acompanha o grid; a sombra fica à direita/frente, sempre visível,
  sem esconder o objeto.
- Parâmetros em `sombras.py`: `DIR=(2,1)`, `LEN=0.5` (px de sombra por px de altura), `SHRINK=0.8`
  (copa: a sombra usa 80% da largura), cor `SHADE=(22,34,46)`, contato `CORE=(10,18,26)`, `ALPHA=0.38`.

Técnicas comparadas (`out/sombras/comparacao.png`, 3x sobre a grama do kit `out/kit-g/terrain_atlas.png`):

| técnica | como | veredito |
|---|---|---|
| hoje | elipse 2:1 sob o pé | não dá direção nem forma; some sob objetos pequenos |
| **B projeção** | cada pixel do sprite a altura h do chão vai para (x, chão) + h·LEN·DIR. Chão = y do anchor (árvore, cupinzeiro, pilão) ou última linha opaca da coluna (carreta, moinho, casa). Árvore/blob: cada linha vira um disco (profundidade = largura do trecho, ±d/2 em y). Fechamento + preenchimento + sem pixel solto. Contato (elipse da largura do tronco) em 2º tom | **recomendada**: forma do objeto (pilão com a mão, carro com timão e roda, casa com o telhado), direção idêntica em tudo, 0 gerações, roda em ~1 s |
| B + autosombra | B + pixels do lado de baixo-direita do objeto (vizinho a 3 px transparente) descem 1 degrau na rampa do próprio sprite | discreto; ajuda copa e cupinzeiro, quase nada nos sprites que já vêm sombreados. Opcional |
| C proxy | copa = elipse projetada do centro da copa + faixa do tronco; blob = base varrida | parecido com B nas copas redondas, perde a forma (pequi, cagaita em tufos). Só para árvore/blob; não serve para carreta/casa |
| A1 inpaint | moss-inpaint (denoise 1.0) na cena 8x (grama do kit + objeto), máscara = sombra B dilatada 2 px menos o objeto | inconsistente: tamanho e força variam (ipê: só um borrão perto do tronco; pequi: sombra cheia e boa; carro: inventou uma roda solta; moinho: sombra fraca em degradê e alargou a terra). Degradê = não é pixel art |
| A2 inpaint guiado | base já escurecida com a sombra B, denoise 0.8 | devolve a forma do guia com textura de grama mais escura dentro: bonito, mas preso àquele trecho de grama (não serve sobre terra/caminho) e a forma é a da B. Não acrescenta nada que justifique 4 min por objeto |
| A3 inpaint sobre branco | objeto colado em branco liso (mesma célula), máscara = sombra B dilatada 4 px menos o objeto, prompt de sombra cinza no chão branco (`A3_PROMPT`). Extração: box para 1x, escurecimento = 1 - lum/255 (pixel saturado = objeto inventado, fora), 3 níveis (cortes 0.10/0.22/0.36 -> alfa 0.22/0.36/0.50), cor fixa `SHADE`, sem mancha < 6 px, + elipse de contato da B (o modelo deixa vão no pé). PNG RGBA só da sombra | melhor que A1/A2: a extração é limpa (sem grama para descontar) e reaproveitável em qualquer chão. Ipê: **a mais bonita do estudo**, borda orgânica e furos de luz entre as folhas. Mas continua inconsistente: pequi saiu quase branco (só sobra o contato), carro fraco e só embaixo do carro. 1 de 3 boa |

Árvores com fases (`out/sombras/fases.png`): a sombra B é feita por fase, num quadro comum a todas as
fases (mesmo `anchor`/`offset`), então no Godot só a textura da sombra troca junto com a do objeto. O
tronco é o mesmo em todas as fases (`phases.py`), então a parte do tronco é idêntica; muda só a copa.
Fase sem copa (`seco`): sem volume, em xadrez (meia sombra de galhos).

Saídas (`python sombras.py all`):
- `<objeto>[_<fase>]_sombra{B,C,A1,A2}.png` + `.json`: cor única opaca (2 tons: contato mais escuro).
  `.json`: `anchor` (pixel da sombra no centro da célula, mesma regra do objeto), `offset` (canto sup.
  esq. da sombra menos o anchor do objeto), `alpha` sugerido, `dir`, `len`, `tech`.
- `<objeto>_autosombra.png` (objeto com sombra própria), `<objeto>_embutida.png` + `.json` (objeto com a
  sombra B dentro; a tela cresce, ipê 78x92 -> 101x119; anchor muda se a sombra passar à esquerda/acima).
- `comparacao.png`, `fases.png`, `sobreposicao.png` (alfa por sprite x camada única x embutida).
- `*_sombraA3.png` + `.json`: alfa já no PNG (3 níveis); no Godot fica fora do CanvasGroup ou num grupo
  com alfa 1 (senão o alfa aplica duas vezes). Quebra a regra de alfa único: 3 tons por sombra.
- Bases/máscaras do inpaint: `specs/bases/sombra_*`, `specs/masks/sombra_*`, ids em `specs/bases/sombra_ids.json`.

Godot (recomendado):
- Sombra como **sprite separado**, não embutida. PNG de cor opaca; o alfa vem de **um** nó para todas:
  `CanvasGroup` "Sombras" entre o `TileMapLayer` do chão e a camada dos objetos (y-sort), com
  `self_modulate.a = 0.38`. O CanvasGroup achata os filhos antes do alfa: onde duas sombras se cruzam o
  tom é o mesmo (alfa único, pixel art). Com alfa em cada sprite a sobreposição dobra o escuro
  (`sobreposicao.png`, painel 1).
- Cada sombra: `Sprite2D`, `centered = false`, `offset = -anchor` (do `.json` da sombra), na mesma
  posição do objeto. Como a sombra fica em outro nó, guardar a referência no objeto e mover/trocar junto
  (fase da árvore = trocar as duas texturas).
- Embutida: um nó só, mas a sombra vira alfa parcial dentro do PNG do objeto, entra na ordem y (a
  sombra de um objeto cobre o pé do vizinho de trás), dobra no cruzamento, aumenta a tela e o retângulo
  de clique, e precisa refazer a cada mudança de luz. Só vale para objeto isolado e fixo.
- Sobre a grama do kit (verde-amarelo claro), cor opaca não funciona (não serve em terra/caminho);
  alfa único 0.35-0.40 de azul-esverdeado escuro lê bem sem virar mancha preta. Xadrez opaco (dither)
  fica ruidoso com a textura da grama; só usei no ipê seco.

| lote | modelo | o quê | veredito |
|---|---|---|---|
| o36 | moss inpaint (base = cena 8x) | ipê: A1 (denoise 1.0, máscara = sombra B) e A2 (guia escurecido, denoise 0.8) | A1 desenhou só um borrão em degradê junto ao tronco (usa ~1/3 da máscara); A2 manteve o guia e pôs textura de grama escura |
| o37 | moss inpaint (A1, denoise 1.0) | pequi, carro de boi, moinho, cupinzeiro alto, casa (casa em 4x, cupinzeiro em 16x) | 1 de 5 bom (pequi: sombra cheia, borda em pixel, textura de grama). Carro: inventou uma roda solta na máscara e a sombra quase não aparece; moinho e casa: sombra fraca em degradê; cupinzeiro: nada. A direção segue a máscara, o tamanho e a força não |

| o38 | moss inpaint (A3, objeto sobre branco, denoise 1.0) | ipê, pequi (8x, 1280), carro de boi; moinho e casa cancelados (fila do ComfyUI cheia de jobs de outra sessão) | ipê: sombra em pixel com furos de luz, ótima; pequi: sombra quase invisível (abaixo do 1º corte); carro: sombra cinza fraca só sob a carroceria e 2 manchas marrons inventadas (o filtro de saturação tira) |

Conclusão do inpaint (A1/A2/A3, 10 gerações): a direção sai certa porque vem da máscara (que é a B), mas
a presença, o tamanho e a força variam de seed para seed; 2 de 8 objetos bons sem guia. Para virar
receita precisaria de várias seeds por objeto e escolha à mão. A B dá o mesmo resultado em todos, de graça.
Caminho para juntar os dois: B como forma e alfa; A3 só como textura opcional (furos de luz) nas árvores de destaque.

Problemas:
- A projeção B trata o sprite como volume sobre o ponto de pé (árvore) ou sobre a última linha de cada
  coluna (carreta/casa). Objeto com chão no sprite (moinho: terra) ou com parte baixa longe do pé pode
  sair torto; conferir. O anchor da casa (`house.png`) foi medido à mão (66,104).
- Ipê seco: a sombra de galho vira faixa fina (os galhos não têm profundidade); ficou em xadrez.
- A sombra fica embaixo de tudo: não cai sobre o objeto vizinho (a sombra da árvore não escurece a carreta ao lado).
- A2 foi guiado pela B antiga (LEN 0.4, sem `SHRINK`); as bases do inpaint não foram refeitas.

### Rodada 2: sol alto e D (difusão + gradiente)

Retorno do usuário: a B parece artificial ("círculo geométrico"); só a do ipê por difusão (A3) funcionou.
O jogador tem sombra quase vertical (elipse preta, alfa 100/255, sob os pés, `old_assets/Player/farmer_Player.png`),
então a luz mudou para **sol alto**: `LEN 0.18` (era 0.5), `SHRINK 0.85`, cor preta, alfa 100/255 (= jogador).
A copa projeta quase embaixo de si, achatada 2:1, com leve deslocamento para baixo-direita.

D = A3 com a geometria nova + gradiente de alfa no PNG:
- Base: objeto sobre branco (mesma célula de `layout`), máscara = sombra B (sol alto) dilatada 3 px (`D_GROW`;
  `w` = 7 px, máscara larga para quando a sombra sai fraca), sem o objeto. Prompt `D_PROMPT` (sol a pino, sombra
  cinza média embaixo do objeto, levemente para baixo-direita). `n=2` por job (2 seeds).
- Extração (`d_extract`): box para 1x; sombra = escurecimento (1 - lum/255) >= 0.07 dentro da máscara, sem cor
  saturada (objeto inventado), sem mancha < 6 px; + elipse de contato no pé.
- Gradiente (`D_W`, `D_BIAS`): nota = 0.45·escurecimento da própria difusão + 0.25·profundidade dentro da forma
  (borda 0, miolo 1) + 0.30·(1 - distância ao pé, com a distância 60% mais longa na direção baixo-direita).
  4 níveis de alfa `D_LEVELS = 24/48/72/100` (100 = jogador), nível = piso(nota·4 + Bayer 4x4 + 0.25), então o
  pontilhado aparece só nas transições. Contato no pé sempre 100.
- Contato (`d_contact`): árvore = elipse 2:1 da largura do tronco acima das raízes (6 a 14 px); o resto = faixa de
  2 px sob o contorno de baixo do objeto, só onde ele toca o chão. A elipse antiga (largura da base com raízes)
  virava um oval sólido de 30 px no baru, o mesmo "círculo geométrico" da B.
- Saída: `out/sombras/<nome>_sombraD.png` + `.json` (`anchor`, `offset`, `obj_anchor`, alfa já no PNG).
- Escolha da seed: `sombras.py dsheet` monta `tmp/sombras/candidatos.png` (todas as seeds sobre a grama);
  a escolhida vai em `D_PICK`; `sombras.py dfinal` grava as finais e `out/sombras/comparacao_D.png` (B sol alto, A3, D, com o jogador ao lado).
- Jogo: `python sombras_jogo.py <repo_do_jogo> --tech D` (alfa no PNG, `modulate` 1.0).

| exp | o que | resultado |
|---|---|---|
| o39 | D, máscara normal (3 px), 10 objetos x 2 seeds | 8 de 10 bons: baru 067, seca caída 666, house 832, cagaita 942, ipê roxo 416, ipê amarelo 815, carro 687, cupinzeiro 820. Pequi: difusão pintou branco nas 2 seeds (uma inventou uma pessoa). Moinho: só uma linha de contato. |
| o40 | D `w` (máscara 7 px, feather 16, prompt "dark grey cast shadow, strong contrast"), pequi x3, moinho x2 | pequi 450 bom (449 grande demais, solta para baixo; 451 risco estranho); moinho 581 bom. |

Total D: 12 jobs, 25 imagens. Escolhas em `D_PICK` (sombras.py). Pequi do ensaio (`arvore_pequi_maduro.png`) é
idêntico ao `old_assets/Green trees/arvore_pequi.png` do jogo, então a D dele serve para `arvore_6.tscn`.

Problemas:
- ~50% das seeds saem fracas ou com coisa inventada (pessoa, toco, riscos); 2 seeds + 1 retry com máscara
  larga resolveu todos os 10. Para objetos novos, conte 2 a 5 imagens por objeto.
- A fila é compartilhada: cada job esperou 2 a 3 jobs de outros agentes (~15 min por job meu).
- A D sai mais clara que a B (só o miolo chega a 72/100). `D_BIAS` maior escurece tudo de uma vez.
