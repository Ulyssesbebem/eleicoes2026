"""
Monta o diretorio site/ que vai para o GitHub Pages.

  site/index.html   - Agregador Nota A (pesquisas de 2026)
  site/urnas.html   - Pesquisa contra Urna (afericao 2018/2022)
  site/dados/       - CSVs e JSONs, para quem quiser conferir a conta

A barra de navegacao entre as duas paginas e injetada aqui, e nao nos modelos,
porque os links relativos so fazem sentido no site - nos Artifacts cada pagina
vive numa URL propria.

Uso:  python montar_site.py
"""

import io
import os
import shutil

SAIDA = "site"

PAGINAS = [
    # (arquivo gerado, nome no site, rotulo da aba, titulo curto)
    ("painel_publico.html", "index.html", "Agregador 2026", "index.html"),
    ("aferidor_publico.html", "urnas.html", "Pesquisa × Urna", "urnas.html"),
    ("estados_publico.html", "estados.html", "Estado por Estado", "estados.html"),
]

DADOS = [
    "pesquisas_1t.csv", "pesquisas_2t.csv", "agregado.json",
    "pesquisas_2018.csv", "pesquisas_2022.csv",
    "pesquisas_2018_2t.csv", "pesquisas_2022_2t.csv", "afericao.json",
    "resultados_2022_uf.csv", "projecao_uf.json", "pesquisas_uf.csv",
]

NAV_CSS = """
<style>
.nav-site{
  display:flex; gap:2px; align-items:center; flex-wrap:wrap;
  max-width:1080px; margin:0 auto; padding:14px 20px 0;
  font-family:"IBM Plex Sans",system-ui,sans-serif; font-size:13px;
}
.nav-site a{
  text-decoration:none; color:var(--tinta-2,#52514e); padding:6px 13px;
  border:1px solid var(--borda,rgba(11,11,11,.10)); border-radius:7px;
  background:var(--superficie,#fcfcfb);
}
.nav-site a+a{margin-left:6px}
.nav-site a[aria-current="page"]{
  background:var(--tinta,#0b0b0b); color:var(--plano,#f9f9f7); font-weight:500;
  border-color:var(--tinta,#0b0b0b);
}
.nav-site a:hover:not([aria-current]){background:var(--realce,#f0efec)}
.nav-site .dados{margin-left:auto; color:var(--tinta-3,#898781); border-style:dashed}
</style>
"""


def barra(atual):
    itens = "".join(
        f'<a href="{destino}"{" aria-current=\"page\"" if destino == atual else ""}>{rotulo}</a>'
        for _orig, destino, rotulo, _t in PAGINAS
    )
    return (NAV_CSS + '<nav class="nav-site">' + itens +
            '<a class="dados" href="dados/">dados brutos</a></nav>')


def injetar(html, atual):
    """Coloca a barra logo depois da abertura do <body>."""
    marca = "<body>"
    i = html.find(marca)
    if i == -1:
        return barra(atual) + html
    i += len(marca)
    return html[:i] + "\n" + barra(atual) + html[i:]


def indice_dados(arquivos):
    linhas = "".join(
        f'<li><a href="{a}">{a}</a> '
        f'<span>{os.path.getsize(os.path.join(SAIDA, "dados", a)):,} bytes</span></li>'
        .replace(",", ".")
        for a in arquivos
    )
    return f"""<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Dados brutos</title>
<style>
 body{{font-family:"IBM Plex Sans",system-ui,sans-serif;max-width:640px;margin:0 auto;
   padding:48px 20px;background:#f9f9f7;color:#0b0b0b;line-height:1.6}}
 h1{{font-family:Georgia,serif;font-weight:600;font-size:30px;margin:0 0 6px}}
 p{{color:#52514e;font-size:14px}}
 ul{{list-style:none;padding:0;margin:24px 0 0}}
 li{{display:flex;justify-content:space-between;gap:16px;padding:10px 0;
   border-bottom:1px solid #e1e0d9;font-size:14px}}
 li span{{color:#898781;font-family:ui-monospace,monospace;font-size:12px}}
 a{{color:#2a78d6}}
 @media (prefers-color-scheme:dark){{
   body{{background:#0d0d0d;color:#fff}} p{{color:#c3c2b7}}
   li{{border-color:#2c2c2a}} a{{color:#3987e5}}}}
</style></head><body>
<h1>Dados brutos</h1>
<p>As bases que alimentam as duas páginas, como saíram da coleta.
<a href="../">voltar</a></p>
<ul>{linhas}</ul>
</body></html>"""


def main():
    if os.path.isdir(SAIDA):
        shutil.rmtree(SAIDA)
    os.makedirs(os.path.join(SAIDA, "dados"))

    for origem, destino, _rotulo, _t in PAGINAS:
        if not os.path.exists(origem):
            print(f"(aviso) {origem} nao existe - pulando")
            continue
        html = io.open(origem, encoding="utf-8").read()
        io.open(os.path.join(SAIDA, destino), "w", encoding="utf-8").write(
            injetar(html, destino))
        print(f"  {origem} -> {SAIDA}/{destino}")

    copiados = []
    for d in DADOS:
        if os.path.exists(d):
            shutil.copy2(d, os.path.join(SAIDA, "dados", d))
            copiados.append(d)
    io.open(os.path.join(SAIDA, "dados", "index.html"), "w",
            encoding="utf-8").write(indice_dados(copiados))
    print(f"  {len(copiados)} arquivos de dados copiados")

    # impede o Jekyll do GitHub Pages de mexer no que ja esta pronto
    io.open(os.path.join(SAIDA, ".nojekyll"), "w").write("")
    print(f"\nsite/ pronto.")


if __name__ == "__main__":
    main()
