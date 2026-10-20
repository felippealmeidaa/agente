// Controle dentro do Hermes Desktop: página "Controle" (Agora, Permissões, Atividade), indicador na barra
// de status e conferência do log encadeado. As aprovações em si aparecem na tela de aprovação do próprio
// Hermes (chat, terminal ou mensagens); aqui ficam as regras, a pausa e o histórico.
// Arquivo carregado sem build: só `@hermes/plugin-sdk`, `react` e `react/jsx-runtime` podem ser importados.
import { host, useValue, ROUTES_AREA, SIDEBAR_NAV_AREA, STATUSBAR_AREAS, atom } from '@hermes/plugin-sdk'
import { createElement as h, Fragment, useCallback, useEffect, useMemo, useState } from 'react'

const ROTA = '/controle'
const MODOS = [['livre', 'Livre'], ['perguntar', 'Perguntar'], ['bloqueado', 'Bloqueado']]
const VAZAMENTO = [['perguntar', 'Perguntar'], ['bloquear', 'Bloquear'], ['desligado', 'Desligado']]
const DECISOES = {
  bloqueado: ['Bloqueado', 'ruim'], negar: ['Negado', 'ruim'], deny: ['Negado', 'ruim'], once: ['Permitido uma vez', 'bom'],
  sessao: ['Permitido na sessão', 'bom'], session: ['Permitido na sessão', 'bom'], always: ['Sempre permitir', 'bom'],
  perguntado: ['Perguntado', 'alerta'], tempo: ['Sem resposta', 'ruim'], timeout: ['Sem resposta', 'ruim'],
  fechado: ['App fechado', 'ruim'], cancelled: ['Cancelado', 'ruim'], smart_approve: ['Aprovado (auto)', 'bom'],
  smart_deny: ['Negado (auto)', 'ruim'], notify_failed: ['Aviso falhou', 'ruim'],
}

const cx = (...c) => c.filter(Boolean).join(' ')
const hora = (iso) => new Date(iso).toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
const dataLonga = (dia) => {
  const [a, m, d] = dia.split('-').map(Number)
  return new Date(a, m - 1, d).toLocaleDateString('pt-BR', { weekday: 'long', day: 'numeric', month: 'long' })
}
const rotuloPadrao = (padrao) => {
  const [tipo, ...resto] = String(padrao || '').split(':')
  return tipo === 'escrita' ? `arquivos em ${resto.join(':')}` : resto.join(':')
}

// Estado compartilhado entre a página e o indicador da barra de status
const $politica = atom(null)
const $cadeia = atom(null)

