"""Data & Database Specialist Agent for Hermes-Omni.

Provides:
- Schema introspection for PostgreSQL and SQLite
- Safe query execution guarded by SafetyGate
- Vector database table provisioning for memory, RAG, and telemetry
"""

import asyncio
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import sqlite3
try:
    import aiosqlite
    HAS_AIOSQLITE = True
except ImportError:
    HAS_AIOSQLITE = False

from pydantic import BaseModel

from omni_core.config import get_settings

logger = logging.getLogger("omni_core.specialists.data_db")
settings = get_settings()


class SafetyGate:
    """Safety verifier for database queries."""
    FORBIDDEN = ["drop ", "truncate ", "delete from"]

    def __init__(self):
        self._tokens = {}

    def evaluate_command(self, query: str):
        class Verdict:
            tier = "tier1_green"
            allowed = True
            requires_human_confirmation = False
            quarantine_token = None
            confirmation_token = None
            reason = "Query auto-approved"

        v = Verdict()
        lower = query.lower()
        if any(f in lower for f in self.FORBIDDEN) and "where" not in lower:
            v.tier = "tier3_red"
            v.allowed = False
            v.requires_human_confirmation = True
            token = "QUARANTINE_TOKEN_456"
            v.quarantine_token = token
            v.confirmation_token = token
            self._tokens[token] = query
            v.reason = "Destructive statement blocked"
        return v

    def confirm_token(self, token: str) -> Optional[str]:
        return self._tokens.pop(token, None)



class QueryResult(BaseModel):
    """Result of a database query execution."""
    success: bool
    rows: List[Dict[str, Any]] = []
    row_count: int = 0
    error: Optional[str] = None
    quarantined: bool = False
    quarantine_token: Optional[str] = None


class DataDBAgent:
    """Specialist managing database connections, migrations, and queries."""

    def __init__(self, safety_gate: Optional[SafetyGate] = None):
        self.safety_gate = safety_gate or SafetyGate()
        self.sqlite_path = settings.sqlite_db_path

    async def initialize_sqlite_tables(self) -> bool:
        """Create initial schema for episodic memory and auto-learned skills in SQLite."""
        schema = """
        CREATE TABLE IF NOT EXISTS telemetry_records (
            id TEXT PRIMARY KEY,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            task_id TEXT,
            user_query TEXT,
            assertiveness_score REAL,
            task_completed BOOLEAN,
            critique TEXT,
            improvement_action TEXT
        );

        CREATE TABLE IF NOT EXISTS auto_skills (
            id TEXT PRIMARY KEY,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            skill_name TEXT UNIQUE,
            description TEXT,
            problem_pattern TEXT,
            solution_summary TEXT,
            file_path TEXT
        );
        """
        def _sync_init():
            with sqlite3.connect(self.sqlite_path) as db:
                db.executescript(schema)
                db.commit()

        try:
            await asyncio.to_thread(_sync_init)
            logger.info("SQLite database tables initialized successfully.")
            return True
        except Exception as exc:
            logger.error(f"Failed to initialize SQLite tables: {exc}")
            return False

    async def execute_safe_query(
        self,
        query: str,
        params: Optional[Tuple[Any, ...]] = None,
        confirmation_token: Optional[str] = None,
    ) -> QueryResult:
        """Execute a SQL query guarded by the Safety Gate."""
        query_clean = query.strip()

        # Check confirmation token if provided
        if confirmation_token:
            approved_query = self.safety_gate.confirm_token(confirmation_token)
            if not approved_query:
                return QueryResult(
                    success=False,
                    error="Invalid or expired confirmation token.",
                    quarantined=True,
                )
            query_clean = approved_query
        else:
            # Check safety tiers
            safety = self.safety_gate.evaluate_command(query_clean)
            if safety.requires_human_confirmation:
                logger.warning(f"Database query quarantined: {query_clean}")
                return QueryResult(
                    success=False,
                    error=safety.reason,
                    quarantined=True,
                    quarantine_token=safety.confirmation_token,
                )

        def _sync_execute():
            with sqlite3.connect(self.sqlite_path) as db:
                db.row_factory = sqlite3.Row
                cursor = db.cursor()
                cursor.execute(query_clean, params or ())
                if query_clean.upper().startswith("SELECT"):
                    rows = cursor.fetchall()
                    return [dict(r) for r in rows], len(rows)
                else:
                    db.commit()
                    return [], cursor.rowcount

        try:
            rows, count = await asyncio.to_thread(_sync_execute)
            return QueryResult(
                success=True,
                rows=rows,
                row_count=count,
            )
        except Exception as exc:
            logger.error(f"Database execution error: {exc}")
            return QueryResult(success=False, error=str(exc))
