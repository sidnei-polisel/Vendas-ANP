"""Persistência: Parquet por ano-mês, agregado.parquet e state.json, sempre com escrita atômica."""
import json
import os
from pathlib import Path

import pandas as pd

from .carga import AGREG

ESTADO_VAZIO = {"fonte": {}, "meses": {}, "parciais": [], "estornos": 0, "ultima_falha": None}


def _escrever(df, caminho):
    df.to_parquet(caminho, compression="zstd", index=False)


def _ler(caminho):
    return pd.read_parquet(caminho)


def _atomico(escrever, destino):
    # Temporário na mesma pasta para o os.replace ser atômico.
    tmp = destino.with_name(destino.name + ".tmp")
    escrever(tmp)
    os.replace(tmp, destino)


def ler_estado(data):
    arq = Path(data) / "state.json"
    return json.loads(arq.read_text(encoding="utf-8")) if arq.exists() else json.loads(json.dumps(ESTADO_VAZIO))


def gravar_estado(data, estado):
    Path(data).mkdir(parents=True, exist_ok=True)
    _atomico(lambda p: p.write_text(json.dumps(estado, ensure_ascii=False, indent=1), encoding="utf-8"),
             Path(data) / "state.json")


def gravar(data, base, agregado, mudados, completo):
    """Regrava só as partições mudadas e os trechos afetados do agregado. O state.json fica por último."""
    data = Path(data)
    for ym, g in base.groupby("ano_mes"):
        if ym in mudados:
            pasta = data / "base" / f"ano_mes={ym}"
            pasta.mkdir(parents=True, exist_ok=True)
            _atomico(lambda p, g=g: _escrever(g, p), pasta / "part.parquet")
    alvo = data / "agregado.parquet"
    novo = agregado[agregado.ano_mes.isin(mudados)]
    if not completo and alvo.exists():
        # category -> object evita conflito de categorias no concat
        antigo = _ler(alvo).astype({c: "object" for c in AGREG})
        novo = pd.concat([antigo[~antigo.ano_mes.isin(mudados)], novo])
    novo = novo.sort_values(AGREG, ignore_index=True).astype({c: "category" for c in AGREG})
    _atomico(lambda p: _escrever(novo, p), alvo)
