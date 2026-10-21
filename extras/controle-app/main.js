// Controle do Hermes: janela, bandeja e o lado do app do canal com o plugin `controle`.
const fs = require("fs");
const path = require("path");
const { app, BrowserWindow, Tray, Menu, ipcMain, Notification, dialog, nativeImage, shell } = require("electron");

const canal = require("./canal");
const hermes = require("./hermes");
const mural = require("./mural");
const icone = require("./icone");

const TITULO = "Controle do Hermes";
let janela = null;
let bandeja = null;
let saindo = false;
let pedidosVistos = new Set();

if (!app.requestSingleInstanceLock()) {
  app.quit();
}

function mostrar() {
  if (!janela) return;
  if (janela.isMinimized()) janela.restore();
  janela.show();
  janela.focus();
}

function enviar(canalIpc, dados) {
  if (janela && !janela.isDestroyed()) janela.webContents.send(canalIpc, dados);
}

function estadoBandeja() {
  const politica = canal.lerPolitica();
  const pedidos = canal.listarPedidos();
  const estado = pedidos.length ? "pedido" : politica.parado ? "pausado" : "livre";
  const dica = pedidos.length
    ? `${TITULO}: ${pedidos.length} ${pedidos.length === 1 ? "ação espera" : "ações esperam"} você`
    : politica.parado ? `${TITULO}: agente pausado` : `${TITULO}: agente liberado`;
  return { politica, pedidos, estado, dica };
}

function atualizarBandeja() {
  if (!bandeja) return;
  const { politica, pedidos, estado, dica } = estadoBandeja();
  bandeja.setImage(nativeImage.createFromBuffer(icone.png(estado, 32)));
  bandeja.setToolTip(dica);
  bandeja.setContextMenu(Menu.buildFromTemplate([
    { label: pedidos.length ? `Abrir (${pedidos.length} pendente${pedidos.length > 1 ? "s" : ""})` : "Abrir", click: mostrar },
    { type: "separator" },
    politica.parado
      ? { label: "Retomar o agente", click: () => pausar(false) }
      : { label: "Pausar o agente", click: () => pausar(true) },
    { label: "Parar tudo…", click: confirmarPararTudo },
    { type: "separator" },
    { label: "Sair", click: () => { saindo = true; app.quit(); } },
  ]));
  if (janela) janela.setTitle(pedidos.length ? `(${pedidos.length}) ${TITULO}` : TITULO);
  if (process.platform === "win32" && janela) janela.setOverlayIcon(pedidos.length ? nativeImage.createFromBuffer(icone.png("pedido", 16)) : null, dica);
}

function pausar(parado) {
  const politica = canal.salvarPolitica({ ...canal.lerPolitica(), parado });
  enviar("politica", politica);
  atualizarBandeja();
  return politica;
}

async function pararTudo() {
  pausar(true);
  const processos = await hermes.listarProcessos();
  const encerrados = [];
  for (const p of processos) {
    try {
      await hermes.encerrarProcesso(p.pid);
      encerrados.push(p.pid);
    } catch {}
  }
  return { encerrados };
}

async function confirmarPararTudo() {
  const { response } = await dialog.showMessageBox(janela && janela.isVisible() ? janela : undefined, {
    type: "warning", buttons: ["Parar tudo", "Cancelar"], defaultId: 1, cancelId: 1, title: TITULO,
    message: "Parar tudo?", detail: "Pausa o agente e encerra todos os processos do Hermes neste PC (CLI, gateway e painel).",
  });
  if (response === 0) {
    const { encerrados } = await pararTudo();
    new Notification({ title: TITULO, body: `Agente pausado. ${encerrados.length} processo(s) encerrado(s).` }).show();
  }
}

// Âncoras do log ficam na pasta do app (fora da pasta que o agente usa): se alguém reescrever o
// histórico e recalcular a cadeia inteira, o hash guardado aqui para a linha N deixa de bater.
const arquivoAncoras = () => path.join(app.getPath("userData"), "ancoras-atividade.json");
let alertouIntegridade = new Set();

function integridade(qualDia) {
  const diaAlvo = qualDia || canal.dia();
  const cadeia = canal.verificarCadeia(diaAlvo);
  const ancoras = canal.lerJson(arquivoAncoras()) || {};
  const ancora = ancoras[diaAlvo];
  let reescrito = false;
  if (cadeia.ok && ancora && ancora.linhas > 0) {
    reescrito = cadeia.linhas < ancora.linhas || cadeia.hashes[ancora.linhas - 1] !== ancora.hash;
  }
  if (cadeia.ok && !reescrito && cadeia.linhas) {
    ancoras[diaAlvo] = { linhas: cadeia.linhas, hash: cadeia.ultimo };
    try {
      canal.gravarJson(arquivoAncoras(), ancoras);
    } catch {}
  }
  return { ok: cadeia.ok && !reescrito, linhas: cadeia.linhas, quebra: cadeia.quebra, reescrito, ancoradas: ancora ? ancora.linhas : 0 };
}

function vigiarIntegridade() {
  const r = integridade();
  const chave = canal.dia();
  if (!r.ok && !alertouIntegridade.has(chave)) {
    alertouIntegridade.add(chave);
    const aviso = new Notification({
      title: "O registro de atividade foi alterado",
      body: r.reescrito ? "O histórico de hoje foi reescrito depois que o app o conferiu." : `A linha ${r.quebra} de hoje não confere com a anterior.`,
      urgency: "critical",
    });
    aviso.on("click", mostrar);
    aviso.show();
  }
  if (r.ok) alertouIntegridade.delete(chave);
}

