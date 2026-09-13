"""
Orchestrator Adapter — Backward compatibility facade delegating to src.graphs.graph.
"""

from src.graphs.graph import run_research, build_research_graph, research_graph

__all__ = [
    "run_research",
    "build_research_graph",
    "research_graph",
]
