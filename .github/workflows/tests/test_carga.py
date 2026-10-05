import pandas as pd
import pytest

from ingest import carga


def _chunk(linhas):
    cols = ["ano", "mes", "agente", "produto_cod", "produto", "reg_origem", "uf_origem",
            "reg_destino", "uf_destino", "mercado", "quantidade"]
    return pd.DataFrame([["2026", m, "A", "1", "Diesel B", "SE", "SP", "SE", "SP", "TRR", q] for m, q in linhas],
                        columns=cols)


def test_normalizar_soma_estornos_e_descarta_invalidas():
    agg, n, inval, est = carga._normalizar(_chunk([("1", "2,5"), ("1", "-0,5"), ("13", "1"), ("1", "x")]), 1000)
    assert (n, inval, est) == (4, 2, 1)
    assert agg.volume_m3.tolist() == [2000.0]  # (2,5 - 0,5) mil m³ = 2000 m³


def _resumo(vols, agentes=100):
    idx = [f"2025-{m:02d}" for m in range(1, 13)] + ["2026-01", "2026-02", "2026-03", "2026-04", "2026-05"]
    return pd.DataFrame({"volume_m3": vols, "agentes": agentes}, index=idx[:len(vols)])


def test_parcial_so_na_ponta():
    assert carga.marcar_parciais(_resumo([100] * 13 + [40]), 0.6, 3) == ["2026-02"]
    assert carga.marcar_parciais(_resumo([100] * 14), 0.6, 3) == []


def test_parciais_demais_falha():
    with pytest.raises(ValueError, match="seguidos"):
        carga.marcar_parciais(_resumo([100] * 13 + [40] * 4), 0.6, 3)


def test_regressao():
    antigos = {"2025-01": {"volume_m3": 100.0}}
    r = pd.DataFrame({"volume_m3": [95.0, 10.0]}, index=["2025-01", "2025-02"])
    carga.checar_regressao(antigos, [], r, 0.10)
    r.loc["2025-01", "volume_m3"] = 85.0
    with pytest.raises(ValueError, match="encolheu"):
        carga.checar_regressao(antigos, [], r, 0.10)
