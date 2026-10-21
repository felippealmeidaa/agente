// Mural no app: as mesmas rotas de plugins/mural/dashboard/plugin_api.py, falando direto com o Supabase.
// A chave é lida do .env do Hermes e fica no processo principal; a tela nunca a vê.
const hermes = require("./hermes");

const TIPOS = ["passagem", "pergunta", "aviso"];
const STATUS = ["novo", "lido", "feito"];
const CAIXAS = ["entrada", "enviados", "todos"];
const FILTROS = ["abertos", "feitos", "tudo"];
const PESSOA = /^[a-z0-9][a-z0-9_-]{0,39}$/;
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;

class ErroMural extends Error {
  constructor(mensagem, status = 400, extra = {}) {
    super(mensagem);
    this.status = status;
    Object.assign(this, extra);
  }
}

function pessoa(valor) {
  const v = String(valor || "").trim().toLowerCase();
  return PESSOA.test(v) ? v : null;
}

function configuracao() {
  const env = hermes.lerEnv();
  const ajustes = hermes.lerConfig()?.plugins?.entries?.mural?.settings || {};
  const url = String(env.MURAL_SUPABASE_URL || process.env.MURAL_SUPABASE_URL || "").trim().replace(/\/+$/, "");
  const chave = String(env.MURAL_SUPABASE_CHAVE || process.env.MURAL_SUPABASE_CHAVE || "").trim();
  const eu = pessoa(ajustes.eu || process.env.MURAL_EU);
  const parceiro = pessoa(ajustes.parceiro || process.env.MURAL_PARCEIRO);
  const faltando = [
    ["MURAL_SUPABASE_URL no .env", url], ["MURAL_SUPABASE_CHAVE no .env", chave],
    ["plugins.entries.mural.settings.eu", eu], ["plugins.entries.mural.settings.parceiro", parceiro],
  ].filter(([, v]) => !v).map(([n]) => n);
  if (faltando.length) throw new ErroMural(`Mural não configurado: falta ${faltando.join(", ")}.`, 503, { faltando });
  if (eu === parceiro) throw new ErroMural("Você e o parceiro precisam ter nomes diferentes no config.yaml.");
  return { url, chave, eu, parceiro };
}

function texto(valor, limite, campo, obrigatorio = true) {
  const t = String(valor ?? "").trim();
  if (obrigatorio && !t) throw new ErroMural(`Preencha ${campo}.`);
  if (t.length > limite) throw new ErroMural(`${campo[0].toUpperCase()}${campo.slice(1)} passou de ${limite} caracteres.`);
  return t;
}

function id(valor) {
  const v = String(valor || "").trim().toLowerCase();
  if (!UUID.test(v)) throw new ErroMural("Cartão inválido.", 404);
  return v;
}

function resumo(cartao) {
  const contagem = cartao.mural_respostas;
  delete cartao.mural_respostas;
  cartao.respostas = Array.isArray(contagem) && contagem[0] && "count" in contagem[0] ? contagem[0].count : 0;
  return cartao;
}

async function pedir(cfg, metodo, tabela, params = {}, corpo, representar = false) {
  const url = new URL(`${cfg.url}/rest/v1/${tabela}`);
  for (const [k, v] of Object.entries(params)) url.searchParams.set(k, v);
  const cabecalhos = { apikey: cfg.chave, "Content-Type": "application/json" };
  if (cfg.chave.startsWith("eyJ")) cabecalhos.Authorization = `Bearer ${cfg.chave}`;
  if (representar) cabecalhos.Prefer = "return=representation";
  let resposta;
  try {
    resposta = await fetch(url, { method: metodo, headers: cabecalhos, body: corpo === undefined ? undefined : JSON.stringify(corpo), signal: AbortSignal.timeout(15000) });
  } catch (erro) {
    throw new ErroMural(`Sem conexão com o Supabase do mural (${erro.name}).`, 502);
  }
  const bruto = await resposta.text();
  if (resposta.status === 401 || resposta.status === 403) throw new ErroMural("O Supabase recusou a chave do mural. Confira MURAL_SUPABASE_CHAVE.", 502);
  if (resposta.status === 404 && bruto.includes("mural_")) throw new ErroMural("As tabelas do mural não existem. Rode o supabase.sql no projeto.", 502);
  if (resposta.status >= 400) throw new ErroMural(`O Supabase respondeu ${resposta.status}.`, 502);
  return bruto ? JSON.parse(bruto) : null;
}

