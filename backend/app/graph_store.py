from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import requests

from .config import settings
from .utils import clamp_confidence


@dataclass(slots=True)
class GraphWriteResult:
    enabled: bool
    success: bool
    warnings: list[str]


class GraphStore:
    def __init__(self) -> None:
        self.enabled = bool(settings.neo4j_http_url)

    def health(self) -> dict[str, Any]:
        if not self.enabled:
            return {"enabled": False, "available": False, "reason": "neo4j_http_url is not configured"}
        try:
            response = requests.get(
                f"{settings.neo4j_http_url.rstrip('/')}/browser/",
                auth=(settings.neo4j_user, settings.neo4j_password),
                timeout=5,
            )
            return {"enabled": True, "available": response.status_code < 500, "status_code": response.status_code}
        except Exception as exc:  # pragma: no cover - network dependent
            return {"enabled": True, "available": False, "reason": str(exc)}

    def write_document_graph(
        self,
        *,
        document: dict[str, Any],
        fragments: list[dict[str, Any]],
        facts: list[dict[str, Any]],
    ) -> GraphWriteResult:
        if not self.enabled:
            return GraphWriteResult(enabled=False, success=False, warnings=["Neo4j graph store is disabled."])

        statements = [
            {
                "statement": """
                MERGE (d:Document {id: $id})
                SET d.filename = $filename,
                    d.source_type = $source_type,
                    d.language = $language,
                    d.path = $path,
                    d.access_level = $access_level
                """,
                "parameters": document,
            }
        ]

        for fragment in fragments:
            statements.append(
                {
                    "statement": """
                    MATCH (d:Document {id: $document_id})
                    MERGE (f:Fragment {id: $id})
                    SET f.fragment_type = $fragment_type,
                        f.page_number = $page_number,
                        f.ordinal = $ordinal,
                        f.text = $text
                    MERGE (d)-[:HAS_FRAGMENT]->(f)
                    """,
                    "parameters": fragment,
                }
            )

        for fact in facts:
            subject_label = _safe_label(fact.get("subject_type") or "Unknown")
            object_label = _safe_label(fact.get("object_type") or "Unknown")
            predicate = _safe_rel_type(fact["predicate"])
            statements.append(
                {
                    "statement": f"""
                    MATCH (d:Document {{id: $document_id}})
                    MATCH (f:Fragment {{id: $fragment_id}})
                    MERGE (s:{subject_label} {{name: $subject}})
                    MERGE (o:{object_label} {{name: $object_value}})
                    MERGE (fact:Fact {{id: $fact_id}})
                    SET fact.predicate = $predicate,
                        fact.unit = $unit,
                        fact.min_value = $min_value,
                        fact.max_value = $max_value,
                        fact.numeric_value = $numeric_value,
                        fact.confidence = $confidence,
                        fact.verification_status = $verification_status
                    MERGE (s)-[r:{predicate}]->(o)
                    SET r.confidence = $confidence,
                        r.unit = $unit,
                        r.min_value = $min_value,
                        r.max_value = $max_value
                    MERGE (fact)-[:SUBJECT]->(s)
                    MERGE (fact)-[:OBJECT]->(o)
                    MERGE (fact)-[:SUPPORTED_BY]->(f)
                    MERGE (fact)-[:DESCRIBED_IN]->(d)
                    """,
                    "parameters": {
                        **fact,
                        "fact_id": fact["id"],
                        "predicate": fact["predicate"],
                        "confidence": clamp_confidence(float(fact.get("confidence", 0.5))),
                    },
                }
            )

        try:
            payload = {"statements": statements}
            response = requests.post(
                f"{settings.neo4j_http_url.rstrip('/')}/db/neo4j/tx/commit",
                auth=(settings.neo4j_user, settings.neo4j_password),
                json=payload,
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()
            errors = data.get("errors", [])
            if errors:
                return GraphWriteResult(enabled=True, success=False, warnings=[error.get("message", "Unknown Neo4j error") for error in errors])
            return GraphWriteResult(enabled=True, success=True, warnings=[])
        except Exception as exc:  # pragma: no cover - network dependent
            return GraphWriteResult(enabled=True, success=False, warnings=[str(exc)])

    def neighborhood_multi(self, *, seeds: list[str], hops: int = 2, limit: int = 50) -> dict[str, Any] | None:
        if not self.enabled or not seeds:
            return None
        clean_seeds = [str(seed).strip() for seed in seeds if str(seed).strip()][:8]
        if not clean_seeds:
            return None
        statement = """
        MATCH (n)
        WHERE any(seed IN $seeds WHERE toLower(coalesce(n.name, n.filename, "")) CONTAINS toLower(seed))
        MATCH path = (n)-[*1..2]-(m)
        RETURN path
        LIMIT $limit
        """
        try:
            response = requests.post(
                f"{settings.neo4j_http_url.rstrip('/')}/db/neo4j/tx/commit",
                auth=(settings.neo4j_user, settings.neo4j_password),
                json={
                    "statements": [
                        {
                            "statement": statement.replace("*1..2", f"*1..{max(1, min(int(hops or 2), 3))}"),
                            "parameters": {"seeds": clean_seeds, "limit": limit},
                            "resultDataContents": ["graph"],
                        }
                    ]
                },
                timeout=15,
            )
            response.raise_for_status()
            data = response.json()
            results = data.get("results", [])
            if not results:
                return {"nodes": [], "edges": []}
            rows = results[0].get("data", [])
            nodes: dict[str, dict[str, Any]] = {}
            edges: list[dict[str, Any]] = []
            seen_edges: set[str] = set()
            for row in rows:
                for graph_row in row.get("graph", {}).get("nodes", []):
                    labels = graph_row.get("labels", ["Unknown"])
                    props = graph_row.get("properties", {})
                    nodes[str(graph_row["id"])] = {
                        "id": str(graph_row["id"]),
                        "label": props.get("name") or props.get("filename") or props.get("title") or str(graph_row["id"]),
                        "type": labels[0] if labels else "Unknown",
                    }
                for rel in row.get("graph", {}).get("relationships", []):
                    rel_id = str(rel.get("id"))
                    if rel_id in seen_edges:
                        continue
                    seen_edges.add(rel_id)
                    edges.append(
                        {
                            "id": rel_id,
                            "source": str(rel["startNode"]),
                            "target": str(rel["endNode"]),
                            "label": rel["type"],
                            "confidence": rel.get("properties", {}).get("confidence"),
                        }
                    )
            return {"nodes": list(nodes.values()), "edges": edges}
        except Exception:
            return None

    def neighborhood(self, *, seed: str, limit: int = 25) -> dict[str, Any] | None:
        if not self.enabled:
            return None
        statement = """
        MATCH (n)-[r]-(m)
        WHERE toLower(coalesce(n.name, n.filename, "")) CONTAINS toLower($seed)
           OR toLower(coalesce(m.name, m.filename, "")) CONTAINS toLower($seed)
        RETURN DISTINCT n, r, m
        LIMIT $limit
        """
        try:
            response = requests.post(
                f"{settings.neo4j_http_url.rstrip('/')}/db/neo4j/tx/commit",
                auth=(settings.neo4j_user, settings.neo4j_password),
                json={
                    "statements": [
                        {
                            "statement": statement,
                            "parameters": {"seed": seed, "limit": limit},
                            "resultDataContents": ["graph"],
                        }
                    ]
                },
                timeout=15,
            )
            response.raise_for_status()
            data = response.json()
            results = data.get("results", [])
            if not results:
                return {"nodes": [], "edges": []}
            rows = results[0].get("data", [])
            nodes: dict[str, dict[str, Any]] = {}
            edges: list[dict[str, Any]] = []
            for row in rows:
                graph_row = row.get("graph", {})
                for node in graph_row.get("nodes", []):
                    labels = node.get("labels", ["Unknown"])
                    nodes[node["id"]] = {
                        "id": node["id"],
                        "label": node.get("properties", {}).get("name") or node.get("properties", {}).get("filename") or node["id"],
                        "type": labels[0],
                    }
                for rel in graph_row.get("relationships", []):
                    edges.append(
                        {
                            "id": rel["id"],
                            "source": rel["startNode"],
                            "target": rel["endNode"],
                            "label": rel["type"],
                            "confidence": rel.get("properties", {}).get("confidence"),
                        }
                    )
            return {"nodes": list(nodes.values()), "edges": edges}
        except Exception:  # pragma: no cover - network dependent
            return None


def _safe_label(label: str) -> str:
    cleaned = "".join(ch if ch.isalnum() else "_" for ch in label)
    return cleaned or "Unknown"


def _safe_rel_type(rel_type: str) -> str:
    cleaned = "".join(ch if ch.isalnum() else "_" for ch in rel_type.upper())
    return cleaned or "RELATED_TO"


graph_store = GraphStore()
