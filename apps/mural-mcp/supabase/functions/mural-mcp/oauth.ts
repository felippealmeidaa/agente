// Servidor de autorização OAuth 2.1 do mural (o que um cliente MCP como o Hermes espera):
// metadados (RFC 8414 / 9728), registro dinâmico (RFC 7591), PKCE S256 obrigatório e o login de
// verdade delegado ao GitHub. Só GitHubs cadastrados em mural_pessoas entram.
import type { Banco } from "./banco.ts";

export interface Config {
  base: string; // URL pública do servidor, sem barra no fim (é o issuer e o resource)
  githubId: string;
  githubSegredo: string;
  githubFalso?: boolean; // só nos testes: pula o GitHub e usa o login de `githubFalsoLogin`
  githubFalsoLogin?: string;
}

const MIN = 60;
export const DURACAO = { pendente: 10 * MIN, codigo: 5 * MIN, acesso: 60 * MIN, renovacao: 60 * 24 * 60 * MIN };

const agora = () => Math.floor(Date.now() / 1000);

export function aleatorio(bytes = 32): string {
  const b = crypto.getRandomValues(new Uint8Array(bytes));
  return btoa(String.fromCharCode(...b)).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

export async function sha256(texto: string): Promise<string> {
  const d = new Uint8Array(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(texto)));
  return [...d].map((x) => x.toString(16).padStart(2, "0")).join("");
}

async function desafioPkce(verificador: string): Promise<string> {
  const d = new Uint8Array(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(verificador)));
  return btoa(String.fromCharCode(...d)).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

const json = (corpo: unknown, status = 200, extra: Record<string, string> = {}) =>
  new Response(JSON.stringify(corpo), { status, headers: { "Content-Type": "application/json", "Cache-Control": "no-store", ...extra } });

const erroOAuth = (erro: string, descricao: string, status = 400) => json({ error: erro, error_description: descricao }, status);

function pagina(titulo: string, texto: string, status = 200): Response {
  const esc = (s: string) => s.replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]!);
  const html = `<!doctype html><html lang="pt-BR"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>${esc(titulo)}</title><body style="margin:0;min-height:100vh;display:grid;place-items:center;background:#041c1c;color:#ffe6cb;font:16px/1.6 system-ui,Segoe UI,sans-serif">
<main style="max-width:30rem;padding:2rem"><h1 style="font-size:1.4rem;margin:0 0 .5rem">${esc(titulo)}</h1><p style="margin:0;opacity:.8">${esc(texto)}</p></main></body></html>`;
  return new Response(html, { status, headers: { "Content-Type": "text/html; charset=utf-8" } });
}

export function metadadosRecurso(cfg: Config) {
  return { resource: cfg.base, authorization_servers: [cfg.base], scopes_supported: ["mural"], bearer_methods_supported: ["header"], resource_name: "Mural de passagem" };
}

export function metadadosServidor(cfg: Config) {
  return {
    issuer: cfg.base,
    authorization_endpoint: `${cfg.base}/authorize`,
    token_endpoint: `${cfg.base}/token`,
    registration_endpoint: `${cfg.base}/register`,
    response_types_supported: ["code"],
    grant_types_supported: ["authorization_code", "refresh_token"],
    code_challenge_methods_supported: ["S256"],
    token_endpoint_auth_methods_supported: ["none"],
    scopes_supported: ["mural"],
    // Campos que leitores de OpenID Connect exigem; o login de verdade é do GitHub
    subject_types_supported: ["public"],
    id_token_signing_alg_values_supported: ["none"],
  };
}

export function naoAutorizado(cfg: Config, motivo = "Faça login no mural"): Response {
  return json({ error: "invalid_token", error_description: motivo }, 401, {
    "WWW-Authenticate": `Bearer realm="mural", resource_metadata="${cfg.base}/.well-known/oauth-protected-resource", scope="mural"`,
  });
}

function redirectValido(uri: unknown): uri is string {
  if (typeof uri !== "string") return false;
  try {
    const u = new URL(uri);
    if (u.hash) return false;
    if (u.protocol === "https:") return true;
    // Clientes nativos (Hermes, Claude Code) recebem o código num servidor local
    return u.protocol === "http:" && ["127.0.0.1", "localhost", "[::1]"].includes(u.hostname);
  } catch {
    return false;
  }
}

