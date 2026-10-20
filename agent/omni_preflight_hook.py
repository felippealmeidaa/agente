"""OmniCore pre-flight memory hook — injected into the Hermes system-prompt
assembly pipeline.

When Hermes builds the ``volatile`` tier of the system prompt
(see ``agent/system_prompt.py``) it calls
``_collect_volatile_omni_section()`` which this module exposes.

The hook:
1. Loads the HUMAN_GOLDEN_RULES from omni_core config.
2. Fetches the top-N relevant lessons from the telemetry store.
3. Returns a formatted block that Hermes appends to the volatile tier so it
   travels with every API call — keeping the prefix cache warm on the stable
   and context tiers.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Sentinel: if omni_core is not installed, this module is a no-op.
# ---------------------------------------------------------------------------
_OMNI_AVAILABLE = False
try:
    from omni_core import config as _omni_config          # noqa: F401
    _OMNI_AVAILABLE = True
except ImportError:
    pass


_GOLDEN_RULES_HEADER = "## OmniCore: Human Golden Rules & Learned Lessons\n\n"
_MAX_LESSONS = 5  # top lessons to inject per turn


def collect_volatile_omni_section(
    *,
    agent: object | None = None,
    model: str | None = None,
    session_id: str | None = None,
    task_hint: str | None = None,
) -> str:
    """Return a markdown block to append to the Hermes volatile system-prompt tier.

    Called from ``agent/system_prompt.py`` inside ``_build_volatile()``.
    Must be fast (≤50 ms) — no blocking I/O, no LLM calls.
    """
    if not _OMNI_AVAILABLE:
        return ""

    parts: list[str] = [_GOLDEN_RULES_HEADER]

    # ── 1. HUMAN_GOLDEN_RULES ──────────────────────────────────────────────
    try:
        from omni_core.config import HUMAN_GOLDEN_RULES
        if HUMAN_GOLDEN_RULES:
            parts.append("### Golden Rules\n")
            for i, rule in enumerate(HUMAN_GOLDEN_RULES, 1):
                parts.append(f"{i}. {rule}\n")
            parts.append("\n")
    except Exception as exc:  # noqa: BLE001
        logger.debug("omni golden-rules load failed: %s", exc)

    # ── 2. Learned lessons from reflexion store ────────────────────────────
    try:
        from omni_core.self_improvement.telemetry_store import get_top_lessons
        lessons = get_top_lessons(n=_MAX_LESSONS, context=task_hint)
        if lessons:
            parts.append("### Lessons Learned (from past sessions)\n")
            for lesson in lessons:
                parts.append(f"- {lesson}\n")
            parts.append("\n")
    except Exception as exc:  # noqa: BLE001
        logger.debug("omni lessons load failed: %s", exc)

    # ── 3. Active omni gateway config reminder ─────────────────────────────
    try:
        from omni_core.config import LITELLM_BASE_URL, DEFAULT_MODEL
        parts.append(
            f"<!-- omni-gateway: {LITELLM_BASE_URL} | model: {DEFAULT_MODEL} -->\n"
        )
    except Exception:  # noqa: BLE001
        pass

    block = "".join(parts)
    return block if len(block) > len(_GOLDEN_RULES_HEADER) else ""


# ---------------------------------------------------------------------------
# Post-response evaluator hook
# ---------------------------------------------------------------------------

def evaluate_response_quality(
    *,
    response_text: str,
    task_description: str,
    agent: object | None = None,
) -> dict:
    """Called after the Hermes turn finalizer; returns an eval dict.

    Hooks into ``agent/turn_finalizer.py`` (or ``gateway/run_turn.py``) via
    the ``_omni_post_turn_hook`` entry-point pattern.
    Never raises — returns empty dict on any failure.
    """
    if not _OMNI_AVAILABLE or not response_text:
        return {}
    try:
        from omni_core.self_improvement.evaluator_judge import evaluate
        return evaluate(
            response_text=response_text,
            task_description=task_description,
        )
    except Exception as exc:  # noqa: BLE001
        logger.debug("omni evaluator failed: %s", exc)
        return {}
