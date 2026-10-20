"""omni_core tool registration — plugs the omni_core extension layer into the
native Hermes tool registry so the AIAgent can invoke it through the standard
tool-call path (CLI, Gateway Telegram/WhatsApp, etc.).

Import chain (cycle-safe, mirrors the Hermes convention):
  tools/omni_core_tools.py  →  tools/registry.py  (no agent.* imports here)
"""

from __future__ import annotations

import json
import logging
import traceback
from typing import Any

from tools.registry import registry, tool_error, tool_result

logger = logging.getLogger(__name__)


def _import_omni(module_path: str):
    """Lazy import; returns None on failure."""
    import importlib
    try:
        return importlib.import_module(module_path)
    except Exception as exc:  # noqa: BLE001
        logger.warning("omni_core unavailable (%s): %s", module_path, exc)
        return None


# ===========================================================================
# 1. CODING COUNCIL
# ===========================================================================

CODING_COUNCIL_SCHEMA = {
    "name": "omni_coding_council",
    "description": (
        "Invoke the OmniCore Coding Council: a multi-model LangGraph pipeline "
        "that runs your code through Aider, Claude-Sonnet auditor and an "
        "optional GPT-4o reviewer, then synthesises a consensus patch. "
        "Use for complex refactors, bug-hunts or when a second (and third) "
        "model opinion is needed."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "task": {
                "type": "string",
                "description": "Natural-language description of the coding task or bug to fix.",
            },
            "repo_path": {
                "type": "string",
                "description": "Absolute path to the git repo the council should work on.",
            },
            "models": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Override the default model list, e.g. ['aider','claude','gpt4o'].",
            },
        },
        "required": ["task"],
    },
}

def _handle_omni_coding_council(args: dict, **kw) -> str:
    mod = _import_omni("omni_core.coding_council.council_graph")
    if mod is None:
        return tool_error("omni_core.coding_council not available")
    try:
        result = mod.run_council(
            task=args["task"],
            repo_path=args.get("repo_path"),
            models=args.get("models"),
        )
        return tool_result(json.dumps(result, ensure_ascii=False))
    except Exception as exc:  # noqa: BLE001
        return tool_error(f"Coding council error: {exc}")

registry.register(
    name="omni_coding_council",
    toolset="omni_core",
    schema=CODING_COUNCIL_SCHEMA,
    handler=_handle_omni_coding_council,
    emoji="🏛️",
)


# ===========================================================================
# 2. SPECIALIST DELEGATION
# ===========================================================================

_SPECIALIST_DESCRIPTIONS = {
    "sec_reverse": "Cybersecurity, reverse engineering, REA, RES, binary & network analysis",
    "frontend_ui": "Next.js, React, Electron, modern responsive design, Playwright verification",
    "clean_code": "Clean Code, SOLID, TDD, architectural refactoring, cyclomatic hygiene",
    "data_rag": "PostgreSQL, pgvector, hybrid search, RAG pipelines, database migrations",
    "os_devops": "Full-PC OS automation, WSL2, PowerShell, Docker, Cloudflare Zero Trust",
}

SPECIALIST_SCHEMA = {
    "name": "omni_delegate_specialist",
    "description": (
        "Delegate a complex domain task to an OmniCore specialized sub-agent: "
        "sec_reverse, frontend_ui, clean_code, data_rag, os_devops."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "specialist": {
                "type": "string",
                "enum": list(_SPECIALIST_DESCRIPTIONS.keys()),
                "description": "Which specialist to invoke.",
            },
            "task": {
                "type": "string",
                "description": "Full task description for the specialist.",
            },
            "context": {
                "type": "object",
                "description": "Optional additional context.",
            },
        },
        "required": ["specialist", "task"],
    },
}

