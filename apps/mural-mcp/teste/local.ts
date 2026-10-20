// Servidor local para testes: banco em memória e GitHub falso. Nunca use em produção.
//   npx deno run --allow-net --allow-env teste/local.ts
// POST /__teste/login {"login": "..."} troca quem o "GitHub" diz que está logando.
import { BancoMemoria } from "../supabase/functions/mural-mcp/banco.ts";
import { criarServidor } from "../supabase/functions/mural-mcp/servidor.ts";

const porta = Number(Deno.env.get("PORTA") ?? "8794");
const banco = new BancoMemoria({ anaexemplo: "ana", brunoexemplo: "bruno" });
const cfg = { base: `http://127.0.0.1:${porta}/functions/v1/mural-mcp`, githubId: "", githubSegredo: "", githubFalso: true, githubFalsoLogin: "anaexemplo" };
await banco.criarCartao({ de: "bruno", para: "ana", autor: "agente", tipo: "passagem", titulo: "Gateway do WhatsApp configurado", conteudo: "Falta trocar o webhook na VPS." });
const servidor = criarServidor(banco, cfg);

Deno.serve({ port: porta, hostname: "127.0.0.1", onListen: () => console.log(`pronto ${cfg.base}`) }, async (req) => {
  const url = new URL(req.url);
  if (url.pathname === "/__teste/login" && req.method === "POST") {
    cfg.githubFalsoLogin = (await req.json()).login;
    return new Response("ok");
  }
  if (url.pathname === "/__teste/estado") {
    return Response.json({ cartoes: banco.cartoes, respostas: banco.lista_respostas, tokens: banco.tokens.size, clientes: banco.clientes.size });
  }
  return servidor(req);
});
