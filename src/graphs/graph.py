"""
LangGraph Workflow — StateGraph assembly, compilation, and execution.
"""

import time
from typing import Callable, Optional
from langgraph.graph import StateGraph, START, END

from src.graphs.state import ResearchGraphState
from src.graphs.nodes import plan_node, retrieve_node, synthesize_node, verify_node, improve_node
from src.models.schemas import ResearchResult, QueryPlan
from src.memory.semantic_cache import get_semantic_cache
from src.memory.stm import get_stm
from src.memory.ltm import get_ltm
from src.utils.logger import get_logger

logger = get_logger("graphs.workflow")


def route_after_verifier(state: ResearchGraphState) -> str:
    """Route to improver if score < 8 and revision limit not reached; else finish."""
    verification = state.get("verification")
    revision_count = state.get("revision_count", 0)
    max_revisions = state.get("max_revisions", 2)

    if verification and verification.overall_score < 8 and revision_count < max_revisions:
        logger.info(
            f"[Router] Score {verification.overall_score}/10 < 8. "
            f"Routing to improver (Revision {revision_count + 1}/{max_revisions})."
        )
        return "improver"

    return END


def build_research_graph() -> StateGraph:
    """Assemble and configure the LangGraph research state machine."""
    workflow = StateGraph(ResearchGraphState)

    # Register graph nodes
    workflow.add_node("planner", plan_node)
    workflow.add_node("retriever", retrieve_node)
    workflow.add_node("synthesizer", synthesize_node)
    workflow.add_node("verifier", verify_node)
    workflow.add_node("improver", improve_node)

    # Establish graph edges
    workflow.add_edge(START, "planner")
    workflow.add_edge("planner", "retriever")
    workflow.add_edge("retriever", "synthesizer")
    workflow.add_edge("synthesizer", "verifier")

    # Conditional routing after verification: refine if score < 8
    workflow.add_conditional_edges(
        "verifier",
        route_after_verifier,
        {
            "improver": "improver",
            END: END,
        },
    )
    workflow.add_edge("improver", "verifier")

    return workflow


# Compiled LangGraph instance ready for invoke / stream
research_graph = build_research_graph().compile()


def run_research(
    query: str,
    max_papers: int = 3,
    max_web: int = 3,
    max_revisions: int = 2,
    on_progress: Optional[Callable[[str, str], None]] = None,
    use_cache: bool = True,
) -> ResearchResult:
    """
    Execute end-to-end research workflow via the compiled LangGraph StateGraph.

    Checks SemanticCache first for instant cache hits (unless use_cache=False).
    Tracks session state in Redis STM, and upon completion archives the run in
    pgvector/SQLite LTM and SemanticCache.
    """
    start_time = time.time()

    def notify(status: str, detail: str = ""):
        logger.info(f"[{status}] {detail}")
        if on_progress:
            on_progress(status, detail)

    # 1. Semantic Cache check (Instant short-circuit)
    if use_cache:
        cached_result, similarity = get_semantic_cache().get(query)
        if cached_result:
            notify("cache_hit", f"⚡ Retrieved from Semantic Cache ({similarity:.0%} similarity)")
            cached_result.is_cache_hit = True
            return cached_result


    notify("planning", f"Decomposing query: '{query}'")

    session_id = f"session_{int(time.time() * 1000)}"
    stm = get_stm()
    stm.set_session(session_id, {"query": query, "status": "planning"})

    initial_state: ResearchGraphState = {
        "query": query,
        "max_papers": max_papers,
        "max_web": max_web,
        "max_revisions": max_revisions,
        "revision_count": 0,
        "session_id": session_id,
        "is_cache_hit": False,
        "plan": None,
        "sources": [],
        "synthesis": [],
        "verification": None,
        "status": "initialized",
        "errors": [],
    }

    final_state: ResearchGraphState = dict(initial_state)

    # Stream through LangGraph nodes
    for event in research_graph.stream(initial_state):
        for node_name, state_update in event.items():
            final_state.update(state_update)
            stm.update_session(session_id, "current_node", node_name)

            if node_name == "planner":
                plan = final_state.get("plan")
                count = len(plan.sub_queries) if plan else 0
                notify("planned", f"{count} sub-queries created")
                notify("retrieving", f"Retrieving sources across {count} sub-queries...")

            elif node_name == "retriever":
                sources = final_state.get("sources", [])
                notify("retrieved", f"Retrieved {len(sources)} sources")
                notify("deduplicated", f"Unified into {len(sources)} unique sources")
                notify("synthesizing", "Synthesizing research report via LangChain...")

            elif node_name == "synthesizer":
                sections = final_state.get("synthesis", [])
                notify("synthesized", f"{len(sections)} sections generated")
                notify("verifying", "Verifying report against sources (LLM-as-judge)...")

            elif node_name == "verifier":
                verification = final_state.get("verification")
                rev_count = final_state.get("revision_count", 0)
                if verification:
                    iteration_label = f" (Iteration {rev_count})" if rev_count > 0 else ""
                    notify(
                        "verified",
                        f"Score: {verification.overall_score}/10{iteration_label} — "
                        f"{'✅ Approved' if verification.is_approved else '⚠️ Flagged'} "
                        f"({len(verification.issues)} issues)"
                    )
                    if verification.overall_score < 8 and rev_count < max_revisions:
                        notify(
                            "improving",
                            f"Score {verification.overall_score}/10 < 8 — refining report based on reviewer feedback (Revision {rev_count + 1}/{max_revisions})..."
                        )

            elif node_name == "improver":
                rev_count = final_state.get("revision_count", 1)
                notify("improved", f"Report refined (Revision {rev_count}). Re-verifying...")

    duration = round(time.time() - start_time, 2)
    notify("complete", f"Research finished in {duration}s")

    result = ResearchResult(
        query=query,
        plan=final_state.get("plan") or QueryPlan(original_query=query),
        sources=final_state.get("sources", []),
        synthesis=final_state.get("synthesis", []),
        verification=final_state.get("verification"),
        duration_seconds=duration,
        is_cache_hit=False,
    )

    # 2. Persist to Semantic Cache and LTM Archive
    get_semantic_cache().set(query, result)
    get_ltm().save_research(query, result)
    stm.clear_session(session_id)

    return result


