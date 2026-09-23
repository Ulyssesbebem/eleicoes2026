"""
Confere se a coleta e a agregacao produziram dados plausiveis.

Roda sem ninguem olhando, dentro do GitHub Actions: se a Wikipedia sair do ar,
mudar o formato das tabelas ou alguem vandalizar uma pagina, e este script que
impede o site de publicar numero errado. Sai com codigo 1 se algo nao bate.

Uso:  python verificar.py
"""

import csv
import io
import json
import sys
from datetime import date, timedelta

MIN_PESQUISAS_1T = 20        # a base historica ja tem 41; menos que isso e suspeito
MIN_INSTITUTOS = 3
MAX_DIAS_SEM_PESQUISA = 60   # se a mais recente for antiga demais, algo quebrou
DIAS_PARA_ESTRANHAR = 5      # na reta final sai pesquisa quase todo dia
FAIXA_LIDER = (20.0, 70.0)   # o primeiro colocado tem de cair numa faixa sensata

problemas = []
avisos = []


def erro(msg):
    problemas.append(msg)


def aviso(msg):
    avisos.append(msg)


def ler_csv(caminho):
    with io.open(caminho, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


# ------------------------------------------------------------------ 1o turno

try:
    p1 = ler_csv("pesquisas_1t.csv")
except FileNotFoundError:
    erro("pesquisas_1t.csv nao existe - coletar.py nao rodou")
    p1 = []

if p1:
    if len(p1) < MIN_PESQUISAS_1T:
        erro(f"so {len(p1)} pesquisas de 1o turno (minimo {MIN_PESQUISAS_1T})")

    institutos = {r["instituto"] for r in p1}
    if len(institutos) < MIN_INSTITUTOS:
        erro(f"so {len(institutos)} institutos: {sorted(institutos)}")

    datas = []
    for r in p1:
        try:
            datas.append(date.fromisoformat(r["data_fim"]))
        except (ValueError, KeyError):
            erro(f"data invalida: {r.get('data_fim')!r} ({r.get('instituto')})")
    if datas:
        hoje = date.today()
        recente = max(datas)
        if recente > hoje + timedelta(days=1):
            erro(f"pesquisa com data no futuro: {recente.isoformat()}")
        atraso = (hoje - recente).days
        if atraso > MAX_DIAS_SEM_PESQUISA:
            erro(f"pesquisa mais recente e de {recente.isoformat()}, "
                 f"ha {atraso} dias")
        elif atraso > DIAS_PARA_ESTRANHAR:
            # nao e erro: pode nao ter saido pesquisa mesmo. Mas perto da
            # eleicao costuma significar que a coleta parou de enxergar a
            # fonte, e vale aparecer no log antes de virar uma semana parada.
            aviso(f"nenhuma pesquisa nova ha {atraso} dias "
                  f"(a mais recente e de {recente.isoformat()}) - "
                  f"confira se a coleta ainda enxerga a fonte")

    # percentuais dentro de 0-100 e soma plausivel
    for r in p1:
        soma = 0.0
        for k, v in r.items():
            if k in ("instituto", "data_inicio", "data_fim", "amostra", "margem"):
                continue
            if v in (None, ""):
                continue
            try:
                x = float(v)
            except ValueError:
                erro(f"valor nao numerico {v!r} em {k} ({r['instituto']} {r['data_fim']})")
                continue
            if not 0 <= x <= 100:
                erro(f"{k}={x} fora de 0-100 ({r['instituto']} {r['data_fim']})")
            soma += x
        if soma and not 85 <= soma <= 115:
            aviso(f"soma {soma:.1f}% em {r['instituto']} {r['data_fim']}")

# ------------------------------------------------------------------ agregado

try:
    with io.open("agregado.json", encoding="utf-8") as f:
        ag = json.load(f)
except FileNotFoundError:
    erro("agregado.json nao existe - agregar.py nao rodou")
    ag = None

if ag:
    if not ag.get("agregado"):
        erro("agregado.json sem candidatos")
    else:
        lider = max(ag["agregado"].items(), key=lambda x: x[1]["media"])
        media = lider[1]["media"]
        if not FAIXA_LIDER[0] <= media <= FAIXA_LIDER[1]:
            erro(f"lider {lider[0]} com {media}% - fora da faixa {FAIXA_LIDER}")
        if lider[1]["n"] < 2:
            erro(f"lider {lider[0]} apoiado em {lider[1]['n']} pesquisa(s)")

    if not ag.get("pesquisas_janela"):
        erro("nenhuma pesquisa dentro da janela")
    if not ag.get("serie"):
        erro("serie temporal vazia")

# ------------------------------------------------------------------ paginas

for arquivo, minimo in (("painel_publico.html", 100_000),
                        ("aferidor_publico.html", 20_000),
                        ("estados_publico.html", 15_000)):
    try:
        with io.open(arquivo, encoding="utf-8") as f:
            html = f.read()
    except FileNotFoundError:
        erro(f"{arquivo} nao foi gerado")
        continue
    if len(html) < minimo:
        erro(f"{arquivo} tem so {len(html)} bytes - parece truncado")
    if "/*__DADOS__*/" in html:
        erro(f"{arquivo} ficou com o marcador de dados sem preencher")

# ------------------------------------------------------------------ saida

for a in avisos:
    print(f"  aviso: {a}")

if problemas:
    print(f"\nFALHOU - {len(problemas)} problema(s):")
    for p in problemas:
        print(f"  - {p}")
    sys.exit(1)

print(f"OK - {len(p1)} pesquisas, {len({r['instituto'] for r in p1})} institutos, "
      f"mais recente {max(r['data_fim'] for r in p1)}"
      + (f", {len(avisos)} aviso(s)" if avisos else ""))
