from typing import Callable, Any
from src.utils.logger import get_logger

logger = get_logger("graph_builder")

class CompiledGraph:
    """An executable state graph workflow."""
    def __init__(self, nodes: dict[str, Callable], edges: dict[str, str], entry_point: str, finish_point: str):
        self.nodes = nodes
        self.edges = edges
        self.entry_point = entry_point
        self.finish_point = finish_point

    def invoke(self, initial_state: dict[str, Any]) -> dict[str, Any]:
        """Execute nodes sequentially according to edges."""
        current_node_name = self.entry_point
        state = dict(initial_state)

        while current_node_name:
            logger.info(f"Executing Graph Node: [{current_node_name}]")
            node_fn = self.nodes.get(current_node_name)
            if not node_fn:
                raise ValueError(f"Node '{current_node_name}' not found in compiled graph.")

            # Run the node
            update = node_fn(state)
            if isinstance(update, dict):
                state.update(update)

            # Check if finished
            if current_node_name == self.finish_point:
                break

            # Move to next node along edge
            current_node_name = self.edges.get(current_node_name)

        logger.info("Graph execution completed successfully.")
        return state

class GraphBuilder:
    """Minimal, flexible state graph builder."""
    def __init__(self):
        self.nodes: dict[str, Callable] = {}
        self.edges: dict[str, str] = {}
        self.entry_point: str | None = None
        self.finish_point: str | None = None

    def add_node(self, name: str, func: Callable) -> "GraphBuilder":
        self.nodes[name] = func
        return self

    def add_edge(self, from_node: str, to_node: str) -> "GraphBuilder":
        self.edges[from_node] = to_node
        return self

    def set_entry_point(self, name: str) -> "GraphBuilder":
        self.entry_point = name
        return self

    def set_finish_point(self, name: str) -> "GraphBuilder":
        self.finish_point = name
        return self

    def compile(self) -> CompiledGraph:
        if not self.entry_point or self.entry_point not in self.nodes:
            raise ValueError("Invalid entry point for GraphBuilder.")
        return CompiledGraph(
            nodes=self.nodes,
            edges=self.edges,
            entry_point=self.entry_point,
            finish_point=self.finish_point or "",
        )
