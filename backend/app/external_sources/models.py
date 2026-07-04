from __future__ import annotations

from datetime import datetime, timezone
from pydantic import BaseModel, Field


class ExternalSearchRequest(BaseModel):
    query: str
    limit: int = 5
    connectors: list[str] = Field(default_factory=list)
    language: str = "any"          # "ru" | "en" | "any"
    year_from: int | None = None
    year_to: int | None = None
    include_patents: bool = True
    timeout_ms: int = 8000


class ExternalSourceHit(BaseModel):
    id: str
    source_mode: str = "external"
    connector_id: str
    source_name: str
    source_type: str = "publication"  # article_review|publication|patent|regulation|dataset|unknown
    title: str
    authors: list[str] = Field(default_factory=list)
    year: int | None = None
    url: str
    doi: str | None = None
    patent_number: str | None = None
    journal: str | None = None
    publisher: str | None = None
    snippet: str | None = None
    language: str | None = None
    relevance_score: float = 0.0
    quality_score: float = 0.0
    access_status: str = "metadata_only"  # metadata_only|abstract_available|full_text_available|restricted
    matched_terms: list[str] = Field(default_factory=list)
    retrieved_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    license: str | None = None
    raw: dict = Field(default_factory=dict)


class ConnectorFailure(BaseModel):
    id: str
    reason: str


class ExternalSearchResult(BaseModel):
    items: list[ExternalSourceHit]
    took_ms: int
    used_connectors: list[str]
    failed_connectors: list[ConnectorFailure]
