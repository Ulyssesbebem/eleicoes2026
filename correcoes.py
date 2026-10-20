"""
Correcoes manuais aplicadas por coletar.py depois de ler a Wikipedia.

A fonte e editada a mao por voluntarios e as vezes erra. Corrigir o CSV nao
adianta: o robo rebaixa a Wikipedia a cada execucao e traria o erro de volta.
Por isso a correcao mora aqui, e e reaplicada toda vez.

Cada entrada diz qual linha descartar, por que, e onde se confirmou. Quando a
Wikipedia for corrigida na origem, a entrada vira inofensiva (nao acha nada
para descartar) e pode ser apagada.
"""

# linhas que nao correspondem a nenhuma pesquisa real
DESCARTAR = [
    {
        "instituto": "Gerp",
        "data_inicio": "2026-10-01",
        "data_fim": "2026-10-03",
        "turno": 1,
        "motivo": (
            "Linha inexistente. A pesquisa final do Gerp foi de 30/09 a 02/10, "
            "amostra 2.400, Flavio 46 x Lula 44 nos validos (43 x 41 no total) - "
            "que ja esta na base. Esta linha repete amostra e margem com campo "
            "sobreposto e o resultado invertido, e derrubava o Gerp de 1o para 8o "
            "na afericao do 1o turno."
        ),
        "fonte": (
            "https://exame.com/brasil/pesquisa-gerp-flavio-bolsonaro-tem-46-e-lula-44"
            "-dos-votos-validos-no-1o-turno/"
        ),
    },
]


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def copia_do_resultado_1t(p):
    """
    Linha de 2o turno cujo duelo e IDENTICO ao resultado oficial do 1o turno.

    Nenhuma pesquisa publica Lula 45,16 x Flavio 47,03 por acaso: e o numero do
    TSE colado na linha errada. Aconteceu com a Verita de 15-19/10/2026, que
    ainda repetia a amostra (15.554) da rodada de 12-16/10 - e era o instituto
    de maior peso no agregado. A regra e geral para pegar a proxima vez sem
    depender de alguem notar.
    """
    from resultado_1t import RESULTADO_1T
    if not str(p.get("cenario", "")).startswith("Lula e Fl"):
        return False
    a, b = _num(p.get("Lula")), _num(p.get("Flávio"))
    if a is None or b is None:
        return False
    return (abs(a - RESULTADO_1T["Lula"]) < 0.005
            and abs(b - RESULTADO_1T["Flávio"]) < 0.005)


def aplicar(pesquisas, turno):
    """
    Remove as linhas listadas em DESCARTAR e, no 2o turno, as que copiam o
    resultado oficial do 1o. Devolve (mantidas, descartadas).
    """
    regras = [c for c in DESCARTAR if c["turno"] == turno]
    mantidas, descartadas = [], []
    for p in pesquisas:
        if any(p["instituto"] == c["instituto"]
               and p.get("data_inicio") == c["data_inicio"]
               and p["data_fim"] == c["data_fim"] for c in regras):
            descartadas.append(p)
        elif turno == 2 and copia_do_resultado_1t(p):
            descartadas.append(p)
        else:
            mantidas.append(p)
    return mantidas, descartadas
