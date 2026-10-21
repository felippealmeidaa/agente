(function () {
"use strict";
// Mural de passagem: aba do painel do Hermes. JS puro (React.createElement), sem etapa de build.
const SDK = window.__HERMES_PLUGIN_SDK__;
const { React } = SDK;
const { useState, useEffect, useCallback, useRef, useMemo } = SDK.hooks;
const h = React.createElement;
const Fragment = React.Fragment;

const API = "/api/plugins/mural";
const INTERVALO = 8000;

const TIPOS = {
  passagem: { rotulo: "Passagem", dica: "Entrega de trabalho ou contexto" },
  pergunta: { rotulo: "Pergunta", dica: "Precisa de resposta" },
  aviso: { rotulo: "Aviso", dica: "Algo importante para saber" },
};
const STATUS = { novo: "Novo", lido: "Lido", feito: "Feito" };
const CAIXAS = [
  ["entrada", "Para mim"],
  ["enviados", "Enviados"],
  ["todos", "Todos"],
];
const FILTROS = [
  ["abertos", "Abertos"],
  ["feitos", "Feitos"],
  ["tudo", "Tudo"],
];

// --- Utilidades ---------------------------------------------------------------

function pedir(caminho, metodo, corpo) {
  const init = { method: metodo || "GET" };
  if (corpo !== undefined) {
    init.headers = { "Content-Type": "application/json" };
    init.body = JSON.stringify(corpo);
  }
  return SDK.fetchJSON(API + caminho, init);
}

function nome(pessoa) {
  return pessoa ? pessoa.charAt(0).toUpperCase() + pessoa.slice(1) : "";
}

function quem(pessoa, eu) {
  return pessoa === eu ? "Você" : nome(pessoa);
}

function quando(iso) {
  const data = new Date(iso);
  const seg = (Date.now() - data.getTime()) / 1000;
  if (seg < 45) return "agora";
  if (seg < 3600) return `há ${Math.round(seg / 60)} min`;
  if (seg < 86400) return `há ${Math.round(seg / 3600)} h`;
  const ontem = new Date();
  ontem.setDate(ontem.getDate() - 1);
  if (data.toDateString() === ontem.toDateString()) return "ontem";
  return data.toLocaleDateString("pt-BR", { day: "2-digit", month: "short" });
}

function quandoCompleto(iso) {
  return new Date(iso).toLocaleString("pt-BR", { dateStyle: "long", timeStyle: "short" });
}

function cx(...classes) {
  return classes.filter(Boolean).join(" ");
}

// --- Ícones (traços do Lucide) -------------------------------------------------

const ICONES = {
  mais: ["M5 12h14", "M12 5v14"],
  x: ["M18 6 6 18", "m6 6 12 12"],
  check: ["M20 6 9 17l-5-5"],
  pino: ["M12 17v5", "M9 10.76a2 2 0 0 1-1.11 1.79l-1.78.9A2 2 0 0 0 5 15.24V16a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1v-.76a2 2 0 0 0-1.11-1.79l-1.78-.9A2 2 0 0 1 15 10.76V7a1 1 0 0 1 1-1 2 2 0 0 0 0-4H8a2 2 0 0 0 0 4 1 1 0 0 1 1 1z"],
  reabrir: ["M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8", "M3 3v5h5"],
  lixo: ["M3 6h18", "M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6", "M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"],
  copiar: ["M8 8h12a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H10a2 2 0 0 1-2-2z", "M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2"],
  voltar: ["m12 19-7-7 7-7", "M19 12H5"],
  robo: ["M12 8V4H8", "M6 8h12a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2v-8a2 2 0 0 1 2-2z", "M2 14h2", "M20 14h2", "M15 13v2", "M9 13v2"],
  enviar: ["m22 2-7 20-4-9-9-4Z", "M22 2 11 13"],
  balao: ["M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"],
  caixa: ["M22 12h-6l-2 3h-4l-2-3H2", "M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z"],
  alerta: ["M12 9v4", "M12 17h.01", "M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"],
};

function Icone({ nome: n, tamanho }) {
  const t = tamanho || 16;
  return h(
    "svg",
    {
      width: t, height: t, viewBox: "0 0 24 24", fill: "none", stroke: "currentColor",
      strokeWidth: 2, strokeLinecap: "round", strokeLinejoin: "round", "aria-hidden": "true",
      className: "mural-icone",
    },
    ICONES[n].map((d) => h("path", { key: d, d })),
  );
}

// --- Markdown mínimo (sem HTML cru) ---------------------------------------------

function Inline({ texto }) {
  const partes = [];
  const padrao = /(`[^`\n]+`)|(\*\*[^*\n]+\*\*)|(\[[^\]\n]+\]\((https?:\/\/[^\s)]+)\))|(https?:\/\/[^\s<>()]+[^\s<>().,;:!?])/g;
  let ultimo = 0;
  let m;
  while ((m = padrao.exec(texto))) {
    if (m.index > ultimo) partes.push(texto.slice(ultimo, m.index));
    const k = m.index;
    if (m[1]) partes.push(h("code", { key: k }, m[1].slice(1, -1)));
    else if (m[2]) partes.push(h("strong", { key: k }, m[2].slice(2, -2)));
    else if (m[3]) {
      const rotulo = m[3].slice(1, m[3].indexOf("]("));
      partes.push(h("a", { key: k, href: m[4], target: "_blank", rel: "noreferrer" }, rotulo));
    } else partes.push(h("a", { key: k, href: m[5], target: "_blank", rel: "noreferrer" }, m[5]));
    ultimo = padrao.lastIndex;
  }
  if (ultimo < texto.length) partes.push(texto.slice(ultimo));
  return h(Fragment, null, ...partes);
}

function Markdown({ texto }) {
  const blocos = [];
  const linhas = (texto || "").replace(/\r\n/g, "\n").split("\n");
  let i = 0;
  let paragrafo = [];
  const fecharParagrafo = () => {
    if (paragrafo.length) {
      blocos.push(h("p", { key: `p${i}` }, paragrafo.flatMap((l, j) => (j ? [h("br", { key: j }), h(Inline, { key: `i${j}`, texto: l })] : [h(Inline, { key: `i${j}`, texto: l })]))));
      paragrafo = [];
    }
  };
  while (i < linhas.length) {
    const linha = linhas[i];
    if (/^```/.test(linha)) {
      fecharParagrafo();
      const codigo = [];
      i++;
      while (i < linhas.length && !/^```/.test(linhas[i])) codigo.push(linhas[i++]);
      i++;
      blocos.push(h("pre", { key: `c${i}` }, h("code", null, codigo.join("\n"))));
      continue;
    }
    const titulo = /^(#{1,3})\s+(.*)$/.exec(linha);
    if (titulo) {
      fecharParagrafo();
      blocos.push(h(`h${titulo[1].length + 2}`, { key: `h${i}` }, h(Inline, { texto: titulo[2] })));
      i++;
      continue;
    }
    if (/^\s*([-*]|\d+\.)\s+/.test(linha)) {
      fecharParagrafo();
      const numerada = /^\s*\d+\./.test(linha);
      const itens = [];
      while (i < linhas.length && /^\s*([-*]|\d+\.)\s+/.test(linhas[i])) {
        const item = linhas[i].replace(/^\s*([-*]|\d+\.)\s+/, "");
        const marcado = /^\[([ xX])\]\s+/.exec(item);
        itens.push(h("li", { key: i, className: marcado ? "mural-tarefa" : undefined },
          marcado ? h("span", { className: cx("mural-caixinha", marcado[1] !== " " && "mural-caixinha--ok") }) : null,
          h(Inline, { texto: marcado ? item.slice(marcado[0].length) : item })));
        i++;
      }
      blocos.push(h(numerada ? "ol" : "ul", { key: `l${i}` }, itens));
      continue;
    }
    if (/^>\s?/.test(linha)) {
      fecharParagrafo();
      const citacao = [];
      while (i < linhas.length && /^>\s?/.test(linhas[i])) citacao.push(linhas[i++].replace(/^>\s?/, ""));
      blocos.push(h("blockquote", { key: `q${i}` }, h(Inline, { texto: citacao.join(" ") })));
      continue;
    }
    if (!linha.trim()) fecharParagrafo();
    else paragrafo.push(linha);
    i++;
  }
  fecharParagrafo();
  return h("div", { className: "mural-md" }, blocos);
}

// --- Peças ------------------------------------------------------------------------

function Avatar({ pessoa, eu, autor }) {
  return h(
    "span",
    { className: cx("mural-avatar", pessoa === eu ? "mural-avatar--eu" : "mural-avatar--outro"), title: nome(pessoa) },
    autor === "agente" ? h(Icone, { nome: "robo", tamanho: 14 }) : nome(pessoa).charAt(0),
  );
}

function Origem({ cartao, eu }) {
  return h(
    "span",
    { className: "mural-origem" },
    quem(cartao.de, eu),
    cartao.autor === "agente" ? h("span", { className: "mural-tag-agente" }, h(Icone, { nome: "robo", tamanho: 12 }), "agente") : null,
    h("span", { className: "mural-seta" }, "→"),
    quem(cartao.para, eu),
  );
}

function Segmentos({ opcoes, valor, aoMudar, contagens, rotuloAria }) {
  return h(
    "div",
    { className: "mural-segmentos", role: "tablist", "aria-label": rotuloAria },
    opcoes.map(([id, rotulo]) =>
      h(
        "button",
        {
          key: id, type: "button", role: "tab", "aria-selected": valor === id,
          className: cx("mural-segmento", valor === id && "mural-segmento--ativo"),
          onClick: () => aoMudar(id),
        },
        rotulo,
        contagens && contagens[id] ? h("span", { className: "mural-contador" }, contagens[id]) : null,
      ),
    ),
  );
}

function ItemLista({ cartao, eu, ativo, aoAbrir }) {
  const novoParaMim = cartao.status === "novo" && cartao.para === eu;
  return h(
    "button",
    {
      type: "button",
      className: cx("mural-item", `mural-item--${cartao.tipo}`, ativo && "mural-item--ativo", cartao.status === "feito" && "mural-item--feito"),
      onClick: () => aoAbrir(cartao.id),
      "aria-current": ativo ? "true" : undefined,
    },
    h(
      "span",
      { className: "mural-item__topo" },
      h("span", { className: cx("mural-pilula", `mural-pilula--${cartao.tipo}`) }, TIPOS[cartao.tipo].rotulo),
      cartao.fixado ? h("span", { className: "mural-item__fixado", title: "Fixado" }, h(Icone, { nome: "pino", tamanho: 13 })) : null,
      h("span", { className: "mural-item__quando" }, quando(cartao.atualizado_em)),
    ),
    h(
      "span",
      { className: "mural-item__titulo" },
      novoParaMim ? h("span", { className: "mural-ponto", "aria-label": "Novo" }) : null,
      cartao.status === "feito" ? h("span", { className: "mural-item__ok" }, h(Icone, { nome: "check", tamanho: 14 })) : null,
      cartao.titulo,
    ),
    cartao.conteudo ? h("span", { className: "mural-item__previa" }, cartao.conteudo.replace(/[#*`>\[\]]/g, "").slice(0, 160)) : null,
    h(
      "span",
      { className: "mural-item__rodape" },
      h(Origem, { cartao, eu }),
      cartao.respostas ? h("span", { className: "mural-item__respostas" }, h(Icone, { nome: "balao", tamanho: 13 }), cartao.respostas) : null,
    ),
  );
}

