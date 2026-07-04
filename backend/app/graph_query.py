from __future__ import annotations

import difflib
import hashlib
import re
from collections import defaultdict
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .graph_store import graph_store
from .models import DocumentRecord, EntityRecord, FactRecord
from .domain_knowledge import domain_graph_nodes, search_domain_knowledge
from .ontology import CANONICAL_ENTITY_TYPES, DEFAULT_SYNONYMS, DEFAULT_UNITS, ENTITY_HINTS
from .search import GRAPH_STOPWORDS, collect_facts_for_fragments, detect_contradictions, search_fragments
from .utils import TOKEN_RE, clamp_confidence, normalize_text, tokenize


CONTRACT_NODE_TYPES = {
    "Query", "Material", "Process", "Equipment", "Parameter", "Condition", "Result",
    "Publication", "SourceFragment", "Claim", "Gap", "Contradiction", "Unknown",
}

NODE_TYPE_MAP = {
    "Material": "Material",
    "Process": "Process",
    "Equipment": "Equipment",
    "Parameter": "Parameter",
    "Property": "Parameter",
    "NormalizedValue": "Parameter",
    "Condition": "Condition",
    "Geo": "Condition",
    "Result": "Result",
    "Experiment": "Result",
    "Publication": "Publication",
    "Document": "Publication",
    "Fragment": "SourceFragment",
    "SourceFragment": "SourceFragment",
    "Claim": "Claim",
    "Gap": "Gap",
    "Contradiction": "Contradiction",
    "ReferenceEntry": "Material",
    "Query": "Query",
}

EDGE_TYPES = {"related", "evidence", "parameter", "contradiction", "gap", "source"}

EDGE_TYPE_BY_PREDICATE = {
    "DESCRIBED_IN": "evidence",
    "MENTIONED_IN": "evidence",
    "VALIDATED_BY": "evidence",
    "SUPPORTED_BY": "evidence",
    "HAS_PARAMETER": "parameter",
    "HAS_RANGE": "parameter",
    "OPERATES_AT": "parameter",
    "OPERATES_AT_CONDITION": "parameter",
    "CONTRADICTS": "contradiction",
    "HAS_FRAGMENT": "source",
}

RELATION_LABELS_RU = {
    "USES_MATERIAL": "использует материал",
    "USES_EQUIPMENT": "использует оборудование",
    "OPERATES_AT_CONDITION": "работает при условии",
    "OPERATES_AT": "работает при условии",
    "PRODUCES_OUTPUT": "дает результат",
    "PRODUCES": "дает результат",
    "DESCRIBED_IN": "описано в",
    "MENTIONED_IN": "упомянуто в",
    "VALIDATED_BY": "подтверждено",
    "CONTRADICTS": "противоречит",
    "AUTHORED_BY": "автор",
    "EXPERT_IN": "экспертиза",
    "LOCATED_IN": "расположено в",
    "SAME_AS": "синоним",
    "QUERY_MATCH": "связано с запросом",
    "HAS_PARAMETER": "имеет параметр",
    "HAS_RANGE": "имеет диапазон",
    "HAS_FRAGMENT": "содержит фрагмент",
    "APPLIES_TO": "применимо к",
    "SUPPORTED_BY": "подтверждается фрагментом",
    "SUBJECT": "субъект",
    "OBJECT": "объект",
}

UNITS_PATTERN = r"мг/дм3|мг/дм³|мг/л|г/дм3|г/дм³|г/л|кг/т|г/т|т/сут|а/дм2|а/дм²|а/м2|а/м²|°\s?[cс]|%"

NUMERIC_CONSTRAINT_RE = re.compile(
    r"(?P<op><=|>=|≤|≥|<|>|не\s*более|не\s*менее|более|менее|до|от)?\s*"
    r"(?P<left>\d+(?:[.,]\d+)?)"
    r"(?:\s*(?:-|до)\s*(?P<right>\d+(?:[.,]\d+)?))?"
    r"\s*(?P<unit>" + UNITS_PATTERN + r")",
    re.IGNORECASE,
)

CHEMICAL_SYMBOL_RE = re.compile(r"\b(Au|Ag|Pt|Pd|Rh|Ru|Ir|Ni|Cu|Co|Fe|Zn|Pb)\b")

CHEMICAL_SYMBOL_NAMES = {
    "Au": "золото", "Ag": "серебро", "Pt": "платина", "Pd": "палладий",
    "Rh": "родий", "Ru": "рутений", "Ir": "иридий", "Ni": "никель",
    "Cu": "медь", "Co": "кобальт", "Fe": "железо", "Zn": "цинк", "Pb": "свинец",
}

YEAR_RE = re.compile(r"\b(?:19|20)\d{2}\b")

MAX_OPERATORS = {"<=", "≤", "<", "не более", "неболее", "до", "менее"}
MIN_OPERATORS = {">=", "≥", ">", "не менее", "ненее", "от", "более"}


def contract_node_type(raw_type: str | None) -> str:
    return NODE_TYPE_MAP.get((raw_type or "").strip(), "Unknown")


