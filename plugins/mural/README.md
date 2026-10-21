# Mural de passagem

Aba **Mural** no painel do Hermes (`hermes dashboard`) e três ferramentas para o agente. É por aqui que o Guilherme, o Felipe e os agentes de cada um deixam contexto uns para os outros. Cada um roda o Hermes no seu PC; o mural fica num projeto Supabase que os dois compartilham.

- **Cartão:** tem um tipo (passagem, pergunta ou aviso), um título e um conteúdo em Markdown, e vai sempre para o parceiro.
- **Status:** começa em `novo`, vira `lido` quando o destinatário abre e `feito` quando alguém fecha. Os cartões aceitam respostas e podem ser fixados no topo.
- **Ferramentas do agente:**
  - `mural_ler` lista ou abre cartões;
  - `mural_escrever` deixa um cartão para o parceiro;
  - `mural_responder` responde e muda o status.

  O que o agente escreve aparece com a etiqueta "agente".

## Configurar (uma vez por PC)

1. **Banco (só uma vez, por um dos dois):** crie um projeto no Supabase e rode `supabase.sql` no SQL Editor. O RLS fica ligado e sem políticas, então só a chave secreta acessa as tabelas.
2. **`.env` do Hermes** (`%LOCALAPPDATA%\hermes\.env` no Windows, `~/.hermes/.env` no Linux/Mac) (a chave fica só no servidor; o navegador nunca a vê):
   ```
   MURAL_SUPABASE_URL=https://<ref>.supabase.co
   MURAL_SUPABASE_CHAVE=sb_secret_...
   ```
3. **`config.yaml` do Hermes**, na mesma pasta (no PC do Felipe, troque os dois nomes):
   ```yaml
   plugins:
     entries:
       mural:
         settings:
           eu: guilherme
           parceiro: felipe
   ```
4. **Ativar:** `hermes plugins enable mural` e reinicie o painel.

Para o agente olhar o mural sozinho no começo das tarefas, ponha no `SOUL.md`: "Ao começar uma tarefa, leia a caixa de entrada do mural com `mural_ler`."

## Arquivos

| Arquivo | O que faz |
|---|---|
| `loja.py` | Acesso ao Supabase (PostgREST): validações, filtros, marcar lido, excluir só o que é seu |
| `ferramentas.py`, `__init__.py` | Schemas e handlers das ferramentas; registro no toolset `mural` |
| `dashboard/plugin_api.py` | Rotas em `/api/plugins/mural/` |
| `dashboard/dist/index.js`, `style.css` | A tela: JS puro com `React.createElement` do SDK do painel, sem etapa de build |
| `supabase.sql` | Tabelas, índices e gatilho |

Para o uso entre os dois PCs, prefira o servidor MCP em `apps/mural-mcp`, com login GitHub e sem chave no `.env`. Este plugin continua como alternativa local.

Testes: `python -m pytest tests/test_mural.py`. Eles usam um PostgREST falso em memória (`tests/mural_postgrest_falso.py`).
