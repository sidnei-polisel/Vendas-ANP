"""Verifica (HEAD) e baixa o liquidos.zip da ANP. Só usa a rede aqui; o resto do pacote é puro."""
import hashlib
import logging
import os
import re
import zipfile
from pathlib import Path
from urllib.parse import urljoin


log = logging.getLogger("ingest")
# O gov.br recusa clientes sem cara de navegador; é o mesmo arquivo público de dados abertos.
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0 Safari/537.36",
      "Accept": "*/*", "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.5"}


def assinatura(h):
    """Identidade da versão remota: ETag e Last-Modified (+ tamanho como reforço)."""
    return {"etag": h.get("ETag"), "last_modified": h.get("Last-Modified"),
            "bytes": int(h["Content-Length"]) if h.get("Content-Length", "").isdigit() else None}


def mudou(remoto, fonte):
    """True se o arquivo remoto difere do último processado. Sem nenhum cabeçalho útil, assume que mudou."""
    if not (remoto["etag"] or remoto["last_modified"]):
        return True
    for k in ("etag", "last_modified"):
        if remoto[k] and remoto[k] != fonte.get(k):
            return True
    return False


def achar_url(cfg, sessao):
    """URL do zip; se falhar, procura o link liquidos.zip na página-mãe oficial."""
    url = cfg["fontes"]["liquidos_zip"]
    r = sessao.head(url, allow_redirects=True, timeout=30)
    if r.ok:
        return url, r
    log.warning("HEAD %s -> %s; procurando na página-mãe", url, r.status_code)
    pag = sessao.get(cfg["fontes"]["pagina_mae"], timeout=60)
    pag.raise_for_status()
    m = re.search(r'href="([^"]*liquidos\.zip[^"]*)"', pag.text, re.I)
    if not m:
        raise RuntimeError("liquidos.zip não encontrado na página-mãe da ANP")
    url = urljoin(cfg["fontes"]["pagina_mae"], m.group(1))
    r = sessao.head(url, allow_redirects=True, timeout=30)
    r.raise_for_status()
    return url, r


def sessao(tentativas=3):
    import requests
    s = requests.Session()
    s.headers.update(UA)
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry
    s.mount("https://", HTTPAdapter(max_retries=Retry(total=tentativas, backoff_factor=2,
                                                      status_forcelist=(429, 500, 502, 503, 504))))
    return s


def baixar(url, destino, sessao_, esperado=None):
    """Baixa em arquivo temporário, confere tamanho e integridade do zip e só então renomeia."""
    destino = Path(destino)
    tmp = destino.with_name(destino.name + ".part")
    h = hashlib.sha256()
    with sessao_.get(url, stream=True, timeout=120) as r:
        r.raise_for_status()
        with open(tmp, "wb") as f:
            for bloco in r.iter_content(1 << 20):
                f.write(bloco)
                h.update(bloco)
        info = assinatura(r.headers)
    tam = tmp.stat().st_size
    esperado = esperado or info["bytes"]
    if esperado and tam != esperado:
        tmp.unlink()
        raise RuntimeError(f"download incompleto: {tam} de {esperado} bytes")
    if not zipfile.is_zipfile(tmp) or zipfile.ZipFile(tmp).testzip() is not None:
        tmp.unlink()
        raise RuntimeError("arquivo baixado não é um zip íntegro")
    os.replace(tmp, destino)
    return info
