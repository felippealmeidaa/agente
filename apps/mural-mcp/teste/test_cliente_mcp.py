"""Fluxo completo com o SDK MCP oficial em Python (o mesmo que o Hermes usa): descoberta, registro
dinâmico, login (GitHub falso do teste/local.ts), PKCE, token, ferramentas e renovação.

    npx deno run --allow-net --allow-env teste/local.ts      # em outro terminal
    python -m pytest teste/test_cliente_mcp.py
"""

from __future__ import annotations

import json
import os
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest

mcp = pytest.importorskip("mcp")
httpx2 = pytest.importorskip("httpx2")
from mcp.client.auth import OAuthClientProvider, TokenStorage
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.shared.auth import AuthorizationCodeResult, OAuthClientMetadata

PORTA = os.environ.get("PORTA", "8794")
RAIZ = f"http://127.0.0.1:{PORTA}"
URL = f"{RAIZ}/functions/v1/mural-mcp"
RETORNO = "http://127.0.0.1:53999/callback"

pytestmark = pytest.mark.anyio


def _provedor_do_hermes():
    """A classe que o `hermes mcp login` usa (SDK + checagens de emissor do Hermes), se o repo estiver à mão."""
    import sys
    from pathlib import Path
    raiz = Path(__file__).resolve().parents[3]
    if not (raiz / "tools" / "mcp_oauth_provider.py").exists():
        return None
    sys.path.insert(0, str(raiz))
    try:
        from tools.mcp_oauth_provider import HermesProviderMixin
    except Exception:
        return None
    import logging
    return type("HermesOAuthClientProvider", (HermesProviderMixin, OAuthClientProvider), {"_hermes_logger": logging.getLogger("teste")})


CLASSE_PROVEDOR = _provedor_do_hermes() or OAuthClientProvider


def test_usa_o_provedor_do_hermes():
    assert CLASSE_PROVEDOR is not OAuthClientProvider, "rode com o repo do Hermes e as dependências do tools/mcp_oauth_provider"


@pytest.fixture
def anyio_backend():
    return "asyncio"


def servidor_no_ar() -> bool:
    try:
        return httpx.get(f"{URL}/.well-known/oauth-protected-resource", timeout=2).status_code == 200
    except httpx.HTTPError:
        return False


if not servidor_no_ar():
    pytest.skip("suba o teste/local.ts antes", allow_module_level=True)


class Memoria(TokenStorage):
    def __init__(self):
        self.tokens = None
        self.cliente = None

    async def get_tokens(self):
        return self.tokens

    async def set_tokens(self, tokens):
        self.tokens = tokens

    async def get_client_info(self):
        return self.cliente

    async def set_client_info(self, client_info):
        self.cliente = client_info


def provedor(login: str, guardado: Memoria):
    httpx.post(f"{RAIZ}/__teste/login", json={"login": login})
    capturado: dict = {}

    async def abrir_navegador(url: str) -> None:
        # Faz o papel do navegador: segue /authorize -> "GitHub" -> volta ao redirect do cliente
        alvo = url
        async with httpx.AsyncClient(follow_redirects=False) as navegador:
            for _ in range(5):
                r = await navegador.get(alvo)
                if r.status_code != 302:
                    capturado["erro"] = (r.status_code, r.text)
                    return
                alvo = r.headers["location"]
                if alvo.startswith(RETORNO):
                    capturado.update({k: v[0] for k, v in parse_qs(urlsplit(alvo).query).items()})
                    return

    async def receber_codigo() -> AuthorizationCodeResult:
        assert "code" in capturado, capturado
        return AuthorizationCodeResult(code=capturado["code"], state=capturado.get("state"))

    meta = OAuthClientMetadata(client_name="Hermes Agent", redirect_uris=[RETORNO], grant_types=["authorization_code", "refresh_token"],
                               response_types=["code"], token_endpoint_auth_method="none")
    return CLASSE_PROVEDOR(server_url=URL, client_metadata=meta, storage=guardado,
                           redirect_handler=abrir_navegador, callback_handler=receber_codigo), capturado


