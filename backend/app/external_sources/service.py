from __future__ import annotations

import asyncio
import os
import time
from dataclasses import dataclass

from .connectors.base import ConnectorError, ExternalSourceConnector
from .connectors.crossref import CrossrefConnector
from .connectors.google_patents import GooglePatentsConnector
from .connectors.openalex import OpenAlexConnector
from .models import ConnectorFailure, ExternalSearchRequest, ExternalSearchResult, ExternalSourceHit
from .ranking import dedup_and_rank


@dataclass
class _CacheEntry:
    result: ExternalSearchResult
    expires_at: float


class ExternalResearchService:
    """
    Orchestrates connector fan-out per spec section 6:
    - runs connectors concurrently with a per-connector timeout
    - a single connector failing never fails the whole search
    - dedups + ranks
    - caches identical requests for CACHE_TTL_SECONDS
    """

    CACHE_TTL_SECONDS = 60 * 30  # 30 min, within the spec's 15-60 min range

    def __init__(self, connectors: list[ExternalSourceConnector] | None = None):
        self._connectors = connectors or self._default_connectors()
        self._cache: dict[str, _CacheEntry] = {}

    @staticmethod
    def _default_connectors() -> list[ExternalSourceConnector]:
        mailto = os.getenv("EXTERNAL_SOURCES_CONTACT_EMAIL") or None
        return [
            OpenAlexConnector(mailto=mailto, enabled=os.getenv("OPENALEX_ENABLED", "true") == "true"),
            CrossrefConnector(mailto=mailto, enabled=os.getenv("CROSSREF_ENABLED", "true") == "true"),
            GooglePatentsConnector(enabled=os.getenv("GOOGLE_PATENTS_ENABLED", "true") == "true"),
            # Springer / Wiley / ScienceDirect / MDPI / CyberLeninka / elibrary /
            # researchgate connectors slot in here once implemented — each
            # should self-report is_enabled()=False when no key is configured
            # rather than being omitted from this list, so /connectors can
            # show them as "missing_api_key" instead of silently absent.
        ]

    def list_connectors(self) -> list[dict]:
        return [
            {
                "id": c.id,
                "label": c.label,
                "enabled": c.is_enabled(),
                "requires_api_key": c.requires_api_key,
                "status": "ok" if c.is_enabled() else (
                    "missing_api_key" if c.requires_api_key else "disabled"
                ),
            }
            for c in self._connectors
        ]

    def _cache_key(self, request: ExternalSearchRequest) -> str:
        return "|".join([
            request.query.strip().lower(),
            str(request.limit),
            ",".join(sorted(request.connectors)),
            request.language,
            str(request.year_from),
            str(request.year_to),
            str(request.include_patents),
        ])

    async def search(self, request: ExternalSearchRequest) -> ExternalSearchResult:
        cache_key = self._cache_key(request)
        cached = self._cache.get(cache_key)
        now = time.monotonic()
        if cached and cached.expires_at > now:
            return cached.result

        start = time.monotonic()
        requested_ids = set(request.connectors) if request.connectors else None
        active = [
            c for c in self._connectors
            if c.is_enabled() and (requested_ids is None or c.id in requested_ids)
        ]

        per_connector_timeout = max(2.0, min(4.0, request.timeout_ms / 1000))

        async def run_one(connector: ExternalSourceConnector):
            try:
                return connector.id, await asyncio.wait_for(
                    connector.search(request), timeout=per_connector_timeout
                )
            except asyncio.TimeoutError:
                return connector.id, ConnectorError(connector.id, "timeout")
            except ConnectorError as exc:
                return connector.id, exc
            except Exception as exc:  # noqa: BLE001 - must never leak raw errors to API
                return connector.id, ConnectorError(connector.id, "unexpected_error")

        try:
            outcomes = await asyncio.wait_for(
                asyncio.gather(*(run_one(c) for c in active)),
                timeout=request.timeout_ms / 1000,
            )
        except asyncio.TimeoutError:
            outcomes = [(c.id, ConnectorError(c.id, "global_timeout")) for c in active]

        all_hits: list[ExternalSourceHit] = []
        used: list[str] = []
        failed: list[ConnectorFailure] = []
        for connector_id, outcome in outcomes:
            if isinstance(outcome, ConnectorError):
                failed.append(ConnectorFailure(id=connector_id, reason=outcome.reason))
            else:
                used.append(connector_id)
                all_hits.extend(outcome)

        ranked = dedup_and_rank(request.query, all_hits, request.limit)
        result = ExternalSearchResult(
            items=ranked,
            took_ms=int((time.monotonic() - start) * 1000),
            used_connectors=used,
            failed_connectors=failed,
        )
        self._cache[cache_key] = _CacheEntry(result=result, expires_at=now + self.CACHE_TTL_SECONDS)
        return result
