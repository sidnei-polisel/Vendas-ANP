from ingest import estado_texto as estado


def test_data_br_e_avisos():
    assert estado.data_br("2026-10-03T09:15:56-03:00") == "03/10/2026"
    assert estado.avisos(None)[0][0] == "erro"
    est = {"atualizado_em": "2026-09-05T06:00:00-03:00", "parciais": ["2026-08"],
           "ultima_falha": {"em": "2026-09-28T06:00:00-03:00", "motivo": "rede"}}
    a = estado.avisos(est)
    assert "desatualizados desde 05/09/2026" in a[0][1] and "28/09/2026" in a[0][1] and "2026-08" in a[1][1]
    assert estado.avisos({"parciais": [], "ultima_falha": None}) == []


def test_validar_consultar():
    import pandas as pd

    from ingest import validar
    ag = pd.DataFrame({"ano_mes": ["2025-06"] * 3, "produto": ["Diesel B"] * 3, "uf_destino": ["SP", "SP", "RJ"],
                       "uf_origem": ["SP"] * 3, "mercado": ["TRR", "CONSUMIDOR FINAL", "TRR"], "volume_m3": [30.0, 10.0, 5.0]})
    t, mk = validar.consultar(ag, "2025-06", "Diesel B", "SP")
    assert t == 40.0 and mk.index[0] == "TRR"
    assert validar.consultar(ag, "2025-06", "Diesel B", "RJ", "origem")[0] == 0.0


def test_destino_efetivo_ni_usa_origem():
    import pandas as pd

    from ingest.geo import destino_efetivo
    d = pd.DataFrame({"uf_origem": ["SP", "MG"], "reg_origem": ["SE", "SE"], "uf_destino": ["NI", "BA"],
                      "reg_destino": ["NI", "NE"], "volume_m3": [1.0, 2.0]}).astype({"uf_destino": "category"})
    r = destino_efetivo(d)
    assert r.uf_destino.tolist() == ["SP", "BA"] and r.reg_destino.tolist() == ["SE", "NE"]
    assert d.uf_destino.tolist() == ["NI", "BA"]  # entrada intacta
