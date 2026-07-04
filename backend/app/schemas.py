from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, model_validator

from .text_normalization import repair_payload


class ApiEnvelope(BaseModel):
    request_id: str
    mode: str
    sources: list[dict[str, Any]] = Field(default_factory=list)
    confidence: float = 0.0
    warnings: list[str] = Field(default_factory=list)
    data: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def normalize_text_payload(self) -> "ApiEnvelope":
        self.sources = repair_payload(self.sources)
        self.warnings = repair_payload(self.warnings)
        self.data = repair_payload(self.data)
        return self


class SourceUploadBody(BaseModel):
    source_type: str
    access_level: str = "internal"
    tags: list[str] = Field(default_factory=list)
    name: str | None = None


class FolderImportRequest(BaseModel):
    path_alias: str
    filesystem_path: str
    source_type: str
    watch_mode: str = "manual"
    recursive: bool = True
    access_level: str = "internal"
    tags: list[str] = Field(default_factory=list)


class ScanRequest(BaseModel):
    source_ids: list[str] | None = None


class ImportRunRequest(BaseModel):
    source_ids: list[str]
    extraction_profile: str = "default"
    force_reingest: bool = False


class SearchRequest(BaseModel):
    query: str
    filters: dict[str, Any] = Field(default_factory=dict)
    limit: int = 8


class AnswerRequest(BaseModel):
    query: str
    filters: dict[str, Any] = Field(default_factory=dict)
    limit: int = 8


class CompareRequest(BaseModel):
    query: str
    filters: dict[str, Any] = Field(default_factory=dict)
    group_by: str = "document"


class GraphRequest(BaseModel):
    seed: str
    limit: int = 25

class GraphQueryRequest(BaseModel):
    query: str
    mode: str = "auto"
    max_nodes: int = 50
    max_hops: int = 3
    answer_id: str | None = None


class FactReviewRequest(BaseModel):
    decision: str
    comment: str | None = None
    confidence_override: float | None = None
    actor: str = "demo-curator"


class SavedQueryRequest(BaseModel):
    query: str
    filters: dict[str, Any] = Field(default_factory=dict)
    alert_enabled: bool = False
    owner: str = "demo-user"


class SubscriptionRequest(BaseModel):
    name: str
    query: dict[str, Any]
    owner: str = "demo-user"
    active: bool = True


class ExportRequest(BaseModel):
    query: str
    filters: dict[str, Any] = Field(default_factory=dict)
    format: str = "markdown"


class ContradictionResolveRequest(BaseModel):
    signature: str
    left_fact_id: str
    right_fact_id: str
    decision: str
    comment: str | None = None
    actor: str = "demo-curator"


class SourceSummary(BaseModel):
    id: str
    name: str
    source_type: str
    source_mode: str
    status: str
    document_count: int = 0


class DocumentSummary(BaseModel):
    id: str
    filename: str
    source_type: str
    parse_status: str
    ingest_status: str
    language: str | None = None
    chunk_count: int = 0
    warnings: list[str] = Field(default_factory=list)


class JobSummary(BaseModel):
    id: str
    kind: str
    status: str
    stage: str
    progress: float
    stats: dict[str, Any] = Field(default_factory=dict)
    error_message: str | None = None
    created_at: datetime | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None


class ParsedFragment(BaseModel):
    fragment_type: str
    text: str
    page_number: int | None = None
    section_title: str | None = None
    ordinal: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)


class ParsedDocument(BaseModel):
    title: str
    language: str
    page_count: int = 0
    fragments: list[ParsedFragment] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ExtractedFact(BaseModel):
    subject: str
    subject_type: str | None = None
    predicate: str
    object_value: str
    object_type: str | None = None
    numeric_value: float | None = None
    min_value: float | None = None
    max_value: float | None = None
    unit: str | None = None
    geo: str | None = None
    time_period: str | None = None
    confidence: float = 0.5
    metadata: dict[str, Any] = Field(default_factory=dict)


