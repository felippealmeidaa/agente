"""Rotas do painel de controle em /api/plugins/controle/, usadas pela página do Hermes Desktop.

Rodam dentro do processo do Hermes. O arquivo é importado sozinho, fora do pacote, então o pacote do
plugin (canal, política) é carregado pelo caminho.
"""

from __future__ import annotations

import asyncio
import importlib.util
import sys
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel


def _carregar_pacote():
    nome = "hermes_dashboard_plugin_controle_pkg"
    if nome in sys.modules:
        return sys.modules[nome]
    raiz = Path(__file__).resolve().parent.parent
    spec = importlib.util.spec_from_file_location(nome, raiz / "__init__.py", submodule_search_locations=[str(raiz)])
    modulo = importlib.util.module_from_spec(spec)
    sys.modules[nome] = modulo
    spec.loader.exec_module(modulo)
    return modulo


_pacote = _carregar_pacote()
canal = _pacote.canal
pol = _pacote.pol
router = APIRouter()


def _hoje() -> str:
    from datetime import datetime
    return datetime.now().strftime("%Y-%m-%d")


def _dia_valido(dia: Optional[str]) -> str:
    import re
    return dia if dia and re.fullmatch(r"\d{4}-\d{2}-\d{2}", dia) else _hoje()


def _ler_atividade(dia: str, limite: int = 500) -> list[dict[str, Any]]:
    import json
    caminho = canal.pasta() / "atividade" / f"{dia}.jsonl"
    try:
        linhas = caminho.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    eventos = []
    for linha in linhas[-limite:]:
        try:
            eventos.append(json.loads(linha))
        except ValueError:
            continue
    return eventos[::-1]


def _dias() -> list[str]:
    pasta = canal.pasta() / "atividade"
    if not pasta.exists():
        return []
    return sorted((p.stem for p in pasta.glob("*.jsonl")), reverse=True)


def _limite_dos_hooks() -> float:
    try:
        from hermes_cli.plugins import _resolve_hook_callback_timeout
        return float(_resolve_hook_callback_timeout())
    except Exception:
        return 30.0


class Politica(BaseModel):
    politica: dict[str, Any]


class Pausa(BaseModel):
    parado: bool


@router.get("/estado")
async def estado():
    def ler():
        return {
            "politica": canal.ler_politica(),
            "categorias": [{"id": cid, "nome": nome, "ferramentas": list(exatas), "prefixos": list(prefixos),
                            "padrao": padrao, "descricao": pol.DESCRICOES[cid]}
                           for cid, (nome, exatas, prefixos, padrao) in pol.CATEGORIAS.items()],
            "pasta": str(canal.pasta()),
            "limite_hooks": _limite_dos_hooks(),
            "hoje": _hoje(),
        }
    return await asyncio.to_thread(ler)


@router.post("/politica")
async def salvar(corpo: Politica):
    return await asyncio.to_thread(canal.salvar_politica, corpo.politica)


@router.post("/pausar")
async def pausar(corpo: Pausa):
    def mudar():
        atual = dict(canal.ler_politica())
        atual["parado"] = corpo.parado
        return canal.salvar_politica(atual)
    return await asyncio.to_thread(mudar)


@router.get("/atividade")
async def atividade(dia: Optional[str] = Query(None)):
    alvo = _dia_valido(dia)
    return await asyncio.to_thread(lambda: {"eventos": _ler_atividade(alvo), "dias": _dias(), "hoje": _hoje(), "dia": alvo})


@router.get("/integridade")
async def integridade(dia: Optional[str] = Query(None), ancora: int = Query(0, ge=0)):
    """Confere a cadeia do dia. Com `ancora=N`, devolve também o hash da linha N para a página comparar
    com o que ela guardou da última vez (detecta histórico reescrito com cadeia recalculada)."""
    alvo = _dia_valido(dia)
    caminho = canal.pasta() / "atividade" / f"{alvo}.jsonl"

    def conferir():
        r = canal.verificar(caminho)
        if ancora and r["ok"] and ancora <= r["linhas"]:
            r["hash_ancora"] = canal.hash_da_linha(caminho, ancora)
        return {**r, "dia": alvo}
    if ancora > 1_000_000:
        raise HTTPException(status_code=400, detail="Âncora inválida.")
    return await asyncio.to_thread(conferir)
