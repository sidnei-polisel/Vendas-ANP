"""Atualização mensal: python -m ingest.atualizar [--forcar]. Verifica a ANP (HEAD), baixa só se mudou."""
import argparse
import logging
import sys
import tempfile
from pathlib import Path

import yaml

from . import conferencia, fonte, run, store

log = logging.getLogger("ingest")


def _conferir(cfg, sess, agregado, estado_novo, data):
    """Falhas aqui só viram aviso: a conferência nunca bloqueia a carga."""
    try:
        r = sess.get(cfg["fontes"]["conferencia_csv"], timeout=120)
        r.raise_for_status()
        ref = conferencia.ler(r.content, cfg["encoding"], cfg["separador"])
        ag = agregado.astype({"ano_mes": "object", "produto": "object", "uf_destino": "object"})
        div = conferencia.comparar(ag, ref, cfg["qualidade"]["divergencia_conferencia"])
        conferencia.registrar(div, cfg["qualidade"]["divergencia_conferencia"], ref.ano_mes.nunique())
        estado_novo["conferencia"] = {"divergencias": int(len(div)), "ate": ref.ano_mes.max()}
        store.gravar_estado(data, estado_novo)
    except Exception as e:  # noqa: BLE001
        log.warning("conferência não executada: %s", e)


def atualizar(cfg, data, forcar=False, sess=None, pasta=None, zip_local=None):
    """Retorna 0 (atualizado ou sem mudança) ou 1 (falha; base preservada).

    `zip_local`: processa um liquidos.zip já baixado (plano B quando a ANP bloqueia o download automático).
    """
    sess = sess or fonte.sessao()
    estado = store.ler_estado(data)
    try:
        if zip_local:
            novo, agregado = run.executar(Path(zip_local), cfg, data, False, estado, None)
            _conferir(cfg, sess, agregado, novo, data)
            return 0
        url, head = fonte.achar_url(cfg, sess)
        remoto = fonte.assinatura(head.headers)
        if not forcar and not estado.get("ultima_falha") and not fonte.mudou(remoto, estado["fonte"]):
            log.info("sem mudança na ANP (ETag/Last-Modified iguais); nada a fazer")
            return 0
        with tempfile.TemporaryDirectory(dir=pasta) as tmp:
            zip_path = Path(tmp) / "liquidos.zip"
            info = fonte.baixar(url, zip_path, sess, remoto["bytes"])
            remoto = {**remoto, **{k: v for k, v in info.items() if v}}
            novo, agregado = run.executar(zip_path, cfg, data, False, estado, remoto)
        _conferir(cfg, sess, agregado, novo, data)
    except Exception as e:  # noqa: BLE001
        run.registrar_falha(data, estado, cfg, e)
        return 1
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", default="config.yaml", type=Path)
    ap.add_argument("--data", default="data", type=Path)
    ap.add_argument("--zip", type=Path, help="liquidos.zip já baixado (pula o download)")
    ap.add_argument("--forcar", action="store_true", help="baixa e processa mesmo sem mudança")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    cfg = yaml.safe_load(a.config.read_text(encoding="utf-8"))
    return atualizar(cfg, a.data, a.forcar, zip_local=a.zip)


if __name__ == "__main__":
    sys.exit(main())
