"""
Agrega as pesquisas de pesquisas_1t.csv / pesquisas_2t.csv em uma media
ponderada por nota do instituto, recencia e tamanho da amostra.

Gera:
  agregado.json  - numeros do agregador (serie temporal, medias, house effects)
  painel.html    - painel visual com esses dados embutidos

Uso:  python agregar.py [--janela 45] [--meia-vida 14]
"""

import csv
import json
import math
import sys
from collections import defaultdict
from datetime import date, timedelta

from institutos import (FATOR_AMOSTRA_FIXO, FORA_DA_DISPUTA, NOTAS,
                        NOTAS_ACEITAS, PESO_NOTA)

# ------------------------------------------------------------------ parametros

JANELA_DIAS = 45      # so pesquisas terminadas nos ultimos N dias entram na media
MEIA_VIDA = 14        # a cada N dias o peso de uma pesquisa cai pela metade
AMOSTRA_REF = 2000    # amostra de referencia para o fator de tamanho
AMOSTRA_MIN = 0.75    # limites do fator de amostra, para uma pesquisa grande
AMOSTRA_MAX = 1.40    # nao dominar sozinha o agregado

MIN_PESQUISAS_CAND = 2   # candidato precisa aparecer em >= N pesquisas da janela


def arg(nome, padrao):
    if nome in sys.argv:
        return type(padrao)(sys.argv[sys.argv.index(nome) + 1])
    return padrao


# ------------------------------------------------------------------ leitura

def ler_csv(caminho):
    with open(caminho, encoding="utf-8-sig", newline="") as f:
        linhas = list(csv.DictReader(f))
    saida = []
    for r in linhas:
        reg = {
            "instituto": r["instituto"],
            "data_fim": date.fromisoformat(r["data_fim"]),
            "amostra": int(r["amostra"]) if r.get("amostra") else None,
            "margem": float(r["margem"]) if r.get("margem") else None,
            "valores": {},
        }
        if "cenario" in r:
            reg["cenario"] = r["cenario"]
        for k, v in r.items():
            if k in ("instituto", "data_inicio", "data_fim", "amostra", "margem", "cenario"):
                continue
            if v not in (None, ""):
                reg["valores"][k] = float(v)
        saida.append(reg)
    return saida


# ------------------------------------------------------------------ pesos

def fator_amostra(n, instituto=None):
    """
    Peso por tamanho de amostra: sqrt(n/2000), limitado a [0,75 - 1,40].

    Institutos em FATOR_AMOSTRA_FIXO ignoram a regra e usam o valor de la -
    ver o comentario em institutos.py sobre a AtlasIntel e o painel online.
    """
    if instituto in FATOR_AMOSTRA_FIXO:
        return FATOR_AMOSTRA_FIXO[instituto]
    if not n:
        return 1.0
    f = math.sqrt(n / AMOSTRA_REF)
    return max(AMOSTRA_MIN, min(AMOSTRA_MAX, f))


def peso_pesquisa(p, referencia, ordem_no_instituto, meia_vida=MEIA_VIDA):
    """
    peso = nota x recencia x amostra x repeticao

    'repeticao' evita que um instituto que publica toda semana domine a media:
    a k-esima pesquisa mais recente daquele instituto vale 1/sqrt(k).
    """
    nota = NOTAS.get(p["instituto"], {}).get("nota", "A-")
    w_nota = PESO_NOTA.get(nota, 0.5)
    dias = (referencia - p["data_fim"]).days
    w_rec = 0.5 ** (dias / meia_vida)
    w_amo = fator_amostra(p["amostra"], p["instituto"])
    w_rep = 1 / math.sqrt(ordem_no_instituto)
    return w_nota * w_rec * w_amo * w_rep


