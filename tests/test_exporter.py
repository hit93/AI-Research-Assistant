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

