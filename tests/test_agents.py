"""
Tests for Backward-Compatibility Facades: LLM Client, Planner, Synthesizer, and Orchestrator.

Verifies that callers using src.agents continue to work seamlessly when delegating
to the new canonical LangChain and LangGraph layers (src.chains and src.graphs).
"""

import json
from unittest.mock import patch, MagicMock

from src.models.schemas import (
    SubQuery,
    QueryPlan,
    SynthesisSection,
    SynthesisReport,
    VerificationIssue,
    VerificationResult,
    ResearchSource,
    ResearchResult,
)


# ═══════════════════════════════════════════════════════════════
# LLM Client Tests (Facade)
# ═══════════════════════════════════════════════════════════════

class TestLLMClient:
    """Tests for the LLM client facade."""

    @patch("src.chains.llm.get_chat_llm")
    def test_call_llm_returns_text(self, mock_get_llm):
        """call_llm() should return the model's text response."""
        mock_response = MagicMock()
        mock_response.content = "Hello from LangChain LLM"
        mock_get_llm.return_value.invoke.return_value = mock_response

        from src.agents.llm_client import call_llm
        result = call_llm("system", "user")
        assert result == "Hello from LangChain LLM"

    @patch("src.chains.llm.call_llm")
    def test_call_llm_json_parses_response(self, mock_call_llm):
        """call_llm_json() should parse valid JSON from the LLM."""
        mock_call_llm.return_value = json.dumps({"key": "value", "items": [1, 2, 3]})

        from src.agents.llm_client import call_llm_json
        result = call_llm_json("system", "user")
        assert result == {"key": "value", "items": [1, 2, 3]}

    @patch("src.chains.llm.call_llm")
    def test_call_llm_json_strips_code_fences(self, mock_call_llm):
        """call_llm_json() should handle ```json ... ``` wrapper."""
        mock_call_llm.return_value = '```json\n{"result": true}\n```'

        from src.agents.llm_client import call_llm_json
        result = call_llm_json("system", "user")
        assert result == {"result": True}

    @patch("src.chains.llm.call_llm")
    def test_call_llm_json_raises_on_invalid(self, mock_call_llm):
        """call_llm_json() should raise ValueError on invalid JSON."""
        mock_call_llm.return_value = "not valid json at all"

        from src.agents.llm_client import call_llm_json
        try:
            call_llm_json("system", "user")
            assert False, "Should have raised ValueError"
        except ValueError:
            pass


# ═══════════════════════════════════════════════════════════════
# Planner Tests (Facade)
# ═══════════════════════════════════════════════════════════════

class TestPlanner:
    """Tests for the Planner facade delegating to src.chains.planner."""

    @patch("src.chains.gateway.get_chat_llm")
    def test_plan_research_parses_subqueries(self, mock_get_llm):
        """plan_research() should return a QueryPlan with parsed sub-queries."""
        expected_plan = QueryPlan(
            original_query="Quantum Computing in Drug Discovery",
            reasoning="Test decomposition",
            sub_queries=[
                SubQuery(
                    question="What is quantum computing?",
                    search_keywords=["quantum computing basics"],
                    source_type="both",
                ),
                SubQuery(
                    question="Drug discovery applications?",
                    search_keywords=["quantum drug discovery"],
                    source_type="arxiv",
                ),
            ],
        )
        mock_structured = MagicMock()
        mock_structured.return_value = expected_plan
        mock_structured.invoke.return_value = expected_plan
        mock_get_llm.return_value.with_structured_output.return_value = mock_structured

        from src.agents.planner import plan_research
        plan = plan_research("Quantum Computing in Drug Discovery")

        assert isinstance(plan, QueryPlan)
        assert plan.original_query == "Quantum Computing in Drug Discovery"
        assert len(plan.sub_queries) == 2
        assert plan.sub_queries[0].source_type == "both"
        assert plan.sub_queries[1].source_type == "arxiv"
        assert "quantum" in plan.sub_queries[0].search_keywords[0].lower()

    def test_plan_research_empty_query(self):
        """plan_research() with empty query should return empty plan."""
        from src.agents.planner import plan_research
        plan = plan_research("")
        assert len(plan.sub_queries) == 0

    @patch("src.chains.gateway.get_chat_llm")
    def test_plan_research_fallback_on_error(self, mock_get_llm):
        """plan_research() should fallback to direct query on LangChain error."""
        mock_get_llm.side_effect = RuntimeError("Groq Connection Refused")

        from src.agents.planner import plan_research
        plan = plan_research("test topic")

        assert len(plan.sub_queries) == 1
        assert plan.sub_queries[0].question == "test topic"
        assert "Fallback" in plan.reasoning


