"""Telemetry & Episodic Memory Store for Hermes-Omni.

Persists assertiveness scores, judge evaluations, reflexion trajectories,
and synthesized skills into local SQLite or PostgreSQL.
"""

import asyncio
import json
import logging
from pathlib import Path
import sqlite3
import time
from typing import Any, Dict, List, Optional
import uuid

from omni_core.config import get_settings
from omni_core.self_improvement.evaluator_judge import AssertivenessEvaluation

logger = logging.getLogger("omni_core.self_improvement.telemetry_store")
settings = get_settings()


class TelemetryStore:
    """Manages telemetry events, quality audits, and historical skill records."""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or settings.sqlite_db_path
        self._init_db()

    def _init_db(self):
        """Ensure telemetry tables exist."""
        with sqlite3.connect(self.db_path) as db:
            db.execute("""
            CREATE TABLE IF NOT EXISTS telemetry_evaluations (
                id TEXT PRIMARY KEY,
                created_at REAL,
                task_id TEXT,
                user_query TEXT,
                task_completed INTEGER,
                completeness_score REAL,
                accuracy_score REAL,
                hallucination_detected INTEGER,
                final_assertiveness_score REAL,
                critique TEXT,
                improvement_action TEXT
            )
            """)
            db.execute("""
            CREATE TABLE IF NOT EXISTS skill_index (
                id TEXT PRIMARY KEY,
                created_at REAL,
                skill_name TEXT UNIQUE,
                description TEXT,
                problem_pattern TEXT,
                solution_summary TEXT,
                file_path TEXT,
                keywords TEXT
            )
            """)
            db.commit()

    async def record_evaluation(
        self,
        task_id: str,
        user_query: str,
        evaluation: AssertivenessEvaluation,
    ) -> str:
        """Persist a Judge assertiveness evaluation record."""
        rec_id = f"eval_{uuid.uuid4().hex[:10]}"
        now = time.time()

        def _insert():
            with sqlite3.connect(self.db_path) as db:
                db.execute(
                    """
                    INSERT INTO telemetry_evaluations (
                        id, created_at, task_id, user_query, task_completed,
                        completeness_score, accuracy_score, hallucination_detected,
                        final_assertiveness_score, critique, improvement_action
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        rec_id, now, task_id, user_query,
                        1 if evaluation.task_completed else 0,
                        evaluation.completeness_score,
                        evaluation.code_or_execution_accuracy,
                        1 if evaluation.hallucination_detected else 0,
                        evaluation.final_assertiveness_score,
                        evaluation.critique,
                        evaluation.improvement_action or "",
                    ),
                )
                db.commit()

        await asyncio.to_thread(_insert)
        logger.info(f"Telemetry record persisted: {rec_id} (Score: {evaluation.final_assertiveness_score:.2f})")
        return rec_id

    async def get_average_score(self, since_hours: float = 24.0) -> float:
        """Calculate average assertiveness score for recent tasks."""
        cutoff = time.time() - (since_hours * 3600)

        def _query():
            with sqlite3.connect(self.db_path) as db:
                cursor = db.execute(
                    "SELECT AVG(final_assertiveness_score) FROM telemetry_evaluations WHERE created_at >= ?",
                    (cutoff,),
                )
                row = cursor.fetchone()
                return float(row[0]) if row and row[0] is not None else 1.0

        return await asyncio.to_thread(_query)

    async def list_skills(self) -> List[Dict[str, Any]]:
        """Retrieve all auto-learned skills from the index."""
        def _query():
            with sqlite3.connect(self.db_path) as db:
                db.row_factory = sqlite3.Row
                cursor = db.execute("SELECT * FROM skill_index ORDER BY created_at DESC")
                return [dict(r) for r in cursor.fetchall()]

        return await asyncio.to_thread(_query)

    async def upsert_skill(
        self,
        skill_name: str,
        description: str,
        problem_pattern: str,
        solution_summary: str,
        file_path: str,
        keywords: str,
    ) -> str:
        """Insert or update a skill in the index."""
        skill_id = f"skill_{uuid.uuid4().hex[:8]}"
        now = time.time()

        def _upsert():
            with sqlite3.connect(self.db_path) as db:
                db.execute(
                    """
                    INSERT INTO skill_index (
                        id, created_at, skill_name, description,
                        problem_pattern, solution_summary, file_path, keywords
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(skill_name) DO UPDATE SET
                        description=excluded.description,
                        problem_pattern=excluded.problem_pattern,
                        solution_summary=excluded.solution_summary,
                        file_path=excluded.file_path,
                        keywords=excluded.keywords
                    """,
                    (
                        skill_id, now, skill_name, description,
                        problem_pattern, solution_summary, file_path, keywords
                    ),
                )
                db.commit()

        await asyncio.to_thread(_upsert)
        return skill_id