function Vazio({ icone, titulo, texto, acao }) {
  return h(
    "div",
    { className: "mural-vazio" },
    h("span", { className: "mural-vazio__icone" }, h(Icone, { nome: icone, tamanho: 22 })),
    h("p", { className: "mural-vazio__titulo" }, titulo),
    texto ? h("p", { className: "mural-vazio__texto" }, texto) : null,
    acao || null,
  );
}

function Botao({ icone, children, variante, ...resto }) {
  return h(
    "button",
    { type: "button", className: cx("mural-botao", variante && `mural-botao--${variante}`), ...resto },
    icone ? h(Icone, { nome: icone, tamanho: 15 }) : null,
    children,
  );
}

// --- Detalhe -------------------------------------------------------------------

function Detalhe({ id, eu, aoVoltar, aoMudar, avisar }) {
  const [cartao, setCartao] = useState(null);
  const [erro, setErro] = useState(null);
  const [resposta, setResposta] = useState("");
  const [enviando, setEnviando] = useState(false);
  const [confirmarExclusao, setConfirmarExclusao] = useState(false);
  const fimRef = useRef(null);

  const carregar = useCallback(
    (silencioso) =>
      pedir(`/cartoes/${id}`)
        .then((c) => {
          setCartao(c);
          setErro(null);
          if (!silencioso) aoMudar();
        })
        .catch((e) => setErro(e.message)),
    [id, aoMudar],
  );

  useEffect(() => {
    setCartao(null);
    setResposta("");
    setConfirmarExclusao(false);
    carregar(false);
    const t = setInterval(() => document.visibilityState === "visible" && carregar(true), INTERVALO);
    return () => clearInterval(t);
  }, [id]);

  const acao = (promessa, mensagem) =>
    promessa
      .then(() => {
        if (mensagem) avisar(mensagem);
        aoMudar();
        return carregar(true);
      })
      .catch((e) => avisar(e.message, "erro"));

  const responder = () => {
    if (!resposta.trim() || enviando) return;
    setEnviando(true);
    pedir(`/cartoes/${id}/respostas`, "POST", { texto: resposta })
      .then(() => {
        setResposta("");
        aoMudar();
        return carregar(true).then(() => fimRef.current && fimRef.current.scrollIntoView({ behavior: "smooth", block: "end" }));
      })
      .catch((e) => avisar(e.message, "erro"))
      .finally(() => setEnviando(false));
  };

  if (erro && !cartao) return h(Vazio, { icone: "alerta", titulo: "Não deu para abrir o cartão", texto: erro });
  if (!cartao) return h("div", { className: "mural-carregando" }, h("span"), h("span"), h("span"));

  const feito = cartao.status === "feito";
  return h(
    "article",
    { className: "mural-detalhe", "aria-labelledby": "mural-detalhe-titulo" },
    h(
      "div",
      { className: "mural-detalhe__barra" },
      h(Botao, { icone: "voltar", variante: "fantasma", className: "mural-botao mural-botao--fantasma mural-so-celular", onClick: aoVoltar }, "Voltar"),
      h("span", { className: cx("mural-pilula", `mural-pilula--${cartao.tipo}`) }, TIPOS[cartao.tipo].rotulo),
      h("span", { className: cx("mural-status", `mural-status--${cartao.status}`) }, cartao.status === "novo" && cartao.de === eu ? "Não lido" : STATUS[cartao.status]),
      h("span", { className: "mural-espaco" }),
      h(Botao, {
        icone: "pino", variante: cartao.fixado ? "ligado" : "fantasma", title: cartao.fixado ? "Desafixar" : "Fixar no topo",
        "aria-pressed": cartao.fixado, onClick: () => acao(pedir(`/cartoes/${id}`, "PATCH", { fixado: !cartao.fixado })),
      }),
      h(Botao, {
        icone: "copiar", variante: "fantasma", title: "Copiar o id para pedir ao agente",
        onClick: () => navigator.clipboard.writeText(cartao.id).then(() => avisar("Id copiado. Peça ao agente: \"abra o cartão " + cartao.id.slice(0, 8) + "… do mural\".")),
      }),
      cartao.de === eu
        ? h(Botao, {
            icone: "lixo", variante: confirmarExclusao ? "perigo" : "fantasma", title: "Excluir",
            onClick: () => (confirmarExclusao ? acao(pedir(`/cartoes/${id}`, "DELETE"), "Cartão excluído.").then(aoVoltar) : setConfirmarExclusao(true)),
            onBlur: () => setConfirmarExclusao(false),
          }, confirmarExclusao ? "Confirmar" : null)
        : null,
    ),
    h("h2", { id: "mural-detalhe-titulo", className: "mural-detalhe__titulo" }, cartao.titulo),
    h(
      "div",
      { className: "mural-detalhe__meta" },
      h(Avatar, { pessoa: cartao.de, eu, autor: cartao.autor }),
      h(Origem, { cartao, eu }),
      h("span", { className: "mural-meta-sep" }, "·"),
      h("time", { dateTime: cartao.criado_em, title: quandoCompleto(cartao.criado_em) }, quando(cartao.criado_em)),
    ),
    cartao.conteudo ? h(Markdown, { texto: cartao.conteudo }) : h("p", { className: "mural-sem-conteudo" }, "Sem descrição."),
    h(
      "div",
      { className: "mural-detalhe__acoes" },
      feito
        ? h(Botao, { icone: "reabrir", onClick: () => acao(pedir(`/cartoes/${id}`, "PATCH", { status: "lido" }), "Cartão reaberto.") }, "Reabrir")
        : h(Botao, { icone: "check", variante: "primario", onClick: () => acao(pedir(`/cartoes/${id}`, "PATCH", { status: "feito" }), "Marcado como feito.") }, "Marcar como feito"),
    ),
    h(
      "section",
      { className: "mural-conversa", "aria-label": "Respostas" },
      h("h3", { className: "mural-conversa__titulo" }, cartao.respostas.length ? `Respostas (${cartao.respostas.length})` : "Respostas"),
      cartao.respostas.length === 0 ? h("p", { className: "mural-sem-conteudo" }, "Ninguém respondeu ainda.") : null,
      h(
        "ol",
        { className: "mural-respostas" },
        cartao.respostas.map((r) =>
          h(
            "li",
            { key: r.id, className: cx("mural-resposta", r.de === eu && "mural-resposta--eu") },
            h(Avatar, { pessoa: r.de, eu, autor: r.autor }),
            h(
              "div",
              { className: "mural-resposta__corpo" },
              h(
                "div",
                { className: "mural-resposta__cabeca" },
                h("strong", null, quem(r.de, eu)),
                r.autor === "agente" ? h("span", { className: "mural-tag-agente" }, h(Icone, { nome: "robo", tamanho: 12 }), "agente") : null,
                h("time", { dateTime: r.criado_em, title: quandoCompleto(r.criado_em) }, quando(r.criado_em)),
              ),
              h(Markdown, { texto: r.texto }),
            ),
          ),
        ),
      ),
      h(
        "form",
        {
          className: "mural-responder", ref: fimRef,
          onSubmit: (e) => {
            e.preventDefault();
            responder();
          },
        },
        h("label", { htmlFor: "mural-resposta", className: "mural-invisivel" }, "Sua resposta"),
        h("textarea", {
          id: "mural-resposta", value: resposta, rows: 3, placeholder: "Responder… (Ctrl+Enter envia)",
          onChange: (e) => setResposta(e.target.value),
          onKeyDown: (e) => {
            if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
              e.preventDefault();
              responder();
            }
          },
        }),
        h(Botao, { icone: "enviar", variante: "primario", type: "submit", disabled: !resposta.trim() || enviando }, enviando ? "Enviando…" : "Responder"),
      ),
    ),
  );
}

