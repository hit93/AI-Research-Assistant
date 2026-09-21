import re
from typing import List, Literal, Optional
from pydantic import BaseModel, Field
from langchain_core.runnables import Runnable
from config.settings import settings
from src.prompts.verifier import claim_verifier_prompt
from src.chains.llm import get_chat_llm
from src.chains.gateway import run_structured
from src.chains.synthesizer import SYNTHESIS_FALLBACK_HEADING
from src.models.schemas import (
    ResearchSource,
    SynthesisSection,
    VerificationIssue,
    VerificationResult,
    AtomicClaim,
    SubQueryCoverage,
)
from src.utils.logger import get_logger

logger = get_logger("chains.verifier")

PROMOTIONAL_TERMS = [
    "decisive", "transformative", "exponentially", "revolutionary",
    "game-changing", "miraculous", "groundbreaking", "unprecedented",
    "revolutionized", "seamlessly", "definitive", "robust foundation",
]


class EvaluatedClaim(BaseModel):
    claim_id: str
    status: Literal["SUPPORTED", "PARTIAL", "UNSUPPORTED", "CONTRADICTED", "UNCITED", "UNVERIFIED"]
    evidence_quote: str = Field(default="", description="Exact verbatim quote from evidence passage that supports or contradicts the claim")
    issues: list[str] = Field(default_factory=list, description="Reasoning, discrepancies, dropped caveats, or ungrounded figures")


class AdversarialAuditOutput(BaseModel):
    claims: list[EvaluatedClaim] = Field(default_factory=list)
    overclaiming_flags: list[str] = Field(default_factory=list, description="List of promotional or hyperbolic terms identified")
    scope_creep_flags: list[str] = Field(default_factory=list, description="List of instances where limitations of one platform were attributed to another")
    internal_contradictions: list[str] = Field(default_factory=list, description="List of direct contradictions between different sections")
    audit_summary: str = Field(default="")


def _split_into_atomic_facts(sentence: str) -> list[str]:
    """
    Split compound sentences so each claim contains a single fact.
    Splits across semicolons, em dashes, and coordinating conjunction clauses.
    """
    clauses = re.split(r"[;—]\s*|--\s*", sentence)
    facts: list[str] = []
    for cl in clauses:
        # Split on coordinating conjunctions separating clauses: ", and ", ", while ", ", whereas ", ", but "
        sub_parts = re.split(r",\s+(?:and|while|whereas|but|although|yet)\s+", cl, flags=re.IGNORECASE)
        for part in sub_parts:
            part_clean = part.strip()
            # Clean leading conjunctions if leftover
            part_clean = re.sub(r"^(?:and|while|whereas|but|although|yet|however,)\s+", "", part_clean, flags=re.IGNORECASE).strip()
            if len(part_clean) >= 15:
                facts.append(part_clean)
            elif facts:
                facts[-1] = f"{facts[-1]}, {part_clean}"
            elif part_clean:
                facts.append(part_clean)
    return facts if facts else [sentence]