const acoes = {
  async estado() {
    let cfg;
    try {
      cfg = configuracao();
    } catch (erro) {
      if (erro.faltando) return { configurado: false, faltando: erro.faltando };
      throw erro;
    }
    try {
      const novos = await pedir(cfg, "GET", "mural_cartoes", { select: "id", para: `eq.${cfg.eu}`, status: "eq.novo", limit: "200" });
      return { configurado: true, eu: cfg.eu, parceiro: cfg.parceiro, novos: (novos || []).length };
    } catch (erro) {
      return { configurado: true, eu: cfg.eu, parceiro: cfg.parceiro, erro: erro.message };
    }
  },

  async listar(cfg, { caixa = "entrada", filtro = "abertos" }) {
    if (!CAIXAS.includes(caixa)) throw new ErroMural("Caixa inválida.");
    if (!FILTROS.includes(filtro)) throw new ErroMural("Filtro inválido.");
    const params = { select: "*,mural_respostas(count)", order: "fixado.desc,atualizado_em.desc", limit: "100" };
    if (caixa === "entrada") params.para = `eq.${cfg.eu}`;
    if (caixa === "enviados") params.de = `eq.${cfg.eu}`;
    if (filtro === "abertos") params.status = "in.(novo,lido)";
    if (filtro === "feitos") params.status = "eq.feito";
    return { cartoes: (await pedir(cfg, "GET", "mural_cartoes", params) || []).map(resumo) };
  },

  async criar(cfg, corpo) {
    const tipo = String(corpo.tipo || "passagem");
    if (!TIPOS.includes(tipo)) throw new ErroMural("Tipo inválido: use passagem, pergunta ou aviso.");
    const linha = {
      de: cfg.eu, para: cfg.parceiro, autor: "humano", tipo,
      titulo: texto(corpo.titulo, 200, "o título"), conteudo: texto(corpo.conteudo, 50000, "o conteúdo", false),
    };
    return resumo((await pedir(cfg, "POST", "mural_cartoes", {}, linha, true))[0]);
  },

  async abrir(cfg, cid) {
    const linhas = await pedir(cfg, "GET", "mural_cartoes", { select: "*,mural_respostas(*)", id: `eq.${cid}`, "mural_respostas.order": "criado_em.asc" });
    if (!linhas || !linhas.length) throw new ErroMural("Cartão não encontrado.", 404);
    const cartao = linhas[0];
    const respostas = cartao.mural_respostas || [];
    delete cartao.mural_respostas;
    if (cartao.para === cfg.eu && cartao.status === "novo") {
      await pedir(cfg, "PATCH", "mural_cartoes", { id: `eq.${cid}`, status: "eq.novo" }, { status: "lido" });
      cartao.status = "lido";
    }
    cartao.respostas = respostas;
    return cartao;
  },

  async atualizar(cfg, cid, corpo) {
    const mudancas = {};
    if (corpo.status != null) {
      if (!STATUS.includes(corpo.status)) throw new ErroMural("Status inválido: use novo, lido ou feito.");
      mudancas.status = corpo.status;
    }
    if (corpo.fixado != null) mudancas.fixado = Boolean(corpo.fixado);
    if (!Object.keys(mudancas).length) throw new ErroMural("Nada para mudar.");
    mudancas.atualizado_em = new Date().toISOString();
    const linhas = await pedir(cfg, "PATCH", "mural_cartoes", { id: `eq.${cid}` }, mudancas, true);
    if (!linhas || !linhas.length) throw new ErroMural("Cartão não encontrado.", 404);
    return resumo(linhas[0]);
  },

  async excluir(cfg, cid) {
    const linhas = await pedir(cfg, "DELETE", "mural_cartoes", { id: `eq.${cid}`, de: `eq.${cfg.eu}` }, undefined, true);
    if (!linhas || !linhas.length) throw new ErroMural("Só quem escreveu o cartão pode excluir.", 403);
    return { ok: true };
  },

  async responder(cfg, cid, corpo) {
    const linha = { cartao_id: cid, de: cfg.eu, autor: "humano", texto: texto(corpo.texto, 20000, "a resposta") };
    return (await pedir(cfg, "POST", "mural_respostas", {}, linha, true))[0];
  },
};

// Recebe o mesmo caminho que a tela do mural chama no painel (/api/plugins/mural/...)
async function rota(caminho, metodo = "GET", corpo = {}) {
  const url = new URL(String(caminho).replace(/^\/api\/plugins\/mural/, ""), "http://mural.local");
  const partes = url.pathname.split("/").filter(Boolean);
  if (partes[0] === "estado" && metodo === "GET") return acoes.estado();
  if (partes[0] !== "cartoes") throw new ErroMural("Rota desconhecida.", 404);
  const cfg = configuracao();
  if (partes.length === 1 && metodo === "GET") return acoes.listar(cfg, Object.fromEntries(url.searchParams));
  if (partes.length === 1 && metodo === "POST") return acoes.criar(cfg, corpo || {});
  const cid = id(partes[1]);
  if (partes.length === 2 && metodo === "GET") return acoes.abrir(cfg, cid);
  if (partes.length === 2 && metodo === "PATCH") return acoes.atualizar(cfg, cid, corpo || {});
  if (partes.length === 2 && metodo === "DELETE") return acoes.excluir(cfg, cid);
  if (partes.length === 3 && partes[2] === "respostas" && metodo === "POST") return acoes.responder(cfg, cid, corpo || {});
  throw new ErroMural("Rota desconhecida.", 404);
}

module.exports = { rota, ErroMural };
