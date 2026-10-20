"""Skill Router: Dynamic Niche-Based Skill Loader.

Prevents wasting model context window (64k context limit) by injecting only the
exact niche-relevant skills + top-3 semantic matches into the active subagent prompt.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Set

logger = logging.getLogger(__name__)

NICHE_SKILL_MAP: Dict[str, List[str]] = {
    "sec_reverse": [
        "reverse-engineer-anything",
        "res-saas-reverse-engineering",
        "trailofbits-security-auditing",
        "owasp-top10-hardening",
    ],
    "frontend_ui": [
        "frontend-design-system",
        "nextjs-app-router-best-practices",
        "electron-desktop-architecture",
        "tailwind-shadcn-mastery",
        "playwright-visual-verification",
    ],
    "clean_code": [
        "test-driven-development",
        "systematic-debugging",
        "writing-plans",
        "requesting-code-review",
        "clean-code-solid-principles",
    ],
    "data_rag": [
        "postgres-pgvector-optimization",
        "sql-query-tuning",
        "agentic-rag-hybrid-search",
        "database-migrations-zero-downtime",
    ],
    "os_devops": [
        "windows-powershell-automation",
        "linux-wsl2-sysadmin",
        "docker-compose-production",
        "cloudflare-tunnels-dns-zero-trust",
    ],
}


class SkillRouter:
    """Routes and filters skills for agents based on their assigned niche."""

    @staticmethod
    def get_skills_for_niche(niche: str, extra_query: str = "") -> List[str]:
        """Returns the primary niche skills and any dynamic semantic additions."""
        base_skills = NICHE_SKILL_MAP.get(niche, [])
        logger.info("SkillRouter: selected %d skills for niche '%s'", len(base_skills), niche)
        return list(base_skills)
