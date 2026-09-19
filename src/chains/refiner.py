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

logger = get_logger("chains.refiner")


def get_refiner_chain(temperature: float = 0.3, max_tokens: int = 4096) -> Runnable:
    """Return an LCEL chain for structured report refinement."""
    llm = get_chat_llm(temperature=temperature, max_tokens=max_tokens)
    structured_llm = llm.with_structured_output(SynthesisReport)
    return refiner_prompt | structured_llm


def _format_sources_for_refiner(sources: list[ResearchSource]) -> str:
    """Format sources as a numbered reference for the refiner."""
    lines = []
    for i, s in enumerate(sources):
        source_label = "📘 ArXiv Paper" if s.source_type == "arxiv" else "🌐 Web Source"
        authors_str = f" by {', '.join(s.authors)}" if s.authors else ""
        content_preview = s.content[:600] + ("..." if len(s.content) > 600 else "")
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
) -> list[SynthesisSection]:
    """
    Revise and improve synthesis sections to address reviewer feedback.

    Args:
        query:        Original research question.
        sources:      Available retrieved sources.
        synthesis:    Current synthesis sections.
        verification: Evaluator's verdict containing score, issues, and suggestions.

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
    formatted_synthesis = _format_synthesis_for_refiner(synthesis)
    feedback_issues = _format_issues_for_refiner(verification)

    try:
        chain = get_refiner_chain(temperature=0.3, max_tokens=4096)
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
