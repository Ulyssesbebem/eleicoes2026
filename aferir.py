"""
Afere o vies pesquisa -> urna: compara o agregado das pesquisas finais de
2018 e 2022 com o resultado oficial do TSE.

Projeto separado do agregador de 2026. Nao altera coletar.py nem agregar.py.

Gera:
  aferição.json  - numeros da aferição
  aferidor.html  - painel visual (se aferidor_modelo.html existir)

Uso:  python aferir.py [--dias 7]
"""

import csv
import json
import math
import sys
from collections import defaultdict
from datetime import date

from institutos import NOTAS, PESO_NOTA, normalizar_instituto
from resultados import CAMPOS, RESULTADOS

DIAS_FINAIS = 7        # pesquisas encerradas ate N dias antes da eleicao
AMOSTRA_REF = 2000
AMOSTRA_MIN, AMOSTRA_MAX = 0.75, 1.40
MEIA_VIDA = 10         # calibrado em calibrar.py


def arg(nome, padrao):
    if nome in sys.argv:
        return type(padrao)(sys.argv[sys.argv.index(nome) + 1])
    return padrao


# ------------------------------------------------------------------ leitura

def ler(caminho):
    with open(caminho, encoding="utf-8-sig", newline="") as f:
        linhas = list(csv.DictReader(f))
    saida = []
    for r in linhas:
        reg = {
            "instituto_bruto": r["instituto"],
            "instituto": normalizar_instituto(r["instituto"]),
            "data_fim": date.fromisoformat(r["data_fim"]),
            "amostra": int(r["amostra"]) if r.get("amostra") else None,
            "valores": {},
        }
        for k, v in r.items():
            if k in ("instituto", "data_inicio", "data_fim", "amostra", "margem"):
                continue
            if v not in (None, ""):
                try:
                    reg["valores"][k] = float(v)
                except ValueError:
                    pass
        saida.append(reg)
    return saida


# ------------------------------------------------------------------ pesos

def peso(p, ref, k, meia_vida):
    nota = NOTAS.get(p["instituto"], {}).get("nota")
    w_nota = PESO_NOTA.get(nota, 0.55) if nota else 0.55
    dias = (ref - p["data_fim"]).days
    w_amo = 1.0
    if p["amostra"]:
        w_amo = max(AMOSTRA_MIN, min(AMOSTRA_MAX, math.sqrt(p["amostra"] / AMOSTRA_REF)))
    return w_nota * (0.5 ** (dias / meia_vida)) * w_amo / math.sqrt(k)


def agregar(pesquisas, cands, ref, meia_vida):
    ordenadas = sorted(pesquisas, key=lambda x: x["data_fim"], reverse=True)
    vistos = defaultdict(int)
    pesos = {}
    for p in ordenadas:
        vistos[p["instituto"]] += 1
        pesos[id(p)] = peso(p, ref, vistos[p["instituto"]], meia_vida)

    out = {}
    for c in cands:
        num = den = 0.0
        for p in ordenadas:
            v = p["valores"].get(c)
            if v is None:
                continue
            num += pesos[id(p)] * v
            den += pesos[id(p)]
        if den:
            out[c] = num / den
    return out


def validos(d):
    t = sum(v for k, v in d.items() if k not in ("Indefinidos", "Outros"))
    if t <= 0:
        return {}
    return {k: v * 100 / t for k, v in d.items() if k not in ("Indefinidos", "Outros")}


def comparavel(pesquisa_vals, oficial):
    """
    Normaliza os dois lados sobre a INTERSECAO de candidatos, para que as
    porcentagens tenham o mesmo denominador.
    """
    comuns = [c for c in oficial if pesquisa_vals.get(c) is not None]
    if len(comuns) < 2:
        return {}, {}
    return (validos({c: pesquisa_vals[c] for c in comuns}),
            validos({c: oficial[c] for c in comuns}))


# ------------------------------------------------------------------ aferição

