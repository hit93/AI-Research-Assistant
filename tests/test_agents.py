from src.agents.graph_builder import GraphBuilder
from src.agents.nodes import planner_node
from src.agents.orchestrator import create_research_graph

def test_graph_builder_mechanics():
    builder = GraphBuilder()
    builder.add_node("step1", lambda s: {"count": s.get("count", 0) + 1})
    builder.add_node("step2", lambda s: {"count": s.get("count", 0) * 2})
    builder.set_entry_point("step1")
    builder.add_edge("step1", "step2")
    builder.set_finish_point("step2")

    graph = builder.compile()
    result = graph.invoke({"count": 2})
    # step1: 2 + 1 = 3 -> step2: 3 * 2 = 6
    assert result["count"] == 6

def test_planner_node():
    state = {"topic": "Autonomous Driving Safety"}
    output = planner_node(state)
    assert "sub_questions" in output
    assert len(output["sub_questions"]) >= 1

def test_research_graph_compilation():
    graph = create_research_graph()
    assert graph.entry_point == "planner"
    assert graph.finish_point == "synthesizer"
    assert "researcher" in graph.nodes

if __name__ == "__main__":
    test_graph_builder_mechanics()
    test_planner_node()
    test_research_graph_compilation()
    print("All Graph Builder and Agent tests passed successfully!")
