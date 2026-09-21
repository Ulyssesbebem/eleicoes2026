"""
Projeta o 2o turno de 2026 por unidade federativa por SWING UNIFORME.

O metodo: mede o quanto o agregado nacional de hoje se moveu em relacao ao
resultado de 2022 (em votos validos) e aplica esse mesmo deslocamento a cada
estado sobre o que ele votou em 2022.

  lula_uf_2026 = lula_uf_2022 + (lula_nacional_2026 - lula_nacional_2022)

Isto e MODELO, nao medicao. Nao existem pesquisas presidenciais estaduais dos
institutos nota A: eles medem presidente no nacional e, no estadual, medem
governador. O pressuposto de que todos os estados andam igual e sabidamente
falso no Brasil - desde 2014 o Nordeste e o Centro-Sul vem se afastando -, e
por isso a pagina mostra tambem quanto de swing cada estado aguenta antes de
virar, que e a leitura que sobrevive ao pressuposto.

Saida: projecao_uf.json (e estados.html, se mapa_modelo.html existir)

Uso:  python projetar_uf.py
"""

import csv
import io
import json
import sys
from datetime import date

from institutos import NOTAS, normalizar_instituto
# resultado nacional oficial do 2o turno de 2022, em votos validos
from resultados import RESULTADOS


def ler_uf():
    try:
        with io.open("resultados_2022_uf.csv", encoding="utf-8-sig", newline="") as f:
            linhas = list(csv.DictReader(f))
    except FileNotFoundError:
        print("resultados_2022_uf.csv nao existe - rode 'python coletar_uf.py' antes.")
        sys.exit(1)
    return [{
        "uf": r["uf"], "estado": r["estado"], "regiao": r["regiao"],
        "eleitorado": int(r["eleitorado"]),
        "lula_2022": float(r["lula"]),
        "adv_2022": float(r["bolsonaro"]),
    } for r in linhas]


def ler_pesquisas_uf():
    """
    Pesquisas presidenciais ESTADUAIS, preenchidas a mao em pesquisas_uf.csv.

    Nao ha fonte estruturada para elas: cada uma sai como materia ou PDF
    avulso, e as paginas estaduais da Wikipedia cobrem governador, nao
    presidente. Por isso este CSV e alimentado a mao, uma linha por pesquisa.
    So institutos com nota A-, A ou A+ entram, como no resto do projeto.
    """
    try:
        with io.open("pesquisas_uf.csv", encoding="utf-8-sig", newline="") as f:
            linhas = list(csv.DictReader(f))
    except FileNotFoundError:
        return []

    saida, ignorados = [], []
    for r in linhas:
        inst = normalizar_instituto(r["instituto"])
        if inst not in NOTAS:
            ignorados.append(r["instituto"])
            continue
        try:
            saida.append({
                "uf": r["uf"].strip().upper(),
                "instituto": inst,
                "nota": NOTAS[inst]["nota"],
                "data_fim": r["data_fim"],
                "amostra": int(r["amostra"]) if r.get("amostra") else None,
                "margem": float(r["margem"]) if r.get("margem") else None,
                "turno": int(r["turno"]),
                "lula": float(r["lula"]),
                "adversario": float(r["adversario"]),
                "fonte": r.get("fonte", ""),
            })
        except (ValueError, KeyError) as e:
            print(f"  (linha ignorada em pesquisas_uf.csv: {e})")
    if ignorados:
        print(f"  ({len(ignorados)} pesquisa(s) fora da lista nota A ignorada(s): "
              f"{', '.join(sorted(set(ignorados)))})")
    return saida


def comparar_com_2022(pesquisas, ufs, turno=2):
    """
    Para cada UF, pega a pesquisa mais recente do turno pedido, converte para
    votos validos e compara com o mesmo turno de 2022.
    """
    por_uf, quantas = {}, {}
    for p in pesquisas:
        if p["turno"] != turno:
            continue
        quantas[p["uf"]] = quantas.get(p["uf"], 0) + 1
        if p["uf"] not in por_uf or p["data_fim"] > por_uf[p["uf"]]["data_fim"]:
            por_uf[p["uf"]] = p

    base = {u["uf"]: u for u in ufs}
    saida = []
    for uf, p in por_uf.items():
        if uf not in base:
            print(f"  (UF desconhecida em pesquisas_uf.csv: {uf})")
            continue
        total = p["lula"] + p["adversario"]
        if total <= 0:
            continue
        # a conversao para validos e feita aqui, e nao confiando no rotulo da
        # materia: varias publicam '% de votos validos' em numeros que nao
        # somam 100, porque ainda carregam indecisos
        lula_val = 100 * p["lula"] / total
        adv_val = 100 - lula_val
        b = base[uf]
        saida.append({
            "uf": uf, "estado": b["estado"], "regiao": b["regiao"],
            "eleitorado": b["eleitorado"],
            "instituto": p["instituto"], "nota": p["nota"],
            "data": p["data_fim"], "amostra": p["amostra"],
            "bruto_lula": p["lula"], "bruto_adv": p["adversario"],
            "indefinidos": round(max(0.0, 100 - total), 1),
            "lula_2026": round(lula_val, 1),
            "adv_2026": round(adv_val, 1),
            "lula_2022": b["lula_2022"],
            "adv_2022": b["adv_2022"],
            "delta_lula": round(lula_val - b["lula_2022"], 1),
            "delta_adv": round(adv_val - b["adv_2022"], 1),
            "n_pesquisas": quantas[uf],
            "fonte": p["fonte"],
        })
    saida.sort(key=lambda x: -x["delta_adv"])
    return saida


