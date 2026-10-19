"""Automated tests for Metacognition, Reflexion Circuit Breaker, and Skill Deduplication."""

from pathlib import Path
import pytest

from omni_core.orchestrator.state import AssertivenessEvaluation
from omni_core.self_improvement.evaluator_judge import EvaluatorJudge
from omni_core.self_improvement.reflexion_engine import ReflexionEngine
from omni_core.self_improvement.skill_synthesizer import SkillSynthesizer
from omni_core.self_improvement.telemetry_store import TelemetryStore


@pytest.mark.asyncio
async def test_telemetry_store_lifecycle(tmp_path: Path):
    """Verify storing evaluations and calculating quality averages."""
    db_file = tmp_path / "test_telemetry.db"
    store = TelemetryStore(db_path=db_file)

    eval_high = AssertivenessEvaluation(
        task_completed=True,
        completeness_score=0.95,
        code_or_execution_accuracy=0.95,
        hallucination_detected=False,
        final_assertiveness_score=0.95,
        critique="Excellent solution.",
        improvement_action=None,
    )

    rec_id = await store.record_evaluation(
        task_id="task_1",
        user_query="implement fast sort",
        evaluation=eval_high,
    )
    assert rec_id.startswith("eval_")

    avg_score = await store.get_average_score()
    assert avg_score == 0.95


def test_reflexion_circuit_breaker():
    """Verify that Reflexion Engine retries up to 3 turns then triggers Circuit Breaker."""
    engine = ReflexionEngine(max_turns=3)

    eval_fail = AssertivenessEvaluation(
        task_completed=False,
        completeness_score=0.6,
        code_or_execution_accuracy=0.5,
        hallucination_detected=False,
        final_assertiveness_score=0.55,
        critique="Unit tests failed.",
        improvement_action="Fix syntax error on line 42",
    )

    # Turn 0 -> Should retry (turn 1)
    d1 = engine.evaluate_loop_state(current_turn=0, evaluation=eval_fail)
    assert d1.approved is False
    assert d1.should_retry is True
    assert d1.circuit_breaker_opened is False
    assert d1.current_turn == 1

    # Turn 1 -> Should retry (turn 2)
    d2 = engine.evaluate_loop_state(current_turn=1, evaluation=eval_fail)
    assert d2.should_retry is True
    assert d2.circuit_breaker_opened is False
    assert d2.current_turn == 2

    # Turn 2 -> Circuit breaker opens!
    d3 = engine.evaluate_loop_state(current_turn=2, evaluation=eval_fail)
    assert d3.approved is False
    assert d3.should_retry is False
    assert d3.circuit_breaker_opened is True
    assert "Circuit Breaker Triggered" in d3.escalation_message


@pytest.mark.asyncio
async def test_skill_synthesizer_deduplication(tmp_path: Path):
    """Verify that identical or highly similar skills are merged rather than duplicated."""
    skills_dir = tmp_path / "skills"
    db_path = tmp_path / "skills.db"
    store = TelemetryStore(db_path=db_path)
    synth = SkillSynthesizer(skills_dir=skills_dir, telemetry_store=store)

    # Skill 1: Initial resolution
    res1 = await synth.synthesize_skill(
        problem_description="Fixing postgres connection timeout under high load",
        failed_attempt_reason="Default pool size was too small",
        definitive_solution="Increased max_connections and added connection pooling",
        skill_name="postgres_pool_timeout",
    )
    assert res1["action"] == "created"
    skill_file = Path(res1["file_path"])
    assert skill_file.exists()

    # Skill 2: Very similar problem description -> Must MERGE instead of creating duplicate file!
    res2 = await synth.synthesize_skill(
        problem_description="Fixing postgres connection timeout under extreme load",
        failed_attempt_reason="Pool was exhausted during peak queries",
        definitive_solution="Configured pgbouncer with statement pooling",
    )
    assert res2["action"] == "merged"
    assert res2["similarity"] >= 0.70
    # Verify the file was enhanced
    content = skill_file.read_text(encoding="utf-8")
    assert "Additional Edge Case & Resolution (Merged)" in content
