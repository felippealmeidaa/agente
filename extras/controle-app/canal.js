// Lado do app do canal em arquivos com o plugin `controle` (ver plugins/controle/canal.py).
const fs = require("fs");
const os = require("os");
const path = require("path");
const crypto = require("crypto");

const CATEGORIAS = require("../../plugins/controle/categorias.json");
const MODOS = ["livre", "perguntar", "bloqueado"];
const VAZAMENTO = ["perguntar", "bloquear", "desligado"];
// "sempre" e "nunca" viram regra na política e chegam ao plugin como "once" e "negar"
const DECISOES = ["once", "sessao", "negar", "sempre", "nunca"];
const HASH_ZERO = "0".repeat(64);
const SUFIXO_HASH = /,"hash":"([0-9a-f]{64})"\}$/;

function pasta() {
  const definida = (process.env.HERMES_CONTROLE_DIR || "").trim();
  if (definida) return definida;
  // Mesma regra do canal.py: um Hermes isolado (HERMES_HOME) tem o seu próprio controle
  const isolado = (process.env.HERMES_HOME || "").trim();
  if (isolado) return path.join(isolado, "controle");
  if (process.platform === "win32") {
    return path.join(process.env.LOCALAPPDATA || path.join(os.homedir(), "AppData", "Local"), "hermes-controle");
  }
  return path.join(os.homedir(), ".hermes-controle");
}

function gravarJson(caminho, dados) {
  fs.mkdirSync(path.dirname(caminho), { recursive: true });
  const temp = path.join(path.dirname(caminho), `.${path.basename(caminho)}.${crypto.randomUUID()}.tmp`);
  fs.writeFileSync(temp, JSON.stringify(dados, null, 2), "utf8");
  fs.renameSync(temp, caminho);
}

function lerJson(caminho) {
  try {
    return JSON.parse(fs.readFileSync(caminho, "utf8"));
  } catch {
    return null;
  }
}

function politicaPadrao() {
  return {
    versao: 1,
    parado: false,
    categorias: Object.fromEntries(CATEGORIAS.map((c) => [c.id, c.padrao])),
    pastas_livres: [],
    espera_segundos: 120,
    regras: [],
    liberar_triviais: true,
    vazamento: "perguntar",
    cercar_externo: true,
    aprovar_em: "hermes",
  };
}

// Mesmas regras do politica.normalizar() em Python
function normalizar(bruta) {
  const base = politicaPadrao();
  if (!bruta || typeof bruta !== "object") return base;
  base.parado = bruta.parado === true;
  const cats = bruta.categorias && typeof bruta.categorias === "object" ? bruta.categorias : {};
  for (const id of Object.keys(base.categorias)) if (MODOS.includes(cats[id])) base.categorias[id] = cats[id];
  if (Array.isArray(bruta.pastas_livres)) base.pastas_livres = bruta.pastas_livres.filter((p) => typeof p === "string" && p.trim());
  const espera = parseInt(bruta.espera_segundos, 10);
  if (Number.isFinite(espera)) base.espera_segundos = Math.max(10, Math.min(espera, 590));
  if (Array.isArray(bruta.regras)) {
    base.regras = bruta.regras
      .filter((r) => r && typeof r === "object" && typeof r.padrao === "string" && r.padrao && ["livre", "bloqueado"].includes(r.modo))
      .map((r) => ({ padrao: r.padrao, modo: r.modo }));
  }
  if (bruta.liberar_triviais === false) base.liberar_triviais = false;
  if (VAZAMENTO.includes(bruta.vazamento)) base.vazamento = bruta.vazamento;
  if (bruta.cercar_externo === false) base.cercar_externo = false;
  if (["hermes", "app"].includes(bruta.aprovar_em)) base.aprovar_em = bruta.aprovar_em;
  return base;
}

function lerPolitica() {
  return normalizar(lerJson(path.join(pasta(), "politica.json")));
}

function salvarPolitica(politica) {
  const limpa = normalizar(politica);
  gravarJson(path.join(pasta(), "politica.json"), limpa);
  return limpa;
}

function prepararPasta() {
  for (const sub of ["pedidos", "respostas", "atividade"]) fs.mkdirSync(path.join(pasta(), sub), { recursive: true });
  if (!fs.existsSync(path.join(pasta(), "politica.json"))) salvarPolitica(politicaPadrao());
}

function batimento() {
  gravarJson(path.join(pasta(), "vivo.json"), { ts: Date.now() / 1000, pid: process.pid });
}

function encerrarBatimento() {
  try {
    fs.unlinkSync(path.join(pasta(), "vivo.json"));
  } catch {}
}

