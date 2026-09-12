"""
Coleta as pesquisas presidenciais de 2026 a partir do wikitexto da Wikipedia
e grava em pesquisas_1t.csv / pesquisas_2t.csv.

Por padrao so institutos com nota A-, A ou A+ entram na base (institutos.py).
Use --todos para gravar todos os institutos.

Quando uma pesquisa traz mais de um cenario (linhas agrupadas por rowspan na
Wikipedia), usamos o PRIMEIRO cenario, que e o principal/estimulado completo.

Uso:  python coletar.py [--todos]
"""

import csv
import re
import sys
import urllib.parse
import urllib.request
from datetime import date

from institutos import NOTAS, normalizar_instituto

BASE = "https://pt.wikipedia.org/w/index.php?title={}&action=raw"

PAGINA_PRINCIPAL = "Pesquisas de opinião para a eleição presidencial no Brasil em 2026"
PAGINA_JAN_AGO = (
    "Pesquisas de opinião para a eleição presidencial no Brasil em 2026"
    "/Primeiro Turno/2026/Janeiro a Agosto"
)

MESES = {
    "jan": 1, "fev": 2, "mar": 3, "abr": 4, "mai": 5, "jun": 6,
    "jul": 7, "ago": 8, "set": 9, "out": 10, "nov": 11, "dez": 12,
}