# ═══════════════════════════════════════════════════════════════
# Synthesizer Tests (Facade)
# ═══════════════════════════════════════════════════════════════

class TestSynthesizer:
    """Tests for the Synthesizer facade delegating to src.chains.synthesizer."""

    @patch("src.chains.gateway.get_chat_llm")
    def test_synthesize_returns_sections(self, mock_get_llm):
        """synthesize_sources() should return structured SynthesisSection list."""
        mock_report = SynthesisReport(
            sections=[
                SynthesisSection(
                    heading="Key Findings",
                    content="Source [0] shows X. Source [1] confirms Y.",
                    source_indices=[0, 1],
                ),
                SynthesisSection(
                    heading="Research Gaps",
                    content="No sources address Z.",
                    source_indices=[],
                ),
            ]
        )
        mock_structured = MagicMock()
        mock_structured.return_value = mock_report
        mock_structured.invoke.return_value = mock_report
        mock_get_llm.return_value.with_structured_output.return_value = mock_structured

        sources = [
            ResearchSource(title="Paper A", url_or_id="http://a.com", content="Content A", source_type="arxiv"),
            ResearchSource(title="Article B", url_or_id="http://b.com", content="Content B", source_type="web"),
        ]

        from src.agents.synthesizer import synthesize_sources
        sections = synthesize_sources("test query", sources)

        assert len(sections) == 2
        assert sections[0].heading == "Key Findings"
        assert 0 in sections[0].source_indices
        assert sections[1].heading == "Research Gaps"

    def test_synthesize_no_sources(self):
        """synthesize_sources() with empty sources should return fallback."""
        from src.agents.synthesizer import synthesize_sources
        sections = synthesize_sources("test query", [])
        assert len(sections) == 1
        assert "No Sources" in sections[0].heading

    @patch("src.chains.gateway.get_chat_llm")
    def test_synthesize_fallback_on_error(self, mock_get_llm):
        """synthesize_sources() should return raw summary on LangChain error."""
        mock_get_llm.side_effect = RuntimeError("Synthesis model timeout")

        sources = [
            ResearchSource(title="Paper A", url_or_id="http://a.com", content="Content A", source_type="arxiv"),
        ]

        from src.agents.synthesizer import synthesize_sources
        sections = synthesize_sources("test", sources)

        assert len(sections) == 1
        assert "Fallback" in sections[0].heading


# ═══════════════════════════════════════════════════════════════
# Verifier Tests (Facade)
# ═══════════════════════════════════════════════════════════════

