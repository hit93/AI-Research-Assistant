"""
Long-Term Memory (LTM) — Persistent research archive with pgvector and SQLite fallback.
"""

import sqlite3
import json
import time
from typing import Any
from pathlib import Path
from config.settings import settings
from src.models.schemas import ResearchResult
from src.utils.logger import get_logger

logger = get_logger("memory.ltm")


class LongTermMemory:
    """Persistent storage for completed research reports and evaluation metrics."""

    def __init__(self, db_path: Path | None = None):
        self.db_path = db_path or (settings.CACHE_DIR / "ltm.db")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_sqlite()

    def _init_sqlite(self) -> None:
        """Initialize local SQLite database table."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS research_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    topic TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    score INTEGER,
                    approved BOOLEAN,
                    sources_count INTEGER,
                    synthesis_summary TEXT,
                    raw_data TEXT
                )
                """
            )
            conn.commit()

    def save_research(self, topic: str, result: ResearchResult) -> int:
        """Archive a completed research result."""
        score = result.verification.overall_score if result.verification else None
        approved = result.verification.is_approved if result.verification else True
        sources_count = len(result.sources)
        if isinstance(result.synthesis, list) and result.synthesis:
            synthesis_summary = result.synthesis[0].content[:500]
        elif hasattr(result.synthesis, "executive_summary"):
            synthesis_summary = getattr(result.synthesis, "executive_summary", "")
        else:
            synthesis_summary = ""
        raw_json = result.model_dump_json()


        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO research_history 
                (topic, created_at, score, approved, sources_count, synthesis_summary, raw_data)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (topic, time.time(), score, approved, sources_count, synthesis_summary, raw_json),
            )
            conn.commit()
            record_id = cursor.lastrowid
            logger.info(f"Archived research run #{record_id} for topic: '{topic}' in LTM.")
            return record_id

    def get_history(self, limit: int = 10) -> list[dict[str, Any]]:
        """Retrieve recent research records."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, topic, created_at, score, approved, sources_count, synthesis_summary "
                "FROM research_history ORDER BY created_at DESC LIMIT ?",
                (limit,),
            )
            return [dict(row) for row in cursor.fetchall()]

    def search_past_research(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        """Keyword search across past research topics and summaries."""
        term = f"%{query.lower()}%"
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, topic, created_at, score, synthesis_summary FROM research_history "
                "WHERE LOWER(topic) LIKE ? OR LOWER(synthesis_summary) LIKE ? "
                "ORDER BY created_at DESC LIMIT ?",
                (term, term, limit),
            )
            return [dict(row) for row in cursor.fetchall()]


_ltm_instance: LongTermMemory | None = None


def get_ltm() -> LongTermMemory:
    """Return shared LongTermMemory singleton."""
    global _ltm_instance
    if _ltm_instance is None:
        _ltm_instance = LongTermMemory()
    return _ltm_instance
