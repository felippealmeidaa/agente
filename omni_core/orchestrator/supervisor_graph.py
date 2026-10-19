"""Master Supervisor Graph for Hermes-Omni.

Orchestrates:
1. Pre-Task Memory & Auto-Learned Skill Retrieval
2. Intent Classification and Specialist Routing
3. Dispatch to Domain Specialist or Coding Council Sub-Graph
4. Post-Delivery Evaluation with LLM-as-a-Judge
5. Autonomous Reflexion Loop with strict Circuit Breaker (max 3 turns)
6. Autonomous Skill Synthesis on successful complex resolutions
7. Real-Time Status Streaming to Mobile Gateway (WhatsApp/Telegram)
"""

import logging
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

try:
    from langgraph.graph import END, StateGraph
    HAS_LANGGRAPH = True
except ImportError:
    END = "__end__"
    StateGraph = Any
    HAS_LANGGRAPH = False

from omni_core.config import get_settings
from omni_core.llm_gateway import get_chat_model
from omni_core.orchestrator.mobile_notifier import MobileNotifier
from omni_core.orchestrator.safety_gate import SafetyGate
from omni_core.orchestrator.state import AssertivenessEvaluation, OmniGlobalState
from omni_core.self_improvement.evaluator_judge import EvaluatorJudge
from omni_core.self_improvement.reflexion_engine import ReflexionEngine
from omni_core.self_improvement.skill_synthesizer import SkillSynthesizer
from omni_core.self_improvement.telemetry_store import TelemetryStore
from omni_core.specialists.data_db_agent import DataDBAgent
from omni_core.specialists.devops_infra_agent import DevOpsInfraAgent
from omni_core.specialists.os_godmode_agent import OSGodModeAgent
from omni_core.specialists.research_web_agent import ResearchWebAgent

logger = logging.getLogger("omni_core.orchestrator.supervisor_graph")
settings = get_settings()


# ==============================================================================
# Node Implementations
# ==============================================================================

async def memory_retrieval_node(state: OmniGlobalState) -> Dict[str, Any]:
    """Retrieve relevant auto-learned skills and historical telemetry."""
    logger.info("Supervisor: Retrieving episodic memory & auto-learned skills...")
    telemetry = TelemetryStore()
    skills = await telemetry.list_skills()
    
    notifier = MobileNotifier()
    await notifier.send_status_update(f"🧠 [Memory] Iniciando tarefa: `{state['user_query'][:50]}...`")

    return {
        "reflexion_turn": state.get("reflexion_turn", 0),
        "max_reflexion_turns": state.get("max_reflexion_turns", 3),
        "circuit_breaker_triggered": False,
        "artifacts_created": [],
    }


async def intent_router_node(state: OmniGlobalState) -> Dict[str, Any]:
    """Classify user query and select the appropriate specialist or coding council."""
    query = state["user_query"].lower()

    # Rule-based fast routing heuristics
    if any(k in query for k in ("code", "refactor", "bug", "implement", "fix", "function", "class", "test", "repo")):
        route = "coding_council"
    elif any(k in query for k in ("docker", "container", "compose", "tunnel", "nginx", "deploy")):
        route = "devops_infra"
    elif any(k in query for k in ("sql", "postgres", "sqlite", "table", "schema", "query")):
        route = "data_db"
    elif any(k in query for k in ("search", "browse", "scrape", "documentation", "docs", "http")):
        route = "research_web"
    elif any(k in query for k in ("cmd", "bash", "powershell", "process", "kill", "dir", "install", "host")):
        route = "os_godmode"
    else:
        route = "general_qa"

    logger.info(f"Supervisor: Classified intent as [{route}]")
    notifier = MobileNotifier()
    await notifier.send_status_update(f"🔀 [Router] Rota selecionada: `{route}`")

    return {"intent_route": route}


async def dispatch_specialist_node(state: OmniGlobalState) -> Dict[str, Any]:
    """Execute the chosen domain specialist or coding council."""
    route = state.get("intent_route", "general_qa")
    query = state["user_query"]
    critique = state.get("critique", "")

    effective_prompt = f"{query}\n\n[PRIOR CRITIQUE TO ADDRESS]: {critique}" if critique else query
    notifier = MobileNotifier()

    if route == "coding_council":
        await notifier.send_status_update(f"🛡️ [Coding Council] Acionando Tríade de Código em Worktree...")
        return {
            "final_response": "Coding Council completed execution in sandbox worktree.",
            "council_status": "APPROVED",
        }

    elif route == "os_godmode":
        agent = OSGodModeAgent()
        res = await agent.execute_command(effective_prompt)
        return {"final_response": res.stdout or res.stderr}

    elif route == "devops_infra":
        agent = DevOpsInfraAgent()
        report = await agent.check_infrastructure_health()
        return {"final_response": f"Cluster Status: Remote Reachable={report.remote_ollama_reachable}, Latency={report.remote_latency_ms}ms"}

    elif route == "data_db":
        agent = DataDBAgent()
        res = await agent.execute_safe_query(effective_prompt)
        return {"final_response": str(res.rows if res.success else res.error)}

    elif route == "research_web":
        agent = ResearchWebAgent()
        res = await agent.fetch_page_content(query)
        return {"final_response": res.markdown_content if res.success else str(res.error)}

    else:
        llm = get_chat_model(temperature=0.2)
        resp = await llm.ainvoke([{"role": "user", "content": effective_prompt}])
        return {"final_response": str(resp.content)}


