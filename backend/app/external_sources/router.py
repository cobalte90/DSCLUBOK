from __future__ import annotations

import html
import os
import uuid

from fastapi import APIRouter

from ..text_normalization import repair_payload
from .models import ExternalSearchRequest
from .service import ExternalResearchService

router = APIRouter(prefix="/api/external-sources", tags=["external-sources"])
_service = ExternalResearchService()


def _envelope(data: dict, *, sources: list | None = None, confidence: float = 1.0, warnings: list | None = None):
    return {
        "request_id": f"req_{uuid.uuid4().hex[:12]}",
        "mode": "yandex",
        "sources": sources or [],
        "confidence": confidence,
        "warnings": warnings or [],
        "data": data,
    }


@router.get("/connectors")
async def get_connectors():
    return _envelope({"connectors": _service.list_connectors()})


@router.post("/search")
async def search_external_sources(request: ExternalSearchRequest):
    if os.getenv("EXTERNAL_SOURCES_ENABLED", "false") != "true":
        return _envelope(
            {"items": [], "took_ms": 0, "used_connectors": [], "failed_connectors": []},
            confidence=0.0,
            warnings=["external_sources_disabled"],
        )

    result = await _service.search(request)

    top_level_sources = [
        {
            "source_mode": "external",
            "connector_id": item.connector_id,
            "title": item.title,
            "url": item.url,
            "doi": item.doi,
            "year": item.year,
        }
        for item in result.items
    ]
    warnings = [f"{f.id}: {f.reason}" for f in result.failed_connectors]
    confidence = 0.0 if not result.items else min(1.0, sum(i.relevance_score for i in result.items) / len(result.items))

    return _envelope(
        {
            "items": [_normalize_item(item.model_dump()) for item in result.items],
            "took_ms": result.took_ms,
            "used_connectors": result.used_connectors,
            "failed_connectors": [f.model_dump() for f in result.failed_connectors],
        },
        sources=top_level_sources,
        confidence=round(confidence, 4),
        warnings=warnings,
    )


def _normalize_item(item: dict) -> dict:
    normalized = dict(item)
    for key in ("title", "snippet", "journal", "publisher", "source_name"):
        if normalized.get(key):
            normalized[key] = html.unescape(str(repair_payload(normalized[key])))
    normalized["authors"] = repair_payload(normalized.get("authors") or [])
    return normalized
