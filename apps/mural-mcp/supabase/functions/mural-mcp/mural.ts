// Regras do mural e as ferramentas MCP. Quem chama já está autenticado: `pessoa` vem do login GitHub.
import type { Banco, Cartao, Status, Tipo } from "./banco.ts";

export const TIPOS: Tipo[] = ["passagem", "pergunta", "aviso"];
export const STATUS: Status[] = ["novo", "lido", "feito"];
const CAIXAS = ["entrada", "enviados", "todos"] as const;
const FILTROS = ["abertos", "feitos", "tudo"] as const;
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;

export class ErroMural extends Error {}

function texto(valor: unknown, limite: number, campo: string, obrigatorio = true): string {
  const t = String(valor ?? "").trim();
  if (obrigatorio && !t) throw new ErroMural(`Preencha ${campo}.`);
  if (t.length > limite) throw new ErroMural(`${campo[0].toUpperCase()}${campo.slice(1)} passou de ${limite} caracteres.`);
  return t;
}

function id(valor: unknown): string {
  const v = String(valor ?? "").trim().toLowerCase();
  if (!UUID.test(v)) throw new ErroMural("Cartão inválido.");
  return v;
}

async function destinatario(banco: Banco, pessoa: string, para: unknown): Promise<string> {
  const outros = (await banco.pessoas()).filter((p) => p !== pessoa);
  if (para != null && para !== "") {
    const alvo = String(para).trim().toLowerCase();
    if (!outros.includes(alvo)) throw new ErroMural(`Ninguém chamado "${alvo}" no mural. Pessoas: ${outros.join(", ") || "nenhuma"}.`);
    return alvo;
  }
  if (outros.length !== 1) throw new ErroMural(`Diga para quem é o cartão em "para": ${outros.join(", ") || "não há mais ninguém no mural"}.`);
  return outros[0];
}

export async function ler(banco: Banco, pessoa: string, args: Record<string, unknown>) {
  if (args.id) {
    const cid = id(args.id);
    const cartao = await banco.cartao(cid);
    if (!cartao || (cartao.de !== pessoa && cartao.para !== pessoa)) throw new ErroMural("Cartão não encontrado.");
    if (cartao.para === pessoa && cartao.status === "novo") {
      await banco.atualizarCartao(cid, { status: "lido" }, "novo");
      cartao.status = "lido";
    }
    return { eu: pessoa, cartao: { ...cartao, respostas: await banco.respostas(cid) } };
  }
  const caixa = (args.caixa ?? "entrada") as (typeof CAIXAS)[number];
  const filtro = (args.filtro ?? "abertos") as (typeof FILTROS)[number];
  if (!CAIXAS.includes(caixa)) throw new ErroMural("Caixa inválida: use entrada, enviados ou todos.");
  if (!FILTROS.includes(filtro)) throw new ErroMural("Filtro inválido: use abertos, feitos ou tudo.");
  const cartoes = await banco.listar({ pessoa, caixa, filtro, limite: 30 });
  // Na lista vai só o começo do conteúdo; o cartão inteiro sai com "id"
  return {
    eu: pessoa,
    pessoas: (await banco.pessoas()).filter((p) => p !== pessoa),
    cartoes: cartoes.map((c) => ({ ...c, conteudo: c.conteudo.length > 400 ? c.conteudo.slice(0, 400) + "…" : c.conteudo })),
  };
}

export async function escrever(banco: Banco, pessoa: string, args: Record<string, unknown>, autor: "agente" | "humano" = "agente") {
  const tipo = String(args.tipo ?? "passagem") as Tipo;
  if (!TIPOS.includes(tipo)) throw new ErroMural("Tipo inválido: use passagem, pergunta ou aviso.");
  const cartao: Cartao = await banco.criarCartao({
    de: pessoa, para: await destinatario(banco, pessoa, args.para), autor, tipo,
    titulo: texto(args.titulo, 200, "o título"), conteudo: texto(args.conteudo, 50000, "o conteúdo", false),
  });
  return { ok: true, id: cartao.id, para: cartao.para };
}

