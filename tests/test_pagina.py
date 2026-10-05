import json

import numpy as np
import pandas as pd

from pagina import build


def _ag():
    linhas = [
        # ano_mes, agente, produto, reg_origem, uf_origem, reg_destino, uf_destino, mercado, volume_m3
        ("2025-01", "A", "Diesel B", "SE", "SP", "SE", "SP", "TRR", 1000.4),
        ("2025-01", "A", "Diesel B", "SE", "SP", "NI", "NI", "CONSUMIDOR FINAL", 200.0),   # NI -> SP
        ("2025-02", "B", "Gasolina C", "NE", "BA", "NE", "BA", "POSTO DE COMBUSTÍVEIS - BANDEIRADO", 500.0),
        ("2025-02", "B", "GLP", "NE", "BA", "NE", "BA", "TRR", 9.0),                        # produto fora
    ]
    return pd.DataFrame(linhas, columns=["ano_mes", "agente", "produto", "reg_origem", "uf_origem",
                                         "reg_destino", "uf_destino", "mercado", "volume_m3"])


def _decodificar(meta, b):
    n = meta["n"]
    v = np.frombuffer(b, "<i4", n, 0)
    m = np.frombuffer(b, "<u2", n, 4 * n)
    a = np.frombuffer(b, "<u2", n, 6 * n)
    p, u, k = (np.frombuffer(b, "u1", n, o * n) for o in (8, 9, 10))
    return pd.DataFrame({"v": v, "mes": [meta["meses"][i] for i in m], "ag": [meta["agentes"][i] for i in a],
                         "prod": [meta["produtos"][i] for i in p], "uf": [meta["ufs"][i] for i in u],
                         "merc": [meta["mercados"][i] for i in k]})


def test_montar_ni_vira_origem_e_layout_binario():
    est = {"atualizado_em": "2026-10-03T09:00:00-03:00", "parciais": ["2025-02"], "ultima_falha": None}
    meta, b = build.montar(_ag(), est)
    assert meta["n"] == 3 and len(b) == 11 * 3 and meta["atualizado"] == "2026-10-03"
    d = _decodificar(meta, b)
    assert d.v.sum() == 1000 + 200 + 500          # GLP fora; 1000,4 arredonda
    assert set(d[d.mes == "2025-01"].uf) == {"SP"}  # NI -> UF de origem
    assert meta["mercados"][2] == "Consumidor final" and meta["agentes"][0] == "A"
    assert meta["parciais"] == ["2025-02"] and any("2025-02" in t for t in meta["avisos"])


def test_aviso_de_falha_vai_para_a_pagina():
    est = {"atualizado_em": "2026-09-05T06:00:00-03:00", "parciais": [],
           "ultima_falha": {"em": "2026-09-28T06:00:00-03:00", "motivo": "rede"}}
    meta, _ = build.montar(_ag(), est)
    assert "desatualizados desde 05/09/2026" in meta["avisos"][0]


def test_montar_html_substitui_marcadores_e_protege_script():
    meta = {"x": "</script>"}
    html = build.montar_html('<script id="meta">/*META*/</script><script id="bin">/*BIN*/</script>', meta, b"\x01\x02")
    assert "</script>\"" not in html and json.loads(html.split(">", 1)[1].split("</script>")[0].replace("<\\/", "</")) == meta
    assert "AQI=" in html
    t = (build.AQUI / "template.html").read_text(encoding="utf-8")
    assert t.count("/*META*/") == 1 and t.count("/*BIN*/") == 1 and "Prévia" not in t
