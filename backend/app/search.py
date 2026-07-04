from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import AuditEventRecord, DocumentRecord, ExperimentPassportRecord, FactRecord, ReferenceEntryRecord, SavedQueryRecord, SourceFragment, SubscriptionRecord
from .ontology import DEFAULT_SYNONYMS
from .utils import cosine_similarity, hashed_embedding, json_loads, tokenize


EXPERT_NAME_RE = re.compile(r'"name"\s*:\s*"(?P<name>[^"]+)"', re.IGNORECASE)
EXPERT_ORG_RE = re.compile(r'"organization"\s*:\s*"(?P<org>[^"]+)"', re.IGNORECASE)
TOPIC_BLOCK_RE = re.compile(r'"topics"\s*:\s*\[(?P<topics>.*?)\]', re.IGNORECASE | re.DOTALL)
TOPIC_ITEM_RE = re.compile(r'"([^"]+)"')

GRAPH_STOPWORDS = {
    "что", "такое", "это", "какой", "какая", "какие", "каких", "как", "где", "когда", "почему",
    "покажи", "показать", "расскажи", "найди", "нужно", "надо", "есть", "были", "будет",
    "при", "для", "про", "по", "между", "через", "без", "или", "и", "в", "во", "на", "с", "со", "из", "от", "до", "о", "об",
    "the", "what", "which", "show", "find", "for", "with", "and", "or", "in", "on", "of", "to",
}


def search_fragments(session: Session, query: str, filters: dict[str, Any] | None = None, limit: int = 8) -> list[dict[str, Any]]:
    filters = filters or {}
    tokens = _expand_query_tokens(query)
    query_embedding = hashed_embedding(query)
    docs = {doc.id: doc for doc in session.scalars(select(DocumentRecord)).all()}
    results = []
    for fragment in session.scalars(select(SourceFragment)).all():
        doc = docs.get(fragment.document_id)
        if not doc:
            continue
        if filters.get("source_type") and doc.source_type != filters["source_type"]:
            continue
        if filters.get("language") and doc.language != filters["language"]:
            continue
        text_tokens = set(tokenize(fragment.text))
        lexical = _token_overlap_ratio(tokens, text_tokens)
        semantic = cosine_similarity(query_embedding, json_loads(fragment.embedding_json, []))
        score = lexical * 0.65 + semantic * 0.35
        if doc.source_type == "reference_catalog" and lexical > 0:
            score += 0.08
        if doc.source_type == "experiment_protocol" and lexical > 0:
            score += 0.05
        if score <= 0:
            continue
        results.append({
            "fragment_id": fragment.id,
            "document_id": fragment.document_id,
            "filename": doc.filename,
            "source_type": doc.source_type,
            "language": doc.language,
            "text": fragment.text,
            "page_number": fragment.page_number,
            "score": round(score, 4),
        })
    results.sort(key=lambda item: item["score"], reverse=True)
    return results[:limit]


def collect_facts_for_fragments(session: Session, fragment_ids: list[str]) -> list[dict[str, Any]]:
    if not fragment_ids:
        return []
    docs = {doc.id: doc for doc in session.scalars(select(DocumentRecord)).all()}
    facts = session.scalars(select(FactRecord).where(FactRecord.fragment_id.in_(fragment_ids))).all()
    return [{
        "id": fact.id,
        "document_id": fact.document_id,
        "filename": docs.get(fact.document_id).filename if docs.get(fact.document_id) else fact.document_id,
        "source_type": docs.get(fact.document_id).source_type if docs.get(fact.document_id) else None,
        "language": docs.get(fact.document_id).language if docs.get(fact.document_id) else None,
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
        "metadata": json_loads(fact.metadata_json, {}),
    } for fact in facts]



