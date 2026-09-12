"""
Resultados oficiais das eleicoes presidenciais, em VOTOS VALIDOS (%).

Fonte: TSE, via as paginas de resultado da Wikipedia
('Eleicao presidencial no Brasil em <ano>', secao Resultados).

As chaves usam o mesmo nome curto que aparece nas colunas das tabelas de
pesquisa, para que a comparacao pesquisa x urna seja direta.
"""

RESULTADOS = {
    2018: {
        "dia_1t": "2018-10-07",
        "dia_2t": "2018-10-28",
        "turno1": {
            "Bolsonaro": 46.03,
            "Haddad": 29.28,
            "Gomes": 12.47,
            "Alckmin": 4.76,
            "Amoêdo": 2.50,
            "Daciolo": 1.26,
            "Meirelles": 1.20,
            "Silva": 1.00,
            "Dias": 0.80,
            "Boulos": 0.58,
        },
        "turno2": {"Bolsonaro": 55.13, "Haddad": 44.87},
    },
    2022: {
        "dia_1t": "2022-10-02",
        "dia_2t": "2022-10-30",
        "turno1": {
            "Lula": 48.43,
            "Bolsonaro": 43.20,
            "Tebet": 4.16,
            "Gomes": 3.04,
            "Thronicke": 0.51,
            "D'Avila": 0.47,
            "Kelmon": 0.07,
            "Péricles": 0.05,
            "Manzano": 0.04,
            "Salgado": 0.02,
            "Eymael": 0.01,
        },
        "turno2": {"Lula": 50.90, "Bolsonaro": 49.10},
    },
}

# quem era o candidato da direita e o da esquerda em cada ciclo - serve para
# somar o vies "por campo" em vez de por nome proprio
CAMPOS = {
    2018: {"direita": "Bolsonaro", "esquerda": "Haddad"},
    2022: {"direita": "Bolsonaro", "esquerda": "Lula"},
    2026: {"direita": "Flávio", "esquerda": "Lula"},
}
