"""
Coleta o resultado do 2o turno de 2022 por unidade federativa.

Fonte: 'Resultados da eleicao presidencial no Brasil em 2022' na Wikipedia,
secao 'Por unidade federativa', que reproduz a totalizacao do TSE. As
porcentagens da tabela ja sao de VOTOS VALIDOS (Lula + Bolsonaro = 100).

Saida: resultados_2022_uf.csv

Uso:  python coletar_uf.py
"""

import csv
import re
import sys

from coletar import baixar, dividir_tabelas, secoes

PAGINA = "Resultados da eleição presidencial no Brasil em 2022"

UFS = {
    "AC": ("Acre", "Norte"), "AL": ("Alagoas", "Nordeste"),
    "AP": ("Amapá", "Norte"), "AM": ("Amazonas", "Norte"),
    "BA": ("Bahia", "Nordeste"), "CE": ("Ceará", "Nordeste"),
    "DF": ("Distrito Federal", "Centro-Oeste"), "ES": ("Espírito Santo", "Sudeste"),
    "GO": ("Goiás", "Centro-Oeste"), "MA": ("Maranhão", "Nordeste"),
    "MT": ("Mato Grosso", "Centro-Oeste"), "MS": ("Mato Grosso do Sul", "Centro-Oeste"),
    "MG": ("Minas Gerais", "Sudeste"), "PA": ("Pará", "Norte"),
    "PB": ("Paraíba", "Nordeste"), "PR": ("Paraná", "Sul"),
    "PE": ("Pernambuco", "Nordeste"), "PI": ("Piauí", "Nordeste"),
    "RJ": ("Rio de Janeiro", "Sudeste"), "RN": ("Rio Grande do Norte", "Nordeste"),
    "RS": ("Rio Grande do Sul", "Sul"), "RO": ("Rondônia", "Norte"),
    "RR": ("Roraima", "Norte"), "SC": ("Santa Catarina", "Sul"),
    "SP": ("São Paulo", "Sudeste"), "SE": ("Sergipe", "Nordeste"),
    "TO": ("Tocantins", "Norte"),
}

UF_RE = re.compile(r"\{\{\s*BR-([A-Z]{2})\s*\}\}")
FMTN_RE = re.compile(r"\{\{\s*Fmtn\s*\|\s*([\d\s.]+?)\s*\}\}", re.I)
SMALL_RE = re.compile(r"\{\{\s*Small\s*\|\s*([\d,.]+)\s*%\s*\}\}", re.I)


def num(txt):
    return int(re.sub(r"[^\d]", "", txt) or 0)


def pct(txt):
    return float(txt.replace(".", "").replace(",", "."))


def parse_uf(tabela):
    """
    Le a tabela do 2o turno por UF.

    Cada linha tem, nesta ordem:
      {{BR-XX}} | eleitorado | abstencao | %abst | Lula | %Lula |
      Bolsonaro | %Bols | brancos | %br | nulos | %nl
    As porcentagens de Lula e Bolsonaro ja somam 100 (votos validos).
    """
    saida = []
    for bloco in re.split(r"\n\|-", tabela):
        m = UF_RE.search(bloco)
        if not m:
            continue
        uf = m.group(1)
        if uf not in UFS:
            continue
        fmtn = [num(x) for x in FMTN_RE.findall(bloco)]
        small = [pct(x) for x in SMALL_RE.findall(bloco)]
        if len(fmtn) < 4 or len(small) < 3:
            continue

        nome, regiao = UFS[uf]
        saida.append({
            "uf": uf,
            "estado": nome,
            "regiao": regiao,
            "eleitorado": fmtn[0],
            "votos_lula": fmtn[2],
            "votos_bolsonaro": fmtn[3],
            "lula": small[1],
            "bolsonaro": small[2],
        })
    return saida


def main():
    print("Baixando resultados de 2022 por UF...")
    wiki = baixar(PAGINA)

    # so a secao 'Por unidade federativa' -> 'Segundo turno'
    dentro_uf = False
    tabela_2t = None
    for titulo, conteudo in secoes(wiki):
        t = titulo.strip().lower()
        if t == "por unidade federativa":
            dentro_uf = True
            continue
        if dentro_uf and t == "segundo turno":
            tabelas = dividir_tabelas(conteudo)
            if tabelas:
                tabela_2t = tabelas[0]
            break
        if dentro_uf and t.startswith("gráficos"):
            break

    if not tabela_2t:
        print("Nao achei a tabela de 2o turno por UF.")
        sys.exit(1)

    dados = parse_uf(tabela_2t)

    # ---- conferencias: a tabela so serve se fechar
    problemas = []
    if len(dados) != 27:
        problemas.append(f"{len(dados)} unidades federativas em vez de 27")
    faltando = set(UFS) - {d["uf"] for d in dados}
    if faltando:
        problemas.append(f"faltando: {sorted(faltando)}")
    for d in dados:
        soma = d["lula"] + d["bolsonaro"]
        if abs(soma - 100) > 0.15:
            problemas.append(f"{d['uf']}: Lula+Bolsonaro = {soma:.2f}, nao 100")
    if problemas:
        print("FALHOU:")
        for p in problemas:
            print("  -", p)
        sys.exit(1)

    with open("resultados_2022_uf.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(dados[0]))
        w.writeheader()
        for d in sorted(dados, key=lambda x: -x["lula"]):
            w.writerow(d)

    total_l = sum(d["votos_lula"] for d in dados)
    total_b = sum(d["votos_bolsonaro"] for d in dados)
    nac = 100 * total_l / (total_l + total_b)
    print(f"resultados_2022_uf.csv -> 27 unidades, todas fechando em 100%")
    print(f"Nacional recomposto dos estados: Lula {nac:.2f}%  "
          f"Bolsonaro {100 - nac:.2f}%  (oficial: 50,90 x 49,10)")

    print("\nExtremos:")
    ordenado = sorted(dados, key=lambda x: -x["lula"])
    for d in ordenado[:3]:
        print(f"  {d['uf']}  Lula {d['lula']:.1f}%")
    print("  ...")
    for d in ordenado[-3:]:
        print(f"  {d['uf']}  Lula {d['lula']:.1f}%")


if __name__ == "__main__":
    main()
