"""
LangGraph Nodes — Discrete executable functions for each graph state transition.
"""

from src.graphs.state import ResearchGraphState
from src.chains.planner import plan_research
from src.chains.synthesizer import synthesize_sources
from src.chains.verifier import verify_synthesis
from src.chains.refiner import refine_synthesis
from src.tools.arxiv_tool import search_arxiv, papers_to_sources
from src.tools.web_search_tool import search_web, web_results_to_sources
from src.tools.text_cleaner import deduplicate_sources
from src.models.schemas import ResearchSource
from src.utils.logger import get_logger

logger = get_logger("graphs.nodes")


def plan_node(state: ResearchGraphState) -> dict:
    """Graph Node: Decompose user query into structured sub-queries."""
    query = state.get("query", "")
    logger.info(f"[Node: Planner] Processing query: '{query}'")
    plan = plan_research(query)
    return {
        "plan": plan,
        "status": "planned",
    }


def retrieve_node(state: ResearchGraphState) -> dict:
    """Graph Node: Execute multi-source retrieval across all decomposed sub-queries."""
    plan = state.get("plan")
    max_papers = state.get("max_papers", 3)
    max_web = state.get("max_web", 3)
    all_sources: list[ResearchSource] = []
    errors: list[str] = list(state.get("errors", []))

    if not plan or not plan.sub_queries:
        logger.warning("[Node: Retriever] No sub-queries found in plan.")
        return {"sources": [], "status": "retrieved", "errors": errors}

    logger.info(f"[Node: Retriever] Retrieving for {len(plan.sub_queries)} sub-queries")

    for i, sq in enumerate(plan.sub_queries, start=1):
        search_term = " ".join(sq.search_keywords) if sq.search_keywords else sq.question
        logger.debug(f"[Node: Retriever] Sub-query {i}: '{search_term}' (type={sq.source_type})")

        try:
            # ArXiv retrieval
            if sq.source_type in ("arxiv", "both"):
                papers = search_arxiv(search_term, max_results=max_papers)
                all_sources.extend(papers_to_sources(papers))

            # Web retrieval
            if sq.source_type in ("web", "both"):
                web_results = search_web(search_term, max_results=max_web)
                all_sources.extend(web_results_to_sources(web_results))

        except Exception as e:
            msg = f"Retrieval failed for sub-query {i} ('{search_term}'): {e}"
            logger.error(msg)
            errors.append(msg)

    deduped = deduplicate_sources(all_sources)
    logger.info(f"[Node: Retriever] Total unique sources retrieved: {len(deduped)}")

    return {
        "sources": deduped,
        "status": "retrieved",
        "errors": errors,
    }


def synthesize_node(state: ResearchGraphState) -> dict:
    """Graph Node: Synthesize all gathered sources into a multi-section report."""
    query = state.get("query", "")
    sources = state.get("sources", [])
    logger.info(f"[Node: Synthesizer] Synthesizing {len(sources)} sources for: '{query}'")

    synthesis = synthesize_sources(query, sources)
    return {
        "synthesis": synthesis,
        "status": "synthesized",
    }


def verify_node(state: ResearchGraphState) -> dict:
    """Graph Node: Verify the synthesized report against sources (LLM-as-judge)."""
    query = state.get("query", "")
    sources = state.get("sources", [])
    synthesis = state.get("synthesis", [])
    logger.info(
        f"[Node: Verifier] Verifying {len(synthesis)} sections "
        f"against {len(sources)} sources for: '{query}'"
    )

    verification = verify_synthesis(query, sources, synthesis)
    return {
        "verification": verification,
        "status": "verified",
    }


def improve_node(state: ResearchGraphState) -> dict:
    """Graph Node: Refine and elevate synthesis sections when verifier score < 8."""
    query = state.get("query", "")
    sources = state.get("sources", [])
    synthesis = state.get("synthesis", [])
    verification = state.get("verification")
    revision_count = state.get("revision_count", 0)

    if not verification:
        logger.warning("[Node: Improver] No verification verdict found to guide improvement.")
        return {"status": "improved"}

    logger.info(
        f"[Node: Improver] Refining report (Revision {revision_count + 1}) "
        f"for: '{query}' (Verifier Score: {verification.overall_score}/10)"
    )

    improved_synthesis = refine_synthesis(
        query=query,
        sources=sources,
        synthesis=synthesis,
        verification=verification,
    )

    return {
        "synthesis": improved_synthesis,
        "revision_count": revision_count + 1,
        "status": "improved",
    }

