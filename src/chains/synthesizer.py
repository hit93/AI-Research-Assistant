"""
Synthesizer Chain — LCEL chain for synthesizing gathered sources into structured sections.
"""

from langchain_core.runnables import Runnable
from src.prompts.synthesizer import synthesizer_prompt
from src.chains.llm import get_chat_llm
from src.chains.gateway import run_structured, MODEL_CONTEXT_LIMITS, _safe_max_tokens
from src.models.schemas import (
    ResearchSource,
    SynthesisSection,
    SynthesisReport,
)
from src.utils.logger import get_logger
from config.settings import settings

logger = get_logger("chains.synthesizer")

SYNTHESIS_FALLBACK_HEADING = "Raw Source Summary (Synthesis Fallback)"


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


def _source_preview_chars(model: str) -> int:
    """Return max characters per source to include in the prompt.

    Small-context models (e.g. gpt-oss-20b, 8k tokens) need shorter
    source previews so the prompt + completion fits in the context window.
    Large models get a generous 2500-char preview.
    """
    limit = MODEL_CONTEXT_LIMITS.get(model)
    if limit is not None and limit <= 8000:
        return 800   # ~200-250 tokens per source for small models
    return 2500      # full preview for large-context models


def _format_sources_for_prompt(sources: list[ResearchSource], model: str = "") -> str:
    """Format the source list as a numbered reference for the LLM."""
    preview_chars = _source_preview_chars(model)
    lines = []
    for i, s in enumerate(sources):
        source_label = "📘 ArXiv Paper" if s.source_type == "arxiv" else "🌐 Web Source"
        authors_str = f" by {', '.join(s.authors)}" if s.authors else ""
        content_preview = s.content[:preview_chars] + ("..." if len(s.content) > preview_chars else "")
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

    synth_model = model or getattr(settings, "SYNTHESIZER_MODEL", "openai/gpt-oss-120b")
    formatted_sources = _format_sources_for_prompt(sources, model=synth_model)

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
        prompt_value = synthesizer_prompt.invoke({
            "query": query,
            "source_count": len(sources),
            "formatted_sources": formatted_sources,
        })
        result = run_structured(
            SynthesisReport,
            prompt_value,
            model=synth_model,
            temperature=0.3,
            max_tokens=_safe_max_tokens(synth_model, 8192),
        )

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
                heading=SYNTHESIS_FALLBACK_HEADING,
                content=f"The synthesis engine encountered an issue ({e}). "
                        f"Here are the raw source excerpts:\n\n{raw_summary}",
                source_indices=list(range(min(5, len(sources)))),
            )
        ]