const ESTILO = `
.ctl { --ctl-livre: var(--ui-green, #4ade80); --ctl-perguntar: var(--ui-yellow, #ffbd38); --ctl-bloqueado: var(--ui-red, #fb2c36);
  height: 100%; overflow-y: auto; color: var(--ui-text-primary); font-size: 13px; }
.ctl * { box-sizing: border-box; }
.ctl-pagina { max-width: 980px; margin: 0 auto; padding: 24px 28px 48px; display: flex; flex-direction: column; gap: 20px; }
.ctl-cabeca { display: flex; align-items: flex-end; justify-content: space-between; gap: 16px; flex-wrap: wrap; }
.ctl-cabeca h1 { margin: 0; font-size: 22px; font-weight: 650; letter-spacing: -0.01em; }
.ctl-cabeca p { margin: 4px 0 0; color: var(--ui-text-tertiary); max-width: 64ch; }
.ctl-abas { display: inline-flex; gap: 2px; padding: 2px; border-radius: 8px; background: var(--ui-bg-tertiary, rgba(127,127,127,.12)); }
.ctl-aba { border: 0; background: transparent; color: var(--ui-text-secondary); padding: 6px 14px; border-radius: 6px; font: inherit; font-weight: 550; cursor: pointer; }
.ctl-aba:hover { color: var(--ui-text-primary); }
.ctl-aba--ativa { background: var(--ui-bg-elevated, var(--ui-bg-editor)); color: var(--ui-text-primary); box-shadow: 0 0 0 1px var(--ui-stroke-secondary); }
.ctl-botao { display: inline-flex; align-items: center; gap: 6px; min-height: 30px; padding: 0 12px; border-radius: 6px; font: inherit; font-weight: 600;
  border: 1px solid var(--ui-stroke-secondary); background: var(--ui-bg-elevated, transparent); color: var(--ui-text-primary); cursor: pointer; }
.ctl-botao:hover:not(:disabled) { background: var(--ui-control-hover-background, rgba(127,127,127,.12)); }
.ctl-botao:disabled { opacity: .5; cursor: not-allowed; }
.ctl-botao--primario { background: var(--ui-accent); color: var(--ui-bg-editor, #000); border-color: transparent; }
.ctl-botao--perigo { color: var(--ctl-bloqueado); border-color: color-mix(in srgb, var(--ctl-bloqueado) 45%, transparent); background: color-mix(in srgb, var(--ctl-bloqueado) 8%, transparent); }
.ctl-botao--perigo-cheio { background: var(--ctl-bloqueado); color: #fff; border-color: transparent; }
.ctl-link { border: 0; background: none; padding: 0; color: var(--ui-text-tertiary); text-decoration: underline; text-underline-offset: 3px; font: inherit; cursor: pointer; }
.ctl-link:hover { color: var(--ui-text-primary); }
.ctl-status { display: flex; align-items: center; justify-content: space-between; gap: 20px; flex-wrap: wrap; padding: 18px 20px; border-radius: 12px;
  border: 1px solid color-mix(in srgb, var(--ctl-cor) 35%, transparent); background: color-mix(in srgb, var(--ctl-cor) 7%, transparent); }
.ctl-status--livre { --ctl-cor: var(--ctl-livre); }
.ctl-status--pausado { --ctl-cor: var(--ctl-perguntar); }
.ctl-status strong { display: inline-flex; align-items: center; gap: 8px; font-size: 17px; }
.ctl-status p { margin: 4px 0 0; color: var(--ui-text-tertiary); max-width: 60ch; }
.ctl-ponto { width: 8px; height: 8px; border-radius: 99px; background: var(--ctl-cor, currentColor); box-shadow: 0 0 0 3px color-mix(in srgb, var(--ctl-cor, currentColor) 25%, transparent); flex: none; }
.ctl-acoes { display: flex; gap: 8px; flex-wrap: wrap; }
.ctl-secao { display: flex; flex-direction: column; gap: 10px; }
.ctl-secao h2 { margin: 0; font-size: 11px; font-weight: 700; letter-spacing: .07em; text-transform: uppercase; color: var(--ui-text-tertiary); }
.ctl-linha-titulo { display: flex; align-items: center; justify-content: space-between; }
.ctl-vazio { margin: 0; padding: 14px 16px; border: 1px dashed var(--ui-stroke-secondary); border-radius: 8px; color: var(--ui-text-tertiary); }
.ctl-aviso { display: grid; grid-template-columns: auto 1fr; gap: 6px 10px; margin: 0; padding: 12px 14px; border-radius: 8px;
  border: 1px solid color-mix(in srgb, var(--ctl-perguntar) 40%, transparent); background: color-mix(in srgb, var(--ctl-perguntar) 7%, transparent); }
.ctl-aviso code, .ctl code { font-family: var(--ui-font-mono, ui-monospace, Consolas, monospace); font-size: 12px; padding: 1px 4px; border-radius: 4px; background: var(--ui-inline-code-background, rgba(127,127,127,.15)); color: var(--ui-inline-code-foreground, inherit); white-space: pre-wrap; }
.ctl-lista { list-style: none; margin: 0; padding: 0; border: 1px solid var(--ui-stroke-secondary); border-radius: 10px; overflow: hidden; }
.ctl-lista > li + li { border-top: 1px solid var(--ui-stroke-tertiary, var(--ui-stroke-secondary)); }
.ctl-perm { display: grid; grid-template-columns: minmax(0,1fr) auto; gap: 8px 20px; align-items: center; padding: 14px 16px; }
.ctl-perm strong { font-size: 13px; }
.ctl-perm p { margin: 2px 0 0; color: var(--ui-text-tertiary); }
.ctl-perm .ctl-ferr { font-family: var(--ui-font-mono, ui-monospace, monospace); font-size: 11px; color: var(--ui-text-quaternary, var(--ui-text-tertiary)); word-spacing: 4px; }
.ctl-modos { display: inline-flex; gap: 2px; padding: 2px; border-radius: 7px; background: var(--ui-bg-tertiary, rgba(127,127,127,.12)); }
.ctl-modo { min-width: 88px; padding: 5px 10px; border: 0; border-radius: 5px; background: transparent; color: var(--ui-text-tertiary); font: inherit; font-weight: 600; cursor: pointer; }
.ctl-modo:hover { color: var(--ui-text-primary); }
.ctl-modo--livre { --ctl-cor: var(--ctl-livre); } .ctl-modo--perguntar { --ctl-cor: var(--ctl-perguntar); } .ctl-modo--bloqueado { --ctl-cor: var(--ctl-bloqueado); }
.ctl-modo--ativo { color: var(--ctl-cor); background: color-mix(in srgb, var(--ctl-cor) 14%, transparent); box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--ctl-cor) 45%, transparent); }
.ctl-chave { display: inline-flex; align-items: center; gap: 8px; border: 0; background: none; color: var(--ui-text-tertiary); font: inherit; font-weight: 600; cursor: pointer; }
.ctl-chave i { position: relative; width: 34px; height: 19px; border-radius: 99px; background: var(--ui-bg-tertiary, rgba(127,127,127,.25)); box-shadow: inset 0 0 0 1px var(--ui-stroke-secondary); }
.ctl-chave i::after { content: ""; position: absolute; top: 3px; left: 3px; width: 13px; height: 13px; border-radius: 99px; background: var(--ui-text-tertiary); transition: transform .15s; }
.ctl-chave--ligada { color: var(--ctl-livre); }
.ctl-chave--ligada i { background: color-mix(in srgb, var(--ctl-livre) 30%, transparent); }
.ctl-chave--ligada i::after { transform: translateX(15px); background: var(--ctl-livre); }
.ctl-pastas { grid-column: 1 / -1; display: flex; flex-direction: column; gap: 6px; padding: 10px 12px; border-radius: 8px; background: var(--ui-bg-tertiary, rgba(127,127,127,.08)); }
.ctl-pastas form { display: flex; gap: 6px; }
.ctl input, .ctl select { min-height: 30px; padding: 0 10px; border-radius: 6px; border: 1px solid var(--ui-stroke-secondary); background: var(--ui-bg-editor, transparent); color: var(--ui-text-primary); font: inherit; }
.ctl input { flex: 1; min-width: 0; }
.ctl-pasta, .ctl-regra { display: flex; align-items: center; gap: 8px; }
.ctl-regra { padding: 8px 14px; }
.ctl-tirar { margin-left: auto; border: 0; background: none; color: var(--ui-text-tertiary); cursor: pointer; font-size: 15px; line-height: 1; padding: 2px 6px; border-radius: 4px; }
.ctl-tirar:hover { color: var(--ctl-bloqueado); background: var(--ui-control-hover-background, rgba(127,127,127,.12)); }
.ctl-pilula { display: inline-flex; align-items: center; height: 19px; padding: 0 7px; border-radius: 99px; font-size: 11px; font-weight: 650; white-space: nowrap;
  color: var(--ctl-cor, var(--ui-text-tertiary)); background: color-mix(in srgb, var(--ctl-cor, var(--ui-text-tertiary)) 14%, transparent); }
.ctl-pilula--livre { --ctl-cor: var(--ctl-livre); } .ctl-pilula--bloqueado { --ctl-cor: var(--ctl-bloqueado); }
.ctl-filtros { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.ctl-dia { display: inline-flex; align-items: center; gap: 4px; font-weight: 600; }
.ctl-dia span { min-width: 150px; text-align: center; }
.ctl-ativ { display: grid; grid-template-columns: 72px 150px 130px minmax(0,1fr) auto; gap: 10px; align-items: start; padding: 7px 14px; font-size: 12px; }
.ctl-ativ--alerta { background: color-mix(in srgb, var(--ctl-perguntar) 5%, transparent); }
.ctl-ativ time, .ctl-ativ .ctl-mono { font-family: var(--ui-font-mono, ui-monospace, monospace); }
.ctl-ativ time { color: var(--ui-text-tertiary); }
.ctl-resumo { border: 0; background: none; padding: 0; text-align: left; font: inherit; font-family: var(--ui-font-mono, ui-monospace, monospace); color: var(--ui-text-primary);
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis; cursor: pointer; min-width: 0; }
.ctl-resumo--aberto { white-space: pre-wrap; word-break: break-word; }
.ctl-res { font-weight: 650; white-space: nowrap; }
.ctl-res--bom { color: var(--ctl-livre); } .ctl-res--ruim { color: var(--ctl-bloqueado); } .ctl-res--alerta { color: var(--ctl-perguntar); } .ctl-res--neutro { color: var(--ui-text-tertiary); }
.ctl-integro { display: flex; align-items: center; gap: 8px; margin: 0; padding: 8px 12px; border-radius: 8px; color: var(--ctl-livre);
  border: 1px solid color-mix(in srgb, var(--ctl-livre) 30%, transparent); background: color-mix(in srgb, var(--ctl-livre) 6%, transparent); }
.ctl-integro--ruim { color: var(--ctl-bloqueado); font-weight: 650; border-color: color-mix(in srgb, var(--ctl-bloqueado) 45%, transparent); background: color-mix(in srgb, var(--ctl-bloqueado) 8%, transparent); }
.ctl-ajuste { display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap; padding: 12px 16px; border: 1px solid var(--ui-stroke-secondary); border-radius: 10px; }
.ctl-chip { display: inline-flex; align-items: center; gap: 6px; padding: 0 6px; height: 100%; border: 0; background: none; color: var(--ui-text-tertiary); font: inherit; font-size: 11px; cursor: pointer; }
.ctl-chip:hover { color: var(--ui-text-primary); }
.ctl-chip--livre { --ctl-cor: var(--ui-green, #4ade80); } .ctl-chip--pausado { --ctl-cor: var(--ui-yellow, #ffbd38); } .ctl-chip--alterado { --ctl-cor: var(--ui-red, #fb2c36); color: var(--ui-red, #fb2c36); }
.ctl-chip .ctl-ponto { width: 6px; height: 6px; box-shadow: none; }
@media (max-width: 900px) { .ctl-ativ { grid-template-columns: 72px 120px minmax(0,1fr) auto; } .ctl-ativ .ctl-cat { display: none; } }
`