// --- Novo cartão ------------------------------------------------------------------

function NovoCartao({ parceiro, aoFechar, aoCriar, avisar }) {
  const [titulo, setTitulo] = useState("");
  const [conteudo, setConteudo] = useState("");
  const [tipo, setTipo] = useState("passagem");
  const [enviando, setEnviando] = useState(false);
  const tituloRef = useRef(null);

  useEffect(() => {
    tituloRef.current && tituloRef.current.focus();
    const esc = (e) => e.key === "Escape" && aoFechar();
    window.addEventListener("keydown", esc);
    return () => window.removeEventListener("keydown", esc);
  }, []);

  const enviar = (e) => {
    e && e.preventDefault();
    if (!titulo.trim() || enviando) return;
    setEnviando(true);
    pedir("/cartoes", "POST", { titulo, conteudo, tipo })
      .then((c) => {
        avisar(`Cartão enviado para ${nome(parceiro)}.`);
        aoCriar(c);
      })
      .catch((err) => {
        avisar(err.message, "erro");
        setEnviando(false);
      });
  };

  return h(
    "div",
    { className: "mural-fundo", onMouseDown: (e) => e.target === e.currentTarget && aoFechar() },
    h(
      "form",
      { className: "mural-janela", role: "dialog", "aria-modal": "true", "aria-labelledby": "mural-novo-titulo", onSubmit: enviar },
      h(
        "div",
        { className: "mural-janela__cabeca" },
        h("h2", { id: "mural-novo-titulo" }, `Novo cartão para ${nome(parceiro)}`),
        h(Botao, { icone: "x", variante: "fantasma", title: "Fechar", onClick: aoFechar }),
      ),
      h(
        "div",
        { className: "mural-tipos", role: "radiogroup", "aria-label": "Tipo" },
        Object.entries(TIPOS).map(([id, t]) =>
          h(
            "button",
            {
              key: id, type: "button", role: "radio", "aria-checked": tipo === id,
              className: cx("mural-tipo", `mural-tipo--${id}`, tipo === id && "mural-tipo--ativo"),
              onClick: () => setTipo(id),
            },
            h("span", { className: "mural-tipo__rotulo" }, t.rotulo),
            h("span", { className: "mural-tipo__dica" }, t.dica),
          ),
        ),
      ),
      h("label", { className: "mural-campo" },
        h("span", null, "Título"),
        h("input", { ref: tituloRef, value: titulo, maxLength: 200, placeholder: "Ex.: Login com Google pronto, falta o deploy", onChange: (e) => setTitulo(e.target.value) }),
      ),
      h("label", { className: "mural-campo" },
        h("span", null, "Conteúdo ", h("small", null, "aceita Markdown")),
        h("textarea", {
          value: conteudo, rows: 10, placeholder: "O que foi feito, onde parou, decisões, próximos passos…",
          onChange: (e) => setConteudo(e.target.value),
          onKeyDown: (e) => e.key === "Enter" && (e.ctrlKey || e.metaKey) && enviar(e),
        }),
      ),
      h(
        "div",
        { className: "mural-janela__rodape" },
        h(Botao, { variante: "fantasma", onClick: aoFechar }, "Cancelar"),
        h(Botao, { icone: "enviar", variante: "primario", type: "submit", disabled: !titulo.trim() || enviando }, enviando ? "Enviando…" : "Enviar"),
      ),
    ),
  );
}

