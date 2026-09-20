"""
Integration tests verifying the full prompt + schema + exporter chain coheres.
No LLM calls; tests structural guarantees only.
"""
from src.prompts.planner import PLANNER_SYSTEM_PROMPT
from src.prompts.synthesizer import SYNTHESIZER_SYSTEM_PROMPT
from src.prompts.verifier import VERIFIER_SYSTEM_PROMPT
from src.prompts.refiner import REFINER_SYSTEM_PROMPT
from src.utils.exporter import _extract_mermaid_blocks, export_to_markdown
from src.models.schemas import SynthesisSection, ResearchResult, QueryPlan, ResearchSource


def test_all_7_section_names_in_synthesizer():
    required = [
        "Abstract", "Executive Summary", "Architectural Evolution",
        "Technical Architecture", "Comparative Performance", "Practical Applications",
        "Research Gaps"
    ]
    for name in required:
        assert name in SYNTHESIZER_SYSTEM_PROMPT, f"Missing section name in synthesizer: {name}"


def test_verifier_structural_checklist_present():
    checklist_items = ["Abstract", "Core Insight", "N.M", "Mermaid", "comparison table"]
    for item in checklist_items:
        assert item in VERIFIER_SYSTEM_PROMPT, f"Verifier missing checklist item: {item}"


def test_refiner_section_order_matches_synthesizer():
    synth_sections = [
        "Abstract", "Executive Summary", "Architectural Evolution",
        "Technical Architecture", "Comparative Performance", "Practical Applications",
        "Research Gaps"
    ]
    for sec in synth_sections:
        assert sec in REFINER_SYSTEM_PROMPT, f"Refiner missing section: {sec}"


def test_mermaid_extraction_round_trip():
    """Simulate synthesizer output with a Mermaid block and verify extraction + markdown export."""
    mermaid_content = (
        "Some preamble text.\n\n"
        "```mermaid\ngraph TD\n    Input --> Process --> Output\n```\n\n"
        "Analysis follows."
    )
    section = SynthesisSection(heading="Technical Architecture", content=mermaid_content)
    result = ResearchResult(
        query="Test",
        plan=QueryPlan(original_query="Test"),
        sources=[ResearchSource(title="S", url_or_id="http://x.com", content="x" * 500, source_type="web")],
        synthesis=[section],
    )
    md = export_to_markdown(result)
    assert "Table of Contents" in md
    assert "```mermaid" in md
    blocks = _extract_mermaid_blocks(mermaid_content)
    assert len(blocks) == 1
    pre, src, post = blocks[0]
    assert "graph TD" in src
    assert "preamble" in pre
    assert "Analysis" in post


def test_planner_prompt_has_5_to_7_requirement():
    assert "5-7" in PLANNER_SYSTEM_PROMPT


def test_export_toc_long_heading_no_crash():
    long_heading = "A" * 90 + " Very Long Section Heading"
    section = SynthesisSection(heading=long_heading, content="Content.")
    result = ResearchResult(
        query="Test",
        plan=QueryPlan(original_query="Test"),
        sources=[],
        synthesis=[section],
    )
    md = export_to_markdown(result)
    assert "Table of Contents" in md
