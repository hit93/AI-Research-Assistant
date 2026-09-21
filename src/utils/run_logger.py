"""
Stage-by-stage Run Logger — Logs complete execution traces to timestamped files for debugging.
Records landscape search, sub-queries, retrieval per sub-query, full text extraction,
claim extraction, claim verification results, and revision loops.
"""

import json
import time
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict
from config.settings import settings
from src.utils.logger import get_logger

logger = get_logger("utils.run_logger")


def _slugify(text: str, max_length: int = 30) -> str:
    clean = re.sub(r"[^\w\s-]", "", text.lower()).strip()
    clean = re.sub(r"[\s_-]+", "-", clean)
    return clean[:max_length] if clean else "run"


class RunLogger:
    """Records audit trail for research workflows."""

    def __init__(self, query: str):
        self.query = query
        self.start_time = time.time()
        self.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.slug = _slugify(query)
        self.log_dir = Path(settings.RUNS_LOG_DIR)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.file_path = self.log_dir / f"run_{self.timestamp}_{self.slug}.json"
        self.data: Dict[str, Any] = {
            "query": query,
            "timestamp": self.timestamp,
            "stages": {},
            "metrics": {},
        }

    def log_stage(self, stage_name: str, payload: Any) -> None:
        """Record stage execution details."""
        try:
            # Convert Pydantic models or dicts to JSON-serializable structures
            if hasattr(payload, "model_dump"):
                clean_payload = payload.model_dump()
            elif isinstance(payload, list):
                clean_payload = [
                    item.model_dump() if hasattr(item, "model_dump") else item
                    for item in payload
                ]
            else:
                clean_payload = payload

            self.data["stages"][stage_name] = {
                "recorded_at": datetime.now().isoformat(),
                "duration_from_start": round(time.time() - self.start_time, 2),
                "data": clean_payload,
            }
            self.save()
        except Exception as e:
            logger.warning(f"Failed to record run log stage '{stage_name}': {e}")

    def log_metric(self, key: str, value: Any) -> None:
        """Record high-level metric."""
        self.data["metrics"][key] = value

    def save(self) -> None:
        """Write current log state to file."""
        try:
            self.data["total_duration_seconds"] = round(time.time() - self.start_time, 2)
            with open(self.file_path, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=2, default=str)
        except Exception as e:
            logger.warning(f"Could not persist run log to {self.file_path}: {e}")
