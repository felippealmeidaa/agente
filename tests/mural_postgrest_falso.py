"""PostgREST falso em memória para testar o plugin do mural sem Supabase.

Cobre só o que ``plugins/mural/loja.py`` usa: filtros ``eq``/``in``, ``order``, ``limit``,
contagem e embed de ``mural_respostas``, ``Prefer: return=representation`` e a cascata do delete.
"""

from __future__ import annotations

import itertools
import json
import uuid
from datetime import datetime, timedelta, timezone, UTC

import httpx

CHAVE = "sb_secret_teste"
_inicio = datetime(2026, 10, 20, 12, 0, tzinfo=UTC)


class PostgrestFalso:
    def __init__(self, chave: str = CHAVE):
        self.chave = chave
        self.tabelas = {"mural_cartoes": [], "mural_respostas": []}
        self._relogio = itertools.count(1)
        self.pedidos: list[httpx.Request] = []

    def agora(self) -> str:
        return (_inicio + timedelta(seconds=next(self._relogio))).isoformat()

    @property
    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self._responder)

    # --- filtros --------------------------------------------------------------

    @staticmethod
    def _casa(linha: dict, coluna: str, condicao: str) -> bool:
        op, _, valor = condicao.partition(".")
        atual = linha.get(coluna)
        if isinstance(atual, bool):
            atual = "true" if atual else "false"
        if op == "eq":
            return str(atual) == valor
        if op == "in":
            return str(atual) in valor.strip("()").split(",")
        raise AssertionError(f"operador não suportado: {op}")

    def _filtrar(self, tabela: str, params: httpx.QueryParams) -> list[dict]:
        reservados = {"select", "order", "limit"}
        linhas = self.tabelas[tabela]
        for coluna, condicao in params.multi_items():
            if coluna in reservados or "." in coluna:
                continue
            linhas = [l for l in linhas if self._casa(l, coluna, condicao)]
        return linhas

    def _com_select(self, linha: dict, select: str) -> dict:
        if select == "id":
            return {"id": linha["id"]}
        saida = dict(linha)
        respostas = [r for r in self.tabelas["mural_respostas"] if r["cartao_id"] == linha["id"]]
        if "mural_respostas(count)" in select:
            saida["mural_respostas"] = [{"count": len(respostas)}]
        elif "mural_respostas(*)" in select:
            saida["mural_respostas"] = sorted((dict(r) for r in respostas), key=lambda r: r["criado_em"])
        return saida

    # --- HTTP -----------------------------------------------------------------

    def _responder(self, pedido: httpx.Request) -> httpx.Response:
        self.pedidos.append(pedido)
        if pedido.headers.get("apikey") != self.chave:
            return httpx.Response(401, json={"message": "Invalid API key"})
        tabela = pedido.url.path.rsplit("/", 1)[-1]
        if tabela not in self.tabelas:
            return httpx.Response(404, json={"message": f"relation public.{tabela} does not exist"})
        params = pedido.url.params
        representar = "return=representation" in pedido.headers.get("prefer", "")

        if pedido.method == "GET":
            linhas = list(self._filtrar(tabela, params))
            for campo in reversed((params.get("order") or "").split(",")):
                if campo:
                    nome, _, direcao = campo.partition(".")
                    linhas.sort(key=lambda l: l[nome], reverse=direcao == "desc")
            if params.get("limit"):
                linhas = linhas[: int(params["limit"])]
            return httpx.Response(200, json=[self._com_select(l, params.get("select", "*")) for l in linhas])

        if pedido.method == "POST":
            corpo = json.loads(pedido.content)
            agora = self.agora()
            if tabela == "mural_cartoes":
                linha = {"id": str(uuid.uuid4()), "criado_em": agora, "atualizado_em": agora, "status": "novo",
                         "fixado": False, "autor": "humano", "tipo": "passagem", "conteudo": "", **corpo}
            else:
                if not any(c["id"] == corpo["cartao_id"] for c in self.tabelas["mural_cartoes"]):
                    return httpx.Response(409, json={"message": "foreign key violation"})
                linha = {"id": str(uuid.uuid4()), "criado_em": agora, "autor": "humano", **corpo}
                for c in self.tabelas["mural_cartoes"]:  # o gatilho mural_respostas_tocar
                    if c["id"] == corpo["cartao_id"]:
                        c["atualizado_em"] = agora
            self.tabelas[tabela].append(linha)
            return httpx.Response(201, json=[linha] if representar else None)

        if pedido.method == "PATCH":
            corpo = json.loads(pedido.content)
            alvos = self._filtrar(tabela, params)
            for linha in alvos:
                linha.update(corpo)
                if "atualizado_em" in corpo:
                    linha["atualizado_em"] = self.agora()
            return httpx.Response(200, json=[dict(l) for l in alvos]) if representar else httpx.Response(204)

        if pedido.method == "DELETE":
            alvos = self._filtrar(tabela, params)
            ids = {l["id"] for l in alvos}
            self.tabelas[tabela] = [l for l in self.tabelas[tabela] if l["id"] not in ids]
            if tabela == "mural_cartoes":
                self.tabelas["mural_respostas"] = [r for r in self.tabelas["mural_respostas"] if r["cartao_id"] not in ids]
            return httpx.Response(200, json=[dict(l) for l in alvos]) if representar else httpx.Response(204)

        return httpx.Response(405)