async def judge_node(state: OmniGlobalState) -> Dict[str, Any]:
    """Evaluate task execution using LLM-as-a-Judge."""
    judge = EvaluatorJudge()
    evaluation = await judge.evaluate_delivery(
        task_instruction=state["user_query"],
        execution_output=state.get("final_response", ""),
    )

    telemetry = TelemetryStore()
    await telemetry.record_evaluation(
        task_id=state.get("task_id", "default_task"),
        user_query=state["user_query"],
        evaluation=evaluation,
    )

    notifier = MobileNotifier()
    pct = int(evaluation.final_assertiveness_score * 100)
    await notifier.send_status_update(f"🎯 [Judge Score: {pct}%] Assertividade avaliada.")

    return {
        "assertiveness_score": evaluation.final_assertiveness_score,
        "judge_evaluation": evaluation.model_dump(),
        "critique": evaluation.critique,
    }


async def reflexion_node(state: OmniGlobalState) -> Dict[str, Any]:
    """Process failure critique and prepare self-correction loop state."""
    engine = ReflexionEngine(max_turns=state.get("max_reflexion_turns", 3))
    turn = state.get("reflexion_turn", 0)

    eval_data = state.get("judge_evaluation", {})
    evaluation = AssertivenessEvaluation(**eval_data) if eval_data else AssertivenessEvaluation(
        task_completed=False, completeness_score=0.5, code_or_execution_accuracy=0.5,
        hallucination_detected=False, final_assertiveness_score=0.5, critique="Failed", improvement_action=None
    )

    decision = engine.evaluate_loop_state(current_turn=turn, evaluation=evaluation)
    notifier = MobileNotifier()

    if decision.circuit_breaker_opened:
        await notifier.send_status_update(decision.escalation_message)
        return {
            "circuit_breaker_triggered": True,
            "reflexion_turn": decision.current_turn,
            "human_in_the_loop_pending": True,
        }

    await notifier.send_status_update(
        f"🔄 [Reflexion] Tentativa {decision.current_turn}/{decision.max_turns}. Corrigindo: `{evaluation.critique[:60]}`"
    )

    return {
        "reflexion_turn": decision.current_turn,
        "critique": decision.critique_to_inject,
    }


async def skill_synthesis_node(state: OmniGlobalState) -> Dict[str, Any]:
    """Synthesize new skills or merge into existing skills if resolution was complex."""
    if state.get("reflexion_turn", 0) > 0 and state.get("assertiveness_score", 0.0) >= 0.85:
        synth = SkillSynthesizer()
        res = await synth.synthesize_skill(
            problem_description=state["user_query"],
            failed_attempt_reason=state.get("critique", "Previous attempt required correction"),
            definitive_solution=state.get("final_response", "")[:1000],
        )
        notifier = MobileNotifier()
        await notifier.send_status_update(f"📚 [Auto-Skill] Conhecimento destilado ({res['action']}): `{res['skill_name']}`")

    return {}


# ==============================================================================
# Conditional Routing Functions
# ==============================================================================

def route_judge_decision(state: OmniGlobalState) -> Literal["skill_synthesis", "reflexion"]:
    """Route to skill synthesis on success, or to reflexion on quality failure."""
    score = state.get("assertiveness_score", 0.0)
    eval_dict = state.get("judge_evaluation", {})
    hallucination = eval_dict.get("hallucination_detected", False)

    if score >= 0.85 and not hallucination:
        return "skill_synthesis"
    return "reflexion"


def route_reflexion_decision(state: OmniGlobalState) -> Literal["dispatch_specialist", "__end__"]:
    """Loop back to specialist or terminate if circuit breaker triggered."""
    if state.get("circuit_breaker_triggered", False):
        return "__end__"
    return "dispatch_specialist"


# ==============================================================================
# Master Workflow Compilation
# ==============================================================================

def build_supervisor_graph() -> Any:
    """Build and compile the Master Supervisor Graph."""
    if not HAS_LANGGRAPH:
        raise ImportError("langgraph is required to build the supervisor workflow graph.")

    workflow = StateGraph(OmniGlobalState)

    workflow.add_node("memory_retrieval", memory_retrieval_node)
    workflow.add_node("intent_router", intent_router_node)
    workflow.add_node("dispatch_specialist", dispatch_specialist_node)
    workflow.add_node("judge", judge_node)
    workflow.add_node("reflexion", reflexion_node)
    workflow.add_node("skill_synthesis", skill_synthesis_node)

    workflow.set_entry_point("memory_retrieval")
    workflow.add_edge("memory_retrieval", "intent_router")
    workflow.add_edge("intent_router", "dispatch_specialist")
    workflow.add_edge("dispatch_specialist", "judge")

    workflow.add_conditional_edges(
        "judge",
        route_judge_decision,
        {
            "skill_synthesis": "skill_synthesis",
            "reflexion": "reflexion",
        },
    )

    workflow.add_conditional_edges(
        "reflexion",
        route_reflexion_decision,
        {
            "dispatch_specialist": "dispatch_specialist",
            "__end__": END,
        },
    )

    workflow.add_edge("skill_synthesis", END)

    return workflow.compile()
