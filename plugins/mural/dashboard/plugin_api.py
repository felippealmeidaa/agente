"""Rotas do Mural no painel, montadas em /api/plugins/mural/.

A chave do Supabase fica no servidor: o navegador só fala com estas rotas. Cada chamada ao
Supabase é síncrona e roda fora do event loop (``asyncio.to_thread``).
"""

from __future__ import annotations

import asyncio
import importlib.util
import sys
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel


def _carregar_loja():
    # O painel importa este arquivo sozinho, fora do pacote do plugin: a loja vem pelo caminho
    nome = "hermes_dashboard_plugin_mural_loja"
    if nome in sys.modules:
        return sys.modules[nome]
    spec = importlib.util.spec_from_file_location(nome, Path(__file__).resolve().parent.parent / "loja.py")
    modulo = importlib.util.module_from_spec(spec)
    sys.modules[nome] = modulo
    spec.loader.exec_module(modulo)
    return modulo


loja = _carregar_loja()
router = APIRouter()


async def _rodar(funcao, *args: Any, **kwargs: Any) -> Any:
    def chamada():
        return funcao(loja.do_ambiente(), *args, **kwargs)
    try:
        return await asyncio.to_thread(chamada)
    except loja.ErroMural as erro:
        raise HTTPException(status_code=erro.status, detail=erro.mensagem) from erro


class NovoCartao(BaseModel):
    titulo: str
    conteudo: str = ""
    tipo: str = "passagem"


class Mudanca(BaseModel):
    status: Optional[str] = None
    fixado: Optional[bool] = None


class NovaResposta(BaseModel):
    texto: str


@router.get("/estado")
async def estado():
    def ler():
        try:
            mural = loja.do_ambiente()
        except loja.MuralNaoConfigurado as erro:
            return {"configurado": False, "faltando": erro.faltando}
        try:
            return {"configurado": True, "eu": mural.eu, "parceiro": mural.parceiro, "novos": mural.contar_novos()}
        except loja.ErroMural as erro:
            return {"configurado": True, "eu": mural.eu, "parceiro": mural.parceiro, "erro": erro.mensagem}
    return await asyncio.to_thread(ler)


@router.get("/cartoes")
async def listar(caixa: str = Query("entrada"), filtro: str = Query("abertos")):
    cartoes = await _rodar(lambda m: m.listar(caixa, filtro))
    return {"cartoes": cartoes}


@router.post("/cartoes")
async def criar(corpo: NovoCartao):
    return await _rodar(lambda m: m.criar(corpo.titulo, corpo.conteudo, corpo.tipo, autor="humano"))


@router.get("/cartoes/{cartao_id}")
async def abrir(cartao_id: str):
    return await _rodar(lambda m: m.abrir(cartao_id))


@router.patch("/cartoes/{cartao_id}")
async def atualizar(cartao_id: str, corpo: Mudanca):
    return await _rodar(lambda m: m.atualizar(cartao_id, status=corpo.status, fixado=corpo.fixado))


@router.delete("/cartoes/{cartao_id}")
async def excluir(cartao_id: str):
    await _rodar(lambda m: m.excluir(cartao_id))
    return {"ok": True}


@router.post("/cartoes/{cartao_id}/respostas")
async def responder(cartao_id: str, corpo: NovaResposta):
    return await _rodar(lambda m: m.responder(cartao_id, corpo.texto, autor="humano"))
