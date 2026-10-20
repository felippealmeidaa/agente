"""Política de permissões do painel de controle: categorias de ferramentas e a decisão para cada chamada.

Funções puras (sem disco): ``canal.py`` lê a política gravada pelo app e chama ``decidir``.
"""

from __future__ import annotations

import json
import ntpath
import os
import posixpath
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Optional

from . import protecao

MODOS = ("livre", "perguntar", "bloqueado")
VAZAMENTO = ("perguntar", "bloquear", "desligado")

# id -> (nome, ferramentas exatas, prefixos, modo padrão); o app desktop lê o mesmo arquivo
_ARQUIVO = Path(__file__).with_name("categorias.json")
CATEGORIAS: dict[str, tuple[str, tuple[str, ...], tuple[str, ...], str]] = {
    c["id"]: (c["nome"], tuple(c["ferramentas"]), tuple(c["prefixos"]), c["padrao"])
    for c in json.loads(_ARQUIVO.read_text(encoding="utf-8"))
}
DESCRICOES: dict[str, str] = {c["id"]: c["descricao"] for c in json.loads(_ARQUIVO.read_text(encoding="utf-8"))}

# Mural, perguntas ao dono e lista de tarefas nunca pedem aprovação (mas param com o resto)
SEMPRE_LIVRES = frozenset({"mural_ler", "mural_escrever", "mural_responder", "clarify", "todo_list"})


def categoria(ferramenta: str) -> str:
    for cid, (_, exatas, prefixos, _) in CATEGORIAS.items():
        if ferramenta in exatas or any(ferramenta.startswith(p) for p in prefixos):
            return cid
    return "outros"


def politica_padrao() -> dict[str, Any]:
    return {
        "versao": 1,
        "parado": False,
        "categorias": {cid: padrao for cid, (_, _, _, padrao) in CATEGORIAS.items()},
        "pastas_livres": [],
        "espera_segundos": 120,
        # Lembradas pelo app ("sempre permitir / sempre negar"): [{"padrao": ..., "modo": "livre"|"bloqueado"}]
        "regras": [],
        "liberar_triviais": True,
        "vazamento": "perguntar",
        "cercar_externo": True,
        # Onde o dono aprova: "hermes" (tela de aprovação do próprio Hermes) ou "app" (app de controle separado)
        "aprovar_em": "hermes",
    }


def normalizar(politica: Any) -> dict[str, Any]:
    """Completa e saneia o que veio do arquivo; valor estranho volta ao padrão mais seguro."""
    base = politica_padrao()
    if not isinstance(politica, dict):
        return base
    base["parado"] = politica.get("parado") is True
    cats = politica.get("categorias") if isinstance(politica.get("categorias"), dict) else {}
    for cid in base["categorias"]:
        if cats.get(cid) in MODOS:
            base["categorias"][cid] = cats[cid]
    pastas = politica.get("pastas_livres")
    if isinstance(pastas, list):
        base["pastas_livres"] = [p for p in pastas if isinstance(p, str) and p.strip()]
    try:
        base["espera_segundos"] = max(10, min(int(politica.get("espera_segundos", 120)), 590))
    except (TypeError, ValueError):
        pass
    regras = politica.get("regras")
    if isinstance(regras, list):
        base["regras"] = [{"padrao": r["padrao"], "modo": r["modo"]} for r in regras
                          if isinstance(r, dict) and isinstance(r.get("padrao"), str) and r["padrao"]
                          and r.get("modo") in ("livre", "bloqueado")]
    if politica.get("liberar_triviais") is False:
        base["liberar_triviais"] = False
    if politica.get("vazamento") in VAZAMENTO:
        base["vazamento"] = politica["vazamento"]
    if politica.get("cercar_externo") is False:
        base["cercar_externo"] = False
    if politica.get("aprovar_em") in ("hermes", "app"):
        base["aprovar_em"] = politica["aprovar_em"]
    return base


def _absoluto(caminho: str) -> str:
    if ntpath.isabs(caminho) or (len(caminho) > 1 and caminho[1] == ":"):
        return ntpath.normcase(ntpath.normpath(caminho))
    if caminho.startswith("/"):
        return posixpath.normpath(caminho)
    return os.path.normcase(os.path.abspath(caminho))


def dentro_de(caminho: str, pastas: list[str]) -> bool:
    alvo = _absoluto(os.path.expanduser(caminho))
    for pasta in pastas:
        raiz = _absoluto(os.path.expanduser(pasta)).rstrip("\\/")
        if alvo == raiz or alvo.startswith(raiz + "\\") or alvo.startswith(raiz + "/"):
            return True
    return False


