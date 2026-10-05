"""Gera a página estática (HTML único com os dados embutidos): python -m pagina.build [--data data] [--saida docs]."""
import argparse
import base64
import json
from pathlib import Path

import numpy as np
import pandas as pd

from ingest import estado_texto
from ingest.geo import destino_efetivo

UFS = ["AC", "AL", "AM", "AP", "BA", "CE", "DF", "ES", "GO", "MA", "MG", "MS", "MT", "PA", "PB", "PE", "PI", "PR",
       "RJ", "RN", "RO", "RR", "RS", "SC", "SE", "SP", "TO"]
PRODUTOS = ["Diesel B", "Gasolina C", "Etanol Hidratado", "Óleo Comb."]
MERCADOS = {"POSTO DE COMBUSTÍVEIS - BANDEIRA BRANCA": "Posto bandeira branca",
            "POSTO DE COMBUSTÍVEIS - BANDEIRADO": "Posto bandeirado", "CONSUMIDOR FINAL": "Consumidor final",
            "TRR": "TRR", "TRRNI": "TRRNI"}
AQUI = Path(__file__).parent


def montar(ag, estado):
    """Agregado (com origem/destino) + state.json -> (meta dict, bytes das colunas)."""
    d = destino_efetivo(ag.astype({c: "object" for c in ("ano_mes", "agente", "produto", "mercado",
                                                         "uf_destino", "uf_origem", "reg_origem", "reg_destino") if c in ag}))
    d = d[d.uf_destino.isin(UFS) & d["produto"].isin(PRODUTOS) & d.mercado.isin(MERCADOS)]
    d = d.groupby(["ano_mes", "agente", "produto", "uf_destino", "mercado"], as_index=False).volume_m3.sum()
    d = d[d.volume_m3.round() != 0]
    meses = sorted(d.ano_mes.unique())
    agentes = d.groupby("agente").volume_m3.sum().sort_values(ascending=False, kind="stable").index.tolist()
    if len(meses) > 65535 or len(agentes) > 65535:
        raise ValueError("índices acima de uint16")
    cols = {
        "v": d.volume_m3.round().astype("int64").clip(-2**31, 2**31 - 1).astype("<i4").to_numpy(),
        "m": d.ano_mes.map({m: i for i, m in enumerate(meses)}).astype("<u2").to_numpy(),
        "a": d.agente.map({a: i for i, a in enumerate(agentes)}).astype("<u2").to_numpy(),
        "p": d["produto"].map({p: i for i, p in enumerate(PRODUTOS)}).astype("u1").to_numpy(),
        "u": d.uf_destino.map({u: i for i, u in enumerate(UFS)}).astype("u1").to_numpy(),
        "k": d.mercado.map({m: i for i, m in enumerate(MERCADOS)}).astype("u1").to_numpy(),
    }
    binario = b"".join(cols[c].tobytes() for c in "vmapuk")
    meta = {"meses": meses, "produtos": PRODUTOS, "ufs": UFS, "agentes": agentes,
            "mercados": list(MERCADOS.values()), "n": int(len(d)),
            "atualizado": (estado.get("atualizado_em") or "")[:10],
            "parciais": estado.get("parciais", []),
            "avisos": [t for _, t in estado_texto.avisos(estado)]}
    return meta, binario


def montar_html(template, meta, binario):
    m = json.dumps(meta, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    return (template.replace("/*META*/", m, 1)
            .replace("/*BIN*/", base64.b64encode(binario).decode("ascii"), 1))


def construir(data, saida):
    from ingest import store
    estado = store.ler_estado(data)
    if not estado.get("meses"):
        raise SystemExit("data/ vazio: rode a carga antes de gerar a página")
    meta, binario = montar(pd.read_parquet(Path(data) / "agregado.parquet"), estado)
    html = montar_html((AQUI / "template.html").read_text(encoding="utf-8"), meta, binario)
    saida = Path(saida)
    saida.mkdir(parents=True, exist_ok=True)
    (saida / "index.html").write_text(html, encoding="utf-8")
    (saida / ".nojekyll").write_text("", encoding="utf-8")
    print(f"página: {saida / 'index.html'} ({len(html) / 1e6:.1f} MB, {meta['n']} linhas, "
          f"{meta['meses'][0]} a {meta['meses'][-1]})")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data", default="data", type=Path)
    ap.add_argument("--saida", default="docs", type=Path)
    a = ap.parse_args(argv)
    construir(a.data, a.saida)


if __name__ == "__main__":
    main()
