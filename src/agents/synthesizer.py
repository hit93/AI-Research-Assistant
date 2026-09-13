"""
Synthesizer Adapter — Backward compatibility facade delegating to src.chains.synthesizer.
"""

from src.prompts.synthesizer import SYNTHESIZER_SYSTEM_PROMPT
from src.chains.synthesizer import synthesize_sources, get_synthesizer_chain

__all__ = [
    "SYNTHESIZER_SYSTEM_PROMPT",
    "synthesize_sources",
    "get_synthesizer_chain",
]
