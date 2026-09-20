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
