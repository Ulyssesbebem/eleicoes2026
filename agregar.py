"""
Agrega as pesquisas do 2o turno de 2026 (Lula x Flavio) em uma media ponderada.

  peso = instituto x recencia x amostra x repeticao

onde 'instituto' vem do erro MEDIDO no 1o turno de 4/10/2026 (institutos.py),
e nao de um ranking montado antes da eleicao.

Cada pesquisa e convertida para VOTOS VALIDOS antes de entrar na media: num
duelo a soma tem de fechar em 100, e institutos com taxas de indecisos muito
diferentes deslocariam a base de comparacao se a conversao viesse depois.

Gera:
  agregado.json  - numeros do agregador
  painel.html    - painel visual com esses dados embutidos

Uso:  python agregar.py [--janela 30] [--meia-vida 10]
"""

import csv
import io
import json
import math
import sys
from collections import defaultdict
from datetime import date, timedelta

from institutos import (ACURACIA, ERRO_REFERENCIA, PESO_SEM_MEDIDA,
                        erro_de, peso_instituto, tem_medida)
from resultado_1t import DIA_1T, DIA_2T, DUELO_2T, RESULTADO_1T

# ------------------------------------------------------------------ parametros

JANELA_DIAS = 30      # a campanha de 2o turno e curta: janela menor que a do 1o
MEIA_VIDA = 10        # e decaimento mais rapido, porque tudo se move mais
AMOSTRA_REF = 2000
AMOSTRA_MIN, AMOSTRA_MAX = 0.75, 1.30

A, B = DUELO_2T       # "Lula", "Flávio"

# Minimo de pesquisas feitas DEPOIS do 1o turno para o agregado passar a usar
# so elas. Enquanto nao houver, o painel mostra o cenario hipotetico - e diz
# que e hipotetico.
MIN_PESQUISAS_REAIS = 2


def arg(nome, padrao):
    if nome in sys.argv:
        return type(padrao)(sys.argv[sys.argv.index(nome) + 1])
    return padrao


# ------------------------------------------------------------------ leitura

def ler_2t(caminho="pesquisas_2t.csv"):
    """Pesquisas do confronto que foi ao 2o turno, ja em votos validos."""
    with io.open(caminho, encoding="utf-8-sig", newline="") as f:
        linhas = list(csv.DictReader(f))

    saida = []
    for r in linhas:
        cen = r.get("cenario", "")
        if not cen or "hipótese" in cen.lower():
            continue
        try:
            va, vb = float(r[A]), float(r[B])
        except (KeyError, ValueError, TypeError):
            continue
        total = va + vb
        if total <= 0:
            continue
        ind = r.get("Indefinidos")
        d = date.fromisoformat(r["data_fim"])
        saida.append({
            "instituto": r["instituto"],
            "data_fim": d,
            # pesquisa feita DEPOIS do 1o turno mede o 2o turno de verdade;
            # antes dele era cenario hipotetico, perguntado a um eleitor que
            # ainda nao tinha visto o resultado nem a campanha reiniciar
            "real": d > date.fromisoformat(DIA_1T),
            "amostra": int(r["amostra"]) if r.get("amostra") else None,
            "bruto_a": va,
            "bruto_b": vb,
            "indefinidos": float(ind) if ind not in (None, "") else None,
            # a conversao para validos acontece AQUI, pesquisa por pesquisa
            "a": 100 * va / total,
            "b": 100 * vb / total,
        })
    return saida


# ------------------------------------------------------------------ pesos

def fator_amostra(n):
    if not n:
        return 1.0
    return max(AMOSTRA_MIN, min(AMOSTRA_MAX, math.sqrt(n / AMOSTRA_REF)))


def peso(p, referencia, ordem, meia_vida):
    """peso = instituto x recencia x amostra x repeticao"""
    w_inst = peso_instituto(p["instituto"])
    dias = (referencia - p["data_fim"]).days
    w_rec = 0.5 ** (dias / meia_vida)
    w_amo = fator_amostra(p["amostra"])
    w_rep = 1 / math.sqrt(ordem)
    return w_inst * w_rec * w_amo * w_rep


def elegiveis(pesquisas, referencia, janela):
    """Pesquisas da janela, com a ordem de cada uma dentro do seu instituto."""
    els = [p for p in pesquisas
           if p["data_fim"] <= referencia
           and (referencia - p["data_fim"]).days <= janela]
    por_inst = defaultdict(list)
    for p in sorted(els, key=lambda x: x["data_fim"], reverse=True):
        por_inst[p["instituto"]].append(p)
    ordem = {}
    for lista in por_inst.values():
        for i, p in enumerate(lista, start=1):
            ordem[id(p)] = i
    return els, ordem


