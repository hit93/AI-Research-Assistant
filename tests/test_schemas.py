"""Tests for SynthesisSection schema backward compatibility and new figures field."""
from src.models.schemas import SynthesisSection


def test_synthesis_section_has_figures_field():
    section = SynthesisSection(heading="Test", content="Test content")
    assert hasattr(section, "figures")
    assert isinstance(section.figures, list)
    assert section.figures == []


def test_synthesis_section_accepts_figures():
    section = SynthesisSection(
        heading="Test",
        content="Test content",
        figures=["```mermaid\ngraph TD\n    A --> B\n```"],
    )
    assert len(section.figures) == 1
    assert "mermaid" in section.figures[0]


def test_synthesis_section_backward_compatible_without_figures():
    """Old cached dicts without figures key must deserialize cleanly."""
    old_dict = {"heading": "Old Section", "content": "Some text", "source_indices": [0, 1]}
    section = SynthesisSection(**old_dict)
    assert section.figures == []
    assert section.comparative_table is None


def test_comparative_table_schema():
    from src.models.schemas import ComparativeTable, TableRow
    table = ComparativeTable(
        headers=["Model", "Score"],
        rows=[TableRow(cells=["GPT-4", "92%"]), TableRow(cells=["Qwen-2.5", "88%"])],
        caption="Benchmark Results"
    )
    section = SynthesisSection(
        heading="Benchmarks",
        content="Overview of results.",
        comparative_table=table,
    )
    assert section.comparative_table is not None
    assert len(section.comparative_table.headers) == 2
    assert len(section.comparative_table.rows) == 2
    assert section.comparative_table.rows[0].cells[1] == "92%"