def relation_label(predicate: str | None) -> str:
    predicate = (predicate or "").strip()
    if not predicate:
        return "связано"
    return RELATION_LABELS_RU.get(predicate.upper(), predicate.replace("_", " ").lower())


def edge_type_for_predicate(predicate: str | None) -> str:
    return EDGE_TYPE_BY_PREDICATE.get((predicate or "").upper(), "related")


def _clean_label(value: Any) -> str:
    text = normalize_text(str(value or "")).strip()
    if not text:
        return ""
    if len(text) > 120:
        text = text[:119].rstrip() + "…"
    return text


class GraphBuilder:
    """Accumulates nodes and edges with deterministic ids, deduplication and validation."""

    def __init__(self) -> None:
        self.nodes: dict[str, dict[str, Any]] = {}
        self.edges: dict[tuple[str, str, str], dict[str, Any]] = {}
        self.node_docs: dict[str, set[str]] = defaultdict(set)
        self.pinned: set[str] = set()

    def add_node(
        self,
        label: Any,
        node_type: str,
        *,
        confidence: float = 0.6,
        description: str | None = None,
        metadata: dict[str, Any] | None = None,
        doc_id: str | None = None,
        uid: str | None = None,
        pinned: bool = False,
    ) -> str | None:
        label = _clean_label(label)
        if not label:
            return None
        node_type = node_type if node_type in CONTRACT_NODE_TYPES else contract_node_type(node_type)
        key_source = uid or f"{node_type}|{label.lower()}"
        node_id = f"{node_type.lower()}_{hashlib.sha1(key_source.encode('utf-8')).hexdigest()[:10]}"
        existing = self.nodes.get(node_id)
        if existing:
            existing["confidence"] = max(existing["confidence"], clamp_confidence(confidence))
            if description and not existing.get("description"):
                existing["description"] = _clean_label(description)
            if metadata:
                existing.setdefault("metadata", {}).update(metadata)
        else:
            node: dict[str, Any] = {
                "id": node_id,
                "label": label,
                "type": node_type,
                "confidence": clamp_confidence(confidence),
                "sourceCount": 0,
            }
            if description:
                node["description"] = _clean_label(description)
            if metadata:
                node["metadata"] = dict(metadata)
            self.nodes[node_id] = node
        if doc_id:
            self.node_docs[node_id].add(doc_id)
        if pinned:
            self.pinned.add(node_id)
        return node_id

    def add_edge(
        self,
        source: str | None,
        target: str | None,
        label: str,
        edge_type: str = "related",
        confidence: float = 0.6,
    ) -> None:
        if not source or not target or source == target:
            return
        if source not in self.nodes or target not in self.nodes:
            return
        label = _clean_label(label) or "связано"
        edge_type = edge_type if edge_type in EDGE_TYPES else "related"
        key = (source, target, label.lower())
        if key in self.edges or (target, source, label.lower()) in self.edges:
            return
        edge_id = "edge_" + hashlib.sha1(f"{source}|{target}|{label.lower()}".encode("utf-8")).hexdigest()[:10]
        self.edges[key] = {
            "id": edge_id,
            "source": source,
            "target": target,
            "label": label,
            "type": edge_type,
            "confidence": clamp_confidence(confidence),
        }

    def node_count(self) -> int:
        return len(self.nodes)

    def edge_count(self) -> int:
        return len(self.edges)

    def finalize(self, max_nodes: int = 50, max_edges: int = 80) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        for node_id, docs in self.node_docs.items():
            if node_id in self.nodes:
                self.nodes[node_id]["sourceCount"] = max(self.nodes[node_id]["sourceCount"], len(docs))

        degree: dict[str, int] = defaultdict(int)
        for edge in self.edges.values():
            degree[edge["source"]] += 1
            degree[edge["target"]] += 1

        def node_score(node: dict[str, Any]) -> float:
            score = node["confidence"] * 0.5 + min(node["sourceCount"], 5) * 0.08 + degree[node["id"]] * 0.1
            if node["id"] in self.pinned:
                score += 100.0
            if node["type"] in {"Gap", "Contradiction"}:
                score += 10.0
            return score

        ranked = sorted(self.nodes.values(), key=node_score, reverse=True)
        kept = ranked[: max(1, max_nodes)]
        kept_ids = {node["id"] for node in kept}

        edges = [edge for edge in self.edges.values() if edge["source"] in kept_ids and edge["target"] in kept_ids]
        edges.sort(key=lambda edge: edge["confidence"], reverse=True)
        edges = edges[:max_edges]

        # Put the query node first so the frontend can always center it.
        kept.sort(key=lambda node: (node["type"] != "Query", -node_score(node)))
        return kept, edges