def conjunto_valido(pesquisas, referencia):
    """
    Devolve (lista, hipotetico). Assim que existirem pesquisas de 2o turno
    feitas depois do 1o, elas passam a ser as unicas usadas: perguntar o duelo
    antes do 1o turno e outra pergunta, feita a um eleitor que ainda nao tinha
    visto o resultado. E essas mesmas pesquisas erraram a margem do 1o turno
    por volta de 5 pontos.
    """
    reais = [p for p in pesquisas if p["real"] and p["data_fim"] <= referencia]
    if len(reais) >= MIN_PESQUISAS_REAIS:
        return reais, False
    return [p for p in pesquisas if p["data_fim"] <= referencia], True


def agregar(pesquisas, referencia, janela, meia_vida):
    """Media ponderada do duelo, em votos validos. Devolve None se nao der."""
    base, hipotetico = conjunto_valido(pesquisas, referencia)
    els, ordem = elegiveis(base, referencia, janela)
    if len(els) < 2:
        return None

    pesos = [peso(p, referencia, ordem[id(p)], meia_vida) for p in els]
    den = sum(pesos)
    if den <= 0:
        return None

    va = sum(p["a"] * w for p, w in zip(els, pesos)) / den
    vb = 100 - va

    # dispersao entre institutos -> margem do agregado
    var = sum(w * (p["a"] - va) ** 2 for p, w in zip(els, pesos)) / den
    dp = math.sqrt(var)
    s2 = sum(w * w for w in pesos)
    n_ef = den * den / s2 if s2 else 0.0
    margem = 1.96 * dp / math.sqrt(n_ef) if n_ef > 1 else None

    return {
        "a": va, "b": vb,
        "hipotetico": hipotetico,
        "desvio": dp,
        "n": len(els),
        "n_efetivo": n_ef,
        "margem": margem,
        "min": min(p["a"] for p in els),
        "max": max(p["a"] for p in els),
    }


def serie(pesquisas, fim, dias, janela, meia_vida):
    """Agregado recalculado dia a dia, para o grafico."""
    saida = []
    d = fim - timedelta(days=dias)
    while d <= fim:
        r = agregar(pesquisas, d, janela, meia_vida)
        if r:
            saida.append({
                "data": d.isoformat(),
                "a": round(r["a"], 2),
                "b": round(r["b"], 2),
                "margem": round(r["margem"], 2) if r["margem"] else None,
            })
        d += timedelta(days=1)
    return saida


# ------------------------------------------------------------------ principal

