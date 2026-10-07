"""
Mede quanto cada instituto errou no 1o turno de 2026 e grava acuracia_2026.json.

E esse numero que define o peso de cada instituto no agregador de 2o turno:
em vez de confiar num ranking de acuracia montado antes da eleicao, usamos o
desempenho na eleicao que acabou de acontecer.

O erro que importa e o da MARGEM (Flavio menos Lula), nao o do percentual de
cada um. Um instituto pode errar o nivel dos dois candidatos junto - por ter
mais ou menos indecisos - e ainda assim acertar quem esta na frente e por
quanto, que e o que o agregador precisa.

Uso:  python aferir_1t.py
"""

import csv
import io
import json
import sys
from datetime import date, timedelta

from resultado_1t import DIA_1T, RESULTADO_1T

# so pesquisas encerradas nesta janela antes do pleito contam como "reta final"
DIAS_RETA_FINAL = 14

A, B = "Flávio", "Lula"
MARGEM_REAL = RESULTADO_1T[A] - RESULTADO_1T[B]


def validos(valores):
    """Converte para votos validos, tirando indecisos/brancos/nulos."""
    c = {k: v for k, v in valores.items()
         if k not in ("Indefinidos", "Outros") and v is not None}
    total = sum(c.values())
    if total <= 0:
        return {}
    return {k: 100 * v / total for k, v in c.items()}


def ler(caminho="pesquisas_1t.csv"):
    with io.open(caminho, encoding="utf-8-sig", newline="") as f:
        linhas = list(csv.DictReader(f))
    saida = []
    for r in linhas:
        vals = {}
        for k, v in r.items():
            if k in ("instituto", "data_inicio", "data_fim", "amostra", "margem", "cenario"):
                continue
            if v not in (None, ""):
                try:
                    vals[k] = float(v)
                except ValueError:
                    pass
        saida.append({
            "instituto": r["instituto"],
            "data_fim": date.fromisoformat(r["data_fim"]),
            "amostra": int(r["amostra"]) if r.get("amostra") else None,
            "valores": vals,
        })
    return saida


def main():
    dia = date.fromisoformat(DIA_1T)
    inicio = dia - timedelta(days=DIAS_RETA_FINAL)

    try:
        pesquisas = ler()
    except FileNotFoundError:
        print("pesquisas_1t.csv nao existe - rode 'python coletar.py' antes.")
        sys.exit(1)

    # ultima pesquisa de cada instituto na reta final
    ultima = {}
    for p in pesquisas:
        if not (inicio <= p["data_fim"] < dia):
            continue
        if A not in p["valores"] or B not in p["valores"]:
            continue
        atual = ultima.get(p["instituto"])
        if atual is None or p["data_fim"] > atual["data_fim"]:
            ultima[p["instituto"]] = p

    medidos = {}
    for inst, p in ultima.items():
        v = validos(p["valores"])
        if A not in v or B not in v:
            continue
        erro_margem = (v[A] - v[B]) - MARGEM_REAL
        medidos[inst] = {
            "data": p["data_fim"].isoformat(),
            "amostra": p["amostra"],
            "previsto_a": round(v[A], 2),
            "previsto_b": round(v[B], 2),
            "erro_margem": round(erro_margem, 2),
            "erro_abs": round(abs(erro_margem), 2),
            "erro_nivel": round((abs(v[A] - RESULTADO_1T[A])
                                 + abs(v[B] - RESULTADO_1T[B])) / 2, 2),
        }

    if not medidos:
        print("Nenhum instituto com pesquisa na reta final.")
        sys.exit(1)

    dados = {
        "dia_1t": DIA_1T,
        "oficial": RESULTADO_1T,
        "margem_real": round(MARGEM_REAL, 2),
        "dias_reta_final": DIAS_RETA_FINAL,
        "institutos": medidos,
    }
    with io.open("acuracia_2026.json", "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=1)

    ordem = sorted(medidos.items(), key=lambda x: x[1]["erro_abs"])
    print(f"Aferição do 1º turno de {DIA_1T}")
    print(f"Oficial: {A} {RESULTADO_1T[A]}%  x  {B} {RESULTADO_1T[B]}%  "
          f"(margem {MARGEM_REAL:+.2f})\n")
    print(f"  {'#':<3}{'instituto':<24}{'campo':<12}{A:>8}{B:>7}"
          f"{'erro margem':>13}{'erro nivel':>12}")
    for i, (inst, d) in enumerate(ordem, 1):
        print(f"  {i:<3}{inst[:22]:<24}{d['data']:<12}{d['previsto_a']:7.1f}%"
              f"{d['previsto_b']:6.1f}%{d['erro_margem']:>+13.1f}{d['erro_nivel']:>12.1f}")

    acertaram = [i for i, d in medidos.items() if d["erro_margem"] > -MARGEM_REAL]
    print(f"\n  {len(medidos)} institutos medidos · "
          f"{len(acertaram)} acertaram quem estava na frente")
    print("\nacuracia_2026.json gravado.")


if __name__ == "__main__":
    main()
