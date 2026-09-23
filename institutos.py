"""
Institutos aceitos no agregador: somente nota A-, A ou A+.

A nota e o numero de pesquisas vem do ranking de acuracia de institutos
(mesma tabela que originou este projeto). O peso base e derivado da nota:
quanto melhor a nota, maior o peso da pesquisa na media.
"""

import re

# peso base por nota
PESO_NOTA = {
    "A+": 1.00,
    "A":  0.70,
    "A-": 0.55,
}

NOTAS = {
    "Datafolha":          {"nota": "A+", "rank": 1,  "n_pesquisas": 29, "erro_medio": 3.2},
    "AtlasIntel":         {"nota": "A+", "rank": 2,  "n_pesquisas": 8,  "erro_medio": 3.4},
    "MDA":                {"nota": "A+", "rank": 6,  "n_pesquisas": 6,  "erro_medio": 3.6},
    "Paraná Pesquisas":   {"nota": "A",  "rank": 11, "n_pesquisas": 71, "erro_medio": 3.9},
    "Real Time Big Data": {"nota": "A",  "rank": 12, "n_pesquisas": 67, "erro_medio": 4.6},
    "Futura":             {"nota": "A-", "rank": 14, "n_pesquisas": 29, "erro_medio": 3.9},
}

# Candidatos que sairam da disputa. Ficam de fora do agregado, das barras e da
# conta de votos validos, mesmo nas pesquisas antigas em que apareciam: quem nao
# esta na urna nao e mais uma opcao, e manter o nome so inflaria um percentual
# que nao existe mais.
#
# As pesquisas seguem intactas em pesquisas_1t.csv, que e o arquivo historico -
# aqui se muda o que entra na conta, nao o que foi medido.
FORA_DA_DISPUTA = {
    "Marçal": {
        "desde": "2026-09-11",
        "motivo": "registro indeferido pelo TSE",
    },
}


# como os nomes aparecem na Wikipedia -> nome canonico
APELIDOS = {
    "datafolha": "Datafolha",
    "folha": "Datafolha",
    "atlasintel": "AtlasIntel",
    "atlas intel": "AtlasIntel",
    "atlas": "AtlasIntel",
    "mda": "MDA",
    "cnt/mda": "MDA",
    "cnt / mda": "MDA",
    "cnt mda": "MDA",
    "parana pesquisas": "Paraná Pesquisas",
    "paraná pesquisas": "Paraná Pesquisas",
    "real time big data": "Real Time Big Data",
    "realtime big data": "Real Time Big Data",
    "rtbd": "Real Time Big Data",
    "record/real time big data": "Real Time Big Data",
    "futura": "Futura",
    "apex/futura": "Futura",
    "apex / futura": "Futura",
    "instituto futura": "Futura",
    "futura inteligencia": "Futura",
    "futura inteligência": "Futura",
}


def normalizar_instituto(texto):
    """
    Converte o texto da celula 'Contratante / Pesquisa' no nome canonico do
    instituto, ou devolve o texto limpo se nao reconhecer.
    """
    if not texto:
        return ""
    t = texto.strip().strip("'\" ")
    if not t:
        return ""
    baixo = t.lower()

    # match direto
    if baixo in APELIDOS:
        return APELIDOS[baixo]

    # o instituto costuma vir depois de 'contratante/', ex. 'CNN/Real Time Big Data'
    for parte in reversed(re.split(r"[/\\]", baixo)):
        p = parte.strip()
        if p in APELIDOS:
            return APELIDOS[p]

    # match por conteudo (mais longo primeiro, para 'mda' nao pegar antes)
    for apelido in sorted(APELIDOS, key=len, reverse=True):
        if len(apelido) <= 3:
            if re.search(r"\b" + re.escape(apelido) + r"\b", baixo):
                return APELIDOS[apelido]
        elif apelido in baixo:
            return APELIDOS[apelido]

    return t
