"""
Confere se a coleta e a agregacao produziram dados plausiveis.

Roda sem ninguem olhando, dentro do GitHub Actions: se a Wikipedia sair do ar,
mudar o formato das tabelas ou alguem errar uma digitacao, e este script que
impede o site de publicar numero errado. Sai com codigo 1 se algo nao bate.

Uso:  python verificar.py
"""

import csv
import io
import json
import sys
from datetime import date, timedelta

MIN_PESQUISAS_2T = 8
MIN_INSTITUTOS = 4
MAX_DIAS_SEM_PESQUISA = 30
DIAS_PARA_ESTRANHAR = 5
AMOSTRA_MIN_PLAUSIVEL = 300
AMOSTRA_MAX_PLAUSIVEL = 200_000
FAIXA_DUELO = (30.0, 70.0)   # num duelo, ninguem fica fora disso

problemas, avisos = [], []
erro = problemas.append
aviso = avisos.append


def ler_csv(caminho):
    with io.open(caminho, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


# ------------------------------------------------------------------ CSV

try:
    p2 = ler_csv("pesquisas_2t.csv")
except FileNotFoundError:
    erro("pesquisas_2t.csv nao existe - coletar.py nao rodou")
    p2 = []

duelo = [r for r in p2 if r.get("cenario", "").startswith("Lula e Fl")]
if p2 and len(duelo) < MIN_PESQUISAS_2T:
    erro(f"so {len(duelo)} pesquisas do duelo (minimo {MIN_PESQUISAS_2T})")

institutos = {r["instituto"] for r in duelo}
if duelo and len(institutos) < MIN_INSTITUTOS:
    erro(f"so {len(institutos)} institutos: {sorted(institutos)}")

hoje = date.today()
datas = []
for r in duelo:
    try:
        datas.append(date.fromisoformat(r["data_fim"]))
    except (ValueError, KeyError):
        erro(f"data invalida: {r.get('data_fim')!r} ({r.get('instituto')})")

    a = r.get("amostra")
    if a not in (None, ""):
        try:
            n = int(a)
            if not AMOSTRA_MIN_PLAUSIVEL <= n <= AMOSTRA_MAX_PLAUSIVEL:
                erro(f"amostra implausivel de {n} ({r['instituto']} {r['data_fim']}) - "
                     f"provavel linha deslocada na origem")
        except ValueError:
            erro(f"amostra nao numerica {a!r} ({r['instituto']} {r['data_fim']})")

    for k in ("Lula", "Flávio"):
        v = r.get(k)
        if v in (None, ""):
            continue
        try:
            x = float(v)
        except ValueError:
            erro(f"valor nao numerico {v!r} em {k} ({r['instituto']})")
            continue
        if not 0 <= x <= 100:
            erro(f"{k}={x} fora de 0-100 ({r['instituto']} {r['data_fim']})")

if datas:
    recente = max(datas)
    if recente > hoje + timedelta(days=1):
        erro(f"pesquisa com data no futuro: {recente.isoformat()}")
    atraso = (hoje - recente).days
    if atraso > MAX_DIAS_SEM_PESQUISA:
        erro(f"pesquisa mais recente e de {recente.isoformat()}, ha {atraso} dias")
    elif atraso > DIAS_PARA_ESTRANHAR:
        aviso(f"nenhuma pesquisa nova ha {atraso} dias - confira se a coleta "
              f"ainda enxerga a fonte")

# ------------------------------------------------------------------ agregado

try:
    with io.open("agregado.json", encoding="utf-8") as f:
        ag = json.load(f)
except FileNotFoundError:
    erro("agregado.json nao existe - agregar.py nao rodou")
    ag = None

if ag:
    a = ag.get("agregado", {})
    if not a:
        erro("agregado.json sem numeros")
    else:
        for lado in ("a", "b"):
            v = a.get(lado)
            if v is None or not FAIXA_DUELO[0] <= v <= FAIXA_DUELO[1]:
                erro(f"agregado {lado}={v} fora da faixa {FAIXA_DUELO}")
        soma = (a.get("a") or 0) + (a.get("b") or 0)
        if abs(soma - 100) > 0.2:
            erro(f"o duelo soma {soma:.2f}, nao 100 - a conversao para validos quebrou")
        if (a.get("n") or 0) < 2:
            erro("agregado apoiado em menos de 2 pesquisas")
    if not ag.get("serie"):
        erro("serie temporal vazia")
    if not ag.get("acuracia_1t"):
        aviso("sem acuracia do 1o turno - os pesos cairam para a mediana")

# ------------------------------------------------------------------ pagina

for arquivo, minimo in (("painel_publico.html", 30_000),):
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

for a_ in avisos:
    print(f"  aviso: {a_}")

if problemas:
    print(f"\nFALHOU - {len(problemas)} problema(s):")
    for p_ in problemas:
        print(f"  - {p_}")
    sys.exit(1)

print(f"OK - {len(duelo)} pesquisas do duelo, {len(institutos)} institutos"
      + (f", mais recente {max(datas).isoformat()}" if datas else "")
      + (f", {len(avisos)} aviso(s)" if avisos else ""))
