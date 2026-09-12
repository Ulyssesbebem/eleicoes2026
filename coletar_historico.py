"""
Coleta as pesquisas finais das eleicoes presidenciais de 2018 e 2022 para
medir o vies pesquisa->urna. Projeto separado: nao altera nada do agregador
de 2026 (coletar.py / agregar.py), so reaproveita as funcoes de parsing.

As duas eleicoes usam layouts diferentes na Wikipedia:

  2022  mesma estrutura de 2026 - meta na ordem
        [instituto, data, amostra, margem] e o candidato vem do cabecalho.

  2018  meta na ordem [data, instituto, amostra, margem] e o candidato NAO
        esta no cabecalho (que traz siglas de partido) e sim dentro da
        propria celula, anotado como '36%<small>(Bolsonaro)</small>'.

Saida: pesquisas_2018.csv e pesquisas_2022.csv

Uso:  python coletar_historico.py
"""

import csv
import re

from coletar import (
    baixar, cortar_em_segundo_turno, dividir_celulas, dividir_tabelas,
    eh_so_numero, parse_data, pesquisas_do_wikitexto, sem_atributos,
    texto_limpo, valor_celula, colspan_de, secoes, PULAR_SECAO,
)

PAGINAS = {
    2018: "Pesquisas de opinião para a eleição presidencial no Brasil em 2018",
    2022: "Pesquisas de opinião para a eleição presidencial no Brasil em 2022",
}

# 1o turno de cada eleicao
DIA_ELEICAO = {2018: "2018-10-07", 2022: "2022-10-02", 2026: "2026-10-04"}


# ------------------------------------------------------------------ 2018

# '36%<small>(Bolsonaro)</small>' -> valor 36.0, candidato 'Bolsonaro'
NOME_NA_CELULA = re.compile(r"\(([^)]{2,40})\)\s*$")


def celula_2018(celula):
    """Devolve (valor, nome_do_candidato) de uma celula da tabela de 2018."""
    t = texto_limpo(celula)
    if not t or t in {"-", "–", "—"}:
        return None, None
    valor = valor_celula(celula)
    m = NOME_NA_CELULA.search(t)
    nome = m.group(1).strip() if m else None
    if nome and not re.match(r"^[A-ZÁÉÍÓÚÂÊÔÃÕÇ]", nome):
        nome = None
    return valor, nome


def parse_tabela_2018(tabela, ano=2018):
    """
    Le uma tabela de 2018. A ordem das colunas de metadado e
    [periodo, contratante/instituto, entrevistados, margem] e os valores
    vem depois, cada um trazendo o nome do candidato dentro da celula.
    """
    blocos = re.split(r"\n\|-+[^\n]*", tabela)
    pesquisas = []

    for bloco in blocos[1:]:
        if not bloco.strip():
            continue
        celulas = dividir_celulas(bloco)
        while celulas and not celulas[0].strip():
            celulas.pop(0)
        while celulas and not celulas[-1].strip():
            celulas.pop()
        if len(celulas) < 6:
            continue
        if any(colspan_de(c) >= 5 for c in celulas):
            continue
        # linha de cor do cabecalho: so celulas com style e nada dentro
        if all(not texto_limpo(sem_atributos(c)) for c in celulas):
            continue

        periodo = sem_atributos(celulas[0])
        # o proprio texto do periodo traz o ano ('8-11 de fevereiro de 2017'),
        # e a pagina de 2018 lista tambem pesquisas de 2017 e 2016
        m_ano = re.search(r"\b(20\d{2})\b", texto_limpo(periodo))
        ini, fim = parse_data(periodo, int(m_ano.group(1)) if m_ano else ano)
        if fim is None:
            continue

        inst = texto_limpo(sem_atributos(celulas[1]))
        # a celula traz um link externo [url Rotulo] seguido do numero de
        # registro: tira a URL, depois o registro, e so entao os colchetes
        inst = re.sub(r"\[?https?://\S+\s*", "", inst)
        inst = re.sub(r"\s*BR[-–]?\d+/\d+\s*", "", inst)
        inst = inst.replace("[", "").replace("]", "").strip(" ,;")
        if not inst or eh_so_numero(celulas[1]):
            continue

        amostra_txt = re.sub(r"[ .]", "", texto_limpo(sem_atributos(celulas[2])))
        m = re.search(r"\d+", amostra_txt)

        reg = {
            "instituto": inst,
            "data_inicio": ini.isoformat() if ini else "",
            "data_fim": fim.isoformat(),
            "amostra": int(m.group()) if m else None,
            "margem": valor_celula(celulas[3]),
        }
        achou = False
        for cel in celulas[4:]:
            v, nome = celula_2018(sem_atributos(cel))
            if v is None or not nome:
                continue
            reg[nome] = v
            achou = True
        if achou:
            pesquisas.append(reg)
    return pesquisas


