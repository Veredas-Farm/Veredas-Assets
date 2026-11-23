# Sweep de modelos de pixel art (2026-11-22/23)

Img2img de 11 combinações de modelo e estilo sobre 7 folhas com os assets da entrega, reduzidas com
repixelate para o tamanho exato do original (mesmo anchor). Ferramenta: `tools/sweep.py`.

## Resumo

- Nenhum modelo supera o conjunto atual de forma geral. Os atuais já vêm do moss-pixel e de uma
  redução cuidadosa; o sweep serve como fonte de variantes e de redesenho pontual, não para trocar tudo.
- Melhor relação fidelidade e limpeza: **flux-pixel 0.45** (contorno e silhueta preservados, grade limpa,
  cores sóbrias). O custo é de 8,6 min por imagem.
- Melhor para redesenhar mantendo o ângulo: **moss-pixel 0.5** (árvores, cultivos, cascalho) e
  **moss-refiner 0.65** (objetos de madeira: carro de boi e moinho mais limpos que os atuais).
- **sdxl-pad 0.5-0.65**: fiel e barato (2 min); em 0.65 acrescenta detalhe sem perder a forma.
- Ruins: sd15-pixel (grade grossa, 0.25 MP), sdxl-sai (inventa coisas: mesa no lugar do pequi),
  moss-iso e moss-sentence (árvore genérica em pirulito, verde neon), flux sem LoRA (quase não muda e borra).

## Tabela (1 = ruim, 5 = bom; avaliação visual das folhas, score médio = IoU da silhueta - distância de cor)

| modelo (template + estilo) | dn | iso 2:1 | legível em 1x | paleta | artefatos | score árv/obj/ícone/terreno | s/img |
| :-- | :-- | :-: | :-: | :-: | :-: | :-- | --: |
| flux-pixel (flux-pixel-lora) | 0.45 | 5 | 5 | 4 | 5 | 0.80 / 0.74 / 0.71 / 0.97 | 516 |
| moss-pixel (moss-pixel-lora) | 0.5 | 5 | 5 | 2 (saturado; ok com `_pal`) | 4 | 0.70 / 0.71 / 0.64 / 0.92 | 284 |
| sdxl-pad (sdxl-pixel-art-diffusion) | 0.5 / 0.65 | 5 | 4 | 4 | 3 (vaza célula: melancia no ícone de pequi) | 0.74 / 0.74 / 0.71 / 0.96 | 128 |
| moss-refiner (moss-pixel-refiner) | 0.65 | 4 | 4 | 3 | 3 (ícones viram outra coisa) | 0.67 / 0.65 / 0.56 / 0.92 | 217 |
| sdxl-pixel (pixel-art-xl) | 0.5 | 4 | 3 | 3 | 2 (carro vira barris, cultivo vira vaso) | 0.75 / 0.74 / 0.70 / 0.95 | 124 |
| sdxl-pixel-iso (pixel-art-xl-isometric) | 0.5 | 4 | 3 | 3 | 2 (igual ao anterior; o estilo iso não muda nada) | 0.75 / 0.73 / 0.70 / 0.95 | 115 |
| sdxl-sai (sdxl + pixel-art-sai) | 0.6 | 3 | 2 | 3 | 1 | 0.77 / 0.71 / 0.65 / 0.95 | 105 |
| moss-iso (moss + isometric) | 0.65 | 3 | 3 | 1 | 2 (árvore genérica) | 0.65 / - / - / 0.92 | 242 |
| moss-sentence (moss + moss-pixel-art-sentence) | 0.65 | 3 | 3 | 1 | 2 | 0.64 / - / - / 0.93 | 231 |
| flux (sem LoRA, "pixel art" no prompt) | 0.72 | 4 | 2 | 3 | 2 (borrado, quase igual ao original) | 0.69 / - / - / 0.95 | 564 |
| sd15-pixel (sd15-pixel-toolkit) | 0.45 | 3 | 1 | 2 | 1 (blocos grossos, objeto se desfaz em 0.6) | 0.62 / 0.58 / 0.53 / 0.93 | 14 |

O score alto em "terreno" é efeito do recorte pela máscara do bloco original: o ângulo do terreno é
garantido pela construção, não pelo modelo. O score premia quem muda pouco (por isso sdxl-sai 0.6 pontua
bem nas árvores); a coluna visual é a que vale.

## Melhores por categoria

| categoria | escolha | observação |
| :-- | :-- | :-- |
| árvores | flux-pixel 0.45 (t1 seed 1001) ou moss-pixel 0.5 + `_pal` | moss-pixel troca a cor do fruto conforme o prompt (pequi saiu com fruto verde porque o prompt dizia "yellow-green"); em 0.7 perde a forma |
| árvore seca | moss-pixel 0.5 (t2) | galhos finos legíveis; sdxl-pad também |
| objetos grandes | moss-refiner 0.65 (obj seed 1001) e flux-pixel 0.45 | refiner redesenha carro de boi e moinho com roda mais clara; moss-pixel 0.7 acrescenta um boi ao carro (sai do retângulo) |
| objetos pequenos e ícones | flux-pixel 0.45 ou sdxl-pad 0.5 | todos sofrem com a folha 4x5 reduzida a 1 MP (fator 4,8): ícones de 32 px ficam com pouca grade. Para ícones, folha menor (2x2) |
| cultivos | moss-pixel 0.5 | sdxl/sd15 transformam os estágios em plantas de vaso |
| terreno | moss-pixel 0.7 `_pal` (cascalho e trilha com textura) ou sdxl-pad 0.65 `_pal` (grama) | sem `_pal` todo moss deixa a grama verde-limão; flux quase não muda o tile |
| personagem | nenhum | o fazendeiro tem ~16 px; todos perdem o rosto. Mantém o atual |

