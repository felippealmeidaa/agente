"""Ferramentas do agente para o mural: ler as passagens, escrever uma nova e responder/fechar."""

from __future__ import annotations

import json
from typing import Any

from . import loja

LER = {
    "name": "mural_ler",
    "description": (
        "Lê o mural de passagem compartilhado com o agente do parceiro (o outro dono deste projeto). "
        "Sem 'id', lista os cartões; com 'id', abre um cartão com as respostas e o marca como lido. "
        "Consulte a caixa 'entrada' ao começar uma tarefa: o parceiro deixa ali contexto, decisões e pedidos."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "id": {"type": "string", "description": "Id do cartão para abrir por inteiro."},
            "caixa": {"type": "string", "enum": list(loja.CAIXAS),
                      "description": "entrada (para mim), enviados (que eu escrevi) ou todos. Padrão: entrada."},
            "filtro": {"type": "string", "enum": list(loja.FILTROS),
                       "description": "abertos (novo/lido), feitos ou tudo. Padrão: abertos."},
        },
    },
}

ESCREVER = {
    "name": "mural_escrever",
    "description": (
        "Deixa um cartão no mural para o parceiro e o agente dele. Use para passar contexto que o outro "
        "lado precisa: o que foi feito, decisões, onde parou, comandos, caminhos de arquivos e próximos passos. "
        "Escreva em pt-BR, completo o bastante para ser lido sem esta conversa. Nunca inclua senhas ou chaves."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "titulo": {"type": "string", "description": "Resumo em uma linha (até 200 caracteres)."},
            "conteudo": {"type": "string", "description": "Corpo em Markdown."},
            "tipo": {"type": "string", "enum": list(loja.TIPOS),
                     "description": "passagem (entrega de trabalho), pergunta (precisa de resposta) ou aviso."},
        },
        "required": ["titulo", "conteudo"],
    },
}

RESPONDER = {
    "name": "mural_responder",
    "description": (
        "Responde a um cartão do mural e/ou muda o status dele. Marque 'feito' quando o pedido do cartão "
        "estiver resolvido; use 'texto' para responder perguntas ou dizer o que foi feito."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "id": {"type": "string", "description": "Id do cartão."},
            "texto": {"type": "string", "description": "Resposta em Markdown (opcional se só mudar o status)."},
            "status": {"type": "string", "enum": list(loja.STATUS), "description": "Novo status (opcional)."},
        },
        "required": ["id"],
    },
}


def _resultado(funcao):
    def handler(args: dict, **kwargs: Any) -> str:
        try:
            return json.dumps(funcao(loja.do_ambiente(), args or {}), ensure_ascii=False, default=str)
        except loja.ErroMural as erro:
            return json.dumps({"erro": erro.mensagem}, ensure_ascii=False)
        except Exception as erro:  # a ferramenta nunca levanta
            return json.dumps({"erro": f"Falha inesperada no mural: {erro}"}, ensure_ascii=False)
    return handler


def _ler(mural: loja.Mural, args: dict) -> dict:
    if args.get("id"):
        return {"eu": mural.eu, "cartao": mural.abrir(args["id"])}
    cartoes = mural.listar(args.get("caixa") or "entrada", args.get("filtro") or "abertos", limite=30)
    # Na lista vai só o começo do conteúdo; o cartão inteiro sai com 'id'
    for c in cartoes:
        if len(c.get("conteudo") or "") > 400:
            c["conteudo"] = c["conteudo"][:400] + "…"
    return {"eu": mural.eu, "parceiro": mural.parceiro, "cartoes": cartoes}


def _escrever(mural: loja.Mural, args: dict) -> dict:
    cartao = mural.criar(args.get("titulo"), args.get("conteudo"), args.get("tipo") or "passagem", autor="agente")
    return {"ok": True, "id": cartao["id"], "para": cartao["para"]}


def _responder(mural: loja.Mural, args: dict) -> dict:
    if not args.get("texto") and not args.get("status"):
        raise loja.ErroMural("Informe 'texto', 'status' ou os dois.")
    feito: dict[str, Any] = {"ok": True}
    if args.get("texto"):
        feito["resposta"] = mural.responder(args.get("id"), args["texto"], autor="agente")["id"]
    if args.get("status"):
        feito["status"] = mural.atualizar(args.get("id"), status=args["status"])["status"]
    return feito


ler = _resultado(_ler)
escrever = _resultado(_escrever)
responder = _resultado(_responder)
