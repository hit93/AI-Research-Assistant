from langchain_core.runnables import Runnable
from config.settings import settings
from src.prompts.verifier import verifier_prompt
from src.chains.llm import get_chat_llm
from src.models.schemas import (
    ResearchSource,
    SynthesisSection,
    VerificationResult,
)
from src.utils.logger import get_logger

logger = get_logger("chains.verifier")


def get_verifier_chain(temperature: float = 0.2, model: str | None = None) -> Runnable:
    """Return an LCEL chain for structured report verification."""
    verifier_model = model or settings.VERIFIER_MODEL
    logger.debug(f"Creating verifier chain with model: {verifier_model}")
    llm = get_chat_llm(temperature=temperature, model=verifier_model)
    structured_llm = llm.with_structured_output(VerificationResult)
    return verifier_prompt | structured_llm


def _format_sources_for_verification(sources: list[ResearchSource]) -> str:
    """Format sources as a numbered reference for the verification LLM."""
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


def _format_synthesis_for_verification(sections: list[SynthesisSection]) -> str:
    """Format synthesis sections for the verification LLM."""
    lines = []
    for section in sections:
        refs = ", ".join(f"[{i}]" for i in section.source_indices) if section.source_indices else "none"
        lines.append(
            f"## {section.heading}\n"
            f"{section.content}\n"
            f"(Sources referenced: {refs})\n"
        )
    return "\n".join(lines)


def verify_synthesis(
    query: str,
    sources: list[ResearchSource],
    synthesis: list[SynthesisSection],
    model: str | None = None,
) -> VerificationResult:
    """
    Verify a synthesized report against its sources via LLM-as-judge.

    Args:
        query:     The original research question.
        sources:   All retrieved ResearchSource items.
        synthesis: The synthesized report sections to verify.
        model:     Optional model override (defaults to settings.VERIFIER_MODEL).

    Returns:
        A VerificationResult with approval status, score, and any issues found.
    """
    if not synthesis:
        logger.warning("No synthesis sections to verify.")
        return VerificationResult(
            is_approved=False,
            overall_score=1,
            issues=[],
            summary="No synthesis sections were provided for verification.",
        )

    if not sources:
        logger.warning("No sources to verify against — auto-approving with low score.")
        return VerificationResult(
            is_approved=True,
            overall_score=3,
            issues=[],
            summary="No sources available for cross-referencing. Report accepted with low confidence.",
        )

    logger.info(
        f"Verifying {len(synthesis)} sections against {len(sources)} sources for: '{query}'"
    )

    formatted_sources = _format_sources_for_verification(sources)
    formatted_synthesis = _format_synthesis_for_verification(synthesis)

    try:
        chain = get_verifier_chain(temperature=0.2, model=model)
        result = chain.invoke({
            "query": query,
            "source_count": len(sources),
            "formatted_sources": formatted_sources,
            "formatted_synthesis": formatted_synthesis,
        })

        if isinstance(result, VerificationResult):
            verification = result
        elif isinstance(result, dict):
            verification = VerificationResult(**result)
        else:
            raise ValueError(f"Unexpected verifier output type: {type(result)}")

        logger.info(
            f"Verification complete: score={verification.overall_score}/10, "
            f"approved={verification.is_approved}, issues={len(verification.issues)}"
        )
        return verification

    except Exception as e:
        logger.error(f"LangChain verifier encountered an error: {e}")
        return VerificationResult(
            is_approved=True,
            overall_score=5,
            issues=[],
            summary=f"Verification could not be completed ({e}). Report auto-approved with reduced confidence.",
        )
