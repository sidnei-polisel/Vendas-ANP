"""Leitura do state.json para o aviso de dados desatualizados e o rodapé (sem Streamlit)."""
import json
from pathlib import Path


def ler(data):
    arq = Path(data) / "state.json"
    return json.loads(arq.read_text(encoding="utf-8")) if arq.exists() else None


def data_br(iso):
    """'2026-10-03T09:15:56-03:00' -> '03/10/2026'."""
    return f"{iso[8:10]}/{iso[5:7]}/{iso[:4]}" if iso else "—"


def avisos(est):
    """Lista de (nivel, texto). nivel: 'erro' | 'aviso'."""
    if not est:
        return [("erro", "Base ainda não carregada. Rode a carga inicial (python -m ingest.run).")]
    out = []
    f = est.get("ultima_falha")
    if f:
        out.append(("aviso", f"Dados desatualizados desde {data_br(est.get('atualizado_em'))}. "
                             f"A última atualização falhou em {data_br(f['em'])}: {f['motivo']}"))
    if est.get("parciais"):
        out.append(("aviso", "Mês(es) possivelmente parcial(is) na ANP: " + ", ".join(est["parciais"])
                    + ". Ficam fora da variação sobre o ano anterior."))
    return out
