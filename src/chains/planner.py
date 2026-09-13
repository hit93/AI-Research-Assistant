"""
Planner Chain — LCEL chain for decomposing a research query into targeted sub-queries.
"""

from langchain_core.runnables import Runnable
from src.prompts.planner import planner_prompt
from src.chains.llm import get_chat_llm
from src.models.schemas import SubQuery, QueryPlan
from src.utils.logger import get_logger

logger = get_logger("chains.planner")


def get_planner_chain(temperature: float = 0.3) -> Runnable:
    """Return an LCEL chain for structured query planning."""
    llm = get_chat_llm(temperature=temperature)
    structured_llm = llm.with_structured_output(QueryPlan)
    return planner_prompt | structured_llm


def plan_research(query: str) -> QueryPlan:
    """
    Decompose a user query into a structured research plan via LangChain LCEL.

    Args:
        query: The user's broad research topic or question.

    Returns:
        A QueryPlan containing the original query and decomposed sub-queries.
    """
    if not query.strip():
        return QueryPlan(original_query=query, sub_queries=[], reasoning="Empty query")

    logger.info(f"Planning research via LangChain for: '{query}'")

    try:
        chain = get_planner_chain(temperature=0.3)
        plan = chain.invoke({"query": query})

        if isinstance(plan, QueryPlan):
            if not plan.original_query:
                plan.original_query = query
        elif isinstance(plan, dict):
            sub_queries = [
                SubQuery(**sq) if isinstance(sq, dict) else sq
                for sq in plan.get("sub_queries", [])
            ]
            plan = QueryPlan(
                original_query=query,
                sub_queries=sub_queries,
                reasoning=plan.get("reasoning", ""),
            )

        logger.info(
            f"Query plan created: {len(plan.sub_queries)} sub-queries "
            f"({plan.reasoning[:80]}...)"
        )
        return plan

    except Exception as e:
        logger.error(f"LangChain planner encountered an error: {e}")
        fallback = SubQuery(
            question=query,
            search_keywords=[query],
            source_type="both",
        )
        return QueryPlan(
            original_query=query,
            sub_queries=[fallback],
            reasoning=f"Fallback plan (LangChain error: {e})",
        )
