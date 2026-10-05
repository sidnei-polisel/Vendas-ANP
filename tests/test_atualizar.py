import io
import pickle
import zipfile

import pandas as pd
import pytest

from ingest import atualizar, conferencia, fonte, store

CFG = {
    "fontes": {"liquidos_zip": "https://x/liquidos.zip", "pagina_mae": "https://x/pagina",
               "conferencia_csv": "https://x/conf.csv"},
    "arquivos_csv": {"atual": "Liquidos_Vendas_Atual.csv", "historico": "H.csv"},
    "incluir_historico": False, "encoding": "cp1252", "separador": ";", "fuso": "America/Sao_Paulo",
    "qualidade": {"max_linhas_invalidas": 0.01, "limiar_parcial": 0.6, "max_parciais_seguidos": 3,
                  "max_queda_mes_fechado": 0.10, "alerta_salto_estornos": 0.5, "divergencia_conferencia": 0.01},
}
CAB = ("Ano;Mês;Agente Regulado;Código do Produto;Nome do Produto;Descrição do Produto;Região Origem;"
       "UF Origem;Região Destinatário;UF Destino;Mercado Destinatário;Quantidade de Produto (mil m³)\n")


def _zip_bytes(meses=range(1, 4), q="10,0"):
    linhas = "".join(f"2025;{m};AG1;1;Diesel B;d;SE;SP;SE;SP;Posto Revendedor;{q}\n" for m in meses)
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        z.writestr("Liquidos_Vendas_Atual.csv", (CAB + linhas).encode("cp1252"))
    return b.getvalue()


class Resp:
    def __init__(self, headers=None, content=b"", status=200, text=""):
        self.headers, self.content, self.status_code, self.text = headers or {}, content, status, text
        self.ok = status < 400

    def raise_for_status(self):
        if not self.ok:
            raise RuntimeError(f"HTTP {self.status_code}")

    def iter_content(self, n):
        yield self.content

    def __enter__(self):
        return self

    def __exit__(self, *a):
        pass


class Sessao:
    def __init__(self, conteudo, etag='"v1"', conf=b""):
        self.conteudo, self.etag, self.conf, self.gets = conteudo, etag, conf, 0

    def head(self, url, **kw):
        return Resp({"ETag": self.etag, "Last-Modified": "Mon", "Content-Length": str(len(self.conteudo))})

    def get(self, url, **kw):
        self.gets += 1
        return Resp(content=self.conf if url.endswith("conf.csv") else self.conteudo)


@pytest.fixture(autouse=True)
def sem_pyarrow(monkeypatch):
    monkeypatch.setattr(store, "_escrever", lambda df, p: pickle.dump(df, open(p, "wb")))
    monkeypatch.setattr(store, "_ler", lambda p: pickle.load(open(p, "rb")))


def test_mudou():
    f = {"etag": '"v1"', "last_modified": "Mon"}
    assert not fonte.mudou({"etag": '"v1"', "last_modified": "Mon"}, f)
    assert fonte.mudou({"etag": '"v2"', "last_modified": "Mon"}, f)
    assert fonte.mudou({"etag": None, "last_modified": None}, f)  # sem cabeçalhos: reprocessa


def test_ciclo_sem_mudanca_nao_baixa(tmp_path):
    s = Sessao(_zip_bytes())
    assert atualizar.atualizar(CFG, tmp_path / "d", sess=s, pasta=tmp_path) == 0
    assert s.gets >= 1
    est = store.ler_estado(tmp_path / "d")
    assert est["fonte"]["etag"] == '"v1"' and est["ultimo_periodo"] == "2025-03"
    s.gets = 0
    assert atualizar.atualizar(CFG, tmp_path / "d", sess=s, pasta=tmp_path) == 0
    assert s.gets == 0  # HEAD igual: não baixou nada