def coletar_2018():
    wiki = baixar(PAGINAS[2018])
    bloco_1t, _ = cortar_em_segundo_turno(wiki)
    saida = []
    for titulo, conteudo in secoes(bloco_1t):
        if PULAR_SECAO.search(titulo) or "boca" in titulo.lower():
            continue
        for tabela in dividir_tabelas(conteudo):
            if not re.search(r"entrevistados|amostra", tabela, re.I):
                continue
            saida.extend(parse_tabela_2018(tabela))
    return saida


# ------------------------------------------------------------------ 2022

def coletar_2022():
    """2022 usa a mesma estrutura de 2026."""
    wiki = baixar(PAGINAS[2022])
    bloco_1t, _ = cortar_em_segundo_turno(wiki)
    pesquisas, _cols = pesquisas_do_wikitexto(bloco_1t, ano_padrao=2022)
    saida = []
    for p in pesquisas:
        reg = {k: p[k] for k in ("instituto", "data_inicio", "data_fim", "amostra", "margem")}
        reg.update({c: v for c, v in p["valores"].items() if v is not None}
                   if "valores" in p else
                   {c: v for c, v in p.items()
                    if c not in ("instituto", "data_inicio", "data_fim", "amostra", "margem")
                    and v is not None})
        saida.append(reg)
    return saida


# ------------------------------------------------------------------ 2o turno

def tabelas_livres(wiki):
    """
    Como dividir_tabelas(), mas aceita '{| class=wikitable' sem aspas -
    a forma usada nas tabelas de 2o turno de 2022.
    """
    tabelas, i = [], 0
    while True:
        m = re.search(r"\{\|", wiki[i:])
        if not m:
            return tabelas
        ini = i + m.start()
        prof, j = 0, ini
        while j < len(wiki):
            if wiki.startswith("{|", j):
                prof += 1; j += 2
            elif wiki.startswith("|}", j):
                prof -= 1; j += 2
                if prof == 0:
                    break
            else:
                j += 1
        tabelas.append(wiki[ini:j])
        i = j


def args_template(texto, nome):
    """
    Devolve a lista de argumentos de {{<nome>|a|b|c}}, respeitando templates
    aninhados ({{Partido X/meta/cor}} conta como UM argumento).
    """
    m = re.search(r"\{\{\s*" + re.escape(nome), texto, re.I)
    if not m:
        return None
    i = m.end()
    prof, args, atual = 1, [], []
    while i < len(texto) and prof:
        if texto.startswith("{{", i):
            prof += 1; atual.append("{{"); i += 2; continue
        if texto.startswith("}}", i):
            prof -= 1
            if prof == 0:
                break
            atual.append("}}"); i += 2; continue
        if texto[i] == "|" and prof == 1:
            args.append("".join(atual)); atual = []; i += 1; continue
        atual.append(texto[i]); i += 1
    args.append("".join(atual))
    return args[1:] if args and not args[0].strip() else args