def extract_claims_from_synthesis(synthesis: list[SynthesisSection], num_sources: int) -> list[AtomicClaim]:
    """
    Extract factual statements from synthesized sections as atomic single-fact claims with cited source IDs.
    Compound sentences are split so each claim contains a single fact.
    """
    claims: list[AtomicClaim] = []
    claim_counter = 1

    for sec in synthesis:
        lines = sec.content.split("\n")
        in_code_block = False
        for line in lines:
            line_str = line.strip()
            if line_str.startswith("```"):
                in_code_block = not in_code_block
                continue
            if in_code_block or not line_str or line_str.startswith("|") or line_str.startswith("#"):
                continue

            # Split into sentences using punctuation boundaries
            raw_sentences = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9\[])", line_str)
            for sent in raw_sentences:
                sent_clean = sent.strip()
                if len(sent_clean) < 15:
                    continue

                # Extract sentence-level parent citations
                parent_cited_indices: list[int] = []
                matches = re.findall(r"\[(\d+(?:\s*,\s*\d+)*)\]", sent_clean)
                for m in matches:
                    for num_str in m.split(","):
                        num_clean = num_str.strip()
                        if num_clean.isdigit():
                            val = int(num_clean)
                            if 0 <= val < num_sources:
                                parent_cited_indices.append(val)
                parent_cited_indices = sorted(list(set(parent_cited_indices)))

                # Split compound sentences so each claim contains a single fact
                fact_clauses = _split_into_atomic_facts(sent_clean)

                for fact in fact_clauses:
                    # Check if clause has its own specific citation
                    clause_matches = re.findall(r"\[(\d+(?:\s*,\s*\d+)*)\]", fact)
                    clause_indices: list[int] = []
                    for cm in clause_matches:
                        for num_str in cm.split(","):
                            num_clean = num_str.strip()
                            if num_clean.isdigit():
                                val = int(num_clean)
                                if 0 <= val < num_sources:
                                    clause_indices.append(val)
                    clause_indices = sorted(list(set(clause_indices)))

                    # Use clause-specific citation if present, else inherit from parent sentence
                    cited_indices = clause_indices if clause_indices else parent_cited_indices
                    claim_body = re.sub(r"\[\d+(?:\s*,\s*\d+)*\]", "", fact).strip()

                    if len(claim_body) < 10:
                        continue

                    is_uncited = len(cited_indices) == 0

                    claim = AtomicClaim(
                        claim_id=f"c_{claim_counter}",
                        claim_text=claim_body,
                        section_heading=sec.heading,
                        cited_source_indices=cited_indices,
                        verification_status="UNCITED" if is_uncited else "SUPPORTED",
                        evidence_quote="",
                        matched_source_index=cited_indices[0] if cited_indices else None,
                        issues=["Uncited factual sentence. Statements must cite verified source [N]."] if is_uncited else [],
                    )
                    claims.append(claim)
                    claim_counter += 1

    return claims


def audit_citations(
    synthesis: list[SynthesisSection],
    sources: list[ResearchSource],
) -> list[VerificationIssue]:
    """
    Deterministically verify all in-text citations [N] against available sources.
    Flags out-of-bounds citation indices.
    """
    issues: list[VerificationIssue] = []
    num_sources = len(sources)

    for section in synthesis:
        matches = re.findall(r"\[(\d+(?:\s*,\s*\d+)*)\]", section.content)
        for match in matches:
            for num_str in match.split(","):
                num_str = num_str.strip()
                if num_str.isdigit():
                    idx = int(num_str)
                    if idx < 0 or idx >= num_sources:
                        issues.append(
                            VerificationIssue(
                                section_heading=section.heading,
                                issue=f"Citation index [{idx}] is out of bounds (only {num_sources} sources available: [0..{num_sources-1}]).",
                                severity="high",
                                suggestion=f"Remove or re-map [{idx}] to a valid retrieved source index.",
                            )
                        )
    return issues


def _normalize_text(text: str) -> str:
    """Normalize whitespace and convert to lowercase for exact substring matching."""
    return " ".join(text.lower().split())


def _is_quote_in_source(quote: str, source: ResearchSource) -> bool:
    """Check if the evidence quote exists as a verbatim substring in the source text (normalized)."""
    if not quote or not quote.strip():
        return False
    norm_quote = _normalize_text(quote)
    if not norm_quote or len(norm_quote) < 5:
        return False

    source_texts = []
    if getattr(source, "full_text", None):
        source_texts.append(source.full_text)
    if getattr(source, "content", None):
        source_texts.append(source.content)
    combined = " ".join(source_texts)
    norm_source = _normalize_text(combined)
    return norm_quote in norm_source


def apply_approval_policy(verification: VerificationResult) -> VerificationResult:
    """Enforce approval from score, issue severity, and claim grounding; never trust LLM flag alone."""
    if not verification.judge_ran:
        verification.is_approved = False
        return verification
    has_high = any(issue.severity == "high" for issue in verification.issues)
    has_unsupported = any(c.verification_status in ("UNSUPPORTED", "CONTRADICTED", "UNCITED", "UNVERIFIED") for c in verification.claims)
    threshold = getattr(settings, "VERIFICATION_PASS_THRESHOLD", 0.95)
    verification.is_approved = (
        verification.overall_score >= 8
        and not has_high
        and not has_unsupported
        and (verification.supported_ratio >= threshold if verification.total_claims > 0 else True)
    )
    return verification


def get_verifier_chain(temperature: float = 0.0, model: str | None = None) -> Runnable:
    """Return an LCEL chain for structured adversarial report verification."""
    verifier_model = model or settings.VERIFIER_MODEL
    logger.debug(f"Creating verifier chain with model: {verifier_model}")
    llm = get_chat_llm(temperature=temperature, model=verifier_model)
    structured_llm = llm.with_structured_output(AdversarialAuditOutput)
    return claim_verifier_prompt | structured_llm


