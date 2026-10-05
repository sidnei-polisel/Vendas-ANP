"""Conferência manual: python -m ingest.validar --mes 2025-06 --produto "Diesel B" --uf SP [--base destino|origem]."""
import argparse
from pathlib import Path

import pandas as pd

from .geo import destino_efetivo


def consultar(ag, mes, produto, uf, base="destino"):
    """Volume (m³) do mês/produto/UF e a quebra por mercado destinatário."""
    col = "uf_destino" if base == "destino" else "uf_origem"
    ag = destino_efetivo(ag) if base == "destino" else ag
    d = ag[(ag.ano_mes.astype(str) == mes) & (ag.produto.astype(str) == produto) & (ag[col].astype(str) == uf)]
    por_mercado = d.groupby("mercado", observed=True).volume_m3.sum().sort_values(ascending=False)
    return float(d.volume_m3.sum()), por_mercado


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--mes", required=True)
    ap.add_argument("--produto", required=True)
    ap.add_argument("--uf", required=True)
    ap.add_argument("--base", default="destino", choices=["destino", "origem"])
    ap.add_argument("--vendas", type=Path, help="CSV vendas-combustiveis-m3 da ANP, para comparar")
    ap.add_argument("--data", default="data", type=Path)
    a = ap.parse_args(argv)
    total, mk = consultar(pd.read_parquet(a.data / "agregado.parquet"), a.mes, a.produto, a.uf.upper(), a.base)
    f = lambda x: f"{x:,.3f}".replace(",", "X").replace(".", ",").replace("X", ".")  # noqa: E731
    print(f"{a.mes} · {a.produto} · {a.uf.upper()} ({a.base}): {f(total)} m³ = {f(total / 1e3)} mil m³")
    print(f"  = {total / 1e6:.3f} milhões de m³".replace(".", ","))
    if a.vendas:
        from . import conferencia
        r = conferencia.ler(a.vendas)
        v = r[(r.ano_mes == a.mes) & (r.produto == a.produto) & (r.uf == a.uf.upper())].vendas_m3.sum()
        print(f"  base de vendas da ANP: {f(v)} m³ (SIMP/vendas = {total / v - 1:+.2%})" if v else "  base de vendas: sem registro")
    for m, v in mk.items():
        print(f"  {m}: {f(v / 1e3)} mil m³ ({v / total:.1%})" if total else f"  {m}: 0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
