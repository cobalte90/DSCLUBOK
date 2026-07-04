from __future__ import annotations

import httpx

from ..models import ExternalSearchRequest, ExternalSourceHit
from .base import ConnectorError

API_URL = "https://api.crossref.org/works"
MAX_SNIPPET_LEN = 800


def _clean_abstract(raw: str | None) -> str | None:
    if not raw:
        return None
    # Crossref abstracts sometimes come wrapped in JATS-like <jats:p> tags.
    import re

    text = re.sub(r"<[^>]+>", " ", raw)
    text = " ".join(text.split())
    return text[:MAX_SNIPPET_LEN] or None


class CrossrefConnector:
    id = "crossref"
    label = "Crossref"
    requires_api_key = False

    def __init__(self, *, mailto: str | None = None, enabled: bool = True):
        self._mailto = mailto
        self._enabled = enabled

    def is_enabled(self) -> bool:
        return self._enabled

    async def search(self, request: ExternalSearchRequest) -> list[ExternalSourceHit]:
        params = {
            "query": request.query,
            "rows": min(request.limit, 25),
        }
        filters = []
        if request.year_from:
            filters.append(f"from-pub-date:{request.year_from}-01-01")
        if request.year_to:
            filters.append(f"until-pub-date:{request.year_to}-12-31")
        if filters:
            params["filter"] = ",".join(filters)
        # Crossref's "polite pool": pass contact email via User-Agent, not a key.
        headers = {}
        if self._mailto:
            headers["User-Agent"] = (
                f"external-sources-module/1.0 (mailto:{self._mailto})"
            )

        timeout = httpx.Timeout(min(request.timeout_ms, 4000) / 1000)
        try:
            async with httpx.AsyncClient(timeout=timeout, headers=headers) as client:
                resp = await client.get(API_URL, params=params)
                resp.raise_for_status()
                payload = resp.json()
        except httpx.TimeoutException as exc:
            raise ConnectorError(self.id, "timeout") from exc
        except httpx.HTTPStatusError as exc:
            raise ConnectorError(self.id, f"http_{exc.response.status_code}") from exc
        except httpx.HTTPError as exc:
            raise ConnectorError(self.id, "network_error") from exc

        hits: list[ExternalSourceHit] = []
        for item in payload.get("message", {}).get("items", []):
            doi = item.get("DOI")
            title_list = item.get("title") or []
            title = title_list[0] if title_list else "Untitled"
            authors = [
                " ".join(filter(None, [a.get("given"), a.get("family")]))
                for a in item.get("author", [])
            ] if item.get("author") else []
            year = None
            date_parts = (
                item.get("published-print", {}).get("date-parts")
                or item.get("published-online", {}).get("date-parts")
                or item.get("issued", {}).get("date-parts")
            )
            if date_parts and date_parts[0]:
                year = date_parts[0][0]

            hits.append(
                ExternalSourceHit(
                    id=f"external_crossref_{doi or item.get('URL', '')}",
                    connector_id=self.id,
                    source_name=self.label,
                    source_type="patent" if item.get("type") == "patent" else "publication",
                    title=title,
                    authors=authors,
                    year=year,
                    url=item.get("URL", ""),
                    doi=doi,
                    journal=(item.get("container-title") or [None])[0],
                    publisher=item.get("publisher"),
                    snippet=_clean_abstract(item.get("abstract")),
                    access_status="abstract_available" if item.get("abstract") else "metadata_only",
                    matched_terms=[],
                    raw={},
                )
            )
        return hits
