// Onde o servidor guarda tudo: o mural (cartões e respostas) e o estado do login OAuth.
// `BancoMemoria` serve aos testes; `banco_supabase.ts` é o de produção.

export type Tipo = "passagem" | "pergunta" | "aviso";
export type Status = "novo" | "lido" | "feito";
export type Autor = "humano" | "agente";

export interface Cartao {
  id: string;
  criado_em: string;
  atualizado_em: string;
  de: string;
  para: string;
  autor: Autor;
  tipo: Tipo;
  status: Status;
  fixado: boolean;
  titulo: string;
  conteudo: string;
}

export interface Resposta {
  id: string;
  cartao_id: string;
  criado_em: string;
  de: string;
  autor: Autor;
  texto: string;
}

export interface FiltroLista {
  pessoa: string;
  caixa: "entrada" | "enviados" | "todos";
  filtro: "abertos" | "feitos" | "tudo";
  limite: number;
}

export interface ClienteOAuth {
  client_id: string;
  redirect_uris: string[];
  client_name: string;
  criado_em: string;
}

export interface Pendente {
  estado: string; // o state que mandamos ao GitHub
  client_id: string;
  redirect_uri: string;
  code_challenge: string;
  estado_cliente: string;
  expira_em: number;
}

export interface Codigo {
  hash: string;
  client_id: string;
  redirect_uri: string;
  code_challenge: string;
  pessoa: string;
  expira_em: number;
}

export interface Token {
  hash: string;
  tipo: "acesso" | "renovacao";
  client_id: string;
  pessoa: string;
  expira_em: number;
}

export interface Banco {
  pessoaDoGithub(login: string): Promise<string | null>;
  pessoas(): Promise<string[]>;

  salvarCliente(c: ClienteOAuth): Promise<void>;
  cliente(id: string): Promise<ClienteOAuth | null>;
  salvarPendente(p: Pendente): Promise<void>;
  tomarPendente(estado: string): Promise<Pendente | null>; // lê e apaga (uso único)
  salvarCodigo(c: Codigo): Promise<void>;
  tomarCodigo(hash: string): Promise<Codigo | null>;
  salvarToken(t: Token): Promise<void>;
  token(hash: string): Promise<Token | null>;
  apagarToken(hash: string): Promise<void>;

  listar(f: FiltroLista): Promise<(Cartao & { respostas: number })[]>;
  cartao(id: string): Promise<Cartao | null>;
  respostas(cartaoId: string): Promise<Resposta[]>;
  criarCartao(c: Omit<Cartao, "id" | "criado_em" | "atualizado_em" | "status" | "fixado">): Promise<Cartao>;
  atualizarCartao(id: string, mudancas: Partial<Pick<Cartao, "status" | "fixado">>, soSeStatus?: Status): Promise<Cartao | null>;
  criarResposta(r: Omit<Resposta, "id" | "criado_em">): Promise<Resposta>;
}

export class BancoMemoria implements Banco {
  githubs = new Map<string, string>();
  clientes = new Map<string, ClienteOAuth>();
  pendentes = new Map<string, Pendente>();
  codigos = new Map<string, Codigo>();
  tokens = new Map<string, Token>();
  cartoes: Cartao[] = [];
  lista_respostas: Resposta[] = [];
  private relogio = 0;

  constructor(githubs: Record<string, string> = {}) {
    for (const [login, pessoa] of Object.entries(githubs)) this.githubs.set(login.toLowerCase(), pessoa);
  }

  private agora() {
    return new Date(Date.UTC(2026, 9, 20, 12, 0, 0) + ++this.relogio * 1000).toISOString();
  }

  async pessoaDoGithub(login: string) {
    return this.githubs.get(login.toLowerCase()) ?? null;
  }
  async pessoas() {
    return [...new Set(this.githubs.values())].sort();
  }

  async salvarCliente(c: ClienteOAuth) {
    this.clientes.set(c.client_id, c);
  }
  async cliente(id: string) {
    return this.clientes.get(id) ?? null;
  }
  async salvarPendente(p: Pendente) {
    this.pendentes.set(p.estado, p);
  }
  async tomarPendente(estado: string) {
    const p = this.pendentes.get(estado) ?? null;
    this.pendentes.delete(estado);
    return p;
  }
  async salvarCodigo(c: Codigo) {
    this.codigos.set(c.hash, c);
  }
  async tomarCodigo(hash: string) {
    const c = this.codigos.get(hash) ?? null;
    this.codigos.delete(hash);
    return c;
  }
  async salvarToken(t: Token) {
    this.tokens.set(t.hash, t);
  }
  async token(hash: string) {
    return this.tokens.get(hash) ?? null;
  }
  async apagarToken(hash: string) {
    this.tokens.delete(hash);
  }

  async listar(f: FiltroLista) {
    return this.cartoes
      .filter((c) => (f.caixa === "entrada" ? c.para === f.pessoa : f.caixa === "enviados" ? c.de === f.pessoa : c.de === f.pessoa || c.para === f.pessoa))
      .filter((c) => (f.filtro === "abertos" ? c.status !== "feito" : f.filtro === "feitos" ? c.status === "feito" : true))
      .sort((a, b) => Number(b.fixado) - Number(a.fixado) || (a.atualizado_em < b.atualizado_em ? 1 : -1))
      .slice(0, f.limite)
      .map((c) => ({ ...c, respostas: this.lista_respostas.filter((r) => r.cartao_id === c.id).length }));
  }
  async cartao(id: string) {
    const c = this.cartoes.find((x) => x.id === id);
    return c ? { ...c } : null;
  }
  async respostas(cartaoId: string) {
    return this.lista_respostas.filter((r) => r.cartao_id === cartaoId);
  }
  async criarCartao(dados: Omit<Cartao, "id" | "criado_em" | "atualizado_em" | "status" | "fixado">) {
    const agora = this.agora();
    const c: Cartao = { ...dados, id: crypto.randomUUID(), criado_em: agora, atualizado_em: agora, status: "novo", fixado: false };
    this.cartoes.push(c);
    return { ...c };
  }
  async atualizarCartao(id: string, mudancas: Partial<Pick<Cartao, "status" | "fixado">>, soSeStatus?: Status) {
    const c = this.cartoes.find((x) => x.id === id);
    if (!c || (soSeStatus && c.status !== soSeStatus)) return null;
    Object.assign(c, mudancas, { atualizado_em: this.agora() });
    return { ...c };
  }
  async criarResposta(dados: Omit<Resposta, "id" | "criado_em">) {
    const r: Resposta = { ...dados, id: crypto.randomUUID(), criado_em: this.agora() };
    this.lista_respostas.push(r);
    const c = this.cartoes.find((x) => x.id === dados.cartao_id);
    if (c) c.atualizado_em = r.criado_em;
    return r;
  }
}
