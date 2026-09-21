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

    Enforces safe character budgets so that prompt + completion easily stay
    below Groq free/on-demand tier TPM limits (7000 ITPM for Qwen, 8000 TPM for GPT-OSS).
    """
    model_lower = model.lower()
    if "20b" in model_lower:
        return 500
    if "qwen" in model_lower:
        return 700
    return 900


from datetime import datetime


def _format_sources_for_prompt(sources: list[ResearchSource], model: str = "") -> str:
    """Format all provided sources as a numbered reference for the LLM with token budgeting and full-text metadata."""
    preview_chars = _source_preview_chars(model)
    lines = []
    for i, s in enumerate(sources):
        source_label = "📘 ArXiv Paper" if s.source_type == "arxiv" else "🌐 Web Source"
        authors_str = f" by {', '.join(s.authors)}" if s.authors else ""
        pub_str = f" ({s.published})" if s.published else ""
        full_text_label = (
            f"[FULL TEXT AVAILABLE - {len(s.full_text)} chars indexed]"
            if getattr(s, "has_full_text", False)
            else "[ABSTRACT / SNIPPET ONLY - HEDGE CONSERVATIVELY]"
        )
        content_preview = s.content[:preview_chars] + ("..." if len(s.content) > preview_chars else "")
        lines.append(
            f"[{i}] {source_label}: \"{s.title}\"{authors_str}{pub_str}\n"
            f"    Status: {full_text_label}\n"
            f"    Source: {s.url_or_id}\n"
            f"    Content Excerpt: {content_preview}\n"
        )
    return "\n".join(lines)


def _sync_section_citations(sections: list[SynthesisSection], num_sources: int) -> list[SynthesisSection]:
    """Ensure declared source_indices reflect all valid in-text [N] citations."""
    import re
    for sec in sections:
        cited_indices: set[int] = set(sec.source_indices or [])
        matches = re.findall(r"\[(\d+(?:\s*,\s*\d+)*)\]", sec.content)
        for match in matches:
            for num_str in match.split(","):
                num_str = num_str.strip()
                if num_str.isdigit():
                    val = int(num_str)
                    if 0 <= val < num_sources:
                        cited_indices.add(val)
        sec.source_indices = sorted(list(cited_indices))
    return sections



def synthesize_sources(
    query: str,
    sources: list[ResearchSource],
    hybrid_rag: list | None = None,
    plan_coverage: list | None = None,
    model: str | None = None,
) -> list[SynthesisSection]:
    """
    Synthesize retrieved sources into structured research findings via LangChain LCEL.

    Args:
        query:         The original research question.
        sources:       All retrieved and deduplicated ResearchSource items.
        hybrid_rag:    Optional HybridRAG instance for targeted passage retrieval.
        plan_coverage: Optional list of SubQueryCoverage objects.
        model:         Optional model override (defaults to settings.GROQ_MODEL / GPT-OSS-120B).

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
    current_date = datetime.now().strftime("%B %Y")

    coverage_lines = []
    if plan_coverage:
        for c in plan_coverage:
            status_tag = "✅ Sufficient" if getattr(c, "status", "") == "sufficient" else "⚠️ Insufficient Evidence (Emit Gap Note, Do Not Pad)"
            q_text = c.sub_query.question if hasattr(c, "sub_query") else str(c)
            coverage_lines.append(f"- Sub-Query: {q_text} -> {status_tag}")
    coverage_summary = "\n".join(coverage_lines) if coverage_lines else "Standard query decomposition; verify all sections against evidence."

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
            "current_date": current_date,
            "coverage_summary": coverage_summary,
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


        if hasattr(result, "sections"):
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

        # Synchronize declared source_indices with any inline text citations [N]
        sections = _sync_section_citations(sections, len(sources))

        logger.info(f"Synthesis complete: {len(sections)} sections generated and citations synchronized.")
        return sections

    except Exception as e:
        logger.error(f"LangChain synthesizer encountered an error: {e}", exc_info=True)
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
