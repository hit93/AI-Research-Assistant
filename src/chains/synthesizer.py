"""
Synthesizer Chain — LCEL chain for synthesizing gathered sources into structured sections.
"""

from langchain_core.runnables import Runnable
from src.prompts.synthesizer import synthesizer_prompt
from src.chains.llm import get_chat_llm
from src.models.schemas import (
    ResearchSource,
    SynthesisSection,
    SynthesisReport,
)
from src.utils.logger import get_logger
from config.settings import settings

logger = get_logger("chains.synthesizer")


def get_synthesizer_chain(
    temperature: float = 0.3,
    max_tokens: int = 8192,
    model: str | None = None,
) -> Runnable:
    """Return an LCEL chain for structured source synthesis using GPT-OSS-120B."""
    synth_model = model or getattr(settings, "SYNTHESIZER_MODEL", "openai/gpt-oss-120b")
    logger.debug(f"Creating synthesizer chain with model: {synth_model}")
    llm = get_chat_llm(temperature=temperature, max_tokens=max_tokens, model=synth_model)
    structured_llm = llm.with_structured_output(SynthesisReport)
    return synthesizer_prompt | structured_llm


def _format_sources_for_prompt(sources: list[ResearchSource]) -> str:
    """Format the source list as a numbered reference for the LLM."""
    lines = []
    for i, s in enumerate(sources):
        source_label = "📘 ArXiv Paper" if s.source_type == "arxiv" else "🌐 Web Source"
        authors_str = f" by {', '.join(s.authors)}" if s.authors else ""
        content_preview = s.content[:2500] + ("..." if len(s.content) > 2500 else "")
        lines.append(
            f"[{i}] {source_label}: \"{s.title}\"{authors_str}\n"
            f"    Source: {s.url_or_id}\n"
            f"    Content: {content_preview}\n"
        )
    return "\n".join(lines)


def synthesize_sources(
    query: str,
    sources: list[ResearchSource],
    hybrid_rag: list | None = None,
    model: str | None = None,
) -> list[SynthesisSection]:
    """
    Synthesize retrieved sources into structured research findings via LangChain LCEL.

    Args:
        query:      The original research question.
        sources:    All retrieved and deduplicated ResearchSource items.
        hybrid_rag: Optional HybridRAG instance for targeted passage retrieval.
        model:      Optional model override (defaults to settings.GROQ_MODEL / GPT-OSS-120B).

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

    logger.info(f"Synthesizing {len(sources)} sources via LangChain for: '{query}'")

    formatted_sources = _format_sources_for_prompt(sources)

    if hybrid_rag and hasattr(hybrid_rag, "search"):
        try:
            rag_chunks = hybrid_rag.search(query, top_k=6)
            if rag_chunks:
                from src.tools.hybrid_rag import format_rag_chunks_for_prompt
                rag_block = format_rag_chunks_for_prompt(rag_chunks)
                formatted_sources += f"\n\n=== RELEVANT HYBRID RAG PASSAGES (BM25 + VECTOR RRF) ===\n{rag_block}"
                logger.info(f"[Synthesizer RAG] Injected {len(rag_chunks)} hybrid RAG passages into synthesis context.")
        except Exception as e:
            logger.warning(f"Failed to inject RAG passages into synthesis: {e}")

    try:
        chain = get_synthesizer_chain(temperature=0.3, max_tokens=8192, model=model)
        result = chain.invoke({
            "query": query,
            "source_count": len(sources),
            "formatted_sources": formatted_sources,
        })

        if isinstance(result, SynthesisReport):
            sections = result.sections
        elif isinstance(result, dict):
            sections = [
                SynthesisSection(**s) if isinstance(s, dict) else s
                for s in result.get("sections", [])
            ]
        else:
            sections = []

        if not sections:
            raise ValueError("LLM returned empty synthesis sections.")

        logger.info(f"Synthesis complete: {len(sections)} sections generated")
        return sections

    except Exception as e:
        logger.error(f"LangChain synthesizer encountered an error: {e}")
        raw_summary = "\n\n".join(
            f"**{s.title}** ({s.source_type}): {s.content[:200]}"
            for s in sources[:5]
        )
        return [
            SynthesisSection(
                heading="Raw Source Summary (Synthesis Fallback)",
                content=f"The synthesis engine encountered an issue ({e}). "
                        f"Here are the raw source excerpts:\n\n{raw_summary}",
                source_indices=list(range(min(5, len(sources)))),
            )
        ]
