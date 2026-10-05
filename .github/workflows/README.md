# Vendas de combustíveis no Brasil (ANP, dados abertos)

Fonte única: gov.br/anp (movimentação de derivados, base SIMP). Atualização em Python puro, sem LLM.
Resultado: uma página HTML interativa (GitHub Pages) que se atualiza sozinha.

## Como funciona

- `ingest/`: carga incremental (ETag/Last-Modified, hash por mês, Parquet por ano-mês, `state.json`).
- `pagina/build.py`: lê `data/` e gera `docs/index.html` (HTML único, dados embutidos, Chart.js).
- `.github/workflows/atualizar.yml`: dias 5 e 28 (e manual) atualiza `data/`, faz commit só se mudou e republica a página.
  Se a atualização falhar, a base não muda e a página mostra "dados desatualizados desde dd/mm/aaaa".

## Decisões validadas contra a ANP

- Quantidade em **mil m³** (×1.000 → m³). Total mensal vs. base de vendas da ANP: diferença ≤ 0,4%.
- Estado/região = **destino**; linhas com destino `NI` entram na UF de origem (critério do Painel Dinâmico da ANP).
  Conferido em jun/2025 contra o painel: diesel B SP 1.167,56 e GO 313,36; etanol hidratado GO 127,43 e MG 176,75 (mil m³).
- GLP fora; histórico 2007-2016 fora (`config.yaml`).

## Publicar (só navegador)

1. GitHub: novo repositório público e vazio; suba o conteúdo desta pasta (incluindo `.github`).
2. Settings → Actions → General → Workflow permissions → **Read and write permissions**.
3. Settings → Pages → Source: **GitHub Actions**.
4. Actions → "Atualizar dados ANP e publicar página" → Run workflow (marque "forcar" na primeira vez).
5. O link da página aparece no job "publicar" e em Settings → Pages.

## Local (opcional)

```bash
pip install -r requirements-dev.txt
python -m pytest -q
python -m ingest.run --zip liquidos.zip      # carga inicial a partir de um zip baixado
python -m pagina.build                       # gera docs/index.html
python -m ingest.validar --mes 2025-06 --produto "Diesel B" --uf SP --vendas vendas-combustiveis-m3-1990-2025.csv
```
