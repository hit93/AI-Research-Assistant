"""
Semantic Caching — Fast similarity-based cache to bypass redundant research pipelines.
"""

import json
import re
from difflib import SequenceMatcher
from pathlib import Path
from config.settings import settings
from src.models.schemas import ResearchResult
from src.utils.logger import get_logger

logger = get_logger("memory.cache")


def _tokenize(text: str) -> set[str]:
    """Extract normalized lowercase alphanumeric word tokens."""
    return set(re.findall(r"\w+", text.lower()))


def compute_query_similarity(q1: str, q2: str) -> float:
    """
    Compute semantic similarity between two query strings.
    Blends token Jaccard & overlap coefficient (70%) with character sequence matching (30%).
    """
    s1, s2 = q1.strip().lower(), q2.strip().lower()
    if s1 == s2:
        return 1.0

    tokens1, tokens2 = _tokenize(s1), _tokenize(s2)
    if not tokens1 or not tokens2:
        return 0.0

    # Token overlap metrics
    intersection = len(tokens1 & tokens2)
    jaccard = intersection / len(tokens1 | tokens2)
    overlap = intersection / min(len(tokens1), len(tokens2))
    token_score = 0.5 * jaccard + 0.5 * overlap

    # Sequence matcher for phrase similarity
    seq_ratio = SequenceMatcher(None, s1, s2).ratio()

    # Blended score
    return round(0.7 * token_score + 0.3 * seq_ratio, 4)



class SemanticCache:
    """Disk-backed semantic cache for research query results."""

    def __init__(self, cache_file: Path | None = None):
        self.cache_file = cache_file or (settings.CACHE_DIR / "semantic_cache.json")
        self.cache_file.parent.mkdir(parents=True, exist_ok=True)
        self.threshold = settings.CACHE_SIMILARITY_THRESHOLD
        self._entries: list[dict] = self._load()

    def _load(self) -> list[dict]:
        if self.cache_file.exists():
            try:
                with open(self.cache_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Failed to read semantic cache: {e}")
        return []

    def _save(self) -> None:
        try:
            with open(self.cache_file, "w", encoding="utf-8") as f:
                json.dump(self._entries, f, indent=2)
        except Exception as e:
            logger.warning(f"Failed to write semantic cache: {e}")

    def get(self, query: str) -> tuple[ResearchResult | None, float]:
        """
        Check for a cache hit with similarity >= threshold.
        Returns: (cached_result, similarity_score)
        """
        if not settings.SEMANTIC_CACHE_ENABLED or not self._entries:
            return None, 0.0

        best_score = 0.0
        best_entry = None

        for entry in self._entries:
            sim = compute_query_similarity(query, entry["query"])
            if sim > best_score:
                best_score = sim
                best_entry = entry

        if best_score >= self.threshold and best_entry:
            logger.info(
                f"Semantic Cache HIT for '{query}' (matched '{best_entry['query']}' with sim={best_score:.2f})"
            )
            result = ResearchResult.model_validate(best_entry["result"])
            return result, best_score

        return None, best_score

    def set(self, query: str, result: ResearchResult) -> None:
        """Store a completed research result in the cache."""
        if not settings.SEMANTIC_CACHE_ENABLED:
            return

        # Avoid duplicate identical query records
        self._entries = [e for e in self._entries if e["query"].lower() != query.lower()]
        self._entries.append({
            "query": query,
            "result": result.model_dump(),
        })
        self._save()
        logger.debug(f"Saved query '{query}' to semantic cache (total entries: {len(self._entries)})")

    def clear(self) -> None:
        """Clear the semantic cache."""
        self._entries = []
        self._save()


_cache_instance: SemanticCache | None = None


def get_semantic_cache() -> SemanticCache:
    """Return shared SemanticCache singleton."""
    global _cache_instance
    if _cache_instance is None:
        _cache_instance = SemanticCache()
    return _cache_instance
