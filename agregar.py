"""
Agrega as pesquisas do 2o turno de 2026 (Lula x Flavio) em uma media ponderada.

  peso = instituto x recencia x amostra

So a pesquisa MAIS RECENTE de cada instituto entra na conta: a rodada nova
substitui a anterior, para quem publica toda semana nao pesar mais que quem
publica uma vez.

onde 'instituto' vem do erro MEDIDO no 1o turno de 4/10/2026 (institutos.py),
e nao de um ranking montado antes da eleicao.

Cada pesquisa e convertida para VOTOS VALIDOS antes de entrar na media: num
duelo a soma tem de fechar em 100, e institutos com taxas de indecisos muito
diferentes deslocariam a base de comparacao se a conversao viesse depois.

Gera:
  agregado.json  - numeros do agregador
  painel.html    - painel visual com esses dados embutidos

Uso:  python agregar.py [--janela 30] [--meia-vida 5] [--pesos erro_1t|pg]
"""

import csv
import io
import json
import math
import sys
from datetime import date, timedelta

import correcoes
from institutos import (ACURACIA, ERRO_REFERENCIA, PESO_SEM_MEDIDA,
                        erro_de, normalizar_instituto, peso_instituto, tem_medida)
from resultado_1t import DIA_1T, DIA_2T, DUELO_2T, RESULTADO_1T

# ------------------------------------------------------------------ parametros

JANELA_DIAS = 30      # a campanha de 2o turno e curta: janela menor que a do 1o
MEIA_VIDA = 5         # e decaimento rapido: na reta final tudo se move mais.
                      # Era 10 ate 23/10/2026; com 5, campo de uma semana
                      # atras pesa 38% de um de hoje (antes, 62%)
AMOSTRA_REF = 2000
AMOSTRA_MIN, AMOSTRA_MAX = 0.75, 1.30

A, B = DUELO_2T       # "Lula", "Flávio"

# Minimo de pesquisas feitas DEPOIS do 1o turno para o agregado passar a usar
# so elas. Enquanto nao houver, o painel mostra o cenario hipotetico - e diz
# que e hipotetico.
MIN_PESQUISAS_REAIS = 2

# Erro que TODOS os institutos podem cometer juntos (desvio padrao, em pontos
# de votos validos de um candidato). A margem antiga media so a discordancia
# entre institutos e dava +/-0,5 - mas no 1o turno de 2026 a mediana errou a
# margem em ~4 pontos (~2 em cada candidato), todos na mesma direcao. Em 2018
# e 2022 o 2o turno errou menos que o 1o. 1,5 fica entre os dois: assume que o
# 2o turno erra menos, sem assumir que nao erra.
DP_SISTEMATICO = 1.5

# Cenario "se o erro do 1o turno se repetir": tira de cada pesquisa esta
# fracao do erro de margem que o instituto cometeu em 4/10. Metade, e nao
# tudo, porque erro de uma eleicao so e meio pontaria, meio sorte.
FRACAO_VIES = 0.5

# Projecao para o dia da eleicao: tendencia medida DENTRO de cada instituto
# (cada casa comparada so com ela mesma, o que tira o efeito-casa) nos ultimos
# TENDENCIA_DIAS dias, estendida ate o pleito. Janela curta porque o que
# interessa e o movimento de agora: de 8 a 16/10 Lula subia 0,12/dia, e de
# 14/10 em diante parou - uma janela longa projetaria uma alta que acabou.
TENDENCIA_DIAS = 10
TENDENCIA_MIN_INSTITUTOS = 3   # casas com 2+ rodadas na janela

