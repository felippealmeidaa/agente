# Controle do Hermes

Mini app desktop (Electron) para decidir o que o agente pode fazer no seu PC. Cada um, você e o Felipe, roda o seu.

- **Agora:** mostra as ações que esperam a sua aprovação e o botão de pausar ou parar tudo. Também lista os processos do Hermes que estão rodando e as últimas ações.
- **Permissões:** cada categoria de ferramenta fica em **Livre**, **Perguntar** ou **Bloqueado**. Há também as pastas onde o agente pode gravar sem perguntar e o tempo de espera por uma resposta.
- **Atividade:** registra cada ferramenta usada, com o resultado e a duração, além de cada decisão sua, separado por dia.
- **Mural:** é o mesmo mural do painel web, para trocar passagens com o parceiro.

Fechar a janela só esconde o app na bandeja, de onde ainda dá para pausar ou parar tudo. A cor do ícone mostra o estado: verde é liberado, amarelo é pausado e vermelho é pedido esperando. Cada pedido novo também gera uma notificação do Windows.

## Como o agente passa por aqui

O plugin `plugins/controle` roda dentro do Hermes e intercepta toda ferramenta antes dela executar (hook `pre_tool_call`). Ele e o app conversam por arquivos numa pasta local, sem porta de rede:

```
%LOCALAPPDATA%\hermes-controle\
  politica.json        o app grava; o plugin lê a cada ação
  vivo.json            sinal de vida do app (a cada 2 s)
  pedidos\ respostas\  aprovações
  atividade\AAAA-MM-DD.jsonl
```

O controle **falha fechado**. Com o app fechado, ou sem resposta dentro do prazo, tudo que está em Perguntar é bloqueado. O agente recebe o motivo e pode avisar você. Pausar bloqueia todas as ferramentas, inclusive as do mural. Parar tudo pausa e ainda encerra os processos do Hermes neste PC.

Este controle soma com as proteções do próprio Hermes (aprovação de comandos perigosos, `approvals.deny`), não substitui.

## Proteções

| Proteção | O que faz |
|---|---|
| Vazamento por sessão | Se uma ferramenta devolver chave, token, senha, CPF, CNPJ ou cartão, a sessão fica marcada. Daí em diante, o que pode levar isso para fora do PC passa a pedir aprovação, mesmo em Livre: internet, navegador, MCP, mural e terminal com `curl`, `git push`, `Invoke-WebRequest` etc. Pode bloquear em vez de perguntar. "Nesta sessão" não cobre esse caso. |
| Cerca contra injeção | Quando um resultado da web, de um MCP ou do mural traz "ignore as instruções…", ele chega ao agente cercado com o aviso de que é dado, não ordem. |
| Risco alto | Registro do Windows, `diskpart`, `bcdedit`, serviços, firewall, Defender, apagar `C:\Windows` e `iex (iwr …)` sempre perguntam, mesmo com o terminal em Livre. Esses pedidos não oferecem "nesta sessão" nem "sempre". |
| Só leitura | `git status`, `dir`, `Get-ChildItem`, `--version` e afins rodam direto. Comandos com `\|`, `;`, `&&` ou `>` seguem a regra normal. |
| Sempre permitir / sempre negar | Num pedido, o app lembra o padrão da ação, como `git push` ou `github.com`. As regras aparecem em Permissões → Lembradas e dá para esquecer qualquer uma. |
| Pasta do controle | O agente nunca pode ler nem mexer em `%LOCALAPPDATA%\hermes-controle`, mesmo como admin. |
| Registro encadeado | Cada linha da atividade guarda o hash da anterior. O app confere o registro a cada 30 s e guarda âncoras na pasta dele. Se alguém editar, apagar ou reescrever o histórico, aparece um aviso e uma notificação. |

Partes dessas proteções foram adaptadas do [OpenJarvis](https://github.com/open-jarvis/OpenJarvis) (Apache-2.0): o taint de sessão, a cerca de conteúdo externo, os níveis de aprovação e a ideia do log em cadeia de hash.

## Instalar e rodar

```powershell
cd apps\controle
npm install
npm start            # ou: npm start -- --escondido  (abre direto na bandeja)
```

No Hermes deste PC, em `%LOCALAPPDATA%\hermes\config.yaml`:

```yaml
plugins:
  enabled:
    - controle
    - mural
  # Sem isto o Hermes corta a espera dos plugins em 30 s
  hook_callback_timeout: 300
```

Reinicie o Hermes depois de ativar. O app avisa na tela Agora se o plugin não estiver ativo ou se o limite estiver curto.

Para o Mural, o app lê `MURAL_SUPABASE_URL` e `MURAL_SUPABASE_CHAVE` do `.env` do Hermes e `plugins.entries.mural.settings` do `config.yaml`. Veja `plugins/mural/README.md`.

## Testes

- `npm test`: o canal do lado do app.
- `python -m pytest tests/test_controle.py`: o plugin.
