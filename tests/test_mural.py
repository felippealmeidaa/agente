"""Mural de passagem: loja (Supabase), ferramentas do agente e rotas do painel."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mural_postgrest_falso import CHAVE, PostgrestFalso

RAIZ = Path(__file__).resolve().parents[1]

from plugins.mural import ferramentas, loja

URL = "https://mural-teste.supabase.co"


@pytest.fixture
def banco():
    return PostgrestFalso()


def mural(banco, eu="guilherme", parceiro="felipe", chave=CHAVE):
    return loja.Mural(URL, chave, eu, parceiro, transport=banco.transport)


# --- loja -----------------------------------------------------------------------


def test_passagem_chega_ao_parceiro_e_volta_como_lida(banco):
    gui, felipe = mural(banco), mural(banco, "felipe", "guilherme")
    criado = gui.criar("Login pronto", "Falta o **deploy**.", "passagem")
    assert (criado["de"], criado["para"], criado["status"]) == ("guilherme", "felipe", "novo")

    assert felipe.contar_novos() == 1
    assert [c["titulo"] for c in felipe.listar("entrada")] == ["Login pronto"]
    assert gui.listar("entrada") == []

    aberto = felipe.abrir(criado["id"])
    assert aberto["status"] == "lido" and aberto["respostas"] == []
    assert felipe.contar_novos() == 0
    assert gui.listar("enviados")[0]["status"] == "lido"


def test_quem_escreveu_abrir_nao_marca_como_lido(banco):
    gui = mural(banco)
    criado = gui.criar("Aviso", tipo="aviso")
    assert gui.abrir(criado["id"])["status"] == "novo"


def test_resposta_conta_e_sobe_o_cartao(banco):
    gui, felipe = mural(banco), mural(banco, "felipe", "guilherme")
    primeiro = gui.criar("Primeiro")
    gui.criar("Segundo")
    felipe.responder(primeiro["id"], "Vi, vou olhar.")
    gui.responder(primeiro["id"], "Valeu", autor="agente")

    lista = felipe.listar("entrada")
    assert [c["titulo"] for c in lista] == ["Primeiro", "Segundo"]
    assert lista[0]["respostas"] == 2
    respostas = felipe.abrir(primeiro["id"])["respostas"]
    assert [(r["de"], r["autor"], r["texto"]) for r in respostas] == [
        ("felipe", "humano", "Vi, vou olhar."), ("guilherme", "agente", "Valeu")]


def test_filtros_de_status_e_fixado_no_topo(banco):
    gui, felipe = mural(banco), mural(banco, "felipe", "guilherme")
    a, _b, c = (gui.criar(t) for t in ("A", "B", "C"))
    felipe.atualizar(a["id"], status="feito")
    felipe.atualizar(c["id"], fixado=True)

    assert [x["titulo"] for x in felipe.listar("entrada", "abertos")] == ["C", "B"]
    assert [x["titulo"] for x in felipe.listar("entrada", "feitos")] == ["A"]
    assert len(felipe.listar("todos", "tudo")) == 3


def test_so_quem_escreveu_exclui(banco):
    gui, felipe = mural(banco), mural(banco, "felipe", "guilherme")
    criado = gui.criar("Meu")
    gui.responder(criado["id"], "nota")
    with pytest.raises(loja.ErroMural) as erro:
        felipe.excluir(criado["id"])
    assert erro.value.status == 403
    gui.excluir(criado["id"])
    assert banco.tabelas == {"mural_cartoes": [], "mural_respostas": []}


@pytest.mark.parametrize("chamada, mensagem", [
    (lambda m: m.criar("   "), "Preencha o título."),
    (lambda m: m.criar("x" * 201), "O título passou de 200 caracteres."),
    (lambda m: m.criar("Oi", tipo="spam"), "Tipo inválido"),
    (lambda m: m.abrir("../../etc"), "Cartão inválido."),
    (lambda m: m.atualizar("00000000-0000-0000-0000-000000000000", status="apagado"), "Status inválido"),
    (lambda m: m.listar("lixo"), "Caixa inválida."),
])
def test_validacoes(banco, chamada, mensagem):
    with pytest.raises(loja.ErroMural) as erro:
        chamada(mural(banco))
    assert erro.value.mensagem.startswith(mensagem)
    assert banco.pedidos == []


def test_cartao_inexistente(banco):
    with pytest.raises(loja.ErroMural) as erro:
        mural(banco).abrir("00000000-0000-0000-0000-000000000000")
    assert erro.value.status == 404


def test_chave_errada_vira_mensagem_clara(banco):
    with pytest.raises(loja.ErroMural) as erro:
        mural(banco, chave="sb_secret_errada").listar()
    assert "MURAL_SUPABASE_CHAVE" in erro.value.mensagem


def test_cabecalhos_por_tipo_de_chave(banco):
    mural(banco).listar()
    assert "authorization" not in banco.pedidos[-1].headers
    banco.chave = "eyJ.jwt.antigo"
    mural(banco, chave="eyJ.jwt.antigo").listar()
    assert banco.pedidos[-1].headers["authorization"] == "Bearer eyJ.jwt.antigo"


def test_mesma_pessoa_dos_dois_lados_e_recusada(banco):
    with pytest.raises(loja.ErroMural):
        mural(banco, "felipe", "felipe")


def test_do_ambiente_diz_o_que_falta(monkeypatch):
    for nome in ("MURAL_SUPABASE_URL", "MURAL_SUPABASE_CHAVE", "MURAL_EU", "MURAL_PARCEIRO"):
        monkeypatch.delenv(nome, raising=False)
    monkeypatch.setattr(loja, "_ajustes", lambda: {"eu": "Guilherme", "parceiro": "nome com espaço"})
    monkeypatch.setenv("MURAL_SUPABASE_URL", URL + "/")
    with pytest.raises(loja.MuralNaoConfigurado) as erro:
        loja.do_ambiente()
    assert erro.value.faltando == ["MURAL_SUPABASE_CHAVE no .env", "plugins.entries.mural.settings.parceiro"]

    monkeypatch.setenv("MURAL_SUPABASE_CHAVE", CHAVE)
    monkeypatch.setattr(loja, "_ajustes", lambda: {"eu": "Guilherme", "parceiro": "felipe"})
    pronto = loja.do_ambiente()
    assert (pronto.eu, pronto.parceiro, str(pronto._http.base_url)) == ("guilherme", "felipe", URL + "/rest/v1/")


# --- ferramentas do agente ---------------------------------------------------------


@pytest.fixture
def agente(banco, monkeypatch):
    monkeypatch.setattr(loja, "do_ambiente", lambda: mural(banco, "felipe", "guilherme"))
    return banco


def test_agente_escreve_le_e_fecha(agente):
    gui = mural(agente)
    pergunta = gui.criar("Qual banco?", "x" * 1000, "pergunta")

    lista = json.loads(ferramentas.ler({}))
    assert lista["eu"] == "felipe" and len(lista["cartoes"]) == 1
    assert lista["cartoes"][0]["conteudo"].endswith("…") and len(lista["cartoes"][0]["conteudo"]) == 401

    aberto = json.loads(ferramentas.ler({"id": pergunta["id"]}))
    assert aberto["cartao"]["conteudo"] == "x" * 1000 and aberto["cartao"]["status"] == "lido"

    feito = json.loads(ferramentas.responder({"id": pergunta["id"], "texto": "Postgres.", "status": "feito"}))
    assert feito["status"] == "feito"
    assert agente.tabelas["mural_respostas"][0]["autor"] == "agente"

    novo = json.loads(ferramentas.escrever({"titulo": "Deploy feito", "conteudo": "Render ok."}))
    assert novo["para"] == "guilherme"
    assert gui.listar("entrada")[0]["autor"] == "agente"


def test_ferramentas_devolvem_erro_em_json_sem_levantar(agente, monkeypatch):
    assert json.loads(ferramentas.responder({"id": "x"})) == {"erro": "Informe 'texto', 'status' ou os dois."}
    assert "erro" in json.loads(ferramentas.escrever({"titulo": ""}))

    def quebrado():
        raise loja.MuralNaoConfigurado(["MURAL_SUPABASE_URL no .env"])
    monkeypatch.setattr(loja, "do_ambiente", quebrado)
    assert json.loads(ferramentas.ler({}))["erro"].startswith("Mural não configurado")


def test_registro_das_ferramentas(monkeypatch):
    import plugins.mural as plugin

    registradas = []

    class Ctx:
        def register_tool(self, **kw):
            registradas.append(kw)

    plugin.register(Ctx())
    assert [r["name"] for r in registradas] == ["mural_ler", "mural_escrever", "mural_responder"]
    assert {r["toolset"] for r in registradas} == {"mural"}
    assert all(r["schema"]["name"] == r["name"] for r in registradas)
    monkeypatch.setattr(loja, "do_ambiente", lambda: (_ for _ in ()).throw(loja.MuralNaoConfigurado(["x"])))
    assert registradas[0]["check_fn"]() is False


# --- rotas do painel ------------------------------------------------------------------


@pytest.fixture
def painel(banco, monkeypatch):
    fastapi = pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    caminho = RAIZ / "plugins" / "mural" / "dashboard" / "plugin_api.py"
    spec = importlib.util.spec_from_file_location("hermes_dashboard_plugin_mural", caminho)
    modulo = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = modulo
    spec.loader.exec_module(modulo)
    # O painel carrega a própria cópia da loja pelo caminho: o mural e os erros vêm dela
    monkeypatch.setattr(modulo.loja, "do_ambiente",
                        lambda: modulo.loja.Mural(URL, CHAVE, "guilherme", "felipe", transport=banco.transport))
    app = fastapi.FastAPI()
    app.include_router(modulo.router, prefix="/api/plugins/mural")
    return TestClient(app), modulo


def test_painel_fluxo_completo(painel, banco):
    cliente, _ = painel
    assert cliente.get("/api/plugins/mural/estado").json() == {
        "configurado": True, "eu": "guilherme", "parceiro": "felipe", "novos": 0}

    criado = cliente.post("/api/plugins/mural/cartoes", json={"titulo": "Oi", "conteudo": "corpo", "tipo": "aviso"}).json()
    assert criado["autor"] == "humano" and criado["para"] == "felipe"
    assert cliente.get("/api/plugins/mural/cartoes", params={"caixa": "enviados"}).json()["cartoes"][0]["id"] == criado["id"]

    r = cliente.post(f"/api/plugins/mural/cartoes/{criado['id']}/respostas", json={"texto": "mais info"})
    assert r.status_code == 200
    assert cliente.get(f"/api/plugins/mural/cartoes/{criado['id']}").json()["respostas"][0]["texto"] == "mais info"
    assert cliente.patch(f"/api/plugins/mural/cartoes/{criado['id']}", json={"status": "feito"}).json()["status"] == "feito"
    assert cliente.delete(f"/api/plugins/mural/cartoes/{criado['id']}").json() == {"ok": True}


def test_painel_erros_viram_status_http(painel, monkeypatch):
    cliente, modulo = painel
    r = cliente.post("/api/plugins/mural/cartoes", json={"titulo": " "})
    assert (r.status_code, r.json()["detail"]) == (400, "Preencha o título.")
    assert cliente.get("/api/plugins/mural/cartoes/nao-e-uuid").status_code == 404

    def sem_config():
        raise modulo.loja.MuralNaoConfigurado(["MURAL_SUPABASE_URL no .env"])
    monkeypatch.setattr(modulo.loja, "do_ambiente", sem_config)
    assert cliente.get("/api/plugins/mural/estado").json() == {
        "configurado": False, "faltando": ["MURAL_SUPABASE_URL no .env"]}
