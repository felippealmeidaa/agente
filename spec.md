# MASTER PROMPT & ARCHITECTURAL SPECIFICATION v3.0: PROJETO "HERMES-OMNI"
**Target Environment:** Antigravity IDE (Agentic Development Mode)  
**Architecture Pattern:** Hermes Agent Native Core + OmniCore Extension Suite (Continuous Learning, Deterministic Harness, Niche Specialists & Skill Harvester)

---

## 1. VISÃO GERAL E ALINHAMENTO
O projeto unifica o ecossistema oficial do **Hermes Agent (Nous Research)** com os super-poderes autônomos do **OmniCore**:
1. O runtime, CLI, gateways de mensageria (WhatsApp/Telegram/Discord), barramento de ferramentas e loop de conversação residem nativamente no motor do Hermes (`run_agent.py`, `cli.py`, `gateway/`, `tools/`).
2. O pacote `omni_core/` fornece extensões de alto nível:
   * **Aprendizado Contínuo Bilateral**: Captura automática de correções humanas (`human_feedback_learner.py`) + Injeção pré-voo (`pre_flight_memory.py`).
   * **Anti-Regressão Matemática**: Política "Every Bug Becomes a Test" com suíte cumulativa (`regression_guard.py`).
   * **Metodologia Agent Harness**: Autonomia multi-hora em 6 estágios (`harness/`).
   * **Ecossistema de Skills por Nicho & Harvester**: Roteamento dinâmico sem estourar o contexto de 64k (`skill_router.py`) + Harvester com sanitização de segurança (`skill_harvester.py`) + Ponte REA/RES e Chrome Debugging (`mcp_rea_bridge.py`).

---

## 2. ESTRUTURA UNIFICADA DO REPOSITÓRIO

```text
hermes-omni/
├── agent/                          # Hermes Core Turn Loop, Memory & System Prompt
│   ├── omni_preflight_hook.py      # Hook pré-voo de injeção de HUMAN_GOLDEN_RULES
│   └── system_prompt.py            # System Prompt do Hermes patchado com Omni Hook
├── gateway/                        # Gateways nativos do Hermes (WhatsApp, Telegram, Slack, etc.)
├── tools/                          # Ferramentas nativas do Hermes
│   └── omni_core_tools.py          # Registro oficial de ferramentas OmniCore no registry Hermes
├── skills/                         # Skills em Markdown (Superpowers, REA, etc.)
│   ├── auto_learned/               # Skills sintetizadas ou colhidas via GitHub
│   ├── superpowers/                # obra/superpowers (TDD, Systematic Debugging, Writing Plans)
│   └── reverse-engineer-anything/  # morluto/rea e alextnetto/res
├── omni_core/
│   ├── coding_council/
│   │   ├── council_graph.py        # Orquestrador do Conselho de Código
│   │   ├── claude_driver.py        # Driver Claude Code
│   │   ├── auditor_codex_driver.py # Auditor determinístico e agêntico
│   │   ├── aider_driver.py         # Cirurgião de código Aider
│   │   ├── worktree_manager.py     # Gerenciamento de Git Worktree
│   │   └── regression_guard.py     # Anti-regressão matemática acumulada
│   ├── self_improvement/
│   │   ├── human_feedback_learner.py   # Extração de UserCorrectionRule & SOUL.md sync
│   │   ├── pre_flight_memory.py        # Injeção de restrições negativas no prompt
│   │   ├── evaluator_judge.py          # LLM-as-a-Judge
│   │   ├── reflexion_engine.py         # Auto-reflexão com Circuit Breaker
│   │   └── telemetry_store.py          # Persistência de lições e regras
│   ├── harness/                        # METODOLOGIA HARNESS (AUTONOMIA DETERMINÍSTICA)
│   │   ├── harness_runner.py           # Ciclo de 6 Estágios (obra/superpowers)
│   │   ├── evidence_verifier.py        # Evidence Over Claims Gate
│   │   └── context_compactor.py        # Compactador de contexto em sessões longas
│   ├── skills_registry/                # ECOSSISTEMA DE SKILLS & REVERSE ENGINEERING
│   │   ├── skill_router.py             # Roteador dinâmico de skills por nicho
│   │   ├── skill_harvester.py          # GitHub Harvester autônomo com Security Sanitizer
│   │   └── mcp_rea_bridge.py           # Ponte REA, RES e Chrome Remote Debugging (9222)
│   └── specialists/                    # SUB-AGENTES ESPECIALISTAS POR NICHO
│       ├── sec_reverse_agent.py        # Cybersegurança + Engenharia Reversa (REA/RES)
│       ├── frontend_ui_agent.py        # Frontend Next.js / Electron / Playwright Vision
│       ├── clean_code_architect.py     # Clean Code, SOLID, TDD e Design Patterns
│       ├── data_rag_agent.py           # DBA Postgres / pgvector / Agentic RAG
│       └── os_devops_godmode_agent.py  # Automação Full-PC (WSL2 + PowerShell) e Infra
├── tests/
│   ├── regression/                 # Suíte cumulativa gerada pelo RegressionGuard
│   ├── test_coding_council.py
│   ├── test_harness_and_feedback.py
│   ├── test_safety_gate.py
│   ├── test_self_improvement.py
│   └── test_specialists.py
└── scripts/
    ├── bootstrap_skills.py         # Provisionamento inicial de skills (Superpowers, REA)
    └── verify_system.py            # Diagnóstico de ambiente e dependências
```

