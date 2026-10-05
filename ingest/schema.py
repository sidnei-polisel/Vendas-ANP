"""Mapeia colunas pelo nome do cabeçalho (sem acento, minúsculas) e extrai a unidade."""
import re
import unicodedata


class SchemaError(Exception):
    pass


NOMES = {
    "ano": "ano",
    "mes": "mes",
    "agente": "agente regulado",
    "produto_cod": "codigo do produto",
    "produto": "nome do produto",
    "reg_origem": "regiao origem",
    "uf_origem": "uf origem",
    "reg_destino": "regiao destinatario",
    "uf_destino": "uf destino",
    "mercado": "mercado destinatario",
}
OPCIONAIS = {"produto_desc": "descricao do produto"}

# Histórico 2007-2016: sem cabeçalho e sem descrição do produto. A unidade (mil m³)
# não vem escrita; foi confirmada só por comparação com a base de vendas da ANP.
SEM_CABECALHO = ["ano", "mes", "agente", "produto_cod", "produto", "reg_origem",
                 "uf_origem", "reg_destino", "uf_destino", "mercado", "quantidade"]
FATOR_SEM_CABECALHO = 1000


def norm(texto):
    ascii_ = unicodedata.normalize("NFKD", str(texto)).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", ascii_).strip().strip('"').lower()


def tem_cabecalho(primeira_linha, sep):
    return not norm(primeira_linha.split(sep)[0]).isdigit()


def fator_unidade(coluna):
    """Fator para converter a quantidade em m³; recusa unidade não reconhecida."""
    n = norm(coluna)
    if "mil m3" in n:
        return 1000
    if re.search(r"\bm3\b", n):
        return 1
    raise SchemaError(f"Unidade não reconhecida em '{coluna}'; não converto sem confirmação.")


def mapear(colunas):
    """Retorna ({nome_original: nome_canônico}, fator_para_m3) ou levanta SchemaError."""
    por_nome = {norm(c): c for c in colunas}
    renome, faltando = {}, []
    for canon, nome in NOMES.items():
        if nome in por_nome:
            renome[por_nome[nome]] = canon
        else:
            faltando.append(nome)
    for canon, nome in OPCIONAIS.items():
        if nome in por_nome:
            renome[por_nome[nome]] = canon
    qtd = [c for n, c in por_nome.items() if n.startswith("quantidade")]
    if not qtd:
        faltando.append("quantidade")
    if faltando:
        raise SchemaError(f"Layout mudou; colunas ausentes: {faltando}. Cabeçalho lido: {list(colunas)}")
    renome[qtd[0]] = "quantidade"
    return renome, fator_unidade(qtd[0])
