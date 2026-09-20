"""
LangGraph State Schema — Represents state across the research assistant graph.
"""

from typing import TypedDict, Optional, Any
from src.models.schemas import QueryPlan, ResearchSource, SynthesisSection, VerificationResult


class ResearchGraphState(TypedDict, total=False):
    """State schema for the Research StateGraph."""
    query: str
    max_papers: int
    max_web: int
    plan: Optional[QueryPlan]
    sources: list[ResearchSource]
    synthesis: list[SynthesisSection]
    verification: Optional[VerificationResult]
    revision_count: int
    max_revisions: int
    session_id: Optional[str]
    is_cache_hit: Optional[bool]
    cache_similarity: Optional[float]
    hybrid_rag: Optional[Any]
    status: str
    errors: list[str]


