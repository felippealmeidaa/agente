"""Reflexion Engine for Autonomous Self-Correction and Circuit Breaking.

Intercepts deliverables with final_assertiveness_score < 0.85 or hallucination_detected == True.
- Injects structured critique and improvement actions back into agent context.
- Enforces a hard Circuit Breaker at MAX_GLOBAL_REFLEXION_TURNS = 3 to prevent token loops.
- Prepares human escalation payloads when the circuit breaker opens.
"""

import logging
from typing import Any, Dict, Tuple

from pydantic import BaseModel

from omni_core.config import get_settings
from omni_core.orchestrator.state import AssertivenessEvaluation

logger = logging.getLogger("omni_core.self_improvement.reflexion_engine")
settings = get_settings()


class ReflexionDecision(BaseModel):
    """Decision produced by the Reflexion Engine."""
    approved: bool
    should_retry: bool
    circuit_breaker_opened: bool
    current_turn: int
    max_turns: int
    critique_to_inject: str
    improvement_action_to_inject: str
    escalation_message: str = ""


class ReflexionEngine:
    """Manages reflection loops, retry state, and loop circuit breakers."""

    def __init__(self, max_turns: int = 3):
        self.max_turns = max_turns

    def evaluate_loop_state(
        self,
        current_turn: int,
        evaluation: AssertivenessEvaluation,
    ) -> ReflexionDecision:
        """Evaluate if the task is finished or requires self-correction."""
        # Quality cutoff rule from Spec:
        is_high_quality = (
            evaluation.final_assertiveness_score >= 0.85
            and not evaluation.hallucination_detected
            and evaluation.task_completed
        )

        if is_high_quality:
            logger.info(
                f"Reflexion: Task APPROVED with score {evaluation.final_assertiveness_score:.2f}."
            )
            return ReflexionDecision(
                approved=True,
                should_retry=False,
                circuit_breaker_opened=False,
                current_turn=current_turn,
                max_turns=self.max_turns,
                critique_to_inject="",
                improvement_action_to_inject="",
            )

        # Check circuit breaker
        next_turn = current_turn + 1
        if next_turn >= self.max_turns:
            logger.warning(
                f"Reflexion: Circuit Breaker OPENED after {self.max_turns} attempts. Score: {evaluation.final_assertiveness_score:.2f}."
            )
            escalation = (
                f"⚠️ Circuit Breaker Triggered (Turn {next_turn}/{self.max_turns}).\n"
                f"Quality score: {int(evaluation.final_assertiveness_score * 100)}%.\n"
                f"Reason: {evaluation.critique}\n"
                f"Action needed: Human guidance required."
            )
            return ReflexionDecision(
                approved=False,
                should_retry=False,
                circuit_breaker_opened=True,
                current_turn=next_turn,
                max_turns=self.max_turns,
                critique_to_inject=evaluation.critique,
                improvement_action_to_inject=evaluation.improvement_action or "",
                escalation_message=escalation,
            )

        logger.info(
            f"Reflexion: Retrying with critique (Turn {next_turn}/{self.max_turns}). Score: {evaluation.final_assertiveness_score:.2f}"
        )
        return ReflexionDecision(
            approved=False,
            should_retry=True,
            circuit_breaker_opened=False,
            current_turn=next_turn,
            max_turns=self.max_turns,
            critique_to_inject=evaluation.critique,
            improvement_action_to_inject=evaluation.improvement_action or "Review errors and correct previous mistakes.",
        )
