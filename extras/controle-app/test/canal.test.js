// Lado do app do canal: mesma normalização do plugin Python e respostas só para pedidos vivos.
const test = require("node:test");
const assert = require("node:assert");
const fs = require("fs");
const os = require("os");
const path = require("path");

const dir = fs.mkdtempSync(path.join(os.tmpdir(), "controle-"));
process.env.HERMES_CONTROLE_DIR = dir;
const canal = require("../canal");
const { tipoDoProcesso } = require("../hermes");

test("cria a pasta com a política padrão", () => {
  canal.prepararPasta();
  const p = canal.lerPolitica();
  assert.strictEqual(p.categorias.pc, "bloqueado");
  assert.strictEqual(p.categorias.leitura, "livre");
  assert.strictEqual(p.parado, false);
});

test("normaliza igual ao politica.normalizar() do Python", () => {
  const p = canal.normalizar({ parado: "sim", categorias: { pc: "talvez", leitura: "bloqueado" }, espera_segundos: 99999, pastas_livres: [3, "", "C:\ok"] });
  assert.strictEqual(p.parado, false);
  assert.strictEqual(p.categorias.pc, "bloqueado");
  assert.strictEqual(p.categorias.leitura, "bloqueado");
  assert.strictEqual(p.espera_segundos, 590);
  assert.deepStrictEqual(p.pastas_livres, ["C:\ok"]);
  assert.deepStrictEqual(canal.normalizar("lixo"), canal.politicaPadrao());
});

test("lista só pedidos vivos e sem resposta, e responde com validação", () => {
  const agora = Date.now() / 1000;
  const vivo = "a".repeat(32), velho = "b".repeat(32), respondido = "c".repeat(32);
  canal.gravarJson(path.join(dir, "pedidos", `${vivo}.json`), { id: vivo, criado_em: "2026-10-20T10:00:00Z", expira_em: agora + 60 });
  canal.gravarJson(path.join(dir, "pedidos", `${velho}.json`), { id: velho, criado_em: "2026-10-20T09:00:00Z", expira_em: agora - 1 });
  canal.gravarJson(path.join(dir, "pedidos", `${respondido}.json`), { id: respondido, criado_em: "2026-10-20T09:30:00Z", expira_em: agora + 60 });
  canal.gravarJson(path.join(dir, "respostas", `${respondido}.json`), { decisao: "once" });
  assert.deepStrictEqual(canal.listarPedidos().map((p) => p.id), [vivo]);

  assert.throws(() => canal.responder("../x", "once"), /Pedido inválido/);
  assert.throws(() => canal.responder(vivo, "talvez"), /Decisão inválida/);
  assert.throws(() => canal.responder("d".repeat(32), "once"), /expirou/);
  canal.responder(vivo, "negar", "não");
  assert.deepStrictEqual(canal.lerJson(path.join(dir, "respostas", `${vivo}.json`)).decisao, "negar");
  assert.deepStrictEqual(canal.listarPedidos(), []);
});

test("lê a atividade do dia, mais recente primeiro, ignorando linha quebrada", () => {
  const hoje = canal.dia();
  fs.writeFileSync(path.join(dir, "atividade", `${hoje}.jsonl`), '{"ferramenta":"a"}\n{quebrada\n{"ferramenta":"b"}\n');
  assert.deepStrictEqual(canal.lerAtividade().map((e) => e.ferramenta), ["b", "a"]);
  assert.deepStrictEqual(canal.diasComAtividade(), [hoje]);
});

test("reconhece o tipo de processo do Hermes", () => {
  assert.strictEqual(tipoDoProcesso("python -m hermes_cli.main gateway run"), "Gateway (mensagens)");
  assert.strictEqual(tipoDoProcesso("hermes dashboard --port 9119"), "Painel web");
  assert.strictEqual(tipoDoProcesso("python -m tui_gateway.entry"), "App/TUI");
  assert.strictEqual(tipoDoProcesso("python cli.py"), "Agente (CLI)");
});
