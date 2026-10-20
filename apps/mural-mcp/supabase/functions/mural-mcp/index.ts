// Edge Function "mural-mcp": servidor MCP remoto do mural com login GitHub.
// Segredos (definidos uma vez no painel do Supabase): GITHUB_CLIENT_ID e GITHUB_CLIENT_SECRET.
// SUPABASE_URL e SUPABASE_SERVICE_ROLE_KEY o próprio Supabase injeta.
import { BancoSupabase } from "./banco_supabase.ts";
import { criarServidor } from "./servidor.ts";

const url = Deno.env.get("SUPABASE_URL")!;
const base = (Deno.env.get("MURAL_URL_PUBLICA") ?? `${url}/functions/v1/mural-mcp`).replace(/\/+$/, "");

Deno.serve(criarServidor(new BancoSupabase(url, Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!), {
  base,
  githubId: Deno.env.get("GITHUB_CLIENT_ID") ?? "",
  githubSegredo: Deno.env.get("GITHUB_CLIENT_SECRET") ?? "",
}));
