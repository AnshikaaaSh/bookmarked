"""Character graph store — one NetworkX graph per book, persisted as JSON.

Every node and edge carries `introduced_at`: the chapter where the reader first
meets that character or learns that relationship. `view()` filters on it, so the
graph the UI renders is always bounded by reading position (FR9).

The merge is incremental by design (FR8): re-running extraction for a later
chapter adds to the existing graph rather than regenerating it, and an entity
keeps the *earliest* position it was seen at — a character introduced in
chapter 2 doesn't get pushed to chapter 9 because they reappear there.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

import networkx as nx

from ..config import GRAPH_DIR


@dataclass
class GraphNode:
    id: str
    label: str
    introduced_at: int
    main: bool = False


@dataclass
class GraphEdge:
    source: str
    target: str
    label: str
    introduced_at: int


class GraphStore:
    def __init__(self, directory: Path | None = None):
        self._dir = directory or GRAPH_DIR

    def _path(self, source_id: str) -> Path:
        return self._dir / f"{source_id}.json"

    def exists(self, source_id: str) -> bool:
        return self._path(source_id).exists()

    # --- Persistence -----------------------------------------------------

    def load(self, source_id: str) -> nx.Graph:
        graph = nx.Graph()
        path = self._path(source_id)
        if not path.exists():
            return graph

        raw = json.loads(path.read_text(encoding="utf-8"))
        for node in raw.get("nodes", []):
            graph.add_node(
                node["id"],
                label=node.get("label", node["id"]),
                introduced_at=int(node.get("introduced_at", 1)),
                main=bool(node.get("main", False)),
            )
        for edge in raw.get("edges", []):
            graph.add_edge(
                edge["source"],
                edge["target"],
                label=edge.get("label", ""),
                introduced_at=int(edge.get("introduced_at", 1)),
            )
        return graph

    def save(self, source_id: str, graph: nx.Graph) -> None:
        self._dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "nodes": [
                {"id": node_id, **{k: v for k, v in attrs.items()}}
                for node_id, attrs in graph.nodes(data=True)
            ],
            "edges": [
                {"source": u, "target": v, **{k: w for k, w in attrs.items()}}
                for u, v, attrs in graph.edges(data=True)
            ],
        }
        self._path(source_id).write_text(
            json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    # --- Incremental merge (used by extraction, build-order step 4) ------

    def merge(
        self,
        source_id: str,
        nodes: list[GraphNode],
        edges: list[GraphEdge],
    ) -> nx.Graph:
        """Fold newly extracted entities into the stored graph and persist it."""
        graph = self.load(source_id)

        for node in nodes:
            if graph.has_node(node.id):
                existing = graph.nodes[node.id]
                # Earliest introduction wins — never push a character later.
                existing["introduced_at"] = min(existing["introduced_at"], node.introduced_at)
                existing["main"] = existing["main"] or node.main
                if len(node.label) > len(existing["label"]):
                    existing["label"] = node.label  # prefer the fuller name
            else:
                graph.add_node(
                    node.id,
                    label=node.label,
                    introduced_at=node.introduced_at,
                    main=node.main,
                )

        for edge in edges:
            if not (graph.has_node(edge.source) and graph.has_node(edge.target)):
                continue  # a relationship can't precede both its endpoints
            if graph.has_edge(edge.source, edge.target):
                existing = graph.edges[edge.source, edge.target]
                existing["introduced_at"] = min(existing["introduced_at"], edge.introduced_at)
                if edge.label and edge.label not in existing["label"]:
                    existing["label"] = edge.label
            else:
                graph.add_edge(
                    edge.source,
                    edge.target,
                    label=edge.label,
                    introduced_at=edge.introduced_at,
                )

        self.save(source_id, graph)
        return graph

    # --- Reading ---------------------------------------------------------

    def view(self, source_id: str, position: int) -> dict:
        """The graph as of `position` — nothing introduced later is included."""
        graph = self.load(source_id)

        nodes = [
            {"id": node_id, **attrs}
            for node_id, attrs in graph.nodes(data=True)
            if attrs.get("introduced_at", 1) <= position
        ]
        visible = {node["id"] for node in nodes}
        edges = [
            {"source": u, "target": v, **attrs}
            for u, v, attrs in graph.edges(data=True)
            if attrs.get("introduced_at", 1) <= position and u in visible and v in visible
        ]

        max_position = max(
            [attrs.get("introduced_at", 1) for _, attrs in graph.nodes(data=True)] or [1]
        )
        return {
            "source_id": source_id,
            "position": position,
            "max_position": max_position,
            "nodes": sorted(nodes, key=lambda n: n["introduced_at"]),
            "edges": edges,
            "hidden": graph.number_of_nodes() - len(nodes),
        }


_graph_store: GraphStore | None = None


def get_graph_store() -> GraphStore:
    global _graph_store
    if _graph_store is None:
        _graph_store = GraphStore()
    return _graph_store
