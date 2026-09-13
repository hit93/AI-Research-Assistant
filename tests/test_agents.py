"""
Tests for Phase 3: LLM Client, Planner, Synthesizer, and Orchestrator.

Uses unittest.mock to patch the Groq API calls so tests run without
a live API key and without hitting rate limits.
"""

import json
from unittest.mock import patch, MagicMock

from src.models.schemas import (
    SubQuery,
    QueryPlan,
    SynthesisSection,
    ResearchSource,
    ResearchResult,
)


# ═══════════════════════════════════════════════════════════════
# LLM Client Tests
# ═══════════════════════════════════════════════════════════════

class TestLLMClient:
    """Tests for the LLM client wrapper."""

    @patch("src.agents.llm_client._get_client")
    def test_call_llm_returns_text(self, mock_get_client):
        """call_llm() should return the model's text response."""
        # Mock the Groq client response
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Hello from LLM"
        mock_get_client.return_value.chat.completions.create.return_value = mock_response

        from src.agents.llm_client import call_llm
        result = call_llm("system", "user")
        assert result == "Hello from LLM"

    @patch("src.agents.llm_client._get_client")
    def test_call_llm_json_parses_response(self, mock_get_client):
        """call_llm_json() should parse valid JSON from the LLM."""
        json_response = json.dumps({"key": "value", "items": [1, 2, 3]})
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = json_response
        mock_get_client.return_value.chat.completions.create.return_value = mock_response

        from src.agents.llm_client import call_llm_json
        result = call_llm_json("system", "user")
        assert result == {"key": "value", "items": [1, 2, 3]}

    @patch("src.agents.llm_client._get_client")
    def test_call_llm_json_strips_code_fences(self, mock_get_client):
        """call_llm_json() should handle ```json ... ``` wrapper."""
        wrapped = '```json\n{"result": true}\n```'
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = wrapped
        mock_get_client.return_value.chat.completions.create.return_value = mock_response

        from src.agents.llm_client import call_llm_json
        result = call_llm_json("system", "user")
        assert result == {"result": True}

    @patch("src.agents.llm_client._get_client")
    def test_call_llm_json_raises_on_invalid(self, mock_get_client):
        """call_llm_json() should raise ValueError on invalid JSON."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "not valid json at all"
        mock_get_client.return_value.chat.completions.create.return_value = mock_response

        from src.agents.llm_client import call_llm_json
        try:
            call_llm_json("system", "user")
            assert False, "Should have raised ValueError"
        except ValueError:
            pass


# ═══════════════════════════════════════════════════════════════
# Planner Tests
# ═══════════════════════════════════════════════════════════════

class TestPlanner:
    """Tests for the Planner agent."""

    @patch("src.agents.planner.call_llm_json")
    def test_plan_research_parses_subqueries(self, mock_llm):
        """plan_research() should return a QueryPlan with parsed sub-queries."""
        mock_llm.return_value = {
            "reasoning": "Test decomposition",
            "sub_queries": [
                {
                    "question": "What is quantum computing?",
                    "search_keywords": ["quantum computing basics"],
                    "source_type": "both",
                },
                {
                    "question": "Drug discovery applications?",
                    "search_keywords": ["quantum drug discovery"],
                    "source_type": "arxiv",
                },
            ],
        }

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

    @patch("src.agents.planner.call_llm_json")
    def test_plan_research_fallback_on_error(self, mock_llm):
        """plan_research() should fallback to direct query on LLM error."""
        mock_llm.side_effect = ValueError("Bad JSON")

        from src.agents.planner import plan_research
        plan = plan_research("test topic")

        assert len(plan.sub_queries) == 1
        assert plan.sub_queries[0].question == "test topic"
        assert "Fallback" in plan.reasoning


# ═══════════════════════════════════════════════════════════════
# Synthesizer Tests
# ═══════════════════════════════════════════════════════════════

class TestSynthesizer:
    """Tests for the Synthesizer agent."""

    @patch("src.agents.synthesizer.call_llm_json")
    def test_synthesize_returns_sections(self, mock_llm):
        """synthesize_sources() should return structured SynthesisSection list."""
        mock_llm.return_value = {
            "sections": [
                {
                    "heading": "Key Findings",
                    "content": "Source [0] shows X. Source [1] confirms Y.",
                    "source_indices": [0, 1],
                },
                {
                    "heading": "Research Gaps",
                    "content": "No sources address Z.",
                    "source_indices": [],
                },
            ],
        }

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

    @patch("src.agents.synthesizer.call_llm_json")
    def test_synthesize_fallback_on_error(self, mock_llm):
        """synthesize_sources() should return raw summary on LLM error."""
        mock_llm.side_effect = ValueError("Bad JSON")

        sources = [
            ResearchSource(title="Paper A", url_or_id="http://a.com", content="Content A", source_type="arxiv"),
        ]

        from src.agents.synthesizer import synthesize_sources
        sections = synthesize_sources("test", sources)

        assert len(sections) == 1
        assert "Failed" in sections[0].heading


# ═══════════════════════════════════════════════════════════════
# Orchestrator Integration Tests
# ═══════════════════════════════════════════════════════════════

class TestOrchestrator:
    """Integration tests for the full pipeline (with mocked LLM)."""

    @patch("src.agents.orchestrator.synthesize_sources")
    @patch("src.agents.orchestrator.plan_research")
    @patch("src.agents.orchestrator.search_web")
    @patch("src.agents.orchestrator.search_arxiv")
    def test_run_research_full_pipeline(
        self, mock_arxiv, mock_web, mock_plan, mock_synth
    ):
        """run_research() should chain plan → retrieve → synthesize."""
        from src.models.schemas import AcademicPaper, WebSearchResult

        # Mock planner
        mock_plan.return_value = QueryPlan(
            original_query="test",
            sub_queries=[
                SubQuery(question="sub q1", search_keywords=["kw1"], source_type="both"),
            ],
            reasoning="test plan",
        )

        # Mock retrieval tools
        mock_arxiv.return_value = [
            AcademicPaper(
                title="Test Paper", authors=["Author A"], summary="Abstract",
                published="2024-01-01", arxiv_id="2401.00001", pdf_url="http://pdf.com",
            )
        ]
        mock_web.return_value = [
            WebSearchResult(title="Web Article", url="http://web.com", snippet="Snippet")
        ]

        # Mock synthesizer
        mock_synth.return_value = [
            SynthesisSection(heading="Findings", content="Summary text", source_indices=[0, 1]),
        ]

        from src.agents.orchestrator import run_research
        result = run_research("test", max_papers=2, max_web=2)

        assert isinstance(result, ResearchResult)
        assert result.query == "test"
        assert len(result.plan.sub_queries) == 1
        assert len(result.sources) > 0
        assert len(result.synthesis) == 1
        assert result.duration_seconds >= 0  # mocked calls may complete in 0ms

    @patch("src.agents.orchestrator.synthesize_sources")
    @patch("src.agents.orchestrator.plan_research")
    @patch("src.agents.orchestrator.search_web")
    @patch("src.agents.orchestrator.search_arxiv")
    def test_run_research_handles_retrieval_errors(
        self, mock_arxiv, mock_web, mock_plan, mock_synth
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

        from src.agents.orchestrator import run_research
        result = run_research("test")

        # Should complete without crashing
        assert isinstance(result, ResearchResult)
        assert result.duration_seconds >= 0  # mocked calls may complete in 0ms


# ═══════════════════════════════════════════════════════════════
# Schema Tests
# ═══════════════════════════════════════════════════════════════

class TestPhase3Schemas:
    """Test the new Phase 3 Pydantic models."""

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


# ═══════════════════════════════════════════════════════════════
# CLI Runner (for manual execution)
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
