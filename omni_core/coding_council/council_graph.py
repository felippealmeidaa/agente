"""LangGraph Orchestration Sub-Graph for the Coding Council.

Orchestrates the Triad of Software Engineering inside an isolated Git Worktree:
1. Pre-Flight: Spawns isolated Git Worktree (.omni_sandboxes/task_<id>).
2. Architect (Claude Code): Implements the architectural design and code.
3. Auditor (Codex / Deterministic): Runs test suites and audits git diff.
4. Surgeon (Aider): Applies surgical diff fixes if tests fail (max 3 cycles).
5. Finalize: Commits and cleans up or escalates to human if circuit breaker opens.
"""

import logging
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, TypedDict

try:
    from langgraph.graph import END, StateGraph
    HAS_LANGGRAPH = True
except ImportError:
    END = "__end__"
    StateGraph = Any
    HAS_LANGGRAPH = False

from omni_core.coding_council.aider_driver import AiderDriver
from omni_core.coding_council.auditor_codex_driver import AuditorCodexDriver, AuditReport
from omni_core.coding_council.claude_driver import ClaudeDriver
from omni_core.coding_council.worktree_manager import WorktreeManager

logger = logging.getLogger("omni_core.coding_council.council_graph")


class CouncilState(TypedDict):
    """Global state flowing through the Coding Council LangGraph."""
    repo_root: str
    task_id: str
    task_instruction: str
    worktree_path: str
    branch_name: str
    council_cycle: int
    max_council_cycles: int
    git_diff: str
    last_traceback: str
    last_critique: str
    audit_approved: bool
    final_status: str  # "APPROVED", "BLOCKED", "ERROR"
    error_message: str


# ==============================================================================
# Node Implementations
# ==============================================================================

async def pre_flight_node(state: CouncilState) -> Dict[str, Any]:
    """Initialize the isolated Git Worktree for the task."""
    logger.info(f"Council Pre-Flight: Setting up worktree for task {state['task_id']}")
    wm = WorktreeManager()
    repo_root = Path(state["repo_root"])

    try:
        worktree_path, branch_name = await wm.create_worktree(
            repo_root=repo_root,
            task_id=state["task_id"],
        )
        return {
            "worktree_path": str(worktree_path),
            "branch_name": branch_name,
            "council_cycle": 0,
            "max_council_cycles": state.get("max_council_cycles", 3),
            "audit_approved": False,
            "final_status": "IN_PROGRESS",
        }
    except Exception as exc:
        logger.error(f"Pre-flight failed: {exc}")
        return {
            "final_status": "ERROR",
            "error_message": f"Failed to create worktree: {exc}",
        }


async def architect_node(state: CouncilState) -> Dict[str, Any]:
    """Execute Claude Code to construct or refactor code in the worktree."""
    logger.info("Council Architect: Dispatching Claude Code...")
    driver = ClaudeDriver()
    wm = WorktreeManager()
    worktree_path = Path(state["worktree_path"])

    result = await driver.execute_task(
        prompt=state["task_instruction"],
        worktree_path=worktree_path,
    )

    diff = await wm.get_clean_diff(worktree_path)
    return {
        "git_diff": diff,
        "last_critique": result.output if not result.success else "",
    }


async def auditor_node(state: CouncilState) -> Dict[str, Any]:
    """Execute deterministic test suite and semantic diff audit."""
    logger.info(f"Council Auditor: Auditing worktree (Cycle {state.get('council_cycle', 0)})...")
    driver = AuditorCodexDriver()
    worktree_path = Path(state["worktree_path"])

    report: AuditReport = await driver.audit_worktree(
        worktree_path=worktree_path,
        git_diff=state.get("git_diff", ""),
        task_instruction=state["task_instruction"],
    )

    return {
        "audit_approved": report.approved,
        "last_traceback": report.traceback,
        "last_critique": report.agentic_critique,
    }