def extract_query_entities(query: str) -> list[dict[str, Any]]:
    """Hybrid rule-based extraction: numeric constraints, dictionary terms, hints, chemistry, years."""
    text = normalize_text(query or "")
    lowered = text.lower()
    entities: list[dict[str, Any]] = []
    seen: set[str] = set()

    def push(entity: dict[str, Any]) -> None:
        key = f"{entity['type']}|{entity['normalized'].lower()}"
        if key in seen:
            return
        seen.add(key)
        entities.append(entity)

    for match in NUMERIC_CONSTRAINT_RE.finditer(lowered):
        op = (match.group("op") or "").replace(" ", "")
        left = float(match.group("left").replace(",", "."))
        right = float(match.group("right").replace(",", ".")) if match.group("right") else None
        unit_raw = re.sub(r"\s+", "", match.group("unit"))
        unit = DEFAULT_UNITS.get(unit_raw.lower(), unit_raw)
        min_value: float | None = None
        max_value: float | None = None
        if right is not None:
            min_value, max_value = min(left, right), max(left, right)
        elif op in MAX_OPERATORS:
            max_value = left
        elif op in MIN_OPERATORS:
            min_value = left
        else:
            min_value = max_value = left
        push({
            "text": match.group(0).strip(),
            "normalized": match.group(0).strip(),
            "type": "Parameter",
            "kind": "numeric_constraint",
            "unit": unit,
            "operator": op or None,
            "min_value": min_value,
            "max_value": max_value,
            "position": match.start(),
        })

    for canonical, aliases in DEFAULT_SYNONYMS.items():
        for form in [canonical, *aliases]:
            position = _find_term(lowered, form.lower())
            if position < 0:
                continue
            push({
                "text": form,
                "normalized": canonical,
                "type": CANONICAL_ENTITY_TYPES.get(canonical, "Unknown"),
                "kind": "dictionary",
                "synonyms": [canonical, *aliases],
                "position": position,
            })
            break

    for hint_type, terms in ENTITY_HINTS.items():
        for term in terms:
            position = _find_term(lowered, term)
            if position < 0:
                continue
            push({
                "text": term,
                "normalized": term,
                "type": contract_node_type(hint_type),
                "kind": "term",
                "position": position,
            })

    for match in CHEMICAL_SYMBOL_RE.finditer(text):
        symbol = match.group(1)
        push({
            "text": symbol,
            "normalized": CHEMICAL_SYMBOL_NAMES.get(symbol, symbol),
            "type": "Material",
            "kind": "chemical_symbol",
            "position": match.start(),
        })

    for match in YEAR_RE.finditer(lowered):
        push({
            "text": match.group(0),
            "normalized": match.group(0),
            "type": "Condition",
            "kind": "time_range",
            "position": match.start(),
        })

    covered = " ".join(entity["normalized"].lower() for entity in entities)
    typed_count = sum(1 for entity in entities if entity["type"] != "Unknown")
    max_residual = 2 if typed_count >= 3 else 5
    residual = 0
    for token in tokenize(lowered):
        if residual >= max_residual:
            break
        if len(token) < 5 or token in GRAPH_STOPWORDS or token.isdigit():
            continue
        if token in covered or any(token[:5] == item[:5] for item in tokenize(covered)):
            continue
        push({
            "text": token,
            "normalized": token,
            "type": "Unknown",
            "kind": "unknown_term",
            "position": _find_term(lowered, token),
        })
        residual += 1

    return entities


def _find_term(lowered: str, term: str) -> int:
    term = term.lower().strip()
    if not term:
        return -1
    if len(term) <= 3:
        match = re.search(rf"(?<![a-zа-яё0-9]){re.escape(term)}(?![a-zа-яё0-9])", lowered)
        return match.start() if match else -1
    index = lowered.find(term)
    if index >= 0:
        return index
    # Inflection-tolerant match for Russian word forms: "шахтные воды" ~ "шахтных вод".
    term_tokens = tokenize(term)
    if not term_tokens:
        return -1
    query_tokens = [(match.group(0).lower(), match.start()) for match in TOKEN_RE.finditer(lowered)]
    for start in range(len(query_tokens) - len(term_tokens) + 1):
        if all(_stem_equal(query_tokens[start + offset][0], term_tokens[offset]) for offset in range(len(term_tokens))):
            return query_tokens[start][1]
    return -1


def _stem_equal(left: str, right: str) -> bool:
    if left == right:
        return True
    if abs(len(left) - len(right)) > 3:
        return False
    shared = min(len(left), len(right))
    if shared < 3:
        return False
    prefix = max(3, shared - 2)
    return left[:prefix] == right[:prefix]


def detect_intent(query: str, entities: list[dict[str, Any]]) -> str:
    lowered = (query or "").lower()
    if re.search(r"\b(что такое|what is)\b", lowered):
        return "definition"
    if any(entity["kind"] == "numeric_constraint" for entity in entities):
        return "parameter_search"
    if "сравн" in lowered or "compare" in lowered or " vs " in lowered:
        return "comparison"
    return "exploration"


