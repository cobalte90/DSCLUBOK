from __future__ import annotations

import httpx

from ..models import ExternalSearchRequest, ExternalSourceHit
from .base import ConnectorError

# This is the same JSON endpoint patents.google.com's own search UI calls.
# It returns metadata/snippets only — no PDF bytes, no bulk export. Per the
# module spec this connector is limited to links + metadata for patents.
API_URL = "https://patents.google.com/xhr/query"
BASE_PATENT_URL = "https://patents.google.com/patent/{pub_id}"
MAX_SNIPPET_LEN = 800


class GooglePatentsConnector:
    id = "google_patents"
    label = "Google Patents"
    requires_api_key = False

    def __init__(self, *, enabled: bool = True):
        self._enabled = enabled

    def is_enabled(self) -> bool:
        return self._enabled

    async def search(self, request: ExternalSearchRequest) -> list[ExternalSourceHit]:
        if not request.include_patents:
            return []

        query_parts = [f"q={request.query}"]
        if request.year_from:
            query_parts.append(f"before=priority:{request.year_from}0101")
        if request.year_to:
            query_parts.append(f"after=priority:{request.year_to}1231")

        params = {
            "url": "&".join(query_parts),
            "exp": "",
        }
        headers = {
            "User-Agent": "external-sources-module/1.0",
            "Accept": "application/json",
        }

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
        except (httpx.HTTPError, ValueError) as exc:
            # ValueError covers JSON decode failures — Google occasionally
            # changes this endpoint's shape since it's not a documented API.
            raise ConnectorError(self.id, "unexpected_response_shape") from exc

        results = (
            payload.get("results", {}).get("cluster", [])
            if isinstance(payload.get("results"), dict)
            else []
        )

        hits: list[ExternalSourceHit] = []
        count = 0
        for cluster in results:
            for item in cluster.get("result", []):
                if count >= request.limit:
                    break
                patent = item.get("patent", {})
                pub_id = patent.get("publication_number")
                if not pub_id:
                    continue
                title = (patent.get("title") or "Untitled").strip()
                snippet = (patent.get("snippet") or "").strip()[:MAX_SNIPPET_LEN] or None
                year = None
                priority_date = patent.get("priority_date") or patent.get("filing_date")
                if priority_date and len(priority_date) >= 4:
                    try:
                        year = int(priority_date[:4])
                    except ValueError:
                        year = None

                hits.append(
                    ExternalSourceHit(
                        id=f"external_google_patents_{pub_id}",
                        connector_id=self.id,
                        source_name=self.label,
                        source_type="patent",
                        title=title,
                        authors=[],
                        year=year,
                        url=BASE_PATENT_URL.format(pub_id=pub_id),
                        patent_number=pub_id,
                        snippet=snippet,
                        access_status="abstract_available" if snippet else "metadata_only",
                        matched_terms=[],
                        raw={},
                    )
                )
                count += 1
            if count >= request.limit:
                break

        return hits
