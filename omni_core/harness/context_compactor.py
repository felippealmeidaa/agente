"""Context Compactor for Multi-Hour Autonomous Harness Sessions.

Prevents Context Rot within long tasks by compressing conversational turns
and passing only essential architectural summaries, files touched, and active goals.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


class ContextCompactor:
    """Summarizes and compacts past steps to keep prompt size lean and high-signal."""

    @staticmethod
    def compact_history(past_steps: List[Dict[str, Any]], max_recent_steps: int = 3) -> Dict[str, Any]:
        """Keeps full details for recent steps, and creates a condensed summary of older steps."""
        if len(past_steps) <= max_recent_steps:
            return {
                "summary": "Recent interaction without compaction.",
                "active_steps": past_steps,
            }

        older_steps = past_steps[:-max_recent_steps]
        recent_steps = past_steps[-max_recent_steps:]

        summary_lines = []
        for step in older_steps:
            desc = step.get("description", "Action performed")
            status = step.get("status", "completed")
            summary_lines.append(f"- {desc} (status: {status})")

        return {
            "summary": "Condensed past execution summary:\n" + "\n".join(summary_lines),
            "active_steps": recent_steps,
        }
