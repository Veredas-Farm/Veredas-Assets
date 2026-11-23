# Galeria

Imagens brutas geradas no aig (projeto `veredas-assets`), exportadas com
`aig export`. Cada imagem tem ao lado a versão reduzida pelo repixelate,
`<nome>-<largura>x<altura>-repixelate.png` (grade de pixel nativa, até 32 cores, fundo branco
removido quando há).

| Pasta | O que é |
| :-- | :-- |
| `arvores/<especie>` | baru, cagaita, ipê amarelo, ipê roxo, ipê seco, jatobá, paineira, pequi: árvores, fases e variantes |
| `colheitas` | estágios de crescimento dos cultivos (feijão, soja, cana, mandioca, arroz, melancia, capim) |
| `itens` | ícones de inventário |
| `objetos/<objeto>` | carro de boi, carroça, reboque, cerca, cupinzeiro, moinho, pilão |
| `personagens/<quem>` | fazendeiro (parado, andando, ações), dona da venda, vaqueiro, criança |
| `sombras` | sombras pintadas por inpaint em fundo branco (estudo de sombra) |
| `terreno/texturas` | texturas de chão vistas de cima (grama, trilha, palha, arado) |
| `terreno/folhas-isometricas` | folhas 4x4 de blocos isométricos (inclui 3e9149 e 83fb90) |
| `terreno/decoracao` | folhas de tufos, flores, seixos, folhas secas |
| `comparativos/sweep/<modelo>` | sweep final de modelos de pixel art (ver `ensaio/out/sweep/RELATORIO.md`) |
| `<categoria>/bases` | imagens importadas usadas como entrada de img2img/inpaint (assets do jogo ampliados, folhas de entrada) |

Nome do arquivo: `<template>-<id>.png`. Prompt, estilo, seed, força, imagem
de origem e review estão em `indice.csv` / `indice.json`; `aig img show <id>`
mostra o job completo. As receitas e o que foi aproveitado de cada rodada
estão em `ensaio/README.md` e `ensaio/objects/README.md`.

O banco do aig guarda o caminho de cada arquivo. Para reorganizar, use
`ensaio/tools/galeria.py` (subcomandos `mover`, `repixelate`, `indice`),
que move e atualiza o banco; mover à mão faz o aig perder a imagem.
