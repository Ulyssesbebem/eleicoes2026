"""
Calibra a janela e a meia-vida por validacao cruzada fora da amostra.

Ideia: para cada pesquisa p do duelo, calcula o agregado usando SO as
pesquisas encerradas antes dela e mede o erro ao prever o numero de p (em
votos validos). A combinacao (janela, meia-vida) que erra menos e a que melhor
rastreia a opiniao.

Usa exatamente a funcao agregar() de agregar.py - pesos por instituto,
recencia, amostra, so a mais recente de cada casa e a troca de cenario
hipotetico por real depois do 1o turno. Se o agregador mudar, a calibracao
acompanha.

Isso calibra o SUAVIZAMENTO. Nao corrige o vies pesquisa->urna, que e outro
problema e nao esta neste conjunto de dados.

Uso:  python calibrar.py [--min-previas 3] [--desde 2026-10-05]
"""

import math
import sys
from datetime import date, timedelta

from agregar import agregar, ler_2t

GRADE_JANELA = [7, 10, 14, 21, 30, 45, 60]
GRADE_MEIA_VIDA = [2, 3, 5, 7, 10, 14, 21]


def arg(nome, padrao):
    if nome in sys.argv:
        return sys.argv[sys.argv.index(nome) + 1]
    return padrao


def avaliaveis(pesquisas, min_previas, janela_minima, desde):
    """
    Pesquisas que podem ser previstas sob QUALQUER combinacao da grade:
    as que tem pelo menos min_previas pesquisas nos janela_minima dias
    anteriores. Sem isto cada combinacao seria avaliada num conjunto diferente
    e o erro medio nao seria comparavel.
    """
    saida = []
    for p in pesquisas:
        if p["data_fim"] < desde:
            continue
        antes = [q for q in pesquisas
                 if q["data_fim"] < p["data_fim"]
                 and (p["data_fim"] - q["data_fim"]).days <= janela_minima
                 and q["real"] == p["real"]]
        if len(antes) >= min_previas:
            saida.append(p)
    return saida


def erro_medio(pesquisas, alvo, janela, meia_vida):
    """Erro absoluto medio (pontos de votos validos) ao prever cada pesquisa alvo."""
    erros = []
    for p in alvo:
        vespera = p["data_fim"] - timedelta(days=1)
        anteriores = [q for q in pesquisas if q["data_fim"] <= vespera]
        r = agregar(anteriores, vespera, janela, meia_vida)
        if r:
            erros.append(abs(r["a"] - p["a"]))
    if not erros:
        return None, 0
    return sum(erros) / len(erros), len(erros)


def main():
    min_previas = int(arg("--min-previas", "3"))
    desde = date.fromisoformat(arg("--desde", "2026-10-05"))

    pesquisas = sorted(ler_2t(), key=lambda p: p["data_fim"])
    if not pesquisas:
        print("pesquisas_2t.csv vazio - rode 'python coletar.py' antes.")
        return

    alvo = avaliaveis(pesquisas, min_previas, min(GRADE_JANELA), desde)
    print(f"Calibracao fora da amostra - {len(pesquisas)} pesquisas do duelo")
    print(f"Avaliando {len(alvo)} pesquisas desde {desde.isoformat()} "
          f"(as que tem >= {min_previas} pesquisas nos {min(GRADE_JANELA)} dias anteriores)\n")
    if len(alvo) < 5:
        print("AVISO: conjunto pequeno demais - o resultado abaixo e fraco.\n")

    resultados = {}
    for j in GRADE_JANELA:
        for mv in GRADE_MEIA_VIDA:
            mae, n = erro_medio(pesquisas, alvo, j, mv)
            if mae is not None:
                resultados[(j, mv)] = (mae, n)

    if not resultados:
        print("Dados insuficientes para calibrar.")
        return

    melhor = min(resultados, key=lambda k: resultados[k][0])
    pior = max(resultados, key=lambda k: resultados[k][0])

    print("Erro absoluto medio (pontos de votos validos), menor = melhor")
    print("linhas = janela em dias | colunas = meia-vida em dias\n")
    print(f"{'':>8}" + "".join(f"{mv:>7}" for mv in GRADE_MEIA_VIDA))
    for j in GRADE_JANELA:
        linha = f"{j:>7}d"
        for mv in GRADE_MEIA_VIDA:
            r = resultados.get((j, mv))
            if r is None:
                linha += f"{'-':>7}"
            else:
                linha += f"{r[0]:>6.2f}" + ("*" if (j, mv) == melhor else " ")
        print(linha)

    mae_m, n_m = resultados[melhor]
    print(f"\nMelhor: janela {melhor[0]}d, meia-vida {melhor[1]}d "
          f"(erro {mae_m:.2f} pp, {n_m} previsoes)")
    print(f"Pior:   janela {pior[0]}d, meia-vida {pior[1]}d "
          f"(erro {resultados[pior][0]:.2f} pp)")
    print(f"Diferenca: {resultados[pior][0] - mae_m:.2f} pp")

    # piso de ruido: so o erro de amostra de UMA pesquisa de 2000 entrevistas
    piso = 100 * math.sqrt(0.5 * 0.5 / 2000) * math.sqrt(2 / math.pi)
    print(f"\nReferencia: so o ruido de amostra de uma pesquisa de 2.000 ja da "
          f"~{piso:.2f} pp de erro medio.")
    print("Diferencas menores que isso entre combinacoes nao significam muito.")
    print("\nObs.: este erro mede o quanto o agregado acerta a PROXIMA PESQUISA.")
    print("O vies pesquisa->urna e outro problema e nao sai destes dados.")


if __name__ == "__main__":
    main()
