"""Canal em arquivos entre o plugin (dentro do Hermes) e o app de controle.

Pasta: ``HERMES_CONTROLE_DIR``; senão ``<HERMES_HOME>/controle`` quando um Hermes isolado está em uso;
senão ``%LOCALAPPDATA%\\hermes-controle`` (``~/.hermes-controle`` fora do Windows). É a mesma para todos
os perfis de um Hermes, então um painel controla todos.

- ``politica.json``   o app grava; o plugin lê a cada chamada (com cache por mtime)
- ``vivo.json``       o app renova a cada 2 s; sem ele, o que pede aprovação é bloqueado
- ``pedidos/<id>.json`` e ``respostas/<id>.json``  aprovação: o plugin pede e espera a resposta
- ``atividade/AAAA-MM-DD.jsonl``  uma linha por chamada de ferramenta

Toda gravação é atômica (arquivo temporário + ``os.replace``).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

from . import politica as pol

VIVO_SEGUNDOS = 10
_cache: dict[str, Any] = {"mtime": None, "politica": None}
_trava = threading.Lock()


def pasta() -> Path:
    definida = os.environ.get("HERMES_CONTROLE_DIR", "").strip()
    if definida:
        return Path(definida)
    # Um Hermes isolado (testes, ambiente de desenvolvimento) tem o seu próprio controle
    isolado = os.environ.get("HERMES_HOME", "").strip()
    if isolado:
        return Path(os.path.expanduser(os.path.expandvars(isolado))) / "controle"
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / "hermes-controle"
    return Path.home() / ".hermes-controle"


def agora_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds")


def gravar_json(caminho: Path, dados: Any) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    temp = caminho.with_name(f".{caminho.name}.{uuid.uuid4().hex}.tmp")
    temp.write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temp, caminho)


def ler_json(caminho: Path) -> Any:
    try:
        return json.loads(caminho.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def ler_politica() -> dict[str, Any]:
    caminho = pasta() / "politica.json"
    try:
        mtime = caminho.stat().st_mtime_ns
    except OSError:
        return pol.politica_padrao()
    with _trava:
        if _cache["mtime"] != mtime or _cache["politica"] is None:
            bruto = ler_json(caminho)
            # Arquivo ilegível no meio de uma gravação: mantém a última política boa
            if bruto is None and _cache["politica"] is not None:
                return _cache["politica"]
            _cache["politica"] = pol.normalizar(bruto)
            _cache["mtime"] = mtime
        return _cache["politica"]


def salvar_politica(politica: Any) -> dict[str, Any]:
    """Grava a política já normalizada (o que a página do Desktop ou o app mandar)."""
    limpa = pol.normalizar(politica)
    gravar_json(pasta() / "politica.json", limpa)
    with _trava:
        _cache.update(mtime=None, politica=None)
    return limpa


def app_aberto() -> bool:
    vivo = ler_json(pasta() / "vivo.json")
    try:
        return time.time() - float(vivo["ts"]) <= VIVO_SEGUNDOS
    except (TypeError, KeyError, ValueError):
        return False


HASH_ZERO = "0" * 64
_SUFIXO_HASH = re.compile(r',"hash":"([0-9a-f]{64})"\}$')


def serializar(evento: dict[str, Any]) -> str:
    """Forma canônica da linha (chaves ordenadas, sem espaços): é sobre ela que o hash é calculado."""
    return json.dumps(evento, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def encadear(anterior: str, linha_sem_hash: str) -> str:
    return hashlib.sha256((anterior + "\n" + linha_sem_hash).encode("utf-8")).hexdigest()


def ultimo_hash(caminho: Path) -> str:
    """Hash da última linha do arquivo (lendo só o fim); HASH_ZERO num arquivo novo ou sem cadeia."""
    try:
        with caminho.open("rb") as arquivo:
            arquivo.seek(0, os.SEEK_END)
            tamanho = arquivo.tell()
            arquivo.seek(max(0, tamanho - 65536))
            linhas = arquivo.read().decode("utf-8", "replace").rstrip("\n").split("\n")
    except OSError:
        return HASH_ZERO
    ultima = linhas[-1].rstrip("\r") if linhas else ""
    achado = _SUFIXO_HASH.search(ultima) if ultima else None
    return achado.group(1) if achado else HASH_ZERO


class _TravaDeArquivo:
    """Trava entre processos por arquivo exclusivo; uma trava largada há mais de 10 s é removida."""

    def __init__(self, caminho: Path, espera: float = 3.0):
        self.caminho = caminho
        self.espera = espera
        self.fd: int | None = None

    def __enter__(self):
        limite = time.monotonic() + self.espera
        while True:
            try:
                self.fd = os.open(self.caminho, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                return self
            except FileExistsError:
                try:
                    if time.time() - self.caminho.stat().st_mtime > 10:
                        self.caminho.unlink()
                        continue
                except OSError:
                    pass
                if time.monotonic() > limite:
                    raise TimeoutError(f"trava ocupada: {self.caminho}")
                time.sleep(0.01)

    def __exit__(self, *exc):
        if self.fd is not None:
            os.close(self.fd)
        try:
            self.caminho.unlink()
        except OSError:
            pass


def registrar(evento: dict[str, Any]) -> None:
    """Acrescenta uma linha encadeada ao log do dia: cada linha leva o hash da anterior, então editar
    ou apagar o histórico fica visível no app. Falha de disco nunca derruba a ferramenta."""
    try:
        destino = pasta() / "atividade" / (datetime.now().strftime("%Y-%m-%d") + ".jsonl")
        destino.parent.mkdir(parents=True, exist_ok=True)
        corpo = serializar({"ts": agora_iso(), **evento})
        with _trava, _TravaDeArquivo(destino.with_name(destino.name + ".trava")):
            elo = encadear(ultimo_hash(destino), corpo)
            with destino.open("a", encoding="utf-8", newline="\n") as arquivo:
                arquivo.write(corpo[:-1] + f',"hash":"{elo}"}}' + "\n")
    except (OSError, TimeoutError):
        pass


def verificar(caminho: Path) -> dict[str, Any]:
    """Confere a cadeia de um arquivo do log: {'ok', 'linhas', 'quebra' (nº da 1ª linha errada), 'ultimo'}."""
    anterior = HASH_ZERO
    try:
        texto = caminho.read_text(encoding="utf-8")
    except OSError:
        return {"ok": True, "linhas": 0, "quebra": None, "ultimo": HASH_ZERO}
    linhas = [l for l in texto.split("\n") if l.strip()]
    for numero, linha in enumerate(linhas, start=1):
        linha = linha.rstrip("\r")
        achado = _SUFIXO_HASH.search(linha)
        if not achado or encadear(anterior, linha[: achado.start()] + "}") != achado.group(1):
            return {"ok": False, "linhas": len(linhas), "quebra": numero, "ultimo": anterior}
        anterior = achado.group(1)
    return {"ok": True, "linhas": len(linhas), "quebra": None, "ultimo": anterior}


def hash_da_linha(caminho: Path, numero: int) -> str | None:
    """Hash guardado na linha N (1 = primeira) do log, ou None."""
    try:
        with caminho.open(encoding="utf-8") as arquivo:
            for atual, linha in enumerate((l for l in arquivo if l.strip()), start=1):
                if atual == numero:
                    achado = _SUFIXO_HASH.search(linha.rstrip())
                    return achado.group(1) if achado else None
    except OSError:
        pass
    return None


def pedir_aprovacao(pedido: dict[str, Any], espera: float,
                    dormir: Callable[[float], None] = time.sleep) -> tuple[str, str]:
    """Grava o pedido e espera a resposta do app: ('once'|'sessao'|'negar'|'tempo'|'fechado', nota)."""
    pid = uuid.uuid4().hex
    base = pasta()
    arquivo_pedido = base / "pedidos" / f"{pid}.json"
    arquivo_resposta = base / "respostas" / f"{pid}.json"
    gravar_json(arquivo_pedido, {"id": pid, "criado_em": agora_iso(), "expira_em": time.time() + espera, **pedido})
    limite = time.monotonic() + espera
    try:
        while time.monotonic() < limite:
            resposta = ler_json(arquivo_resposta)
            if isinstance(resposta, dict) and resposta.get("decisao") in ("once", "sessao", "negar"):
                return resposta["decisao"], str(resposta.get("nota") or "")[:500]
            if not app_aberto():
                return "fechado", ""
            dormir(0.25)
        return "tempo", ""
    finally:
        for caminho in (arquivo_pedido, arquivo_resposta):
            try:
                caminho.unlink()
            except OSError:
                pass


def espera_maxima(desejada: float) -> float:
    """Não passa do timeout dos hooks do Hermes, senão ele bloqueia antes de o app responder."""
    try:
        from hermes_cli.plugins import _resolve_hook_callback_timeout
        limite = float(_resolve_hook_callback_timeout())
    except Exception:
        limite = 30.0
    if limite <= 0:
        return desejada
    return max(1.0, min(desejada, limite - 3.0))


def limpar_orfaos(idade: float = 3600) -> None:
    """Pedidos de processos que morreram no meio da espera."""
    for sub in ("pedidos", "respostas"):
        for caminho in (pasta() / sub).glob("*.json"):
            try:
                if time.time() - caminho.stat().st_mtime > idade:
                    caminho.unlink()
            except OSError:
                pass