---

## 3. ESPECIFICAÇÃO DAS NOVAS CAPACIDADES

### 3.1. Aprendizado Bilateral & Zero-Regressão
* **Detecção de Feedback Humano (`human_feedback_learner.py`):** Captura frases imperativas e de correção do usuário, converte em `UserCorrectionRule`, persiste no banco vetorial como `HUMAN_GOLDEN_RULE` com prioridade máxima e escreve na seção imutável do `SOUL.md`.
* **Zero Regressão Cumulativa (`regression_guard.py`):** "Every Bug Becomes a Test". Todo erro corrigido gera um teste em `tests/regression/test_regression_<slug>.py`. A suíte inteira roda antes de qualquer aprovação de merge.
* **Injeção Pré-Voo (`pre_flight_memory.py`):** Busca regras e os top 5 erros passados e os injeta como restrição negativa rigorosa no topo do System Prompt do Hermes.

### 3.2. Metodologia de Harness (6 Estágios)
1. **Socratic Clarifier & Context Discovery:** Resolução de ambiguidades e ativação do Modo Autônomo.
2. **Bite-Sized Plan Generation:** Criação do `OMNI_PLAN.md` com micro-tarefas atômicas de 2 a 5 minutos.
3. **Isolated Workspace:** Git Worktree com baseline de testes verificado.
4. **Subagent-Driven Execution:** Sessão limpa (fresh context) para cada micro-tarefa com skills do nicho.
5. **Strict TDD Enforcement:** Ciclo obrigatório RED -> GREEN -> REFACTOR.
6. **Evidence Gate:** Regra Evidence Over Claims — bloqueio de avanço sem prova real de execução (exit code 0, HTTP 200, output validado).

### 3.3. Skills por Nicho, Superpowers & REA
* **obra/superpowers:** TDD, Systematic Debugging, Writing Plans integrados nativamente.
* **morluto/rea + alextnetto/res (`mcp_rea_bridge.py`):** Engenharia reversa de binários, Electron/ASAR, pacotes Android e inspeção em runtime via Chrome Remote Debugging (porta 9222).
* **GitHub Skill Harvester (`skill_harvester.py`):** Download autônomo de skills do GitHub com sanitização de segurança (bloqueio de comandos destrutivos e prompt injection).
* **Skill Router (`skill_router.py`):** Injeção dinâmica de skills no System Prompt focada exclusivamente no nicho ativo, preservando a janela de contexto de 64k.
