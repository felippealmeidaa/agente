// Telas do Controle do Hermes: Agora, Permissões, Atividade e Mural.
(function () {
  "use strict";
  const R = window.React;
  const { useState, useEffect, useCallback, useRef, useMemo } = R;
  const h = R.createElement;
  const api = window.controle;

  const MODOS = [
    ["livre", "Livre"],
    ["perguntar", "Perguntar"],
    ["bloqueado", "Bloqueado"],
  ];
  const DECISOES = {
    bloqueado: ["Bloqueado", "ruim"],
    negar: ["Negado", "ruim"],
    once: ["Permitido uma vez", "bom"],
    sessao: ["Permitido na sessão", "bom"],
    tempo: ["Sem resposta", "ruim"],
    fechado: ["App fechado", "ruim"],
  };
  const VAZAMENTO = [
    ["perguntar", "Perguntar"],
    ["bloquear", "Bloquear"],
    ["desligado", "Desligado"],
  ];

  // "terminal:git push" -> "git push"; "navegador:github.com" -> "github.com"
  function rotuloPadrao(padrao) {
    const [tipo, ...resto] = String(padrao || "").split(":");
    const valor = resto.join(":");
    return tipo === "escrita" ? `arquivos em ${valor}` : valor;
  }

  function cx(...c) {
    return c.filter(Boolean).join(" ");
  }

  // --- Ícones (traços do Lucide) -----------------------------------------------------------
  const ICONES = {
    agora: ["M22 12h-4l-3 9L9 3l-3 9H2"],
    escudo: ["M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z"],
    lista: ["M3 12h.01", "M3 18h.01", "M3 6h.01", "M8 12h13", "M8 18h13", "M8 6h13"],
    balao: ["M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"],
    pausa: ["M14 4h4v16h-4z", "M6 4h4v16H6z"],
    play: ["M6 3l14 9-14 9z"],
    parar: ["M5 5h14v14H5z"],
    check: ["M20 6 9 17l-5-5"],
    x: ["M18 6 6 18", "m6 6 12 12"],
    pasta: ["M20 20a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9a2 2 0 0 1-1.69-.9L9.6 3.9A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2Z"],
    mais: ["M5 12h14", "M12 5v14"],
    alerta: ["M12 9v4", "M12 17h.01", "M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"],
    terminal: ["m4 17 6-6-6-6", "M12 19h8"],
    esquerda: ["m15 18-6-6 6-6"],
    direita: ["m9 18 6-6-6-6"],
    relogio: ["M12 6v6l4 2", "M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20z"],
  };

  function Icone({ nome, tamanho }) {
    const t = tamanho || 16;
    return h("svg", { width: t, height: t, viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: 2, strokeLinecap: "round", strokeLinejoin: "round", "aria-hidden": "true", className: "c-icone" },
      ICONES[nome].map((d) => h("path", { key: d, d })));
  }

  function Botao({ icone, children, variante, className, ...resto }) {
    return h("button", { type: "button", className: cx("c-botao", variante && `c-botao--${variante}`, className), ...resto },
      icone ? h(Icone, { nome: icone, tamanho: 16 }) : null, children);
  }

  function hora(iso) {
    return new Date(iso).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  }

  function dataLonga(dia) {
    const [a, m, d] = dia.split("-").map(Number);
    return new Date(a, m - 1, d).toLocaleDateString("pt-BR", { weekday: "long", day: "numeric", month: "long" });
  }

  function useTique(ms) {
    const [, set] = useState(0);
    useEffect(() => {
      const t = setInterval(() => set((n) => n + 1), ms);
      return () => clearInterval(t);
    }, [ms]);
  }

  // --- Agora -----------------------------------------------------------------------------------

  function Pedido({ pedido, categorias, avisar }) {
    useTique(1000);
    const [negando, setNegando] = useState(false);
    const [nota, setNota] = useState("");
    const [enviando, setEnviando] = useState(false);
    const restante = Math.max(0, pedido.expira_em - Date.now() / 1000);
    const total = Math.max(1, pedido.expira_em - new Date(pedido.criado_em).getTime() / 1000);
    const cat = categorias.find((c) => c.id === pedido.categoria);

    const decidir = (decisao) => {
      setEnviando(true);
      api.responder(pedido.id, decisao, decisao === "negar" ? nota : "").then((r) => {
        if (!r.ok) {
          avisar(r.mensagem, "erro");
          setEnviando(false);
        } else if (decisao === "sempre") avisar(`Lembrado: ${rotuloPadrao(pedido.padrao)} roda sem perguntar.`);
        else if (decisao === "nunca") avisar(`Lembrado: ${rotuloPadrao(pedido.padrao)} fica sempre bloqueado.`);
      });
    };
    const lembravel = pedido.padrao && pedido.risco !== "alto" && !pedido.vazamento;

    return h("article", { className: cx("c-pedido", pedido.risco === "alto" && "c-pedido--alto", pedido.vazamento && "c-pedido--vazamento"), "aria-label": `Pedido: ${pedido.ferramenta}` },
      h("div", { className: "c-pedido__topo" },
        h("span", { className: "c-pilula c-pilula--perguntar" }, cat ? cat.nome : pedido.nome_categoria),
        pedido.risco === "alto" ? h("span", { className: "c-pilula c-pilula--alto" }, "Risco alto") : null,
        pedido.vazamento ? h("span", { className: "c-pilula c-pilula--alto" }, "Possível vazamento") : null,
        h("code", { className: "c-pedido__ferramenta" }, pedido.ferramenta),
        h("span", { className: "c-pedido__tempo", title: "Sem resposta, a ação é bloqueada" }, h(Icone, { nome: "relogio", tamanho: 14 }), `${Math.ceil(restante)} s`)),
      h("div", { className: "c-barra" }, h("span", { style: { transform: `scaleX(${restante / total})` } })),
      pedido.motivo && pedido.motivo !== (cat && cat.nome) ? h("p", { className: "c-pedido__motivo" }, pedido.motivo.charAt(0).toUpperCase() + pedido.motivo.slice(1) + ".") : null,
      h("pre", { className: "c-pedido__resumo" }, pedido.resumo || "(sem detalhes)"),
      h("p", { className: "c-pedido__meta" }, `Sessão ${String(pedido.sessao || "—").slice(0, 18)} · processo ${pedido.processo}`),
      negando
        ? h("form", { className: "c-pedido__negar", onSubmit: (e) => { e.preventDefault(); decidir("negar"); } },
            h("label", { className: "c-invisivel", htmlFor: `nota-${pedido.id}` }, "Motivo para o agente"),
            h("input", { id: `nota-${pedido.id}`, autoFocus: true, value: nota, maxLength: 500, placeholder: "Motivo para o agente (opcional): ex. use a pasta de testes", onChange: (e) => setNota(e.target.value) }),
            h(Botao, { variante: "perigo", type: "submit", disabled: enviando }, "Negar"),
            h(Botao, { variante: "fantasma", onClick: () => setNegando(false) }, "Voltar"))
        : h(R.Fragment, null,
            h("div", { className: "c-pedido__acoes" },
              h(Botao, { icone: "check", variante: "primario", disabled: enviando, onClick: () => decidir("once") }, "Permitir uma vez"),
              pedido.risco !== "alto" && !pedido.vazamento
                ? h(Botao, { disabled: enviando, onClick: () => decidir("sessao"), title: `Libera "${cat ? cat.nome : pedido.categoria}" até essa sessão terminar` }, "Permitir nesta sessão")
                : null,
              h(Botao, { icone: "x", variante: "perigo-suave", disabled: enviando, onClick: () => setNegando(true) }, "Negar")),
            lembravel
              ? h("div", { className: "c-pedido__lembrar" },
                  h("span", { className: "c-apagado" }, "Para ", h("code", null, rotuloPadrao(pedido.padrao)), ":"),
                  h("button", { type: "button", className: "c-link", disabled: enviando, onClick: () => decidir("sempre") }, "sempre permitir"),
                  h("button", { type: "button", className: "c-link", disabled: enviando, onClick: () => decidir("nunca") }, "sempre negar"))
              : pedido.risco === "alto"
                ? h("p", { className: "c-pedido__meta" }, "Ações de risco alto mexem no sistema e sempre pedem aprovação. Confira o comando inteiro antes de permitir.")
                : null));
  }

  function Status({ politica, pedidos, processos, aoPausar, aoPararTudo }) {
    const [confirmar, setConfirmar] = useState(false);
    useEffect(() => {
      if (!confirmar) return undefined;
      const t = setTimeout(() => setConfirmar(false), 4000);
      return () => clearTimeout(t);
    }, [confirmar]);
    const estado = politica.parado ? "pausado" : "livre";
    return h("section", { className: cx("c-status", `c-status--${estado}`), "aria-live": "polite" },
      h("div", { className: "c-status__texto" },
        h("span", { className: "c-status__rotulo" }, h("span", { className: "c-status__ponto" }), politica.parado ? "Agente pausado" : "Agente liberado"),
        h("p", null, politica.parado
          ? "Toda ferramenta é bloqueada até você retomar. O agente recebe o aviso e para de agir."
          : `Seguindo suas permissões. ${pedidos.length ? `${pedidos.length} ${pedidos.length === 1 ? "ação espera" : "ações esperam"} você.` : "Nada esperando aprovação."} ${processos === null ? "" : `${processos.length} processo${processos.length === 1 ? "" : "s"} do Hermes rodando.`}`)),
      h("div", { className: "c-status__acoes" },
        politica.parado
          ? h(Botao, { icone: "play", variante: "primario", onClick: () => aoPausar(false) }, "Retomar")
          : h(Botao, { icone: "pausa", onClick: () => aoPausar(true) }, "Pausar agente"),
        h(Botao, {
          icone: "parar", variante: confirmar ? "perigo" : "perigo-suave",
          title: "Pausa o agente e encerra todos os processos do Hermes neste PC",
          onClick: () => (confirmar ? (setConfirmar(false), aoPararTudo()) : setConfirmar(true)),
        }, confirmar ? "Confirmar: parar tudo" : "Parar tudo")));
  }

  function Agora({ info, pedidos, avisar, irPara }) {
    const [processos, setProcessos] = useState(null);
    const [recentes, setRecentes] = useState([]);
    const carregar = useCallback(() => {
      api.processos().then((r) => r.ok && setProcessos(r.dados));
      api.atividade().then((r) => r.ok && setRecentes(r.dados.eventos.slice(0, 6)));
    }, []);
    useEffect(() => {
      carregar();
      const t = setInterval(carregar, 4000);
      return () => clearInterval(t);
    }, []);

    const pausar = (parado) => api.pausar(parado).then((r) => (r.ok ? avisar(parado ? "Agente pausado." : "Agente retomado.") : avisar(r.mensagem, "erro")));
    const pararTudo = () => api.pararTudo().then((r) => {
      if (!r.ok) return avisar(r.mensagem, "erro");
      avisar(`Agente pausado. ${r.dados.encerrados.length} processo(s) encerrado(s).`);
      carregar();
    });
    const encerrar = (pid) => api.encerrar(pid).then((r) => {
      avisar(r.ok ? `Processo ${pid} encerrado.` : r.mensagem, r.ok ? "ok" : "erro");
      carregar();
    });

    return h("div", { className: "c-pagina" },
      h("header", { className: "c-cabeca" }, h("h1", null, "Agora")),
      h(Status, { politica: info.politica, pedidos, processos, aoPausar: pausar, aoPararTudo: pararTudo }),
      h(Alertas, { info }),
      h("section", { className: "c-secao", "aria-labelledby": "t-pedidos" },
        h("h2", { id: "t-pedidos", className: "c-secao__titulo" }, "Esperando você", pedidos.length ? h("span", { className: "c-contador" }, pedidos.length) : null),
        pedidos.length
          ? h("div", { className: "c-pedidos" }, pedidos.map((p) => h(Pedido, { key: p.id, pedido: p, categorias: info.categorias, avisar })))
          : h("p", { className: "c-vazio" }, "Quando o agente quiser fazer algo que está em “Perguntar”, o pedido aparece aqui e numa notificação do Windows.")),
      h("div", { className: "c-duas" },
        h("section", { className: "c-secao", "aria-labelledby": "t-proc" },
          h("h2", { id: "t-proc", className: "c-secao__titulo" }, "Processos do Hermes"),
          processos === null
            ? h("p", { className: "c-vazio" }, "Procurando…")
            : processos.length === 0
              ? h("p", { className: "c-vazio" }, "Nenhum processo do Hermes rodando neste PC.")
              : h("ul", { className: "c-processos" }, processos.map((p) =>
                  h("li", { key: p.pid },
                    h("div", null, h("strong", null, p.tipo), h("span", { className: "c-mono c-apagado" }, ` PID ${p.pid}`),
                      h("p", { className: "c-mono c-processos__cmd", title: p.comando }, p.comando)),
                    h(Botao, { variante: "perigo-suave", onClick: () => encerrar(p.pid) }, "Encerrar"))))),
        h("section", { className: "c-secao", "aria-labelledby": "t-rec" },
          h("div", { className: "c-secao__linha" },
            h("h2", { id: "t-rec", className: "c-secao__titulo" }, "Últimas ações"),
            h("button", { type: "button", className: "c-link", onClick: () => irPara("atividade") }, "Ver tudo")),
          recentes.length
            ? h("ul", { className: "c-recentes" }, recentes.map((e, i) => h(LinhaAtividade, { key: i, evento: e, categorias: info.categorias, compacta: true })))
            : h("p", { className: "c-vazio" }, "Nada ainda hoje."))));
  }

  function Alertas({ info }) {
    const itens = [];
    if (!info.pluginsAtivos.includes("controle")) {
      itens.push(h("li", { key: "p" }, "O plugin ", h("code", null, "controle"), " não aparece ativo no ", h("code", null, "config.yaml"),
        " do Hermes, então o agente ainda não passa por aqui. Rode ", h("code", null, "hermes plugins enable controle"), " e reinicie o Hermes."));
    }
    if (info.limiteHooks > 0 && info.limiteHooks < info.politica.espera_segundos + 3) {
      itens.push(h("li", { key: "t" }, `O Hermes corta a espera dos plugins em ${info.limiteHooks} s, então pedidos sem resposta são bloqueados nesse tempo. Para ter ${info.politica.espera_segundos} s, ponha `,
        h("code", null, `plugins:\n  hook_callback_timeout: ${info.politica.espera_segundos + 10}`), " no config.yaml."));
    }
    if (!itens.length) return null;
    return h("ul", { className: "c-alertas", role: "note" }, itens.map((i) => h(R.Fragment, { key: i.key }, h(Icone, { nome: "alerta", tamanho: 16 }), i)));
  }

  // --- Permissões ------------------------------------------------------------------------------

  function Chave({ ligada, rotulo, aoMudar }) {
    return h("button", {
      type: "button", role: "switch", "aria-checked": ligada, "aria-label": rotulo,
      className: cx("c-chave", ligada && "c-chave--ligada"), onClick: () => aoMudar(!ligada),
    }, h("span", { className: "c-chave__bolinha" }), h("span", { className: "c-chave__texto" }, ligada ? "Ligada" : "Desligada"));
  }

  function Permissoes({ info, avisar }) {
    const politica = info.politica;
    const salvar = (mudanca, mensagem) => api.salvarPolitica({ ...politica, ...mudanca }).then((r) => {
      if (r.ok) {
        if (mensagem) avisar(mensagem);
      } else avisar(r.mensagem, "erro");
    });
    const mudarModo = (id, modo) => salvar({ categorias: { ...politica.categorias, [id]: modo } });
    const adicionarPasta = () => api.escolherPasta().then((r) => {
      if (r.ok && r.dados && !politica.pastas_livres.includes(r.dados)) salvar({ pastas_livres: [...politica.pastas_livres, r.dados] }, "Pasta liberada.");
    });

    return h("div", { className: "c-pagina" },
      h("header", { className: "c-cabeca" },
        h("h1", null, "Permissões"),
        h("p", null, "Vale na próxima ação do agente, sem reiniciar nada. Livre roda direto, Perguntar espera você aqui e Bloqueado nunca roda.")),
      h("ul", { className: "c-permissoes" }, info.categorias.map((c) =>
        h("li", { key: c.id, className: "c-permissao" },
          h("div", { className: "c-permissao__texto" },
            h("strong", { id: `cat-${c.id}` }, c.nome),
            h("p", null, c.descricao),
            c.ferramentas.length || c.prefixos.length
              ? h("p", { className: "c-mono c-apagado c-permissao__ferr" }, [...c.ferramentas, ...c.prefixos.map((p) => `${p}*`)].join("  "))
              : null),
          h("div", { className: "c-modos", role: "radiogroup", "aria-labelledby": `cat-${c.id}` }, MODOS.map(([modo, rotulo]) =>
            h("button", {
              key: modo, type: "button", role: "radio", "aria-checked": politica.categorias[c.id] === modo,
              className: cx("c-modo", `c-modo--${modo}`, politica.categorias[c.id] === modo && "c-modo--ativo"),
              onClick: () => mudarModo(c.id, modo),
            }, rotulo))),
          c.id === "escrita"
            ? h("div", { className: "c-pastas" },
                h("p", { className: "c-pastas__titulo" }, "Pastas liberadas para gravar sem perguntar"),
                politica.pastas_livres.length
                  ? h("ul", null, politica.pastas_livres.map((p) =>
                      h("li", { key: p, className: "c-pasta" }, h(Icone, { nome: "pasta", tamanho: 15 }), h("span", { className: "c-mono" }, p),
                        h("button", { type: "button", className: "c-pasta__tirar", "aria-label": `Tirar ${p}`, onClick: () => salvar({ pastas_livres: politica.pastas_livres.filter((x) => x !== p) }) }, h(Icone, { nome: "x", tamanho: 14 })))))
                  : h("p", { className: "c-apagado" }, "Nenhuma. Toda gravação segue o modo acima."),
                h(Botao, { icone: "mais", variante: "fantasma", onClick: adicionarPasta }, "Adicionar pasta"))
            : null))),
      h("section", { className: "c-secao", "aria-labelledby": "t-protecoes" },
        h("h2", { id: "t-protecoes", className: "c-secao__titulo" }, "Proteções"),
        h("ul", { className: "c-permissoes" },
          h("li", { className: "c-permissao" },
            h("div", { className: "c-permissao__texto" },
              h("strong", { id: "p-vaz" }, "Vazamento de segredos"),
              h("p", null, "Quando o agente lê uma chave, token, senha, CPF ou cartão, o que pode mandar isso para fora (internet, navegador, MCP, mural, curl, git push) passa a pedir aprovação naquela sessão, mesmo se estiver em Livre.")),
            h("div", { className: "c-modos", role: "radiogroup", "aria-labelledby": "p-vaz" }, VAZAMENTO.map(([modo, rotulo]) =>
              h("button", {
                key: modo, type: "button", role: "radio", "aria-checked": politica.vazamento === modo,
                className: cx("c-modo", `c-modo--${modo === "perguntar" ? "perguntar" : modo === "bloquear" ? "bloqueado" : "livre"}`, politica.vazamento === modo && "c-modo--ativo"),
                onClick: () => salvar({ vazamento: modo }),
              }, rotulo)))),
          h("li", { className: "c-permissao" },
            h("div", { className: "c-permissao__texto" },
              h("strong", null, "Cerca contra instruções escondidas"),
              h("p", null, "Páginas da web, MCP e o mural podem trazer textos do tipo “ignore as instruções”. Quando aparecer, o resultado chega ao agente marcado como dado, não como ordem.")),
            h(Chave, { ligada: politica.cercar_externo, rotulo: "Cerca contra instruções escondidas", aoMudar: (v) => salvar({ cercar_externo: v }) })),
          h("li", { className: "c-permissao" },
            h("div", { className: "c-permissao__texto" },
              h("strong", null, "Comandos só de leitura rodam direto"),
              h("p", null, "git status, git log, dir, ls, Get-ChildItem, --version e afins não pedem aprovação, mesmo com Terminal em Perguntar. Comandos com |, ;, && ou > sempre seguem a regra normal.")),
            h(Chave, { ligada: politica.liberar_triviais, rotulo: "Comandos só de leitura rodam direto", aoMudar: (v) => salvar({ liberar_triviais: v }) })))),
      h("section", { className: "c-secao", "aria-labelledby": "t-regras" },
        h("h2", { id: "t-regras", className: "c-secao__titulo" }, "Lembradas"),
        politica.regras.length
          ? h("ul", { className: "c-regras" }, politica.regras.map((r) =>
              h("li", { key: r.padrao },
                h("span", { className: cx("c-pilula", r.modo === "livre" ? "c-pilula--livre" : "c-pilula--alto") }, r.modo === "livre" ? "Sempre permitir" : "Sempre negar"),
                h("code", null, rotuloPadrao(r.padrao)),
                h("span", { className: "c-apagado c-regras__tipo" }, (info.categorias.find((c) => c.id === r.padrao.split(":")[0]) || {}).nome || ""),
                h("button", { type: "button", className: "c-pasta__tirar", "aria-label": `Esquecer ${r.padrao}`, onClick: () => salvar({ regras: politica.regras.filter((x) => x.padrao !== r.padrao) }, "Regra esquecida.") }, h(Icone, { nome: "x", tamanho: 14 })))))
          : h("p", { className: "c-vazio" }, "Nada lembrado. Use “sempre permitir” ou “sempre negar” num pedido para criar uma regra. Ações de risco alto nunca viram regra.")),
      h("section", { className: "c-secao c-ajustes" },
        h("label", { htmlFor: "espera" }, h("strong", null, "Tempo para responder um pedido"),
          h("span", { className: "c-apagado" }, " Sem resposta nesse tempo, a ação é bloqueada.")),
        h("select", { id: "espera", value: politica.espera_segundos, onChange: (e) => salvar({ espera_segundos: Number(e.target.value) }) },
          [30, 60, 120, 300, 590].map((s) => h("option", { key: s, value: s }, s < 60 ? `${s} segundos` : `${Math.round(s / 60)} minuto${s >= 120 ? "s" : ""}`)))),
      h("p", { className: "c-rodape" }, "Com o app fechado, tudo que está em Perguntar é bloqueado. O controle fica em ",
        h("button", { type: "button", className: "c-link c-mono", onClick: () => api.abrirPasta() }, info.pasta), "."));
  }

  // --- Atividade -------------------------------------------------------------------------------

  function LinhaAtividade({ evento, categorias, compacta }) {
    const [aberta, setAberta] = useState(false);
    const cat = categorias.find((c) => c.id === evento.categoria);
    let resultado;
    if (evento.tipo === "decisao") {
      const [rotulo, tom] = DECISOES[evento.decisao] || [evento.decisao, ""];
      resultado = h("span", { className: cx("c-resultado", `c-resultado--${tom}`) }, evento.risco === "alto" ? `${rotulo} · risco alto` : evento.vazamento ? `${rotulo} · vazamento` : rotulo);
    } else if (evento.tipo === "marca") {
      resultado = h("span", { className: "c-resultado c-resultado--alerta" }, "Sessão marcada");
    } else if (evento.tipo === "cercado") {
      resultado = h("span", { className: "c-resultado c-resultado--alerta" }, "Injeção cercada");
    } else {
      resultado = h("span", { className: cx("c-resultado", evento.ok ? "c-resultado--neutro" : "c-resultado--ruim") },
        evento.ok ? "ok" : "erro", evento.duracao_ms ? h("span", { className: "c-apagado" }, ` ${evento.duracao_ms < 1000 ? `${evento.duracao_ms} ms` : `${(evento.duracao_ms / 1000).toFixed(1)} s`}`) : null);
    }
    return h("li", { className: cx("c-ativ", compacta && "c-ativ--compacta", evento.tipo !== "ferramenta" && "c-ativ--decisao") },
      h("time", { className: "c-mono c-apagado", dateTime: evento.ts }, hora(evento.ts)),
      compacta ? null : h("span", { className: cx("c-pilula", `c-pilula--cat`) }, cat ? cat.nome : evento.categoria),
      h("code", { className: "c-ativ__ferr" }, evento.ferramenta),
      h("button", { type: "button", className: cx("c-ativ__resumo", aberta && "c-ativ__resumo--aberto"), onClick: () => setAberta(!aberta), title: aberta ? "" : evento.resumo },
        evento.resumo || "—", evento.nota ? h("span", { className: "c-apagado" }, ` — “${evento.nota}”`) : null),
      resultado);
  }

  function Atividade({ info }) {
    const [dados, setDados] = useState(null);
    const [dia, setDia] = useState(null);
    const [categoria, setCategoria] = useState("");
    const [soDecisoes, setSoDecisoes] = useState(false);
    const [busca, setBusca] = useState("");
    const [cadeia, setCadeia] = useState(null);

    useEffect(() => {
      let vivo = true;
      const carregar = () => {
        api.atividade(dia).then((r) => vivo && r.ok && setDados(r.dados));
        api.integridade(dia).then((r) => vivo && r.ok && setCadeia(r.dados));
      };
      carregar();
      const t = setInterval(() => (!dia || (dados && dia === dados.hoje)) && carregar(), 2000);
      return () => {
        vivo = false;
        clearInterval(t);
      };
    }, [dia]);

    const eventos = useMemo(() => {
      if (!dados) return [];
      const termo = busca.trim().toLowerCase();
      return dados.eventos.filter((e) => (!categoria || e.categoria === categoria) && (!soDecisoes || e.tipo !== "ferramenta")
        && (!termo || `${e.ferramenta} ${e.resumo}`.toLowerCase().includes(termo)));
    }, [dados, categoria, soDecisoes, busca]);

    const diaAtual = dia || (dados && dados.hoje);
    const dias = dados ? Array.from(new Set([dados.hoje, ...dados.dias])).sort().reverse() : [];
    const pos = dias.indexOf(diaAtual);

    return h("div", { className: "c-pagina c-pagina--larga" },
      h("header", { className: "c-cabeca" },
        h("h1", null, "Atividade"),
        h("p", null, "Cada ferramenta que o agente usou e cada decisão sua. Fica só neste PC.")),
      h("div", { className: "c-filtros" },
        h("div", { className: "c-dia" },
          h(Botao, { icone: "esquerda", variante: "fantasma", "aria-label": "Dia anterior", disabled: pos < 0 || pos >= dias.length - 1, onClick: () => setDia(dias[pos + 1]) }),
          h("span", null, diaAtual ? (dados && diaAtual === dados.hoje ? "Hoje" : dataLonga(diaAtual)) : "…"),
          h(Botao, { icone: "direita", variante: "fantasma", "aria-label": "Dia seguinte", disabled: pos <= 0, onClick: () => setDia(pos - 1 === 0 ? null : dias[pos - 1]) })),
        h("label", { className: "c-invisivel", htmlFor: "f-cat" }, "Categoria"),
        h("select", { id: "f-cat", value: categoria, onChange: (e) => setCategoria(e.target.value) },
          h("option", { value: "" }, "Todas as categorias"), info.categorias.map((c) => h("option", { key: c.id, value: c.id }, c.nome))),
        h("label", { className: "c-check" }, h("input", { type: "checkbox", checked: soDecisoes, onChange: (e) => setSoDecisoes(e.target.checked) }), "Só pedidos, bloqueios e alertas"),
        h("label", { className: "c-invisivel", htmlFor: "f-busca" }, "Buscar"),
        h("input", { id: "f-busca", type: "search", placeholder: "Buscar comando, arquivo, site…", value: busca, onChange: (e) => setBusca(e.target.value) })),
      cadeia && cadeia.linhas
        ? h("p", { className: cx("c-integridade", !cadeia.ok && "c-integridade--ruim"), role: cadeia.ok ? undefined : "alert" },
            h(Icone, { nome: cadeia.ok ? "escudo" : "alerta", tamanho: 15 }),
            cadeia.ok
              ? `Registro íntegro: as ${cadeia.linhas} linhas deste dia conferem uma com a outra.`
              : cadeia.reescrito
                ? "O registro deste dia foi reescrito depois que o app o conferiu. Trate o histórico abaixo como suspeito."
                : `O registro deste dia foi alterado a partir da linha ${cadeia.quebra}. Algo editou ou apagou o histórico.`)
        : null,
      dados === null
        ? h("p", { className: "c-vazio" }, "Carregando…")
        : eventos.length === 0
          ? h("p", { className: "c-vazio" }, dados.eventos.length ? "Nada com esses filtros." : "Nenhuma ação registrada neste dia.")
          : h("ul", { className: "c-atividade" }, eventos.map((e, i) => h(LinhaAtividade, { key: `${e.ts}-${i}`, evento: e, categorias: info.categorias }))),
      dados && dados.eventos.length >= 500 ? h("p", { className: "c-rodape" }, "Mostrando as 500 mais recentes do dia.") : null);
  }

  // --- Mural -----------------------------------------------------------------------------------

  function MuralAba() {
    const Componente = (window.__PLUGINS_DO_APP__ || {}).mural;
    return h("div", { className: "c-pagina c-pagina--mural" }, Componente ? h(Componente) : h("p", { className: "c-vazio" }, "Não deu para carregar o mural."));
  }

  // --- Moldura ---------------------------------------------------------------------------------

  const ABAS = [
    ["agora", "Agora", "agora"],
    ["permissoes", "Permissões", "escudo"],
    ["atividade", "Atividade", "lista"],
    ["mural", "Mural", "balao"],
  ];

  function App() {
    const [info, setInfo] = useState(null);
    const [erro, setErro] = useState(null);
    const [aba, setAba] = useState("agora");
    const [pedidos, setPedidos] = useState([]);
    const [novosMural, setNovosMural] = useState(0);
    const [aviso, setAviso] = useState(null);
    const avisoRef = useRef(null);

    const avisar = useCallback((texto, tipo) => {
      setAviso({ texto, tipo: tipo || "ok" });
      clearTimeout(avisoRef.current);
      avisoRef.current = setTimeout(() => setAviso(null), 4000);
    }, []);

    const carregar = useCallback(() => api.estado().then((r) => {
      if (r.ok) {
        setInfo(r.dados);
        setPedidos(r.dados.pedidos);
        setErro(null);
      } else setErro(r.mensagem);
    }), []);

    useEffect(() => {
      carregar();
      const t = setInterval(carregar, 5000);
      const sairPedidos = api.aoMudar("pedidos", (p) => {
        setPedidos(p);
        if (p.length) setAba((atual) => (atual === "mural" ? atual : "agora"));
      });
      const sairPolitica = api.aoMudar("politica", (politica) => setInfo((i) => (i ? { ...i, politica } : i)));
      const muralT = setInterval(() => api.mural("/api/plugins/mural/estado").then((r) => r.ok && setNovosMural(r.dados.novos || 0)), 15000);
      api.mural("/api/plugins/mural/estado").then((r) => r.ok && setNovosMural(r.dados.novos || 0));
      return () => {
        clearInterval(t);
        clearInterval(muralT);
        sairPedidos();
        sairPolitica();
      };
    }, []);

    if (erro && !info) return h("main", { className: "c-erro" }, h("h1", null, "Não deu para abrir o controle"), h("p", null, erro));
    if (!info) return null;

    const contagens = { agora: pedidos.length, mural: novosMural };
    return h("div", { className: "c-app" },
      h("nav", { className: "c-lateral", "aria-label": "Seções" },
        h("div", { className: "c-marca" }, h("span", { className: "c-marca__logo", "aria-hidden": "true" }), h("div", null, h("strong", null, "Controle"), h("span", null, "Hermes neste PC"))),
        h("ul", null, ABAS.map(([id, rotulo, icone]) =>
          h("li", { key: id },
            h("button", { type: "button", className: cx("c-nav", aba === id && "c-nav--ativa"), "aria-current": aba === id ? "page" : undefined, onClick: () => setAba(id) },
              h(Icone, { nome: icone, tamanho: 18 }), rotulo,
              contagens[id] ? h("span", { className: cx("c-contador", id === "agora" && "c-contador--urgente") }, contagens[id]) : null)))),
        h("div", { className: cx("c-lateral__estado", info.politica.parado && "c-lateral__estado--pausado") },
          h("span", { className: "c-status__ponto" }), info.politica.parado ? "Pausado" : "Liberado")),
      h("main", { className: "c-conteudo" },
        aba === "agora" ? h(Agora, { info: { ...info }, pedidos, avisar, irPara: setAba }) : null,
        aba === "permissoes" ? h(Permissoes, { info, avisar }) : null,
        aba === "atividade" ? h(Atividade, { info }) : null,
        aba === "mural" ? h(MuralAba) : null),
      aviso ? h("div", { className: cx("c-aviso", aviso.tipo === "erro" && "c-aviso--erro"), role: "status" }, aviso.texto) : null);
  }

  ReactDOM.createRoot(document.getElementById("raiz")).render(h(App));
})();
