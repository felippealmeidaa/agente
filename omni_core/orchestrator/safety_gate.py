"""Tiered Safety Gate Policy Engine for Hermes-Omni.

Classifies all system, shell, database, and file actions into 3 security tiers:
- Tier 1 (Green - Auto-Approve): Read-only, inspection, sandbox test runs, git status/diff.
- Tier 2 (Yellow - Sandbox Required): Worktree code edits, local venv package installs, docker restarts.
- Tier 3 (Red - Destructive / Host-Level): rm -rf, Remove-Item, DROP/DELETE without WHERE,
  taskkill of host processes, filesystem wiping outside sandboxes.
  -> Strict Human-in-the-Loop (HITL) confirmation required via WhatsApp/Telegram token.
"""

import logging
import re
import secrets
from typing import Dict, Optional

from omni_core.config import get_settings
from omni_core.orchestrator.state import SafetyEvaluationResult

logger = logging.getLogger("omni_core.orchestrator.safety_gate")
settings = get_settings()

# Patterns that trigger immediate Tier 3 (Red) quarantine
TIER3_PATTERNS = [
    re.compile(r"\brm\s+-(?:r|f|rf|fr)\b", re.IGNORECASE),
    re.compile(r"\bRemove-Item\b.*-(?:Recurse|Force)", re.IGNORECASE),
    re.compile(r"\bformat\b\s+[a-z]:", re.IGNORECASE),
    re.compile(r"\bdrop\s+(?:database|table|schema)\b", re.IGNORECASE),
    re.compile(r"\bdelete\s+from\b(?!.*\bwhere\b)", re.IGNORECASE),
    re.compile(r"\btruncate\s+table\b", re.IGNORECASE),
    re.compile(r"\btaskkill\s+/f\b", re.IGNORECASE),
    re.compile(r"\bkill\s+-9\s+1\b", re.IGNORECASE),
    re.compile(r":\(\)\s*\{\s*:\|:&\s*\};:", re.IGNORECASE),  # Forkbomb
    re.compile(r"\bdd\s+if=.*of=/dev/[sh]d[a-z]", re.IGNORECASE),
]

# Patterns recognized as Tier 1 (Green)
TIER1_PATTERNS = [
    re.compile(r"^\s*(?:git\s+(?:status|diff|log|branch|show)|ls|dir|cat|type|pwd|echo|pytest|npm\s+test|node\s+-v|python\s+--version)\b", re.IGNORECASE),
    re.compile(r"^\s*select\s+.*\s+from\s+", re.IGNORECASE),
]


class SafetyGate:
    """Evaluates operations and manages one-time tokens for high-risk actions."""

    def __init__(self):
        # In-memory storage for active confirmation tokens: token -> metadata
        self._pending_confirmations: Dict[str, Dict[str, str]] = {}

    def evaluate_command(self, command_or_action: str) -> SafetyEvaluationResult:
        """Evaluate a shell command or SQL statement against security tiers."""
        cmd_clean = command_or_action.strip()

        if not settings.enable_safety_gate:
            return SafetyEvaluationResult(
                tier="tier1_green",
                is_safe_to_execute=True,
                requires_human_confirmation=False,
                reason="Safety gate is disabled in settings.",
                target_command_or_path=cmd_clean,
            )

        # Check for Tier 3 (Red) destructive patterns
        for pattern in TIER3_PATTERNS:
            if pattern.search(cmd_clean):
                token = secrets.token_hex(3).upper()  # e.g. "A4F89C"
                self._pending_confirmations[token] = {
                    "command": cmd_clean,
                    "tier": "tier3_red",
                }
                logger.warning(
                    f"SAFETY GATE ALERT: Destructive command intercepted [Tier 3]. Token: {token}. Command: {cmd_clean}"
                )
                return SafetyEvaluationResult(
                    tier="tier3_red",
                    is_safe_to_execute=False,
                    requires_human_confirmation=True,
                    reason="Potentially destructive command detected. Human confirmation required.",
                    target_command_or_path=cmd_clean,
                    confirmation_token=token,
                )

        # Check if command contains redirection or file writing
        has_write_redirection = bool(re.search(r"(?:>|>>|\|\s*tee\b)", cmd_clean))

        # Check for Tier 1 (Green) safe patterns
        if not has_write_redirection:
            for pattern in TIER1_PATTERNS:
                if pattern.search(cmd_clean):
                    return SafetyEvaluationResult(
                        tier="tier1_green",
                        is_safe_to_execute=True,
                        requires_human_confirmation=False,
                        reason="Read-only or non-destructive inspection command.",
                        target_command_or_path=cmd_clean,
                    )

        # Default fallback is Tier 2 (Yellow)
        return SafetyEvaluationResult(
            tier="tier2_yellow",
            is_safe_to_execute=True,
            requires_human_confirmation=False,
            reason="Standard operation approved with operational audit logging.",
            target_command_or_path=cmd_clean,
        )

    def confirm_token(self, token: str) -> Optional[str]:
        """Validate a user confirmation token sent via mobile (WhatsApp/Telegram).

        Returns the approved command string if valid, else None.
        """
        token = token.strip().upper()
        if token in self._pending_confirmations:
            entry = self._pending_confirmations.pop(token)
            logger.info(f"Token {token} approved by human. Authorizing command: {entry['command']}")
            return entry["command"]
        return None
