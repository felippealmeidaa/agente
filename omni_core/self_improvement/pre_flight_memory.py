"""Pre-Flight Memory Hook for Negative Constraint & Rule Injection.

Fetches:
1. All immutable HUMAN_GOLDEN_RULE items.
2. Top-5 similar lessons learned / past errors from the TelemetryStore.
Builds a strict negative restriction block for injection into the Agent system prompt.
"""

from __future__ import annotations

import logging
from typing import List, Optional

logger = logging.getLogger(__name__)


def retrieve_past_mistakes_and_rules(task_description: str = "") -> str:
    """Queries memory and returns the strict negative constraint block."""
    rules: List[str] = []
    lessons: List[str] = []

    # 1. Load Human Golden Rules from SOUL.md / config
    try:
        from omni_core.config import HUMAN_GOLDEN_RULES
        for r in HUMAN_GOLDEN_RULES:
            rules.append(r)
    except Exception:
        pass

    # 2. Query Telemetry Store
    try:
        from omni_core.self_improvement.telemetry_store import TelemetryStore
        ts = TelemetryStore()
        top_entries = ts.get_relevant_lessons(query=task_description, limit=5)
        for entry in top_entries:
            lessons.append(entry)
    except Exception as exc:
        logger.debug("Failed querying telemetry store for pre-flight memory: %s", exc)

    if not rules and not lessons:
        return ""

    lines = [
        "==================================================================",
        "[⚠️ MEMÓRIA DE ERROS PASSADOS E REGRAS DO USUÁRIO - PROIBIDO VIOLAR]",
    ]

    if rules:
        lines.append("--- REGRAS DE ENGENHARIA MANDATÓRIAS (HUMAN GOLDEN RULES) ---")
        for i, rule in enumerate(rules, 1):
            lines.append(f"{i}. {rule}")

    if lessons:
        lines.append("--- LIÇÕES APRENDIDAS DE ERROS PASSADOS NESTE PROJETO ---")
        for j, lesson in enumerate(lessons, 1):
            lines.append(f"{j}. {lesson}")

    lines.append("==================================================================")
    return "\n".join(lines)
