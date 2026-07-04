from __future__ import annotations

import httpx

from ..models import ExternalSearchRequest, ExternalSourceHit
from .base import ConnectorError

API_URL = "https://api.openalex.org/works"
MAX_SNIPPET_LEN = 800


def _invert_abstract(inverted_index: dict | None) -> str | None:
    """OpenAlex returns abstracts as an inverted index {word: [positions]}.
    Reconstruct plain text from it (legal — OpenAlex explicitly provides
    this for reuse), then truncate to the snippet length cap.
    """
    if not inverted_index:
        return None
    position_map: dict[int, str] = {}
    for word, positions in inverted_index.items():
        for pos in positions:
            position_map[pos] = word
    if not position_map:
        return None
    ordered = [position_map[i] for i in sorted(position_map)]
    text = " ".join(ordered)
    return text[:MAX_SNIPPET_LEN]


class OpenAlexConnector:
    id = "openalex"
    label = "OpenAlex"
    requires_api_key = False

    def __init__(self, *, mailto: str | None = None, enabled: bool = True):
        # OpenAlex asks for a contact email via `mailto` param for the
        # "polite pool" (higher rate limits) — optional, not a secret.
        self._mailto = mailto
        self._enabled = enabled

    def is_enabled(self) -> bool:
        return self._enabled

    async def search(self, request: ExternalSearchRequest) -> list[ExternalSourceHit]:
        params = {
            "search": request.query,
            "per-page": min(request.limit, 25),
        }
        filters = []
        if request.year_from:
            filters.append(f"from_publication_date:{request.year_from}-01-01")
        if request.year_to:
            filters.append(f"to_publication_date:{request.year_to}-12-31")
        if filters:
            params["filter"] = ",".join(filters)
        if self._mailto:
            params["mailto"] = self._mailto

        timeout = httpx.Timeout(min(request.timeout_ms, 4000) / 1000)
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
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
        for work in payload.get("results", []):
            doi = (work.get("doi") or "").replace("https://doi.org/", "") or None
            authors = [
                a.get("author", {}).get("display_name", "")
                for a in work.get("authorships", [])
                if a.get("author", {}).get("display_name")
            ]
            oa = work.get("open_access", {}) or {}
            is_oa = bool(oa.get("is_oa"))
            best_url = (
                work.get("primary_location", {}).get("landing_page_url")
                or work.get("id")
            )
            snippet = _invert_abstract(work.get("abstract_inverted_index"))

            hits.append(
                ExternalSourceHit(
                    id=f"external_openalex_{work.get('id', '').rsplit('/', 1)[-1]}",
                    connector_id=self.id,
                    source_name=self.label,
                    source_type="publication",
                    title=work.get("title") or "Untitled",
                    authors=authors,
                    year=work.get("publication_year"),
                    url=best_url or work.get("id", ""),
                    doi=doi,
                    journal=(work.get("primary_location", {}) or {})
                    .get("source", {})
                    .get("display_name"),
                    snippet=snippet,
                    language=work.get("language"),
                    access_status="abstract_available" if snippet else (
                        "full_text_available" if is_oa else "metadata_only"
                    ),
                    matched_terms=[],
                    license=(work.get("primary_location", {}) or {})
                    .get("license"),
                    raw={},
                )
            )
        return hits
