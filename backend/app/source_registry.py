from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SourceTypeSpec:
    key: str
    label: str
    allowed_formats: tuple[str, ...]
    parser: str
    extraction_profile: str
    graph_write_profile: str
    reingest_policy: str


SOURCE_TYPE_REGISTRY: dict[str, SourceTypeSpec] = {
    "article_review": SourceTypeSpec(
        key="article_review",
        label="Scientific Articles and Reviews",
        allowed_formats=("pdf", "docx", "doc", "docm", "txt", "md", "zip", "rar"),
        parser="document_parser",
        extraction_profile="scientific_text",
        graph_write_profile="publication_graph",
        reingest_policy="hash_dedup",
    ),
    "internal_report": SourceTypeSpec(
        key="internal_report",
        label="Internal Technical Reports",
        allowed_formats=("pdf", "docx", "doc", "docm", "pptx", "txt", "md", "zip", "rar"),
        parser="document_parser",
        extraction_profile="technical_report",
        graph_write_profile="publication_graph",
        reingest_policy="hash_dedup",
    ),
    "experiment_protocol": SourceTypeSpec(
        key="experiment_protocol",
        label="Experiment Protocols",
        allowed_formats=("pdf", "docx", "xlsx", "xls", "json", "csv", "txt", "zip", "rar"),
        parser="experiment_parser",
        extraction_profile="experiment_protocol",
        graph_write_profile="experiment_graph",
        reingest_policy="hash_dedup",
    ),
    "patent_regulation": SourceTypeSpec(
        key="patent_regulation",
        label="Patent and Regulation",
        allowed_formats=("pdf", "docx", "doc", "docm", "json", "txt", "md", "zip", "rar"),
        parser="document_parser",
        extraction_profile="patent_regulation",
        graph_write_profile="publication_graph",
        reingest_policy="hash_dedup",
    ),
    "reference_catalog": SourceTypeSpec(
        key="reference_catalog",
        label="Reference Catalogs",
        allowed_formats=("xlsx", "xls", "json", "csv", "pdf", "txt", "zip", "rar"),
        parser="reference_parser",
        extraction_profile="reference_catalog",
        graph_write_profile="reference_graph",
        reingest_policy="replace_by_key",
    ),
    "expert_directory": SourceTypeSpec(
        key="expert_directory",
        label="Expert Directory",
        allowed_formats=("json", "xlsx", "xls", "docx", "txt", "csv", "zip", "rar"),
        parser="directory_parser",
        extraction_profile="expert_directory",
        graph_write_profile="expert_graph",
        reingest_policy="replace_by_key",
    ),
    "taxonomy_catalog": SourceTypeSpec(
        key="taxonomy_catalog",
        label="Taxonomy Catalog",
        allowed_formats=("json", "xlsx", "xls", "csv", "txt", "zip", "rar"),
        parser="taxonomy_parser",
        extraction_profile="taxonomy_catalog",
        graph_write_profile="taxonomy_graph",
        reingest_policy="replace_by_key",
    ),
}


INGEST_STATUSES = (
    "queued",
    "parsing",
    "chunking",
    "extracting",
    "resolving",
    "graph_writing",
    "indexed",
    "done",
    "partial",
    "failed",
    "metadata_only",
    "needs_ocr",
)