// Novos pedidos: avisa na hora, mesmo com a janela escondida
function vigiarPedidos() {
  const pedidos = canal.listarPedidos();
  const ids = new Set(pedidos.map((p) => p.id));
  const novos = pedidos.filter((p) => !pedidosVistos.has(p.id));
  const mudou = novos.length > 0 || ids.size !== pedidosVistos.size;
  pedidosVistos = ids;
  enviar("pedidos", pedidos);
  if (mudou) atualizarBandeja();
  if (novos.length) {
    for (const p of novos) {
      const titulo = p.risco === "alto" ? `Risco alto: ${p.nome_categoria}` : p.vazamento ? `Possível vazamento: ${p.nome_categoria}` : `Aprovar: ${p.nome_categoria}`;
      const aviso = new Notification({ title: titulo, body: `${p.ferramenta} — ${String(p.resumo).slice(0, 140)}`, urgency: "critical" });
      aviso.on("click", mostrar);
      aviso.show();
    }
    if (janela && !janela.isFocused()) janela.flashFrame(true);
  }
}

function criarJanela() {
  janela = new BrowserWindow({
    width: 1200, height: 800, minWidth: 920, minHeight: 620, title: TITULO, backgroundColor: "#041c1c",
    icon: nativeImage.createFromBuffer(icone.png("livre", 64)), autoHideMenuBar: true, show: false,
    webPreferences: { preload: path.join(__dirname, "preload.js"), contextIsolation: true, sandbox: true, nodeIntegration: false, spellcheck: false },
  });
  janela.removeMenu();
  janela.loadFile(path.join(__dirname, "ui", "index.html"));
  janela.once("ready-to-show", () => { if (!process.argv.includes("--escondido")) janela.show(); });
  janela.on("focus", () => janela.flashFrame(false));
  // Fechar esconde na bandeja; o app continua aprovando
  janela.on("close", (e) => {
    if (!saindo) {
      e.preventDefault();
      janela.hide();
    }
  });
  janela.webContents.setWindowOpenHandler(({ url }) => {
    if (/^https?:\/\//.test(url)) shell.openExternal(url);
    return { action: "deny" };
  });
  janela.webContents.on("will-navigate", (e) => e.preventDefault());
}

function responder(trabalho) {
  return async (_evento, ...args) => {
    try {
      return { ok: true, dados: await trabalho(...args) };
    } catch (erro) {
      return { ok: false, mensagem: erro.message || String(erro), status: erro.status || 500, faltando: erro.faltando };
    }
  };
}

function registrarIpc() {
  ipcMain.handle("estado", responder(() => {
    const config = hermes.lerConfig();
    return {
      politica: canal.lerPolitica(), pedidos: canal.listarPedidos(), categorias: canal.CATEGORIAS,
      pasta: canal.pasta(), pastaHermes: hermes.pastaHermes(), limiteHooks: hermes.limiteDosHooks(config),
      pluginsAtivos: hermes.pluginsAtivos(config),
    };
  }));
  ipcMain.handle("politica:salvar", responder((politica) => {
    const salva = canal.salvarPolitica(politica);
    enviar("politica", salva);
    atualizarBandeja();
    return salva;
  }));
  ipcMain.handle("pausar", responder((parado) => pausar(Boolean(parado))));
  ipcMain.handle("parar-tudo", responder(pararTudo));
  ipcMain.handle("pedido:responder", responder((id, decisao, nota) => {
    canal.responder(id, decisao, nota);
    if (decisao === "sempre" || decisao === "nunca") enviar("politica", canal.lerPolitica());
    setTimeout(vigiarPedidos, 50);
    return true;
  }));
  ipcMain.handle("integridade", responder((dia) => integridade(dia)));
  ipcMain.handle("atividade", responder((dia) => ({ eventos: canal.lerAtividade(dia), dias: canal.diasComAtividade(), hoje: canal.dia() })));
  ipcMain.handle("processos", responder(() => hermes.listarProcessos()));
  ipcMain.handle("processo:encerrar", responder((pid) => hermes.encerrarProcesso(pid)));
  ipcMain.handle("pasta:escolher", responder(async () => {
    const { canceled, filePaths } = await dialog.showOpenDialog(janela, { title: "Pasta onde o agente pode gravar sem perguntar", properties: ["openDirectory"] });
    return canceled ? null : filePaths[0];
  }));
  ipcMain.handle("pasta:abrir", responder(() => shell.openPath(canal.pasta())));
  ipcMain.handle("mural", responder((caminho, metodo, corpo) => mural.rota(caminho, metodo, corpo)));
}

app.on("second-instance", mostrar);
app.on("before-quit", () => { saindo = true; });
app.on("will-quit", () => canal.encerrarBatimento());
app.on("window-all-closed", (e) => e.preventDefault());

app.whenReady().then(() => {
  if (process.platform === "win32") app.setAppUserModelId("hermes.controle");
  canal.prepararPasta();
  canal.batimento();
  setInterval(() => canal.batimento(), 2000);
  registrarIpc();
  criarJanela();
  bandeja = new Tray(nativeImage.createFromBuffer(icone.png("livre", 32)));
  bandeja.on("click", mostrar);
  atualizarBandeja();
  pedidosVistos = new Set(canal.listarPedidos().map((p) => p.id));
  setInterval(vigiarPedidos, 600);
  vigiarIntegridade();
  setInterval(vigiarIntegridade, 30000);
});