# Origem do peso de cada instituto. "erro_1t" (padrao) usa o erro medido em
# 4/10 (institutos.py); "pg" usa o ranking do PollsterGraph (pollstergraph.py)
# e grava em arquivos proprios, para a aba "Ranking PollsterGraph".
MODOS = {
    "erro_1t": {"json": "agregado.json", "painel": "painel.html",
                "publico": "painel_publico.html"},
    "pg": {"json": "agregado_pg.json", "painel": "painel_pg.html",
           "publico": "painel_pg_publico.html"},
}
PESO_INST = peso_instituto


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
        if correcoes.copia_do_resultado_1t(r):
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
        # validos calculados a partir do total arredondado (46 x 47) podem
        # sair meio ponto longe do que o instituto publicou (50 x 50); quando
        # o numero oficial esta em correcoes.py, ele prevalece
        oficial = correcoes.validos_oficiais(r)
        if oficial:
            va_val, vb_val = oficial[A], oficial[B]
        else:
            va_val, vb_val = 100 * va / total, 100 * vb / total
        saida.append({
            # renormaliza aqui tambem: o CSV pode ter sido gravado antes de um
            # apelido novo entrar em institutos.py
            "instituto": normalizar_instituto(r["instituto"]),
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
            "a": va_val,
            "b": vb_val,
            "validos_oficiais": bool(oficial),
        })
    return saida


# ------------------------------------------------------------------ pesos

def fator_amostra(n):
    if not n:
        return 1.0
    return max(AMOSTRA_MIN, min(AMOSTRA_MAX, math.sqrt(n / AMOSTRA_REF)))


def peso(p, referencia, meia_vida):
    """peso = instituto x recencia x amostra"""
    w_inst = PESO_INST(p["instituto"])
    dias = (referencia - p["data_fim"]).days
    w_rec = 0.5 ** (dias / meia_vida)
    w_amo = fator_amostra(p["amostra"])
    return w_inst * w_rec * w_amo


def elegiveis(pesquisas, referencia, janela):
    """So a pesquisa mais recente de cada instituto dentro da janela."""
    ultima = {}
    for p in pesquisas:
        if p["data_fim"] > referencia or (referencia - p["data_fim"]).days > janela:
            continue
        atual = ultima.get(p["instituto"])
        if atual is None or p["data_fim"] > atual["data_fim"]:
            ultima[p["instituto"]] = p
    return list(ultima.values())


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
    els = elegiveis(base, referencia, janela)
    if len(els) < 2:
        return None

    pesos = [peso(p, referencia, meia_vida) for p in els]
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
    margem_disp = 1.96 * dp / math.sqrt(n_ef) if n_ef > 1 else None

    # Piso amostral: a variancia da media ponderada de pesquisas independentes,
    # cada uma com seu proprio erro de amostra. Com poucas pesquisas a
    # dispersao e medida em dois ou tres pontos e pode sair menor que o erro de
    # QUALQUER pesquisa isolada - com Datafolha e PoderData concordando por
    # acaso, deu +/-0,6, quando cada uma sozinha ja tem +/-2. A margem da media
    # nao pode ser mais estreita que isso.
    var_amo = sum((w / den) ** 2 * (p["a"] * (100 - p["a"])) / (p["amostra"] or AMOSTRA_REF)
                  for p, w in zip(els, pesos))
    margem_amo = 1.96 * math.sqrt(var_amo)
    margem = max(margem_disp or 0.0, margem_amo)

    # Margem que cabe dizer ao leitor: a da media mais o erro que todos os
    # institutos podem cometer juntos. Dela sai a chance de cada lado.
    dp_total = math.sqrt((margem / 1.96) ** 2 + DP_SISTEMATICO ** 2)
    prob_b = 1 - normal_acumulada((va - 50) / dp_total)

    return {
        "a": va, "b": vb,
        "hipotetico": hipotetico,
        "margem_total": 1.96 * dp_total,
        "prob_a": 1 - prob_b,
        "prob_b": prob_b,
        "desvio": dp,
        "n": len(els),
        "n_efetivo": n_ef,
        "margem": margem,
        "min": min(p["a"] for p in els),
        "max": max(p["a"] for p in els),
    }


def normal_acumulada(z):
    return 0.5 * (1 + math.erf(z / math.sqrt(2)))


def mediana(xs):
    xs = sorted(xs)
    if not xs:
        return 0.0
    m = len(xs) // 2
    return xs[m] if len(xs) % 2 else (xs[m - 1] + xs[m]) / 2


