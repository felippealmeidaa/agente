// O que o app precisa saber do Hermes local: pasta, .env, config.yaml e os processos rodando.
const fs = require("fs");
const os = require("os");
const path = require("path");
const { execFile } = require("child_process");
const YAML = require("yaml");

function pastaHermes() {
  const definida = (process.env.HERMES_HOME || "").trim();
  if (definida) return definida;
  if (process.platform === "win32") {
    return path.join(process.env.LOCALAPPDATA || path.join(os.homedir(), "AppData", "Local"), "hermes");
  }
  return path.join(os.homedir(), ".hermes");
}

function lerEnv() {
  const valores = {};
  let texto = "";
  try {
    texto = fs.readFileSync(path.join(pastaHermes(), ".env"), "utf8");
  } catch {
    return valores;
  }
  for (const linha of texto.split(/\r?\n/)) {
    const m = /^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)\s*$/.exec(linha);
    if (!m) continue;
    let valor = m[2];
    if (/^(['"]).*\1$/.test(valor)) valor = valor.slice(1, -1);
    else valor = valor.replace(/\s+#.*$/, "");
    valores[m[1]] = valor;
  }
  return valores;
}

function lerConfig() {
  try {
    return YAML.parse(fs.readFileSync(path.join(pastaHermes(), "config.yaml"), "utf8")) || {};
  } catch {
    return {};
  }
}

function limiteDosHooks(config = lerConfig()) {
  const valor = Number(config?.plugins?.hook_callback_timeout);
  return Number.isFinite(valor) && valor >= 0 ? valor : 30;
}

function pluginsAtivos(config = lerConfig()) {
  const lista = config?.plugins?.enabled;
  return Array.isArray(lista) ? lista.map(String) : [];
}

const MARCAS = /hermes|run_agent\.py|tui_gateway|gateway[\\/]run\.py/i;

function tipoDoProcesso(comando) {
  if (/tui_gateway/i.test(comando)) return "App/TUI";
  if (/\bdashboard\b/i.test(comando)) return "Painel web";
  if (/\bgateway\b/i.test(comando)) return "Gateway (mensagens)";
  if (/\bcron\b/i.test(comando)) return "Agendador";
  return "Agente (CLI)";
}

function rodar(programa, args) {
  return new Promise((ok) => {
    execFile(programa, args, { windowsHide: true, maxBuffer: 8 * 1024 * 1024, timeout: 15000 }, (erro, saida) => ok(erro ? "" : String(saida)));
  });
}

async function listarProcessos() {
  let linhas = [];
  if (process.platform === "win32") {
    const script = "Get-CimInstance Win32_Process -Filter \"Name like 'python%' or Name like 'hermes%' or Name like 'pythonw%' or Name like 'uv%'\" | Select-Object ProcessId,ParentProcessId,Name,CommandLine | ConvertTo-Json -Compress";
    const saida = await rodar("powershell.exe", ["-NoProfile", "-NonInteractive", "-Command", script]);
    try {
      const dados = JSON.parse(saida || "[]");
      linhas = (Array.isArray(dados) ? dados : [dados]).map((p) => ({ pid: p.ProcessId, pai: p.ParentProcessId, nome: p.Name, comando: p.CommandLine || "" }));
    } catch {
      linhas = [];
    }
  } else {
    const saida = await rodar("ps", ["-eo", "pid=,ppid=,comm=,args="]);
    linhas = saida.split("\n").map((l) => /^\s*(\d+)\s+(\d+)\s+(\S+)\s+(.*)$/.exec(l)).filter(Boolean).map((m) => ({ pid: +m[1], pai: +m[2], nome: m[3], comando: m[4] }));
  }
  const candidatos = linhas.filter((p) => p.pid !== process.pid && MARCAS.test(p.comando) && !/hermes-controle|apps[\\/]controle/i.test(p.comando));
  // Esconde filhos de um processo que já está na lista (o wrapper e o python que ele abriu)
  const pids = new Set(candidatos.map((p) => p.pid));
  return candidatos
    .filter((p) => !pids.has(p.pai))
    .map((p) => ({ pid: p.pid, tipo: tipoDoProcesso(p.comando), comando: p.comando.slice(0, 400) }));
}

async function encerrarProcesso(pid) {
  const numero = parseInt(pid, 10);
  if (!Number.isInteger(numero) || numero <= 0 || numero === process.pid) throw new Error("Processo inválido.");
  const permitidos = new Set((await listarProcessos()).map((p) => p.pid));
  if (!permitidos.has(numero)) throw new Error("Esse processo não é do Hermes (ou já terminou).");
  if (process.platform === "win32") {
    await rodar("taskkill.exe", ["/PID", String(numero), "/T", "/F"]);
  } else {
    try {
      process.kill(-numero, "SIGTERM");
    } catch {
      try {
        process.kill(numero, "SIGTERM");
      } catch {}
    }
  }
}

module.exports = { pastaHermes, lerEnv, lerConfig, limiteDosHooks, pluginsAtivos, listarProcessos, encerrarProcesso, tipoDoProcesso };
