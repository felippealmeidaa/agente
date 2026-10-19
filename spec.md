# MASTER PROMPT & ARCHITECTURAL SPECIFICATION v2.0: PROJETO "HERMES-OMNI"
**Target Environment:** Antigravity IDE (Agentic Development Mode)  
**Architecture Pattern:** Hybrid Autonomous Agent OS (Hermes Base + LiteLLM Local Gateway + LangGraph Orchestration + Git Worktree Coding Council + Self-Evolving Reflexion Loop)

---

## 1. INFRAESTRUTURA E TOPOLOGIA DE CONEXÃO (BLINDADA CONTRA OOM E CONCORRÊNCIA)

### 1.1. Motor de Inferência Remoto (Servidor RTX 5090 - 32GB VRAM)
* **Engine:** Ollama Server (`0.0.0.0:11434`) exposto via Túnel HTTPS fixo (`OLLAMA_REMOTE_URL`).
* **Modelo Base:** `qwen3.8-pro` (`hf.co/unsloth/Qwen3.8-27B-GGUF:UD-Q6_K`, ~22GB VRAM).
* **Orçamento Estrito de VRAM (Zero CPU Offloading):**
  * `num_ctx`: `65536` (64k tokens por slot; dinâmico via request: `32768` para sub-agentes rápidos e `65536` para o Coding Council).
  * `OLLAMA_KV_CACHE_TYPE`: `q8_0` (ou `q4_0` em carga máxima).
  * `OLLAMA_NUM_PARALLEL`: `2` (1 slot dedicado para cada máquina/usuário, totalizando ~27.5 GB de VRAM e mantendo 4.5 GB de margem de segurança).

### 1.2. Gateway Local de LLM e Semáforo Cross-Process (No Notebook)
Para resolver simultaneamente:
1. A tradução perfeita da API Anthropic (`POST /v1/messages`) exigida pelo Claude Code CLI;
2. O roteamento do Aider para o túnel remoto;
3. O controle de concorrência entre o Python (LangGraph) e subprocessos externos (CLIs):

* **LiteLLM Proxy / FastAPI LLM Gateway (`omni_core/llm_gateway.py` ou container `litellm`):**
  * Roda localmente no notebook em `http://127.0.0.1:4000`.
  * Recebe chamadas tanto no formato OpenAI (`/v1/chat/completions`) quanto no formato Anthropic (`/v1/messages`) e traduz de forma transparente para `${OLLAMA_REMOTE_URL}`.
  * **Semáforo Global IPC/Redis:** O Gateway Local aplica um semáforo com limite de concorrência configurável (ou lock via Redis/FileLock em `.omni_gpu.lock`) na fila de saída do notebook. Assim, mesmo que o `supervisor_graph` (Python), o `claude` (subprocesso) e o `aider` (subprocesso) rodem no notebook, eles passam pelo proxy local `127.0.0.1:4000` e respeitam rigorosamente a fila sem estourar o Ollama remoto.

### 1.3. Pré-Requisitos de Sistema Operacional (WSL2 Ubuntu + Windows Host)
* Binários obrigatórios verificados no boot (`scripts/verify_system.py`): `git`, `ffmpeg` (obrigatório para decodificar áudios `.ogg`/Opus do WhatsApp/Telegram para PCM 16kHz no `faster-whisper`), `node`/`npm`, `uv`, `docker`.
* Modelo de transcrição local: `faster-whisper` fixado no modelo `"small"` ou `"base"` com `compute_type="int8"` na CPU local (transcrição em <500ms sem congelar o notebook).

---

## 2. ESTRUTURA DE DIRETÓRIOS DO PROJETO