def caminho_do_arquivo(args: dict) -> Optional[str]:
    for chave in ("path", "file_path", "filename"):
        valor = args.get(chave)
        if isinstance(valor, str) and valor.strip():
            return valor
    return None


@dataclass(frozen=True)
class Decisao:
    modo: str                      # livre | perguntar | bloqueado
    motivo: str = ""
    padrao: Optional[str] = None   # chave lembrável; None quando não dá para lembrar
    risco: str = "normal"          # alto | trivial | normal
    vazamento: bool = False        # pergunta porque a sessão viu dado sensível


def _pasta_do_arquivo(args: dict) -> Optional[str]:
    caminho = caminho_do_arquivo(args)
    if not caminho:
        return None
    absoluto = _absoluto(os.path.expanduser(caminho))
    return (ntpath if ("\\" in absoluto or ":" in absoluto[:3]) else posixpath).dirname(absoluto)


def decidir(ferramenta: str, args: dict, politica: dict, marcas: Iterable[str] = (),
            protegidas: Iterable[str] = ()) -> Decisao:
    """O que fazer com esta chamada, na ordem: pausa, pasta do controle, vazamento, regra lembrada,
    risco e por fim o modo da categoria."""
    if politica["parado"]:
        return Decisao("bloqueado", "o agente está pausado no painel de controle")
    if protegidas and protecao.toca_em(args, protegidas):
        return Decisao("bloqueado", "o agente não pode mexer na pasta do painel de controle")

    cid = categoria(ferramenta)
    nome = CATEGORIAS[cid][0]
    risco = protecao.risco(ferramenta, cid, args)
    chave = protecao.padrao(ferramenta, cid, args, _pasta_do_arquivo(args))
    if chave is not None and risco == "alto":
        chave = None  # risco alto nunca vira "sempre"

    marcas = frozenset(marcas)
    if marcas and politica["vazamento"] != "desligado" and protecao.eh_saida(ferramenta, cid, args):
        tipo = "um segredo (chave, token ou senha)" if "segredo" in marcas else "dados pessoais (CPF, CNPJ ou cartão)"
        motivo = f"esta sessão leu {tipo} e esta ação pode mandar isso para fora do PC"
        if politica["vazamento"] == "bloquear":
            return Decisao("bloqueado", motivo, risco=risco, vazamento=True)
        return Decisao("perguntar", motivo, padrao=None, risco=risco, vazamento=True)

    if ferramenta in SEMPRE_LIVRES or protecao.acao_do_mural(ferramenta):
        return Decisao("livre")

    modo = politica["categorias"][cid]
    if modo == "bloqueado":
        return Decisao("bloqueado", f"a permissão \"{nome}\" está desligada no painel de controle", risco=risco)

    lembrada = next((r["modo"] for r in politica["regras"] if chave is not None and r["padrao"] == chave), None)
    if lembrada == "bloqueado":
        return Decisao("bloqueado", f"você marcou \"sempre negar\" para {chave}", padrao=chave, risco=risco)
    if risco == "alto":
        return Decisao("perguntar", f"{nome}: ação de risco alto (mexe no sistema)", risco=risco)
    if lembrada == "livre":
        return Decisao("livre", padrao=chave, risco=risco)

    if cid == "escrita":
        caminho = caminho_do_arquivo(args)
        if modo == "livre" or (caminho and politica["pastas_livres"] and dentro_de(caminho, politica["pastas_livres"])):
            return Decisao("livre", padrao=chave)
        return Decisao("perguntar", f"{nome}: {caminho or 'arquivo'}", padrao=chave)
    if modo == "perguntar" and risco == "trivial" and politica["liberar_triviais"]:
        return Decisao("livre", padrao=chave, risco=risco)
    return Decisao(modo, nome if modo == "perguntar" else "", padrao=chave, risco=risco)


def resumo(ferramenta: str, args: dict, limite: int = 400) -> str:
    """Uma linha legível do que a ferramenta vai fazer, para o pedido e a atividade."""
    for chave in ("command", "code", "url", "query", "path", "file_path", "action", "goal", "prompt", "task"):
        valor = args.get(chave)
        if isinstance(valor, str) and valor.strip():
            texto = valor.strip()
            break
    else:
        texto = ", ".join(f"{k}={v}" for k, v in list(args.items())[:4]) if args else ""
    texto = " ".join(texto.split()) if "\n" not in texto else texto
    return texto if len(texto) <= limite else texto[:limite] + "…"
