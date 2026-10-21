"""Mural de passagem — acesso ao Supabase (PostgREST) compartilhado pelos dois PCs.

Tudo que lê ou grava cartões passa por aqui: as ferramentas do agente (``ferramentas.py``) e as
rotas do painel (``dashboard/plugin_api.py``). As chamadas são síncronas; o painel as roda fora
do event loop com ``asyncio.to_thread``.
"""

from __future__ import annotations

import os
import re
from datetime import datetime, timezone, UTC
from typing import Any, Optional

import httpx

TIPOS = ("passagem", "pergunta", "aviso")
STATUS = ("novo", "lido", "feito")
AUTORES = ("humano", "agente")
CAIXAS = ("entrada", "enviados", "todos")
FILTROS = ("abertos", "feitos", "tudo")

LIMITE_TITULO = 200
LIMITE_CONTEUDO = 50_000
LIMITE_RESPOSTA = 20_000

_PESSOA = re.compile(r"^[a-z0-9][a-z0-9_-]{0,39}$")
_UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


class ErroMural(Exception):
    """Erro com mensagem pronta para mostrar (painel) ou devolver ao modelo (ferramenta)."""

    def __init__(self, mensagem: str, status: int = 400):
        super().__init__(mensagem)
        self.mensagem = mensagem
        self.status = status


class MuralNaoConfigurado(ErroMural):
    def __init__(self, faltando: list[str]):
        super().__init__("Mural não configurado: falta " + ", ".join(faltando) + ".", 503)
        self.faltando = faltando


def _segredo(nome: str) -> Optional[str]:
    try:
        from agent.secret_scope import get_secret
    except Exception:  # fora do Hermes (testes)
        return os.environ.get(nome)
    return get_secret(nome)


def _ajustes() -> dict[str, Any]:
    """``plugins.entries.mural.settings`` do config.yaml do perfil ativo."""
    try:
        from hermes_cli.config import load_config_readonly
    except Exception:
        return {}
    cfg = load_config_readonly() or {}
    entrada = ((cfg.get("plugins") or {}).get("entries") or {}).get("mural") or {}
    return entrada.get("settings") or {}


def pessoa_valida(nome: Any) -> Optional[str]:
    valor = str(nome or "").strip().lower()
    return valor if _PESSOA.match(valor) else None


def do_ambiente(transport: Optional[httpx.BaseTransport] = None) -> Mural:
    """Monta o mural com a chave do .env e as pessoas do config.yaml; avisa o que faltar."""
    ajustes = _ajustes()
    url = (_segredo("MURAL_SUPABASE_URL") or "").strip().rstrip("/")
    chave = (_segredo("MURAL_SUPABASE_CHAVE") or "").strip()
    eu = pessoa_valida(ajustes.get("eu") or os.environ.get("MURAL_EU"))
    parceiro = pessoa_valida(ajustes.get("parceiro") or os.environ.get("MURAL_PARCEIRO"))
    faltando = [nome for nome, valor in (
        ("MURAL_SUPABASE_URL no .env", url), ("MURAL_SUPABASE_CHAVE no .env", chave),
        ("plugins.entries.mural.settings.eu", eu), ("plugins.entries.mural.settings.parceiro", parceiro),
    ) if not valor]
    if faltando:
        raise MuralNaoConfigurado(faltando)
    return Mural(url, chave, eu, parceiro, transport=transport)


def _texto(valor: Any, limite: int, campo: str, obrigatorio: bool = True) -> str:
    texto = str(valor or "").strip()
    if obrigatorio and not texto:
        raise ErroMural(f"Preencha {campo}.")
    if len(texto) > limite:
        raise ErroMural(f"{campo.capitalize()} passou de {limite} caracteres.")
    return texto


def _id(valor: Any) -> str:
    texto = str(valor or "").strip().lower()
    if not _UUID.match(texto):
        raise ErroMural("Cartão inválido.", 404)
    return texto