class TestVerifier:
    """Tests for the Verifier facade delegating to src.chains.verifier."""

    @patch("src.chains.gateway.get_chat_llm")
    def test_verify_returns_verification_result(self, mock_get_llm):
        """verify_synthesis() should return a VerificationResult."""
        mock_result = VerificationResult(
            is_approved=True,
            overall_score=8,
            issues=[
                VerificationIssue(
                    section_heading="Key Findings",
                    issue="Minor unsupported claim in paragraph 2",
                    severity="low",
                    suggestion="Add citation for the claim about efficiency gains.",
                )
            ],
            summary="Report is well-structured with minor citation gaps.",
            judge_ran=True,
        )
        mock_structured = MagicMock()
        mock_structured.invoke.return_value = mock_result
        mock_get_llm.return_value.with_structured_output.return_value = mock_structured

        sources = [
            ResearchSource(title="Paper A", url_or_id="http://a.com", content="Content A", source_type="arxiv"),
        ]
        synthesis = [
            SynthesisSection(heading="Key Findings", content="Important results.", source_indices=[0]),
        ]

        from src.agents.verifier import verify_synthesis
        result = verify_synthesis("test query", sources, synthesis)

        assert isinstance(result, VerificationResult)
        assert result.is_approved is True
        assert result.overall_score == 8
        assert len(result.issues) == 1
        assert result.issues[0].severity == "low"

    def test_verify_no_synthesis(self):
        """verify_synthesis() with empty synthesis should return low-score result."""
        from src.agents.verifier import verify_synthesis
        result = verify_synthesis("test", [], [])
        assert result.is_approved is False
        assert result.overall_score == 1

    def test_verify_no_sources(self):
        """verify_synthesis() with no sources should reject the report."""
        from src.agents.verifier import verify_synthesis
        synthesis = [
            SynthesisSection(heading="Summary", content="Content", source_indices=[]),
        ]
        result = verify_synthesis("test", [], synthesis)
        assert result.is_approved is False
        assert result.overall_score == 3
        assert result.judge_ran is False

    @patch("src.chains.gateway.get_chat_llm")
    def test_verify_fallback_on_error(self, mock_get_llm):
        """verify_synthesis() should reject the report when the judge LLM fails."""
        mock_get_llm.side_effect = RuntimeError("Verifier model timeout")

        sources = [
            ResearchSource(title="Paper A", url_or_id="http://a.com", content="Content A", source_type="arxiv"),
        ]
        synthesis = [
            SynthesisSection(heading="Findings", content="Text", source_indices=[0]),
        ]

        from src.agents.verifier import verify_synthesis
        result = verify_synthesis("test", sources, synthesis)

        assert isinstance(result, VerificationResult)
        assert result.is_approved is False
        assert result.overall_score == 1
        assert result.judge_ran is False
        assert "not approved" in result.summary.lower()

    def test_verify_rejects_synthesis_fallback(self):
        """Raw synthesis fallback must not be approved."""
        from src.chains.synthesizer import SYNTHESIS_FALLBACK_HEADING
        from src.agents.verifier import verify_synthesis
        sources = [
            ResearchSource(title="Paper A", url_or_id="http://a.com", content="Content A", source_type="arxiv"),
        ]
        synthesis = [
            SynthesisSection(heading=SYNTHESIS_FALLBACK_HEADING, content="excerpts", source_indices=[0]),
        ]
        result = verify_synthesis("test", sources, synthesis)
        assert result.is_approved is False
        assert result.judge_ran is False

    def test_approval_policy_overrides_llm_flag(self):
        from src.chains.verifier import apply_approval_policy

        inflated = VerificationResult(
            is_approved=True, overall_score=5, issues=[], summary="ok", judge_ran=True
        )
        assert apply_approval_policy(inflated).is_approved is False

        high_issue = VerificationResult(
            is_approved=True,
            overall_score=9,
            issues=[VerificationIssue(section_heading="A", issue="bad", severity="high")],
            summary="ok",
            judge_ran=True,
        )
        assert apply_approval_policy(high_issue).is_approved is False

        solid = VerificationResult(
            is_approved=False, overall_score=8, issues=[], summary="ok", judge_ran=True
        )
        assert apply_approval_policy(solid).is_approved is True


# ═══════════════════════════════════════════════════════════════
# Orchestrator Integration Tests (Facade)
# ═══════════════════════════════════════════════════════════════

