"""Tests for Multi-Format Report Exporter (Markdown, PDF, JSON)."""

import json
from pathlib import Path

import pytest
from src.models.schemas import (
    QueryPlan,
    ResearchResult,
    ResearchSource,
    SubQuery,
    SynthesisSection,
    VerificationIssue,
    VerificationResult,
)
from src.utils.exporter import (
    export_to_json,
    export_to_markdown,
    export_to_pdf,
    save_report,
)


@pytest.fixture
def sample_research_result() -> ResearchResult:
    return ResearchResult(
        query="Multi-Agent Systems in Healthcare",
        plan=QueryPlan(
            original_query="Multi-Agent Systems in Healthcare",
            reasoning="Deconstruct healthcare into clinical diagnostics and hospital operations.",
            sub_queries=[
                SubQuery(
                    question="How are multi-agent systems used in clinical diagnostics?",
                    search_keywords=["multi-agent", "clinical", "diagnostics"],
                    source_type="arxiv",
                ),
                SubQuery(
                    question="What are recent benchmarks for agentic hospital operations?",
                    search_keywords=["agentic", "hospital", "operations", "benchmarks"],
                    source_type="web",
                ),
            ],
        ),
        sources=[
            ResearchSource(
                title="AgentHospital: A Simulated Hospital with Collaborative Agents",
                url_or_id="https://arxiv.org/abs/2405.02957",
                content="AgentHospital is an interactive simulation environment where agents simulate medical tasks.",
                source_type="arxiv",
                authors=["Z. Fan", "J. Chen", "K. Naik"],
                published="2024-05-01",
            ),
            ResearchSource(
                title="AI Agents in Clinical Practice 2026",
                url_or_id="https://example.com/clinical-agents",
                content="Clinical practitioners are reporting high diagnostic triage throughput with agent teams.",
                source_type="web",
                authors=[],
                published="2026-01-15",
            ),
        ],
        synthesis=[
            SynthesisSection(
                heading="1. Executive Summary & Clinical Impact",
                content="Multi-agent systems provide substantial gains in diagnostic accuracy and automated workflow triage.",
                source_indices=[0, 1],
            ),
            SynthesisSection(
                heading="2. Simulation & Benchmark Platforms",
                content="Platforms such as AgentHospital allow risk-free sandbox training of doctor and patient agents.",
                source_indices=[0],
            ),
        ],
        verification=VerificationResult(
            is_approved=True,
            overall_score=9,
            issues=[
                VerificationIssue(
                    section_heading="1. Executive Summary & Clinical Impact",
                    issue="Consider clarifying potential HIPAA regulatory requirements.",
                    severity="low",
                    suggestion="Add a note on data privacy laws.",
                )
            ],
            summary="Strong, well-structured synthesis backed by primary arXiv and web evidence.",
        ),
        duration_seconds=3.42,
    )


def test_export_to_markdown(sample_research_result: ResearchResult):
    md = export_to_markdown(sample_research_result)
    assert isinstance(md, str)
    assert "# 🔬 Research Report: Multi-Agent Systems in Healthcare" in md
    assert "AgentHospital" in md
    assert "Score: 9/10" in md
    assert "1. Executive Summary & Clinical Impact" in md
    assert "Consider clarifying potential HIPAA regulatory requirements" in md
    assert "https://arxiv.org/abs/2405.02957" in md


def test_export_to_json(sample_research_result: ResearchResult):
    json_str = export_to_json(sample_research_result)
    assert isinstance(json_str, str)
    data = json.loads(json_str)
    assert data["query"] == "Multi-Agent Systems in Healthcare"
    assert len(data["sources"]) == 2
    assert len(data["synthesis"]) == 2
    assert data["verification"]["overall_score"] == 9


def test_export_to_pdf_bytes(sample_research_result: ResearchResult):
    pdf_bytes = export_to_pdf(sample_research_result)
    assert isinstance(pdf_bytes, bytes)
    assert len(pdf_bytes) > 0
    # Standard PDF header check
    assert pdf_bytes.startswith(b"%PDF-")


def test_export_to_pdf_file(sample_research_result: ResearchResult, tmp_path: Path):
    target_file = tmp_path / "custom_report.pdf"
    pdf_bytes = export_to_pdf(sample_research_result, output_path=target_file)
    assert target_file.exists()
    assert target_file.stat().st_size == len(pdf_bytes)
    assert pdf_bytes.startswith(b"%PDF-")


def test_save_report(sample_research_result: ResearchResult, tmp_path: Path):
    saved = save_report(
        sample_research_result,
        output_dir=tmp_path / "reports",
        formats=["md", "pdf", "json"],
    )
    assert "md" in saved
    assert "pdf" in saved
    assert "json" in saved

    assert saved["md"].exists()
    assert saved["md"].suffix == ".md"
    assert "Research Report" in saved["md"].read_text(encoding="utf-8")

    assert saved["pdf"].exists()
    assert saved["pdf"].suffix == ".pdf"
    assert saved["pdf"].read_bytes().startswith(b"%PDF-")

    assert saved["json"].exists()
    assert saved["json"].suffix == ".json"
    data = json.loads(saved["json"].read_text(encoding="utf-8"))
    assert data["query"] == "Multi-Agent Systems in Healthcare"
