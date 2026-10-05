"""Leitura, validação e agregação dos CSVs de líquidos (pandas puro, sem I/O de Parquet)."""
import hashlib
import zipfile

import pandas as pd

from .schema import FATOR_SEM_CABECALHO, SEM_CABECALHO, SchemaError, mapear, tem_cabecalho

BASE = ["ano_mes", "agente", "produto_cod", "produto", "produto_desc",
        "reg_origem", "uf_origem", "reg_destino", "uf_destino", "mercado"]
AGREG = ["ano_mes", "agente", "produto", "reg_origem", "uf_origem",
         "reg_destino", "uf_destino", "mercado"]
CHUNK = 500_000


def _normalizar(chunk, fator):
    """Valida linhas e agrega o chunk em m³. Retorna (agregado, linhas, inválidas, estornos)."""
    if "produto_desc" not in chunk:
        chunk["produto_desc"] = ""
    for c in ("ano", "mes"):
        chunk[c] = pd.to_numeric(chunk[c], errors="coerce")
    chunk["quantidade"] = pd.to_numeric(chunk["quantidade"].str.replace(",", ".", regex=False),
                                        errors="coerce")
    ok = (chunk.ano.between(2000, 2100) & chunk.mes.between(1, 12)
          & (chunk.ano % 1 == 0) & (chunk.mes % 1 == 0) & chunk.quantidade.notna())
    v = chunk[ok].copy()
    v["ano_mes"] = v.ano.astype(int).astype(str) + "-" + v.mes.astype(int).astype(str).str.zfill(2)
    v["volume_m3"] = v.quantidade * fator
    for c in BASE[1:]:
        v[c] = v[c].str.strip()
    return v.groupby(BASE, as_index=False)["volume_m3"].sum(), len(chunk), int((~ok).sum()), int((v.quantidade < 0).sum())


def _ler_csv(zf, nome, cfg):
    enc, sep = cfg["encoding"], cfg["separador"]
    with zf.open(nome) as f:
        primeira = f.readline().decode(enc)
    kw = dict(sep=sep, encoding=enc, dtype=str, keep_default_na=False, chunksize=CHUNK)
    if tem_cabecalho(primeira, sep):
        renome, fator = mapear([c.strip('"') for c in primeira.strip().split(sep)])
        leitor = pd.read_csv(zf.open(nome), header=0, **kw)
        return (c.rename(columns=renome) for c in leitor), fator
    return pd.read_csv(zf.open(nome), header=None, names=SEM_CABECALHO, **kw), FATOR_SEM_CABECALHO


def _ler_arquivo(zf, nome, cfg):
    if nome not in zf.namelist():
        raise SchemaError(f"'{nome}' não está no zip; arquivos: {zf.namelist()}")
    chunks, fator = _ler_csv(zf, nome, cfg)
    partes, tot = [], dict(linhas=0, invalidas=0, estornos=0)
    for chunk in chunks:
        agg, n, inval, est = _normalizar(chunk, fator)
        partes.append(agg)
        tot["linhas"] += n
        tot["invalidas"] += inval
        tot["estornos"] += est
    return pd.concat(partes), tot


def ler_zip(caminho, cfg):
    """Lê o zip em chunks. Retorna (base em m³ no grão BASE, estatísticas)."""
    with zipfile.ZipFile(caminho) as zf:
        atual, tot = _ler_arquivo(zf, cfg["arquivos_csv"]["atual"], cfg)
        partes = [atual]
        if cfg["incluir_historico"]:
            hist, t2 = _ler_arquivo(zf, cfg["arquivos_csv"]["historico"], cfg)
            # Atual prevalece onde os períodos se sobrepõem.
            partes.append(hist[hist.ano_mes < atual.ano_mes.min()])
            for k in tot:
                tot[k] += t2[k]
    if tot["invalidas"] / tot["linhas"] > cfg["qualidade"]["max_linhas_invalidas"]:
        raise ValueError(f"{tot['invalidas']} de {tot['linhas']} linhas inválidas (> limite); carga interrompida.")
    base = pd.concat(partes).groupby(BASE, as_index=False)["volume_m3"].sum()
    base["volume_m3"] = base.volume_m3.round(3)
    return base.sort_values(BASE, ignore_index=True), tot


def agregar(base):
    return base.groupby(AGREG, as_index=False)["volume_m3"].sum().round({"volume_m3": 3})


def resumo_mensal(base, agregado):
    g = agregado.groupby("ano_mes").agg(volume_m3=("volume_m3", "sum"), agentes=("agente", "nunique"))
    g["linhas"] = base.groupby("ano_mes").size()
    return g.sort_index()


def marcar_parciais(resumo, limiar, max_seguidos):
    """Marca meses da ponta com volume ou agentes < limiar × mediana dos 12 meses anteriores."""
    parciais = []
    for i in range(len(resumo) - 1, -1, -1):
        anteriores = resumo.iloc[max(0, i - 12):i]
        if len(anteriores) < 12:
            break
        ref, atual = anteriores.median(), resumo.iloc[i]
        if atual.volume_m3 < limiar * ref.volume_m3 or atual.agentes < limiar * ref.agentes:
            parciais.append(resumo.index[i])
        else:
            break  # só a ponta é avaliada: para no primeiro mês fechado
    if len(parciais) > max_seguidos:
        raise ValueError(f"{len(parciais)} meses seguidos abaixo do limiar de mês parcial: {sorted(parciais)}")
    return sorted(parciais)


def checar_regressao(meses_antigos, parciais_antigos, resumo, max_queda):
    """Barra a escrita se a base encolher: menos meses ou mês fechado com queda acima do limite."""
    if len(resumo) < len(meses_antigos):
        raise ValueError(f"Número de meses caiu de {len(meses_antigos)} para {len(resumo)}.")
    for ym, m in meses_antigos.items():
        if ym in parciais_antigos:
            continue
        novo = resumo.volume_m3.get(ym)
        if novo is None or novo < m["volume_m3"] * (1 - max_queda):
            raise ValueError(f"Mês fechado {ym} encolheu: {m['volume_m3']:.0f} -> {novo} m³ (limite {max_queda:.0%}).")


def hashes_por_mes(base):
    def h(df):
        return hashlib.sha256(pd.util.hash_pandas_object(df, index=False).values.tobytes()).hexdigest()
    return {ym: h(g) for ym, g in base.groupby("ano_mes")}
