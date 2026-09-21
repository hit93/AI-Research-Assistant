"""Tests for exporter TOC generation, Mermaid block extraction, and extended excerpts."""
import pytest
from src.utils.exporter import export_to_markdown, _extract_mermaid_blocks
from src.models.schemas import (
    ResearchResult, QueryPlan, SynthesisSection, ResearchSource,
)


def _make_result(sections=None):
    if sections is None:
        sections = [
            SynthesisSection(heading="Abstract", content="This is the abstract."),
            SynthesisSection(
                heading="Technical Architecture",
                content="Some text.\n\n```mermaid\ngraph TD\n    A --> B\n```\n\nMore text.",
            ),
        ]
    return ResearchResult(
        query="Test Query",
        plan=QueryPlan(original_query="Test Query", sub_queries=[]),
        sources=[
            ResearchSource(
                title="Paper One", url_or_id="https://arxiv.org/abs/1234",
                content="Content of paper one " * 60, source_type="arxiv",
            )
        ],
        synthesis=sections,
    )


def test_markdown_export_contains_toc():
    result = _make_result()
    md = export_to_markdown(result)
    assert "Table of Contents" in md


def test_markdown_toc_contains_section_headings():
    result = _make_result()
    md = export_to_markdown(result)
    assert "Abstract" in md
    assert "Technical Architecture" in md


def test_markdown_mermaid_blocks_preserved():
    result = _make_result()
    md = export_to_markdown(result)
    assert "```mermaid" in md


def test_markdown_source_excerpt_extended():
    """Source excerpt in markdown must exceed 280 chars when content is long enough."""
    result = _make_result()
    md = export_to_markdown(result)
    # Content is 60 * "Content of paper one " = 1260 chars; excerpt must exceed 280
    lines = md.split("\n")
    excerpt_lines = [l for l in lines if l.startswith("> ") and "Content of paper" in l]
    assert any(len(l) > 300 for l in excerpt_lines)


def test_extract_mermaid_blocks_basic():
    text = "Before.\n\n```mermaid\ngraph TD\n    A --> B\n```\n\nAfter."
    blocks = _extract_mermaid_blocks(text)
    assert len(blocks) == 1
    pre, src, post = blocks[0]
    assert "Before" in pre
    assert "graph TD" in src
    assert "After" in post


def test_extract_mermaid_blocks_no_mermaid():
    text = "No diagrams here."
    blocks = _extract_mermaid_blocks(text)
    assert blocks == []


def test_extract_mermaid_blocks_multiple():
    text = "```mermaid\ngraph A\n```\n\nMiddle\n\n```mermaid\ngraph B\n```"
    blocks = _extract_mermaid_blocks(text)
    assert len(blocks) == 2


def test_markdown_toc_single_section_no_crash():
    """TOC must not crash on a single-section report."""
    result = _make_result(sections=[
        SynthesisSection(heading="Raw Source Summary (Synthesis Fallback)", content="Fallback.")
    ])
    md = export_to_markdown(result)
    assert "Table of Contents" in md


def test_html_export_renders_mermaid_and_citations(tmp_path):
    from src.utils.html_exporter import export_to_html
    from src.models.schemas import ComparativeTable, TableRow

    table = ComparativeTable(
        headers=["System", "Accuracy"],
        rows=[TableRow(cells=["Model A", "95%"])],
        caption="Empirical Results"
    )
    sections = [
        SynthesisSection(
            heading="Methodology",
            content="We base our model on Transformer architectures [0].\n\n```mermaid\ngraph LR\n   In --> Out\n```",
            source_indices=[0],
            comparative_table=table,
        )
    ]
    result = _make_result(sections=sections)
    out_file = tmp_path / "test_report.html"
    html_content = export_to_html(result, output_path=out_file)

    assert "<!DOCTYPE html>" in html_content
    assert "mermaid" in html_content
    assert 'href="#ref-0"' in html_content
    assert "Model A" in html_content
    assert "Empirical Results" in html_content
    assert out_file.exists()


def test_audit_citations_detects_out_of_bounds():
    from src.chains.verifier import audit_citations
    sources = [ResearchSource(title="Paper 0", url_or_id="p0", content="c0", source_type="arxiv")]
    synthesis = [
        SynthesisSection(heading="Test", content="Valid [0] and invalid [5].", source_indices=[0])
    ]
    issues = audit_citations(synthesis, sources)
    assert len(issues) >= 1
    assert any("out of bounds" in issue.issue and "[5]" in issue.issue for issue in issues)


