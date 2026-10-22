"""
Pesos de instituto pelo ranking do PollsterGraph (pollstergraph.com/ranking/institutes).

E a alternativa ao peso pelo erro do 1o turno de 2026 (institutos.py): aqui o
peso vem do historico de varias eleicoes anteriores, medido por terceiros.

  peso = indice de desempenho do instituto / indice do melhor colocado

O "indice de desempenho" e o numero que o PollsterGraph usa para ordenar o
ranking (media entre desempenho objetivo e comparativo, de 0 a 100). Instituto
sem nota no ranking (classificacao N, ou ausente) recebe o peso do PIOR
classificado da lista principal: sem historico, sem premio.

O ranking e baixado da API publica do site a cada execucao e guardado em
ranking_pollstergraph.json; se a API falhar, vale a ultima copia salva.

Uso:  python pollstergraph.py      (baixa e mostra a tabela)
"""

import io
import json
import sys
import urllib.request

API = "https://api.pollstergraph.com/pollstergraph/ranking/institutes"
PAGINA = "https://pollstergraph.com/ranking/institutes"
ARQUIVO = "ranking_pollstergraph.json"

# nome no PollsterGraph -> nome usado aqui (institutos.normalizar_instituto)
# So entra o que e inequivocamente o mesmo instituto. "Vox Populi" tem nota B,
# mas nao da para afirmar que e o "Vox" das tabelas de 2026, entao fica fora.
NOMES = {
    "Datafolha": "Datafolha",
    "AtlasIntel": "AtlasIntel",
    "MDA": "MDA",
    "Paraná Pesquisas": "Paraná Pesquisas",
    "Real Time Big Data": "Real Time Big Data",
    "Futura": "Futura",
    "Ipespe": "Ipespe",
    "Quaest": "Quaest",
    "Veritá": "Veritá",
    "Ranking Pesquisa": "Ranking",
    "DataPoder360": "PoderData/Aya",
    "Gerp": "Gerp",
    "Ideia Big Data": "Meio/Ideia",
    "Nexus": "Nexus/BTG",
    "Ipec (antigo Ibope)": "Ipsos-Ipec",
    "American Analytics": "American Analytics",
}


def baixar():
    """Baixa o ranking completo. Devolve a lista ou None se a API falhar."""
    url = API + "?sortBy=ranking&pageSize=1000&main_pollster=false"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 agregador-eleicoes2026"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            dados = json.loads(r.read().decode("utf-8"))
    except Exception as e:  # rede, JSON, HTTP
        print(f"(aviso) PollsterGraph indisponivel: {e}")
        return None
    if not isinstance(dados, list) or len(dados) < 20:
        print("(aviso) resposta do PollsterGraph fora do formato esperado")
        return None
    return dados


def atualizar():
    """Baixa e grava; se falhar, mantem a copia anterior."""
    dados = baixar()
    if dados is not None:
        with io.open(ARQUIVO, "w", encoding="utf-8") as f:
            json.dump(dados, f, ensure_ascii=False, indent=1)
        return dados
    try:
        with io.open(ARQUIVO, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"(erro) sem {ARQUIVO} e sem acesso a API")
        sys.exit(1)


def montar(dados):
    """
    Devolve (ranking, peso_sem_nota): ranking[nosso_nome] = {...} so para os
    institutos com nota; peso_sem_nota = peso do pior da lista principal.
    """
    com_nota = [d for d in dados if d.get("grade") is not None]
    melhor = max(d["grade"] for d in com_nota)
    principais = [d["grade"] for d in com_nota if d.get("main_pollster")]
    piso = min(principais) if principais else min(d["grade"] for d in com_nota)

    ranking = {}
    for d in dados:
        nosso = NOMES.get(d["name"])
        if not nosso:
            continue
        item = {
            "nome_pg": d["name"],
            "posicao": d.get("ranking"),
            "classe": d.get("classification"),
            "indice": d.get("grade"),
            "erro_medio": d.get("mean_error"),
            "pesquisas": d.get("n_surveys"),
        }
        item["peso"] = round(d["grade"] / melhor, 4) if d.get("grade") is not None else None
        ranking[nosso] = item
    return ranking, round(piso / melhor, 4), melhor


_cache = None


def carregar():
    global _cache
    if _cache is None:
        _cache = montar(atualizar())
    return _cache


def peso_instituto(inst):
    ranking, sem_nota, _ = carregar()
    r = ranking.get(inst)
    return r["peso"] if r and r["peso"] is not None else sem_nota


def tem_nota(inst):
    r = carregar()[0].get(inst)
    return bool(r and r["peso"] is not None)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    ranking, sem_nota, melhor = carregar()
    print(f"Ranking PollsterGraph · melhor índice {melhor} · sem nota pesa {sem_nota:.2f}\n")
    for inst, r in sorted(ranking.items(), key=lambda x: -(x[1]["indice"] or 0)):
        print(f"  {inst:<22}{str(r['posicao'] or '—'):>5}  {r['classe']:<3}"
              f"{(r['indice'] or 0):6.1f}   peso {(r['peso'] or sem_nota):.2f}")