def _handle_omni_delegate_specialist(args: dict, **kw) -> str:
    specialist = args.get("specialist")
    module_map = {
        "sec_reverse": "omni_core.specialists.sec_reverse_agent",
        "frontend_ui": "omni_core.specialists.frontend_ui_agent",
        "clean_code": "omni_core.specialists.clean_code_architect",
        "data_rag": "omni_core.specialists.data_rag_agent",
        "os_devops": "omni_core.specialists.os_devops_godmode_agent",
    }
    target_mod = module_map.get(specialist)
    if not target_mod:
        return tool_error(f"Unknown specialist '{specialist}'")
    mod = _import_omni(target_mod)
    if mod is None:
        return tool_error(f"Specialist module {target_mod} not available")
    try:
        # Dynamically instantiate agent class
        cls_name = {
            "sec_reverse": "SecReverseAgent",
            "frontend_ui": "FrontendUIAgent",
            "clean_code": "CleanCodeArchitectAgent",
            "data_rag": "DataRAGAgent",
            "os_devops": "OSDevopsGodmodeAgent",
        }[specialist]
        agent_instance = getattr(mod, cls_name)()
        result = agent_instance.run(task=args["task"], context=args.get("context", {}))
        return tool_result(json.dumps(result, ensure_ascii=False))
    except Exception as exc:  # noqa: BLE001
        return tool_error(f"Specialist error: {exc}")

registry.register(
    name="omni_delegate_specialist",
    toolset="omni_core",
    schema=SPECIALIST_SCHEMA,
    handler=_handle_omni_delegate_specialist,
    emoji="🎯",
)


# ===========================================================================
# 3. HARNESS RUNNER (6 STAGES)
# ===========================================================================

HARNESS_SCHEMA = {
    "name": "omni_harness_run",
    "description": (
        "Run an autonomous multi-stage execution harness for complex tasks: "
        "Discovery -> OMNI_PLAN.md generation -> Isolated Worktree -> TDD execution -> Evidence verification."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "goal": {
                "type": "string",
                "description": "High-level goal or objective to accomplish autonomously.",
            },
        },
        "required": ["goal"],
    },
}

def _handle_omni_harness_run(args: dict, **kw) -> str:
    mod = _import_omni("omni_core.harness.harness_runner")
    if mod is None:
        return tool_error("Harness runner not available")
    try:
        runner = mod.HarnessRunner()
        stage1 = runner.execute_stage_1_discovery(args["goal"])
        plan_path = runner.execute_stage_2_plan(args["goal"])
        return tool_result(json.dumps({
            "stage1_discovery": stage1,
            "plan_generated": str(plan_path),
            "status": "Harness initialized. OMNI_PLAN.md generated ready for execution.",
        }, ensure_ascii=False))
    except Exception as exc:  # noqa: BLE001
        return tool_error(f"Harness execution error: {exc}")

registry.register(
    name="omni_harness_run",
    toolset="omni_core",
    schema=HARNESS_SCHEMA,
    handler=_handle_omni_harness_run,
    emoji="⚡",
)


# ===========================================================================
# 4. GITHUB SKILL HARVESTER
# ===========================================================================

HARVESTER_SCHEMA = {
    "name": "omni_harvest_skill",
    "description": (
        "Search, download, security-sanitize, and install a new capability skill "
        "into the agent's active skill repertoire."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "niche_query": {
                "type": "string",
                "description": "Skill topic to harvest (e.g. 'linkedin-automation', 'playwright-stealth').",
            },
        },
        "required": ["niche_query"],
    },
}

def _handle_omni_harvest_skill(args: dict, **kw) -> str:
    mod = _import_omni("omni_core.skills_registry.skill_harvester")
    if mod is None:
        return tool_error("Skill harvester not available")
    try:
        harvester = mod.SkillHarvester()
        result = harvester.search_and_install_github_skill(args["niche_query"])
        return tool_result(json.dumps(result, ensure_ascii=False))
    except Exception as exc:  # noqa: BLE001
        return tool_error(f"Skill harvest error: {exc}")

registry.register(
    name="omni_harvest_skill",
    toolset="omni_core",
    schema=HARVESTER_SCHEMA,
    handler=_handle_omni_harvest_skill,
    emoji="🌾",
)
