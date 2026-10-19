"""Automated tests for Mobile Notifier and Supervisor routing in Hermes-Omni."""

from pathlib import Path
import pytest

from omni_core.orchestrator.mobile_notifier import MobileNotifier
from omni_core.orchestrator.safety_gate import SafetyGate
from omni_core.orchestrator.supervisor_graph import (
    intent_router_node,
    route_judge_decision,
    route_reflexion_decision,
)
from omni_core.self_improvement.telemetry_store import TelemetryStore


@pytest.mark.asyncio
async def test_mobile_notifier_commands(tmp_path: Path):
    """Verify mobile command handling and token confirmation."""
    db_path = tmp_path / "test_mobile.db"
    telemetry = TelemetryStore(db_path=db_path)
    gate = SafetyGate()
    notifier = MobileNotifier(safety_gate=gate, telemetry=telemetry)

    # Status command
    status_resp = await notifier.handle_mobile_command(user_id=123, command_text="/status")
    assert "Hermes-Omni System Status" in status_resp

    # Quarantine and confirm command flow
    eval_res = gate.evaluate_command("rm -rf /test/dir")
    assert eval_res.confirmation_token is not None
    token = eval_res.confirmation_token

    confirm_resp = await notifier.handle_mobile_command(
        user_id=123, command_text=f"/confirm {token}"
    )
    assert "Authorized Tier 3 Command" in confirm_resp


@pytest.mark.asyncio
async def test_supervisor_intent_classification():
    """Verify that user queries route to appropriate domain specialists."""
    # Coding intent
    state_code = {"user_query": "Fix the bug in the authentication class"}
    res_code = await intent_router_node(state_code)
    assert res_code["intent_route"] == "coding_council"

    # DevOps intent
    state_ops = {"user_query": "Check docker container status and compose logs"}
    res_ops = await intent_router_node(state_ops)
    assert res_ops["intent_route"] == "devops_infra"

    # Database intent
    state_db = {"user_query": "Run SQL query on users table to verify schema"}
    res_db = await intent_router_node(state_db)
    assert res_db["intent_route"] == "data_db"


def test_supervisor_conditional_decisions():
    """Verify routing decisions between success, reflexion, and circuit breaking."""
    # Case 1: High assertiveness -> skill synthesis
    state_pass = {
        "assertiveness_score": 0.95,
        "judge_evaluation": {"hallucination_detected": False},
    }
    assert route_judge_decision(state_pass) == "skill_synthesis"

    # Case 2: Low score -> reflexion
    state_fail = {
        "assertiveness_score": 0.70,
        "judge_evaluation": {"hallucination_detected": False},
    }
    assert route_judge_decision(state_fail) == "reflexion"

    # Case 3: Reflexion retry
    state_retry = {"circuit_breaker_triggered": False}
    assert route_reflexion_decision(state_retry) == "dispatch_specialist"

    # Case 4: Circuit breaker tripped -> END
    state_breaker = {"circuit_breaker_triggered": True}
    assert route_reflexion_decision(state_breaker) == "__end__"