def _check_overclaiming_and_contradictions(claims: list[AtomicClaim]) -> tuple[list[str], list[str]]:
    """Scan claims deterministically for promotional buzzwords and apparent contradictions."""
    overclaims: list[str] = []
    contradictions: list[str] = []

    for c in claims:
        text_lower = c.claim_text.lower()
        for term in PROMOTIONAL_TERMS:
            if re.search(r"\b" + re.escape(term) + r"\b", text_lower):
                overclaims.append(f"Claim [{c.claim_id}] contains promotional word '{term}' without verified comparative context.")

    # Cross-section contradiction heuristics
    solved_claims = [c for c in claims if "solved" in c.claim_text.lower() or "eliminated" in c.claim_text.lower()]
    unsolved_claims = [c for c in claims if "unsolved" in c.claim_text.lower() or "bottleneck" in c.claim_text.lower()]
    if solved_claims and unsolved_claims:
        for s in solved_claims:
            for u in unsolved_claims:
                if any(k in s.claim_text.lower() and k in u.claim_text.lower() for k in ["error", "decoherence", "leakage", "scaling"]):
                    contradictions.append(
                        f"Contradiction between '{s.section_heading}' ({s.claim_text[:60]}...) and '{u.section_heading}' ({u.claim_text[:60]}...)"
                    )

    return overclaims, contradictions