async def surgeon_node(state: CouncilState) -> Dict[str, Any]:
    """Execute Aider to surgically patch failing tests or code bugs."""
    cycle = state.get("council_cycle", 0) + 1
    logger.info(f"Council Surgeon: Applying surgical patch (Cycle {cycle}/{state['max_council_cycles']})...")

    driver = AiderDriver()
    wm = WorktreeManager()
    worktree_path = Path(state["worktree_path"])

    failure_context = (
        state.get("last_traceback", "")
        or state.get("last_critique", "Audit rejected the changes.")
    )

    await driver.execute_surgical_fix(
        worktree_path=worktree_path,
        traceback_or_critique=failure_context,
        task_instruction=state["task_instruction"],
    )

    new_diff = await wm.get_clean_diff(worktree_path)
    return {
        "council_cycle": cycle,
        "git_diff": new_diff,
    }


async def commit_and_finalize_node(state: CouncilState) -> Dict[str, Any]:
    """Commit verified changes and mark the task as approved."""
    logger.info("Council Finalize: Committing changes in worktree sandbox.")
    wm = WorktreeManager()
    worktree_path = Path(state["worktree_path"])

    await wm.commit_changes(
        worktree_path=worktree_path,
        message=f"feat(omni): verified implementation for task {state['task_id']}",
    )

    return {
        "final_status": "APPROVED",
    }


async def escalate_blocker_node(state: CouncilState) -> Dict[str, Any]:
    """Circuit breaker opened: preserve worktree and escalate to human."""
    logger.warning(
        f"Council Blocker: Reached maximum cycles ({state['max_council_cycles']}). Escalating to human."
    )
    return {
        "final_status": "BLOCKED",
        "error_message": (
            f"Exceeded {state['max_council_cycles']} correction cycles. "
            f"Traceback: {state.get('last_traceback', '')}"
        ),
    }


# ==============================================================================
# Conditional Routing
# ==============================================================================

def route_pre_flight(state: CouncilState) -> Literal["architect", "__end__"]:
    """Check if pre-flight successfully spawned the sandbox."""
    if state.get("final_status") == "ERROR":
        return "__end__"
    return "architect"


def route_audit_decision(state: CouncilState) -> Literal["commit_and_finalize", "surgeon", "escalate_blocker"]:
    """Route based on audit approval and cycle limits."""
    if state.get("audit_approved") is True:
        return "commit_and_finalize"

    if state.get("council_cycle", 0) >= state.get("max_council_cycles", 3):
        return "escalate_blocker"

    return "surgeon"


# ==============================================================================
# Graph Construction
# ==============================================================================

def build_council_graph() -> Any:
    """Build and compile the LangGraph Coding Council workflow."""
    if not HAS_LANGGRAPH:
        raise ImportError("langgraph is required to build the council workflow graph. Please install it.")
    workflow = StateGraph(CouncilState)

    # Add Nodes
    workflow.add_node("pre_flight", pre_flight_node)
    workflow.add_node("architect", architect_node)
    workflow.add_node("auditor", auditor_node)
    workflow.add_node("surgeon", surgeon_node)
    workflow.add_node("commit_and_finalize", commit_and_finalize_node)
    workflow.add_node("escalate_blocker", escalate_blocker_node)

    # Set Entry Point
    workflow.set_entry_point("pre_flight")

    # Add Edges
    workflow.add_conditional_edges(
        "pre_flight",
        route_pre_flight,
        {
            "architect": "architect",
            "__end__": END,
        },
    )

    workflow.add_edge("architect", "auditor")

    workflow.add_conditional_edges(
        "auditor",
        route_audit_decision,
        {
            "commit_and_finalize": "commit_and_finalize",
            "surgeon": "surgeon",
            "escalate_blocker": "escalate_blocker",
        },
    )

    # After surgeon fixes, loop back to auditor
    workflow.add_edge("surgeon", "auditor")

    # Terminating edges
    workflow.add_edge("commit_and_finalize", END)
    workflow.add_edge("escalate_blocker", END)

    return workflow.compile()