function Modos({ opcoes, valor, rotulo, aoMudar, cores }) {
  return h('div', { className: 'ctl-modos', role: 'radiogroup', 'aria-label': rotulo },
    opcoes.map(([id, texto]) => h('button', {
      key: id, type: 'button', role: 'radio', 'aria-checked': valor === id,
      className: cx('ctl-modo', `ctl-modo--${cores ? cores[id] : id}`, valor === id && 'ctl-modo--ativo'), onClick: () => aoMudar(id),
    }, texto)))
}

function Chave({ ligada, rotulo, aoMudar }) {
  return h('button', { type: 'button', role: 'switch', 'aria-checked': ligada, 'aria-label': rotulo,
    className: cx('ctl-chave', ligada && 'ctl-chave--ligada'), onClick: () => aoMudar(!ligada) }, h('i'), ligada ? 'Ligada' : 'Desligada')
}

function LinhaAtividade({ evento, categorias, compacta }) {
  const [aberta, setAberta] = useState(false)
  const cat = categorias.find((c) => c.id === evento.categoria)
  let resultado
  if (evento.tipo === 'decisao' || evento.tipo === 'aprovacao') {
    const [texto, tom] = DECISOES[evento.decisao] || [evento.decisao || '—', 'neutro']
    resultado = h('span', { className: `ctl-res ctl-res--${tom}` }, evento.risco === 'alto' ? `${texto} · risco alto` : evento.vazamento ? `${texto} · vazamento` : texto)
  } else if (evento.tipo === 'marca') resultado = h('span', { className: 'ctl-res ctl-res--alerta' }, 'Sessão marcada')
  else if (evento.tipo === 'cercado') resultado = h('span', { className: 'ctl-res ctl-res--alerta' }, 'Injeção cercada')
  else {
    const ms = evento.duracao_ms
    resultado = h('span', { className: cx('ctl-res', evento.ok ? 'ctl-res--neutro' : 'ctl-res--ruim') },
      evento.ok ? 'ok' : 'erro', ms ? ` ${ms < 1000 ? `${ms} ms` : `${(ms / 1000).toFixed(1)} s`}` : '')
  }
  return h('li', { className: cx('ctl-ativ', evento.tipo !== 'ferramenta' && 'ctl-ativ--alerta') },
    h('time', { dateTime: evento.ts }, hora(evento.ts)),
    compacta ? null : h('span', { className: 'ctl-cat' }, h('span', { className: 'ctl-pilula' }, cat ? cat.nome : evento.categoria)),
    h('span', { className: 'ctl-mono' }, evento.ferramenta),
    h('button', { type: 'button', className: cx('ctl-resumo', aberta && 'ctl-resumo--aberto'), title: aberta ? '' : evento.resumo, onClick: () => setAberta(!aberta) },
      evento.resumo || '—', evento.nota ? ` — “${evento.nota}”` : ''),
    resultado)
}