def media_ponderada(pesquisas, candidatos, referencia, janela, meia_vida):
    """
    Media ponderada de cada candidato usando as pesquisas com data_fim <= referencia
    e dentro da janela. Devolve (medias, detalhe).
    """
    elegiveis = [p for p in pesquisas
                 if p["data_fim"] <= referencia
                 and (referencia - p["data_fim"]).days <= janela]
    if not elegiveis:
        return {}, {}

    # ordem de cada pesquisa dentro do proprio instituto (1 = mais recente)
    por_inst = defaultdict(list)
    for p in sorted(elegiveis, key=lambda x: x["data_fim"], reverse=True):
        por_inst[p["instituto"]].append(p)
    ordem = {}
    for inst, lista in por_inst.items():
        for i, p in enumerate(lista, start=1):
            ordem[id(p)] = i

    medias, detalhe = {}, {}
    for c in candidatos:
        num = den = 0.0
        vals, pesos = [], []
        for p in elegiveis:
            v = p["valores"].get(c)
            if v is None:
                continue
            w = peso_pesquisa(p, referencia, ordem[id(p)], meia_vida)
            num += w * v
            den += w
            vals.append(v)
            pesos.append(w)
        if den == 0 or len(vals) < 1:
            continue
        m = num / den
        # desvio padrao ponderado das pesquisas: mede o quanto os institutos
        # discordam entre si sobre este candidato
        var = sum(w * (v - m) ** 2 for v, w in zip(vals, pesos)) / den if len(vals) > 1 else 0.0
        dp = math.sqrt(var)

        # Numero EFETIVO de pesquisas: (soma dos pesos)^2 / soma dos quadrados.
        # Doze pesquisas muito desiguais em peso valem menos que doze iguais.
        s2 = sum(w * w for w in pesos)
        n_ef = (den * den / s2) if s2 else 0.0

        # Margem do agregado: erro padrao da media ponderada, a 95%.
        #
        # E deliberadamente a dispersao observada, e nao sqrt(p(1-p)/n) sobre a
        # amostra somada. A formula teorica daria +/-0,6 pp aqui, o que seria
        # falso: ela supoe pesquisas como amostras aleatorias independentes da
        # mesma populacao, e cada instituto carrega vies proprio de metodo que
        # nao desaparece somando entrevistados. A discordancia entre eles ja
        # embute erro amostral E vies de metodo.
        margem = 1.96 * dp / math.sqrt(n_ef) if n_ef > 1 else None

        medias[c] = m
        detalhe[c] = {
            "media": m,
            "desvio": dp,
            "n": len(vals),
            "n_efetivo": n_ef,
            "margem": margem,
            "min": min(vals),
            "max": max(vals),
            "peso_total": den,
        }
    return medias, detalhe


def para_validos(medias):
    """Reescala para 100% excluindo indecisos/brancos/nulos (votos validos)."""
    total = sum(v for k, v in medias.items() if k not in ("Indefinidos", "Outros"))
    if total <= 0:
        return {}
    return {k: v * 100 / total for k, v in medias.items()
            if k not in ("Indefinidos", "Outros")}


# ------------------------------------------------------------------ analise

def candidatos_relevantes(pesquisas, referencia, janela, minimo=MIN_PESQUISAS_CAND):
    cont = defaultdict(int)
    for p in pesquisas:
        if (referencia - p["data_fim"]).days <= janela and p["data_fim"] <= referencia:
            for c, v in p["valores"].items():
                if c in ("Indefinidos", "Outros") or v is None:
                    continue
                if c in FORA_DA_DISPUTA:     # saiu da disputa: nao entra na conta
                    continue
                cont[c] += 1
    return [c for c, n in sorted(cont.items(), key=lambda x: -x[1]) if n >= minimo]


def house_effects(pesquisas, candidatos, referencia, janela, meia_vida):
    """
    Vies medio de cada instituto: quanto ele fica acima/abaixo do agregado
    calculado na data de cada uma de suas pesquisas, EM VOTOS VALIDOS.

    A comparacao e feita em votos validos de proposito: institutos com taxas de
    indecisos muito diferentes (AtlasIntel ~1%, MDA ~14%) deslocariam todos os
    candidatos para cima ou para baixo ao mesmo tempo no numero bruto, o que
    seria lido como vies quando e so metodologia de quem nao declara voto.
    """
    efeitos = defaultdict(lambda: defaultdict(list))
    for p in pesquisas:
        if (referencia - p["data_fim"]).days > janela * 3:
            continue
        base, _ = media_ponderada(
            [q for q in pesquisas if q["instituto"] != p["instituto"]],
            candidatos, p["data_fim"], janela, meia_vida,
        )
        if not base:
            continue
        # os dois lados sao normalizados sobre a INTERSECAO de candidatos: so
        # assim as duas porcentagens tem o mesmo denominador. Normalizar sobre
        # listas diferentes infla quem publica menos nomes na pesquisa.
        comuns = [c for c in base if p["valores"].get(c) is not None]
        if len(comuns) < 2:
            continue
        base_val = para_validos({c: base[c] for c in comuns})
        prop_val = para_validos({c: p["valores"][c] for c in comuns})
        for c in candidatos:
            v, b = prop_val.get(c), base_val.get(c)
            if v is not None and b is not None:
                efeitos[p["instituto"]][c].append(v - b)
    return {
        inst: {c: sum(l) / len(l) for c, l in cands.items() if l}
        for inst, cands in efeitos.items()
    }