// --- Configuração pendente --------------------------------------------------------

function Configurar({ faltando }) {
  const passo = (n, titulo, corpo) =>
    h("li", { className: "mural-passo" }, h("span", { className: "mural-passo__n" }, n), h("div", null, h("strong", null, titulo), corpo));
  return h(
    "div",
    { className: "mural-configurar" },
    h("h2", null, "Falta configurar o mural"),
    h("p", { className: "mural-sem-conteudo" }, "Falta: ", faltando.join(", ") + "."),
    h(
      "ol",
      null,
      passo(1, "Crie o banco", h("p", null, "Num projeto Supabase (um só para os dois), rode ", h("code", null, "plugins/mural/supabase.sql"), " no SQL Editor.")),
      passo(2, "Guarde a chave no .env do Hermes", h("pre", null, h("code", null, "MURAL_SUPABASE_URL=https://<ref>.supabase.co\nMURAL_SUPABASE_CHAVE=sb_secret_..."))),
      passo(3, "Diga quem é quem no config.yaml", h("pre", null, h("code", null, "plugins:\n  entries:\n    mural:\n      settings:\n        eu: guilherme\n        parceiro: felipe"))),
      passo(4, "Ative e recarregue", h("pre", null, h("code", null, "hermes plugins enable mural"))),
    ),
  );
}