// --- Agora ---------------------------------------------------------------------------------------------

function Agora({ ctx, info, irPara }) {
  const politica = useValue($politica) || info.politica
  const ocupadas = useValue(host.state.busyBySession) || {}
  const [recentes, setRecentes] = useState([])
  const [confirmar, setConfirmar] = useState(false)
  const quantasOcupadas = Object.values(ocupadas).filter(Boolean).length

  useEffect(() => {
    let vivo = true
    const carregar = () => ctx.rest('/atividade').then((r) => vivo && setRecentes(r.eventos.slice(0, 8))).catch(() => {})
    carregar()
    const parar = ctx.setInterval(carregar, 3000)
    return () => { vivo = false; parar() }
  }, [])
  useEffect(() => {
    if (!confirmar) return undefined
    return ctx.setTimeout(() => setConfirmar(false), 4000)
  }, [confirmar])

  const pausar = (parado) => ctx.rest('/pausar', { method: 'POST', body: { parado } })
    .then((p) => { $politica.set(p); host.notify({ kind: 'info', message: parado ? 'Agente pausado: toda ferramenta é bloqueada.' : 'Agente retomado.' }) })
    .catch((e) => host.notifyError(e, 'Não deu para mudar a pausa.'))

  const pararTudo = async () => {
    setConfirmar(false)
    try {
      $politica.set(await ctx.rest('/pausar', { method: 'POST', body: { parado: true } }))
      const ids = Object.entries(host.state.busyBySession.get() || {}).filter(([, b]) => b).map(([id]) => id)
      await Promise.all(ids.map((id) => host.request('session.interrupt', { session_id: id }).catch(() => null)))
      host.notify({ kind: 'info', message: `Agente pausado. ${ids.length} conversa(s) em andamento interrompida(s).` })
    } catch (e) {
      host.notifyError(e, 'Não deu para parar tudo.')
    }
  }

  return h(Fragment, null,
    h('section', { className: cx('ctl-status', politica.parado ? 'ctl-status--pausado' : 'ctl-status--livre'), 'aria-live': 'polite' },
      h('div', null,
        h('strong', null, h('span', { className: 'ctl-ponto' }), politica.parado ? 'Agente pausado' : 'Agente liberado'),
        h('p', null, politica.parado
          ? 'Toda ferramenta é bloqueada até você retomar. O agente recebe o aviso e para de agir.'
          : `Seguindo suas permissões. ${quantasOcupadas ? `${quantasOcupadas} conversa(s) trabalhando agora.` : 'Nenhuma conversa trabalhando agora.'} Os pedidos de aprovação aparecem no chat do Hermes.`)),
      h('div', { className: 'ctl-acoes' },
        politica.parado
          ? h('button', { type: 'button', className: 'ctl-botao ctl-botao--primario', onClick: () => pausar(false) }, '▶ Retomar')
          : h('button', { type: 'button', className: 'ctl-botao', onClick: () => pausar(true) }, '❚❚ Pausar agente'),
        h('button', { type: 'button', className: cx('ctl-botao', confirmar ? 'ctl-botao--perigo-cheio' : 'ctl-botao--perigo'),
          title: 'Pausa o agente e interrompe todas as conversas em andamento', onClick: () => (confirmar ? pararTudo() : setConfirmar(true)) },
        confirmar ? 'Confirmar: parar tudo' : '■ Parar tudo'))),
    h('section', { className: 'ctl-secao' },
      h('div', { className: 'ctl-linha-titulo' }, h('h2', null, 'Últimas ações'), h('button', { type: 'button', className: 'ctl-link', onClick: () => irPara('atividade') }, 'Ver tudo')),
      recentes.length
        ? h('ul', { className: 'ctl-lista' }, recentes.map((e, i) => h(LinhaAtividade, { key: `${e.ts}-${i}`, evento: e, categorias: info.categorias, compacta: true })))
        : h('p', { className: 'ctl-vazio' }, 'Nada ainda hoje.')))
}

