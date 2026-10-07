"""
Peso de cada instituto no agregador de 2o turno.

MUDANCA DE CRITERIO APOS O 1o TURNO DE 2026
-------------------------------------------
Ate o 1o turno o peso vinha de um ranking de acuracia montado ANTES da
eleicao - A+, A, A-. Esse ranking falhou como previsor: o A+ MDA ficou em 17o
entre 19, e a A- Futura empatou em 1o. Dos cinco institutos daquele recorte,
nenhum ficou entre os tres melhores.

Agora o peso vem do erro MEDIDO em 4/10/2026, calculado por aferir_1t.py a
partir do resultado do TSE. Quem errou menos pesa mais.

    peso_instituto = 1 / (1 + erro_abs / ERRO_REFERENCIA)

A formula e deliberadamente suave. Com ERRO_REFERENCIA = 4 (perto do erro
mediano), o melhor instituto pesa ~3x o pior, nao 30x: e UMA observacao por
instituto, e uma eleicao so nao distingue pontaria de sorte. Um instituto que
errou 9 pontos ainda entra, com um terco do peso de quem acertou.

RESSALVAS, para quem for defender o criterio:

1. Acerto no 1o turno pode nao transferir para o 2o. A afericao de 2018 e 2022
   mostrou vies grande no 1o turno e praticamente zero no 2o - com dois nomes
   so, os institutos convergem. Entao o erro aqui medido pode estar punindo
   quem erraria pouco agora.

2. Institutos sem pesquisa na reta final do 1o turno nao tem medida. Recebem o
   peso mediano, nem premio nem castigo.
"""

import io
import json
import re

ERRO_REFERENCIA = 4.0    # erro, em pontos de margem, que corta o peso pela metade
PESO_MINIMO = 0.25       # ninguem e zerado: erro grande vira peso pequeno
PESO_SEM_MEDIDA = None   # preenchido com a mediana ao carregar

ARQUIVO_ACURACIA = "acuracia_2026.json"


def _carregar():
    try:
        with io.open(ARQUIVO_ACURACIA, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, ValueError):
        return {"institutos": {}}


ACURACIA = _carregar()


def _peso_do_erro(erro_abs):
    return max(PESO_MINIMO, 1.0 / (1.0 + erro_abs / ERRO_REFERENCIA))


PESOS = {inst: round(_peso_do_erro(d["erro_abs"]), 3)
         for inst, d in ACURACIA.get("institutos", {}).items()}

if PESOS:
    _ordenados = sorted(PESOS.values())
    _meio = len(_ordenados) // 2
    PESO_SEM_MEDIDA = round(
        _ordenados[_meio] if len(_ordenados) % 2
        else (_ordenados[_meio - 1] + _ordenados[_meio]) / 2, 3)
else:
    PESO_SEM_MEDIDA = 0.5


def peso_instituto(nome):
    """Peso do instituto; a mediana para quem nao foi medido no 1o turno."""
    return PESOS.get(nome, PESO_SEM_MEDIDA)


def tem_medida(nome):
    return nome in PESOS


def erro_de(nome):
    d = ACURACIA.get("institutos", {}).get(nome)
    return d["erro_margem"] if d else None


# ----------------------------------------------------------------- nomes

# Grafias que a Wikipedia usa para o mesmo instituto. So entram aqui os casos
# em que a mesma casa aparece com nomes diferentes - nao e mais uma lista de
# quem e aceito, porque agora todos entram.
APELIDOS = {
    "datafolha": "Datafolha",
    "folha": "Datafolha",
    "atlasintel": "AtlasIntel",
    "atlas intel": "AtlasIntel",
    "atlas": "AtlasIntel",
    "mda": "MDA",
    "cnt/mda": "MDA",
    "cnt / mda": "MDA",
    "parana pesquisas": "Paraná Pesquisas",
    "paraná pesquisas": "Paraná Pesquisas",
    "real time big data": "Real Time Big Data",
    "realtime big data": "Real Time Big Data",
    "rtbd": "Real Time Big Data",
    "futura": "Futura",
    "apex/futura": "Futura",
    "instituto futura": "Futura",
    "genial/quaest": "Quaest",
    "quaest": "Quaest",
    "poderdata": "PoderData/Aya",
    "poderdata/aya": "PoderData/Aya",
    "nexus/btg pactual": "Nexus/BTG",
    "nexus/btg": "Nexus/BTG",
    "instituto verità": "Veritá",
    "verità": "Veritá",
    "verita": "Veritá",
    "alfa inteligência": "Alfa Inteligência",
    "vox brasil": "Vox Brasil",
    "meio/ideia": "Meio/Ideia",
    "exame/ideia": "Meio/Ideia",
}

# candidatos que sairam da disputa (ver uso em agregar.py)
FORA_DA_DISPUTA = {}


def normalizar_instituto(texto):
    """Converte o texto da celula de contratante no nome canonico."""
    if not texto:
        return ""
    t = texto.strip().strip("'\" ")
    if not t:
        return ""
    baixo = t.lower()

    if baixo in APELIDOS:
        return APELIDOS[baixo]

    for parte in reversed(re.split(r"[/\\]", baixo)):
        p = parte.strip()
        if p in APELIDOS:
            return APELIDOS[p]

    for apelido in sorted(APELIDOS, key=len, reverse=True):
        if len(apelido) <= 3:
            if re.search(r"\b" + re.escape(apelido) + r"\b", baixo):
                return APELIDOS[apelido]
        elif apelido in baixo:
            return APELIDOS[apelido]

    return t