## Receitas

Bases (ids na galeria): t1 `2a17c1b137dd`, t2 `9e3fc2264a95`, t3 `ddcc60f26ea4`, obj `262c1675bbee`,
small `96cb6a2388e9`, crops `d9c8ca12d867`, terrain `b6edc5fedcda` (PNGs em `specs/sweep/`, 8x nearest;
o template reescala para 1 MP, ou 0.25 MP no sd15). Prompts em `specs/sweep/layout.json`; todos terminam com
"isometric pixel art, cerrado, muted earthy palette, crisp clean pixels, plain white background".

```sh
cd ensaio
python3 tools/sweep.py bases                 # folhas + layout.json + originais em specs/sweep/orig/
python3 tools/sweep.py queue [modelo...]     # fora do sandbox; grava specs/sweep/jobs.json
python3 tools/sweep.py collect               # lê o banco (só leitura), reduz para out/sweep/cells/<asset>/
python3 tools/sweep.py sheets                # out/sweep/<asset>.png e resumo.png
# um job avulso equivalente:
aig job add flux-pixel --base 2a17c1b137dd --set denoise=0.45 --set seed=1001 \
  --set style=flux-pixel-lora --set prompt="<prompt de t1 em layout.json>"
```

| modelo | template | estilo | denoise testado | seeds |
| :-- | :-- | :-- | :-- | :-- |
| moss-pixel | moss-pixel | moss-pixel-lora | 0.5, 0.7 | 1001-1002 (t2, t3, crops: 1001) |
| moss-refiner | moss-refiner | moss-pixel-refiner | 0.65, 0.8 | 1001 |
| moss-iso / moss-sentence | moss | isometric / moss-pixel-art-sentence | 0.65, 0.8 | 1001 (só t1 e terrain) |
| flux-pixel | flux-pixel | flux-pixel-lora | 0.45, 0.6 | 1001 (t1, obj, small, terrain) |
| flux | flux | nenhum, "pixel art, " no prompt | 0.72 | 1001 (t1, terrain) |
| sdxl-pad | sdxl-pad | sdxl-pixel-art-diffusion | 0.5, 0.65 | 1001-1002 |
| sdxl-pixel / -iso | sdxl-pixel | pixel-art-xl / pixel-art-xl-isometric | 0.5, 0.65 | 1001-1002 (t2, t3, crops: 1001) |
| sdxl-sai | sdxl | pixel-art-sai | 0.6, 0.75 | 1001 (t1, obj, small, terrain) |
| sd15-pixel | sd15-pixel | sd15-pixel-toolkit | 0.45, 0.6 | 1001-1002 |

Melhores imagens (id na galeria): flux-pixel t1 0.45 `cf025cea3f97`, obj 0.45 `a4d84d3ebeb1`;
moss-pixel t1 0.5 `ee94786c7c06`, obj 0.5 `9f2124e5e097`, terrain 0.7 `d5e818424e90`, crops 0.5 `205f52bb1fcb`;
moss-refiner obj 0.65 `b7aa028192f9`; sdxl-pad t1 0.65 `305c66bdce8b`, terrain 0.65 `f2bb493c5e65`.

## Redução (`collect`)

- Recorte da célula com folga de 6 px do original; fundo por `pipeline.remove_bg`; `repixelate --pixel-size
  <px da geração por px do original> --colors 0 --blend 0.5 --no-bg`; volta ao tamanho exato por nearest.
- Alfa: máscara reduzida por box (terreno: alfa do bloco original). Pixels quase brancos na borda (e em todo
  o sprite, se o original não tem branco) viram transparentes.
- `_pal`: cada cor vai para a mais próxima da paleta do próprio original (`pipeline.map_palette`).
- Melhor seed = maior score (IoU - distância de cor). Folhas: original | baixo | alto | baixo `_pal` | alto `_pal`.

## Problemas

- A fila custou 7,5 h (104 jobs, 156 imagens): o aig derruba o ComfyUI depois de cada imagem (`restart_after_image`), então o moss
  leva ~4,7 min por imagem e o flux ~8,6 min. Cortei 43 jobs no meio (cancelados): flux-pixel, moss-refiner
  e sdxl-sai sem t2/t3/crops; moss-iso, moss-sentence e flux só em t1 e terrain; moss-refiner com 1 seed;
  segunda seed de t2/t3/crops só no sdxl-pad e sd15. Ipê roxo e jatobá ficaram de fora.
- Folha "small" (4x5 itens) passa de 1 MP: os ícones ficam com fator 4,8 e os modelos misturam células
  vizinhas (sdxl põe melancia no pequi). Ícones pedem folha própria e menor.
- Terreno: na força alta, o bloco gerado sai menor que o original e deixa franja branca na aresta (dentro do
  alfa do original).
- `remove_bg` falhou em 4 células do sdxl-pixel-iso 0.65 (objeto colado no fundo cinza).