// --- Permissões ------------------------------------------------------------------------------------------

function Permissoes({ ctx, info }) {
  const politica = useValue($politica) || info.politica
  const [pasta, setPasta] = useState('')
  const salvar = (mudanca, mensagem) => ctx.rest('/politica', { method: 'POST', body: { politica: { ...politica, ...mudanca } } })
    .then((p) => { $politica.set(p); if (mensagem) host.notify({ kind: 'info', message: mensagem }) })
    .catch((e) => host.notifyError(e, 'Não deu para salvar a permissão.'))

  return h(Fragment, null,
    h('ul', { className: 'ctl-lista' }, info.categorias.map((c) => h('li', { key: c.id, className: 'ctl-perm' },
      h('div', null,
        h('strong', { id: `ctl-${c.id}` }, c.nome), h('p', null, c.descricao),
        c.ferramentas.length || c.prefixos.length ? h('p', { className: 'ctl-ferr' }, [...c.ferramentas, ...c.prefixos.map((p) => `${p}*`)].join('  ')) : null),
      h(Modos, { opcoes: MODOS, valor: politica.categorias[c.id], rotulo: c.nome, aoMudar: (m) => salvar({ categorias: { ...politica.categorias, [c.id]: m } }) }),
      c.id === 'escrita' ? h('div', { className: 'ctl-pastas' },
        h('strong', null, 'Pastas liberadas para gravar sem perguntar'),
        politica.pastas_livres.length
          ? politica.pastas_livres.map((p) => h('div', { key: p, className: 'ctl-pasta' }, h('code', null, p),
              h('button', { type: 'button', className: 'ctl-tirar', 'aria-label': `Tirar ${p}`, onClick: () => salvar({ pastas_livres: politica.pastas_livres.filter((x) => x !== p) }) }, '×')))
          : h('span', { style: { color: 'var(--ui-text-tertiary)' } }, 'Nenhuma. Toda gravação segue o modo acima.'),
        h('form', { onSubmit: (e) => {
          e.preventDefault()
          const nova = pasta.trim().replace(/^"|"$/g, '')
          if (!nova || politica.pastas_livres.includes(nova)) return
          salvar({ pastas_livres: [...politica.pastas_livres, nova] }, 'Pasta liberada.').then(() => setPasta(''))
        } },
          h('input', { value: pasta, onChange: (e) => setPasta(e.target.value), placeholder: 'C:\\Users\\voce\\projetos', 'aria-label': 'Pasta para liberar' }),
          h('button', { type: 'submit', className: 'ctl-botao', disabled: !pasta.trim() }, 'Adicionar'))) : null))),

    h('section', { className: 'ctl-secao' }, h('h2', null, 'Proteções'),
      h('ul', { className: 'ctl-lista' },
        h('li', { className: 'ctl-perm' },
          h('div', null, h('strong', null, 'Vazamento de segredos'),
            h('p', null, 'Depois que o agente lê uma chave, token, senha, CPF ou cartão, o que pode mandar isso para fora (internet, navegador, MCP, mural, curl, git push) passa a pedir aprovação naquela sessão, mesmo se estiver em Livre.')),
          h(Modos, { opcoes: VAZAMENTO, valor: politica.vazamento, rotulo: 'Vazamento', cores: { perguntar: 'perguntar', bloquear: 'bloqueado', desligado: 'livre' }, aoMudar: (v) => salvar({ vazamento: v }) })),
        h('li', { className: 'ctl-perm' },
          h('div', null, h('strong', null, 'Cerca contra instruções escondidas'),
            h('p', null, 'Páginas da web, MCP e o mural podem trazer textos do tipo “ignore as instruções”. Quando aparecer, o resultado chega ao agente marcado como dado, não como ordem.')),
          h(Chave, { ligada: politica.cercar_externo, rotulo: 'Cerca contra instruções escondidas', aoMudar: (v) => salvar({ cercar_externo: v }) })),
        h('li', { className: 'ctl-perm' },
          h('div', null, h('strong', null, 'Comandos só de leitura rodam direto'),
            h('p', null, 'git status, git log, dir, ls, Get-ChildItem, --version e afins não pedem aprovação. Com |, ;, && ou > seguem a regra normal.')),
          h(Chave, { ligada: politica.liberar_triviais, rotulo: 'Comandos só de leitura rodam direto', aoMudar: (v) => salvar({ liberar_triviais: v }) })))),

    h('section', { className: 'ctl-secao' }, h('h2', null, 'Lembradas aqui'),
      politica.regras.length
        ? h('ul', { className: 'ctl-lista' }, politica.regras.map((r) => h('li', { key: r.padrao, className: 'ctl-regra' },
            h('span', { className: cx('ctl-pilula', r.modo === 'livre' ? 'ctl-pilula--livre' : 'ctl-pilula--bloqueado') }, r.modo === 'livre' ? 'Sempre permitir' : 'Sempre negar'),
            h('code', null, rotuloPadrao(r.padrao)),
            h('button', { type: 'button', className: 'ctl-tirar', 'aria-label': `Esquecer ${r.padrao}`, onClick: () => salvar({ regras: politica.regras.filter((x) => x.padrao !== r.padrao) }, 'Regra esquecida.') }, '×'))))
        : h('p', { className: 'ctl-vazio' }, 'Nada lembrado aqui. O “sempre” que você escolhe na tela de aprovação do Hermes fica na lista de permissões do próprio Hermes (hermes approvals).')),

    h('p', { style: { margin: 0, color: 'var(--ui-text-tertiary)' } }, 'O agente nunca pode mexer na pasta do controle: ', h('code', null, info.pasta)))
}

