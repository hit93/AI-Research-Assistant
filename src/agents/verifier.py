"""
Verifier Adapter — Backward compatibility facade delegating to src.chains.verifier.
"""

from src.prompts.verifier import VERIFIER_SYSTEM_PROMPT
from src.chains.verifier import verify_synthesis, get_verifier_chain

__all__ = [
    "VERIFIER_SYSTEM_PROMPT",
    "verify_synthesis",
    "get_verifier_chain",
]
