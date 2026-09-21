# Agregador Nota A

Média ponderada das pesquisas para a eleição presidencial de 2026, usando
**apenas os institutos com nota A-, A ou A+** no ranking de acurácia:
Datafolha (A+), AtlasIntel (A+), MDA (A+), Paraná Pesquisas (A),
Real Time Big Data (A) e Futura (A-).

Três páginas:

- **Agregador 2026** — onde a corrida está, com o peso de cada pesquisa à mostra
- **Pesquisa × Urna** — o que as pesquisas finais de 2018 e 2022 diziam contra o
  que as urnas devolveram
- **Estado por Estado** — o que Bolsonaro fez em cada UF no 2º turno de 2022
  contra o que as pesquisas estaduais dão a Flávio agora

## Como a média é calculada

Cada pesquisa entra com um peso:

```
peso = nota × recência × amostra × repetição
```

| Fator | O que faz |
|---|---|
| `nota` | A+ vale 1,00; A vale 0,70; A- vale 0,55 |
| `recência` | `0,5 ^ (dias / meia-vida)` — meia-vida padrão de 14 dias |
| `amostra` | `√(n / 2000)`, limitado entre 0,75 e 1,40 |
| `repetição` | `1/√k` na k-ésima pesquisa mais recente do mesmo instituto |

O fator de repetição existe para que um instituto que publica toda semana não
domine a média pela frequência em vez da qualidade.

A meia-vida de 14 dias foi calibrada por validação cruzada fora da amostra
(`calibrar.py`): para cada pesquisa, prevê-se o resultado dela usando só as
anteriores. A superfície de erro é bem plana — entre 1,51 e 1,94 pontos —, e
meia-vida curta demais ganha no papel mas reduz o número efetivo de pesquisas
a ponto de o ruído amostral superar o ganho.

## Os arquivos

| Script | O que faz |
|---|---|
| `institutos.py` | Os seis institutos, notas e pesos. É aqui que se muda o critério |
| `coletar.py` | Baixa e parseia as tabelas da Wikipédia → `pesquisas_1t.csv`, `pesquisas_2t.csv` |
| `agregar.py` | Calcula a média ponderada → `agregado.json`, `painel.html` |
| `calibrar.py` | Testa combinações de janela e meia-vida por validação cruzada |
| `coletar_historico.py` | Pesquisas de 2018 e 2022, incluindo 2º turno |
| `resultados.py` | Resultados oficiais do TSE |
| `aferir.py` | Compara pesquisas finais com as urnas → `afericao.json`, `aferidor.html` |
| `verificar.py` | Confere se os dados fazem sentido antes de publicar |
| `coletar_uf.py` | Resultado do 2º turno de 2022 por UF → `resultados_2022_uf.csv` |
| `pesquisas_uf.csv` | **Preenchido à mão**: pesquisas presidenciais estaduais |
| `projetar_uf.py` | Swing uniforme por estado → `projecao_uf.json`, `estados.html` |
| `montar_site.py` | Monta `site/` para o GitHub Pages |

Só biblioteca padrão do Python — nada a instalar.

## Rodando localmente

```bash
python coletar.py       # pesquisas de 2026
python agregar.py       # recalcula e gera o painel
python aferir.py        # relê agregado.json: rode DEPOIS de agregar.py
python projetar_uf.py   # idem: relê agregado.json
python verificar.py     # confere
python montar_site.py   # monta site/
```

`coletar_historico.py` só precisa rodar de novo se a Wikipédia corrigir alguma
pesquisa de 2018 ou 2022 — esses CSVs ficam versionados aqui.

## Atualização automática

O workflow `.github/workflows/atualizar.yml` roda às 8h e às 20h de Brasília:
baixa as pesquisas novas, recalcula, confere, publica no Pages e commita os CSVs
atualizados. Dá para disparar à mão em **Actions → Atualizar agregador → Run
workflow**, com a opção de rebaixar também o histórico de 2018 e 2022.

Se a Wikipédia sair do ar ou mudar o formato das tabelas, `verificar.py`
interrompe o workflow antes da publicação — o site continua no ar com os
últimos dados bons em vez de publicar número errado.

## Limites

**A fonte é a Wikipédia**, que cita o registro de cada pesquisa no TSE. Os
números foram conferidos contra as manchetes referenciadas, mas é uma fonte
editável. Para robustez de produção, o caminho é ler direto do PesqEle/TSE — a
troca fica isolada em `coletar.py`.

**Paraná Pesquisas não publica 1º turno presidencial desde março de 2026** e, na
prática, sai da média pela recência, embora continue na lista.

**A página por estado não se atualiza sozinha.** Pesquisas presidenciais
estaduais existem — a AtlasIntel publica várias —, mas não há fonte estruturada
para elas: cada uma sai como matéria ou PDF avulso, e as páginas estaduais da
Wikipédia cobrem governador, não presidente. Por isso `pesquisas_uf.csv` é
alimentado à mão, uma linha por pesquisa:

```
uf,instituto,data_inicio,data_fim,amostra,margem,turno,lula,adversario,fonte
PR,AtlasIntel,2026-09-11,2026-09-16,1794,2.0,2,38.8,57.5,https://...
```

Percentuais como publicados; a conversão para votos válidos é feita no código,
porque várias matérias rotulam "votos válidos" números que ainda carregam
indecisos. Institutos fora da lista nota A são ignorados na leitura.

O simulador de swing uniforme na mesma página cobre os estados sem pesquisa, e é
**modelo, não medição** — os estados com pesquisa real já mostram que o
movimento não é uniforme.

**Uma média ponderada não é previsão.** E o próprio `aferir.py` mostra o
tamanho do problema: em 2018 e 2022 o agregado subestimou o candidato da direita
no 1º turno em 6,0 e 3,8 pontos, e restringir aos institutos nota A **não**
reduziu esse erro — ele é do conjunto do mercado, não de um instituto. No 2º
turno, com só dois nomes, o viés praticamente desaparece.