```text
hermes-omni/
├── .env.example
├── docker-compose.yml              # Postgres (pgvector) + Redis (Global Locks/Queue) + LiteLLM Proxy
├── pyproject.toml                  # Python 3.12+ via uv
├── SPEC.md                         # Esta especificação v2.0
├── SOUL.md                         # Identidade Mestre e Regras de Tiered Safety
├── skills/                         # Skills em Markdown (nativas + auto-aprendidas)
│   └── auto_learned/               # Skills sintetizadas autonomamente
├── omni_core/
│   ├── __init__.py
│   ├── config.py                   # Pydantic Settings (URLs, Limites, Tiers de Segurança)
│   ├── llm_gateway.py              # Proxy local FastAPI + Cliente com FileLock/IPC
│   ├── orchestrator/
│   │   ├── __init__.py
│   │   ├── supervisor_graph.py     # Grafo Mestre LangGraph
│   │   ├── state.py                # Schemas Pydantic e Estado Global
│   │   ├── safety_gate.py          # Tiered Safety Policy (Auto-Approve vs Mobile HITL Confirmation)
│   │   └── mobile_notifier.py      # Notificações WhatsApp/Telegram + Decoder FFmpeg/Whisper
│   ├── coding_council/             # CONSELHO DE CÓDIGO ISOLADO EM GIT WORKTREES
│   │   ├── __init__.py
│   │   ├── council_graph.py        # Sub-grafo: Worktree -> Claude -> Auditor/Codex -> Aider -> Merge
│   │   ├── worktree_manager.py     # Cria/gerencia Git Worktrees isoladas (../.omni_sandboxes/task_id)
│   │   ├── claude_driver.py        # Subprocesso Claude Code apontando para o Gateway Local (:4000)
│   │   ├── auditor_codex_driver.py # Runner Híbrido: Executa pytest/linters/build + Codex CLI/LLM Audit
│   │   └── aider_driver.py         # Subprocesso Aider (--model openai/qwen3.8-pro --openai-api-base :4000/v1)
│   ├── specialists/
│   │   ├── __init__.py
│   │   ├── os_godmode_agent.py     # Controle de OS (WSL2 Bash + Windows PowerShell) filtrado pelo Safety Gate
│   │   ├── devops_infra_agent.py   # Docker, Rede, Túneis e Deploy
│   │   ├── data_db_agent.py        # Postgres, SQLite, Queries e RAG
│   │   └── research_web_agent.py   # Playwright Headless e Scraping
│   └── self_improvement/
│       ├── __init__.py
│       ├── evaluator_judge.py      # LLM-as-a-Judge (Score 0.0 a 1.0)
│       ├── reflexion_engine.py     # Loop de Auto-Correção com Circuit Breaker (MAX_TURNS = 3)
│       ├── skill_synthesizer.py    # Síntese de Skills com Deduplicação Vetorial (Cosine Sim > 0.85 = Merge)
│       └── telemetry_store.py      # Persistência SQLite/Postgres + pgvector
└── scripts/
    └── verify_system.py            # Diagnóstico de pré-requisitos, túnel RTX 5090 e binários
```

---

## 3. ESPECIFICAÇÃO DOS MÓDULOS CRÍTICOS

### 3.1. Isolamento Total com Git Worktrees (`worktree_manager.py`)
* Proibido rodar `git checkout` no diretório principal onde o usuário está com a IDE aberta.
* Para cada tarefa do Coding Council, o `worktree_manager.py` executa:
  `git worktree add -b omni/task-<id> <repo_parent>/.omni_sandboxes/task-<id> HEAD`
* Todos os subprocessos (`claude_driver`, `auditor_codex_driver`, `aider_driver`) executam com `cwd` apontando para a pasta isolada da Worktree.
* **Merge Condicional:** Somente quando o `auditor_codex_driver` aprovar os testes E o `evaluator_judge` atribuir score $\ge 0.85$, o `worktree_manager` faz o merge limpo na branch solicitada (ou mantém a branch pronta para PR) e remove a worktree temporária (`git worktree remove --force`).

### 3.2. Drivers do Conselho de Código (`omni_core/coding_council/`)
* **`claude_driver.py`**:
  * Injeta `ANTHROPIC_BASE_URL=http://127.0.0.1:4000` (Gateway Local que traduz `/v1/messages` para o Ollama e controla o semáforo da GPU) e `ANTHROPIC_API_KEY=omni-local`.
  * Possui fallback automático para motor de criação multi-arquivo via Aider/LangGraph se o binário `claude` não estiver instalado.