def verify_synthesis(
    query: str,
    sources: list[ResearchSource],
    synthesis: list[SynthesisSection],
    model: str | None = None,
    hybrid_rag: list | None = None,
    plan_coverage: list[SubQueryCoverage] | None = None,
    revision_count: int = 0,
) -> VerificationResult:
    """
    Execute atomic claim-level adversarial verification against full-text source chunks.
    """
    if not synthesis:
        return VerificationResult(
            is_approved=False,
            overall_score=1,
            issues=[],
            summary="No synthesis sections provided for verification.",
            judge_ran=False,
        )

    if not sources:
        return VerificationResult(
            is_approved=False,
            overall_score=3,
            issues=[],
            summary="No sources available for verification cross-referencing. Report not approved.",
            judge_ran=False,
        )

    if any(s.heading == SYNTHESIS_FALLBACK_HEADING for s in synthesis):
        return VerificationResult(
            is_approved=False,
            overall_score=1,
            issues=[],
            summary="Synthesis failed and returned raw source excerpts. Report not approved.",
            judge_ran=False,
        )

    # 1. Extract atomic claims
    claims = extract_claims_from_synthesis(synthesis, len(sources))
    logger.info(f"[Verifier] Extracted {len(claims)} atomic claims across {len(synthesis)} sections.")

    # 2. Retrieve relevant full-text passages per claim
    claims_prompt_blocks: list[str] = []
    for c in claims:
        evidence_passages: list[str] = []
        if c.cited_source_indices and hybrid_rag and hasattr(hybrid_rag, "search_in_source"):
            for s_idx in c.cited_source_indices:
                chunks = hybrid_rag.search_in_source(s_idx, c.claim_text, top_k=2)
                for chk in chunks:
                    full_text_badge = "Full Text" if chk.has_full_text else "Abstract Only"
                    evidence_passages.append(
                        f"  [Source {s_idx} ({full_text_badge})]: \"{chk.text[:350]}\""
                    )

        passages_text = "\n".join(evidence_passages) if evidence_passages else "  (No cited source passages retrieved)"
        claims_prompt_blocks.append(
            f"Claim {c.claim_id} (Section: '{c.section_heading}', Cited: {c.cited_source_indices}):\n"
            f"Assertion: \"{c.claim_text}\"\n"
            f"Evidence from cited sources:\n{passages_text}\n"
        )

    formatted_claims = "\n".join(claims_prompt_blocks)

    # 3. Execute adversarial claim verification LLM call
    verifier_model = model or settings.VERIFIER_MODEL
    audit_output = None
    try:
        prompt_val = claim_verifier_prompt.invoke({
            "query": query,
            "claims_with_evidence": formatted_claims,
        })
        audit_output = run_structured(
            AdversarialAuditOutput,
            prompt_val,
            model=verifier_model,
            temperature=0.0,
        )
        if isinstance(audit_output, VerificationResult):
            return audit_output
    except Exception as e:
        logger.error(f"[Verifier] Adversarial LLM audit failed: {e}")
        return VerificationResult(
            is_approved=False,
            overall_score=1,
            issues=[],
            summary=f"Verification could not be completed ({e}). Report not approved.",
            judge_ran=False,
        )

    # 4. Integrate adversarial results into claims
    if audit_output and audit_output.claims:
        evaluated_map = {item.claim_id: item for item in audit_output.claims}
        for c in claims:
            if c.claim_id in evaluated_map:
                ev = evaluated_map[c.claim_id]
                c.verification_status = ev.status
                c.evidence_quote = ev.evidence_quote
                if ev.issues:
                    c.issues.extend(ev.issues)

    # 4b. Enforce strict quote existence: quote must exist as a substring in cited source's text
    for c in claims:
        if c.verification_status == "SUPPORTED":
            found = False
            if c.evidence_quote and c.cited_source_indices:
                for s_idx in c.cited_source_indices:
                    if 0 <= s_idx < len(sources):
                        if _is_quote_in_source(c.evidence_quote, sources[s_idx]):
                            found = True
                            c.matched_source_index = s_idx
                            break
            if not found:
                c.verification_status = "UNVERIFIED"
                c.issues.append("Evidence quote was empty or not found as a verbatim substring in cited source text.")

    # 5. Run deterministic checks for overclaiming & contradictions
    overclaims, contradictions = _check_overclaiming_and_contradictions(claims)
    citation_issues = audit_citations(synthesis, sources)

    # 6. Gating and Score Calculation
    total_claims = len(claims)
    supported_count = sum(1 for c in claims if c.verification_status == "SUPPORTED")
    supported_ratio = (supported_count / total_claims) if total_claims > 0 else 1.0

    has_unsupported_or_contradicted = any(
        c.verification_status in ("UNSUPPORTED", "CONTRADICTED") for c in claims
    )
    has_unverified = any(c.verification_status == "UNVERIFIED" for c in claims)
    has_uncited = any(c.verification_status == "UNCITED" for c in claims)
    has_citation_error = any(ci.severity == "high" for ci in citation_issues)

    pass_threshold = getattr(settings, "VERIFICATION_PASS_THRESHOLD", 0.95)
    is_approved = (
        supported_ratio >= pass_threshold
        and not has_unsupported_or_contradicted
        and not has_unverified
        and not has_uncited
        and not has_citation_error
    )

    # Calibrate overall score out of 10 (bounded between 1 and 10)
    raw_score = int(round(supported_ratio * 10))
    if has_unsupported_or_contradicted or has_unverified or has_uncited or has_citation_error:
        overall_score = max(1, min(raw_score, 6))
    else:
        overall_score = max(1, min(raw_score, 10))

    unresolved = [c for c in claims if c.verification_status != "SUPPORTED"]

    # Format verification issues list
    issues: list[VerificationIssue] = list(citation_issues)
    for c in unresolved:
        issues.append(
            VerificationIssue(
                section_heading=c.section_heading,
                issue=f"[{c.verification_status}] Claim '{c.claim_text[:80]}...' - {'; '.join(c.issues) if c.issues else 'Lacks full-text evidence'}",
                severity="high" if c.verification_status in ("UNSUPPORTED", "CONTRADICTED", "UNVERIFIED") else "medium",
                suggestion=f"Ground claim with direct evidence from cited sources or remove assertion.",
            )
        )

    summary_text = (
        f"Claim-level audit verified {total_claims} claims: {supported_count}/{total_claims} supported ({supported_ratio:.1%}). "
        f"{len(unresolved)} flagged issues, {len(overclaims)} overclaims, {len(contradictions)} cross-section contradictions."
    )

    full_text_count = sum(1 for s in sources if getattr(s, "has_full_text", False))
    abstract_only_count = len(sources) - full_text_count

    return VerificationResult(
        is_approved=is_approved,
        overall_score=overall_score,
        issues=issues,
        summary=summary_text,
        judge_ran=True,
        claims=claims,
        total_claims=total_claims,
        supported_count=supported_count,
        supported_ratio=round(supported_ratio, 3),
        revisions_made=revision_count,
        unresolved_flags=unresolved,
        overclaiming_flags=overclaims,
        internal_contradictions=contradictions,
        plan_coverage=plan_coverage or [],
        full_text_source_count=full_text_count,
        abstract_only_source_count=abstract_only_count,
    )