export async function registrar(req: Request, banco: Banco): Promise<Response> {
  let corpo: Record<string, unknown>;
  try {
    corpo = await req.json();
  } catch {
    return erroOAuth("invalid_client_metadata", "Corpo JSON inválido.");
  }
  const uris = corpo.redirect_uris;
  if (!Array.isArray(uris) || !uris.length || uris.length > 10 || !uris.every(redirectValido)) {
    return erroOAuth("invalid_redirect_uri", "redirect_uris deve ter de 1 a 10 URLs https ou de loopback (127.0.0.1/localhost).");
  }
  const cliente = {
    client_id: `mural-${aleatorio(18)}`,
    redirect_uris: uris as string[],
    client_name: String(corpo.client_name ?? "cliente MCP").slice(0, 100),
    criado_em: new Date().toISOString(),
  };
  await banco.salvarCliente(cliente);
  return json({
    client_id: cliente.client_id, client_id_issued_at: agora(), client_name: cliente.client_name,
    redirect_uris: cliente.redirect_uris, token_endpoint_auth_method: "none",
    grant_types: ["authorization_code", "refresh_token"], response_types: ["code"], scope: "mural",
  }, 201);
}

export async function autorizar(url: URL, banco: Banco, cfg: Config): Promise<Response> {
  const p = url.searchParams;
  const cliente = await banco.cliente(p.get("client_id") ?? "");
  const redirect = p.get("redirect_uri") ?? "";
  // Sem cliente ou redirect conhecido não dá para devolver o erro ao app: mostra na tela
  if (!cliente) return pagina("Cliente desconhecido", "Este aplicativo não está registrado no mural. Tente conectar de novo.", 400);
  if (!cliente.redirect_uris.includes(redirect)) return pagina("Endereço de retorno inválido", "O aplicativo pediu um retorno que não registrou.", 400);
  const voltar = (erro: string, descricao: string) => {
    const destino = new URL(redirect);
    destino.searchParams.set("error", erro);
    destino.searchParams.set("error_description", descricao);
    if (p.get("state")) destino.searchParams.set("state", p.get("state")!);
    return Response.redirect(destino.toString(), 302);
  };
  if (p.get("response_type") !== "code") return voltar("unsupported_response_type", "Use response_type=code.");
  if (p.get("code_challenge_method") !== "S256" || !p.get("code_challenge")) return voltar("invalid_request", "PKCE com S256 é obrigatório.");
  const resource = p.get("resource");
  if (resource && resource.replace(/\/$/, "") !== cfg.base) return voltar("invalid_target", "Este servidor só emite acesso ao mural.");

  const estado = aleatorio(24);
  await banco.salvarPendente({
    estado, client_id: cliente.client_id, redirect_uri: redirect, code_challenge: p.get("code_challenge")!,
    estado_cliente: p.get("state") ?? "", expira_em: agora() + DURACAO.pendente,
  });
  if (cfg.githubFalso) {
    return Response.redirect(`${cfg.base}/github/callback?code=falso&state=${estado}`, 302);
  }
  const github = new URL("https://github.com/login/oauth/authorize");
  github.searchParams.set("client_id", cfg.githubId);
  github.searchParams.set("redirect_uri", `${cfg.base}/github/callback`);
  github.searchParams.set("state", estado);
  github.searchParams.set("scope", "read:user");
  github.searchParams.set("allow_signup", "false");
  return Response.redirect(github.toString(), 302);
}

async function loginDoGithub(codigo: string, cfg: Config): Promise<string | null> {
  if (cfg.githubFalso) return cfg.githubFalsoLogin ?? null;
  const troca = await fetch("https://github.com/login/oauth/access_token", {
    method: "POST",
    headers: { Accept: "application/json", "Content-Type": "application/json" },
    body: JSON.stringify({ client_id: cfg.githubId, client_secret: cfg.githubSegredo, code: codigo, redirect_uri: `${cfg.base}/github/callback` }),
  });
  const token = (await troca.json().catch(() => ({}))).access_token;
  if (!token) return null;
  const usuario = await fetch("https://api.github.com/user", { headers: { Authorization: `Bearer ${token}`, Accept: "application/vnd.github+json", "User-Agent": "mural-mcp" } });
  const login = (await usuario.json().catch(() => ({}))).login;
  // O token do GitHub não é guardado: só serviu para saber quem é
  await fetch(`https://api.github.com/applications/${cfg.githubId}/token`, {
    method: "DELETE",
    headers: { Authorization: `Basic ${btoa(`${cfg.githubId}:${cfg.githubSegredo}`)}`, Accept: "application/vnd.github+json", "User-Agent": "mural-mcp" },
    body: JSON.stringify({ access_token: token }),
  }).catch(() => {});
  return typeof login === "string" ? login : null;
}

