# Segundo Turno 2026

Média ponderada das pesquisas do 2º turno — **Lula × Flávio Bolsonaro** — com o
peso de cada instituto definido pelo erro que ele cometeu no 1º turno.

## A mudança de critério

Até 4 de outubro este repositório agregava o 1º turno usando um ranking de
acurácia montado **antes** da eleição: só cinco institutos com nota A+ ou A
entravam, e a nota definia o peso.

**Esse critério falhou.** A urna deu Flávio 47,03% × Lula 45,16%; os 19
institutos medidos erraram a margem por 0,3 a 9,2 pontos, **todos na mesma
direção**, e só 5 acertaram quem estava na frente. Entre os cinco do recorte
antigo, nenhum ficou no pódio: o A+ MDA foi 17º de 19, e a Futura, excluída por
ser A-, empatou em 1º.

Agora **todos os institutos entram** e o peso vem do erro medido:

```
peso_instituto = 1 / (1 + erro_margem / 4)
```

Limitado a um piso de 0,25, o que faz o melhor pesar cerca de 3× o pior — e não
30×, porque é **uma** observação por instituto e uma eleição só não distingue
pontaria de sorte. Institutos sem pesquisa na reta final do 1º turno recebem o
peso mediano.

| Fator | O que faz |
|---|---|
| `instituto` | `1/(1 + erro/4)`, do erro medido em 4/10 |
| `recência` | `0,5 ^ (dias / 10)` — meia-vida de 10 dias |
| `amostra` | `√(n / 2000)`, entre 0,75 e 1,30 |
| `repetição` | `1/√k` na k-ésima pesquisa mais recente do mesmo instituto |

Janela e meia-vida são mais curtas que as do 1º turno (30 e 10 dias, contra 45 e
14): a campanha de 2º turno é curta e tudo se move mais rápido.

## Hipotético x real

Pesquisa de 2º turno feita **antes** de 4/10 era cenário hipotético, perguntado
a um eleitor que ainda não tinha visto o resultado. Assim que existirem duas
pesquisas feitas **depois** do 1º turno, o agregado passa a usar só elas, e o
aviso no topo da página some. Até lá a página mostra o cenário hipotético
dizendo, em destaque, que é hipotético.

## Os arquivos

| Script | O que faz |
|---|---|
| `resultado_1t.py` | Resultado oficial do 1º turno (TSE) |
| `aferir_1t.py` | Mede o erro de cada instituto → `acuracia_2026.json` |
| `institutos.py` | Converte erro em peso; normaliza grafias |
| `coletar.py` | Baixa e parseia as tabelas da Wikipédia |
| `agregar.py` | Média ponderada do duelo → `agregado.json`, `painel.html` |
| `verificar.py` | Confere se os dados fazem sentido antes de publicar |
| `montar_site.py` | Monta `site/` para o GitHub Pages |

Só biblioteca padrão do Python.

## Rodando localmente

```bash
python coletar.py       # pesquisas
python aferir_1t.py     # erro de cada instituto no 1º turno
python agregar.py       # média do 2º turno + painel
python verificar.py     # confere
python montar_site.py   # monta site/
```

## Atualização automática

`.github/workflows/atualizar.yml` roda de 4 em 4 horas, publica no Pages e
commita os dados. O site sobe **antes** do commit: arquivar é secundário,
publicar é o objetivo.

## Limites

**A fonte é a Wikipédia**, que cita o registro de cada pesquisa no TSE. É
editável, e já produziu dois erros que entraram aqui: uma linha sem as células
de amostra e margem (que deslocava tudo) e um mês digitado como "Oubt". Ambos
têm tratamento no `coletar.py`, e `verificar.py` recusa amostra fora de 300 a
200.000.

**O peso vem de uma observação.** Acerto no 1º turno pode não transferir para o
2º — a aferição de 2018 e 2022, no histórico deste repositório, mostrou viés
grande no 1º turno e praticamente zero no 2º. Com dois nomes só, os institutos
convergem.

**Margem não é distância até a urna.** O ±X mede a precisão da média; viés
compartilhado por todos passa inteiro. Foi exatamente o que aconteceu no 1º
turno, quando 19 institutos erraram na mesma direção.