function listarPedidos() {
  const dir = path.join(pasta(), "pedidos");
  let nomes = [];
  try {
    nomes = fs.readdirSync(dir).filter((n) => n.endsWith(".json") && !n.startsWith("."));
  } catch {
    return [];
  }
  const respondidos = new Set();
  try {
    for (const n of fs.readdirSync(path.join(pasta(), "respostas"))) respondidos.add(n);
  } catch {}
  return nomes
    .filter((n) => !respondidos.has(n))
    .map((n) => lerJson(path.join(dir, n)))
    .filter((p) => p && p.id && p.expira_em * 1000 > Date.now())
    .sort((a, b) => (a.criado_em < b.criado_em ? -1 : 1));
}

function responder(id, decisao, nota) {
  if (!/^[0-9a-f]{32}$/.test(String(id))) throw new Error("Pedido inválido.");
  if (!DECISOES.includes(decisao)) throw new Error("Decisão inválida.");
  const pedido = lerJson(path.join(pasta(), "pedidos", `${id}.json`));
  if (!pedido) throw new Error("Esse pedido já expirou.");
  let paraPlugin = decisao;
  if (decisao === "sempre" || decisao === "nunca") {
    if (!pedido.padrao || pedido.risco === "alto" || pedido.vazamento) throw new Error("Esta ação não pode virar regra.");
    const modo = decisao === "sempre" ? "livre" : "bloqueado";
    const politica = lerPolitica();
    politica.regras = [...politica.regras.filter((r) => r.padrao !== pedido.padrao), { padrao: pedido.padrao, modo }];
    salvarPolitica(politica);
    paraPlugin = decisao === "sempre" ? "once" : "negar";
  }
  gravarJson(path.join(pasta(), "respostas", `${id}.json`), { decisao: paraPlugin, nota: String(nota || "").slice(0, 500), em: new Date().toISOString() });
  return paraPlugin;
}

// Mesma cadeia do canal.registrar() em Python: sha256(hash_anterior + "\n" + linha_sem_hash)
function verificarCadeia(qualDia) {
  const nome = /^\d{4}-\d{2}-\d{2}$/.test(qualDia || "") ? qualDia : dia();
  let texto = "";
  try {
    texto = fs.readFileSync(path.join(pasta(), "atividade", `${nome}.jsonl`), "utf8");
  } catch {
    return { ok: true, linhas: 0, quebra: null, ultimo: HASH_ZERO, hashes: [] };
  }
  const linhas = texto.split("\n").map((l) => l.replace(/\r$/, "")).filter((l) => l.trim());
  let anterior = HASH_ZERO;
  const hashes = [];
  for (let i = 0; i < linhas.length; i++) {
    const achado = SUFIXO_HASH.exec(linhas[i]);
    const esperado = achado && crypto.createHash("sha256").update(`${anterior}\n${linhas[i].slice(0, achado.index)}}`, "utf8").digest("hex");
    if (!achado || esperado !== achado[1]) return { ok: false, linhas: linhas.length, quebra: i + 1, ultimo: anterior, hashes };
    anterior = achado[1];
    hashes.push(anterior);
  }
  return { ok: true, linhas: linhas.length, quebra: null, ultimo: anterior, hashes };
}

function dia(data) {
  const d = data ? new Date(data) : new Date();
  const p = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

function lerAtividade(qualDia, limite = 500) {
  const nome = /^\d{4}-\d{2}-\d{2}$/.test(qualDia || "") ? qualDia : dia();
  let texto = "";
  try {
    texto = fs.readFileSync(path.join(pasta(), "atividade", `${nome}.jsonl`), "utf8");
  } catch {
    return [];
  }
  const eventos = [];
  for (const linha of texto.split("\n")) {
    if (!linha.trim()) continue;
    try {
      eventos.push(JSON.parse(linha));
    } catch {}
  }
  return eventos.slice(-limite).reverse();
}

function diasComAtividade() {
  try {
    return fs.readdirSync(path.join(pasta(), "atividade")).filter((n) => /^\d{4}-\d{2}-\d{2}\.jsonl$/.test(n)).map((n) => n.slice(0, 10)).sort().reverse();
  } catch {
    return [];
  }
}

module.exports = {
  CATEGORIAS, MODOS, pasta, gravarJson, lerJson, politicaPadrao, normalizar, lerPolitica, salvarPolitica,
  prepararPasta, batimento, encerrarBatimento, listarPedidos, responder, lerAtividade, diasComAtividade, dia,
  verificarCadeia, HASH_ZERO,
};