def cenario_2t(agregado, esquerda="Lula", direita="Flávio"):
    """Pega o confronto Lula x Flavio do agregado de 2026, em votos validos."""
    for c in agregado.get("segundo_turno", []):
        if {c["a"], c["b"]} == {esquerda, direita}:
            va = c["va_valido"] if c["a"] == esquerda else c["vb_valido"]
            vb = c["vb_valido"] if c["a"] == esquerda else c["va_valido"]
            return {"esquerda": va, "direita": vb, "n": c["n"], "ultima": c["ultima"]}
    return None


def main():
    ufs = ler_uf()

    try:
        with io.open("agregado.json", encoding="utf-8") as f:
            ag = json.load(f)
    except FileNotFoundError:
        print("agregado.json nao existe - rode 'python agregar.py' antes.")
        sys.exit(1)

    atual = cenario_2t(ag)
    if not atual:
        print("Sem cenario Lula x Flavio no agregado - nada a projetar.")
        sys.exit(1)

    nac22 = RESULTADOS[2022]["turno2"]          # Lula 50.90 x Bolsonaro 49.10
    lula22, bols22 = nac22["Lula"], nac22["Bolsonaro"]
    swing = atual["esquerda"] - lula22          # deslocamento nacional em pp

    eleitorado_total = sum(u["eleitorado"] for u in ufs)
    for u in ufs:
        u["peso"] = round(100 * u["eleitorado"] / eleitorado_total, 2)
        u["margem_2022"] = round(u["lula_2022"] - u["adv_2022"], 2)
        # swing necessario para o estado virar: metade da margem, porque
        # cada ponto que um ganha e um ponto que o outro perde
        u["swing_para_virar"] = round(-u["margem_2022"] / 2, 2)
        u["lula_2022"] = round(u["lula_2022"], 2)
        u["adv_2022"] = round(u["adv_2022"], 2)

    ufs.sort(key=lambda u: -u["margem_2022"])

    pesquisas_uf = ler_pesquisas_uf()
    comparacoes = comparar_com_2022(pesquisas_uf, ufs, turno=2)

    dados = {
        "atualizado": date.today().isoformat(),
        "metodo": "swing uniforme",
        "nomes": {"esquerda": "Lula", "direita": "Flávio", "direita_2022": "Bolsonaro"},
        "nacional_2022": {"esquerda": lula22, "direita": bols22},
        "nacional_2026": {
            "esquerda": round(atual["esquerda"], 2),
            "direita": round(atual["direita"], 2),
            "n_pesquisas": atual["n"],
            "ultima": atual["ultima"],
        },
        "swing": round(swing, 2),
        "eleitorado_total": eleitorado_total,
        "estados": ufs,
        "comparacoes": comparacoes,
        "n_pesquisas_uf": len(pesquisas_uf),
    }

    with io.open("projecao_uf.json", "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=1)

    # ---------------- relatorio
    print(f"Swing uniforme - 2o turno, votos validos\n")
    print(f"  2022 nacional : Lula {lula22:.2f}%  x  Bolsonaro {bols22:.2f}%")
    print(f"  2026 agregado : Lula {atual['esquerda']:.2f}%  x  Flávio "
          f"{atual['direita']:.2f}%   ({atual['n']} pesquisas)")
    print(f"  swing         : {swing:+.2f} pp para Lula\n")

    virando = [u for u in ufs
               if (u["margem_2022"] > 0) != (u["margem_2022"] + 2 * swing > 0)]
    print(f"Estados que mudam de lado com este swing: "
          f"{', '.join(u['uf'] for u in virando) if virando else 'nenhum'}\n")

    print(f"  {'uf':<4}{'2022':>16}{'projetado':>18}{'vira com':>12}")
    for u in ufs:
        l26 = u["lula_2022"] + swing
        d26 = u["adv_2022"] - swing
        print(f"  {u['uf']:<4}{u['lula_2022']:>7.1f}x{u['adv_2022']:<7.1f}"
              f"{l26:>9.1f}x{d26:<8.1f}{u['swing_para_virar']:>+8.1f} pp")

    if comparacoes:
        print("\nPesquisas estaduais (institutos nota A), 2o turno em votos validos:")
        print(f"  {'uf':<4}{'2022':>10}{'agora':>10}{'Flavio vs Bolsonaro':>22}   fonte")
        for c in comparacoes:
            print(f"  {c['uf']:<4}{c['adv_2022']:>9.1f}%{c['adv_2026']:>9.1f}%"
                  f"{c['delta_adv']:>+21.1f} pp   {c['instituto']} "
                  f"{c['data'][8:10]}/{c['data'][5:7]}")
        cobertos = sum(c["eleitorado"] for c in comparacoes)
        print(f"\n  {len(comparacoes)} de 27 unidades, "
              f"{100 * cobertos / eleitorado_total:.1f}% do eleitorado")
    else:
        print("\nNenhuma pesquisa estadual na base (pesquisas_uf.csv).")

    print("\nprojecao_uf.json gravado.")
    gerar_pagina(dados)


def gerar_pagina(dados, modelo="mapa_modelo.html", saida="estados.html",
                 saida_publica="estados_publico.html"):
    try:
        with io.open(modelo, encoding="utf-8") as f:
            html = f.read()
    except FileNotFoundError:
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
