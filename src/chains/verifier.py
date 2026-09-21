from langchain_core.runnables import Runnable
from config.settings import settings
from src.prompts.verifier import verifier_prompt
from src.chains.llm import get_chat_llm
from src.chains.gateway import run_structured
from src.chains.synthesizer import SYNTHESIS_FALLBACK_HEADING
from src.models.schemas import (
    ResearchSource,
    SynthesisSection,
    VerificationIssue,
    VerificationResult,
)
from src.utils.logger import get_logger

logger = get_logger("chains.verifier")

APPROVAL_SCORE_THRESHOLD = 8


def audit_citations(
    synthesis: list[SynthesisSection],
    sources: list[ResearchSource],
) -> list[VerificationIssue]:
    """
    Deterministically verify all in-text citations [N] against available sources.
    Flags out-of-bounds citation indices, missing references, and mismatch errors.
    """
    import re
    issues: list[VerificationIssue] = []
    num_sources = len(sources)

    for section in synthesis:
        # Extract all [N] or [N, M] citations
        cited_indices: set[int] = set()
        matches = re.findall(r"\[(\d+(?:\s*,\s*\d+)*)\]", section.content)
        for match in matches:
            for num_str in match.split(","):
                num_str = num_str.strip()
                if num_str.isdigit():
                    cited_indices.add(int(num_str))

        # Check for out-of-bounds citations
        for idx in cited_indices:
            if idx < 0 or idx >= num_sources:
                issues.append(
                    VerificationIssue(
                        section_heading=section.heading,
                        issue=f"Citation index [{idx}] is out of bounds (only {num_sources} sources available: [0..{num_sources-1}]).",
                        severity="high",
                        suggestion=f"Remove or re-map [{idx}] to a valid retrieved source index.",
                    )
                )

        # Check declared source_indices vs in-text citations
        declared_indices = set(section.source_indices)
        undeclared = cited_indices - declared_indices
        if undeclared and num_sources > 0:
            issues.append(
                VerificationIssue(
                    section_heading=section.heading,
                    issue=f"Section text cites sources {sorted(list(undeclared))} but they are omitted in declared source_indices.",
                    severity="low",
                    suggestion="Synchronize section.source_indices with inline text citations.",
                )
            )

    return issues


def apply_approval_policy(verification: VerificationResult) -> VerificationResult:
    """Enforce approval from score and issue severity; never trust the LLM flag alone."""
    if not verification.judge_ran:
        verification.is_approved = False
        return verification
    has_high = any(issue.severity == "high" for issue in verification.issues)
    verification.is_approved = verification.overall_score >= APPROVAL_SCORE_THRESHOLD and not has_high
    return verification


def _is_synthesis_fallback(synthesis: list[SynthesisSection]) -> bool:
    return any(section.heading == SYNTHESIS_FALLBACK_HEADING for section in synthesis)


def get_verifier_chain(temperature: float = 0.2, model: str | None = None) -> Runnable:
    """Return an LCEL chain for structured report verification."""
    verifier_model = model or settings.VERIFIER_MODEL
    logger.debug(f"Creating verifier chain with model: {verifier_model}")
    llm = get_chat_llm(temperature=temperature, model=verifier_model)
    structured_llm = llm.with_structured_output(VerificationResult)
    return verifier_prompt | structured_llm


def _format_sources_for_verification(sources: list[ResearchSource]) -> str:
    """Format all provided sources as a numbered reference for the verification LLM with safe token budgeting."""
    lines = []
    for i, s in enumerate(sources):
        source_label = "📘 ArXiv Paper" if s.source_type == "arxiv" else "🌐 Web Source"
        authors_str = f" by {', '.join(s.authors)}" if s.authors else ""
        content_preview = s.content[:700] + ("..." if len(s.content) > 700 else "")
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
    hybrid_rag: list | None = None,
) -> VerificationResult:
    """
    Verify a synthesized report against its sources via LLM-as-judge.

    Args:
        query:      The original research question.
        sources:    All retrieved ResearchSource items.
        synthesis:  The synthesized report sections to verify.
        model:      Optional model override (defaults to settings.VERIFIER_MODEL).
        hybrid_rag: Optional HybridRAG instance for claim-level passage retrieval.

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
            judge_ran=False,
        )

    if not sources:
        logger.warning("No sources to verify against — rejecting with low score.")
        return VerificationResult(
            is_approved=False,
            overall_score=3,
            issues=[],
            summary="No sources available for cross-referencing. Report not approved.",
            judge_ran=False,
        )

    if _is_synthesis_fallback(synthesis):
        logger.warning("Synthesis fallback detected — skipping judge and rejecting report.")
        return VerificationResult(
            is_approved=False,
            overall_score=1,
            issues=[],
            summary="Synthesis failed and returned raw source excerpts. Report not approved.",
            judge_ran=False,
        )

    logger.info(
        f"Verifying {len(synthesis)} sections against {len(sources)} sources for: '{query}'"
    )

    formatted_sources = _format_sources_for_verification(sources)

    if hybrid_rag and hasattr(hybrid_rag, "search"):
        try:
            rag_chunks = hybrid_rag.search(query, top_k=5)
            if rag_chunks:
                from src.tools.hybrid_rag import format_rag_chunks_for_prompt
                rag_block = format_rag_chunks_for_prompt(rag_chunks)
                formatted_sources += f"\n\n=== AUDIT RAG EVIDENCE PASSAGES (BM25 + VECTOR RRF) ===\n{rag_block}"
                logger.info(f"[Verifier RAG] Injected {len(rag_chunks)} hybrid RAG audit passages.")
        except Exception as e:
            logger.warning(f"Failed to inject RAG passages into verifier: {e}")
    formatted_synthesis = _format_synthesis_for_verification(synthesis)

    try:
        verifier_model = model or settings.VERIFIER_MODEL
        prompt_value = verifier_prompt.invoke({
            "query": query,
            "source_count": len(sources),
            "formatted_sources": formatted_sources,
            "formatted_synthesis": formatted_synthesis,
        })
        result = run_structured(
            VerificationResult,
            prompt_value,
            model=verifier_model,
            temperature=0.2,
        )

        if isinstance(result, VerificationResult):
            verification = result
        elif isinstance(result, dict):
            verification = VerificationResult(**result)
        else:
            raise ValueError(f"Unexpected verifier output type: {type(result)}")

        # Merge deterministic citation issues
        citation_issues = audit_citations(synthesis, sources)
        if citation_issues:
            verification.issues.extend(citation_issues)
            if any(ci.severity == "high" for ci in citation_issues):
                verification.overall_score = min(verification.overall_score, 6)
                logger.warning(f"[Verifier Audit] Downgrading score to {verification.overall_score} due to high severity citation errors.")

        verification.judge_ran = True
        verification = apply_approval_policy(verification)

        logger.info(
            f"Verification complete: score={verification.overall_score}/10, "
            f"approved={verification.is_approved}, issues={len(verification.issues)}"
        )
        return verification

    except Exception as e:
        logger.error(f"LangChain verifier encountered an error: {e}")
        return VerificationResult(
            is_approved=False,
            overall_score=1,
            issues=[],
            summary=f"Verification could not be completed ({e}). Report not approved.",
            judge_ran=False,
        )
