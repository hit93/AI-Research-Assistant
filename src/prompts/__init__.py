"""
Prompts Package — Modular, versionable prompt templates.
"""

from .planner import PLANNER_SYSTEM_PROMPT, planner_prompt
from .synthesizer import SYNTHESIZER_SYSTEM_PROMPT, synthesizer_prompt

__all__ = [
    "PLANNER_SYSTEM_PROMPT",
    "planner_prompt",
    "SYNTHESIZER_SYSTEM_PROMPT",
    "synthesizer_prompt",
]