* **`auditor_codex_driver.py` (Runner Determinístico + Agêntico)**:
  * **Passo A (Determinístico):** Detecta automaticamente a stack do repositório na worktree (`pyproject.toml`, `package.json`, `.csproj`) e executa suites reais de validação (`pytest`, `ruff check`, `npm test`, `tsc --noEmit`, `dotnet build`).
  * **Passo B (Agêntico):** Se o CLI `codex` estiver presente no PATH, executa a auditoria agêntica; caso contrário (ou em complemento), envia o git diff sanitizado + output real dos testes para o LLM Auditor via Gateway Local analisar falhas lógicas, contratos quebrados e cobertura.
* **`aider_driver.py`**:
  * Conecta de forma 100% explícita ao Gateway Local:
    `aider --model openai/qwen3.8-pro --openai-api-base http://127.0.0.1:4000/v1 --openai-api-key omni-local --yes-always --no-pretty --no-stream --message "<traceback_and_fix_instruction>"`

### 3.3. Circuit Breaker no `reflexion_engine.py`
* Limite rígido: `MAX_GLOBAL_REFLEXION_TURNS = 3`.
* A cada falha (score $< 0.85$), incrementa `state["reflexion_turn"]`.
* Se `reflexion_turn >= 3`, o Circuit Breaker abre: interrompe o loop imediatamente, preserva o log na worktree e aciona o `mobile_notifier.py` solicitando decisão humana (Human-in-the-Loop).

### 3.4. Tiered Safety Policy no "God Mode" (`safety_gate.py`)
* **Tier 1 (Green - Auto-Approve):** Leitura de arquivos, status de sistema, git status/diff, execução de testes em worktrees, queries SELECT, containers de dev.
* **Tier 2 (Yellow - Sandbox/Snapshot Required):** Edição de código (forçada dentro de Git Worktree), instalação de pacotes locais em `.venv`/`node_modules`, restart de serviços Docker.
* **Tier 3 (Red - Destructive / Host-Level):** Comandos contendo padrões destrutivos (`rm -rf`, `Remove-Item -Recurse`, `DROP`, `DELETE` sem where, formatação, encerramento de processos críticos do Windows, deleção fora de worktrees). Bloqueio automático no `safety_gate.py` até que o usuário envie confirmação explícita via token/botão no Telegram/WhatsApp.

### 3.5. Skill Synthesizer com Desduplicação Semântica (`skill_synthesizer.py`)
* Antes de salvar uma nova `SKILL.md` em `skills/auto_learned/`, gera o embedding da lição aprendida e consulta o `telemetry_store.py`.
* Se encontrar uma skill existente com Similaridade de Cosseno $> 0.85$, carrega o arquivo `.md` existente, faz um Merge Evolutivo (atualizando a skill antiga com o novo caso de borda sem duplicar arquivos) e reindexa o vetor.

---

## 4. PLANO DE EXECUÇÃO SEQUENCIAL

* **FASE 1: Fundação e Setup do Repositório (EM PROGRESSO)**
  * Árvore de diretórios completa do `hermes-omni`.
  * `pyproject.toml`, `.env.example`, `docker-compose.yml`, `SOUL.md`.
  * `omni_core/config.py` e `omni_core/llm_gateway.py` (com proxy local FastAPI, semáforo IPC e tradução Anthropic/OpenAI -> Ollama).
* **FASE 2: Conselho de Código (Worktrees + Claude + Codex + Aider)**
* **FASE 3: Sub-Agentes Especialistas e Modo Deus Filtrado**
* **FASE 4: Metacognição (Judge, Reflexion Circuit Breaker, Deduplicating Auto-Skills)**
* **FASE 5: Grafo Supervisor, Gateway Mobile e Testes End-to-End**