class Mural:
    def __init__(self, url: str, chave: str, eu: str, parceiro: str,
                 transport: Optional[httpx.BaseTransport] = None):
        if eu == parceiro:
            raise ErroMural("Você e o parceiro precisam ter nomes diferentes no config.yaml.")
        self.eu = eu
        self.parceiro = parceiro
        cabecalhos = {"apikey": chave, "Content-Type": "application/json"}
        # Chaves antigas (JWT) também vão no Authorization; as novas sb_secret_ só no apikey
        if chave.startswith("eyJ"):
            cabecalhos["Authorization"] = f"Bearer {chave}"
        self._http = httpx.Client(base_url=f"{url}/rest/v1", headers=cabecalhos,
                                  timeout=15.0, transport=transport)

    # --- HTTP ---------------------------------------------------------------

    def _pedir(self, metodo: str, caminho: str, **kwargs: Any) -> Any:
        try:
            resposta = self._http.request(metodo, caminho, **kwargs)
        except httpx.HTTPError as erro:
            raise ErroMural(f"Sem conexão com o Supabase do mural ({erro.__class__.__name__}).", 502) from erro
        if resposta.status_code in (401, 403):
            raise ErroMural("O Supabase recusou a chave do mural. Confira MURAL_SUPABASE_CHAVE.", 502)
        if resposta.status_code == 404 and "mural_" in resposta.text:
            raise ErroMural("As tabelas do mural não existem. Rode o supabase.sql no projeto.", 502)
        if resposta.status_code >= 400:
            raise ErroMural(f"O Supabase respondeu {resposta.status_code}.", 502)
        return resposta.json() if resposta.content else None

    # --- Leitura ------------------------------------------------------------

    def listar(self, caixa: str = "entrada", filtro: str = "abertos", limite: int = 100) -> list[dict]:
        if caixa not in CAIXAS:
            raise ErroMural("Caixa inválida.")
        if filtro not in FILTROS:
            raise ErroMural("Filtro inválido.")
        params: dict[str, Any] = {
            "select": "*,mural_respostas(count)",
            "order": "fixado.desc,atualizado_em.desc",
            "limit": str(max(1, min(int(limite), 200))),
        }
        if caixa == "entrada":
            params["para"] = f"eq.{self.eu}"
        elif caixa == "enviados":
            params["de"] = f"eq.{self.eu}"
        if filtro == "abertos":
            params["status"] = "in.(novo,lido)"
        elif filtro == "feitos":
            params["status"] = "eq.feito"
        return [_resumo(c) for c in self._pedir("GET", "/mural_cartoes", params=params) or []]

    def contar_novos(self) -> int:
        linhas = self._pedir("GET", "/mural_cartoes", params={
            "select": "id", "para": f"eq.{self.eu}", "status": "eq.novo", "limit": "200"})
        return len(linhas or [])

    def abrir(self, cartao_id: str, marcar_lido: bool = True) -> dict:
        cid = _id(cartao_id)
        linhas = self._pedir("GET", "/mural_cartoes", params={
            "select": "*,mural_respostas(*)", "id": f"eq.{cid}",
            "mural_respostas.order": "criado_em.asc"})
        if not linhas:
            raise ErroMural("Cartão não encontrado.", 404)
        cartao = linhas[0]
        respostas = cartao.pop("mural_respostas", None) or []
        # Quem recebe abriu: o remetente passa a ver que foi lido
        if marcar_lido and cartao["para"] == self.eu and cartao["status"] == "novo":
            self._pedir("PATCH", "/mural_cartoes", params={"id": f"eq.{cid}", "status": "eq.novo"},
                        json={"status": "lido"})
            cartao["status"] = "lido"
        cartao["respostas"] = respostas
        return cartao

    # --- Escrita ------------------------------------------------------------

    def criar(self, titulo: Any, conteudo: Any = "", tipo: Any = "passagem", autor: str = "humano") -> dict:
        tipo = str(tipo or "passagem")
        if tipo not in TIPOS:
            raise ErroMural("Tipo inválido: use passagem, pergunta ou aviso.")
        if autor not in AUTORES:
            raise ErroMural("Autor inválido.")
        corpo = {
            "de": self.eu, "para": self.parceiro, "autor": autor, "tipo": tipo,
            "titulo": _texto(titulo, LIMITE_TITULO, "o título"),
            "conteudo": _texto(conteudo, LIMITE_CONTEUDO, "o conteúdo", obrigatorio=False),
        }
        linhas = self._pedir("POST", "/mural_cartoes", json=corpo, headers={"Prefer": "return=representation"})
        return _resumo(linhas[0])

    def atualizar(self, cartao_id: str, status: Any = None, fixado: Any = None) -> dict:
        cid = _id(cartao_id)
        mudancas: dict[str, Any] = {}
        if status is not None:
            if status not in STATUS:
                raise ErroMural("Status inválido: use novo, lido ou feito.")
            mudancas["status"] = status
        if fixado is not None:
            mudancas["fixado"] = bool(fixado)
        if not mudancas:
            raise ErroMural("Nada para mudar.")
        mudancas["atualizado_em"] = datetime.now(UTC).isoformat()
        linhas = self._pedir("PATCH", "/mural_cartoes", params={"id": f"eq.{cid}"},
                             json=mudancas, headers={"Prefer": "return=representation"})
        if not linhas:
            raise ErroMural("Cartão não encontrado.", 404)
        return _resumo(linhas[0])

    def responder(self, cartao_id: str, texto: Any, autor: str = "humano") -> dict:
        cid = _id(cartao_id)
        if autor not in AUTORES:
            raise ErroMural("Autor inválido.")
        corpo = {"cartao_id": cid, "de": self.eu, "autor": autor,
                 "texto": _texto(texto, LIMITE_RESPOSTA, "a resposta")}
        linhas = self._pedir("POST", "/mural_respostas", json=corpo, headers={"Prefer": "return=representation"})
        return linhas[0]

    def excluir(self, cartao_id: str) -> None:
        cid = _id(cartao_id)
        # Só quem escreveu apaga
        linhas = self._pedir("DELETE", "/mural_cartoes", params={"id": f"eq.{cid}", "de": f"eq.{self.eu}"},
                             headers={"Prefer": "return=representation"})
        if not linhas:
            raise ErroMural("Só quem escreveu o cartão pode excluir.", 403)


def _resumo(cartao: dict) -> dict:
    contagem = cartao.pop("mural_respostas", None)
    if isinstance(contagem, list) and contagem and "count" in contagem[0]:
        cartao["respostas"] = contagem[0]["count"]
    else:
        cartao.setdefault("respostas", 0)
    return cartao