// --- Página ------------------------------------------------------------------------

function Mural() {
  const [estado, setEstado] = useState(null);
  const [caixa, setCaixa] = useState("entrada");
  const [filtro, setFiltro] = useState("abertos");
  const [cartoes, setCartoes] = useState(null);
  const [erro, setErro] = useState(null);
  const [aberto, setAberto] = useState(null);
  const [compondo, setCompondo] = useState(false);
  const [aviso, setAviso] = useState(null);
  const avisoRef = useRef(null);

  const avisar = useCallback((texto, tipo) => {
    setAviso({ texto, tipo: tipo || "ok" });
    clearTimeout(avisoRef.current);
    avisoRef.current = setTimeout(() => setAviso(null), 4000);
  }, []);

  const carregarEstado = useCallback(
    () => pedir("/estado").then(setEstado).catch((e) => setEstado({ configurado: true, erro: e.message })),
    [],
  );

  const carregarLista = useCallback(
    () =>
      pedir(`/cartoes?caixa=${caixa}&filtro=${filtro}`)
        .then((r) => {
          setCartoes(r.cartoes);
          setErro(null);
        })
        .catch((e) => setErro(e.message)),
    [caixa, filtro],
  );

  const atualizarTudo = useCallback(() => {
    carregarEstado();
    carregarLista();
  }, [carregarEstado, carregarLista]);

  useEffect(() => {
    carregarEstado();
  }, []);

  useEffect(() => {
    if (!estado || !estado.configurado || !estado.eu) return undefined;
    setCartoes(null);
    carregarLista();
    const t = setInterval(() => document.visibilityState === "visible" && atualizarTudo(), INTERVALO);
    return () => clearInterval(t);
  }, [estado && estado.eu, caixa, filtro]);

  const contagens = useMemo(() => (estado && estado.novos ? { entrada: estado.novos } : null), [estado]);

  if (!estado) return h("div", { className: "mural" }, h("div", { className: "mural-carregando" }, h("span"), h("span"), h("span")));
  if (!estado.configurado) return h("div", { className: "mural" }, h(Configurar, { faltando: estado.faltando || [] }));

  const { eu, parceiro } = estado;
  const lista = erro
    ? h(Vazio, { icone: "alerta", titulo: "Não deu para carregar o mural", texto: erro, acao: h(Botao, { onClick: carregarLista }, "Tentar de novo") })
    : cartoes === null
      ? h("div", { className: "mural-carregando" }, h("span"), h("span"), h("span"))
      : cartoes.length === 0
        ? h(Vazio, {
            icone: "caixa",
            titulo: caixa === "entrada" ? (filtro === "feitos" ? "Nada marcado como feito" : "Nada pendente para você") : "Nenhum cartão aqui",
            texto: caixa === "entrada" ? `Quando ${nome(parceiro)} ou o agente dele deixar algo, aparece aqui.` : null,
          })
        : h(
            "div",
            { className: "mural-lista__itens" },
            cartoes.map((c) => h(ItemLista, { key: c.id, cartao: c, eu, ativo: c.id === aberto, aoAbrir: setAberto })),
          );

  return h(
    "div",
    { className: cx("mural", aberto && "mural--com-detalhe") },
    h(
      "header",
      { className: "mural-cabeca" },
      h(
        "div",
        null,
        h("h1", { className: "mural-cabeca__titulo" }, "Mural"),
        h("p", { className: "mural-cabeca__sub" },
          "Passagens entre você e ", h("strong", null, nome(parceiro)), ". Os agentes leem e escrevem aqui também."),
      ),
      h(Botao, { icone: "mais", variante: "primario", onClick: () => setCompondo(true) }, "Novo cartão"),
    ),
    estado.erro ? h("p", { className: "mural-faixa-erro", role: "alert" }, h(Icone, { nome: "alerta", tamanho: 15 }), estado.erro) : null,
    h(
      "div",
      { className: "mural-corpo" },
      h(
        "section",
        { className: "mural-lista", "aria-label": "Cartões" },
        h(
          "div",
          { className: "mural-filtros" },
          h(Segmentos, { opcoes: CAIXAS, valor: caixa, aoMudar: (v) => { setCaixa(v); setAberto(null); }, contagens, rotuloAria: "Caixa" }),
          h(Segmentos, { opcoes: FILTROS, valor: filtro, aoMudar: (v) => { setFiltro(v); setAberto(null); }, rotuloAria: "Situação" }),
        ),
        lista,
      ),
      h(
        "section",
        { className: "mural-painel", "aria-label": "Cartão aberto" },
        aberto
          ? h(Detalhe, { key: aberto, id: aberto, eu, aoVoltar: () => setAberto(null), aoMudar: atualizarTudo, avisar })
          : h(Vazio, { icone: "balao", titulo: "Escolha um cartão", texto: "Abra um cartão para ler, responder ou marcar como feito." }),
      ),
    ),
    compondo
      ? h(NovoCartao, {
          parceiro, avisar, aoFechar: () => setCompondo(false),
          aoCriar: (c) => {
            setCompondo(false);
            setCaixa("enviados");
            setFiltro("abertos");
            setAberto(c.id);
          },
        })
      : null,
    aviso ? h("div", { className: cx("mural-aviso", aviso.tipo === "erro" && "mural-aviso--erro"), role: "status" }, aviso.texto) : null,
  );
}

window.__HERMES_PLUGINS__.register("mural", Mural);
})();
