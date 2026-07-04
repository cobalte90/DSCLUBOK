from __future__ import annotations

import sys
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.graph_query import validate_graph_payload  # noqa: E402
from app.main import create_app  # noqa: E402

client = TestClient(create_app())

VALID_NODE_TYPES = {
    "Query", "Material", "Process", "Equipment", "Parameter", "Condition", "Result",
    "Publication", "SourceFragment", "Claim", "Gap", "Contradiction", "Unknown",
}
VALID_EDGE_TYPES = {"related", "evidence", "parameter", "contradiction", "gap", "source"}


def graph_for(query: str, **extra) -> dict:
    response = client.post("/api/graph/query", json={"query": query, **extra})
    assert response.status_code == 200
    body = response.json()
    return body.get("data", body)


def assert_valid_graph(payload: dict) -> None:
    assert payload["graph_mode"] in {"real", "hybrid", "fallback"}
    node_ids = [node["id"] for node in payload["nodes"]]
    assert node_ids
    assert len(node_ids) == len(set(node_ids))
    id_set = set(node_ids)
    for node in payload["nodes"]:
        assert node["label"]
        assert node["type"] in VALID_NODE_TYPES
        assert 0.0 <= node["confidence"] <= 1.0
    edge_ids = [edge["id"] for edge in payload["edges"]]
    assert len(edge_ids) == len(set(edge_ids))
    for edge in payload["edges"]:
        assert edge["source"] in id_set and edge["target"] in id_set
        assert edge["label"]
        assert edge["type"] in VALID_EDGE_TYPES
    assert isinstance(payload["warnings"], list)


def test_any_query_returns_valid_graph_response() -> None:
    for query in ["что такое железо", "какие виды горных пород есть", "nickel electrowinning", ""]:
        payload = graph_for(query)
        assert_valid_graph(payload)
        assert any(node["type"] == "Query" for node in payload["nodes"])


def test_domain_query_builds_relevant_rock_graph() -> None:
    payload = graph_for("какие виды горных пород есть")
    assert_valid_graph(payload)
    labels = {node["label"].lower() for node in payload["nodes"]}
    assert any("горн" in label and "пород" in label for label in labels)
    assert any("магмат" in label or "осад" in label or "метаморф" in label for label in labels)


def test_legacy_neighborhood_endpoint_uses_query_graph() -> None:
    response = client.get("/api/graph/neighborhood", params={"seed": "железо", "limit": 20})
    assert response.status_code == 200
    payload = response.json()["data"]
    assert_valid_graph(payload)


def test_validate_graph_payload_repairs_broken_input() -> None:
    repaired = validate_graph_payload({
        "graph_mode": "unknown",
        "nodes": [
            {"id": "a", "label": "node", "type": "Material", "confidence": 2.0},
            {"id": "a", "label": "duplicate", "type": "Material"},
            {"id": "b", "label": "bad type", "type": "Alien"},
        ],
        "edges": [
            {"id": "e", "source": "a", "target": "b", "label": None, "type": "weird"},
            {"id": "broken", "source": "a", "target": "missing", "label": "x", "type": "related"},
        ],
    })
    assert_valid_graph(repaired)
    assert repaired["graph_mode"] == "fallback"
    assert len(repaired["nodes"]) == 2
    assert len(repaired["edges"]) == 1
