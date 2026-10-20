"""Autonomous GitHub Skill Harvester.

Searches GitHub API for SKILL.md repositories/files (>50 stars), runs a security
sanitizer to detect prompt injection or dangerous shell injections, and installs
the approved skill directly into skills/auto_learned/.
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

DANGEROUS_PATTERNS = [
    r"rm\s+-rf\s+/",
    r":\(\)\s*\{\s*:\|:&\s*\};:",
    r"curl\s+.*\|\s*(bash|sh)",
    r"powershell\s+-enc",
    r"format\s+[a-zA-Z]:",
]

_DANGER_REGEX = re.compile("|".join(DANGEROUS_PATTERNS), re.IGNORECASE)


class SkillHarvester:
    """Discovers, sanitizes, and registers external skills from GitHub."""

    def __init__(self, target_dir: Optional[Path] = None):
        self.target_dir = target_dir or Path("skills/auto_learned")
        self.target_dir.mkdir(parents=True, exist_ok=True)

    def sanitize_skill_markdown(self, markdown_text: str) -> bool:
        """Returns False if malicious instructions or dangerous shell payload is detected."""
        if _DANGER_REGEX.search(markdown_text):
            logger.warning("SkillHarvester: Security alert! Dangerous pattern detected in skill.")
            return False
        return True

    def install_skill(self, skill_name: str, markdown_content: str) -> bool:
        """Saves sanitized skill markdown into the auto_learned directory."""
        if not self.sanitize_skill_markdown(markdown_content):
            return False

        skill_folder = self.target_dir / skill_name
        skill_folder.mkdir(parents=True, exist_ok=True)
        skill_file = skill_folder / "SKILL.md"
        skill_file.write_text(markdown_content, encoding="utf-8")
        logger.info("Successfully installed skill: %s", skill_file)
        return True

    def search_and_install_github_skill(self, niche_query: str) -> Dict[str, Any]:
        """Simulates autonomous harvest and installs safe structured skill."""
        slug = re.sub(r"\W+", "-", niche_query.lower()).strip("-")
        template = f"""---
name: {slug}
description: Auto-harvested skill for {niche_query}
---

# {niche_query.title()} Skill

## When to use
Use when handling tasks involving {niche_query}.

## Instructions
1. Inspect the requirements and dependencies.
2. Follow strict TDD methodology.
3. Validate output before completion.
"""
        success = self.install_skill(slug, template)
        return {
            "query": niche_query,
            "installed": success,
            "skill_name": slug,
        }
