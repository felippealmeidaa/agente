// Banco de produção: tabelas do mural e do OAuth no mesmo projeto Supabase, acessadas com a chave
// de serviço que o próprio Supabase injeta na Edge Function (ninguém copia essa chave).
import { createClient, type SupabaseClient } from "npm:@supabase/supabase-js@2.45.4";
import type { Banco, Cartao, ClienteOAuth, Codigo, FiltroLista, Pendente, Resposta, Status, Token } from "./banco.ts";

const segundos = (iso: string) => Math.floor(new Date(iso).getTime() / 1000);
const iso = (s: number) => new Date(s * 1000).toISOString();

export class BancoSupabase implements Banco {
  private db: SupabaseClient;

  constructor(url: string, chaveServico: string) {
    this.db = createClient(url, chaveServico, { auth: { persistSession: false, autoRefreshToken: false } });
  }

  private falhou(erro: { message: string } | null) {
    if (erro) throw new Error(erro.message);
  }

  async pessoaDoGithub(login: string) {
    const { data, error } = await this.db.from("mural_pessoas").select("pessoa").ilike("github", login).maybeSingle();
    this.falhou(error);
    return data?.pessoa ?? null;
  }

  async pessoas() {
    const { data, error } = await this.db.from("mural_pessoas").select("pessoa");
    this.falhou(error);
    return [...new Set((data ?? []).map((r) => r.pessoa as string))].sort();
  }

  async salvarCliente(c: ClienteOAuth) {
    this.falhou((await this.db.from("mural_oauth_clientes").insert({ client_id: c.client_id, redirect_uris: c.redirect_uris, client_name: c.client_name })).error);
  }

  async cliente(id: string) {
    const { data, error } = await this.db.from("mural_oauth_clientes").select("*").eq("client_id", id).maybeSingle();
    this.falhou(error);
    return data ? { client_id: data.client_id, redirect_uris: data.redirect_uris, client_name: data.client_name, criado_em: data.criado_em } : null;
  }

  async salvarPendente(p: Pendente) {
    this.falhou((await this.db.from("mural_oauth_pendentes").insert({ ...p, expira_em: iso(p.expira_em) })).error);
  }

  async tomarPendente(estado: string) {
    const { data, error } = await this.db.from("mural_oauth_pendentes").delete().eq("estado", estado).select().maybeSingle();
    this.falhou(error);
    return data ? { ...data, expira_em: segundos(data.expira_em) } as Pendente : null;
  }

  async salvarCodigo(c: Codigo) {
    this.falhou((await this.db.from("mural_oauth_codigos").insert({ ...c, expira_em: iso(c.expira_em) })).error);
  }

  async tomarCodigo(hash: string) {
    const { data, error } = await this.db.from("mural_oauth_codigos").delete().eq("hash", hash).select().maybeSingle();
    this.falhou(error);
    return data ? { ...data, expira_em: segundos(data.expira_em) } as Codigo : null;
  }

  async salvarToken(t: Token) {
    this.falhou((await this.db.from("mural_oauth_tokens").insert({ ...t, expira_em: iso(t.expira_em) })).error);
  }

  async token(hash: string) {
    const { data, error } = await this.db.from("mural_oauth_tokens").select("*").eq("hash", hash).maybeSingle();
    this.falhou(error);
    return data ? { ...data, expira_em: segundos(data.expira_em) } as Token : null;
  }

  async apagarToken(hash: string) {
    this.falhou((await this.db.from("mural_oauth_tokens").delete().eq("hash", hash)).error);
  }

  async listar(f: FiltroLista) {
    let q = this.db.from("mural_cartoes").select("*, mural_respostas(count)")
      .order("fixado", { ascending: false }).order("atualizado_em", { ascending: false }).limit(f.limite);
    if (f.caixa === "entrada") q = q.eq("para", f.pessoa);
    else if (f.caixa === "enviados") q = q.eq("de", f.pessoa);
    else q = q.or(`de.eq.${f.pessoa},para.eq.${f.pessoa}`);
    if (f.filtro === "abertos") q = q.in("status", ["novo", "lido"]);
    else if (f.filtro === "feitos") q = q.eq("status", "feito");
    const { data, error } = await q;
    this.falhou(error);
    return (data ?? []).map(({ mural_respostas, ...c }) => ({ ...(c as Cartao), respostas: mural_respostas?.[0]?.count ?? 0 }));
  }

  async cartao(id: string) {
    const { data, error } = await this.db.from("mural_cartoes").select("*").eq("id", id).maybeSingle();
    this.falhou(error);
    return (data as Cartao) ?? null;
  }

  async respostas(cartaoId: string) {
    const { data, error } = await this.db.from("mural_respostas").select("*").eq("cartao_id", cartaoId).order("criado_em");
    this.falhou(error);
    return (data ?? []) as Resposta[];
  }

  async criarCartao(c: Omit<Cartao, "id" | "criado_em" | "atualizado_em" | "status" | "fixado">) {
    const { data, error } = await this.db.from("mural_cartoes").insert(c).select().single();
    this.falhou(error);
    return data as Cartao;
  }

  async atualizarCartao(id: string, mudancas: Partial<Pick<Cartao, "status" | "fixado">>, soSeStatus?: Status) {
    let q = this.db.from("mural_cartoes").update({ ...mudancas, atualizado_em: new Date().toISOString() }).eq("id", id);
    if (soSeStatus) q = q.eq("status", soSeStatus);
    const { data, error } = await q.select().maybeSingle();
    this.falhou(error);
    return (data as Cartao) ?? null;
  }

  async criarResposta(r: Omit<Resposta, "id" | "criado_em">) {
    const { data, error } = await this.db.from("mural_respostas").insert(r).select().single();
    this.falhou(error);
    return data as Resposta;
  }
}
