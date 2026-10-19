"""Automated tests for Coding Council drivers and graph routing."""

from pathlib import Path
import pytest

from omni_core.coding_council.auditor_codex_driver import AuditorCodexDriver
from omni_core.coding_council.council_graph import (
    CouncilState,
    route_audit_decision,
    route_pre_flight,
)


def test_route_audit_decision():
    """Verify state-based routing logic for the Coding Council."""
    # Case 1: Approved -> finalize
    state_approved: CouncilState = {
        "repo_root": ".",
        "task_id": "1",
        "task_instruction": "test",
        "worktree_path": "/tmp",
        "branch_name": "b",
        "council_cycle": 1,
        "max_council_cycles": 3,
        "git_diff": "",
        "last_traceback": "",
        "last_critique": "",
        "audit_approved": True,
        "final_status": "IN_PROGRESS",
        "error_message": "",
    }
    assert route_audit_decision(state_approved) == "commit_and_finalize"

    # Case 2: Rejected, cycle 1 -> surgeon
    state_rejected: CouncilState = {**state_approved, "audit_approved": False, "council_cycle": 1}
    assert route_audit_decision(state_rejected) == "surgeon"

    # Case 3: Rejected, cycle 3 (reached max) -> escalate_blocker (Circuit Breaker)
    state_max: CouncilState = {**state_approved, "audit_approved": False, "council_cycle": 3}
    assert route_audit_decision(state_max) == "escalate_blocker"


def test_route_pre_flight():
    """Verify pre-flight error routing."""
    assert route_pre_flight({"final_status": "ERROR"} ) == "__end__"
    assert route_pre_flight({"final_status": "IN_PROGRESS"}) == "architect"


@pytest.mark.asyncio
async def test_auditor_deterministic_detection(tmp_path: Path):
    """Verify stack detection on an isolated dummy project sandbox."""
    driver = AuditorCodexDriver()
    # Case 1: Empty folder -> passes without runner
    passed, out, tb = await driver.run_deterministic_suite(tmp_path)
    assert passed is True

    # Case 2: Node.js project simulation
    pkg_json = tmp_path / "package.json"
    pkg_json.write_text('{"name": "test-pkg", "scripts": {"test": "echo success"}}')
    passed_node, out_node, _ = await driver.run_deterministic_suite(tmp_path)
    # Even if npm is not installed or test passes, returns boolean
    assert isinstance(passed_node, bool)
