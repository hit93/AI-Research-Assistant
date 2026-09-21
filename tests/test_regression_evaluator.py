"""
Regression Test Suite for Research Assistant Systematic Failure Fixes.

Asserts the three core requirements:
1. Deliberately planted unsupported claim is caught by the verifier.
2. An uncited factual sentence is rejected/flagged as UNCITED.
3. An empty sub-query produces an 'insufficient evidence' note rather than filler.
"""

import pytest
from unittest.mock import MagicMock, patch
from src.models.schemas import (
    ResearchSource,
    SynthesisSection,
    SubQuery,
    SubQueryCoverage,
    QueryPlan,
)
from src.tools.hybrid_rag import HybridRAG
from src.chains.verifier import (
    extract_claims_from_synthesis,
    verify_synthesis,
    _check_overclaiming_and_contradictions,
)
from src.chains.synthesizer import synthesize_sources
from src.utils.exporter import export_to_markdown


@pytest.fixture
def mock_quantum_sources():
    """Fixed benchmark sources with ground-truth full-text passages."""
    s1 = ResearchSource(
        title="Benchmarking a 32-Qubit Trapped-Ion Processor",
        url_or_id="https://arxiv.org/abs/2305.12345",
        content="We benchmark a 32-qubit trapped-ion processor with two-qubit gate fidelities of 99.5%.",
        full_text="We report on the experimental benchmark of a 32-qubit trapped-ion quantum computer. The system achieves an average two-qubit gate fidelity of 99.5% under native gate operations. Single-qubit fidelity is 99.98%. Shuttle times between zones remain the dominant latency bottleneck.",
        source_type="arxiv",
        has_full_text=True,
        source_tier=1,
        authors=["Alice Smith", "Bob Jones"],
        published="2024-03-15",
    )
    s2 = ResearchSource(
        title="Superconducting Qubits: A 127-Qubit Eagle Architecture Overview",
        url_or_id="https://research.ibm.com/blog/127-qubit-eagle",
        content="Overview of the 127-qubit Eagle processor featuring heavy-hexagonal lattice.",
        full_text="The 127-qubit Eagle quantum processor utilizes a heavy-hexagonal lattice layout designed to reduce qubit crosstalk. Coherence times (T1 and T2) average 100 microseconds across the chip. While physical scale is increased, two-qubit gate error rates remain around 1% to 2% under current readout calibrations.",
        source_type="web",
        has_full_text=True,
        source_tier=1,
        authors=["IBM Quantum Team"],
        published="2023-11-20",
    )
    return [s1, s2]


def test_regression_planted_unsupported_claim_is_caught(mock_quantum_sources):
    """
    ASSERTION A: A deliberately planted unsupported / fabricated claim
    is caught by the verifier and fails approval.
    """
    hybrid_rag = HybridRAG(mock_quantum_sources)

    # Deliberately plant a fabricated claim with a promotional word
    bad_sections = [
        SynthesisSection(
            heading="3. Trapped-Ion Benchmarks",
            content="The trapped-ion processor demonstrated 1,000,000 physical qubits with a transformative 99.999% fidelity boost [0].",
            source_indices=[0],
        )
    ]

    # Extract claims
    claims = extract_claims_from_synthesis(bad_sections, len(mock_quantum_sources))
    assert len(claims) == 1
    assert claims[0].claim_id == "c_1"
    assert claims[0].cited_source_indices == [0]

    # Check promotional word detection
    overclaims, _ = _check_overclaiming_and_contradictions(claims)
    assert any("transformative" in oc for oc in overclaims)

    # Mock adversarial auditor to return UNSUPPORTED for the hallucinated 1,000,000 qubits
    mock_audit = MagicMock()
    mock_audit.claims = [
        MagicMock(
            claim_id="c_1",
            status="UNSUPPORTED",
            evidence_quote="",
            issues=["Fabricated qubit count (1,000,000) not in source text; source states 32 qubits."],
        )
    ]
    mock_audit.overclaiming_flags = ["transformative"]
    mock_audit.scope_creep_flags = []
    mock_audit.internal_contradictions = []

    with patch("src.chains.verifier.run_structured", return_value=mock_audit):
        result = verify_synthesis(
            query="Quantum computing benchmarks",
            sources=mock_quantum_sources,
            synthesis=bad_sections,
            hybrid_rag=hybrid_rag,
        )

    assert result.is_approved is False
    assert result.overall_score < 8
    assert any(c.verification_status == "UNSUPPORTED" for c in result.claims)
    assert len(result.unresolved_flags) >= 1
    assert "transformative" in str(result.overclaiming_flags)


