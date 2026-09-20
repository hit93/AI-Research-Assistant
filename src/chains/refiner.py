"""Refiner Chain — LCEL chain for iterative report improvement based on Verifier feedback."""

from langchain_core.runnables import Runnable
from src.prompts.refiner import refiner_prompt
from src.chains.llm import get_chat_llm
from src.models.schemas import (
    ResearchSource,
    SynthesisReport,
    SynthesisSection,
    VerificationResult,
)
from src.utils.logger import get_logger
from config.settings import settings

logger = get_logger("chains.refiner")


def get_refiner_chain(
    temperature: float = 0.3,
    max_tokens: int = 8192,
    model: str | None = None,
) -> Runnable:
    """Return an LCEL chain for structured report refinement using GPT-OSS-120B."""
    refine_model = model or getattr(settings, "SYNTHESIZER_MODEL", "openai/gpt-oss-120b")
    logger.debug(f"Creating refiner chain with model: {refine_model}")
    llm = get_chat_llm(temperature=temperature, max_tokens=max_tokens, model=refine_model)
    structured_llm = llm.with_structured_output(SynthesisReport)
    return refiner_prompt | structured_llm


def _format_sources_for_refiner(sources: list[ResearchSource]) -> str:
    """Format sources as a numbered reference for the refiner."""
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


def _format_synthesis_for_refiner(sections: list[SynthesisSection]) -> str:
    """Format existing synthesis sections for the refiner."""
    lines = []
    for section in sections:
        refs = ", ".join(f"[{i}]" for i in section.source_indices) if section.source_indices else "none"
        lines.append(
            f"### {section.heading}\n"
            f"{section.content}\n"
            f"(Sources cited: {refs})\n"
        )
    return "\n".join(lines)


def _format_issues_for_refiner(verification: VerificationResult) -> str:
    """Format reviewer issues and suggestions into clear action items."""
    if not verification.issues:
        return "No specific section issues were cataloged. Focus on enhancing depth, clarity, and citations."

    lines = []
    for i, issue in enumerate(verification.issues, 1):
        sugg = f" | Suggestion: {issue.suggestion}" if issue.suggestion else ""
        lines.append(
            f"{i}. [{issue.severity.upper()}] in '{issue.section_heading}': {issue.issue}{sugg}"
        )
    return "\n".join(lines)


def refine_synthesis(
    query: str,
    sources: list[ResearchSource],
    synthesis: list[SynthesisSection],
    verification: VerificationResult,
    hybrid_rag: list | None = None,
    model: str | None = None,
) -> list[SynthesisSection]:
    """
    Revise and improve synthesis sections to address reviewer feedback.

    Args:
        query:        Original research question.
        sources:      Available retrieved sources.
        synthesis:    Current synthesis sections.
        verification: Evaluator's verdict containing score, issues, and suggestions.
        hybrid_rag:   Optional HybridRAG instance for targeted gap retrieval.
        model:        Optional model override (defaults to settings.GROQ_MODEL / GPT-OSS-120B).

    Returns:
        Revised list of SynthesisSection objects.
    """
    if not synthesis:
        logger.warning("No synthesis sections provided to refine.")
        return synthesis

    logger.info(
        f"Refining synthesis for '{query}' — current score: {verification.overall_score}/10, "
        f"resolving {len(verification.issues)} issues"
    )

    formatted_sources = _format_sources_for_refiner(sources)

    if hybrid_rag and hasattr(hybrid_rag, "search"):
        try:
            critique_text = f"{query} " + " ".join(i.issue for i in verification.issues)
            rag_chunks = hybrid_rag.search(critique_text, top_k=5)
            if rag_chunks:
                from src.tools.hybrid_rag import format_rag_chunks_for_prompt
                rag_block = format_rag_chunks_for_prompt(rag_chunks)
                formatted_sources += f"\n\n=== REVISION GAP RAG EVIDENCE (BM25 + VECTOR RRF) ===\n{rag_block}"
                logger.info(f"[Refiner RAG] Injected {len(rag_chunks)} targeted gap evidence passages.")
        except Exception as e:
            logger.warning(f"Failed to inject RAG passages into refiner: {e}")
    formatted_synthesis = _format_synthesis_for_refiner(synthesis)
    feedback_issues = _format_issues_for_refiner(verification)

    try:
        chain = get_refiner_chain(temperature=0.3, max_tokens=8192, model=model)
        result = chain.invoke({
            "query": query,
            "source_count": len(sources),
            "formatted_sources": formatted_sources,
            "current_synthesis": formatted_synthesis,
            "overall_score": verification.overall_score,
            "evaluator_summary": verification.summary or "Score below 8. Requires improvement.",
            "feedback_issues": feedback_issues,
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
            raise ValueError("Refiner returned empty sections.")

        logger.info(f"Refinement complete: {len(sections)} revised sections generated")
        return sections

    except Exception as e:
        logger.error(f"Report refinement encountered an error: {e}. Preserving existing synthesis.")
        return synthesis
