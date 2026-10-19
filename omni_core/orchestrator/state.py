"""Global TypedDict and Pydantic Schemas for Hermes-Omni Orchestration.

Maintains multi-turn context, intent routing, coding council artifacts,
assertiveness evaluations, and mobile communication logs.
"""

from typing import Any, Dict, List, Literal, Optional, TypedDict
from pydantic import BaseModel, Field


class SafetyEvaluationResult(BaseModel):
    """Result of evaluating an operation against the Tiered Safety Policy."""
    tier: Literal["tier1_green", "tier2_yellow", "tier3_red"]
    is_safe_to_execute: bool
    requires_human_confirmation: bool
    reason: str
    target_command_or_path: str
    confirmation_token: Optional[str] = None


class AssertivenessEvaluation(BaseModel):
    """Rigorous evaluation rubric scored by the LLM-as-a-Judge."""
    task_completed: bool = Field(description="Was the user's primary goal fully satisfied?")
    completeness_score: float = Field(ge=0.0, le=1.0, description="Completeness of the solution (0.0 to 1.0)")
    code_or_execution_accuracy: float = Field(ge=0.0, le=1.0, description="Accuracy and absence of bugs/breakages (0.0 to 1.0)")
    hallucination_detected: bool = Field(description="True if fictitious functions, files, or facts were cited")
    final_assertiveness_score: float = Field(ge=0.0, le=1.0, description="Composite weighted assertiveness score (0.0 to 1.0)")
    critique: str = Field(description="Detailed critique of what went well and what failed")
    improvement_action: Optional[str] = Field(default=None, description="Actionable step to correct failures")


class OmniGlobalState(TypedDict):
    """Global State passed across Supervisor and Domain Specialists."""
    session_id: str
    user_query: str
    user_voice_audio_path: Optional[str]
    intent_route: Literal["coding_council", "os_godmode", "devops_infra", "data_db", "research_web", "general_qa"]
    
    # Coding Council state
    task_id: str
    worktree_path: Optional[str]
    branch_name: Optional[str]
    council_cycle: int
    council_status: Optional[str]
    
    # Output and artifacts
    final_response: str
    artifacts_created: List[str]
    
    # Self-Improvement & Reflexion
    reflexion_turn: int
    max_reflexion_turns: int
    assertiveness_score: float
    judge_evaluation: Optional[Dict[str, Any]]
    critique: Optional[str]
    circuit_breaker_triggered: bool
    
    # Telemetry and Mobile
    mobile_notifications_sent: List[str]
    human_in_the_loop_pending: bool