def test_mudanca_regrava_so_mes_alterado(tmp_path):
    d = tmp_path / "d"
    atualizar.atualizar(CFG, d, sess=Sessao(_zip_bytes()), pasta=tmp_path)
    antes = {p.parent.name: p.stat().st_mtime_ns for p in (d / "base").glob("*/part.parquet")}
    atualizar.atualizar(CFG, d, sess=Sessao(_zip_bytes(range(1, 5)), etag='"v2"'), pasta=tmp_path)
    depois = {p.parent.name: p.stat().st_mtime_ns for p in (d / "base").glob("*/part.parquet")}
    assert set(depois) == {f"ano_mes=2025-0{m}" for m in range(1, 5)}
    assert all(depois[k] == antes[k] for k in antes)  # meses iguais não foram regravados


def test_falha_preserva_base(tmp_path):
    d = tmp_path / "d"
    atualizar.atualizar(CFG, d, sess=Sessao(_zip_bytes()), pasta=tmp_path)
    ok = store.ler_estado(d)
    # mês fechado encolhendo 50% -> aborta, base intacta, ultima_falha registrada
    assert atualizar.atualizar(CFG, d, sess=Sessao(_zip_bytes(q="5,0"), etag='"v3"'), pasta=tmp_path) == 1
    est = store.ler_estado(d)
    assert "encolheu" in est["ultima_falha"]["motivo"]
    assert est["meses"] == ok["meses"] and est["fonte"]["etag"] == '"v1"'
    # e a próxima execução tenta de novo, mesmo com ETag igual ao último processado
    s = Sessao(_zip_bytes(), etag='"v1"')
    assert atualizar.atualizar(CFG, d, sess=s, pasta=tmp_path) == 0 and s.gets >= 1
    assert store.ler_estado(d)["ultima_falha"] is None


def test_download_incompleto(tmp_path):
    class Curto(Sessao):
        def head(self, url, **kw):
            return Resp({"ETag": '"v1"', "Content-Length": "999999"})
    assert atualizar.atualizar(CFG, tmp_path / "d", sess=Curto(_zip_bytes()), pasta=tmp_path) == 1
    assert "incompleto" in store.ler_estado(tmp_path / "d")["ultima_falha"]["motivo"]


def test_conferencia_ler_e_comparar():
    csv = ("ANO;MÊS;GRANDE REGIÃO;UNIDADE DA FEDERAÇÃO;PRODUTO;VENDAS\n"
           "2025;JAN;SUDESTE;SÃO PAULO;ÓLEO DIESEL (m3);10000,0\n"
           "2025;JAN;SUDESTE;SÃO PAULO;GLP (m3);5\n").encode("cp1252")
    ref = conferencia.ler(csv)
    assert ref.to_dict("records") == [{"ano_mes": "2025-01", "uf": "SP", "produto": "Diesel B", "vendas_m3": 10000.0}]
    ag = pd.DataFrame({"ano_mes": ["2025-01"], "produto": ["Diesel B"], "uf_destino": ["SP"], "volume_m3": [10000.0]})
    assert conferencia.comparar(ag, ref, 0.01).empty
    ag["volume_m3"] = 10500.0
    div = conferencia.comparar(ag, ref, 0.01)
    assert set(div.nivel) == {"mês×produto", "diesel mês×UF"} and div["dif"].round(3).eq(0.05).all()


def test_conferencia_ler_utf8_com_bom():
    csv = "﻿ANO;MÊS;GRANDE REGIÃO;UNIDADE DA FEDERAÇÃO;PRODUTO;VENDAS\n2025;JUN;REGIÃO SUDESTE;SÃO PAULO;ÓLEO DIESEL;1163897,378\n".encode("utf-8")
    assert conferencia.ler(csv).vendas_m3.tolist() == [1163897.378]


def test_zip_local_nao_usa_a_rede(tmp_path):
    z = tmp_path / "liquidos.zip"
    z.write_bytes(_zip_bytes())

    class SemRede(Sessao):
        def head(self, *a, **k):
            raise AssertionError("não deveria consultar a ANP")

        def get(self, url, **k):  # só a conferência tenta, e falha sem bloquear
            raise RuntimeError("403")
    assert atualizar.atualizar(CFG, tmp_path / "d", sess=SemRede(b""), zip_local=z) == 0
    est = store.ler_estado(tmp_path / "d")
    assert est["ultimo_periodo"] == "2025-03" and est["ultima_falha"] is None and est["fonte"]["arquivo"] == "liquidos.zip"
