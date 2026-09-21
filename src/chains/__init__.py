"""
Chains Package — Composable LCEL chains for planning, synthesis, and verification.
"""

from .llm import get_chat_llm, call_llm, call_llm_json
from .gateway import LLMGateway, CircuitBreaker, gateway, run_structured
from .planner import get_planner_chain, plan_research
from .synthesizer import get_synthesizer_chain, synthesize_sources
from .verifier import get_verifier_chain, verify_synthesis, apply_approval_policy
from .refiner import get_refiner_chain, refine_synthesis

__all__ = [
    "get_chat_llm",
    "call_llm",
    "call_llm_json",
    "LLMGateway",
    "CircuitBreaker",
    "gateway",
    "run_structured",
    "get_planner_chain",
    "plan_research",
    "get_synthesizer_chain",
    "synthesize_sources",
    "get_verifier_chain",
    "verify_synthesis",
    "apply_approval_policy",
    "get_refiner_chain",
    "refine_synthesis",
]

