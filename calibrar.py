"""
Calibra a janela e a meia-vida por validacao cruzada fora da amostra.

Ideia: para cada pesquisa p, calcula o agregado usando SO as pesquisas
anteriores a ela e mede o erro ao prever os numeros de p. A combinacao
(janela, meia-vida) que erra menos e a que melhor rastreia a opiniao.

Isso calibra o SUAVIZAMENTO. Nao corrige o vies pesquisa->urna, que e outro
problema e nao esta neste conjunto de dados.

Uso:  python calibrar.py [--cands Lula,Flávio] [--min-previas 3]
"""

import sys
from collections import defaultdict
from datetime import date

from agregar import ler_csv, media_ponderada, para_validos, peso_pesquisa
from institutos import NOTAS

GRADE_JANELA = [14, 21, 30, 45, 60, 75, 90, 120]
GRADE_MEIA_VIDA = [3, 5, 7, 10, 14, 21, 30, 45]


def arg(nome, padrao):
    if nome in sys.argv:
        return sys.argv[sys.argv.index(nome) + 1]
    return padrao


def conjunto_avaliavel(pesquisas, min_previas, janela_minima):
    """
    Pesquisas que podem ser previstas sob QUALQUER combinacao da grade.

    Sem isto a comparacao e invalida: uma janela curta qualifica menos
    pesquisas que uma longa, e cada combinacao acabaria sendo avaliada
    num conjunto diferente - o erro medio nao seria comparavel.
    """
    ordenadas = sorted(pesquisas, key=lambda x: x["data_fim"])
    avaliaveis = []
    for i, p in enumerate(ordenadas):
        dentro = [q for q in ordenadas[:i]
                  if q["data_fim"] < p["data_fim"]
                  and (p["data_fim"] - q["data_fim"]).days <= janela_minima]
        if len(dentro) >= min_previas:
            avaliaveis.append(p["data_fim"].isoformat() + "|" + p["instituto"])
    return set(avaliaveis)


def erro_fora_da_amostra(pesquisas, cands, janela, meia_vida, avaliaveis,
                         validos=True):
    """
    Erro absoluto medio ao prever cada pesquisa a partir das anteriores.
    So avalia as pesquisas do conjunto comum. Devolve (mae, n_previsoes).
    """
    ordenadas = sorted(pesquisas, key=lambda x: x["data_fim"])
    erros = []
    for i, p in enumerate(ordenadas):
        if p["data_fim"].isoformat() + "|" + p["instituto"] not in avaliaveis:
            continue
        anteriores = [q for q in ordenadas[:i] if q["data_fim"] < p["data_fim"]]

        prev, _ = media_ponderada(anteriores, cands, p["data_fim"], janela, meia_vida)
        if not prev:
            continue

        # os dois lados na mesma base: interseccao de candidatos
        comuns = [c for c in prev if p["valores"].get(c) is not None]
        if len(comuns) < 2:
            continue
        if validos:
            a = para_validos({c: prev[c] for c in comuns})
            b = para_validos({c: p["valores"][c] for c in comuns})
        else:
            a = {c: prev[c] for c in comuns}
            b = {c: p["valores"][c] for c in comuns}

        for c in cands:
            if c in a and c in b:
                erros.append(abs(a[c] - b[c]))

    if not erros:
        return None, 0
    return sum(erros) / len(erros), len(erros)


def n_efetivo(pesquisas, referencia, janela, meia_vida):
    """
    Numero efetivo de pesquisas no agregado: (sum w)^2 / sum w^2.
    Mede quanta informacao independente sobrou depois da ponderacao -
    e o piso de ruido do agregador.
    """
    els = [p for p in pesquisas
           if p["data_fim"] <= referencia
           and (referencia - p["data_fim"]).days <= janela]
    if not els:
        return 0.0
    por_inst = defaultdict(list)
    for p in sorted(els, key=lambda x: x["data_fim"], reverse=True):
        por_inst[p["instituto"]].append(p)
    ordem = {}
    for lista in por_inst.values():
        for i, p in enumerate(lista, 1):
            ordem[id(p)] = i

    pesos = [peso_pesquisa(p, referencia, ordem[id(p)], meia_vida) for p in els]
    s1 = sum(pesos)
    s2 = sum(w * w for w in pesos)
    return (s1 * s1 / s2) if s2 else 0.0