def aferir_eleicao(ano, dias_finais, meia_vida, so_nota_a=False, turno=1):
    info = RESULTADOS[ano]
    if turno == 1:
        arquivo = f"pesquisas_{ano}.csv"
        dia = date.fromisoformat(info["dia_1t"])
        oficial = info["turno1"]
    else:
        arquivo = f"pesquisas_{ano}_2t.csv"
        dia = date.fromisoformat(info["dia_2t"])
        oficial = info["turno2"]
    try:
        p = ler(arquivo)
    except FileNotFoundError:
        return None

    finais = [q for q in p if 0 <= (dia - q["data_fim"]).days <= dias_finais]
    if so_nota_a:
        finais = [q for q in finais if q["instituto"] in NOTAS]
    if not finais:
        return None

    cands = list(oficial)
    bruto = agregar(finais, cands, dia, meia_vida)
    prev, real = comparavel(bruto, oficial)
    if not prev:
        return None

    erros = {c: prev[c] - real[c] for c in prev}
    campo = CAMPOS.get(ano, {})

    # ---- por instituto: a ultima pesquisa de cada um
    por_inst = {}
    ultimas = {}
    for q in finais:
        if q["instituto"] not in ultimas or q["data_fim"] > ultimas[q["instituto"]]["data_fim"]:
            ultimas[q["instituto"]] = q
    for inst, q in ultimas.items():
        pv, rv = comparavel(q["valores"], oficial)
        if not pv:
            continue
        por_inst[inst] = {
            "data": q["data_fim"].isoformat(),
            "amostra": q["amostra"],
            "nota": NOTAS.get(inst, {}).get("nota"),
            "erros": {c: round(pv[c] - rv[c], 2) for c in pv},
            "previsto": {c: round(pv[c], 2) for c in pv},
        }

    return {
        "ano": ano,
        "turno": turno,
        "dia_eleicao": info["dia_1t"] if turno == 1 else info["dia_2t"],
        "n_pesquisas": len(finais),
        "institutos": sorted({q["instituto"] for q in finais}),
        "previsto": {c: round(prev[c], 2) for c in prev},
        "oficial": {c: round(real[c], 2) for c in real},
        "erros": {c: round(erros[c], 2) for c in erros},
        "erro_direita": round(erros.get(campo.get("direita"), 0.0), 2),
        "erro_esquerda": round(erros.get(campo.get("esquerda"), 0.0), 2),
        "campo": campo,
        "mae": round(sum(abs(e) for e in erros.values()) / len(erros), 2),
        "por_instituto": por_inst,
    }


# ------------------------------------------------------------------ saida

def linha(rot, valor, largura=26):
    return f"  {rot:<{largura}} {valor}"


