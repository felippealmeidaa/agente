// Regras "sempre/nunca" e a cadeia do log: o Python grava, o app confere (mesmo hash nos dois lados).
const test = require("node:test");
const assert = require("node:assert");
const fs = require("fs");
const os = require("os");
const path = require("path");
const { execFileSync } = require("child_process");

const dir = fs.mkdtempSync(path.join(os.tmpdir(), "controle-prot-"));
process.env.HERMES_CONTROLE_DIR = dir;
const canal = require("../canal");
const REPO = path.resolve(__dirname, "../../..");

function pedido(id, extra) {
  canal.gravarJson(path.join(dir, "pedidos", `${id}.json`), { id, criado_em: new Date().toISOString(), expira_em: Date.now() / 1000 + 60, ...extra });
}

test("sempre permitir vira regra livre e responde once ao plugin", () => {
  canal.prepararPasta();
  const id = "1".repeat(32);
  pedido(id, { padrao: "terminal:git push", risco: "normal" });
  assert.strictEqual(canal.responder(id, "sempre"), "once");
  assert.deepStrictEqual(canal.lerPolitica().regras, [{ padrao: "terminal:git push", modo: "livre" }]);
  assert.strictEqual(canal.lerJson(path.join(dir, "respostas", `${id}.json`)).decisao, "once");
});

test("sempre negar substitui a regra do mesmo padrão", () => {
  const id = "2".repeat(32);
  pedido(id, { padrao: "terminal:git push", risco: "normal" });
  assert.strictEqual(canal.responder(id, "nunca"), "negar");
  assert.deepStrictEqual(canal.lerPolitica().regras, [{ padrao: "terminal:git push", modo: "bloqueado" }]);
});

test("risco alto, vazamento ou sem padrão não viram regra", () => {
  for (const [n, extra] of [["3", { padrao: "terminal:reg", risco: "alto" }], ["4", { padrao: "internet:x.com", vazamento: true }], ["5", { padrao: null }]]) {
    const id = n.repeat(32);
    pedido(id, extra);
    assert.throws(() => canal.responder(id, "sempre"), /não pode virar regra/);
  }
});

test("normaliza os campos novos da política", () => {
  const p = canal.normalizar({ vazamento: "talvez", cercar_externo: "não", liberar_triviais: false, regras: [{ padrao: "a:b", modo: "talvez" }, { padrao: "a:c", modo: "livre", x: 1 }] });
  assert.strictEqual(p.vazamento, "perguntar");
  assert.strictEqual(p.cercar_externo, true);
  assert.strictEqual(p.liberar_triviais, false);
  assert.deepStrictEqual(p.regras, [{ padrao: "a:c", modo: "livre" }]);
});

test("a cadeia escrita pelo plugin Python confere no app, e adulteração é pega", (t) => {
  const python = process.platform === "win32" ? "python" : "python3";
  const script = "from plugins.controle import canal\nfor i in range(4): canal.registrar({'tipo':'ferramenta','ferramenta':f'f{i}','resumo':'ação ✓ com \"aspas\" e \\ barra'})";
  try {
    execFileSync(python, ["-c", script], { env: { ...process.env, PYTHONPATH: REPO, PYTHONUTF8: "1" }, stdio: "pipe" });
  } catch (erro) {
    t.skip(`python indisponível: ${erro.message}`);
    return;
  }
  const r = canal.verificarCadeia();
  assert.strictEqual(r.ok, true, JSON.stringify(r));
  assert.strictEqual(r.linhas, 4);

  const arquivo = path.join(dir, "atividade", `${canal.dia()}.jsonl`);
  const linhas = fs.readFileSync(arquivo, "utf8").split("\n");
  linhas[1] = linhas[1].replace('"f1"', '"f7"');
  fs.writeFileSync(arquivo, linhas.join("\n"));
  const ruim = canal.verificarCadeia();
  assert.strictEqual(ruim.ok, false);
  assert.strictEqual(ruim.quebra, 2);
});