class TestOrchestrator:
    """Integration tests for orchestrator delegating to LangGraph."""

    @patch("src.graphs.nodes.verify_synthesis")
    @patch("src.graphs.nodes.synthesize_sources")
    @patch("src.graphs.nodes.plan_research")
    @patch("src.graphs.nodes.search_web")
    @patch("src.graphs.nodes.search_arxiv")
    def test_run_research_full_pipeline(
        self, mock_arxiv, mock_web, mock_plan, mock_synth, mock_verify
    ):
        """run_research() should execute the LangGraph state machine."""
        from src.models.schemas import AcademicPaper, WebSearchResult

        mock_plan.return_value = QueryPlan(
            original_query="test",
            sub_queries=[
                SubQuery(question="sub q1", search_keywords=["kw1"], source_type="both"),
            ],
            reasoning="test plan",
        )

        mock_arxiv.return_value = [
            AcademicPaper(
                title="Test Paper", authors=["Author A"], summary="Abstract",
                published="2024-01-01", arxiv_id="2401.00001", pdf_url="http://pdf.com",
            )
        ]
        mock_web.return_value = [
            WebSearchResult(title="Web Article", url="http://web.com", snippet="Snippet")
        ]

        mock_synth.return_value = [
            SynthesisSection(heading="Findings", content="Summary text", source_indices=[0, 1]),
        ]

        mock_verify.return_value = VerificationResult(
            is_approved=True, overall_score=8, issues=[], summary="Good report."
        )

        from src.agents.orchestrator import run_research
        result = run_research("test", max_papers=2, max_web=2)

        assert isinstance(result, ResearchResult)
        assert result.query == "test"
        assert len(result.plan.sub_queries) == 1
        assert len(result.sources) > 0
        assert len(result.synthesis) == 1
        assert result.verification is not None
        assert result.verification.is_approved is True
        assert result.duration_seconds >= 0

    @patch("src.graphs.nodes.verify_synthesis")
    @patch("src.graphs.nodes.synthesize_sources")
    @patch("src.graphs.nodes.plan_research")
    @patch("src.graphs.nodes.search_web")
    @patch("src.graphs.nodes.search_arxiv")
    def test_run_research_handles_retrieval_errors(
        self, mock_arxiv, mock_web, mock_plan, mock_synth, mock_verify
    ):
        """run_research() should continue even if retrieval fails."""
        mock_plan.return_value = QueryPlan(
            original_query="test",
            sub_queries=[SubQuery(question="q", search_keywords=["k"], source_type="both")],
        )
        mock_arxiv.side_effect = Exception("Network error")
        mock_web.side_effect = Exception("Network error")
        mock_synth.return_value = [
            SynthesisSection(heading="No Data", content="No sources found", source_indices=[]),
        ]
        mock_verify.return_value = VerificationResult(
            is_approved=True, overall_score=5, issues=[], summary="Limited data."
        )

        from src.agents.orchestrator import run_research
        result = run_research("test")

        assert isinstance(result, ResearchResult)
        assert result.verification is not None
        assert result.duration_seconds >= 0


# ═══════════════════════════════════════════════════════════════
# Schema Tests
# ═══════════════════════════════════════════════════════════════

class TestPhase3Schemas:
    """Test the Phase 3 Pydantic models including LangChain SynthesisReport."""

    def test_subquery_defaults(self):
        sq = SubQuery(question="test?")
        assert sq.source_type == "both"
        assert sq.search_keywords == []

    def test_query_plan_creation(self):
        plan = QueryPlan(
            original_query="test",
            sub_queries=[SubQuery(question="q1"), SubQuery(question="q2")],
        )
        assert len(plan.sub_queries) == 2

    def test_synthesis_report_container(self):
        report = SynthesisReport(
            sections=[
                SynthesisSection(heading="Summary", content="Text", source_indices=[0])
            ]
        )
        assert len(report.sections) == 1
        assert report.sections[0].heading == "Summary"

    def test_research_result_serialization(self):
        result = ResearchResult(
            query="test",
            plan=QueryPlan(original_query="test"),
            sources=[],
            synthesis=[],
            duration_seconds=1.5,
        )
        data = result.model_dump()
        assert data["query"] == "test"
        assert data["duration_seconds"] == 1.5
        assert data["errors"] == []


    def test_verification_result_defaults_are_not_approved(self):
        result = VerificationResult()
        assert result.is_approved is False
        assert result.overall_score == 1
        assert result.judge_ran is True


# ═══════════════════════════════════════════════════════════════
# LangChain Tools Test
# ═══════════════════════════════════════════════════════════════

class TestLangChainTools:
    """Verify LangChain tool definitions."""

    def test_tools_registered(self):
        from src.tools import arxiv_search, web_search
        assert hasattr(arxiv_search, "invoke")
        assert hasattr(web_search, "invoke")
        assert arxiv_search.name == "arxiv_search"
        assert web_search.name == "web_search"


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
