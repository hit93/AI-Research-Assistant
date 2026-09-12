import sys
import argparse
from src.agents.graph_builder import GraphBuilder, CompiledGraph
from src.agents.nodes import planner_node, research_node, synthesizer_node
from src.agents.state import ResearchState
from src.utils.logger import get_logger

logger = get_logger("orchestrator")

def create_research_graph() -> CompiledGraph:
    """Build and compile the multi-agent research workflow graph."""
    builder = GraphBuilder()
    
    # 1. Register Nodes
    builder.add_node("planner", planner_node)
    builder.add_node("researcher", research_node)
    builder.add_node("synthesizer", synthesizer_node)

    # 2. Define Flow Edges
    builder.set_entry_point("planner")
    builder.add_edge("planner", "researcher")
    builder.add_edge("researcher", "synthesizer")
    builder.set_finish_point("synthesizer")

    return builder.compile()

def run_research(topic: str) -> dict:
    """Execute the end-to-end research graph for a given topic."""
    graph = create_research_graph()
    initial_state: ResearchState = {
        "topic": topic,
        "sub_questions": [],
        "sources": [],
        "report": "",
        "errors": [],
    }
    return graph.invoke(initial_state)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run autonomous AI Research Assistant")
    parser.add_argument("--topic", type="str", default="Graph Neural Networks in Drug Discovery", help="Research topic")
    args = parser.parse_args()

    print(f"\n🚀 Starting AI Research Graph for topic: '{args.topic}'\n")
    result = run_research(args.topic)

    print("\n" + "="*70)
    print(f"📋 FINAL SYNTHESIZED RESEARCH REPORT ({len(result.get('sources', []))} sources analyzed)")
    print("="*70 + "\n")
    print(result.get("report", "No report generated."))
