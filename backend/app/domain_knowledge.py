from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from .utils import normalize_text, tokenize

RU_SUFFIXES = (
    "иями", "ями", "ами", "иях", "ях", "ах", "ого", "ему", "ыми", "ими",
    "ой", "ей", "ий", "ый", "ая", "яя", "ое", "ее", "ые", "ие", "ых", "их",
    "ов", "ев", "ам", "ям", "ом", "ем", "ую", "юю", "а", "я", "о", "е", "у", "ю", "ы", "и", "ь",
)


def _stem(token: str) -> str:
    token = token.lower().strip()
    if len(token) <= 4:
        return token
    for suffix in RU_SUFFIXES:
        if token.endswith(suffix) and len(token) - len(suffix) >= 4:
            return token[: -len(suffix)]
    return token


def _stems(text: str) -> set[str]:
    return {_stem(token) for token in tokenize(text) if len(token) >= 2}


@lru_cache(maxsize=1)
def load_domain_knowledge() -> list[dict[str, Any]]:
    path = Path.cwd() / "data" / "domain_knowledge.json"
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError:
        return []
    return list(data.get("entries") or [])


def search_domain_knowledge(query: str, limit: int = 5) -> list[dict[str, Any]]:
    query = normalize_text(query or "")
    query_stems = _stems(query)
    if not query_stems:
        return []
    scored: list[tuple[float, dict[str, Any]]] = []
    for entry in load_domain_knowledge():
        aliases = [entry.get("title", ""), *(entry.get("aliases") or [])]
        best = 0.0
        for alias in aliases:
            alias_stems = _stems(alias)
            if not alias_stems:
                continue
            overlap = len(query_stems & alias_stems) / max(len(alias_stems), 1)
            coverage = len(query_stems & alias_stems) / max(min(len(query_stems), len(alias_stems)), 1)
            score = overlap * 0.65 + coverage * 0.35
            if normalize_text(alias).lower() in query.lower():
                score += 0.35
            best = max(best, score)
        if best >= 0.42:
            item = dict(entry)
            item["score"] = round(min(best, 1.0), 4)
            scored.append((best, item))
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [item for _, item in scored[:limit]]


def domain_summary(matches: list[dict[str, Any]]) -> str:
    if not matches:
        return ""
    primary = matches[0]
    lines = ["Короткий вывод:", primary.get("answer") or primary.get("definition") or primary.get("title", "")]
    children = primary.get("children") or []
    if children:
        lines.extend(["", "Ключевые понятия:"])
        for child in children[:8]:
            desc = child.get("description")
            lines.append(f"- {child.get('label')}: {desc}" if desc else f"- {child.get('label')}")
    lines.extend([
        "",
        "На чем основано:",
        f"- Базовый доменный справочник: {primary.get('title')}.",
        "",
        "Ограничения и риски:",
        "- Это справочный слой. Для инженерных решений нужны локальные документы, параметры и источники.",
    ])
    return "\n".join(lines).strip()


def domain_graph_nodes(entry: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    root_id = f"domain_{entry.get('id', 'entry')}"
    nodes = [
        {
            "id": root_id,
            "label": entry.get("title") or entry.get("id") or "Доменное знание",
            "type": entry.get("entity_type") or "Unknown",
            "confidence": 0.86,
            "sourceCount": 1,
            "description": entry.get("definition"),
            "metadata": {"origin": "domain_knowledge", "entry_id": entry.get("id")},
        }
    ]
    edges: list[dict[str, Any]] = []
    for index, child in enumerate(entry.get("children") or []):
        child_id = f"{root_id}_child_{index}"
        nodes.append(
            {
                "id": child_id,
                "label": child.get("label"),
                "type": child.get("type") or "Unknown",
                "confidence": 0.82,
                "sourceCount": 1,
                "description": child.get("description"),
                "metadata": {"origin": "domain_knowledge", "entry_id": entry.get("id")},
            }
        )
        edges.append(
            {
                "id": f"edge_{root_id}_{index}",
                "source": root_id,
                "target": child_id,
                "label": "включает",
                "type": "related",
                "confidence": 0.82,
            }
        )
    return nodes, edges