def main():
    janela = arg("--janela", JANELA_DIAS)
    meia_vida = arg("--meia-vida", MEIA_VIDA)

    pesquisas = ler_2t()
    if not pesquisas:
        print("Sem pesquisas de 2o turno - rode 'python coletar.py' antes.")
        sys.exit(1)

    hoje = max(p["data_fim"] for p in pesquisas)
    ag = agregar(pesquisas, hoje, janela, meia_vida)
    if not ag:
        print("Pesquisas insuficientes na janela.")
        sys.exit(1)

    base, _hip = conjunto_valido(pesquisas, hoje)
    els, ordem = elegiveis(base, hoje, janela)
    pesos = {id(p): peso(p, hoje, ordem[id(p)], meia_vida) for p in els}
    total_peso = sum(pesos.values()) or 1

    lista = []
    for p in sorted(els, key=lambda x: x["data_fim"], reverse=True):
        lista.append({
            "instituto": p["instituto"],
            "data": p["data_fim"].isoformat(),
            "amostra": p["amostra"],
            "bruto_a": p["bruto_a"], "bruto_b": p["bruto_b"],
            "indefinidos": p["indefinidos"],
            "a": round(p["a"], 1), "b": round(p["b"], 1),
            "peso": round(pesos[id(p)], 4),
            "peso_pct": round(100 * pesos[id(p)] / total_peso, 1),
            "erro_1t": erro_de(p["instituto"]),
            "medido": tem_medida(p["instituto"]),
        })

    historico = [{
        "instituto": p["instituto"],
        "data": p["data_fim"].isoformat(),
        "amostra": p["amostra"],
        "a": round(p["a"], 1), "b": round(p["b"], 1),
        "erro_1t": erro_de(p["instituto"]),
    } for p in sorted(pesquisas, key=lambda x: x["data_fim"], reverse=True)]

    dados = {
        "atualizado": date.today().isoformat(),
        "data_ultima_pesquisa": hoje.isoformat(),
        "dia_1t": DIA_1T,
        "dia_2t": DIA_2T,
        "duelo": {"a": A, "b": B},
        "resultado_1t": RESULTADO_1T,
        "parametros": {
            "janela_dias": janela,
            "meia_vida_dias": meia_vida,
            "amostra_ref": AMOSTRA_REF,
            "amostra_min": AMOSTRA_MIN,
            "amostra_max": AMOSTRA_MAX,
            "erro_referencia": ERRO_REFERENCIA,
            "peso_sem_medida": PESO_SEM_MEDIDA,
        },
        "acuracia_1t": ACURACIA.get("institutos", {}),
        "agregado": {
            "a": round(ag["a"], 2), "b": round(ag["b"], 2),
            "hipotetico": ag["hipotetico"],
            "n_reais": sum(1 for p in pesquisas if p["real"]),
            "margem": round(ag["margem"], 2) if ag["margem"] else None,
            "desvio": round(ag["desvio"], 2),
            "n": ag["n"],
            "n_efetivo": round(ag["n_efetivo"], 2),
            "min": round(ag["min"], 1), "max": round(ag["max"], 1),
        },
        "serie": serie(pesquisas, hoje, 120, janela, meia_vida),
        "pesquisas_janela": lista,
        "historico": historico,
    }

    with io.open("agregado.json", "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=1)

    # ---------------- relatorio
    dias_para = (date.fromisoformat(DIA_2T) - hoje).days
    print(f"Agregador do 2º turno — {A} x {B}")
    print(f"janela {janela}d · meia-vida {meia_vida}d · "
          f"última pesquisa {hoje.isoformat()} ({dias_para} dias do pleito)\n")
    m = ag["margem"]
    print(f"  {A}  {ag['a']:.1f}%" + (f"  ±{m:.1f}" if m else ""))
    print(f"  {B}  {ag['b']:.1f}%")
    dif = abs(ag["a"] - ag["b"])
    if m and dif <= 2 * m:
        print(f"\n  diferença de {dif:.1f} pp — EMPATE ESTATÍSTICO")
    else:
        lider = A if ag["a"] > ag["b"] else B
        print(f"\n  {lider} à frente por {dif:.1f} pp")
    print(f"  {ag['n']} pesquisas na janela ({ag['n_efetivo']:.1f} efetivas)")
    if ag["hipotetico"]:
        print("\n  ATENCAO: nenhuma pesquisa de 2o turno feita DEPOIS do 1o turno.")
        print("  O numero acima vem de cenarios hipoteticos, perguntados antes de")
        print("  04/10 - e foram essas mesmas pesquisas que erraram a margem do")
        print("  1o turno em cerca de 5 pontos. Trate como ponto de partida, nao")
        print("  como medida do 2o turno.")

    print(f"\n  {'data':<12}{'instituto':<22}{'1º turno':>10}{'válidos':>16}{'peso':>8}")
    for p in lista[:12]:
        e = f"{p['erro_1t']:+.1f}" if p["erro_1t"] is not None else "  —"
        print(f"  {p['data']:<12}{p['instituto'][:20]:<22}{e:>10}"
              f"{p['a']:>9.1f} x{p['b']:5.1f}{p['peso_pct']:>7.1f}%")

    print("\nagregado.json gravado.")
    gerar_painel(dados)


def gerar_painel(dados, modelo="painel_modelo.html", saida="painel.html",
                 saida_publica="painel_publico.html"):
    try:
        with io.open(modelo, encoding="utf-8") as f:
            html = f.read()
    except FileNotFoundError:
        print(f"(aviso) {modelo} nao encontrado - painel nao gerado.")
        return
    bruto = json.dumps(dados, ensure_ascii=False).replace("</", "<\\/")
    corpo = html.replace("/*__DADOS__*/", bruto)
    with io.open(saida, "w", encoding="utf-8") as f:
        f.write(corpo)
    completo = (
        '<!doctype html>\n<html lang="pt-BR">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        '<meta name="color-scheme" content="light dark">\n'
        "<style>img{max-width:100%}[hidden]{display:none!important}</style>\n"
        "</head>\n<body>\n" + corpo + "\n</body>\n</html>\n"
    )
    with io.open(saida_publica, "w", encoding="utf-8") as f:
        f.write(completo)
    print(f"{saida} e {saida_publica} gravados.")


if __name__ == "__main__":
    main()