def main():
    dias = arg("--dias", DIAS_FINAIS)
    meia_vida = arg("--meia-vida", MEIA_VIDA)

    saida = {"dias_finais": dias, "meia_vida": meia_vida, "eleicoes": []}

    for ano in sorted(RESULTADOS):
        a = aferir_eleicao(ano, dias, meia_vida)
        if not a:
            print(f"{ano}: sem pesquisas na janela final.")
            continue
        saida["eleicoes"].append(a)

        campo = a["campo"]
        print(f"\n{'=' * 62}\n{ano} - 1o turno em {a['dia_eleicao']}   "
              f"({a['n_pesquisas']} pesquisas nos {dias} dias finais)\n{'=' * 62}")
        print(f"  {'candidato':<14}{'agregado':>10}{'urna':>9}{'erro':>9}")
        for c in sorted(a["erros"], key=lambda x: -a["oficial"][x]):
            print(f"  {c:<14}{a['previsto'][c]:>9.1f}%{a['oficial'][c]:>8.1f}%"
                  f"{a['erros'][c]:>+9.1f}")
        print(f"\n  erro medio absoluto: {a['mae']:.2f} pp")
        if campo:
            print(f"  candidato da direita ({campo['direita']}): "
                  f"{a['erro_direita']:+.1f} pp")
            print(f"  candidato da esquerda ({campo['esquerda']}): "
                  f"{a['erro_esquerda']:+.1f} pp")

        print("\n  Por instituto (erro na dupla de frente):")
        for inst, d in sorted(a["por_instituto"].items(),
                              key=lambda x: x[1]["erros"].get(campo.get("direita"), 0)):
            nota = d["nota"] or "—"
            ed = d["erros"].get(campo.get("direita"))
            ee = d["erros"].get(campo.get("esquerda"))
            marca = " *" if d["nota"] else "  "
            print(f"   {marca}{inst[:26]:<26} nota {nota:<3} "
                  f"{campo.get('direita', '')} {ed:+6.1f}   "
                  f"{campo.get('esquerda', '')} {ee:+6.1f}")
        print("\n   * instituto que entra no agregador de 2026")

    # ---- segundo turno
    saida["eleicoes_2t"] = []
    for ano in sorted(RESULTADOS):
        a = aferir_eleicao(ano, dias, meia_vida, turno=2)
        if not a:
            print(f"\n{ano} 2o turno: sem pesquisas na janela final.")
            continue
        saida["eleicoes_2t"].append(a)
        campo = a["campo"]
        print(f"\n{'=' * 62}\n{ano} - 2o TURNO em {a['dia_eleicao']}   "
              f"({a['n_pesquisas']} pesquisas nos {dias} dias finais)\n{'=' * 62}")
        print(f"  {'candidato':<14}{'agregado':>10}{'urna':>9}{'erro':>9}")
        for c in sorted(a["erros"], key=lambda x: -a["oficial"][x]):
            print(f"  {c:<14}{a['previsto'][c]:>9.1f}%{a['oficial'][c]:>8.1f}%"
                  f"{a['erros'][c]:>+9.1f}")
        print(f"\n  candidato da direita ({campo['direita']}): {a['erro_direita']:+.1f} pp")
        print("\n  Por instituto:")
        for inst, d in sorted(a["por_instituto"].items(),
                              key=lambda x: x[1]["erros"].get(campo.get("direita"), 0)):
            marca = " *" if d["nota"] else "  "
            print(f"   {marca}{inst[:28]:<28} nota {d['nota'] or '—':<3} "
                  f"{campo['direita']} {d['erros'].get(campo['direita']):+6.1f}")

    if saida["eleicoes_2t"]:
        d2 = [a["erro_direita"] for a in saida["eleicoes_2t"]]
        saida["vies_medio_direita_2t"] = round(sum(d2) / len(d2), 2)
        print(f"\n  Vies medio na direita, 2o turno: "
              f"{saida['vies_medio_direita_2t']:+.1f} pp")

    # ---- os institutos nota A foram melhores que o mercado?
    print(f"\n{'=' * 62}\nSO OS INSTITUTOS NOTA A x TODO O MERCADO\n{'=' * 62}")
    print(f"  {'':<6}{'todos':>22}{'so nota A':>22}")
    print(f"  {'':<6}{'direita':>11}{'erro med':>11}{'direita':>11}{'erro med':>11}")
    comparativo = []
    for ano in sorted(RESULTADOS):
        todos = aferir_eleicao(ano, dias, meia_vida, so_nota_a=False)
        soa = aferir_eleicao(ano, dias, meia_vida, so_nota_a=True)
        if not todos or not soa:
            continue
        comparativo.append({
            "ano": ano,
            "todos": {"direita": todos["erro_direita"], "mae": todos["mae"],
                      "n": todos["n_pesquisas"]},
            "so_nota_a": {"direita": soa["erro_direita"], "mae": soa["mae"],
                          "n": soa["n_pesquisas"], "institutos": soa["institutos"]},
        })
        print(f"  {ano:<6}{todos['erro_direita']:>+10.1f}{todos['mae']:>11.2f}"
              f"{soa['erro_direita']:>+11.1f}{soa['mae']:>11.2f}")
    saida["comparativo_nota_a"] = comparativo

    # ---- sintese
    if len(saida["eleicoes"]) >= 1:
        print(f"\n{'=' * 62}\nSINTESE\n{'=' * 62}")
        dir_erros = [a["erro_direita"] for a in saida["eleicoes"]]
        esq_erros = [a["erro_esquerda"] for a in saida["eleicoes"]]
        media_dir = sum(dir_erros) / len(dir_erros)
        media_esq = sum(esq_erros) / len(esq_erros)
        saida["vies_medio_direita"] = round(media_dir, 2)
        saida["vies_medio_esquerda"] = round(media_esq, 2)
        for a in saida["eleicoes"]:
            print(linha(f"{a['ano']} direita", f"{a['erro_direita']:+.1f} pp"))
            print(linha(f"{a['ano']} esquerda", f"{a['erro_esquerda']:+.1f} pp"))
        print()
        print(linha("vies medio na direita", f"{media_dir:+.1f} pp"))
        print(linha("vies medio na esquerda", f"{media_esq:+.1f} pp"))
        print("\n  Sinal negativo = o agregado SUBESTIMOU o candidato.")
        if len(saida["eleicoes"]) < 2:
            print("\n  AVISO: so uma eleicao aferida - isso nao e um padrao.")

        # ---- o que isso implicaria em 2026, se o vies se repetisse
        try:
            with open("agregado.json", encoding="utf-8") as f:
                atual = json.load(f)
        except FileNotFoundError:
            atual = None
        if atual:
            campo26 = CAMPOS[2026]
            brutos = {c: d["media"] for c, d in atual["agregado"].items()}
            hoje_val = validos(brutos)
            ajuste = {campo26["direita"]: -media_dir, campo26["esquerda"]: -media_esq}
            corrigido = {c: v + ajuste.get(c, 0.0) for c, v in hoje_val.items()}
            corrigido = validos(corrigido)
            saida["projecao_2026"] = {
                "sem_correcao": {c: round(v, 1) for c, v in hoje_val.items()},
                "com_correcao": {c: round(v, 1) for c, v in corrigido.items()},
                "ajuste_aplicado": {c: round(v, 1) for c, v in ajuste.items()},
            }
            print(f"\n{'=' * 62}\nSE O MESMO VIES SE REPETISSE EM 2026 (votos validos)\n{'=' * 62}")
            print(f"  {'candidato':<14}{'agregado':>11}{'corrigido':>12}{'delta':>9}")
            for c in sorted(hoje_val, key=lambda x: -hoje_val[x])[:5]:
                d = corrigido.get(c, 0) - hoje_val[c]
                print(f"  {c:<14}{hoje_val[c]:>10.1f}%{corrigido.get(c, 0):>11.1f}%"
                      f"{d:>+9.1f}")
            print("\n  ISTO NAO E UMA PREVISAO. Sao duas eleicoes; o vies pode nao")
            print("  se repetir, e Flavio Bolsonaro nao e Jair Bolsonaro.")

            # ---- 2o turno de 2026: usa o vies de 2o turno, que e outro
            vies2 = saida.get("vies_medio_direita_2t")
            cen = next((c for c in atual.get("segundo_turno", [])
                        if campo26["direita"] in (c["a"], c["b"])
                        and campo26["esquerda"] in (c["a"], c["b"])), None)
            if cen and vies2 is not None:
                dir_, esq_ = campo26["direita"], campo26["esquerda"]
                v = {c: (cen["va_valido"] if cen["a"] == c else cen["vb_valido"])
                     for c in (dir_, esq_)}
                corr = validos({dir_: v[dir_] - vies2, esq_: v[esq_] + vies2})
                saida["projecao_2026_2t"] = {
                    "sem_correcao": {c: round(x, 1) for c, x in v.items()},
                    "com_correcao": {c: round(x, 1) for c, x in corr.items()},
                    "vies_aplicado": vies2,
                }
                print(f"\n  2o turno {esq_} x {dir_}:")
                print(f"    sem correcao : {esq_} {v[esq_]:.1f}%  x  {dir_} {v[dir_]:.1f}%")
                print(f"    com correcao : {esq_} {corr[esq_]:.1f}%  x  "
                      f"{dir_} {corr[dir_]:.1f}%   (vies de 2o turno: {vies2:+.1f} pp)")

    with open("afericao.json", "w", encoding="utf-8") as f:
        json.dump(saida, f, ensure_ascii=False, indent=1)
    print("\nafericao.json gravado.")

    gerar_painel(saida)


def gerar_painel(dados, modelo="aferidor_modelo.html", saida="aferidor.html",
                 saida_publica="aferidor_publico.html"):
    try:
        with open(modelo, encoding="utf-8") as f:
            html = f.read()
    except FileNotFoundError:
        return
    bruto = json.dumps(dados, ensure_ascii=False).replace("</", "<\\/")
    corpo = html.replace("/*__DADOS__*/", bruto)
    with open(saida, "w", encoding="utf-8") as f:
        f.write(corpo)
    completo = (
        '<!doctype html>\n<html lang="pt-BR">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        '<meta name="color-scheme" content="light dark">\n'
        "<style>img{max-width:100%}[hidden]{display:none!important}</style>\n"
        "</head>\n<body>\n" + corpo + "\n</body>\n</html>\n"
    )
    with open(saida_publica, "w", encoding="utf-8") as f:
        f.write(completo)
    print(f"{saida} e {saida_publica} gravados.")


if __name__ == "__main__":
    main()