def parse_2t_2022(tabela):
    """
    2022 usa templates: o cabecalho e {{Pesquisa eleitoral/cabeçalho|pagina|
    rotulo|partido|sigla|...}} e cada linha traz {{Pesquisa eleitoral|cor|cor|
    v1|v2|indefinidos}}.
    """
    cab = args_template(tabela, "Pesquisa eleitoral/cabeçalho")
    if not cab:
        return []
    # os argumentos vem em grupos de 4: pagina, rotulo, partido, sigla
    cands = [cab[i + 1].strip() for i in range(0, len(cab) - 1, 4) if cab[i + 1].strip()]
    if len(cands) < 2:
        return []

    pesquisas = []
    for bloco in re.split(r"\n\|-+[^\n]*", tabela)[1:]:
        if "Pesquisa eleitoral" not in bloco:
            continue
        vals = args_template(bloco, "Pesquisa eleitoral")
        if not vals or len(vals) < 2 + len(cands):
            continue
        numeros = vals[2:]          # os dois primeiros sao cores

        antes = bloco.split("{{Pesquisa eleitoral", 1)[0]
        celulas = [c for c in re.split(r"\|\||\n\|", antes) if c.strip()]
        if len(celulas) < 3:
            continue
        inst = texto_limpo(sem_atributos(celulas[0]))
        ini, fim = parse_data(sem_atributos(celulas[1]), 2022)
        if fim is None or not inst:
            continue
        amostra_txt = re.sub(r"[ .]", "", texto_limpo(sem_atributos(celulas[2])))
        m = re.search(r"\d+", amostra_txt)

        reg = {
            "instituto": inst,
            "data_inicio": ini.isoformat() if ini else "",
            "data_fim": fim.isoformat(),
            "amostra": int(m.group()) if m else None,
            "margem": None,
        }
        for c, v in zip(cands, numeros):
            val = valor_celula(v)
            if val is not None:
                reg[c] = val
        if len(numeros) > len(cands):
            ind = valor_celula(numeros[len(cands)])
            if ind is not None:
                reg["Indefinidos"] = ind
        if any(c in reg for c in cands):
            pesquisas.append(reg)
    return pesquisas


def parse_2t_2018(tabela):
    """
    2018: celulas normais, meta na ordem [periodo, instituto, amostra, margem]
    e os candidatos vindos do cabecalho.
    """
    blocos = re.split(r"\n\|-+[^\n]*", tabela)
    cands = []
    for cel in dividir_celulas(blocos[0]):
        if re.search(r"(Ficheiro|File|Imagem):", cel):
            continue
        t = texto_limpo(cel)
        if re.search(r"Período|Contratante|entrevistados|Margem|Abst|decid|registro|Referência", t, re.I):
            continue
        m = re.search(r"\[\[[^\]|]+\|([^\]]+)\]\]", cel)
        if m:
            nome = m.group(1).strip()
            if nome and nome not in cands and not re.match(r"^(PT|PSL|PL)$", nome):
                cands.append(nome)
    if len(cands) < 2:
        return []

    pesquisas = []
    for bloco in blocos[1:]:
        celulas = dividir_celulas(bloco)
        while celulas and not celulas[0].strip():
            celulas.pop(0)
        if len(celulas) < 4 + len(cands):
            continue
        if all(not texto_limpo(sem_atributos(c)) for c in celulas):
            continue

        periodo = sem_atributos(celulas[0])
        m_ano = re.search(r"\b(20\d{2})\b", texto_limpo(periodo))
        ini, fim = parse_data(periodo, int(m_ano.group(1)) if m_ano else 2018)
        if fim is None:
            continue
        inst = texto_limpo(sem_atributos(celulas[1]))
        inst = re.sub(r"\[?https?://\S+\s*", "", inst)
        inst = re.sub(r"\s*BR[-–‐]?\s?\d+/\d+\s*", "", inst)
        inst = inst.replace("[", "").replace("]", "").strip(" ,;")
        if not inst or eh_so_numero(celulas[1]):
            continue
        amostra_txt = re.sub(r"[ .]", "", texto_limpo(sem_atributos(celulas[2])))
        m = re.search(r"\d+", amostra_txt)

        reg = {
            "instituto": inst,
            "data_inicio": ini.isoformat() if ini else "",
            "data_fim": fim.isoformat(),
            "amostra": int(m.group()) if m else None,
            "margem": valor_celula(celulas[3]),
        }
        for i, c in enumerate(cands):
            v = valor_celula(sem_atributos(celulas[4 + i]))
            if v is not None:
                reg[c] = v
        idx = 4 + len(cands)
        if idx < len(celulas):
            ind = valor_celula(sem_atributos(celulas[idx]))
            if ind is not None:
                reg["Indefinidos"] = ind
        if any(c in reg for c in cands):
            pesquisas.append(reg)
    return pesquisas


