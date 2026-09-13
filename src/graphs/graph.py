"""
LangGraph Workflow — StateGraph assembly, compilation, and execution.
"""

import time
from typing import Callable, Optional
from langgraph.graph import StateGraph, START, END

from src.graphs.state import ResearchGraphState
from src.graphs.nodes import plan_node, retrieve_node, synthesize_node
from src.models.schemas import ResearchResult, QueryPlan
from src.utils.logger import get_logger

logger = get_logger("graphs.workflow")


def build_research_graph() -> StateGraph:
    """Assemble and configure the LangGraph research state machine."""
    workflow = StateGraph(ResearchGraphState)

    # Register graph nodes
    workflow.add_node("planner", plan_node)
    workflow.add_node("retriever", retrieve_node)
    workflow.add_node("synthesizer", synthesize_node)

    # Establish linear state graph edges
    workflow.add_edge(START, "planner")
    workflow.add_edge("planner", "retriever")
    workflow.add_edge("retriever", "synthesizer")
    workflow.add_edge("synthesizer", END)

    return workflow


# Compiled LangGraph instance ready for invoke / stream
research_graph = build_research_graph().compile()


def run_research(
    query: str,
    max_papers: int = 3,
    max_web: int = 3,
    on_progress: Optional[Callable[[str, str], None]] = None,
) -> ResearchResult:
    """
    Execute end-to-end research workflow via the compiled LangGraph StateGraph.

    Uses LangGraph streaming to emit live progress updates during node transitions.

    Args:
        query: Research topic or question.
        max_papers: Maximum ArXiv papers per sub-query.
        max_web: Maximum web search results per sub-query.
        on_progress: Optional callback(status, detail) for UI/CLI updates.

    Returns:
        A complete ResearchResult with plan, sources, synthesis, and elapsed time.
    """
    start_time = time.time()

    def notify(status: str, detail: str = ""):
        logger.info(f"[{status}] {detail}")
        if on_progress:
            on_progress(status, detail)

    notify("planning", f"Decomposing query: '{query}'")

    initial_state: ResearchGraphState = {
        "query": query,
        "max_papers": max_papers,
        "max_web": max_web,
        "plan": None,
        "sources": [],
        "synthesis": [],
        "status": "initialized",
        "errors": [],
    }

    final_state: ResearchGraphState = dict(initial_state)

    # Stream through LangGraph nodes
    for event in research_graph.stream(initial_state):
        for node_name, state_update in event.items():
            final_state.update(state_update)

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

    duration = round(time.time() - start_time, 2)
    notify("complete", f"Research finished in {duration}s")

    return ResearchResult(
        query=query,
        plan=final_state.get("plan") or QueryPlan(original_query=query),
        sources=final_state.get("sources", []),
        synthesis=final_state.get("synthesis", []),
        duration_seconds=duration,
    )
