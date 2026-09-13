"""
Orchestrator — Wires Planner → Retrieval Tools → Synthesizer into one call.

This is the main entry point for running a complete research cycle.
It chains the agents together: plan the query, retrieve sources for each
sub-question, deduplicate, synthesize, and package the final result.
"""

import time
from typing import Callable

from src.agents.planner import plan_research
from src.agents.synthesizer import synthesize_sources
from src.tools.arxiv_tool import search_arxiv, papers_to_sources
from src.tools.web_search_tool import search_web, web_results_to_sources
from src.tools.text_cleaner import deduplicate_sources
from src.models.schemas import (
    ResearchState,
    ResearchResult,
    QueryPlan,
    ResearchSource,
)
from src.utils.logger import get_logger

logger = get_logger("orchestrator")


def _retrieve_for_subquery(
    question: str,
    keywords: list[str],
    source_type: str,
    max_papers: int = 3,
    max_web: int = 3,
) -> list[ResearchSource]:
    """
    Run retrieval tools for a single sub-query.

    Uses the keywords for search. Falls back to the question text if
    no keywords were provided.
    """
    sources: list[ResearchSource] = []
    search_term = " ".join(keywords) if keywords else question

    # ArXiv retrieval
    if source_type in ("arxiv", "both"):
        papers = search_arxiv(search_term, max_results=max_papers)
        sources.extend(papers_to_sources(papers))

    # Web retrieval
    if source_type in ("web", "both"):
        web_results = search_web(search_term, max_results=max_web)
        sources.extend(web_results_to_sources(web_results))

    return sources


def run_research(
    query: str,
    max_papers: int = 3,
    max_web: int = 3,
    on_progress: Callable[[str, str], None] | None = None,
) -> ResearchResult:
    """
    Execute a complete research cycle: Plan → Retrieve → Synthesize.

    Args:
        query:       The user's research topic or question.
        max_papers:  Max ArXiv papers to retrieve per sub-query.
        max_web:     Max web results to retrieve per sub-query.
        on_progress: Optional callback(status, detail) for real-time UI updates.

    Returns:
        A ResearchResult with the plan, all sources, and synthesized sections.
    """
    start_time = time.time()

    def progress(status: str, detail: str = ""):
        """Log and optionally callback progress updates."""
        logger.info(f"[{status}] {detail}")
        if on_progress:
            on_progress(status, detail)

    # ── Step 1: Plan ──────────────────────────────────────────
    progress("planning", f"Decomposing query: '{query}'")
    state = ResearchState(query=query, status="planning")

    try:
        state.plan = plan_research(query)
        progress(
            "planned",
            f"{len(state.plan.sub_queries)} sub-queries created"
        )
    except Exception as e:
        state.errors.append(f"Planning failed: {e}")
        logger.error(f"Planning failed: {e}")
        # Fallback: search the raw query directly
        from src.models.schemas import SubQuery
        state.plan = QueryPlan(
            original_query=query,
            sub_queries=[SubQuery(question=query, search_keywords=[query], source_type="both")],
            reasoning="Direct search (planner failed)",
        )

    # ── Step 2: Retrieve ──────────────────────────────────────
    state.status = "retrieving"
    all_sources: list[ResearchSource] = []

    for i, sq in enumerate(state.plan.sub_queries, start=1):
        progress(
            "retrieving",
            f"Sub-query {i}/{len(state.plan.sub_queries)}: {sq.question[:60]}..."
        )
        try:
            sources = _retrieve_for_subquery(
                question=sq.question,
                keywords=sq.search_keywords,
                source_type=sq.source_type,
                max_papers=max_papers,
                max_web=max_web,
            )
            all_sources.extend(sources)
            progress("retrieved", f"Got {len(sources)} sources for sub-query {i}")
        except Exception as e:
            state.errors.append(f"Retrieval failed for sub-query {i}: {e}")
            logger.error(f"Retrieval error for '{sq.question}': {e}")

    # Deduplicate
    state.sources = deduplicate_sources(all_sources)
    progress(
        "deduplicated",
        f"{len(all_sources)} raw → {len(state.sources)} unique sources"
    )

    # ── Step 3: Synthesize ────────────────────────────────────
    state.status = "synthesizing"
    progress("synthesizing", f"Analyzing {len(state.sources)} sources with LLM...")

    try:
        state.synthesis = synthesize_sources(query, state.sources)
        progress("synthesized", f"{len(state.synthesis)} sections generated")
    except Exception as e:
        state.errors.append(f"Synthesis failed: {e}")
        logger.error(f"Synthesis failed: {e}")

    # ── Package result ────────────────────────────────────────
    state.status = "complete"
    duration = time.time() - start_time

    result = ResearchResult(
        query=query,
        plan=state.plan,
        sources=state.sources,
        synthesis=state.synthesis,
        duration_seconds=round(duration, 2),
    )

    progress(
        "complete",
        f"Research finished in {result.duration_seconds}s — "
        f"{len(result.sources)} sources, {len(result.synthesis)} sections"
    )

    if state.errors:
        logger.warning(f"Completed with {len(state.errors)} error(s): {state.errors}")

    return result