def test_regression_uncited_factual_sentence_is_rejected(mock_quantum_sources):
    """
    ASSERTION B: An uncited factual sentence is detected as UNCITED and rejected.
    """
    hybrid_rag = HybridRAG(mock_quantum_sources)

    sections_with_uncited = [
        SynthesisSection(
            heading="4. Architecture Overview",
            content=(
                "The trapped-ion system benchmarks 32 qubits [0]. "
                "Superconducting circuits have achieved sub-millisecond coherence times across all industrial testbeds."  # UNCITED!
            ),
            source_indices=[0],
        )
    ]

    claims = extract_claims_from_synthesis(sections_with_uncited, len(mock_quantum_sources))
    assert len(claims) == 2

    # Second claim has no [N] citation and must be labeled UNCITED
    uncited_claims = [c for c in claims if c.verification_status == "UNCITED"]
    assert len(uncited_claims) == 1
    assert "sub-millisecond coherence times" in uncited_claims[0].claim_text

    # Verify that presence of uncited claims rejects approval
    mock_audit = MagicMock()
    mock_audit.claims = [
        MagicMock(claim_id="c_1", status="SUPPORTED", evidence_quote="32-qubit trapped-ion processor", issues=[]),
        MagicMock(claim_id="c_2", status="UNCITED", evidence_quote="", issues=["Uncited statement"]),
    ]
    mock_audit.overclaiming_flags = []
    mock_audit.scope_creep_flags = []
    mock_audit.internal_contradictions = []

    with patch("src.chains.verifier.run_structured", return_value=mock_audit):
        result = verify_synthesis(
            query="Quantum architecture",
            sources=mock_quantum_sources,
            synthesis=sections_with_uncited,
            hybrid_rag=hybrid_rag,
        )

    assert result.is_approved is False
    assert any(c.verification_status == "UNCITED" for c in result.claims)


def test_regression_empty_subquery_produces_insufficient_evidence_note(mock_quantum_sources):
    """
    ASSERTION C: An empty sub-query produces an 'insufficient evidence' note
    rather than fabricated filler.
    """
    empty_subquery = SubQuery(
        question="Industrial case studies of quantum computing in pharmaceutical drug discovery",
        search_keywords=["quantum chemistry drug discovery pharma deployment"],
        source_type="both",
    )

    plan_coverage = [
        SubQueryCoverage(
            sub_query=empty_subquery,
            sources_found_count=0,
            full_text_count=0,
            evidence_extracted=False,
            status="insufficient",
            notes="Insufficient evidence retrieved for 'Industrial case studies of quantum computing in pharmaceutical drug discovery'",
        )
    ]

    # When synthesizing with an insufficient coverage subquery, the synthesizer prompt receives the gap note
    # Mock LLM to return evidence-based sections containing the gap disclosure
    mock_report = MagicMock()
    mock_report.sections = [
        SynthesisSection(
            heading="6. Practical Applications & Industrial Impact",
            content="> **Evidence Gap:** Insufficient empirical evidence was retrieved regarding pharmaceutical drug discovery deployment case studies.",
            source_indices=[],
        )
    ]

    with patch("src.chains.synthesizer.run_structured", return_value=mock_report):
        sections = synthesize_sources(
            query="Quantum computing pharma deployment",
            sources=mock_quantum_sources,
            plan_coverage=plan_coverage,
        )

    assert len(sections) >= 1
    content_lower = sections[0].content.lower()
    assert "insufficient" in content_lower or "evidence gap" in content_lower


def test_transparency_report_export(mock_quantum_sources):
    """
    ASSERTION D: The exported markdown report includes transparency header metrics,
    the plan-vs-coverage table, and the claim-level verification audit table.
    """
    from src.models.schemas import ResearchResult, VerificationResult, AtomicClaim

    coverage = [
        SubQueryCoverage(
            sub_query=SubQuery(question="Trapped ion benchmarks", search_keywords=["trapped ion"], source_type="arxiv"),
            sources_found_count=1,
            full_text_count=1,
            evidence_extracted=True,
            status="sufficient",
            notes="Covered",
        )
    ]

    verified_claims = [
        AtomicClaim(
            claim_id="c_1",
            claim_text="We benchmark a 32-qubit processor.",
            section_heading="3. Milestones",
            cited_source_indices=[0],
            verification_status="SUPPORTED",
            evidence_quote="32-qubit trapped-ion processor with 99.5% fidelity",
        )
    ]

    verification = VerificationResult(
        is_approved=True,
        overall_score=10,
        issues=[],
        summary="Verified successfully.",
        claims=verified_claims,
        total_claims=1,
        supported_count=1,
        supported_ratio=1.0,
        revisions_made=0,
        unresolved_flags=[],
        plan_coverage=coverage,
    )

    result = ResearchResult(
        query="Quantum computing hardware",
        plan=QueryPlan(original_query="Quantum computing hardware", sub_queries=[coverage[0].sub_query]),
        sources=mock_quantum_sources,
        synthesis=[
            SynthesisSection(
                heading="3. Milestones",
                content="We benchmark a 32-qubit processor [0].",
                source_indices=[0],
            )
        ],
        verification=verification,
        plan_coverage=coverage,
        duration_seconds=12.5,
    )

    md = export_to_markdown(result)

    # Check for transparency header metrics
    assert "Sources Analyzed:" in md
    assert "full-text body" in md
    assert "Claims Verified:" in md
    assert "Verification Status:" in md

    # Check for Plan-vs-Coverage table
    assert "## 📋 Research Strategy & Sub-Query Coverage" in md
    assert "| Sub-Query | Target | Sources Found |" in md

    # Check for Claim-Level Verification table
    assert "## 🔎 Claim-Level Verification Audit Table" in md
    assert "| Claim # | Section | Claim Statement | Status |" in md
    assert "c_1" in md