def baixar(titulo):
    url = BASE.format(urllib.parse.quote(titulo.replace(" ", "_")))
    req = urllib.request.Request(url, headers={"User-Agent": "agregador-eleicoes/1.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read().decode("utf-8")


# ---------------------------------------------------------------- limpeza

def tirar_refs(t):
    """Remove <ref>...</ref>, <ref/> e comentarios HTML."""
    t = re.sub(r"<!--.*?-->", "", t, flags=re.S)
    t = re.sub(r"<ref[^>/]*?/>", "", t)
    t = re.sub(r"<ref.*?</ref>", "", t, flags=re.S)
    t = re.sub(r"<ref[^>]*>.*?$", "", t, flags=re.M)
    return t


def tirar_templates(t):
    """Remove {{...}} equilibrando chaves (templates de cor, small, N/A...)."""
    saida, i, prof = [], 0, 0
    while i < len(t):
        if t.startswith("{{", i):
            prof += 1
            i += 2
        elif t.startswith("}}", i) and prof:
            prof -= 1
            i += 2
        else:
            if not prof:
                saida.append(t[i])
            i += 1
    return "".join(saida)


def texto_limpo(celula):
    """Converte o conteudo de uma celula wiki em texto simples."""
    t = tirar_refs(celula)
    t = tirar_templates(t)
    t = re.sub(r"\[\[[^\]|]*\|([^\]]*)\]\]", r"\1", t)   # [[alvo|rotulo]] -> rotulo
    t = re.sub(r"\[\[([^\]]*)\]\]", r"\1", t)            # [[alvo]] -> alvo
    t = re.sub(r"<br\s*/?>", " ", t)
    t = re.sub(r"<[^>]+>", "", t)
    t = t.replace("'''", "").replace("''", "")
    return re.sub(r"\s+", " ", t).strip()


NUM_RE = re.compile(r"^\s*(\d+(?:[.,]\d+)?)\s*%?\s*$")


def valor_celula(celula):
    """Pega a porcentagem de uma celula. Devolve None se nao houver numero."""
    t = texto_limpo(celula)
    if not t or t in {"-", "–", "—", "?"}:
        return None
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*%?", t)
    if not m:
        return None
    return float(m.group(1).replace(",", "."))


def eh_so_numero(celula):
    """True se a celula contem apenas um numero/porcentagem (linha de cenario extra)."""
    return bool(NUM_RE.match(texto_limpo(celula)))


# ---------------------------------------------------------------- datas

def parse_data(txt, ano=2026):
    """
    '8 Set - 11 Set', '4 a 9 de setembro', '27-31 Ago' -> (inicio, fim).
    Se o campo cruza a virada do ano (ex. 'Dez - Jan'), ajusta o ano do inicio.
    """
    t = texto_limpo(txt).lower().replace("–", "-").replace("—", "-")
    if not t:
        return None, None

    # pares (dia, mes) explicitos
    pares = []
    for m in re.finditer(r"(\d{1,2})\s*(?:de\s+)?([a-zç]{3,})", t):
        mes = MESES.get(m.group(2)[:3])
        if mes:
            pares.append((int(m.group(1)), mes))

    if not pares:
        return None, None

    # dias sem mes proprio num intervalo "27-31 ago": herdam o mes do par seguinte
    for m in re.finditer(r"(\d{1,2})\s*-\s*(\d{1,2})\s*(?:de\s+)?([a-zç]{3,})", t):
        mes = MESES.get(m.group(3)[:3])
        if mes:
            pares.append((int(m.group(1)), mes))

    datas = []
    for dia, mes in pares:
        try:
            datas.append(date(ano, mes, dia))
        except ValueError:
            pass
    if not datas:
        return None, None

    datas.sort()
    ini, fim = datas[0], datas[-1]
    # campo de virada de ano: 28 dez - 3 jan -> inicio no ano anterior
    if (fim - ini).days > 60:
        ini = ini.replace(year=ano - 1)
        datas = sorted([ini, fim])
        ini, fim = datas[0], datas[-1]
    return ini, fim


# ---------------------------------------------------------------- tabelas

def dividir_tabelas(wiki):
    """Devolve o conteudo de cada wikitable do texto."""
    tabelas, i = [], 0
    while True:
        ini = wiki.find('{| class="wikitable', i)
        if ini == -1:
            return tabelas
        prof, j = 0, ini
        while j < len(wiki):
            if wiki.startswith("{|", j):
                prof += 1
                j += 2
            elif wiki.startswith("|}", j):
                prof -= 1
                j += 2
                if prof == 0:
                    break
            else:
                j += 1
        tabelas.append(wiki[ini:j])
        i = j


def dividir_celulas(linha):
    """
    Separa as celulas de uma linha de wikitable, respeitando [[ ]] e {{ }}.
    Aceita '|' no inicio de linha e '||' na mesma linha.
    """
    celulas, atual = [], []
    i, prof_t, prof_l = 0, 0, 0
    inicio_linha = True
    while i < len(linha):
        c = linha[i]
        if linha.startswith("{{", i):
            prof_t += 1
            atual.append(linha[i:i + 2]); i += 2; inicio_linha = False; continue
        if linha.startswith("}}", i):
            prof_t = max(0, prof_t - 1)
            atual.append(linha[i:i + 2]); i += 2; continue
        if linha.startswith("[[", i):
            prof_l += 1
            atual.append(linha[i:i + 2]); i += 2; inicio_linha = False; continue
        if linha.startswith("]]", i):
            prof_l = max(0, prof_l - 1)
            atual.append(linha[i:i + 2]); i += 2; continue

        if prof_t == 0 and prof_l == 0:
            if linha.startswith("||", i) or (c in "|!" and inicio_linha):
                if not inicio_linha or atual:
                    celulas.append("".join(atual))
                atual = []
                i += 2 if linha.startswith("||", i) else 1
                inicio_linha = False
                continue
        if c == "\n":
            inicio_linha = True
            atual.append(c)
            i += 1
            continue
        inicio_linha = False
        atual.append(c)
        i += 1
    celulas.append("".join(atual))
    return celulas


def sem_atributos(celula):
    """Tira 'style=... |' / 'rowspan="2" |' do inicio da celula."""
    if "|" in celula:
        cabeca, resto = celula.split("|", 1)
        if re.search(r"(style|rowspan|colspan|class|align|bgcolor)\s*=", cabeca, re.I):
            return resto
    return celula


def colspan_de(celula):
    m = re.search(r'colspan\s*=\s*"?(\d+)', celula, re.I)
    return int(m.group(1)) if m else 1


CAND_RE = re.compile(r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]")
NAO_CANDIDATO = re.compile(
    r"^(Partido|Avante|Democracia|Unidade|Movimento|Democrata|Missão|Novo|PT$|PL$)", re.I
)
# colunas de metadado que nunca sao candidato (podem conter wikilinks internos,
# ex.: 'Margem de erro ([[Porcentagem|pontos percentuais]])')
COL_META = re.compile(
    r"Contratante|Pesquisa|Data\(s\)|Tamanho|Amostra|Margem\s+de\s+erro|Porcentagem|"
    r"Indecis|Absent|Abstenç|Vantagem|Outros|Branco|Nulo|Lideran|Diferen|Situaç",
    re.I,
)


def ler_cabecalho(linhas_cab):
    """Extrai, na ordem, os rotulos das colunas de candidato do cabecalho."""
    nomes = []
    for linha in linhas_cab:
        for celula in dividir_celulas(linha):
            if re.search(r"(Ficheiro|File|Arquivo|Imagem):", celula):
                continue
            if COL_META.search(texto_limpo(celula)) or COL_META.search(celula):
                continue
            m = CAND_RE.search(celula)
            if not m:
                continue
            rotulo = re.sub(r"\s+", " ", (m.group(2) or m.group(1)).strip())
            rotulo = re.sub(r"<[^>]+>", " ", rotulo).strip()
            if rotulo and not NAO_CANDIDATO.match(rotulo) and rotulo not in nomes:
                nomes.append(rotulo)
    return nomes


META = ["_instituto", "_data", "_amostra", "_margem"]


def parse_tabela(tabela, ano=2026):
    """
    Devolve (lista_de_pesquisas, colunas_de_candidato).
    Cada pesquisa e um dict com instituto/datas/amostra/margem + % por candidato.
    Linhas de cenario extra (agrupadas por rowspan) e linhas de evento sao ignoradas.
    """
    blocos = re.split(r"\n\|-+[^\n]*", tabela)
    if not blocos:
        return [], []

    # --- cabecalho: o bloco 0 e os blocos seguintes formados so por linhas '!'
    linhas_cab = [blocos[0]]
    corpo_inicio = 1
    for k in range(1, len(blocos)):
        uteis = [l for l in blocos[k].split("\n") if l.strip()]
        if uteis and all(l.lstrip().startswith("!") for l in uteis):
            linhas_cab.append(blocos[k])
            corpo_inicio = k + 1
        else:
            corpo_inicio = k
            break

    cab_txt = "\n".join(linhas_cab)
    candidatos = ler_cabecalho(linhas_cab)
    if not candidatos:
        return [], []

    colunas = list(META) + candidatos
    if re.search(r"\|\s*Outros", cab_txt, re.I):
        colunas.append("Outros")
    if re.search(r"Indecis|Absent|Abstenç|Branco|Nulo|não sabe", cab_txt, re.I):
        colunas.append("Indefinidos")

    pesquisas = []
    for bloco in blocos[corpo_inicio:]:
        if not bloco.strip():
            continue
        celulas = dividir_celulas(bloco)
        # o primeiro elemento e o texto antes do primeiro '|' (normalmente vazio);
        # celulas vazias no meio NAO podem ser descartadas, senao as colunas deslocam
        while celulas and not celulas[0].strip():
            celulas.pop(0)
        while celulas and not celulas[-1].strip():
            celulas.pop()
        if not celulas:
            continue
        # linha de evento / nota de rodape: uma celula cobrindo varias colunas
        if any(colspan_de(c) >= 5 for c in celulas):
            continue
        # linha de cenario extra: comeca direto com uma porcentagem
        if eh_so_numero(sem_atributos(celulas[0])):
            continue

        linha = {}
        for idx, col in enumerate(colunas):
            linha[col] = sem_atributos(celulas[idx]) if idx < len(celulas) else ""

        inst = normalizar_instituto(texto_limpo(linha["_instituto"]))
        if not inst or eh_so_numero(linha["_instituto"]):
            continue
        ini, fim = parse_data(linha["_data"], ano)
        if fim is None:
            continue

        amostra_txt = re.sub(r"[ . ]", "", texto_limpo(linha["_amostra"]))
        m = re.search(r"\d+", amostra_txt)

        reg = {
            "instituto": inst,
            "data_inicio": ini.isoformat() if ini else "",
            "data_fim": fim.isoformat(),
            "amostra": int(m.group()) if m else None,
            "margem": valor_celula(linha["_margem"]),
        }
        tem_candidato = False
        for col in colunas[len(META):]:
            v = valor_celula(linha[col])
            reg[col] = v
            if v is not None and col not in ("Outros", "Indefinidos"):
                tem_candidato = True
        if not tem_candidato:
            continue
        pesquisas.append(reg)

    return pesquisas, colunas[len(META):]


# ---------------------------------------------------------------- secoes

CAB_SECAO = re.compile(r"^(={2,6})\s*(.+?)\s*\1\s*$", re.M)
ANO_RE = re.compile(r"\b(20\d{2})\b")
PULAR_SECAO = re.compile(r"agrega|resumo|refer|ligaç|ver também", re.I)
# titulos que nomeiam um confronto de 2o turno: 'Lula e Flávio Bolsonaro', 'Hipóteses com Lula'
CENARIO_RE = re.compile(r"^(.+\s+e\s+.+|Hipóteses\s+com\s+.+)$", re.I)


def secoes(wiki):
    """Divide o wikitexto em pares (titulo, conteudo)."""
    marcas = [(m.start(), m.end(), m.group(2)) for m in CAB_SECAO.finditer(wiki)]
    if not marcas:
        return [("", wiki)]
    saida = [("", wiki[:marcas[0][0]])]
    for i, (_ini, fim, titulo) in enumerate(marcas):
        prox = marcas[i + 1][0] if i + 1 < len(marcas) else len(wiki)
        saida.append((titulo, wiki[fim:prox]))
    return saida


def eh_tabela_de_pesquisa(tabela):
    if not re.search(r"Tamanho|amostra", tabela, re.I):
        return False
    if re.search(r"\|\s*Agregador", tabela):       # tabela de agregadores
        return False
    return True


def pesquisas_do_wikitexto(wiki, ano_padrao=2026, marcar_cenario=False):
    """
    Varre as secoes de um wikitexto e devolve as pesquisas de todas as tabelas,
    rastreando o ano pelo titulo das secoes ('=== 2025 ===').
    """
    pesquisas, colunas = [], []
    ano = ano_padrao
    cenario = ""
    for titulo, conteudo in secoes(wiki):
        anos = ANO_RE.findall(titulo)
        if anos:
            ano = int(anos[-1])
        elif marcar_cenario and CENARIO_RE.match(titulo.strip()):
            cenario = titulo.strip()
        if PULAR_SECAO.search(titulo):
            continue
        for tabela in dividir_tabelas(conteudo):
            if not eh_tabela_de_pesquisa(tabela):
                continue
            p, cols = parse_tabela(tabela, ano)
            if marcar_cenario:
                for reg in p:
                    reg["cenario"] = cenario
            pesquisas.extend(p)
            for c in cols:
                if c not in colunas:
                    colunas.append(c)
    return pesquisas, colunas


def cortar_em_segundo_turno(wiki):
    """Separa a pagina principal em (bloco_1o_turno, bloco_2o_turno)."""
    m = re.search(r"^==\s*Segundo turno\s*==\s*$", wiki, re.M)
    if not m:
        return wiki, ""
    depois = wiki[m.end():]
    m2 = re.search(r"^==\s*(?!=)[^=\n]+?\s*==\s*$", depois, re.M)
    if m2:
        depois = depois[:m2.start()]
    return wiki[:m.start()], depois


# ---------------------------------------------------------------- saida

def gravar(caminho, registros, colunas, chaves_base):
    cols = chaves_base + [c for c in colunas if c not in chaves_base]
    with open(caminho, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore", restval="")
        w.writeheader()
        for r in sorted(registros, key=lambda x: (x["data_fim"], x["instituto"]), reverse=True):
            w.writerow(r)


def main():
    somente_boas = "--todos" not in sys.argv

    print("Baixando pagina principal...")
    principal = baixar(PAGINA_PRINCIPAL)
    bloco_1t, bloco_2t = cortar_em_segundo_turno(principal)

    print("Baixando historico de janeiro a agosto...")
    jan_ago = baixar(PAGINA_JAN_AGO)

    p1, cols1 = pesquisas_do_wikitexto(bloco_1t)
    p1b, cols1b = pesquisas_do_wikitexto(jan_ago)
    p1 += p1b
    for c in cols1b:
        if c not in cols1:
            cols1.append(c)

    p2, cols2 = pesquisas_do_wikitexto(bloco_2t, marcar_cenario=True)

    print(f"  1o turno: {len(p1)} pesquisas lidas")
    print(f"  2o turno: {len(p2)} pesquisas lidas")

    if somente_boas:
        p1 = [p for p in p1 if p["instituto"] in NOTAS]
        p2 = [p for p in p2 if p["instituto"] in NOTAS]

    base1 = ["instituto", "data_inicio", "data_fim", "amostra", "margem"]
    gravar("pesquisas_1t.csv", p1, cols1, base1)
    gravar("pesquisas_2t.csv", p2, cols2, ["cenario"] + base1)

    print(f"\npesquisas_1t.csv -> {len(p1)} pesquisas")
    print(f"pesquisas_2t.csv -> {len(p2)} pesquisas")

    print("\n1o turno, por instituto:")
    cont = {}
    for p in p1:
        cont.setdefault(p["instituto"], []).append(p["data_fim"])
    for inst, datas in sorted(cont.items(), key=lambda x: -len(x[1])):
        nota = NOTAS.get(inst, {}).get("nota", "?")
        print(f"  {inst:22s} nota {nota:2s}  {len(datas):3d} pesquisas  "
              f"ultima {max(datas)}")


if __name__ == "__main__":
    main()
