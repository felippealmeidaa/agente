"""Mural de passagem entre dois agentes Hermes, cada um num PC, via Supabase compartilhado."""

from __future__ import annotations

from . import ferramentas, loja


def _configurado() -> bool:
    try:
        loja.do_ambiente()
    except loja.ErroMural:
        return False
    return True


def register(ctx):
    for schema, handler in ((ferramentas.LER, ferramentas.ler),
                            (ferramentas.ESCREVER, ferramentas.escrever),
                            (ferramentas.RESPONDER, ferramentas.responder)):
        ctx.register_tool(name=schema["name"], toolset="mural", schema=schema,
                          handler=handler, check_fn=_configurado)
