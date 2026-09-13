"""
Synthesizer Agent — Reasons over retrieved sources to produce structured findings.

Takes the user's original query plus all retrieved ResearchSource items and
uses the LLM to generate a structured research synthesis with:
  - Key Findings
  - Consensus & Controversies
  - Research Gaps
  - Practical Applications
Each section references its supporting sources by index.
"""

from src.agents.llm_client import call_llm_json
from src.models.schemas import ResearchSource, SynthesisSection
from src.utils.logger import get_logger

logger = get_logger("synthesizer")

# ── System prompt that instructs the LLM how to synthesize ────────────

SYNTHESIZER_SYSTEM_PROMPT = """\
You are a research synthesis expert. You will receive a research question and
a numbered list of sources (academic papers and web articles). Your job is to
analyze these sources and produce a structured research synthesis.

Create 3-5 sections from the following categories (skip any that don't apply):
- "Key Findings": The most important discoveries and results
- "Technical Approaches": Methods, algorithms, or frameworks discussed
- "Consensus & Controversies": Where sources agree or disagree
- "Research Gaps": What remains unexplored or unresolved
- "Practical Applications": Real-world use cases and industry impact
- "Future Directions": Where the field is heading

Rules:
- Write clear, informative paragraphs (not bullet lists)
- Reference sources by their index number (e.g., "According to [1]..." or "[2, 3]")
- Be specific — cite actual findings, numbers, and claims from the sources
- If sources are insufficient, note this honestly rather than fabricating content
- Each section should have 2-4 sentences minimum

Respond ONLY with valid JSON in this exact format (no extra text):
{
  "sections": [
    {
      "heading": "Key Findings",
      "content": "Detailed synthesis paragraph referencing [1], [2]...",
      "source_indices": [0, 1, 3]
    }
  ]
}

The source_indices should be 0-based indices into the source list provided.
"""


def _format_sources_for_prompt(sources: list[ResearchSource]) -> str:
    """Format the source list as a numbered reference for the LLM."""
    lines = []
    for i, s in enumerate(sources):
        source_label = "📘 ArXiv Paper" if s.source_type == "arxiv" else "🌐 Web Source"
        authors_str = f" by {', '.join(s.authors)}" if s.authors else ""
        # Truncate very long content to keep within context limits
        content_preview = s.content[:600] + ("..." if len(s.content) > 600 else "")
        lines.append(
            f"[{i}] {source_label}: \"{s.title}\"{authors_str}\n"
            f"    Source: {s.url_or_id}\n"
            f"    Content: {content_preview}\n"
        )
    return "\n".join(lines)


def synthesize_sources(
    query: str,
    sources: list[ResearchSource],
) -> list[SynthesisSection]:
    """
    Synthesize retrieved sources into structured research findings.

    Args:
        query:   The original research question.
        sources: All retrieved and deduplicated ResearchSource items.

    Returns:
        A list of SynthesisSection objects with findings and source references.
    """
    if not sources:
        logger.warning("No sources to synthesize.")
        return [
            SynthesisSection(
                heading="No Sources Found",
                content="The research tools did not retrieve any relevant sources for this query. "
                        "Try broadening the search terms or checking your internet connection.",
                source_indices=[],
            )
        ]

    logger.info(f"Synthesizing {len(sources)} sources for: '{query}'")

    formatted_sources = _format_sources_for_prompt(sources)
    user_prompt = (
        f"Research question: {query}\n\n"
        f"Available sources ({len(sources)} total):\n\n"
        f"{formatted_sources}"
    )

    try:
        data = call_llm_json(
            system_prompt=SYNTHESIZER_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            temperature=0.3,
            max_tokens=4096,
        )

        sections = []
        for item in data.get("sections", []):
            section = SynthesisSection(
                heading=item.get("heading", "Untitled Section"),
                content=item.get("content", ""),
                source_indices=item.get("source_indices", []),
            )
            sections.append(section)

        logger.info(f"Synthesis complete: {len(sections)} sections generated")
        return sections

    except (ValueError, KeyError) as e:
        logger.error(f"Synthesizer failed to parse LLM output: {e}")
        # Fallback: return a raw summary section
        raw_summary = "\n\n".join(
            f"**{s.title}** ({s.source_type}): {s.content[:200]}"
            for s in sources[:5]
        )
        return [
            SynthesisSection(
                heading="Raw Source Summary (Synthesis Failed)",
                content=f"The synthesis engine encountered an error. "
                        f"Here are the raw source excerpts:\n\n{raw_summary}",
                source_indices=list(range(min(5, len(sources)))),
            )
        ]