def tendencia(pesquisas, referencia, dias=TENDENCIA_DIAS):
    """
    Inclinacao comum (pontos de votos validos de A por dia) com efeito fixo
    por instituto: so entram casas com 2+ rodadas na janela, e cada uma e
    centrada na propria media. Devolve (inclinacao, erro_padrao, n_casas) ou
    None se nao houver dado suficiente.
    """
    ini = referencia - timedelta(days=dias)
    por = {}
    for p in pesquisas:
        if p["real"] and ini <= p["data_fim"] <= referencia:
            por.setdefault(p["instituto"], []).append(p)
    xs, ys, casas = [], [], 0
    for ps in por.values():
        if len(ps) < 2 or len({p["data_fim"] for p in ps}) < 2:
            continue
        casas += 1
        mx = sum(p["data_fim"].toordinal() for p in ps) / len(ps)
        my = sum(p["a"] for p in ps) / len(ps)
        for p in ps:
            xs.append(p["data_fim"].toordinal() - mx)
            ys.append(p["a"] - my)
    # graus de liberdade: pontos - casas (medias) - 1 (inclinacao)
    gl = len(xs) - casas - 1
    if casas < TENDENCIA_MIN_INSTITUTOS or gl < 1:
        return None
    sxx = sum(x * x for x in xs)
    b = sum(x * y for x, y in zip(xs, ys)) / sxx
    res = sum((y - b * x) ** 2 for x, y in zip(xs, ys))
    se = math.sqrt(res / gl / sxx)
    return b, se, casas


def projetar(ag_, pesquisas, referencia, dia_eleicao):
    """Agregado de hoje + tendencia x dias ate o pleito, com a incerteza dela."""
    t = tendencia(pesquisas, referencia)
    dias = (dia_eleicao - referencia).days
    if t is None or dias <= 0:
        return None
    b, se, casas = t
    a = max(0.0, min(100.0, ag_["a"] + b * dias))
    dp = math.sqrt((ag_["margem_total"] / 1.96) ** 2 + (se * dias) ** 2)
    prob_b = 1 - normal_acumulada((a - 50) / dp)
    return {
        "a": round(a, 2), "b": round(100 - a, 2),
        "margem_total": round(1.96 * dp, 2),
        "prob_a": round(1 - prob_b, 3), "prob_b": round(prob_b, 3),
        "inclinacao_dia": round(b, 3),
        "inclinacao_ep": round(se, 3),
        "institutos": casas,
        "dias": dias,
        "janela_dias": TENDENCIA_DIAS,
    }


