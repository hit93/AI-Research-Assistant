"""
LangGraph State Schema — Represents state across the research assistant graph.
"""

from typing import TypedDict, Optional
from src.models.schemas import QueryPlan, ResearchSource, SynthesisSection


class ResearchGraphState(TypedDict, total=False):
    """State schema for the Research StateGraph."""
    query: str
    max_papers: int
    max_web: int
    plan: Optional[QueryPlan]
    sources: list[ResearchSource]
    synthesis: list[SynthesisSection]
    status: str
    errors: list[str]
