"""User Feedback & Correction Learner for Hermes Agent.

Detects when the user issues a correction, engineering critique, or explicit constraint
(via CLI, WhatsApp, or Telegram). Extracts structured UserCorrectionRule, persists to
the telemetry store (HUMAN_GOLDEN_RULE with max retrieval priority), and automatically
records immutable rules into SOUL.md.
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Literal, Optional
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

CORRECTION_TRIGGERS = [
    r"^(n[aã]o|não faça|nunca faça|est[aá] errado|pare|está incorreto|nao use|não use)",
    r"(prefiro que|sempre use|mude para|use x em vez|evite|jamais altere|nunca altere)",
    r"^(don't|do not|never|stop|wrong|incorrect|instead of|prefer)",
]

_TRIGGER_REGEX = re.compile("|".join(CORRECTION_TRIGGERS), re.IGNORECASE)


class UserCorrectionRule(BaseModel):
    """Structured representation of an extracted engineering correction or preference."""
    trigger_context: str = Field(description="Context when this rule applies (e.g. 'Ao criar endpoints FastAPI')")
    wrong_behavior: str = Field(description="What was done wrong and must never be repeated")
    mandatory_correct_behavior: str = Field(description="Mandatory requirement by the user")
    scope: Literal["global", "project_specific"] = Field(default="global")


def is_user_correction(message: str) -> bool:
    """Fast deterministic check to detect if user input is an explicit correction."""
    cleaned = message.strip()
    if len(cleaned) < 5:
        return False
    return bool(_TRIGGER_REGEX.search(cleaned))


def extract_correction_rule(user_message: str, last_assistant_action: str = "") -> UserCorrectionRule:
    """Extracts a structured UserCorrectionRule from the feedback message."""
    # Deterministic heuristics with fallback extraction
    msg_clean = user_message.strip()
    trigger_ctx = "General Coding and Execution"
    
    if any(k in msg_clean.lower() for k in ["api", "endpoint", "fastapi", "route"]):
        trigger_ctx = "API and Endpoint Design"
    elif any(k in msg_clean.lower() for k in ["test", "pytest", "mock", "tdd"]):
        trigger_ctx = "Testing and Verification"
    elif any(k in msg_clean.lower() for k in ["git", "commit", "branch", "worktree"]):
        trigger_ctx = "Git and Repository Operations"
    elif any(k in msg_clean.lower() for k in ["banco", "db", "sql", "postgres", "migration"]):
        trigger_ctx = "Database & Persistence"

    wrong = last_assistant_action or "Previous rejected pattern"
    correct = msg_clean
    scope: Literal["global", "project_specific"] = "global"

    return UserCorrectionRule(
        trigger_context=trigger_ctx,
        wrong_behavior=wrong,
        mandatory_correct_behavior=correct,
        scope=scope
    )


def append_rule_to_soul_md(rule: UserCorrectionRule, soul_path: Optional[Path] = None) -> bool:
    """Appends an immutable human golden rule to SOUL.md."""
    if soul_path is None:
        soul_path = Path("SOUL.md")

    if not soul_path.exists():
        soul_path.write_text("# Hermes Agent - SOUL\n\n## REGRAS APRENDIDAS COM O USUÁRIO (IMUTÁVEIS)\n\n", encoding="utf-8")

    content = soul_path.read_text(encoding="utf-8")
    section_header = "## REGRAS APRENDIDAS COM O USUÁRIO (IMUTÁVEIS)"

    rule_entry = (
        f"- [REGRA_USUARIO] Contexto: {rule.trigger_context} | "
        f"Exigência: {rule.mandatory_correct_behavior} | "
        f"Proibido: {rule.wrong_behavior}\n"
    )

    if rule_entry in content:
        return False  # Already present

    if section_header in content:
        new_content = content.replace(section_header, f"{section_header}\n{rule_entry}")
    else:
        new_content = f"{content}\n\n{section_header}\n{rule_entry}\n"

    soul_path.write_text(new_content, encoding="utf-8")
    logger.info("Nova HUMAN_GOLDEN_RULE persistida com sucesso em SOUL.md")
    return True


def record_user_feedback(user_message: str, last_assistant_action: str = "") -> Optional[UserCorrectionRule]:
    """Top-level pipeline executed when user input is received.
    
    1. Detects correction.
    2. Builds UserCorrectionRule.
    3. Persists to telemetry_store (with boost=2.0).
    4. Persists to SOUL.md.
    """
    if not is_user_correction(user_message):
        return None

    rule = extract_correction_rule(user_message, last_assistant_action)

    # 1. Telemetry Store Persistence
    try:
        from omni_core.self_improvement.telemetry_store import TelemetryStore
        ts = TelemetryStore()
        lesson_text = f"Context: {rule.trigger_context} | Mandatory: {rule.mandatory_correct_behavior} | Never: {rule.wrong_behavior}"
        ts.record_reflection(
            task=rule.trigger_context,
            attempt=rule.wrong_behavior,
            failure_reason="Human Correction",
            lesson=lesson_text,
            rule_type="HUMAN_GOLDEN_RULE",
            boost=2.0
        )
    except Exception as exc:
        logger.warning("Could not persist to telemetry store: %s", exc)

    # 2. SOUL.md Persistence
    if rule.scope == "global":
        try:
            append_rule_to_soul_md(rule)
        except Exception as exc:
            logger.warning("Could not persist rule to SOUL.md: %s", exc)

    return rule
