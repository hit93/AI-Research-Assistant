"""Tests for iterative report improvement and router conditional logic."""

from unittest.mock import MagicMock, patch
from langgraph.graph import END

from src.graphs.graph import build_research_graph, route_after_verifier
from src.graphs.nodes import improve_node
from src.graphs.state import ResearchGraphState
from src.models.schemas import (
    ResearchSource,
    SynthesisSection,
    VerificationIssue,
    VerificationResult,
)
from src.chains.refiner import (
    _format_issues_for_refiner,
    _format_sources_for_refiner,
    _format_synthesis_for_refiner,
)


def test_route_after_verifier_under_8():
    state: ResearchGraphState = {
        "query": "AI in Medicine",
        "verification": VerificationResult(
            is_approved=False,
            overall_score=6,
            issues=[VerificationIssue(section_heading="Key Findings", issue="Needs citations")],
            summary="Score below threshold.",
        ),
        "revision_count": 0,
        "max_revisions": 2,
    }
    next_node = route_after_verifier(state)
    assert next_node == "improver"


def test_route_after_verifier_8_or_above():
    state: ResearchGraphState = {
        "query": "AI in Medicine",
        "verification": VerificationResult(
            is_approved=True,
            overall_score=8,
            issues=[],
            summary="Meets quality target.",
        ),
        "revision_count": 0,
        "max_revisions": 2,
    }
    next_node = route_after_verifier(state)
    assert next_node == END

    state_9 = dict(state)
    state_9["verification"] = VerificationResult(
        is_approved=True,
        overall_score=9,
        issues=[],
        summary="Excellent report.",
    )
    assert route_after_verifier(state_9) == END


def test_route_after_verifier_max_revisions_exceeded():
    state: ResearchGraphState = {
        "query": "AI in Medicine",
        "verification": VerificationResult(
            is_approved=False,
            overall_score=7,
            issues=[],
            summary="Still 7/10 but reached max revisions.",
        ),
        "revision_count": 2,
        "max_revisions": 2,
    }
    next_node = route_after_verifier(state)
    assert next_node == END


def test_route_after_verifier_no_verification():
    state: ResearchGraphState = {
        "query": "AI in Medicine",
        "verification": None,
        "revision_count": 0,
        "max_revisions": 2,
    }
    next_node = route_after_verifier(state)
    assert next_node == END


def test_graph_structure_includes_improver():
    graph = build_research_graph()
    nodes = graph.nodes
    assert "planner" in nodes
    assert "retriever" in nodes
    assert "synthesizer" in nodes
    assert "verifier" in nodes
    assert "improver" in nodes


def test_improve_node_increments_revision_count():
    sources = [
        ResearchSource(
            title="Paper A",
            url_or_id="https://arxiv.org/1",
            content="Content A",
            source_type="arxiv",
        )
    ]
    synthesis = [
        SynthesisSection(
            heading="Section 1",
            content="Initial draft.",
            source_indices=[0],
        )
    ]
    verification = VerificationResult(
        is_approved=False,
        overall_score=6,
        issues=[
            VerificationIssue(
                section_heading="Section 1",
                issue="Needs more depth.",
                severity="medium",
                suggestion="Add technical detail.",
            )
        ],
        summary="Needs revision.",
    )
    state: ResearchGraphState = {
        "query": "Quantum AI",
        "sources": sources,
        "synthesis": synthesis,
        "verification": verification,
        "revision_count": 0,
        "max_revisions": 2,
    }

    mock_improved = [
        SynthesisSection(
            heading="Section 1",
            content="Improved draft with technical depth.",
            source_indices=[0],
        )
    ]

    with patch("src.graphs.nodes.refine_synthesis", return_value=mock_improved) as mock_refine:
        result = improve_node(state)
        mock_refine.assert_called_once_with(
            query="Quantum AI",
            sources=sources,
            synthesis=synthesis,
            verification=verification,
            hybrid_rag=None,
        )
        assert result["revision_count"] == 1
        assert result["status"] == "improved"
        assert result["synthesis"] == mock_improved


def test_refiner_formatting_helpers():
    sources = [
        ResearchSource(
            title="Agent Testing",
            url_or_id="https://arxiv.org/abs/2401.0001",
            content="Autonomous agents require benchmarking.",
            source_type="arxiv",
            authors=["Alice", "Bob"],
        )
    ]
    synthesis = [
        SynthesisSection(
            heading="Benchmarks",
            content="Agents are tested on benchmarks.",
            source_indices=[0],
        )
    ]
    verification = VerificationResult(
        is_approved=False,
        overall_score=5,
        issues=[
            VerificationIssue(
                section_heading="Benchmarks",
                issue="Missing specific benchmark names.",
                severity="high",
                suggestion="Cite GAIA or SWE-bench.",
            )
        ],
        summary="Lacks specificity.",
    )

    fmt_sources = _format_sources_for_refiner(sources)
    assert "[0] 📘 ArXiv Paper: \"Agent Testing\" by Alice, Bob" in fmt_sources

    fmt_synth = _format_synthesis_for_refiner(synthesis)
    assert "### Benchmarks" in fmt_synth
    assert "Sources cited: [0]" in fmt_synth

    fmt_issues = _format_issues_for_refiner(verification)
    assert "[HIGH] in 'Benchmarks': Missing specific benchmark names." in fmt_issues
    assert "Cite GAIA or SWE-bench." in fmt_issues
