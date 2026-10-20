"""Painel de controle: cada ferramenta do agente passa pela política do app desktop antes de rodar.

- ``pre_tool_call`` decide (livre / perguntar ao app / bloqueado) com pausa, pasta protegida,
  vazamento por sessão, regras lembradas e risco;
- ``transform_tool_result`` marca a sessão quando aparece segredo ou dado pessoal e cerca conteúdo
  externo que parece prompt injection;
- ``post_tool_call`` registra a atividade (log encadeado por hash).

Erro aqui bloqueia a ferramenta: o Hermes trata exceção em ``pre_tool_call`` como bloqueio.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
from typing import Any

from . import canal
from . import politica as pol
from . import protecao

_MAX_SESSOES = 500
# (sessão, categoria) liberadas com "Permitir nesta sessão"; vale até o processo reiniciar
_liberados: set[tuple[str, str]] = set()
# Marcas de dado sensível que cada sessão já viu ("segredo", "pessoal")
_marcas: dict[str, set[str]] = {}
_trava = threading.Lock()


def _sessao(task_id: str, kwargs: dict) -> str:
    return str(kwargs.get("session_id") or task_id or "")


def _bloquear(mensagem: str) -> dict[str, str]:
    return {"action": "block", "message": f"Bloqueado pelo painel de controle: {mensagem}."}


def marcas_da_sessao(sessao: str) -> frozenset[str]:
    with _trava:
        return frozenset(_marcas.get(sessao, ()))


PREFIXO_REGRA = "controle:"


def chave_de_aprovacao(ferramenta: str, args: dict, decisao: pol.Decisao) -> str:
    """O grão do "sempre" da tela do Hermes. Ação comum: o padrão (ex. "terminal:git push").
    Risco alto, vazamento ou sem padrão: o comando exato, então "sempre" nunca vira carta branca."""
    if decisao.padrao and decisao.risco != "alto" and not decisao.vazamento:
        return PREFIXO_REGRA + decisao.padrao
    exato = hashlib.sha256(json.dumps(args, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()[:16]
    return f"{PREFIXO_REGRA}{ferramenta}:exato:{exato}"


def mensagem_de_aprovacao(ferramenta: str, decisao: pol.Decisao) -> str:
    partes = [f"Painel de controle: {decisao.motivo or pol.CATEGORIAS[pol.categoria(ferramenta)][0]}"]
    if decisao.risco == "alto":
        partes.append("RISCO ALTO, mexe no sistema; confira o comando inteiro")
    if decisao.vazamento:
        partes.append("POSSÍVEL VAZAMENTO")
    return ". ".join(partes)


def depois_da_aprovacao(command: str = "", description: str = "", pattern_key: str = "", session_key: str = "",
                        surface: str = "", choice: str = "", **kwargs: Any):
    """Registra no log encadeado o que o dono escolheu na tela de aprovação do Hermes."""
    if not pattern_key and not command:
        return
    nosso = str(pattern_key).startswith("plugin_rule:" + PREFIXO_REGRA)
    canal.registrar({"tipo": "aprovacao", "ferramenta": "aprovação",
                     "categoria": "outros", "sessao": str(session_key or ""), "processo": os.getpid(),
                     "resumo": (command or description)[:400], "decisao": str(choice or ""), "superficie": surface,
                     "origem": "controle" if nosso else "hermes",
                     "regra": str(pattern_key).removeprefix("plugin_rule:")})


def antes_da_ferramenta(tool_name: str, args: dict, task_id: str = "", **kwargs: Any):
    args = args if isinstance(args, dict) else {}
    sessao = _sessao(task_id, kwargs)
    regras = canal.ler_politica()
    decisao = pol.decidir(tool_name, args, regras, marcas_da_sessao(sessao), protegidas=[str(canal.pasta())])
    if decisao.modo == "livre":
        return None
    cid = pol.categoria(tool_name)
    evento = {"tipo": "decisao", "ferramenta": tool_name, "categoria": cid, "sessao": sessao,
              "resumo": pol.resumo(tool_name, args), "processo": os.getpid(), "risco": decisao.risco}
    if decisao.vazamento:
        evento["vazamento"] = True

    if decisao.modo == "bloqueado":
        canal.registrar({**evento, "decisao": "bloqueado", "motivo": decisao.motivo})
        return _bloquear(decisao.motivo)

    if regras["aprovar_em"] == "hermes":
        # A própria tela de aprovação do Hermes (chat do Desktop, terminal ou gateway de mensagens);
        # a escolha volta pelo hook post_approval_response
        canal.registrar({**evento, "decisao": "perguntado"})
        return {"action": "approve", "message": mensagem_de_aprovacao(tool_name, decisao),
                "rule_key": chave_de_aprovacao(tool_name, args, decisao)}

    # "Nesta sessão" não cobre risco alto nem a suspeita de vazamento
    if decisao.risco != "alto" and not decisao.vazamento:
        with _trava:
            if (sessao, cid) in _liberados:
                return None
    if not canal.app_aberto():
        canal.registrar({**evento, "decisao": "fechado"})
        return _bloquear("o app de controle está fechado e esta ação precisa de aprovação. "
                         "Peça para o dono abrir o app e tentar de novo")

    pedido = {"ferramenta": tool_name, "categoria": cid, "nome_categoria": pol.CATEGORIAS[cid][0],
              "motivo": decisao.motivo, "resumo": pol.resumo(tool_name, args, limite=4000), "sessao": sessao,
              "processo": os.getpid(), "risco": decisao.risco, "padrao": decisao.padrao,
              "vazamento": decisao.vazamento}
    resposta, nota = canal.pedir_aprovacao(pedido, canal.espera_maxima(regras["espera_segundos"]))
    canal.registrar({**evento, "decisao": resposta, **({"nota": nota} if nota else {})})
    if resposta == "sessao":
        if decisao.risco != "alto" and not decisao.vazamento:
            with _trava:
                _liberados.add((sessao, cid))
        return None
    if resposta == "once":
        return None
    if resposta == "negar":
        return _bloquear("o dono negou esta ação" + (f". Motivo: {nota}" if nota else ""))
    if resposta == "fechado":
        return _bloquear("o app de controle foi fechado antes de responder")
    return _bloquear("ninguém respondeu a tempo no app de controle")


def transformar_resultado(tool_name: str, args: dict | None = None, result: Any = "", task_id: str = "", **kwargs: Any):
    if not isinstance(result, str) or not result:
        return None
    sessao = _sessao(task_id, kwargs)
    novas = protecao.marcas(result)
    if novas:
        with _trava:
            if sessao not in _marcas and len(_marcas) >= _MAX_SESSOES:
                _marcas.pop(next(iter(_marcas)))
            antes = set(_marcas.get(sessao, ()))
            _marcas.setdefault(sessao, set()).update(novas)
        if not novas <= antes:
            canal.registrar({"tipo": "marca", "ferramenta": tool_name, "categoria": pol.categoria(tool_name),
                             "sessao": sessao, "marcas": sorted(novas), "processo": os.getpid(),
                             "resumo": "a sessão leu " + " e ".join(
                                 {"segredo": "um segredo", "pessoal": "dados pessoais"}[m] for m in sorted(novas))})
    if not protecao.eh_fonte_externa(tool_name) or not canal.ler_politica()["cercar_externo"]:
        return None
    suspeitas = protecao.suspeitas_de_injecao(result)
    if not suspeitas:
        return None
    canal.registrar({"tipo": "cercado", "ferramenta": tool_name, "categoria": pol.categoria(tool_name),
                     "sessao": sessao, "processo": os.getpid(), "resumo": " · ".join(suspeitas[:3])})
    return protecao.cercar(result)


def depois_da_ferramenta(tool_name: str, args: dict, result: Any = "", task_id: str = "",
                         duration_ms: int = 0, **kwargs: Any):
    ok = True
    try:
        dados = json.loads(result) if isinstance(result, str) else None
        ok = not (isinstance(dados, dict) and (dados.get("error") or dados.get("erro")))
    except (TypeError, ValueError):
        pass
    canal.registrar({
        "tipo": "ferramenta", "ferramenta": tool_name, "categoria": pol.categoria(tool_name),
        "sessao": _sessao(task_id, kwargs),
        "resumo": pol.resumo(tool_name, args if isinstance(args, dict) else {}),
        "duracao_ms": int(duration_ms or 0), "ok": ok, "processo": os.getpid(),
    })


def register(ctx):
    canal.limpar_orfaos()
    ctx.register_hook("pre_tool_call", antes_da_ferramenta)
    ctx.register_hook("transform_tool_result", transformar_resultado)
    ctx.register_hook("post_tool_call", depois_da_ferramenta)
    ctx.register_hook("post_approval_response", depois_da_aprovacao)
