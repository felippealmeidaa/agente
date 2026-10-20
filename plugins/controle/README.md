# Controle

Decide o que o agente pode fazer no seu PC e mostra tudo dentro do próprio Hermes Desktop. É um único pacote com três partes:

| Parte | Arquivos | O que faz |
|---|---|---|
| Agente | `plugin.yaml`, `__init__.py`, `politica.py`, `protecao.py`, `canal.py` | Antes de cada ferramenta, decide entre livre, perguntar e bloqueado. Marca a sessão quando aparece um segredo, cerca instrução escondida e registra tudo num log encadeado por hash. |
| Servidor | `dashboard/plugin_api.py` | Rotas em `/api/plugins/controle/`: estado, política, pausa, atividade e integridade. |
| Desktop | `desktop/plugin.js` | Página **Controle** na barra lateral (abas Agora, Permissões e Atividade), indicador na barra de status e aviso nativo se o log for alterado. |

**Onde aprovar.** Por padrão, o que está em "Perguntar" vai para a **tela de aprovação do próprio Hermes**: o cartão no chat do Desktop, o prompt no terminal ou a mensagem no WhatsApp/Telegram, se você usa o gateway. Ela oferece uma vez, nesta sessão, sempre e negar:
- **Ação comum:** "sempre" vale para o padrão (por exemplo `git push`).
- **Risco alto ou suspeita de vazamento:** "sempre" vale só para o comando exato.

## No app Hermes-Omni (este repositório)

O Controle é um plugin embutido e faz parte do produto:
- **Python:** a parte do agente sobe sempre, por causa de `SEMPRE_ATIVOS_DO_PRODUTO` em `hermes_cli/plugins_discovery.py`. Só `plugins.disabled` a desliga.
- **Servidor:** as rotas montam sozinhas, como em todo plugin embutido.
- **Desktop:** a página entra no app em `apps/desktop/src/plugins/controle/plugin.js`, que reexporta `desktop/plugin.js`, e vem ligada.

Não há nada para configurar.

**Para o agente rodar como administrador**, abra o app com *Executar como administrador*. O gateway que ele inicia herda o acesso.

## Num Hermes oficial (fora deste repositório)

1. Ligue o pacote na pasta de plugins:
   ```powershell
   New-Item -ItemType Junction -Path "$env:LOCALAPPDATA\hermes\plugins\controle" -Target "C:\caminho\do\repo\plugins\controle"
   ```
2. Ponha `controle` em `plugins.enabled` no `config.yaml` e reinicie o Hermes.
3. No Hermes Desktop, ligue **Controle** em **Capabilities → Plugins**.

## Testes

- `python -m pytest tests/test_controle.py tests/test_controle_protecoes.py`: política, proteções, aprovação no Hermes e log encadeado.
- A página foi validada num host de teste que imita o SDK do Desktop e usa as rotas reais. A validação final é no Hermes Desktop de verdade.

Partes das proteções foram adaptadas do [OpenJarvis](https://github.com/open-jarvis/OpenJarvis) (Apache-2.0).
