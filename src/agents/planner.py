"""
Planner Agent — Decomposes a broad user query into focused sub-questions.

Takes a topic like "Quantum Computing in Drug Discovery" and uses the LLM
to break it into 3-5 targeted sub-queries, each with search keywords and
a recommended source type (arxiv, web, or both).
"""

from src.agents.llm_client import call_llm_json
from src.models.schemas import SubQuery, QueryPlan
from src.utils.logger import get_logger

logger = get_logger("planner")

# ── System prompt that instructs the LLM how to decompose queries ─────

PLANNER_SYSTEM_PROMPT = """\
You are a research planning assistant. Your job is to take a broad research topic
and decompose it into 3-5 focused, specific sub-questions that together would
provide comprehensive coverage of the topic.

For each sub-question, provide:
1. A clear, focused research question
2. 2-3 targeted search keywords/phrases for finding relevant sources
3. A source_type recommendation:
   - "arxiv" for technical/academic questions best answered by papers
   - "web" for current events, tutorials, industry applications, or general context
   - "both" when the question benefits from both academic and web sources

Respond ONLY with valid JSON in this exact format (no extra text):
{
  "reasoning": "Brief explanation of your decomposition strategy",
  "sub_queries": [
    {
      "question": "Focused sub-question here",
      "search_keywords": ["keyword1", "keyword2"],
      "source_type": "both"
    }
  ]
}

Guidelines:
- Make sub-questions specific and non-overlapping
- Cover different angles: fundamentals, current state, challenges, applications, future
- Keywords should be precise enough to return relevant academic papers or web results
- Aim for 3-5 sub-queries (fewer for narrow topics, more for broad ones)
"""


def plan_research(query: str) -> QueryPlan:
    """
    Decompose a user query into a structured research plan.

    Args:
        query: The user's broad research topic or question.

    Returns:
        A QueryPlan containing the original query and decomposed sub-queries.
    """
    if not query.strip():
        return QueryPlan(original_query=query, sub_queries=[], reasoning="Empty query")

    logger.info(f"Planning research for: '{query}'")

    try:
        data = call_llm_json(
            system_prompt=PLANNER_SYSTEM_PROMPT,
            user_prompt=f"Research topic: {query}",
            temperature=0.3,
        )

        sub_queries = []
        for item in data.get("sub_queries", []):
            sq = SubQuery(
                question=item.get("question", ""),
                search_keywords=item.get("search_keywords", []),
                source_type=item.get("source_type", "both"),
            )
            sub_queries.append(sq)

        plan = QueryPlan(
            original_query=query,
            sub_queries=sub_queries,
            reasoning=data.get("reasoning", ""),
        )

        logger.info(
            f"Query plan created: {len(plan.sub_queries)} sub-queries "
            f"({plan.reasoning[:80]}...)"
        )
        return plan

    except (ValueError, KeyError) as e:
        logger.error(f"Planner failed to parse LLM output: {e}")
        # Fallback: use the original query as a single sub-query
        fallback = SubQuery(
            question=query,
            search_keywords=[query],
            source_type="both",
        )
        return QueryPlan(
            original_query=query,
            sub_queries=[fallback],
            reasoning=f"Fallback plan (LLM parsing failed: {e})",
        )
