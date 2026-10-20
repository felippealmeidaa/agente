"""Evidence Gate Verifier: Enforces 'Evidence Over Claims' methodology.

Rejects task completion or goal advancement if no empirical proof is recorded in state
(e.g., test suite exit code 0, successful execution output, HTTP 200 payload, or screenshot).
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class ExecutionEvidence(BaseModel):
    """Structured proof of real-world execution."""
    evidence_type: str = Field(description="'test_run', 'http_response', 'command_output', 'screenshot'")
    description: str = Field(description="Description of what was verified")
    verified: bool = Field(default=False)
    exit_code: Optional[int] = Field(default=None)
    details: Optional[str] = Field(default=None)


class EvidenceVerifier:
    """Verifies empirical proofs before marking objectives complete."""

    @staticmethod
    def verify_evidence(evidences: List[Dict[str, Any]]) -> bool:
        """Returns True if there is at least one verified proof with exit_code == 0 or verified=True."""
        if not evidences:
            logger.warning("EvidenceVerifier: No evidence items submitted.")
            return False

        for ev in evidences:
            if ev.get("verified") is True:
                return True
            if ev.get("exit_code") == 0:
                return True
            if ev.get("status_code") in [200, 201, 204]:
                return True

        logger.warning("EvidenceVerifier: Evidence submitted did not meet verification criteria.")
        return False
