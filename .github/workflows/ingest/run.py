"""Carga da ANP: python -m ingest.run --zip liquidos.zip [--full-refresh]. Python puro, sem LLM."""
import argparse
import hashlib
import logging
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

from . import carga, store

log = logging.getLogger("ingest")


def _sha256(caminho):
    h = hashlib.sha256()
    with open(caminho, "rb") as f:
        for bloco in iter(lambda: f.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


def executar(zip_path, cfg, data, completo, estado, remoto=None):
    q = cfg["qualidade"]
    base, st = carga.ler_zip(zip_path, cfg)
    agregado = carga.agregar(base)
    resumo = carga.resumo_mensal(base, agregado)
    parciais = carga.marcar_parciais(resumo, q["limiar_parcial"], q["max_parciais_seguidos"])
    carga.checar_regressao(estado["meses"], estado["parciais"], resumo, q["max_queda_mes_fechado"])

    hashes = carga.hashes_por_mes(base)
    mudados = {ym for ym, h in hashes.items() if completo or estado["meses"].get(ym, {}).get("hash") != h}
    antes = estado["estornos"]
    if antes and st["estornos"] > antes * (1 + q["alerta_salto_estornos"]):
        log.warning("Salto de estornos: %d -> %d", antes, st["estornos"])

    store.gravar(data, base, agregado, mudados, completo or not estado["meses"])
    agora = datetime.now(ZoneInfo(cfg["fuso"])).isoformat(timespec="seconds")
    novo = {
        "fonte": {"arquivo": Path(zip_path).name, "sha256": _sha256(zip_path),
                  "bytes": Path(zip_path).stat().st_size,
                  "etag": (remoto or {}).get("etag"), "last_modified": (remoto or {}).get("last_modified")},
        "atualizado_em": agora,
        "ultimo_periodo": resumo.index[-1],
        "linhas_fonte": st["linhas"], "linhas_invalidas": st["invalidas"], "estornos": st["estornos"],
        "meses": {ym: {"hash": hashes[ym], "linhas": int(r.linhas), "volume_m3": round(float(r.volume_m3), 3),
                       "agentes": int(r.agentes)} for ym, r in resumo.iterrows()},
        "parciais": parciais,
        "ultima_falha": None,
    }
    store.gravar_estado(data, novo)
    log.info("ok: %d meses (%s a %s), %d regravados, parciais=%s, estornos=%d, inválidas=%d",
             len(resumo), resumo.index[0], resumo.index[-1], len(mudados), parciais or "nenhum",
             st["estornos"], st["invalidas"])
    return novo, agregado


def registrar_falha(data, estado, cfg, erro):
    """Base e partições ficam como estavam; só o state.json ganha `ultima_falha` (o app avisa 'desatualizado')."""
    log.error("Falha: %s", erro)
    estado["ultima_falha"] = {"em": datetime.now(ZoneInfo(cfg["fuso"])).isoformat(timespec="seconds"),
                              "motivo": str(erro)}
    store.gravar_estado(data, estado)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--zip", required=True, type=Path)
    ap.add_argument("--config", default="config.yaml", type=Path)
    ap.add_argument("--data", default="data", type=Path)
    ap.add_argument("--full-refresh", action="store_true")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    cfg = yaml.safe_load(a.config.read_text(encoding="utf-8"))
    estado = store.ler_estado(a.data)
    try:
        executar(a.zip, cfg, a.data, a.full_refresh, estado)
    except Exception as e:  # preserva a base atual; o app lê ultima_falha
        registrar_falha(a.data, estado, cfg, e)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
