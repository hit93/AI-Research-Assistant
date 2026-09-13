"""
Tests for LangGraph Workflow: StateGraph, Nodes, and Streaming Graph Execution.
"""

from unittest.mock import patch, MagicMock
from src.graphs import build_research_graph, research_graph, run_research
from src.graphs.nodes import plan_node, retrieve_node, synthesize_node
from src.models.schemas import (
    QueryPlan,
    SubQuery,
    ResearchSource,
    SynthesisSection,
    AcademicPaper,
    WebSearchResult,
    ResearchResult,
)


class TestResearchGraph:
    """Verify LangGraph StateGraph topology and compilation."""

    def test_graph_has_expected_nodes(self):
        """StateGraph should contain planner, retriever, and synthesizer nodes."""
        graph = build_research_graph()
        nodes = graph.nodes
        assert "planner" in nodes
        assert "retriever" in nodes
        assert "synthesizer" in nodes

    def test_compiled_graph_is_runnable(self):
        """Compiled research_graph should have stream and invoke methods."""
        assert hasattr(research_graph, "stream")
        assert hasattr(research_graph, "invoke")


class TestGraphNodes:
    """Unit tests for individual LangGraph functional nodes."""

    @patch("src.graphs.nodes.plan_research")
    def test_plan_node(self, mock_plan):
        mock_plan.return_value = QueryPlan(
            original_query="Quantum AI",
            sub_queries=[SubQuery(question="Q1", search_keywords=["kw"])],
        )

        state = {"query": "Quantum AI"}
        result = plan_node(state)

        assert "plan" in result
        assert result["status"] == "planned"
        assert len(result["plan"].sub_queries) == 1

    @patch("src.graphs.nodes.search_web")
    @patch("src.graphs.nodes.search_arxiv")
    def test_retrieve_node(self, mock_arxiv, mock_web):
        mock_arxiv.return_value = [
            AcademicPaper(
                title="Paper A", authors=["Author 1"], summary="Summary",
                published="2026-01-01", arxiv_id="123", pdf_url="http://pdf.com",
            )
        ]
        mock_web.return_value = [
            WebSearchResult(title="Article B", url="http://b.com", snippet="Snippet")
        ]

        state = {
            "query": "Quantum AI",
            "plan": QueryPlan(
                original_query="Quantum AI",
                sub_queries=[SubQuery(question="Q1", search_keywords=["quantum"], source_type="both")],
            ),
            "max_papers": 1,
            "max_web": 1,
        }

        result = retrieve_node(state)

        assert "sources" in result
        assert len(result["sources"]) == 2
        assert result["status"] == "retrieved"

    @patch("src.graphs.nodes.synthesize_sources")
    def test_synthesize_node(self, mock_synth):
        mock_synth.return_value = [
            SynthesisSection(heading="Key Findings", content="Text", source_indices=[0])
        ]

        state = {
            "query": "Quantum AI",
            "sources": [
                ResearchSource(title="Paper", url_or_id="1", content="Text", source_type="arxiv")
            ],
        }

        result = synthesize_node(state)

        assert "synthesis" in result
        assert len(result["synthesis"]) == 1
        assert result["status"] == "synthesized"


class TestGraphExecution:
    """Test full LangGraph execution using run_research."""

    @patch("src.graphs.nodes.synthesize_sources")
    @patch("src.graphs.nodes.search_web")
    @patch("src.graphs.nodes.search_arxiv")
    @patch("src.graphs.nodes.plan_research")
    def test_run_research_via_langgraph(
        self, mock_plan, mock_arxiv, mock_web, mock_synth
    ):
        mock_plan.return_value = QueryPlan(
            original_query="Test Topic",
            sub_queries=[SubQuery(question="Sub Q", search_keywords=["kw"], source_type="both")],
        )
        mock_arxiv.return_value = [
            AcademicPaper(
                title="P1", authors=["A1"], summary="Sum",
                published="2026", arxiv_id="1", pdf_url="http://p.com",
            )
        ]
        mock_web.return_value = []
        mock_synth.return_value = [
            SynthesisSection(heading="Findings", content="Content", source_indices=[0])
        ]

        events = []
        def on_progress(status, detail):
            events.append(status)

        result = run_research("Test Topic", max_papers=1, max_web=1, on_progress=on_progress)

        assert isinstance(result, ResearchResult)
        assert result.query == "Test Topic"
        assert len(result.sources) == 1
        assert len(result.synthesis) == 1
        assert "planning" in events
        assert "planned" in events
        assert "retrieved" in events
        assert "synthesized" in events
        assert "complete" in events
