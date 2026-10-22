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

# linhas que copiam o resultado oficial do 1o turno (coletar.py e agregar.py
# ja descartam; se aparecer aqui, a coleta rodou com codigo antigo)
import correcoes
for r in duelo:
    if correcoes.copia_do_resultado_1t(r):
        aviso(f"{r['instituto']} {r['data_fim']} repete o resultado oficial do 1o turno "
              f"({r['Lula']} x {r['Flávio']}) - ignorada pelo agregador")

# mesma casa, mesma amostra e campo sobreposto: provavel rodada duplicada na
# origem (foi assim que a linha falsa da Verita de 19/10 apareceu)
por_inst = {}
for r in duelo:
    por_inst.setdefault(r["instituto"], []).append(r)
for inst, rs in por_inst.items():
    rs = sorted(rs, key=lambda r: r["data_fim"])
    for ant, nov in zip(rs, rs[1:]):
        if (ant.get("amostra") and ant.get("amostra") == nov.get("amostra")
                and nov.get("data_inicio") and nov["data_inicio"] < ant["data_fim"]
                and (ant.get("Lula"), ant.get("Flávio")) != (nov.get("Lula"), nov.get("Flávio"))):
            aviso(f"{inst}: rodadas {ant['data_inicio']}~{ant['data_fim']} e "
                  f"{nov['data_inicio']}~{nov['data_fim']} tem a mesma amostra "
                  f"({nov['amostra']}) e campo sobreposto - confira no TSE")

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

def conferir_agregado(arquivo, falha):
    """Checa um agregado. A aba PollsterGraph usa 'aviso' como falha: ela
    nunca pode impedir a publicacao da aba principal."""
    try:
        with io.open(arquivo, encoding="utf-8") as f:
            ag = json.load(f)
    except FileNotFoundError:
        falha(f"{arquivo} nao existe - agregar.py nao rodou")
        return
    a = ag.get("agregado", {})
    if not a:
        falha(f"{arquivo} sem numeros")
    else:
        for lado in ("a", "b"):
            v = a.get(lado)
            if v is None or not FAIXA_DUELO[0] <= v <= FAIXA_DUELO[1]:
                falha(f"agregado {lado}={v} fora da faixa {FAIXA_DUELO}")
        soma = (a.get("a") or 0) + (a.get("b") or 0)
        if abs(soma - 100) > 0.2:
            falha(f"o duelo soma {soma:.2f}, nao 100 - a conversao para validos quebrou")
        if (a.get("n") or 0) < 2:
            falha("agregado apoiado em menos de 2 pesquisas")
        for k in ("prob_a", "prob_b"):
            v = a.get(k)
            if v is None or not 0 <= v <= 1:
                falha(f"probabilidade {k}={v} fora de 0-1")
        if (a.get("margem_total") or 0) < (a.get("margem") or 0):
            falha("margem total menor que a margem da media - erro sistematico sumiu")
    pj = ag.get("projecao")
    if pj:
        if abs((pj.get("a") or 0) + (pj.get("b") or 0) - 100) > 0.2:
            falha("projecao nao soma 100")
        if abs(pj.get("inclinacao_dia") or 0) > 1.0:
            falha(f"tendencia de {pj['inclinacao_dia']} pp/dia - implausivel, confira os dados")
    c = ag.get("corrigido")
    if c and abs((c.get("a") or 0) + (c.get("b") or 0) - 100) > 0.2:
        falha("cenario corrigido nao soma 100")
    if not ag.get("serie"):
        falha("serie temporal vazia")
    if not ag.get("acuracia_1t"):
        aviso(f"{arquivo}: sem acuracia do 1o turno - os pesos cairam para a mediana")


conferir_agregado("agregado.json", erro)
conferir_agregado("agregado_pg.json", aviso)

# ------------------------------------------------------------------ pagina

for arquivo, minimo, falha in (("painel_publico.html", 30_000, erro),
                               ("painel_pg_publico.html", 30_000, aviso)):
    try:
        with io.open(arquivo, encoding="utf-8") as f:
            html = f.read()
    except FileNotFoundError:
        falha(f"{arquivo} nao foi gerado")
        continue
    if len(html) < minimo:
        falha(f"{arquivo} tem so {len(html)} bytes - parece truncado")
    if "/*__DADOS__*/" in html:
        falha(f"{arquivo} ficou com o marcador de dados sem preencher")

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