def build_graph_neighborhood(session: Session, seed: str, limit: int = 25) -> dict[str, Any]:
    """Build a query-centered, weighted graph from extracted local facts.

    This is intentionally product-oriented: the graph starts from the user's
    natural-language query, selects the strongest evidence facts, expands one
    hop through shared entities, then adds a compact second ring between strong
    neighbours. The result behaves like an ego graph without requiring a
    separate graph engine for the demo fallback.
    """
    query = (seed or "").strip()
    query_tokens = _graph_query_tokens(query)
    definition_query = bool(re.search(r"\b(что\s+такое|what\s+is)\b", query.lower()))
    nodes: dict[str, dict[str, Any]] = {}
    edges: list[dict[str, Any]] = []
    edge_index: dict[tuple[str, str, str], dict[str, Any]] = {}

    query_key = f"Topic:{query or 'Запрос'}"
    nodes[query_key] = {
        "id": query_key,
        "label": query or "Запрос",
        "type": "Topic",
        "freq": 1,
        "n_docs": 0,
        "is_query": True,
    }

    facts = session.scalars(select(FactRecord)).all()
    if not facts or not query_tokens:
        return {"nodes": list(nodes.values()), "edges": []}

    docs = {doc.id: doc for doc in session.scalars(select(DocumentRecord)).all()}
    node_stats = _graph_node_stats(facts)
    search_matches = search_fragments(session, query, {}, limit=max(limit * 2, 18))
    fragment_scores: dict[str, float] = {}
    for match in search_matches:
        fragment_text_tokens = set(tokenize(match.get("text") or ""))
        if match["score"] >= 0.12 and _token_overlap_ratio(query_tokens, fragment_text_tokens) > 0:
            fragment_scores[match["fragment_id"]] = match["score"]

    scored: list[tuple[float, FactRecord]] = []
    for fact in facts:
        fact_text = " ".join(part for part in [fact.subject, fact.predicate, fact.object_value, fact.geo, fact.time_period, fact.unit] if part)
        fact_tokens = set(tokenize(fact_text))
        lexical = _token_overlap_ratio(query_tokens, fact_tokens)
        fragment_bonus = fragment_scores.get(fact.fragment_id, 0.0)
        confidence_bonus = float(fact.confidence or 0.0) * 0.10
        numeric_bonus = 0.07 if fact.min_value is not None or fact.max_value is not None or fact.numeric_value is not None else 0.0
        exact_bonus = 0.10 if _graph_exact_entity_hit(query_tokens, fact.subject, fact.object_value) else 0.0
        if definition_query and lexical <= 0 and exact_bonus <= 0:
            continue
        if lexical <= 0 and fragment_bonus <= 0 and exact_bonus <= 0:
            continue
        score = lexical * 0.58 + min(fragment_bonus, 1.0) * 0.22 + confidence_bonus + numeric_bonus + exact_bonus
        if score >= 0.08:
            scored.append((score, fact))

    if not scored:
        return {"nodes": list(nodes.values()), "edges": []}

    scored.sort(key=lambda item: item[0], reverse=True)
    selected: list[FactRecord] = []
    selected_ids: set[str] = set()
    touched_nodes: set[str] = set()

    primary_limit = max(5, min(limit, 16))
    for score, fact in scored:
        if len(selected) >= primary_limit:
            break
        selected.append(fact)
        selected_ids.add(fact.id)
        touched_nodes.add(_fact_node_key(fact.subject_type, fact.subject))
        touched_nodes.add(_fact_node_key(fact.object_type, fact.object_value))

    # First ring: strongest facts sharing an endpoint with the query-selected facts.
    neighbor_candidates: list[tuple[float, FactRecord]] = []
    for fact in facts:
        if fact.id in selected_ids:
            continue
        subject_key = _fact_node_key(fact.subject_type, fact.subject)
        object_key = _fact_node_key(fact.object_type, fact.object_value)
        if subject_key not in touched_nodes and object_key not in touched_nodes:
            continue
        lexical = _token_overlap_ratio(query_tokens, set(tokenize(f"{fact.subject} {fact.object_value} {fact.predicate}")))
        neighbor_score = float(fact.confidence or 0.0) * 0.38 + lexical * 0.35 + (0.08 if fact.fragment_id in fragment_scores else 0.0)
        neighbor_candidates.append((neighbor_score, fact))
    neighbor_candidates.sort(key=lambda item: item[0], reverse=True)
    for score, fact in neighbor_candidates:
        if len(selected) >= limit:
            break
        if score <= 0 and len(selected) >= primary_limit:
            continue
        selected.append(fact)
        selected_ids.add(fact.id)

    # Second ring: add compact connections between already selected neighbours.
    selected_node_keys = {
        key
        for fact in selected
        for key in (_fact_node_key(fact.subject_type, fact.subject), _fact_node_key(fact.object_type, fact.object_value))
    }
    second_ring: list[tuple[float, FactRecord]] = []
    for fact in facts:
        if fact.id in selected_ids:
            continue
        subject_key = _fact_node_key(fact.subject_type, fact.subject)
        object_key = _fact_node_key(fact.object_type, fact.object_value)
        if subject_key in selected_node_keys and object_key in selected_node_keys:
            second_ring.append((float(fact.confidence or 0.0), fact))
    second_ring.sort(key=lambda item: item[0], reverse=True)
    for _, fact in second_ring[: max(3, limit // 5)]:
        selected.append(fact)

    for fact in selected:
        subject_key = _fact_node_key(fact.subject_type, fact.subject)
        object_key = _fact_node_key(fact.object_type, fact.object_value)
        _add_graph_node(nodes, subject_key, fact.subject, fact.subject_type or "Unknown", node_stats)
        _add_graph_node(nodes, object_key, fact.object_value, fact.object_type or "Unknown", node_stats)
        _add_graph_edge(edges, edge_index, subject_key, object_key, fact.predicate, fact.confidence, weight=1)

    # Connect the user question to the strongest matching entities so the map explains why it appeared.
    connected: set[str] = set()
    for score, fact in scored[:10]:
        for key in [_fact_node_key(fact.subject_type, fact.subject), _fact_node_key(fact.object_type, fact.object_value)]:
            if key not in nodes or key in connected:
                continue
            _add_graph_edge(edges, edge_index, query_key, key, "QUERY_MATCH", min(0.94, float(fact.confidence or 0.55) + 0.08), weight=max(2, round(score * 6, 2)))
            connected.add(key)
            if len(connected) >= 6:
                break
        if len(connected) >= 6:
            break

    # Add compact evidence nodes for top facts; this makes provenance visible in graph view without overloading it.
    evidence_docs: set[str] = set()
    for _, fact in scored[: min(5, len(scored))]:
        doc = docs.get(fact.document_id)
        if not doc or doc.id in evidence_docs:
            continue
        evidence_docs.add(doc.id)
        doc_key = f"Publication:{doc.id}"
        _add_graph_node(nodes, doc_key, doc.filename, "Publication", node_stats)
        subject_key = _fact_node_key(fact.subject_type, fact.subject)
        if subject_key in nodes:
            _add_graph_edge(edges, edge_index, subject_key, doc_key, "DESCRIBED_IN", fact.confidence, weight=1)

    edges.sort(key=lambda edge: (edge.get("label") != "QUERY_MATCH", -float(edge.get("weight") or 1), -float(edge.get("confidence") or 0)))
    return {"nodes": list(nodes.values()), "edges": edges[: max(limit + 12, limit)]}


def _graph_node_stats(facts: list[FactRecord]) -> dict[str, dict[str, Any]]:
    stats: dict[str, dict[str, Any]] = defaultdict(lambda: {"freq": 0, "docs": set()})
    for fact in facts:
        for key in [_fact_node_key(fact.subject_type, fact.subject), _fact_node_key(fact.object_type, fact.object_value)]:
            stats[key]["freq"] += 1
            if fact.document_id:
                stats[key]["docs"].add(fact.document_id)
    return stats


def _graph_exact_entity_hit(query_tokens: set[str], subject: str | None, object_value: str | None) -> bool:
    for value in (subject, object_value):
        tokens = set(tokenize(value or ""))
        if tokens and tokens <= query_tokens:
            return True
        if tokens and query_tokens & tokens:
            return True
    return False


def _fact_node_key(node_type: str | None, label: str | None) -> str:
    return f"{node_type or 'Unknown'}:{(label or '').strip() or 'unknown'}"


def _add_graph_node(nodes: dict[str, dict[str, Any]], key: str, label: str | None, node_type: str | None, stats: dict[str, dict[str, Any]] | None = None) -> None:
    stat = (stats or {}).get(key, {})
    nodes.setdefault(
        key,
        {
            "id": key,
            "label": label or "unknown",
            "type": node_type or "Unknown",
            "freq": int(stat.get("freq") or 1),
            "n_docs": len(stat.get("docs") or []),
        },
    )


def _add_graph_edge(
    edges: list[dict[str, Any]],
    edge_index: dict[tuple[str, str, str], dict[str, Any]],
    source: str,
    target: str,
    label: str,
    confidence: float | None,
    weight: float = 1,
) -> None:
    if source == target:
        return
    key = (source, target, label)
    reverse_key = (target, source, label)
    existing = edge_index.get(key) or edge_index.get(reverse_key)
    if existing:
        existing["weight"] = round(float(existing.get("weight") or 1) + float(weight or 1), 3)
        if confidence is not None:
            existing["confidence"] = round(max(float(existing.get("confidence") or 0), float(confidence)), 4)
        return
    edge = {"source": source, "target": target, "label": label, "confidence": confidence, "weight": round(float(weight or 1), 3)}
    edge_index[key] = edge
    edges.append(edge)

def compare_results(session: Session, query: str, filters: dict[str, Any] | None = None, group_by: str = "document") -> dict[str, Any]:
    matches = search_fragments(session, query, filters, limit=20)
    grouped: dict[str, dict[str, Any]] = defaultdict(lambda: {"sources": [], "facts": []})
    facts = collect_facts_for_fragments(session, [match["fragment_id"] for match in matches])
    experiments = collect_experiment_passports(session, query)
    facts_by_fragment = defaultdict(list)
    for fact in facts:
        facts_by_fragment[fact["fragment_id"]].append(fact)
    for match in matches:
        key = match["document_id"] if group_by == "document" else match["source_type"]
        grouped[key]["sources"].append(match)
        grouped[key]["facts"].extend(facts_by_fragment.get(match["fragment_id"], []))
    contradictions = detect_contradictions(facts)
    source_types = sorted({match["source_type"] for match in matches})
    source_quality = _source_quality_for_matches(session, matches)
    return {
        "groups": dict(grouped),
        "matches": matches,
        "experiments": experiments,
        "contradictions": contradictions,
        "resolutions": collect_contradiction_resolutions(session, contradictions),
        "coverage_gaps": detect_gap_signals(query, matches, facts, experiments),
        "source_types": source_types,
        "source_quality": source_quality,
        "overview": {
            "match_count": len(matches),
            "fact_count": len(facts),
            "experiment_count": len(experiments),
            "contradiction_count": len(contradictions),
            "source_type_count": len(source_types),
        },
    }


def collect_experiment_passports(session: Session, query: str) -> list[dict[str, Any]]:
    query_tokens = _expand_query_tokens(query)
    rows = session.scalars(select(ExperimentPassportRecord)).all()
    result = []
    for row in rows:
        haystack = " ".join(item for item in [row.title, row.material, row.process, row.regime, row.result_summary] if item)
        haystack_tokens = set(tokenize(haystack))
        if query_tokens and _token_overlap_ratio(query_tokens, haystack_tokens) <= 0:
            continue
        result.append({
            "id": row.id,
            "title": row.title,
            "material": row.material,
            "process": row.process,
            "regime": row.regime,
            "result_summary": row.result_summary,
        })
    return result[:8]


def detect_contradictions(facts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    numeric_groups: dict[tuple[str, str, str | None], list[dict[str, Any]]] = defaultdict(list)
    for fact in facts:
        if fact.get("min_value") is None and fact.get("max_value") is None:
            continue
        numeric_groups[(fact["subject"], fact["predicate"], fact.get("unit"))].append(fact)

    contradictions: list[dict[str, Any]] = []
    for (subject, predicate, unit), items in numeric_groups.items():
        if len(items) < 2:
            continue
        spans = sorted([((item.get("min_value") or item.get("max_value") or 0.0), (item.get("max_value") or item.get("min_value") or 0.0), item) for item in items], key=lambda row: (row[0], row[1]))
        for index in range(len(spans) - 1):
            _, left_max, left_fact = spans[index]
            right_min, _, right_fact = spans[index + 1]
            if left_max is not None and right_min is not None and left_max < right_min:
                signature = contradiction_signature(subject, predicate, unit, left_fact["id"], right_fact["id"])
                contradictions.append({
                    "signature": signature,
                    "subject": subject,
                    "predicate": predicate,
                    "unit": unit,
                    "left": left_fact,
                    "right": right_fact,
                    "reason": "non_overlapping_numeric_ranges",
                })
                break
    return contradictions


def detect_gap_signals(query: str, matches: list[dict[str, Any]], facts: list[dict[str, Any]], experiments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    gaps: list[dict[str, Any]] = []
    if not matches:
        gaps.append({"type": "no_matches", "message": f"No relevant fragments were found for '{query}'."})
        return gaps
    if not facts:
        gaps.append({"type": "no_facts", "message": "Fragments were found, but they do not yet have extracted structured facts."})
    if not any(fact.get("min_value") is not None or fact.get("max_value") is not None for fact in facts):
        gaps.append({"type": "no_numeric_evidence", "message": "There are textual matches, but no numeric parameters for engineering comparison."})
    if len({match["source_type"] for match in matches}) < 2:
        gaps.append({"type": "low_source_diversity", "message": "The answer relies on a narrow source class; add more document types for a stronger conclusion."})
    if not experiments:
        gaps.append({"type": "no_experiment_passport", "message": "No matching experiment passport was found; add protocols or internal reports for stronger engineering validation."})
    if not any(match["source_type"] == "reference_catalog" for match in matches):
        gaps.append({"type": "no_reference_support", "message": "There is no reference catalog support in the current slice, so term normalization and units may still be incomplete."})
    if not any(match["source_type"] == "patent_regulation" for match in matches):
        gaps.append({"type": "no_patent_or_regulation", "message": "No patent or regulation document supports this answer yet."})
    return gaps


def search_experts(session: Session, query: str, limit: int = 8) -> list[dict[str, Any]]:
    query_tokens = _expand_query_tokens(query)
    docs = {doc.id: doc for doc in session.scalars(select(DocumentRecord).where(DocumentRecord.source_type == "expert_directory")).all()}
    results: list[dict[str, Any]] = []
    for fragment in session.scalars(select(SourceFragment)).all():
        doc = docs.get(fragment.document_id)
        if not doc:
            continue
        for card in extract_expert_cards(fragment.text):
            haystack = " ".join([card["name"], card["organization"], " ".join(card["topics"])]).strip()
            tokens = set(tokenize(haystack))
            lexical = _token_overlap_ratio(query_tokens, tokens)
            semantic = cosine_similarity(hashed_embedding(query), hashed_embedding(haystack))
            score = lexical * 0.7 + semantic * 0.3
            if score <= 0:
                continue
            results.append({"name": card["name"], "organization": card["organization"], "topics": card["topics"], "document_id": doc.id, "filename": doc.filename, "score": round(score, 4)})
    for entry in session.scalars(select(ReferenceEntryRecord).where(ReferenceEntryRecord.entry_type == "expert_directory")).all():
        haystack = f"{entry.canonical_key} {entry.display_value}"
        lexical = _token_overlap_ratio(query_tokens, set(tokenize(haystack)))
        if lexical <= 0:
            continue
        results.append({"name": entry.canonical_key, "organization": entry.metadata_json, "topics": [entry.display_value], "document_id": entry.document_id, "filename": entry.document_id, "score": round(lexical, 4)})
    deduped: dict[tuple[str, str], dict[str, Any]] = {}
    for item in sorted(results, key=lambda row: row["score"], reverse=True):
        deduped.setdefault((item["name"], item["organization"]), item)
    return list(deduped.values())[:limit]


def evaluate_alerts(session: Session) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for row in session.scalars(select(SavedQueryRecord).where(SavedQueryRecord.alert_enabled.is_(True))).all():
        matches = search_fragments(session, row.query_text, json_loads(row.filters_json, {}), limit=5)
        if matches:
            items.append({"kind": "saved_query", "id": row.id, "label": row.query_text, "match_count": len(matches), "top_source": matches[0]["filename"]})
    for row in session.scalars(select(SubscriptionRecord).where(SubscriptionRecord.active.is_(True))).all():
        payload = json_loads(row.query_json, {})
        query = payload.get("query") or row.name
        matches = search_fragments(session, query, payload.get("filters", {}), limit=5)
        if matches:
            items.append({"kind": "subscription", "id": row.id, "label": row.name, "query": query, "match_count": len(matches), "top_source": matches[0]["filename"]})
    return items


def collect_contradiction_resolutions(session: Session, contradictions: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    signatures = {item["signature"] for item in contradictions}
    if not signatures:
        return {}
    rows = session.scalars(select(AuditEventRecord).where(AuditEventRecord.action == "contradiction_resolved")).all()
    resolutions: dict[str, dict[str, Any]] = {}
    for row in rows:
        payload = json_loads(row.payload_json, {})
        signature = payload.get("signature")
        if signature in signatures:
            resolutions[signature] = {"actor": row.actor, "decision": payload.get("decision"), "comment": payload.get("comment"), "created_at": row.created_at.isoformat() if row.created_at else None}
    return resolutions


def contradiction_signature(subject: str, predicate: str, unit: str | None, left_fact_id: str, right_fact_id: str) -> str:
    ordered = sorted([left_fact_id, right_fact_id])
    return "|".join([subject, predicate, unit or "", ordered[0], ordered[1]])


def extract_expert_cards(text: str) -> list[dict[str, Any]]:
    cards: list[dict[str, Any]] = []
    names = EXPERT_NAME_RE.findall(text)
    orgs = EXPERT_ORG_RE.findall(text)
    topic_blocks = TOPIC_BLOCK_RE.findall(text)
    max_len = max(len(names), len(orgs), len(topic_blocks), 0)
    for index in range(max_len):
        topics = TOPIC_ITEM_RE.findall(topic_blocks[index]) if index < len(topic_blocks) else []
        cards.append({"name": names[index] if index < len(names) else f"expert-{index + 1}", "organization": orgs[index] if index < len(orgs) else "", "topics": topics})
    if cards:
        return cards

    fallback: dict[str, str] = {}
    for part in text.split(';'):
        if ':' not in part:
            continue
        key, value = part.split(':', 1)
        fallback[key.strip().lower()] = value.strip()
    if fallback.get('name') or fallback.get('topics') or fallback.get('organization'):
        topics = [item.strip() for item in fallback.get('topics', '').split(',') if item.strip()]
        return [{"name": fallback.get('name', 'expert-1'), "organization": fallback.get('organization', ''), "topics": topics}]
    return []


def _source_quality_for_matches(session: Session, matches: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not matches:
        return []
    docs = {doc.id: doc for doc in session.scalars(select(DocumentRecord)).all()}
    grouped: dict[str, dict[str, Any]] = {}
    for match in matches:
        doc = docs.get(match["document_id"])
        if not doc:
            continue
        entry = grouped.setdefault(doc.source_type, {"source_type": doc.source_type, "documents": set(), "fragments": 0, "avg_score_total": 0.0})
        entry["documents"].add(doc.id)
        entry["fragments"] += 1
        entry["avg_score_total"] += match["score"]
    result = []
    for item in grouped.values():
        result.append({
            "source_type": item["source_type"],
            "document_count": len(item["documents"]),
            "fragment_count": item["fragments"],
            "avg_match_score": round(item["avg_score_total"] / max(item["fragments"], 1), 4),
        })
    return sorted(result, key=lambda row: (row["fragment_count"], row["avg_match_score"]), reverse=True)


def _graph_query_tokens(query: str) -> set[str]:
    return {token for token in _expand_query_tokens(query) if token not in GRAPH_STOPWORDS}


def _expand_query_tokens(query: str) -> set[str]:
    normalized_query = query.lower()
    tokens = set(tokenize(query))
    for canonical, aliases in DEFAULT_SYNONYMS.items():
        forms = [canonical, *aliases]
        if any(form.lower() in normalized_query for form in forms):
            for form in forms:
                tokens.update(tokenize(form))
    return tokens


def _token_overlap_ratio(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    overlap = 0
    for token in left:
        if token in right:
            overlap += 1
            continue
        if any(token.startswith(other[:4]) or other.startswith(token[:4]) for other in right if len(token) >= 4 and len(other) >= 4):
            overlap += 0.75
    return overlap / max(len(left), 1)