def corrigir_vies(pesquisas, fracao=FRACAO_VIES):
    """
    Desconta de cada pesquisa uma fracao do erro de margem que o instituto
    cometeu no 1o turno. erro_margem = (Flavio - Lula previsto) - real, entao
    quem subestimou o Flavio (erro negativo) tem a margem dele aumentada.
    Instituto sem medida recebe o erro MEDIANO - o mesmo criterio do peso.
    """
    erros = [d["erro_margem"] for d in ACURACIA.get("institutos", {}).values()]
    erro_tipico = mediana(erros)
    saida = []
    for p in pesquisas:
        e = erro_de(p["instituto"])
        if e is None:
            e = erro_tipico
        # a e Lula; a margem Flavio-Lula sobe -fracao*e, Lula cai metade disso
        a = p["a"] + fracao * e / 2
        a = max(0.0, min(100.0, a))
        saida.append(dict(p, a=a, b=100 - a))
    return saida, erro_tipico


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
    global PESO_INST
    janela = arg("--janela", JANELA_DIAS)
    meia_vida = arg("--meia-vida", MEIA_VIDA)
    modo = arg("--pesos", "erro_1t")
    if modo not in MODOS:
        print(f"--pesos deve ser um de: {', '.join(MODOS)}")
        sys.exit(1)
    pg = None
    if modo == "pg":
        import pollstergraph as pg
        PESO_INST = pg.peso_instituto

    pesquisas = ler_2t()
    if not pesquisas:
        print("Sem pesquisas de 2o turno - rode 'python coletar.py' antes.")
        sys.exit(1)

    hoje = max(p["data_fim"] for p in pesquisas)
    ag = agregar(pesquisas, hoje, janela, meia_vida)
    if not ag:
        print("Pesquisas insuficientes na janela.")
        sys.exit(1)

    proj = projetar(ag, pesquisas, hoje, date.fromisoformat(DIA_2T))

    pesq_cor, erro_tipico = corrigir_vies(pesquisas)
    cor = agregar(pesq_cor, hoje, janela, meia_vida)

    base, _hip = conjunto_valido(pesquisas, hoje)
    els = elegiveis(base, hoje, janela)
    pesos = {id(p): peso(p, hoje, meia_vida) for p in els}
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
            "pg": pg.carregar()[0].get(p["instituto"]) if pg else None,
        })

    historico = [{
        "instituto": p["instituto"],
        "data": p["data_fim"].isoformat(),
        "amostra": p["amostra"],
        "a": round(p["a"], 1), "b": round(p["b"], 1),
        "erro_1t": erro_de(p["instituto"]),
    } for p in sorted(pesquisas, key=lambda x: x["data_fim"], reverse=True)]

    dados = {
        "modo": modo,
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
            "dp_sistematico": DP_SISTEMATICO,
            "fracao_vies": FRACAO_VIES,
        },
        "ranking_pg": ({
            "fonte": pg.PAGINA,
            "melhor_indice": pg.carregar()[2],
            "peso_sem_nota": pg.carregar()[1],
            "institutos": pg.carregar()[0],
        } if pg else None),
        "acuracia_1t": ACURACIA.get("institutos", {}),
        "agregado": {
            "a": round(ag["a"], 2), "b": round(ag["b"], 2),
            "hipotetico": ag["hipotetico"],
            "n_reais": sum(1 for p in pesquisas if p["real"]),
            "margem": round(ag["margem"], 2) if ag["margem"] else None,
            "margem_total": round(ag["margem_total"], 2),
            "prob_a": round(ag["prob_a"], 3),
            "prob_b": round(ag["prob_b"], 3),
            "desvio": round(ag["desvio"], 2),
            "n": ag["n"],
            "n_efetivo": round(ag["n_efetivo"], 2),
            "min": round(ag["min"], 1), "max": round(ag["max"], 1),
        },
        "projecao": proj,
        "corrigido": {
            "a": round(cor["a"], 2), "b": round(cor["b"], 2),
            "margem_total": round(cor["margem_total"], 2),
            "prob_a": round(cor["prob_a"], 3),
            "prob_b": round(cor["prob_b"], 3),
            "fracao": FRACAO_VIES,
            "erro_tipico_1t": round(erro_tipico, 2),
        } if cor else None,
        "serie": serie(pesquisas, hoje, 120, janela, meia_vida),
        "pesquisas_janela": lista,
        "historico": historico,
    }

    with io.open(MODOS[modo]["json"], "w", encoding="utf-8") as f:
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
    print(f"  com erro sistematico: ±{ag['margem_total']:.1f} · chance "
          f"{A} {100*ag['prob_a']:.0f}% x {B} {100*ag['prob_b']:.0f}%")
    if proj:
        print(f"\n  tendencia ({proj['institutos']} institutos, {TENDENCIA_DIAS}d): "
              f"{A} {proj['inclinacao_dia']:+.2f} ±{1.96*proj['inclinacao_ep']:.2f} pp/dia")
        print(f"  projecao para {DIA_2T}: {A} {proj['a']:.1f} x {B} {proj['b']:.1f} "
              f"±{proj['margem_total']:.1f} · chance {A} {100*proj['prob_a']:.0f}%")
    if cor:
        print(f"\n  se {100*FRACAO_VIES:.0f}% do erro do 1o turno se repetir: "
              f"{A} {cor['a']:.1f} x {B} {cor['b']:.1f} · chance {B} {100*cor['prob_b']:.0f}%")
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

    print(f"\n{MODOS[modo]['json']} gravado.")
    gerar_painel(dados, saida=MODOS[modo]["painel"], saida_publica=MODOS[modo]["publico"])


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