def coletar_2t(ano):
    """
    Pesquisas de 2o turno posteriores ao 1o turno - as anteriores sao
    cenarios hipoteticos e nao servem para aferir a urna.
    """
    from datetime import date as _date
    wiki = baixar(PAGINAS[ano])
    _, bloco = cortar_em_segundo_turno(wiki)
    if not bloco:
        return []

    parser = parse_2t_2022 if ano == 2022 else parse_2t_2018
    saida = []
    for titulo, conteudo in secoes(bloco):
        t = titulo.lower()
        if "boca" in t or "hipótese" in t or "hipotese" in t:
            continue
        # so o confronto que realmente foi as urnas
        if ano == 2022 and titulo.strip() and "x" in t and "bolsonaro" not in t:
            continue
        for tabela in tabelas_livres(conteudo):
            if re.search(r"\|\s*Agregador", tabela):
                continue
            saida.extend(parser(tabela))

    # a janela valida vai do dia seguinte ao 1o turno ate o dia do 2o turno:
    # antes disso sao cenarios hipoteticos, depois sao pesquisas pos-eleicao
    from resultados import RESULTADOS
    corte = _date.fromisoformat(DIA_ELEICAO[ano])
    corte_fim = _date.fromisoformat(RESULTADOS[ano]["dia_2t"])
    vistos, unicas = set(), []
    for r in saida:
        d = _date.fromisoformat(r["data_fim"])
        if d <= corte or d >= corte_fim:   # exclui o dia do pleito (boca de urna)
            continue
        chave = (r["instituto"], r["data_fim"])
        if chave in vistos:
            continue
        vistos.add(chave)
        unicas.append(r)
    return unicas


# ------------------------------------------------------------------ saida

def gravar(caminho, registros):
    if not registros:
        print(f"(nada para gravar em {caminho})")
        return
    base = ["instituto", "data_inicio", "data_fim", "amostra", "margem"]
    extras = []
    for r in registros:
        for k in r:
            if k not in base and k not in extras:
                extras.append(k)
    with open(caminho, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=base + extras, extrasaction="ignore", restval="")
        w.writeheader()
        for r in sorted(registros, key=lambda x: x["data_fim"], reverse=True):
            w.writerow(r)
    print(f"{caminho} -> {len(registros)} pesquisas, "
          f"{len(extras)} colunas de candidato")


def main():
    print("Baixando 2018...")
    p18 = coletar_2018()
    gravar("pesquisas_2018.csv", p18)

    print("\nBaixando 2022...")
    p22 = coletar_2022()
    gravar("pesquisas_2022.csv", p22)

    print("\n2o turno:")
    for ano in (2018, 2022):
        p2t = coletar_2t(ano)
        gravar(f"pesquisas_{ano}_2t.csv", p2t)
        for r in sorted(p2t, key=lambda x: x["data_fim"], reverse=True)[:4]:
            vals = {k: v for k, v in r.items()
                    if k not in ("instituto", "data_inicio", "data_fim", "amostra", "margem")
                    and v not in (None, "")}
            print(f"   {r['data_fim']}  {r['instituto'][:30]:<30} " +
                  "  ".join(f"{k} {v}" for k, v in vals.items()))

    for ano, lista in ((2018, p18), (2022, p22)):
        if not lista:
            continue
        print(f"\n{ano} - ultimas pesquisas antes da eleicao ({DIA_ELEICAO[ano]}):")
        for r in sorted(lista, key=lambda x: x["data_fim"], reverse=True)[:6]:
            vals = {k: v for k, v in r.items()
                    if k not in ("instituto", "data_inicio", "data_fim", "amostra", "margem")
                    and v not in (None, "")}
            topo = sorted(vals.items(), key=lambda x: -float(x[1]))[:3]
            print(f"  {r['data_fim']}  {r['instituto'][:34]:<34} " +
                  "  ".join(f"{k} {v}" for k, v in topo))


if __name__ == "__main__":
    main()