async def sessao(login: str, guardado: Memoria | None = None):
    guardado = guardado or Memoria()
    auth, capturado = provedor(login, guardado)
    cliente = httpx2.AsyncClient(auth=auth, timeout=10)
    return cliente, guardado, capturado


async def usar(login: str, passos, guardado: Memoria | None = None):
    cliente, guardado, capturado = await sessao(login, guardado)
    async with cliente:
        async with streamable_http_client(URL, http_client=cliente) as streams:
            leitura, escrita = streams[0], streams[1]
            async with ClientSession(leitura, escrita) as s:
                info = await s.initialize()
                resultado = await passos(s, info)
    return resultado, guardado, capturado


def campo(obj, novo, antigo):
    """SDK 2.x usa snake_case; 1.x usava camelCase."""
    return getattr(obj, novo) if hasattr(obj, novo) else getattr(obj, antigo)


def corpo(resposta):
    return json.loads(resposta.content[0].text)


async def test_login_ferramentas_e_conversa_entre_os_dois():
    async def como_guilherme(s, info):
        assert campo(info, "server_info", "serverInfo").name == "mural"
        nomes = [t.name for t in (await s.list_tools()).tools]
        entrada = corpo(await s.call_tool("ler", {}))
        criado = corpo(await s.call_tool("escrever", {"titulo": "Mural MCP no ar", "conteudo": "Conecte com `hermes mcp login mural`.", "tipo": "aviso"}))
        return nomes, entrada, criado

    (nomes, entrada, criado), guardado, _ = await usar("guicarvalhal8", como_guilherme)
    assert nomes == ["ler", "escrever", "responder"]
    assert entrada["eu"] == "guilherme" and entrada["pessoas"] == ["felipe"]
    assert [c["titulo"] for c in entrada["cartoes"]] == ["Gateway do WhatsApp configurado"]
    assert criado["para"] == "felipe"
    assert guardado.tokens.access_token and guardado.tokens.refresh_token

    async def como_felipe(s, info):
        caixa = corpo(await s.call_tool("ler", {}))
        aberto = corpo(await s.call_tool("ler", {"id": criado["id"]}))
        fechado = corpo(await s.call_tool("responder", {"id": criado["id"], "texto": "Conectei aqui também.", "status": "feito"}))
        return caixa, aberto, fechado

    (caixa, aberto, fechado), _, _ = await usar("felippealmeidaa", como_felipe)
    assert caixa["eu"] == "felipe" and [c["titulo"] for c in caixa["cartoes"]] == ["Mural MCP no ar"]
    assert aberto["cartao"]["status"] == "lido" and aberto["cartao"]["autor"] == "agente"
    assert fechado == {"ok": True, "resposta": fechado["resposta"], "status": "feito"}


async def test_github_fora_da_lista_nao_entra():
    cliente, guardado, capturado = await sessao("estranho123")
    with pytest.raises(Exception):
        async with cliente:
            async with streamable_http_client(URL, http_client=cliente) as streams:
                async with ClientSession(streams[0], streams[1]) as s:
                    await s.initialize()
    assert capturado["erro"][0] == 403 and "estranho123" in capturado["erro"][1]
    assert guardado.tokens is None


async def test_erros_viram_resultado_de_ferramenta():
    async def passos(s, info):
        return [await s.call_tool("ler", {"id": "nao-e-uuid"}), await s.call_tool("escrever", {"titulo": "", "conteudo": "x"}),
                await s.call_tool("responder", {"id": "00000000-0000-0000-0000-000000000000", "status": "feito"})]

    (r1, r2, r3), _, _ = await usar("guicarvalhal8", passos)
    assert campo(r1, "is_error", "isError") and corpo(r1)["erro"] == "Cartão inválido."
    assert campo(r2, "is_error", "isError") and corpo(r2)["erro"] == "Preencha o título."
    assert campo(r3, "is_error", "isError") and corpo(r3)["erro"] == "Cartão não encontrado."


