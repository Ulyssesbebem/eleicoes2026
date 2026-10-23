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
pontaria de sorte. Institutos sem pesquisa na reta final do 1º turno recebem
o **menor** peso entre os medidos: quem não se expôs no 1º turno não pode pesar
mais que quem se expôs e errou.

| Fator | O que faz |
|---|---|
| `instituto` | `1/(1 + erro/4)`, do erro medido em 4/10 |
| `recência` | `0,5 ^ (dias / 5)` — meia-vida de 5 dias, contados do fim do campo |
| `amostra` | `√(n / 2000)`, entre 0,75 e 1,30 |

Só a pesquisa **mais recente** de cada instituto entra na conta: a rodada nova
substitui a anterior, para quem publica toda semana não pesar mais que quem
publica uma vez.

Janela e meia-vida são mais curtas que as do 1º turno (30 e 5 dias, contra 45 e
14): a campanha de 2º turno é curta e tudo se move mais rápido. A meia-vida era
de 10 dias até 23/10/2026 e foi encurtada para a reta final.

## A margem e a chance de vitória

A discordância entre os institutos dá uma margem de ±0,5 — mas ela só mede a
precisão da média. No 1º turno quase todos erraram na mesma direção, e esse
viés passa inteiro por ela. Por isso a margem do placar soma um **erro comum a
todos os institutos** (`DP_SISTEMATICO = 1,5` ponto em cada candidato), e é
dela que sai a chance de vitória:

```
dp_total = √((margem_da_média / 1,96)² + 1,5²)
chance   = Φ((média − 50) / dp_total)
```

1,5 fica entre o erro do 1º turno de 2026 (~2 pontos em cada candidato) e o
erro menor que o 2º turno teve em 2018 e 2022.

## Projeção para o dia da eleição

Compara cada instituto **só com ele mesmo** nos últimos 10 dias
(`TENDENCIA_DIAS`) — o que tira a diferença de método entre as casas — e mede a
inclinação comum, em pontos por dia. A projeção é o agregado de hoje mais essa
inclinação vezes os dias que faltam; a incerteza da inclinação entra na margem.
Só aparece com pelo menos 3 institutos com duas rodadas na janela.

## E se o erro do 1º turno se repetir?

A página mostra, ao lado do número principal, um cenário que desconta de cada
pesquisa **metade** do erro de margem que o próprio instituto cometeu em 4/10
(`FRACAO_VIES = 0,5`; quem não foi medido recebe o erro mediano). Não é a
previsão principal — é o tamanho do risco se o viés não sumir desta vez.

## Aba "Ranking PollsterGraph"

`site/pollstergraph.html` roda o mesmo agregador (`python agregar.py --pesos pg`)
trocando só o peso do instituto: em vez do erro no 1º turno de 2026, vale o
índice de desempenho do [ranking do PollsterGraph](https://pollstergraph.com/ranking/institutes),
dividido pelo do 1º colocado. Instituto sem nota no ranking (classe N ou ausente)
recebe o peso do pior classificado da lista principal. O ranking é baixado a cada
execução (`pollstergraph.py`) e guardado em `ranking_pollstergraph.json`, que vale
se a API cair. Saída: `agregado_pg.json` e `painel_pg_publico.html`.

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
| `calibrar.py` | Testa janela e meia-vida fora da amostra |
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
editável, e já produziu erros que entraram aqui: uma linha sem as células
de amostra e margem (que deslocava tudo), um mês digitado como "Oubt" e uma
rodada da Veritá (15–19/10) com os números exatos do resultado oficial do 1º
turno. Todos têm tratamento: `coletar.py` e `agregar.py` descartam linha de 2º
turno idêntica ao resultado do TSE, e `verificar.py` recusa amostra fora de 300
a 200.000 e avisa quando o mesmo instituto repete amostra com campo sobreposto.

**O peso vem de uma observação.** Acerto no 1º turno pode não transferir para o
2º — a aferição de 2018 e 2022, no histórico deste repositório, mostrou viés
grande no 1º turno e praticamente zero no 2º. Com dois nomes só, os institutos
convergem.

**Margem não é distância até a urna.** O ±X mede a precisão da média; viés
compartilhado por todos passa inteiro. Foi exatamente o que aconteceu no 1º
turno, quando 19 institutos erraram na mesma direção.
