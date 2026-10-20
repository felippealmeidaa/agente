"""Plugin controle: política, aprovação pelo app (arquivos) e registro de atividade."""

from __future__ import annotations

import json
import threading
import time

import pytest

from plugins import controle
from plugins.controle import canal
from plugins.controle import politica as pol


@pytest.fixture
def base(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_CONTROLE_DIR", str(tmp_path))
    monkeypatch.setattr(canal, "espera_maxima", lambda desejada: 3.0)
    canal._cache.update(mtime=None, politica=None)
    controle._liberados.clear()
    regras = pol.politica_padrao()
    regras["aprovar_em"] = "app"
    canal.gravar_json(tmp_path / "politica.json", regras)
    return tmp_path


def gravar_politica(base, **mudancas):
    regras = pol.politica_padrao()
    regras["aprovar_em"] = "app"
    for chave, valor in mudancas.items():
        if chave in pol.CATEGORIAS:
            regras["categorias"][chave] = valor
        else:
            regras[chave] = valor
    canal.gravar_json(base / "politica.json", regras)
    canal._cache.update(mtime=None)


def app_vivo(base):
    canal.gravar_json(base / "vivo.json", {"ts": time.time()})


def responder_quando_pedir(base, decisao, nota=""):
    """Faz o papel do app: espera o pedido aparecer e grava a resposta."""
    visto = {}

    def app():
        for _ in range(200):
            pedidos = list((base / "pedidos").glob("*.json"))
            if pedidos:
                visto.update(json.loads(pedidos[0].read_text(encoding="utf-8")))
                canal.gravar_json(base / "respostas" / pedidos[0].name, {"decisao": decisao, "nota": nota})
                return
            time.sleep(0.02)

    t = threading.Thread(target=app)
    t.start()
    return t, visto


def atividade(base):
    linhas = []
    for arquivo in (base / "atividade").glob("*.jsonl"):
        linhas += [json.loads(l) for l in arquivo.read_text(encoding="utf-8").splitlines()]
    return linhas


# --- política ------------------------------------------------------------------------


@pytest.mark.parametrize("ferramenta, cid", [
    ("terminal", "terminal"), ("execute_code", "terminal"), ("patch", "escrita"), ("read_file", "leitura"),
    ("browser_click", "navegador"), ("computer_use", "pc"), ("web_search", "internet"),
    ("delegate_task", "delegacao"), ("mcp_github_create_issue", "mcp"), ("memory", "outros"),
])
def test_categorias(ferramenta, cid):
    assert pol.categoria(ferramenta) == cid


def test_padroes_seguros():
    regras = pol.politica_padrao()
    assert pol.decidir("read_file", {"path": "a"}, regras).modo == "livre"
    assert pol.decidir("terminal", {"command": "npm run build"}, regras).modo == "perguntar"
    assert pol.decidir("computer_use", {}, regras).modo == "bloqueado"


def test_pausado_bloqueia_ate_o_que_e_sempre_livre():
    regras = pol.normalizar({"parado": True})
    assert pol.decidir("read_file", {}, regras).modo == "bloqueado"
    assert pol.decidir("mural_ler", {}, regras).modo == "bloqueado"
    assert pol.decidir("mural_ler", {}, pol.politica_padrao()).modo == "livre"


def test_pastas_livres_para_gravar():
    regras = pol.normalizar({"pastas_livres": [r"C:\Users\G\projetos"]})
    assert pol.decidir("write_file", {"path": r"C:\Users\G\projetos\app\x.py"}, regras).modo == "livre"
    assert pol.decidir("write_file", {"path": r"c:\users\g\PROJETOS\y.py"}, regras).modo == "livre"
    assert pol.decidir("write_file", {"path": r"C:\Users\G\projetos-velhos\y.py"}, regras).modo == "perguntar"
    assert pol.decidir("patch", {"path": r"C:\Windows\system32\x"}, regras).modo == "perguntar"
    bloqueada = pol.normalizar({"pastas_livres": [r"C:\Users\G\projetos"], "categorias": {"escrita": "bloqueado"}})
    assert pol.decidir("write_file", {"path": r"C:\Users\G\projetos\x"}, bloqueada).modo == "bloqueado"


def test_politica_estranha_volta_ao_padrao():
    regras = pol.normalizar({"parado": "sim", "categorias": {"pc": "talvez", "leitura": "bloqueado"},
                             "espera_segundos": 99999, "pastas_livres": [3, "", "C:\\ok"]})
    assert regras["parado"] is False
    assert regras["categorias"]["pc"] == "bloqueado" and regras["categorias"]["leitura"] == "bloqueado"
    assert regras["espera_segundos"] == 590 and regras["pastas_livres"] == ["C:\\ok"]
    assert pol.normalizar("lixo") == pol.politica_padrao()


def test_resumo_mostra_o_comando():
    assert pol.resumo("terminal", {"command": "rm   -rf  build"}) == "rm -rf build"
    assert pol.resumo("terminal", {"command": "x" * 500}, limite=10) == "x" * 10 + "…"


# --- hook antes da ferramenta ------------------------------------------------------------


def test_livre_passa_sem_pedido(base):
    assert controle.antes_da_ferramenta("read_file", {"path": "a.txt"}, "s1") is None
    assert not (base / "pedidos").exists()


def test_bloqueado_avisa_o_modelo_e_registra(base):
    feito = controle.antes_da_ferramenta("computer_use", {"action": "click"}, "s1")
    assert feito["action"] == "block" and "Controle do PC" in feito["message"]
    assert atividade(base)[0]["decisao"] == "bloqueado"


def test_app_fechado_bloqueia_o_que_pede_aprovacao(base):
    feito = controle.antes_da_ferramenta("terminal", {"command": "npm test"}, "s1")
    assert feito["action"] == "block" and "fechado" in feito["message"]


@pytest.mark.parametrize("decisao, passa", [("once", True), ("sessao", True), ("negar", False)])
def test_aprovacao_pelo_app(base, decisao, passa):
    app_vivo(base)
    t, visto = responder_quando_pedir(base, decisao, nota="use o build novo" if decisao == "negar" else "")
    feito = controle.antes_da_ferramenta("terminal", {"command": "npm run deploy"}, "s1", session_id="sess-9")
    t.join()
    assert (feito is None) is passa
    assert visto["resumo"] == "npm run deploy" and visto["sessao"] == "sess-9" and visto["nome_categoria"] == "Terminal e código"
    if decisao == "negar":
        assert "use o build novo" in feito["message"]
    assert list((base / "pedidos").glob("*.json")) == [] and list((base / "respostas").glob("*.json")) == []
    assert atividade(base)[-1]["decisao"] == decisao


def test_permitir_na_sessao_nao_pergunta_de_novo(base):
    app_vivo(base)
    t, _ = responder_quando_pedir(base, "sessao")
    assert controle.antes_da_ferramenta("terminal", {"command": "npm test"}, "", session_id="A") is None
    t.join()
    assert controle.antes_da_ferramenta("terminal", {"command": "npm run lint"}, "", session_id="A") is None
    # outra sessão ainda pergunta (e, sem resposta, o tempo acaba)
    feito = controle.antes_da_ferramenta("terminal", {"command": "npm run lint"}, "", session_id="B")
    assert feito["action"] == "block" and "a tempo" in feito["message"]


def test_sem_resposta_bloqueia_por_tempo(base, monkeypatch):
    app_vivo(base)
    monkeypatch.setattr(canal, "espera_maxima", lambda desejada: 0.5)
    inicio = time.monotonic()
    feito = controle.antes_da_ferramenta("browser_navigate", {"url": "https://x.com"}, "s")
    assert feito["action"] == "block" and time.monotonic() - inicio < 2


def test_pausa_no_meio_vale_na_proxima_chamada(base):
    gravar_politica(base, leitura="livre")
    assert controle.antes_da_ferramenta("read_file", {}, "s") is None
    time.sleep(0.01)
    gravar_politica(base, parado=True)
    assert controle.antes_da_ferramenta("read_file", {}, "s")["action"] == "block"


# --- hook depois da ferramenta ------------------------------------------------------------


def test_atividade_registra_resultado(base):
    controle.depois_da_ferramenta("terminal", {"command": "ls"}, '{"output": "a"}', "s", duration_ms=42)
    controle.depois_da_ferramenta("read_file", {"path": "x"}, '{"error": "não existe"}', "s", duration_ms=3)
    a, b = atividade(base)
    assert (a["ferramenta"], a["ok"], a["duracao_ms"], a["resumo"]) == ("terminal", True, 42, "ls")
    assert (b["categoria"], b["ok"]) == ("leitura", False)


def test_registro(base):
    hooks = []

    class Ctx:
        def register_hook(self, nome, funcao):
            hooks.append(nome)

    controle.register(Ctx())
    assert hooks == ["pre_tool_call", "transform_tool_result", "post_tool_call", "post_approval_response"]
