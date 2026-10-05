"""Conferência com a base oficial de vendas (vendas-combustiveis-m3). Só gera log; nunca bloqueia a carga."""
import io
import logging

import pandas as pd

from .geo import destino_efetivo
from .schema import norm

log = logging.getLogger("ingest")
MESES = {m: i + 1 for i, m in enumerate("jan fev mar abr mai jun jul ago set out nov dez".split())}
# produto do SIMP (líquidos) -> prefixo normalizado do produto na base de vendas
PRODUTOS = {"Diesel B": "oleo diesel", "Gasolina C": "gasolina c", "Etanol Hidratado": "etanol hidratado"}
UFS = {"ACRE": "AC", "ALAGOAS": "AL", "AMAPA": "AP", "AMAZONAS": "AM", "BAHIA": "BA", "CEARA": "CE",
       "DISTRITO FEDERAL": "DF", "ESPIRITO SANTO": "ES", "GOIAS": "GO", "MARANHAO": "MA",
       "MATO GROSSO": "MT", "MATO GROSSO DO SUL": "MS", "MINAS GERAIS": "MG", "PARA": "PA",
       "PARAIBA": "PB", "PARANA": "PR", "PERNAMBUCO": "PE", "PIAUI": "PI", "RIO DE JANEIRO": "RJ",
       "RIO GRANDE DO NORTE": "RN", "RIO GRANDE DO SUL": "RS", "RONDONIA": "RO", "RORAIMA": "RR",
       "SANTA CATARINA": "SC", "SAO PAULO": "SP", "SERGIPE": "SE", "TOCANTINS": "TO"}


def _num(s):
    s = s.astype(str).str.strip()
    com_virgula = s.str.contains(",", regex=False)
    s = s.where(~com_virgula, s.str.replace(".", "", regex=False).str.replace(",", ".", regex=False))
    return pd.to_numeric(s, errors="coerce")


def ler(origem, encoding="cp1252", sep=";"):
    """CSV de vendas -> DataFrame [ano_mes, uf, produto, vendas_m3]. Aceita caminho ou bytes."""
    if not isinstance(origem, bytes):
        origem = open(origem, "rb").read()
    try:  # a base de vendas vem em UTF-8 com BOM; cai para o encoding da config se não for
        texto = origem.decode("utf-8-sig")
    except UnicodeDecodeError:
        texto = origem.decode(encoding)
    bruto = pd.read_csv(io.StringIO(texto), sep=sep, dtype=str, keep_default_na=False)
    bruto.columns = [norm(c.strip('"')) for c in bruto.columns]
    ano = pd.to_numeric(bruto["ano"], errors="coerce")
    mes = bruto["mes"].map(lambda m: MESES.get(norm(m)[:3]))
    prod = bruto["produto"].map(norm)
    alvo = {v: k for k, v in PRODUTOS.items()}
    produto = prod.map(lambda p: next((alvo[k] for k in alvo if p.startswith(k)), None))
    df = pd.DataFrame({"ano": ano, "mes": mes, "uf": bruto["unidade da federacao"].map(norm).str.upper().map(UFS),
                       "produto": produto, "vendas_m3": _num(bruto["vendas"])})
    df = df.dropna().copy()
    df["ano_mes"] = df.ano.astype(int).astype(str) + "-" + df.mes.astype(int).astype(str).str.zfill(2)
    return df[["ano_mes", "uf", "produto", "vendas_m3"]]


def comparar(agregado, ref, limite, desde=None):
    """Compara, por mês×produto e por mês×UF do diesel, a base própria (destino) com a base de vendas.

    Retorna DataFrame das divergências acima de `limite` (fração). Só meses presentes nas duas bases.
    """
    base = destino_efetivo(agregado[agregado.produto.isin(PRODUTOS)])
    meses = sorted(set(base.ano_mes) & set(ref.ano_mes))
    if desde:
        meses = [m for m in meses if m >= desde]
    if not meses:
        return pd.DataFrame(columns=["nivel", "ano_mes", "chave", "anp_simp", "vendas", "dif"])
    base, ref = base[base.ano_mes.isin(meses)], ref[ref.ano_mes.isin(meses)]
    saidas = []
    for nivel, cb, cr in (("mês×produto", ["ano_mes", "produto"], ["ano_mes", "produto"]),
                          ("diesel mês×UF", ["ano_mes", "uf_destino"], ["ano_mes", "uf"])):
        b, r = base, ref
        if nivel.startswith("diesel"):
            b, r = b[b.produto == "Diesel B"], r[r.produto == "Diesel B"]
        b = b.groupby(cb).volume_m3.sum().rename("anp_simp")
        r = r.groupby(cr).vendas_m3.sum().rename("vendas")
        r.index.names = b.index.names
        j = pd.concat([b, r], axis=1).fillna(0).reset_index()
        j["dif"] = (j.anp_simp - j.vendas) / j.vendas.where(j.vendas != 0)
        j["chave"] = j[cb[1]]
        j["nivel"] = nivel
        saidas.append(j[["nivel", "ano_mes", "chave", "anp_simp", "vendas", "dif"]])
    t = pd.concat(saidas, ignore_index=True)
    return t[t["dif"].abs().gt(limite) | t["dif"].isna()].sort_values(["nivel", "ano_mes", "chave"], ignore_index=True)


def registrar(div, limite, n_meses):
    if div.empty:
        log.info("conferência: sem divergências acima de %.1f%% em %d meses", limite * 100, n_meses)
        return
    log.warning("conferência: %d divergências acima de %.1f%% (não bloqueia)", len(div), limite * 100)
    for r in div.head(20).itertuples():
        log.warning("  %s %s %s: simp=%.0f vendas=%.0f dif=%+.2f%%", r.nivel, r.ano_mes, r.chave,
                    r.anp_simp, r.vendas, (r.dif or 0) * 100)
