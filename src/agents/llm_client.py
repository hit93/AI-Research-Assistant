"""
LLM Client Adapter — Backward compatibility facade delegating to src.chains.llm.
"""

from src.chains.llm import get_chat_llm, call_llm, call_llm_json

__all__ = [
    "get_chat_llm",
    "call_llm",
    "call_llm_json",
]