def test_quote_must_exist_in_source_or_marked_unverified(mock_quantum_sources):
    """
    Requirement 1: If the evidence quote is empty or does not exist as a substring
    in the cited source (normalized whitespace and case), the claim is marked UNVERIFIED
    and counts as not supported in the pass/fail ratio.
    """
    sections = [
        SynthesisSection(
            heading="3. Benchmarks",
            content="The trapped-ion processor achieved 99.5% gate fidelity [0].",
            source_indices=[0],
        )
    ]

    # Mock adversarial audit returning a fake quote that does not appear in source 0
    mock_audit = MagicMock()
    mock_audit.claims = [
        MagicMock(
            claim_id="c_1",
            status="SUPPORTED",
            evidence_quote="Completely fabricated quote not present anywhere in the source document",
            issues=[],
        )
    ]
    mock_audit.overclaiming_flags = []
    mock_audit.scope_creep_flags = []
    mock_audit.internal_contradictions = []

    with patch("src.chains.verifier.run_structured", return_value=mock_audit):
        result = verify_synthesis(
            query="Quantum computing",
            sources=mock_quantum_sources,
            synthesis=sections,
        )

        assert len(result.claims) == 1
        claim = result.claims[0]
        # Must be marked UNVERIFIED because quote is not in source
        assert claim.verification_status == "UNVERIFIED"
        # UNVERIFIED counts as not supported
        assert result.supported_count == 0
        assert result.supported_ratio == 0.0
        assert result.is_approved is False


def test_split_compound_sentences_one_fact_per_claim():
    """
    Requirement 2: Compound sentences are split so each claim contains a single fact.
    Every claim is printed in the audit table, and the header count matches the table's row count.
    """
    compound_section = [
        SynthesisSection(
            heading="Milestones",
            content="Superconducting qubits achieved 99.5% fidelity [0], while trapped-ion systems demonstrated 1000 qubits [1].",
            source_indices=[0, 1],
        )
    ]

    claims = extract_claims_from_synthesis(compound_section, num_sources=2)
    # Should be split into at least 2 atomic single-fact claims
    assert len(claims) >= 2

    # Verify every claim is rendered in markdown and header matches table row count
    from src.models.schemas import ResearchResult, VerificationResult, ResearchSource, QueryPlan
    sources = [
        ResearchSource(title="S0", url_or_id="http://s0", content="Text 0", source_type="arxiv"),
        ResearchSource(title="S1", url_or_id="http://s1", content="Text 1", source_type="web"),
    ]
    v = VerificationResult(
        is_approved=True,
        overall_score=9,
        claims=claims,
        total_claims=len(claims),
        supported_count=len(claims),
        supported_ratio=1.0,
    )
    res = ResearchResult(
        query="Test query",
        plan=QueryPlan(original_query="Test query"),
        sources=sources,
        synthesis=compound_section,
        verification=v,
    )
    md = export_to_markdown(res)

    # Header claims count matches
    assert f"Claims Verified:** {len(claims)}" in md
    # Every claim is present in the table
    for c in claims:
        assert c.claim_id in md


def test_drop_irrelevant_sources_and_soften_overclaims():
    """
    Requirement 4: Discard sources scoring below threshold for every sub-query.
    Regex-flag words like 'revolutionized', 'seamlessly', 'definitive', etc., and soften them.
    """
    from src.graphs.nodes import discard_irrelevant_sources_across_plan, _soften_synthesized_sections

    sq1 = SubQuery(question="Trapped ion quantum computing", search_keywords=["ion", "trapped"])
    sq2 = SubQuery(question="Superconducting qubit fidelity", search_keywords=["superconducting", "fidelity"])

    relevant_source = ResearchSource(
        title="Superconducting Qubits",
        url_or_id="http://sc.com",
        content="High fidelity superconducting qubits",
        source_type="arxiv",
    )
    irrelevant_source = ResearchSource(
        title="Agricultural Irrigation Techniques in Europe",
        url_or_id="http://farm.com",
        content="Soil moisture retention and crop rotation methods",
        source_type="web",
    )

    retained = discard_irrelevant_sources_across_plan(
        [relevant_source, irrelevant_source],
        [sq1, sq2],
        threshold=1.0,
    )
    # The irrelevant agriculture paper must be discarded
    assert len(retained) == 1
    assert retained[0].title == "Superconducting Qubits"

    # Test softening of promotional overclaims
    sections = [
        SynthesisSection(
            heading="4. Impact",
            content="The platform revolutionized computing and achieved unprecedented scaling seamlessly [0].",
            source_indices=[0],
        )
    ]
    softened = _soften_synthesized_sections(sections)
    content_after = softened[0].content
    assert "revolutionized" not in content_after.lower()
    assert "seamlessly" not in content_after.lower()
    assert "unprecedented" not in content_after.lower()

