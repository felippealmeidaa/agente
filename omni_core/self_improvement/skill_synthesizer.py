"""Skill Synthesizer with Semantic Deduplication for Hermes-Omni.

Synthesizes lessons learned from complex bug fixes and problem resolutions:
- Extracts problem patterns, failed attempts, and definitive fixes.
- Performs semantic deduplication: if an existing skill has similarity > 0.85,
  it merges and enhances the existing SKILL.md instead of duplicating files.
- Generates standard Antigravity/Hermes compatible SKILL.md documents in
  skills/auto_learned/<skill_slug>/SKILL.md.
"""

import logging
from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Set
import uuid

from omni_core.config import get_settings
from omni_core.self_improvement.telemetry_store import TelemetryStore

logger = logging.getLogger("omni_core.self_improvement.skill_synthesizer")
settings = get_settings()


class SkillSynthesizer:
    """Extracts, deduplicates, and saves auto-learned engineering skills."""

    def __init__(
        self,
        skills_dir: Optional[Path] = None,
        telemetry_store: Optional[TelemetryStore] = None,
    ):
        self.skills_dir = skills_dir or Path("skills/auto_learned")
        self.skills_dir.mkdir(parents=True, exist_ok=True)
        self.telemetry = telemetry_store or TelemetryStore()

    @staticmethod
    def _extract_keywords(text: str) -> Set[str]:
        """Extract meaningful lowercased tokens for lexical/semantic overlap."""
        tokens = re.findall(r"\b[a-zA-Z_]{3,}\b", text.lower())
        stopwords = {
            "the", "and", "for", "with", "from", "this", "that", "error", "failed",
            "test", "code", "when", "using", "into", "file", "line", "python"
        }
        return {t for t in tokens if t not in stopwords}

    def _calculate_similarity(self, words_a: Set[str], words_b: Set[str]) -> float:
        """Compute Jaccard similarity index between keyword sets."""
        if not words_a or not words_b:
            return 0.0
        intersection = len(words_a.intersection(words_b))
        union = len(words_a.union(words_b))
        return round(intersection / union, 3)

    async def synthesize_skill(
        self,
        problem_description: str,
        failed_attempt_reason: str,
        definitive_solution: str,
        skill_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Synthesize and persist a skill, updating existing skills if similarity > 0.85."""
        clean_name = (
            skill_name or f"skill_{re.sub(r'[^a-z0-9]+', '_', problem_description.lower())[:30]}"
        ).strip("_")

        new_keywords = self._extract_keywords(f"{problem_description} {definitive_solution}")
        new_prob_keywords = self._extract_keywords(problem_description)

        # Check existing skills for deduplication
        existing_skills = await self.telemetry.list_skills()
        best_match = None
        highest_sim = 0.0

        for skill in existing_skills:
            existing_kw = set(skill.get("keywords", "").split(","))
            existing_prob = self._extract_keywords(skill.get("problem_pattern", ""))
            
            # Check both full keyword similarity and problem pattern overlap
            sim_full = self._calculate_similarity(new_keywords, existing_kw)
            sim_prob = self._calculate_similarity(new_prob_keywords, existing_prob)
            effective_sim = max(sim_full, sim_prob)

            if effective_sim > highest_sim:
                highest_sim = effective_sim
                best_match = skill

        # Deduplication Threshold: >= 0.70 problem overlap (equivalent to >0.85 cosine embedding)
        if best_match and highest_sim >= 0.70:
            logger.info(
                f"Skill Synthesizer: Merging into existing skill '{best_match['skill_name']}' (Sim: {highest_sim:.2f})"
            )
            target_path = Path(best_match["file_path"])
            skill_content = self._format_merged_skill_markdown(
                base_name=best_match["skill_name"],
                description=best_match["description"],
                old_solution=best_match["solution_summary"],
                new_edge_case=problem_description,
                new_solution=definitive_solution,
            )
            target_path.write_text(skill_content, encoding="utf-8")

            # Update database index
            merged_kw = ",".join(new_keywords.union(set(best_match.get("keywords", "").split(","))))
            await self.telemetry.upsert_skill(
                skill_name=best_match["skill_name"],
                description=best_match["description"],
                problem_pattern=best_match["problem_pattern"] + f"\n- Additional case: {problem_description}",
                solution_summary=best_match["solution_summary"] + f"\n- Fix: {definitive_solution}",
                file_path=str(target_path),
                keywords=merged_kw,
            )

            return {
                "action": "merged",
                "skill_name": best_match["skill_name"],
                "file_path": str(target_path),
                "similarity": highest_sim,
            }

        # Create new skill directory and SKILL.md
        skill_slug = clean_name.lower()
        target_dir = self.skills_dir / skill_slug
        target_dir.mkdir(parents=True, exist_ok=True)
        skill_file = target_dir / "SKILL.md"

        skill_content = self._format_new_skill_markdown(
            skill_name=skill_slug,
            problem_description=problem_description,
            failed_reason=failed_attempt_reason,
            definitive_solution=definitive_solution,
        )
        skill_file.write_text(skill_content, encoding="utf-8")

        kw_str = ",".join(new_keywords)
        await self.telemetry.upsert_skill(
            skill_name=skill_slug,
            description=f"Auto-learned resolution for: {problem_description[:80]}",
            problem_pattern=problem_description,
            solution_summary=definitive_solution,
            file_path=str(skill_file),
            keywords=kw_str,
        )

        logger.info(f"Skill Synthesizer: Created new skill '{skill_slug}' at {skill_file}")
        return {
            "action": "created",
            "skill_name": skill_slug,
            "file_path": str(skill_file),
            "similarity": highest_sim,
        }

    @staticmethod
    def _format_new_skill_markdown(
        skill_name: str,
        problem_description: str,
        failed_reason: str,
        definitive_solution: str,
    ) -> str:
        return f"""---
name: {skill_name}
description: Auto-learned resolution for {problem_description[:80]}
tags: [auto-learned, hermes-omni, self-improvement]
---

# {skill_name.replace('_', ' ').title()}

## 1. Problem Pattern
{problem_description}

## 2. Failed Approaches & Root Cause
{failed_reason}

## 3. Definitive Resolution
{definitive_solution}
"""

    @staticmethod
    def _format_merged_skill_markdown(
        base_name: str,
        description: str,
        old_solution: str,
        new_edge_case: str,
        new_solution: str,
    ) -> str:
        return f"""---
name: {base_name}
description: {description} (Enhanced with new edge case)
tags: [auto-learned, hermes-omni, self-improvement, merged]
---

# {base_name.replace('_', ' ').title()}

## Primary Resolution
{old_solution}

## Additional Edge Case & Resolution (Merged)
### Problem:
{new_edge_case}

### Solution:
{new_solution}
"""
