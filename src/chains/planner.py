"""
Planner Chain — LCEL chain for decomposing a research query into targeted sub-queries.
"""

from langchain_core.runnables import Runnable
from src.prompts.planner import planner_prompt
from src.chains.llm import get_chat_llm
from src.chains.gateway import run_structured
from src.models.schemas import SubQuery, QueryPlan
from src.utils.logger import get_logger
from config.settings import settings

logger = get_logger("chains.planner")


def get_planner_chain(temperature: float = 0.3, model: str | None = None) -> Runnable:
    """Return an LCEL chain for structured query planning."""
    llm = get_chat_llm(temperature=temperature, model=model)
    structured_llm = llm.with_structured_output(QueryPlan)
    return planner_prompt | structured_llm


from datetime import datetime
from src.tools.web_search_tool import search_web


def plan_research(query: str, model: str | None = None) -> QueryPlan:
    """
    Decompose a user query into a structured research plan via LangChain LCEL,
    informed by an upfront landscape search and current date injection.
    """
    if not query.strip():
        return QueryPlan(original_query=query, sub_queries=[], reasoning="Empty query")

    logger.info(f"Planning research via LangChain for: '{query}'")

    current_date = datetime.now().strftime("%B %Y")
    landscape_context = "No landscape pre-search available."
    try:
        landscape_results = search_web(f"{query} key players recent developments", max_results=3)
        if landscape_results:
            landscape_context = "\n".join(f"- {r.title}: {r.snippet[:250]}" for r in landscape_results)
    except Exception as e:
        logger.debug(f"Landscape search skipped: {e}")

    try:
        prompt_value = planner_prompt.invoke({
            "query": query,
            "current_date": current_date,
            "landscape_context": landscape_context,
        })
        plan = run_structured(
            QueryPlan,
            prompt_value,
            model=model or settings.GROQ_MODEL,
            temperature=0.3,
        )

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

        if not plan or not plan.sub_queries:
            logger.warning(f"Planner LLM returned 0 sub-queries for '{query}'. Generating robust orthogonal sub-queries.")
            plan = QueryPlan(
                original_query=query,
                sub_queries=[
                    SubQuery(
                        question=f"What are the leading architectures, technical foundations, and hardware modalities in {query} as of {current_date}?",
                        search_keywords=[query, "architectures", "foundations", "hardware platforms"],
                        source_type="both",
                    ),
                    SubQuery(
                        question=f"What are the empirical performance benchmarks, quantitative metrics, and comparative evaluations in {query}?",
                        search_keywords=[query, "benchmarks", "performance metrics", "evaluation"],
                        source_type="arxiv",
                    ),
                    SubQuery(
                        question=f"What are the primary commercial deployments, industrial use cases, and key market players in {query}?",
                        search_keywords=[query, "industry deployments", "commercial applications", "key players"],
                        source_type="web",
                    ),
                    SubQuery(
                        question=f"What are the primary technical bottlenecks, failure modes, and scalability challenges in {query}?",
                        search_keywords=[query, "bottlenecks", "scaling challenges", "limitations"],
                        source_type="both",
                    ),
                ],
                reasoning=f"Robust orthogonal decomposition generated for '{query}' as of {current_date}.",
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
