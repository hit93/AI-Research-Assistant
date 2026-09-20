"""Tests for prompt structural guarantees -- no LLM calls."""
from src.prompts.planner import PLANNER_SYSTEM_PROMPT
from src.prompts.synthesizer import SYNTHESIZER_SYSTEM_PROMPT
from src.prompts.verifier import VERIFIER_SYSTEM_PROMPT
from src.prompts.refiner import REFINER_SYSTEM_PROMPT


def test_planner_prompt_targets_5_to_7_subqueries():
    assert "5-7" in PLANNER_SYSTEM_PROMPT

def test_planner_prompt_requires_benchmark_subquery():
    assert "benchmark" in PLANNER_SYSTEM_PROMPT.lower() or "empirical" in PLANNER_SYSTEM_PROMPT.lower()

def test_planner_prompt_requires_application_subquery():
    assert "deployment" in PLANNER_SYSTEM_PROMPT.lower() or "application" in PLANNER_SYSTEM_PROMPT.lower()

def test_synthesizer_requires_abstract_section():
    assert "Abstract" in SYNTHESIZER_SYSTEM_PROMPT

def test_synthesizer_requires_mermaid_diagram():
    assert "mermaid" in SYNTHESIZER_SYSTEM_PROMPT.lower() or "Mermaid" in SYNTHESIZER_SYSTEM_PROMPT

def test_synthesizer_requires_numbered_subsections():
    assert "subsection" in SYNTHESIZER_SYSTEM_PROMPT.lower() or "N.M" in SYNTHESIZER_SYSTEM_PROMPT

def test_synthesizer_requires_300_word_minimum():
    assert "300" in SYNTHESIZER_SYSTEM_PROMPT

def test_synthesizer_mandates_comparison_table():
    assert "comparison table" in SYNTHESIZER_SYSTEM_PROMPT.lower() or "Comparative" in SYNTHESIZER_SYSTEM_PROMPT

def test_verifier_penalizes_missing_figures():
    assert "figure" in VERIFIER_SYSTEM_PROMPT.lower() or "mermaid" in VERIFIER_SYSTEM_PROMPT.lower()

def test_verifier_penalizes_missing_abstract():
    assert "Abstract" in VERIFIER_SYSTEM_PROMPT

def test_verifier_penalizes_missing_subsections():
    assert "subsection" in VERIFIER_SYSTEM_PROMPT.lower() or "N.M" in VERIFIER_SYSTEM_PROMPT

def test_refiner_preserves_section_order():
    assert "section order" in REFINER_SYSTEM_PROMPT.lower() or "numbered subsection" in REFINER_SYSTEM_PROMPT.lower()

def test_refiner_preserves_figures():
    assert "mermaid" in REFINER_SYSTEM_PROMPT.lower() or "figure" in REFINER_SYSTEM_PROMPT.lower()
