import pytest

from ingest.schema import SchemaError, fator_unidade, mapear, tem_cabecalho

CAB = ["Ano", "Mês", "Agente Regulado", "Código do Produto", "Nome do Produto", "Descrição do Produto",
       "Região Origem", "UF Origem", "Região Destinatário", "UF Destino", "Mercado Destinatário"]


@pytest.mark.parametrize("col,fator", [("Quantidade de Produto (mil m³)", 1000),
                                       ("quantidade de produto (mil m3)", 1000),
                                       ("Quantidade de Produto (m³)", 1)])
def test_unidade(col, fator):
    assert mapear(CAB + [col])[1] == fator


def test_unidade_desconhecida_falha():
    with pytest.raises(SchemaError, match="Unidade"):
        fator_unidade("Quantidade (litros)")


def test_coluna_ausente_falha_com_nome():
    with pytest.raises(SchemaError, match="uf destino"):
        mapear([c for c in CAB if c != "UF Destino"] + ["Quantidade de Produto (mil m³)"])


def test_cabecalho():
    assert tem_cabecalho('"Ano";"Mês"', ";")
    assert not tem_cabecalho("2007;1;ABC", ";")