def main():
    cands = arg("--cands", "Lula,Flávio").split(",")
    min_previas = int(arg("--min-previas", "3"))

    p1 = ler_csv("pesquisas_1t.csv")
    if not p1:
        print("pesquisas_1t.csv vazio - rode 'python coletar.py' antes.")
        return
    hoje = max(p["data_fim"] for p in p1)

    print(f"Calibracao fora da amostra - candidatos: {', '.join(cands)}")
    print(f"{len(p1)} pesquisas na base, ate {hoje.isoformat()}\n")

    avaliaveis = conjunto_avaliavel(p1, min_previas, min(GRADE_JANELA))
    print(f"Conjunto comum de avaliacao: {len(avaliaveis)} pesquisas "
          f"(as que tem >= {min_previas} pesquisas nos {min(GRADE_JANELA)} dias anteriores)\n")
    if len(avaliaveis) < 5:
        print("AVISO: conjunto pequeno demais - o resultado abaixo e fraco.\n")

    resultados = []
    for j in GRADE_JANELA:
        for mv in GRADE_MEIA_VIDA:
            mae, n = erro_fora_da_amostra(p1, cands, j, mv, avaliaveis)
            if mae is None:
                continue
            resultados.append({
                "janela": j, "meia_vida": mv, "mae": mae, "n": n,
                "n_ef": n_efetivo(p1, hoje, j, mv),
            })

    if not resultados:
        print("Dados insuficientes para calibrar.")
        return

    # ---- tabela: erro medio por combinacao
    print("Erro absoluto medio (pontos percentuais), menor = melhor")
    print("linhas = janela em dias | colunas = meia-vida em dias\n")
    print(f"{'':>8}" + "".join(f"{mv:>7}" for mv in GRADE_MEIA_VIDA))
    melhor = min(resultados, key=lambda r: r["mae"])
    for j in GRADE_JANELA:
        linha = f"{j:>7}d"
        for mv in GRADE_MEIA_VIDA:
            r = next((x for x in resultados if x["janela"] == j and x["meia_vida"] == mv), None)
            if r is None:
                linha += f"{'-':>7}"
            else:
                marca = "*" if r is melhor else " "
                linha += f"{r['mae']:>6.2f}{marca}"
        print(linha)

    print(f"\nMelhor combinacao: janela {melhor['janela']}d, meia-vida "
          f"{melhor['meia_vida']}d  (erro {melhor['mae']:.2f} pp, "
          f"{melhor['n']} previsoes)")

    # ---- quao plana e a superficie? diferenca entre o melhor e o pior
    ordenados = sorted(resultados, key=lambda r: r["mae"])
    pior = ordenados[-1]
    print(f"Pior combinacao:   janela {pior['janela']}d, meia-vida "
          f"{pior['meia_vida']}d  (erro {pior['mae']:.2f} pp)")
    print(f"Diferenca entre o melhor e o pior: {pior['mae'] - melhor['mae']:.2f} pp")

    print("\nTop 8 combinacoes:")
    print(f"  {'janela':>7} {'meia-vida':>10} {'erro':>7} {'n_efetivo':>11}")
    for r in ordenados[:8]:
        print(f"  {r['janela']:>6}d {r['meia_vida']:>9}d {r['mae']:>6.2f} {r['n_ef']:>10.1f}")

    # ---- custo de ruido: n efetivo hoje
    print("\nNumero efetivo de pesquisas hoje (quanto menor, mais ruido):")
    print(f"  {'janela':>7} {'meia-vida':>10} {'n_efetivo':>11} {'erro_amostral':>14}")
    for r in ordenados[:8]:
        # erro padrao aproximado de uma proporcao de 40% com n_ef pesquisas de 2000
        import math
        n_total = r["n_ef"] * 2000
        ep = 100 * math.sqrt(0.40 * 0.60 / n_total) if n_total > 0 else float("nan")
        print(f"  {r['janela']:>6}d {r['meia_vida']:>9}d {r['n_ef']:>10.1f} "
              f"{'±' + format(1.96 * ep, '.2f') + ' pp':>14}")

    print("\nObs.: este erro mede o quanto o agregado acerta a PROXIMA PESQUISA.")
    print("O vies pesquisa->urna e outro problema e nao sai destes dados.")


if __name__ == "__main__":
    main()
