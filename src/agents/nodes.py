from config.settings import settings
from src.tools.arxiv_tool import search_arxiv, papers_to_sources
from src.tools.web_search_tool import search_web, web_results_to_sources
from src.tools.text_cleaner import deduplicate_sources
from src.utils.logger import get_logger

logger = get_logger("agents.nodes")

def _call_groq(prompt: str, system_message: str = "You are an expert academic research assistant.") -> str:
    """Helper to call Groq API with fallback."""
    if not settings.GROQ_API_KEY:
        return ""
    try:
        from groq import Groq
        client = Groq(api_key=settings.GROQ_API_KEY)
        response = client.chat.completions.create(
            model=settings.GROQ_MODEL,
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
            max_tokens=2048,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.warning(f"Groq LLM call failed: {e}")
        return ""

def planner_node(state: dict) -> dict:
    """Decompose research topic into targeted sub-questions."""
    topic = state.get("topic", "")
    logger.info(f"Planner Node analyzing topic: '{topic}'")

    prompt = (
        f"Break down this research topic into 3 specific, actionable research search queries or sub-questions.\n"
        f"Topic: {topic}\n"
        f"Respond with only the 3 queries, one per line, no numbering or extra preamble."
    )
    llm_output = _call_groq(prompt)
    if llm_output:
        sub_questions = [line.strip().lstrip("-*123456789. ") for line in llm_output.splitlines() if line.strip()]
    else:
        # Fallback heuristic decomposition
        sub_questions = [
            f"{topic} core concepts and foundational principles",
            f"{topic} latest research breakthroughs and architecture",
            f"{topic} practical applications and open challenges",
        ]

    return {"sub_questions": sub_questions[:3]}

def research_node(state: dict) -> dict:
    """Execute ArXiv and Web Search tools for the topic and sub-questions."""
    topic = state.get("topic", "")
    queries = [topic] + state.get("sub_questions", [])
    logger.info(f"Research Node querying sources for {len(queries)} terms...")

    all_raw_sources = []
    # Query main topic
    arxiv_papers = search_arxiv(topic, max_results=3)
    all_raw_sources.extend(papers_to_sources(arxiv_papers))

    web_items = search_web(topic, max_results=3)
    all_raw_sources.extend(web_results_to_sources(web_items))

    # Query first sub-question for specialized depth
    if len(queries) > 1:
        sub_q = queries[1]
        all_raw_sources.extend(papers_to_sources(search_arxiv(sub_q, max_results=2)))
        all_raw_sources.extend(web_results_to_sources(search_web(sub_q, max_results=2)))

    # Deduplicate
    unique_sources = deduplicate_sources(all_raw_sources)
    sources_data = [s.model_dump() for s in unique_sources]
    logger.info(f"Research Node retrieved {len(sources_data)} unique sources.")
    return {"sources": sources_data}

def synthesizer_node(state: dict) -> dict:
    """Synthesize gathered literature and web evidence into an academic report."""
    topic = state.get("topic", "")
    sources = state.get("sources", [])
    logger.info(f"Synthesizer Node generating report for '{topic}' from {len(sources)} sources...")

    # Format source context for LLM
    context_blocks = []
    for idx, s in enumerate(sources, start=1):
        context_blocks.append(
            f"[{idx}] {s.get('title')} ({s.get('source_type').upper()})\n"
            f"URL/ID: {s.get('url_or_id')}\n"
            f"Excerpt: {s.get('content')[:400]}\n"
        )
    context_text = "\n".join(context_blocks)

    prompt = (
        f"You are a scientific research assistant. Synthesize a structured academic report on the following topic based on the gathered sources.\n\n"
        f"Topic: {topic}\n\n"
        f"Gathered Evidence Sources:\n{context_text}\n\n"
        f"Structure your response with:\n"
        f"# Executive Summary\n"
        f"## Key Research Insights & Findings\n"
        f"## Methodological Approaches & Controversies\n"
        f"## Research Gaps & Future Directions\n"
        f"## References & Sources (include links from the provided evidence)\n"
    )

    llm_report = _call_groq(prompt)
    if not llm_report:
        # Structured fallback summary
        llm_report = (
            f"# Research Report: {topic}\n\n"
            f"## Executive Summary\n"
            f"Synthesized from {len(sources)} academic papers and web sources.\n\n"
            f"## Key Sources & Literature Review\n"
        )
        for idx, s in enumerate(sources, start=1):
            llm_report += f"- **[{s.get('title')}]({s.get('url_or_id')})** ({s.get('source_type')})\n  {s.get('content')[:250]}...\n\n"

    return {"report": llm_report}
