"""
Planner Adapter — Backward compatibility facade delegating to src.chains.planner.
"""

from src.prompts.planner import PLANNER_SYSTEM_PROMPT
from src.chains.planner import plan_research, get_planner_chain

__all__ = [
    "PLANNER_SYSTEM_PROMPT",
    "plan_research",
    "get_planner_chain",
]
