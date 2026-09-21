"""
LangGraph Nodes — Discrete executable functions for each graph state transition.
"""

from src.graphs.state import ResearchGraphState
from src.chains.planner import plan_research
from src.chains.synthesizer import SYNTHESIS_FALLBACK_HEADING, synthesize_sources
from src.chains.verifier import verify_synthesis
from src.chains.refiner import refine_synthesis
from src.tools.arxiv_tool import search_arxiv, papers_to_sources
from src.tools.web_search_tool import search_web, web_results_to_sources
from src.tools.text_cleaner import deduplicate_sources, filter_and_rank_sources
from src.tools.hybrid_rag import HybridRAG
from src.models.schemas import ResearchSource
from src.utils.logger import get_logger

logger = get_logger("graphs.nodes")


def plan_node(state: ResearchGraphState) -> dict:
    """Graph Node: Decompose user query into structured sub-queries."""
    query = state.get("query", "")
    planner_model = state.get("planner_model")
    logger.info(f"[Node: Planner] Processing query: '{query}' (model: {planner_model or 'default'})")
    plan = plan_research(query, model=planner_model)
    errors = list(state.get("errors", []))
    if plan.reasoning.startswith("Fallback plan"):
        errors.append(plan.reasoning)
    return {
        "plan": plan,
        "status": "planned",
        "errors": errors,
    }


def retrieve_node(state: ResearchGraphState) -> dict:
    """Graph Node: Execute multi-source retrieval across all decomposed sub-queries and build Hybrid RAG index."""
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
    logger.info(f"[Node: Retriever] Total unique sources retrieved before filtering: {len(deduped)}")

    # Filter out low-authority/sponsored items and retain top authoritative domain sources (top 12)
    filtered_sources = filter_and_rank_sources(deduped, query=state.get("query", ""), top_k=12)
    logger.info(f"[Node: Retriever] Retained {len(filtered_sources)} authoritative sources after domain relevance filtering.")

    # Build Hybrid RAG Index (BM25 + Vector Cosine Similarity) over filtered authoritative sources
    hybrid_rag = HybridRAG(filtered_sources) if filtered_sources else None
    if hybrid_rag and hybrid_rag.chunks:
        logger.info(f"[Node: Retriever] Hybrid RAG index built with {len(hybrid_rag.chunks)} chunks.")

    return {
        "sources": filtered_sources,
        "hybrid_rag": hybrid_rag,
        "status": "retrieved",
        "errors": errors,
    }


def synthesize_node(state: ResearchGraphState) -> dict:
    """Graph Node: Synthesize all gathered sources into a multi-section report using Hybrid RAG."""
    query = state.get("query", "")
    sources = state.get("sources", [])
    hybrid_rag = state.get("hybrid_rag")
    synthesizer_model = state.get("synthesizer_model")
    logger.info(f"[Node: Synthesizer] Synthesizing {len(sources)} sources for: '{query}' (model: {synthesizer_model or 'default'})")

    synthesis = synthesize_sources(query, sources, hybrid_rag=hybrid_rag, model=synthesizer_model)
    errors = list(state.get("errors", []))
    if any(section.heading == SYNTHESIS_FALLBACK_HEADING for section in synthesis):
        errors.append("Synthesis LLM call failed; raw source excerpts returned.")
    return {
        "synthesis": synthesis,
        "status": "synthesized",
        "errors": errors,
    }


def verify_node(state: ResearchGraphState) -> dict:
    """Graph Node: Verify the synthesized report against sources (LLM-as-judge with Hybrid RAG audit)."""
    query = state.get("query", "")
    sources = state.get("sources", [])
    synthesis = state.get("synthesis", [])
    hybrid_rag = state.get("hybrid_rag")
    verifier_model = state.get("verifier_model")
    logger.info(
        f"[Node: Verifier] Verifying {len(synthesis)} sections "
        f"against {len(sources)} sources for: '{query}' (model: {verifier_model or 'default'})"
    )

    verification = verify_synthesis(query, sources, synthesis, model=verifier_model, hybrid_rag=hybrid_rag)
    errors = list(state.get("errors", []))
    if verification and not verification.judge_ran:
        errors.append(verification.summary or "Verification judge did not complete.")
    return {
        "verification": verification,
        "status": "verified",
        "errors": errors,
    }


def improve_node(state: ResearchGraphState) -> dict:
    """Graph Node: Refine and elevate synthesis sections using targeted Hybrid RAG evidence when score < 8."""
    query = state.get("query", "")
    sources = state.get("sources", [])
    synthesis = state.get("synthesis", [])
    verification = state.get("verification")
    hybrid_rag = state.get("hybrid_rag")
    improver_model = state.get("improver_model") or state.get("synthesizer_model")
    revision_count = state.get("revision_count", 0)

    if not verification:
        logger.warning("[Node: Improver] No verification verdict found to guide improvement.")
        return {"status": "improved"}

    logger.info(
        f"[Node: Improver] Refining report (Revision {revision_count + 1}) "
        f"for: '{query}' (Verifier Score: {verification.overall_score}/10, model: {improver_model or 'default'})"
    )

    improved_synthesis = refine_synthesis(
        query=query,
        sources=sources,
        synthesis=synthesis,
        verification=verification,
        hybrid_rag=hybrid_rag,
        model=improver_model,
    )

    return {
        "synthesis": improved_synthesis,
        "revision_count": revision_count + 1,
        "status": "improved",
    }