def serie_temporal(pesquisas, candidatos, fim, dias, janela, meia_vida):
    """Media ponderada recalculada dia a dia, para o grafico de tendencia."""
    serie = []
    inicio = fim - timedelta(days=dias)
    d = inicio
    while d <= fim:
        m, det = media_ponderada(pesquisas, candidatos, d, janela, meia_vida)
        if m:
            ponto = {"data": d.isoformat()}
            for c in candidatos:
                if c in m:
                    ponto[c] = round(m[c], 2)
                    ponto[c + "__dp"] = round(det[c]["desvio"], 2)
            serie.append(ponto)
        d += timedelta(days=1)
    return serie


def margem_duelo(pesquisas, dois, referencia, janela, meia_vida):
    """
    Margem do confronto de 2o turno, a 95%.

    Aqui cada pesquisa e convertida para votos validos ANTES de entrar na
    media: num duelo a soma tem de fechar em 100, e institutos com taxas de
    indecisos muito diferentes (1% na AtlasIntel, 13% no MDA) nao podem
    deslocar a base de comparacao.
    """
    a, b = dois
    els = [p for p in pesquisas
           if p["data_fim"] <= referencia
           and (referencia - p["data_fim"]).days <= janela
           and p["valores"].get(a) is not None
           and p["valores"].get(b) is not None]
    if len(els) < 2:
        return None

    por_inst = defaultdict(list)
    for p in sorted(els, key=lambda x: x["data_fim"], reverse=True):
        por_inst[p["instituto"]].append(p)
    ordem = {}
    for lista in por_inst.values():
        for i, p in enumerate(lista, start=1):
            ordem[id(p)] = i

    vals, pesos = [], []
    for p in els:
        total = p["valores"][a] + p["valores"][b]
        if total <= 0:
            continue
        vals.append(100 * p["valores"][a] / total)
        pesos.append(peso_pesquisa(p, referencia, ordem[id(p)], meia_vida))

    den = sum(pesos)
    if den <= 0 or len(vals) < 2:
        return None
    m = sum(v * w for v, w in zip(vals, pesos)) / den
    var = sum(w * (v - m) ** 2 for v, w in zip(vals, pesos)) / den
    s2 = sum(w * w for w in pesos)
    n_ef = den * den / s2 if s2 else 0.0
    if n_ef <= 1:
        return None
    return round(1.96 * math.sqrt(var) / math.sqrt(n_ef), 2)


# ------------------------------------------------------------------ painel

def gerar_painel(dados, modelo="painel_modelo.html", saida="painel.html",
                 saida_publica="painel_publico.html"):
    """
    Injeta os dados no template e grava duas versoes:

      painel.html          - corpo da pagina, para publicar como Artifact
                             (o Artifact envolve o arquivo no <html>/<head> dele)
      painel_publico.html   - documento HTML completo e autonomo, que abre com
                             duplo clique e pode ser hospedado em qualquer lugar
    """
    try:
        with open(modelo, encoding="utf-8") as f:
            html = f.read()
    except FileNotFoundError:
        print(f"(aviso) {modelo} nao encontrado - painel nao foi gerado.")
        return

    # </script> dentro do JSON encerraria o bloco <script> antes da hora
    bruto = json.dumps(dados, ensure_ascii=False).replace("</", "<\\/")
    corpo = html.replace("/*__DADOS__*/", bruto)

    with open(saida, "w", encoding="utf-8") as f:
        f.write(corpo)
    print(f"{saida} gravado.")

    # versao autonoma: mesmo conteudo, com o documento fechado em volta
    completo = (
        "<!doctype html>\n"
        '<html lang="pt-BR">\n<head>\n'
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        '<meta name="description" content="Media ponderada das pesquisas '
        'presidenciais de 2026 usando so os institutos com nota A-, A ou A+.">\n'
        '<meta name="color-scheme" content="light dark">\n'
        "<style>img{max-width:100%}[hidden]{display:none!important}</style>\n"
        "</head>\n<body>\n" + corpo + "\n</body>\n</html>\n"
    )
    with open(saida_publica, "w", encoding="utf-8") as f:
        f.write(completo)
    print(f"{saida_publica} gravado (arquivo unico, abre em qualquer navegador).")