export async function responder(banco: Banco, pessoa: string, args: Record<string, unknown>, autor: "agente" | "humano" = "agente") {
  const cid = id(args.id);
  if (!args.texto && !args.status) throw new ErroMural("Informe 'texto', 'status' ou os dois.");
  const cartao = await banco.cartao(cid);
  if (!cartao || (cartao.de !== pessoa && cartao.para !== pessoa)) throw new ErroMural("Cartão não encontrado.");
  const feito: Record<string, unknown> = { ok: true };
  if (args.texto) feito.resposta = (await banco.criarResposta({ cartao_id: cid, de: pessoa, autor, texto: texto(args.texto, 20000, "a resposta") })).id;
  if (args.status) {
    if (!STATUS.includes(args.status as Status)) throw new ErroMural("Status inválido: use novo, lido ou feito.");
    feito.status = (await banco.atualizarCartao(cid, { status: args.status as Status }))?.status;
  }
  return feito;
}

export const FERRAMENTAS = [
  {
    name: "ler",
    title: "Ler o mural",
    description:
      "Lê o mural de passagem compartilhado com o parceiro (o outro dono deste projeto) e o agente dele. " +
      "Sem 'id', lista os cartões; com 'id', abre um cartão com as respostas e o marca como lido. " +
      "Consulte a caixa 'entrada' ao começar uma tarefa: o parceiro deixa ali contexto, decisões e pedidos.",
    inputSchema: {
      type: "object",
      properties: {
        id: { type: "string", description: "Id do cartão para abrir por inteiro." },
        caixa: { type: "string", enum: [...CAIXAS], description: "entrada (para mim), enviados (que eu escrevi) ou todos. Padrão: entrada." },
        filtro: { type: "string", enum: [...FILTROS], description: "abertos (novo/lido), feitos ou tudo. Padrão: abertos." },
      },
    },
    annotations: { readOnlyHint: false, openWorldHint: false },
  },
  {
    name: "escrever",
    title: "Deixar um cartão",
    description:
      "Deixa um cartão no mural para o parceiro e o agente dele. Use para passar contexto que o outro lado precisa: " +
      "o que foi feito, decisões, onde parou, comandos, caminhos de arquivos e próximos passos. Escreva em pt-BR, " +
      "completo o bastante para ser lido sem esta conversa. Nunca inclua senhas ou chaves.",
    inputSchema: {
      type: "object",
      properties: {
        titulo: { type: "string", description: "Resumo em uma linha (até 200 caracteres)." },
        conteudo: { type: "string", description: "Corpo em Markdown." },
        tipo: { type: "string", enum: TIPOS, description: "passagem (entrega de trabalho), pergunta (precisa de resposta) ou aviso." },
        para: { type: "string", description: "Para quem (só se houver mais de uma pessoa no mural)." },
      },
      required: ["titulo", "conteudo"],
    },
    annotations: { readOnlyHint: false, destructiveHint: false, openWorldHint: false },
  },
  {
    name: "responder",
    title: "Responder ou fechar um cartão",
    description:
      "Responde a um cartão do mural e/ou muda o status dele. Marque 'feito' quando o pedido do cartão estiver " +
      "resolvido; use 'texto' para responder perguntas ou dizer o que foi feito.",
    inputSchema: {
      type: "object",
      properties: {
        id: { type: "string", description: "Id do cartão." },
        texto: { type: "string", description: "Resposta em Markdown (opcional se só mudar o status)." },
        status: { type: "string", enum: STATUS, description: "Novo status (opcional)." },
      },
      required: ["id"],
    },
    annotations: { readOnlyHint: false, destructiveHint: false, openWorldHint: false },
  },
];

type Executor = (banco: Banco, pessoa: string, args: Record<string, unknown>) => Promise<unknown>;
const EXECUTORES: Record<string, Executor> = { ler, escrever, responder };

export async function chamar(banco: Banco, pessoa: string, nome: string, args: Record<string, unknown>) {
  const executor = EXECUTORES[nome];
  if (!executor) return { content: [{ type: "text", text: `Ferramenta desconhecida: ${nome}` }], isError: true };
  try {
    const resultado = await executor(banco, pessoa, args ?? {});
    return { content: [{ type: "text", text: JSON.stringify(resultado) }] };
  } catch (erro) {
    const mensagem = erro instanceof ErroMural ? erro.message : `Falha inesperada no mural: ${(erro as Error).message}`;
    return { content: [{ type: "text", text: JSON.stringify({ erro: mensagem }) }], isError: true };
  }
}