def test_token_e_pkce_validados_no_servidor():
    # Sem token, token inventado e cartão de outro: nada passa
    assert httpx.post(URL, json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"}).status_code == 401
    assert httpx.post(URL, json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
                      headers={"Authorization": "Bearer inventado"}).status_code == 401
    cli = httpx.post(f"{URL}/register", json={"redirect_uris": [RETORNO], "client_name": "t"}).json()
    assert httpx.post(f"{URL}/register", json={"redirect_uris": ["http://evil.example/cb"]}).status_code == 400
    # Código com verificador PKCE errado é recusado
    httpx.post(f"{RAIZ}/__teste/login", json={"login": "guicarvalhal8"})
    import base64, hashlib, secrets
    verificador = secrets.token_urlsafe(48)
    desafio = base64.urlsafe_b64encode(hashlib.sha256(verificador.encode()).digest()).rstrip(b"=").decode()
    r = httpx.get(f"{URL}/authorize", params={"response_type": "code", "client_id": cli["client_id"], "redirect_uri": RETORNO,
                                              "code_challenge": desafio, "code_challenge_method": "S256", "state": "abc"})
    r = httpx.get(r.headers["location"])  # o "GitHub" volta ao servidor
    destino = parse_qs(urlsplit(r.headers["location"]).query)
    assert destino["state"] == ["abc"]
    ruim = httpx.post(f"{URL}/token", data={"grant_type": "authorization_code", "code": destino["code"][0], "redirect_uri": RETORNO,
                                            "client_id": cli["client_id"], "code_verifier": "errado"})
    assert ruim.status_code == 400 and ruim.json()["error"] == "invalid_grant"
    # O código é de uso único: mesmo com o verificador certo, depois da tentativa ele já foi gasto
    certo = httpx.post(f"{URL}/token", data={"grant_type": "authorization_code", "code": destino["code"][0], "redirect_uri": RETORNO,
                                             "client_id": cli["client_id"], "code_verifier": verificador})
    assert certo.status_code == 400


def test_renovacao_gira_o_refresh_token():
    cli = httpx.post(f"{URL}/register", json={"redirect_uris": [RETORNO]}).json()
    import base64, hashlib, secrets
    verificador = secrets.token_urlsafe(48)
    desafio = base64.urlsafe_b64encode(hashlib.sha256(verificador.encode()).digest()).rstrip(b"=").decode()
    httpx.post(f"{RAIZ}/__teste/login", json={"login": "felippealmeidaa"})
    r = httpx.get(f"{URL}/authorize", params={"response_type": "code", "client_id": cli["client_id"], "redirect_uri": RETORNO,
                                              "code_challenge": desafio, "code_challenge_method": "S256"})
    codigo = parse_qs(urlsplit(httpx.get(r.headers["location"]).headers["location"]).query)["code"][0]
    tokens = httpx.post(f"{URL}/token", data={"grant_type": "authorization_code", "code": codigo, "redirect_uri": RETORNO,
                                              "client_id": cli["client_id"], "code_verifier": verificador}).json()
    novos = httpx.post(f"{URL}/token", data={"grant_type": "refresh_token", "refresh_token": tokens["refresh_token"], "client_id": cli["client_id"]}).json()
    assert novos["access_token"] != tokens["access_token"]
    repetido = httpx.post(f"{URL}/token", data={"grant_type": "refresh_token", "refresh_token": tokens["refresh_token"], "client_id": cli["client_id"]})
    assert repetido.status_code == 400
    lista = httpx.post(URL, json={"jsonrpc": "2.0", "id": 7, "method": "tools/list"}, headers={"Authorization": f"Bearer {novos['access_token']}"})
    assert lista.status_code == 200 and len(lista.json()["result"]["tools"]) == 3