// --- Atividade ---------------------------------------------------------------------------------------------

function Atividade({ ctx, info }) {
  const [dados, setDados] = useState(null)
  const [dia, setDia] = useState(null)
  const [categoria, setCategoria] = useState('')
  const [soAlertas, setSoAlertas] = useState(false)
  const [busca, setBusca] = useState('')
  const cadeia = useValue($cadeia)
  const [cadeiaDia, setCadeiaDia] = useState(null)

  useEffect(() => {
    let vivo = true
    const carregar = () => {
      ctx.rest(`/atividade${dia ? `?dia=${dia}` : ''}`).then((r) => vivo && setDados(r)).catch(() => {})
      if (dia) conferirCadeia(ctx, dia).then((r) => vivo && setCadeiaDia(r)).catch(() => {})
    }
    carregar()
    const parar = ctx.setInterval(() => { if (!dia) carregar() }, 2000)
    return () => { vivo = false; parar() }
  }, [dia])

  const eventos = useMemo(() => {
    if (!dados) return []
    const termo = busca.trim().toLowerCase()
    return dados.eventos.filter((e) => (!categoria || e.categoria === categoria) && (!soAlertas || e.tipo !== 'ferramenta')
      && (!termo || `${e.ferramenta} ${e.resumo}`.toLowerCase().includes(termo)))
  }, [dados, categoria, soAlertas, busca])

  const dias = dados ? [...new Set([dados.hoje, ...dados.dias])].sort().reverse() : []
  const atual = dia || (dados && dados.hoje)
  const pos = dias.indexOf(atual)
  const integ = dia ? cadeiaDia : cadeia

  return h(Fragment, null,
    h('div', { className: 'ctl-filtros' },
      h('div', { className: 'ctl-dia' },
        h('button', { type: 'button', className: 'ctl-botao', 'aria-label': 'Dia anterior', disabled: pos < 0 || pos >= dias.length - 1, onClick: () => setDia(dias[pos + 1]) }, '‹'),
        h('span', null, atual ? (dados && atual === dados.hoje ? 'Hoje' : dataLonga(atual)) : '…'),
        h('button', { type: 'button', className: 'ctl-botao', 'aria-label': 'Dia seguinte', disabled: pos <= 0, onClick: () => setDia(pos - 1 === 0 ? null : dias[pos - 1]) }, '›')),
      h('select', { value: categoria, 'aria-label': 'Categoria', onChange: (e) => setCategoria(e.target.value) },
        h('option', { value: '' }, 'Todas as categorias'), info.categorias.map((c) => h('option', { key: c.id, value: c.id }, c.nome))),
      h('label', { style: { display: 'inline-flex', gap: 6, alignItems: 'center' } },
        h('input', { type: 'checkbox', checked: soAlertas, onChange: (e) => setSoAlertas(e.target.checked), style: { flex: 'none', minHeight: 0 } }), 'Só pedidos, bloqueios e alertas'),
      h('input', { type: 'search', value: busca, placeholder: 'Buscar comando, arquivo, site…', 'aria-label': 'Buscar', onChange: (e) => setBusca(e.target.value) })),
    integ && integ.linhas
      ? h('p', { className: cx('ctl-integro', !integ.ok && 'ctl-integro--ruim'), role: integ.ok ? undefined : 'alert' },
          integ.ok ? `✓ Registro íntegro: as ${integ.linhas} linhas deste dia conferem uma com a outra.`
            : integ.reescrito ? '⚠ O registro deste dia foi reescrito depois da última conferência. Trate o histórico como suspeito.'
              : `⚠ O registro deste dia foi alterado a partir da linha ${integ.quebra}. Algo editou ou apagou o histórico.`)
      : null,
    dados === null ? h('p', { className: 'ctl-vazio' }, 'Carregando…')
      : eventos.length === 0 ? h('p', { className: 'ctl-vazio' }, dados.eventos.length ? 'Nada com esses filtros.' : 'Nenhuma ação registrada neste dia.')
        : h('ul', { className: 'ctl-lista' }, eventos.map((e, i) => h(LinhaAtividade, { key: `${e.ts}-${i}`, evento: e, categorias: info.categorias }))))
}