export async function retornoGithub(url: URL, banco: Banco, cfg: Config): Promise<Response> {
  const pendente = await banco.tomarPendente(url.searchParams.get("state") ?? "");
  if (!pendente || pendente.expira_em < agora()) return pagina("Login expirou", "Volte ao Hermes e conecte o mural de novo.", 400);
  const codigoGithub = url.searchParams.get("code");
  if (!codigoGithub) return pagina("Login cancelado", "O GitHub não autorizou. Volte ao Hermes e tente de novo.", 400);
  const login = await loginDoGithub(codigoGithub, cfg);
  if (!login) return pagina("Não deu para falar com o GitHub", "Tente de novo em alguns instantes.", 502);
  const pessoa = await banco.pessoaDoGithub(login);
  if (!pessoa) return pagina("Sem acesso ao mural", `O GitHub @${login} não está na lista de pessoas do mural.`, 403);

  const codigo = aleatorio(32);
  await banco.salvarCodigo({
    hash: await sha256(codigo), client_id: pendente.client_id, redirect_uri: pendente.redirect_uri,
    code_challenge: pendente.code_challenge, pessoa, expira_em: agora() + DURACAO.codigo,
  });
  const destino = new URL(pendente.redirect_uri);
  destino.searchParams.set("code", codigo);
  if (pendente.estado_cliente) destino.searchParams.set("state", pendente.estado_cliente);
  return Response.redirect(destino.toString(), 302);
}

async function emitir(banco: Banco, client_id: string, pessoa: string): Promise<Response> {
  const acesso = aleatorio(32);
  const renovacao = aleatorio(32);
  await banco.salvarToken({ hash: await sha256(acesso), tipo: "acesso", client_id, pessoa, expira_em: agora() + DURACAO.acesso });
  await banco.salvarToken({ hash: await sha256(renovacao), tipo: "renovacao", client_id, pessoa, expira_em: agora() + DURACAO.renovacao });
  return json({ access_token: acesso, token_type: "Bearer", expires_in: DURACAO.acesso, refresh_token: renovacao, scope: "mural" });
}

export async function trocarToken(req: Request, banco: Banco): Promise<Response> {
  let p: URLSearchParams;
  try {
    p = new URLSearchParams(await req.text());
  } catch {
    return erroOAuth("invalid_request", "Corpo inválido.");
  }
  const clientId = p.get("client_id") ?? "";
  const cliente = await banco.cliente(clientId);
  if (!cliente) return erroOAuth("invalid_client", "Cliente desconhecido.", 401);

  if (p.get("grant_type") === "authorization_code") {
    const codigo = await banco.tomarCodigo(await sha256(p.get("code") ?? ""));
    if (!codigo || codigo.expira_em < agora() || codigo.client_id !== clientId) return erroOAuth("invalid_grant", "Código inválido ou expirado.");
    if (codigo.redirect_uri !== (p.get("redirect_uri") ?? "")) return erroOAuth("invalid_grant", "redirect_uri diferente do pedido.");
    if ((await desafioPkce(p.get("code_verifier") ?? "")) !== codigo.code_challenge) return erroOAuth("invalid_grant", "code_verifier não confere (PKCE).");
    return emitir(banco, clientId, codigo.pessoa);
  }
  if (p.get("grant_type") === "refresh_token") {
    const hash = await sha256(p.get("refresh_token") ?? "");
    const atual = await banco.token(hash);
    if (!atual || atual.tipo !== "renovacao" || atual.expira_em < agora() || atual.client_id !== clientId) {
      return erroOAuth("invalid_grant", "Refresh token inválido ou expirado.");
    }
    // Rotação: o refresh token usado deixa de valer
    await banco.apagarToken(hash);
    if (!(await banco.pessoas()).includes(atual.pessoa)) return erroOAuth("invalid_grant", "Esta pessoa saiu do mural.");
    return emitir(banco, clientId, atual.pessoa);
  }
  return erroOAuth("unsupported_grant_type", "Use authorization_code ou refresh_token.");
}

export async function pessoaDoToken(req: Request, banco: Banco): Promise<string | null> {
  const m = /^Bearer\s+(\S+)$/i.exec(req.headers.get("Authorization") ?? "");
  if (!m) return null;
  const token = await banco.token(await sha256(m[1]));
  if (!token || token.tipo !== "acesso" || token.expira_em < agora()) return null;
  return (await banco.pessoas()).includes(token.pessoa) ? token.pessoa : null;
}