# ------------------------------------------------------------------ principal

def main():
    janela = arg("--janela", JANELA_DIAS)
    meia_vida = arg("--meia-vida", MEIA_VIDA)

    p1 = ler_csv("pesquisas_1t.csv")
    p2 = ler_csv("pesquisas_2t.csv")
    if not p1:
        print("pesquisas_1t.csv vazio - rode 'python coletar.py' antes.")
        return

    hoje = max(p["data_fim"] for p in p1)
    cands = candidatos_relevantes(p1, hoje, janela)

    medias, detalhe = media_ponderada(p1, cands, hoje, janela, meia_vida)
    validos = para_validos(medias)
    he = house_effects(p1, cands, hoje, janela, meia_vida)
    serie = serie_temporal(p1, cands, hoje, 180, janela, meia_vida)

    # ---- pesquisas da janela, com o peso que cada uma recebeu
    elegiveis = sorted([p for p in p1 if (hoje - p["data_fim"]).days <= janela],
                       key=lambda x: x["data_fim"], reverse=True)
    por_inst = defaultdict(list)
    for p in elegiveis:
        por_inst[p["instituto"]].append(p)
    ordem = {id(p): i for lista in por_inst.values() for i, p in enumerate(lista, 1)}
    peso_total = sum(peso_pesquisa(p, hoje, ordem[id(p)], meia_vida) for p in elegiveis) or 1

    lista_pesquisas = []
    for p in elegiveis:
        w = peso_pesquisa(p, hoje, ordem[id(p)], meia_vida)
        lista_pesquisas.append({
            "instituto": p["instituto"],
            "nota": NOTAS.get(p["instituto"], {}).get("nota", "?"),
            "data": p["data_fim"].isoformat(),
            "amostra": p["amostra"],
            "margem": p["margem"],
            "peso": round(w, 4),
            "peso_pct": round(100 * w / peso_total, 1),
            "valores": {c: p["valores"].get(c) for c in cands if c in p["valores"]},
        })

    # ---- historico completo (todas as pesquisas, para a tabela de conferencia)
    historico = [{
        "instituto": p["instituto"],
        "nota": NOTAS.get(p["instituto"], {}).get("nota", "?"),
        "data": p["data_fim"].isoformat(),
        "amostra": p["amostra"],
        "valores": {c: v for c, v in p["valores"].items() if v is not None},
    } for p in sorted(p1, key=lambda x: x["data_fim"], reverse=True)]

    # ---- segundo turno, por cenario
    cenarios = []
    por_cenario = defaultdict(list)
    for p in p2:
        por_cenario[p.get("cenario", "")].append(p)
    for nome, lista in por_cenario.items():
        if not nome or "hipótese" in nome.lower():
            continue
        fim_c = max(p["data_fim"] for p in lista)
        if (hoje - fim_c).days > janela:
            continue
        cands_c = candidatos_relevantes(lista, hoje, janela, minimo=1)
        cands_c = [c for c in cands_c if c != "Indefinidos"][:2]
        if len(cands_c) < 2:
            continue
        m, det = media_ponderada(lista, cands_c, hoje, janela, meia_vida)
        if len(m) < 2:
            continue
        v = para_validos(m)
        cenarios.append({
            "cenario": nome,
            "a": cands_c[0], "b": cands_c[1],
            "va": round(m.get(cands_c[0], 0), 1),
            "vb": round(m.get(cands_c[1], 0), 1),
            "va_valido": round(v.get(cands_c[0], 0), 1),
            "vb_valido": round(v.get(cands_c[1], 0), 1),
            "n": max(det[c]["n"] for c in cands_c if c in det),
            "margem": margem_duelo(lista, cands_c, hoje, janela, meia_vida),
            "ultima": fim_c.isoformat(),
        })
    cenarios.sort(key=lambda x: -(x["va_valido"] - x["vb_valido"]))

    dados = {
        "atualizado": date.today().isoformat(),
        "data_ultima_pesquisa": hoje.isoformat(),
        "parametros": {
            "janela_dias": janela,
            "meia_vida_dias": meia_vida,
            "amostra_ref": AMOSTRA_REF,
            "peso_nota": PESO_NOTA,
            "fator_amostra_fixo": FATOR_AMOSTRA_FIXO,
        },
        "institutos": NOTAS,
        "notas_aceitas": sorted(NOTAS_ACEITAS),
        "fora_da_disputa": FORA_DA_DISPUTA,
        "candidatos": cands,
        "agregado": {c: {
            "media": round(detalhe[c]["media"], 2),
            "valido": round(validos.get(c, 0), 2),
            "desvio": round(detalhe[c]["desvio"], 2),
            "n": detalhe[c]["n"],
            "n_efetivo": round(detalhe[c]["n_efetivo"], 2),
            "margem": (round(detalhe[c]["margem"], 2)
                       if detalhe[c]["margem"] is not None else None),
            "min": detalhe[c]["min"],
            "max": detalhe[c]["max"],
        } for c in cands if c in detalhe},
        "serie": serie,
        "house_effects": {i: {c: round(v, 2) for c, v in d.items()} for i, d in he.items()},
        "pesquisas_janela": lista_pesquisas,
        "historico": historico,
        "segundo_turno": cenarios,
        "historico_2t": [{
            "cenario": p.get("cenario", ""),
            "instituto": p["instituto"],
            "nota": NOTAS.get(p["instituto"], {}).get("nota", "?"),
            "data": p["data_fim"].isoformat(),
            "amostra": p["amostra"],
            "valores": {c: v for c, v in p["valores"].items() if v is not None},
        } for p in sorted(p2, key=lambda x: x["data_fim"], reverse=True)],
    }

    with open("agregado.json", "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=1)

    gerar_painel(dados)

    # ---------------- resumo no terminal
    print(f"Agregador - 1o turno (janela {janela}d, meia-vida {meia_vida}d)")
    print(f"Ultima pesquisa: {hoje.isoformat()}   "
          f"{len(lista_pesquisas)} pesquisas na janela\n")
    print(f"  {'candidato':<12} {'bruto':>7} {'validos':>9} {'disp.':>7}  {'n':>3}")
    for c in sorted(detalhe, key=lambda x: -detalhe[x]["media"]):
        if c in ("Indefinidos", "Outros"):
            continue
        d = detalhe[c]
        print(f"  {c:<12} {d['media']:>6.1f}% {validos.get(c, 0):>8.1f}% "
              f"{d['min']:>3.0f}-{d['max']:<3.0f} {d['n']:>3}")
    if "Indefinidos" in detalhe:
        print(f"  {'(indecisos)':<12} {detalhe['Indefinidos']['media']:>6.1f}%")

    print("\nPeso de cada pesquisa na media:")
    for p in lista_pesquisas:
        print(f"  {p['data']}  {p['instituto']:<20} {p['nota']:<2} "
              f"amostra {str(p['amostra'] or '-'):>5}  peso {p['peso_pct']:>5.1f}%")

    if cenarios:
        print("\n2o turno (votos validos):")
        for c in cenarios:
            print(f"  {c['cenario']:<28} {c['a']} {c['va_valido']:>5.1f}%  x  "
                  f"{c['b']} {c['vb_valido']:>5.1f}%   (n={c['n']})")

    print("\nHouse effects (desvio medio vs. os demais institutos):")
    for inst, d in sorted(he.items()):
        tops = ", ".join(f"{c} {v:+.1f}" for c, v in list(d.items())[:4])
        print(f"  {inst:<20} {tops}")

    print("\nagregado.json gravado.")


if __name__ == "__main__":
    main()