// --- Conferência do log (âncoras ficam no armazenamento do app, fora do alcance do agente) --------------------

async function conferirCadeia(ctx, dia) {
  const ancoras = ctx.storage.get('ancoras', {})
  const ancora = ancoras[dia]
  const r = await ctx.rest(`/integridade?dia=${dia}${ancora ? `&ancora=${ancora.linhas}` : ''}`)
  let reescrito = false
  if (r.ok && ancora && ancora.linhas > 0) reescrito = r.linhas < ancora.linhas || r.hash_ancora !== ancora.hash
  if (r.ok && !reescrito && r.linhas) {
    ancoras[dia] = { linhas: r.linhas, hash: r.ultimo }
    const dias = Object.keys(ancoras).sort().slice(-30)
    ctx.storage.set('ancoras', Object.fromEntries(dias.map((d) => [d, ancoras[d]])))
  }
  return { ...r, ok: r.ok && !reescrito, reescrito }
}

// --- Página e barra de status ------------------------------------------------------------------------------------

function Pagina({ ctx }) {
  const [info, setInfo] = useState(null)
  const [erro, setErro] = useState(null)
  const [aba, setAba] = useState('agora')
  const carregar = useCallback(() => ctx.rest('/estado').then((r) => { setInfo(r); $politica.set(r.politica); setErro(null) })
    .catch((e) => setErro(e && e.message ? e.message : String(e))), [])
  useEffect(() => {
    carregar()
    return ctx.setInterval(carregar, 5000)
  }, [])

  if (!info) {
    return h('div', { className: 'ctl' }, h('div', { className: 'ctl-pagina' },
      h('div', { className: 'ctl-cabeca' }, h('h1', null, 'Controle')),
      erro ? h('p', { className: 'ctl-aviso' }, '⚠', h('span', null, 'O backend do controle não respondeu (', erro, '). Confira se ', h('code', null, 'controle'),
        ' está em plugins.enabled no config.yaml e reinicie o Hermes.')) : h('p', { className: 'ctl-vazio' }, 'Carregando…')))
  }
  const abas = [['agora', 'Agora'], ['permissoes', 'Permissões'], ['atividade', 'Atividade']]
  return h('div', { className: 'ctl' }, h('div', { className: 'ctl-pagina' },
    h('header', { className: 'ctl-cabeca' },
      h('div', null, h('h1', null, 'Controle'), h('p', null, 'O que o agente pode fazer neste PC, a pausa de emergência e o histórico de tudo que ele fez.')),
      h('div', { className: 'ctl-abas', role: 'tablist' }, abas.map(([id, rotulo]) =>
        h('button', { key: id, type: 'button', role: 'tab', 'aria-selected': aba === id, className: cx('ctl-aba', aba === id && 'ctl-aba--ativa'), onClick: () => setAba(id) }, rotulo)))),
    aba === 'agora' ? h(Agora, { ctx, info, irPara: setAba }) : null,
    aba === 'permissoes' ? h(Permissoes, { ctx, info }) : null,
    aba === 'atividade' ? h(Atividade, { ctx, info }) : null))
}