def link_entities(session: Session, entities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Attach extracted entities to known graph entities; unmatched entities stay virtual."""
    candidates = _collect_link_candidates(session)
    candidate_keys = list(candidates.keys())
    linked: list[dict[str, Any]] = []
    for entity in entities:
        entry = dict(entity)
        if entity["kind"] in {"numeric_constraint", "time_range"}:
            entry.update({"linked": False, "match_name": None, "match_type": None, "source_count": 0, "match_method": None})
            linked.append(entry)
            continue
        probe_terms = [entity["normalized"], entity["text"], *entity.get("synonyms", [])]
        match, method = _match_candidate(probe_terms, candidates, candidate_keys)
        if match:
            entry.update({
                "linked": True,
                "match_name": match["name"],
                "match_type": match["type"],
                "source_count": match["source_count"],
                "match_method": method,
            })
        else:
            entry.update({"linked": False, "match_name": None, "match_type": None, "source_count": 0, "match_method": None})
        linked.append(entry)
    return linked


def _match_candidate(
    probe_terms: list[str],
    candidates: dict[str, dict[str, Any]],
    candidate_keys: list[str],
) -> tuple[dict[str, Any] | None, str | None]:
    normalized_probes = [term.lower().strip() for term in probe_terms if term and term.strip()]
    for probe in normalized_probes:
        if probe in candidates:
            return candidates[probe], "exact"
    for probe in normalized_probes:
        if len(probe) < 5:
            continue
        for key in candidate_keys:
            if probe in key or key in probe:
                return candidates[key], "alias"
    for probe in normalized_probes:
        if len(probe) < 5:
            continue
        close = difflib.get_close_matches(probe, candidate_keys, n=1, cutoff=0.86)
        if close:
            return candidates[close[0]], "fuzzy"
    return None, None


def _collect_link_candidates(session: Session) -> dict[str, dict[str, Any]]:
    candidates: dict[str, dict[str, Any]] = {}

    def register(name: str | None, entity_type: str | None, doc_id: str | None) -> None:
        cleaned = normalize_text(name or "").strip()
        if not cleaned or len(cleaned) < 2 or len(cleaned) > 90:
            return
        key = cleaned.lower()
        entry = candidates.setdefault(key, {"name": cleaned, "type": contract_node_type(entity_type), "source_count": 0, "_docs": set()})
        if doc_id:
            entry["_docs"].add(doc_id)
        entry["source_count"] = len(entry["_docs"])

    for fact in session.scalars(select(FactRecord)).all():
        register(fact.subject, fact.subject_type, fact.document_id)
        register(fact.object_value, fact.object_type, fact.document_id)
    for entity in session.scalars(select(EntityRecord)).all():
        register(entity.canonical_name, entity.entity_type, None)

    for entry in candidates.values():
        entry.pop("_docs", None)
    return candidates


def _fetch_real_graph(seeds: list[str], max_hops: int, limit: int) -> dict[str, Any] | None:
    if not seeds:
        return None
    payload = graph_store.neighborhood_multi(seeds=seeds[:6], hops=max(1, min(max_hops, 3)), limit=max(limit * 2, 40))
    if payload is None:
        # Fall back to the single-seed query for older stores.
        merged_nodes: dict[str, dict[str, Any]] = {}
        merged_edges: list[dict[str, Any]] = []
        available = False
        for seed in seeds[:4]:
            part = graph_store.neighborhood(seed=seed, limit=limit)
            if part is None:
                continue
            available = True
            for node in part.get("nodes", []):
                merged_nodes[str(node["id"])] = node
            merged_edges.extend(part.get("edges", []))
        if not available:
            return None
        payload = {"nodes": list(merged_nodes.values()), "edges": merged_edges}
    return payload


def _merge_real_payload(builder: GraphBuilder, query_node_id: str, payload: dict[str, Any], linked_terms: list[str]) -> int:
    id_map: dict[str, str] = {}
    for node in payload.get("nodes", []):
        label = _clean_label(node.get("label") or node.get("id"))
        node_id = builder.add_node(
            label,
            contract_node_type(node.get("type")),
            confidence=0.8,
            metadata={"origin": "neo4j"},
        )
        if node_id:
            id_map[str(node.get("id"))] = node_id
    edge_count = 0
    for edge in payload.get("edges", []):
        source = id_map.get(str(edge.get("source")))
        target = id_map.get(str(edge.get("target")))
        predicate = edge.get("label")
        builder.add_edge(source, target, relation_label(predicate), edge_type_for_predicate(predicate), float(edge.get("confidence") or 0.7))
        edge_count += 1
    lowered_terms = [term.lower() for term in linked_terms if term]
    connected = 0
    for node in list(builder.nodes.values()):
        if node["id"] == query_node_id or connected >= 6:
            continue
        label_lower = node["label"].lower()
        if any(term in label_lower or label_lower in term for term in lowered_terms):
            builder.add_edge(query_node_id, node["id"], "запрошено", "related", 0.85)
            connected += 1
    return edge_count


def _select_relevant_facts(
    session: Session,
    query: str,
    linked_entities: list[dict[str, Any]],
    limit: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    matches = [match for match in search_fragments(session, query, {}, limit=10) if match["score"] >= 0.3]
    facts = collect_facts_for_fragments(session, [match["fragment_id"] for match in matches])
    known_ids = {fact["id"] for fact in facts}

    entity_terms = {
        term.lower()
        for entity in linked_entities
        for term in [entity.get("match_name"), entity.get("normalized"), entity.get("text")]
        if term and len(str(term)) >= 3
    }
    if entity_terms:
        docs = {doc.id: doc for doc in session.scalars(select(DocumentRecord)).all()}
        for fact in session.scalars(select(FactRecord)).all():
            if fact.id in known_ids:
                continue
            haystack = f"{fact.subject} {fact.object_value}".lower()
            if not any(term in haystack for term in entity_terms):
                continue
            doc = docs.get(fact.document_id)
            facts.append({
                "id": fact.id,
                "document_id": fact.document_id,
                "filename": doc.filename if doc else fact.document_id,
                "fragment_id": fact.fragment_id,
                "subject": fact.subject,
                "subject_type": fact.subject_type,
                "predicate": fact.predicate,
                "object_value": fact.object_value,
                "object_type": fact.object_type,
                "unit": fact.unit,
                "min_value": fact.min_value,
                "max_value": fact.max_value,
                "confidence": fact.confidence,
                "verification_status": fact.verification_status,
                "metadata": {},
            })
            known_ids.add(fact.id)

    query_tokens = {token for token in tokenize(query) if token not in GRAPH_STOPWORDS}

    def fact_score(fact: dict[str, Any]) -> float:
        haystack = set(tokenize(f"{fact.get('subject')} {fact.get('object_value')}"))
        overlap = len(query_tokens & haystack) / max(len(query_tokens), 1) if query_tokens else 0.0
        entity_bonus = 0.3 if any(term in f"{fact.get('subject')} {fact.get('object_value')}".lower() for term in entity_terms) else 0.0
        numeric_bonus = 0.15 if fact.get("min_value") is not None or fact.get("max_value") is not None else 0.0
        return overlap * 0.5 + entity_bonus + numeric_bonus + float(fact.get("confidence") or 0.0) * 0.2

    facts.sort(key=fact_score, reverse=True)
    return facts[: max(limit, 8)], matches



def _add_domain_knowledge(builder: GraphBuilder, query_node_id: str, query: str, limit: int = 2) -> int:
    added = 0
    for entry in search_domain_knowledge(query, limit=limit):
        domain_nodes, domain_edges = domain_graph_nodes(entry)
        id_map: dict[str, str] = {}
        for node in domain_nodes:
            node_id = builder.add_node(
                node.get("label"),
                contract_node_type(node.get("type")),
                confidence=float(node.get("confidence") or 0.82),
                description=node.get("description"),
                metadata={**(node.get("metadata") or {}), "origin": "domain_knowledge"},
                uid=f"domain|{node.get('id')}",
                pinned=added == 0,
            )
            if node_id:
                id_map[node["id"]] = node_id
        root_id = id_map.get(domain_nodes[0]["id"]) if domain_nodes else None
        if root_id:
            builder.add_edge(query_node_id, root_id, "из справочника", "evidence", 0.84)
            added += 1
        for edge in domain_edges:
            builder.add_edge(
                id_map.get(edge.get("source")),
                id_map.get(edge.get("target")),
                edge.get("label") or "связано",
                edge.get("type") or "related",
                float(edge.get("confidence") or 0.78),
            )
    return added

def _add_query_entities(builder: GraphBuilder, query_node_id: str, linked_entities: list[dict[str, Any]]) -> dict[int, str]:
    """Add extracted entities as nodes wired to the query node. Returns position -> node id for parameter anchoring."""
    positioned: dict[int, str] = {}
    parameter_nodes: list[tuple[int, str]] = []
    for entity in linked_entities:
        if entity["kind"] == "numeric_constraint":
            label = entity["normalized"]
            node_id = builder.add_node(
                label,
                "Parameter",
                confidence=0.85,
                metadata={
                    "unit": entity.get("unit"),
                    "min_value": entity.get("min_value"),
                    "max_value": entity.get("max_value"),
                    "operator": entity.get("operator"),
                    "origin": "query",
                },
            )
            if node_id:
                builder.add_edge(query_node_id, node_id, "запрошено", "parameter", 0.85)
                parameter_nodes.append((entity.get("position", 0), node_id))
            continue
        label = entity.get("match_name") or entity["normalized"]
        confidence = 0.9 if entity.get("linked") else 0.5
        node_type = entity.get("match_type") if entity.get("linked") and entity.get("match_type") != "Unknown" else entity["type"]
        node_id = builder.add_node(
            label,
            node_type or "Unknown",
            confidence=confidence,
            metadata={"origin": "query", "linked": bool(entity.get("linked")), "kind": entity["kind"]},
        )
        if node_id:
            builder.add_edge(query_node_id, node_id, "запрошено", "related", confidence)
            positioned[entity.get("position", 0)] = node_id

    # Anchor numeric parameters to the nearest preceding entity mention in the query text.
    for param_position, param_id in parameter_nodes:
        best_position = -1
        best_node = None
        for position, node_id in positioned.items():
            if position < param_position and position > best_position:
                best_position = position
                best_node = node_id
        if best_node:
            builder.add_edge(best_node, param_id, "имеет диапазон", "parameter", 0.8)
    return positioned


def _add_facts_to_builder(
    builder: GraphBuilder,
    query_node_id: str,
    facts: list[dict[str, Any]],
    max_publications: int = 6,
) -> None:
    publication_count = 0
    for index, fact in enumerate(facts):
        subject_id = builder.add_node(fact.get("subject"), contract_node_type(fact.get("subject_type")), confidence=float(fact.get("confidence") or 0.6), doc_id=fact.get("document_id"))
        object_id = builder.add_node(fact.get("object_value"), contract_node_type(fact.get("object_type")), confidence=float(fact.get("confidence") or 0.6), doc_id=fact.get("document_id"))
        builder.add_edge(subject_id, object_id, relation_label(fact.get("predicate")), edge_type_for_predicate(fact.get("predicate")), float(fact.get("confidence") or 0.6))

        if fact.get("min_value") is not None or fact.get("max_value") is not None:
            min_value = fact.get("min_value")
            max_value = fact.get("max_value")
            unit = fact.get("unit") or ""
            if min_value is not None and max_value is not None and min_value != max_value:
                range_label = f"{_format_number(min_value)}-{_format_number(max_value)} {unit}".strip()
            else:
                range_label = f"{_format_number(max_value if max_value is not None else min_value)} {unit}".strip()
            param_id = builder.add_node(range_label, "Parameter", confidence=float(fact.get("confidence") or 0.6), doc_id=fact.get("document_id"), metadata={"unit": unit or None, "min_value": min_value, "max_value": max_value, "origin": "fact"})
            builder.add_edge(subject_id, param_id, "имеет диапазон", "parameter", float(fact.get("confidence") or 0.6))

        if index < 8 and publication_count < max_publications and fact.get("filename"):
            doc_node = builder.add_node(fact["filename"], "Publication", confidence=0.75, doc_id=fact.get("document_id"), metadata={"document_id": fact.get("document_id")})
            if doc_node:
                builder.add_edge(subject_id, doc_node, "описано в", "evidence", float(fact.get("confidence") or 0.6))
                publication_count += 1

    # Connect strongest fact subjects back to the query so the graph is always centered.
    connected = 0
    for fact in facts[:6]:
        subject_id = builder.add_node(fact.get("subject"), contract_node_type(fact.get("subject_type")), confidence=float(fact.get("confidence") or 0.6))
        if subject_id and subject_id != query_node_id:
            builder.add_edge(query_node_id, subject_id, "связано с запросом", "related", min(0.92, float(fact.get("confidence") or 0.55) + 0.1))
            connected += 1
        if connected >= 4:
            break


def _add_fragment_nodes(builder: GraphBuilder, query_node_id: str, matches: list[dict[str, Any]], limit: int = 3) -> None:
    for match in matches[:limit]:
        snippet = _clean_label(match.get("text"))
        if not snippet:
            continue
        fragment_id = builder.add_node(
            f"{match.get('filename')}: {snippet[:60]}",
            "SourceFragment",
            confidence=min(0.9, float(match.get("score") or 0.5) + 0.3),
            description=snippet,
            doc_id=match.get("document_id"),
            uid=f"fragment|{match.get('fragment_id')}",
            metadata={"fragment_id": match.get("fragment_id"), "page_number": match.get("page_number"), "score": match.get("score")},
        )
        if not fragment_id:
            continue
        builder.add_edge(query_node_id, fragment_id, "найдено в поиске", "source", min(0.9, float(match.get("score") or 0.5) + 0.3))
        doc_node = builder.add_node(match.get("filename"), "Publication", confidence=0.75, doc_id=match.get("document_id"), metadata={"document_id": match.get("document_id")})
        builder.add_edge(fragment_id, doc_node, "фрагмент из", "source", 0.8)


def _add_contradictions(builder: GraphBuilder, facts: list[dict[str, Any]]) -> None:
    for item in detect_contradictions(facts)[:3]:
        left = item["left"]
        right = item["right"]
        label = f"{item['subject']}: {left.get('object_value')} vs {right.get('object_value')}"
        node_id = builder.add_node(label, "Contradiction", confidence=0.7, description=item.get("reason"), metadata={"signature": item.get("signature")})
        subject_id = builder.add_node(item["subject"], contract_node_type(left.get("subject_type")), confidence=0.6)
        builder.add_edge(subject_id, node_id, "противоречие", "contradiction", 0.7)


def _format_number(value: Any) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if number.is_integer():
        return str(int(number))
    return f"{number:g}"


def run_graph_query(session: Session, request: Any) -> dict[str, Any]:
    """Main pipeline: always returns a valid graph response with graph_mode real|hybrid|fallback."""
    query = normalize_text(getattr(request, "query", "") or "").strip()
    requested_mode = (getattr(request, "mode", None) or "auto").lower()
    if requested_mode not in {"auto", "real", "hybrid", "fallback"}:
        requested_mode = "auto"
    max_nodes = max(5, min(int(getattr(request, "max_nodes", 50) or 50), 50))
    max_hops = max(1, min(int(getattr(request, "max_hops", 3) or 3), 3))
    answer_id = getattr(request, "answer_id", None)

    warnings: list[str] = []
    debug: dict[str, Any] = {"matched_entities": 0}
    if answer_id:
        debug["answer_id"] = answer_id

    entities = extract_query_entities(query)
    linked_entities = link_entities(session, entities)
    debug["matched_entities"] = sum(1 for entity in linked_entities if entity.get("linked"))
    debug["intent"] = detect_intent(query, entities)

    entities_extracted = [
        {key: entity.get(key) for key in ("text", "normalized", "type", "kind", "unit", "operator", "min_value", "max_value") if entity.get(key) is not None}
        for entity in entities
    ]
    entities_linked = [
        {
            "normalized": entity["normalized"],
            "type": entity.get("match_type") or entity["type"],
            "linked": bool(entity.get("linked")),
            "match_name": entity.get("match_name"),
            "match_method": entity.get("match_method"),
            "source_count": entity.get("source_count", 0),
        }
        for entity in linked_entities
    ]

    if not query:
        builder = GraphBuilder()
        query_node = builder.add_node("Пустой запрос", "Query", confidence=1.0, pinned=True)
        gap_node = builder.add_node("Недостаточно данных в графе", "Gap", confidence=1.0, description="Запрос пуст — сформулируйте вопрос, чтобы построить карту знаний.")
        builder.add_edge(query_node, gap_node, "не найдено в графе", "gap", 1.0)
        nodes, edges = builder.finalize(max_nodes)
        return _response("fallback", query, entities_extracted, entities_linked, nodes, edges, ["Запрос пуст — построен fallback-граф."], {**debug, "fallback_reason": "empty_query"})

    query_label = query if len(query) <= 90 else query[:89].rstrip() + "…"

    # --- Attempt 1: real graph from Neo4j -------------------------------------------------
    real_payload = None
    if requested_mode in {"auto", "real"}:
        seeds = [entity.get("match_name") or entity["normalized"] for entity in linked_entities if entity["kind"] not in {"numeric_constraint", "time_range", "unknown_term"}]
        seeds = [seed for seed in seeds if seed] or ([query_label] if query_label else [])
        real_payload = _fetch_real_graph(seeds, max_hops, max_nodes)
        if real_payload is None and requested_mode == "real":
            warnings.append("Neo4j недоступен или отключен — режим real невозможен, используется деградация.")
        elif real_payload is not None and len(real_payload.get("edges", [])) < 3 and requested_mode == "real":
            warnings.append("В Neo4j найдено слишком мало связей для полноценного real-графа.")

    if real_payload is not None and len(real_payload.get("edges", [])) >= 3 and len(real_payload.get("nodes", [])) >= 4:
        builder = GraphBuilder()
        query_node = builder.add_node(query_label, "Query", confidence=1.0, pinned=True, metadata={"full_query": query})
        linked_terms = [entity.get("match_name") or entity["normalized"] for entity in linked_entities]
        _merge_real_payload(builder, query_node, real_payload, linked_terms)
        _add_query_entities(builder, query_node, linked_entities)
        _add_domain_knowledge(builder, query_node, query)
        nodes, edges = builder.finalize(max_nodes)
        return _response("real", query, entities_extracted, entities_linked, nodes, edges, warnings, debug)

    # --- Attempt 2: hybrid mini-graph from local facts + retrieved chunks -----------------
    if requested_mode in {"auto", "real", "hybrid"}:
        if real_payload is None and requested_mode in {"auto", "hybrid"}:
            reason = "neo4j_http_url is not configured" if not graph_store.enabled else "нет соединения"
            warnings.append(f"Neo4j недоступен ({reason}) — граф построен из локальных фактов и источников.")
        facts, matches = _select_relevant_facts(session, query, linked_entities, limit=max(10, max_nodes // 3))
        top_score = max((match["score"] for match in matches), default=0.0)
        relevant = debug["matched_entities"] > 0 or top_score >= 0.35
        if requested_mode != "hybrid" and not relevant:
            facts, matches = [], []
            debug["fallback_reason"] = "low_relevance_matches"
        builder = GraphBuilder()
        query_node = builder.add_node(query_label, "Query", confidence=1.0, pinned=True, metadata={"full_query": query})
        _add_query_entities(builder, query_node, linked_entities)
        domain_added = _add_domain_knowledge(builder, query_node, query)
        if domain_added and top_score < 0.52 and debug["matched_entities"] == 0:
            facts, matches = [], []
            warnings.append("Локальные документы не дали сильного совпадения — граф сфокусирован на доменном справочнике.")
        if real_payload is not None and real_payload.get("nodes"):
            linked_terms = [entity.get("match_name") or entity["normalized"] for entity in linked_entities]
            _merge_real_payload(builder, query_node, real_payload, linked_terms)
        _add_facts_to_builder(builder, query_node, facts)
        _add_fragment_nodes(builder, query_node, matches)
        _add_contradictions(builder, facts)
        if debug["intent"] == "parameter_search" and not any(fact.get("min_value") is not None or fact.get("max_value") is not None for fact in facts):
            gap_node = builder.add_node("Числовые параметры не найдены в корпусе", "Gap", confidence=0.9, description="Запрошены числовые ограничения, но в извлеченных фактах нет диапазонов.")
            builder.add_edge(query_node, gap_node, "требует поиска", "gap", 0.9)
        non_query_nodes = builder.node_count() - 1
        if facts or matches or domain_added:
            if non_query_nodes >= 3 and builder.edge_count() >= 3:
                nodes, edges = builder.finalize(max_nodes)
                if not debug["matched_entities"]:
                    warnings.append("Точных совпадений сущностей в графовой БД мало — построен hybrid-граф из запроса и найденных источников.")
                return _response("hybrid", query, entities_extracted, entities_linked, nodes, edges, warnings, debug)
        debug.setdefault("fallback_reason", "insufficient_local_evidence" if not facts and not matches else "hybrid_graph_too_small")

    # --- Attempt 3: fallback graph (never fails) -------------------------------------------
    if "fallback_reason" not in debug:
        debug["fallback_reason"] = "fallback_mode_requested" if requested_mode == "fallback" else "no_data"
    builder = GraphBuilder()
    query_node = builder.add_node(query_label, "Query", confidence=1.0, pinned=True, metadata={"full_query": query})
    _add_query_entities(builder, query_node, linked_entities)
    domain_added = _add_domain_knowledge(builder, query_node, query)
    try:
        matches = [match for match in search_fragments(session, query, {}, limit=4) if match["score"] >= 0.3]
    except Exception:
        matches = []
    _add_fragment_nodes(builder, query_node, matches, limit=3)
    gap_node = builder.add_node(
        "Недостаточно данных в графе",
        "Gap",
        confidence=0.9,
        description="Точные совпадения в графовой БД не найдены. Показаны извлеченные из запроса термины и найденные источники.",
        pinned=True,
    )
    builder.add_edge(query_node, gap_node, "не найдено в графе", "gap", 0.9)
    unresolved = 0
    for entity in linked_entities:
        if entity.get("linked") or entity["kind"] in {"numeric_constraint", "time_range"} or unresolved >= 4:
            continue
        entity_node = builder.add_node(entity.get("match_name") or entity["normalized"], entity["type"], confidence=0.5)
        builder.add_edge(entity_node, gap_node, "требует поиска", "gap", 0.6)
        unresolved += 1
    warnings.append("Граф построен по запросу: точных совпадений в базе знаний недостаточно.")
    nodes, edges = builder.finalize(max_nodes)
    return _response("fallback", query, entities_extracted, entities_linked, nodes, edges, warnings, debug)


def _response(
    graph_mode: str,
    query: str,
    entities_extracted: list[dict[str, Any]],
    entities_linked: list[dict[str, Any]],
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    warnings: list[str],
    debug: dict[str, Any],
) -> dict[str, Any]:
    payload = {
        "graph_mode": graph_mode,
        "query": query,
        "entities_extracted": entities_extracted,
        "entities_linked": entities_linked,
        "nodes": nodes,
        "edges": edges,
        "warnings": warnings,
        "debug": debug,
    }
    return validate_graph_payload(payload)


def validate_graph_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Defensive invariants: unique node ids, valid edge endpoints, non-empty labels, graph_mode present."""
    seen_ids: set[str] = set()
    nodes: list[dict[str, Any]] = []
    for node in payload.get("nodes", []):
        node_id = str(node.get("id") or "")
        label = _clean_label(node.get("label"))
        if not node_id or node_id in seen_ids or not label:
            continue
        seen_ids.add(node_id)
        node["id"] = node_id
        node["label"] = label
        if node.get("type") not in CONTRACT_NODE_TYPES:
            node["type"] = "Unknown"
        node["confidence"] = clamp_confidence(float(node.get("confidence") or 0.5))
        node["sourceCount"] = int(node.get("sourceCount") or 0)
        nodes.append(node)
    edges: list[dict[str, Any]] = []
    seen_edges: set[str] = set()
    for edge in payload.get("edges", []):
        if edge.get("source") not in seen_ids or edge.get("target") not in seen_ids:
            continue
        edge_id = str(edge.get("id") or "")
        if not edge_id or edge_id in seen_edges:
            continue
        seen_edges.add(edge_id)
        edge["label"] = _clean_label(edge.get("label")) or "связано"
        if edge.get("type") not in EDGE_TYPES:
            edge["type"] = "related"
        edge["confidence"] = clamp_confidence(float(edge.get("confidence") or 0.5))
        edges.append(edge)
    payload["nodes"] = nodes
    payload["edges"] = edges
    if payload.get("graph_mode") not in {"real", "hybrid", "fallback"}:
        payload["graph_mode"] = "fallback"
    payload.setdefault("warnings", [])
    payload.setdefault("entities_extracted", [])
    payload.setdefault("entities_linked", [])
    return payload
