"""Destino efetivo: linhas com UF/região de destino 'NI' (não informado) passam para a UF/região de origem.

É o critério do Painel Dinâmico da ANP (validado em jun/2025: consumidor final de diesel B em SP 354,90 + 21,73
de linhas NI com origem SP = 376,63 mil m³, igual ao painel). A base em disco continua com os valores brutos.
"""


def destino_efetivo(df):
    if "uf_origem" not in df or "uf_destino" not in df:
        return df
    ni = df["uf_destino"].astype(str) == "NI"
    if not ni.any():
        return df
    df = df.astype({"uf_destino": "object", "reg_destino": "object"})
    df.loc[ni, "uf_destino"] = df.loc[ni, "uf_origem"].astype(str)
    df.loc[ni, "reg_destino"] = df.loc[ni, "reg_origem"].astype(str)
    return df