function Indicador() {
  const politica = useValue($politica)
  const cadeia = useValue($cadeia)
  const alterado = cadeia && !cadeia.ok
  const estado = alterado ? 'alterado' : politica && politica.parado ? 'pausado' : 'livre'
  const texto = alterado ? 'Registro alterado' : politica && politica.parado ? 'Agente pausado' : 'Controle'
  return h('button', { type: 'button', className: `ctl-chip ctl-chip--${estado}`, title: 'Abrir o Controle', onClick: () => host.navigate(ROTA) },
    h('span', { className: 'ctl-ponto' }), texto)
}

export default {
  id: 'controle',
  name: 'Controle',
  register(ctx) {
    const estilo = document.createElement('style')
    estilo.id = 'controle-estilo'
    estilo.textContent = ESTILO
    document.head.appendChild(estilo)
    ctx.onDispose(() => estilo.remove())

    // Estado inicial para o indicador, mesmo antes de abrir a página
    const atualizar = () => ctx.rest('/estado').then((r) => $politica.set(r.politica)).catch(() => {})
    atualizar()
    ctx.setInterval(atualizar, 10000)

    let avisouHoje = ''
    const vigiar = () => {
      const hoje = new Date().toLocaleDateString('sv-SE')
      conferirCadeia(ctx, hoje).then((r) => {
        $cadeia.set(r)
        if (!r.ok && avisouHoje !== hoje) {
          avisouHoje = hoje
          const mensagem = r.reescrito ? 'O histórico de hoje foi reescrito depois da última conferência.' : `A linha ${r.quebra} do registro de hoje não confere com a anterior.`
          host.notify({ kind: 'error', title: 'Registro de atividade alterado', message: mensagem })
          ctx.os.notify({ title: 'Registro de atividade alterado', body: mensagem, activate: ROTA })
        }
      }).catch(() => {})
    }
    vigiar()
    ctx.setInterval(vigiar, 30000)

    ctx.registerMany([
      { id: 'pagina', area: ROUTES_AREA, data: { path: ROTA }, render: () => h(Pagina, { ctx }) },
      { id: 'nav', area: SIDEBAR_NAV_AREA, data: { path: ROTA, label: 'Controle', codicon: 'shield' } },
      { id: 'indicador', area: STATUSBAR_AREAS.right, order: 90, render: () => h(Indicador) },
    ])
  },
}
