from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .database import session_scope
from .extraction import extract_facts
from .graph_store import graph_store
from .models import DocumentRecord, JobRecord, SourceConfig
from .parsers import parse_document
from .repository import audit, create_job, get_source, list_documents_for_source, register_document, replace_experiment_passports, replace_facts, replace_reference_entries, set_job_state, store_entities, store_fragments
from .source_registry import SOURCE_TYPE_REGISTRY
from .utils import hashed_embedding, json_dumps, json_loads


def scan_sources(session: Session, source_ids: list[str] | None = None) -> dict[str, Any]:
    if source_ids:
        source_records = [source for source_id in source_ids if (source := get_source(session, source_id))]
    else:
        source_records = session.scalars(select(SourceConfig)).all()
    discovered = []
    for source in source_records:
        if not source.filesystem_path:
            continue
        root = Path(source.filesystem_path)
        if not root.exists():
            continue
        pattern = "**/*" if source.recursive else "*"
        for path in root.glob(pattern):
            if not path.is_file():
                continue
            spec = SOURCE_TYPE_REGISTRY[source.source_type]
            extension = path.suffix.lower().lstrip(".")
            if extension not in spec.allowed_formats:
                continue
            document = register_document(session, source=source, path=path)
            discovered.append(document.id)
    return {"discovered_document_ids": discovered, "count": len(discovered)}


def queue_import(session: Session, source_ids: list[str], extraction_profile: str) -> JobRecord:
    document_ids: list[str] = []
    for source_id in source_ids:
        document_ids.extend([document.id for document in list_documents_for_source(session, source_id)])
    return create_job(session, kind="import", source_ids=source_ids, document_ids=document_ids, extraction_profile=extraction_profile)


def run_job(job_id: str) -> None:
    with session_scope() as session:
        job = session.get(JobRecord, job_id)
        if not job:
            return
        job.status = "running"
        job.stage = "parsing"
        job.progress = 0.05
        job.started_at = datetime.utcnow()
        session.flush()

        document_ids = json_loads(job.document_ids_json, [])
        total = max(len(document_ids), 1)
        processed = 0
        fact_count = 0
        fragment_count = 0
        warnings: list[str] = []

        for document_id in document_ids:
            document = session.get(DocumentRecord, document_id)
            if not document:
                continue
            try:
                _process_document(session, document)
                processed += 1
                fact_count += session.scalar(select(DocumentRecord.chunk_count).where(DocumentRecord.id == document_id)) or 0
                fragment_count += document.chunk_count
                set_job_state(session, job, status="running", stage=document.ingest_status, progress=0.1 + 0.8 * processed / total, stats={"documents_processed": processed, "documents_total": total, "fragment_count": fragment_count})
                session.flush()
            except Exception as exc:  # pragma: no cover
                document.ingest_status = "failed"
                document.parse_status = "failed"
                warning_list = json_loads(document.warning_json, [])
                warning_list.append(str(exc))
                document.warning_json = json_dumps(warning_list)
                warnings.append(f"{document.filename}: {exc}")
                session.flush()

        job.status = "done" if not warnings else "partial"
        job.stage = "done" if not warnings else "partial"
        job.progress = 1.0
        job.finished_at = datetime.utcnow()
        job.stats_json = json_dumps({"documents_processed": processed, "documents_total": total, "fragment_count": fragment_count, "warnings": warnings, "fact_count": fact_count})


def _process_document(session: Session, document: DocumentRecord) -> None:
    path = Path(document.path)
    document.parse_status = "parsing"
    document.ingest_status = "parsing"
    parsed = parse_document(path)
    document.language = parsed.language
    document.page_count = parsed.page_count
    document.warning_json = json_dumps(parsed.warnings)

    fragment_payloads = [{
        "fragment_type": fragment.fragment_type,
        "text": fragment.text,
        "page_number": fragment.page_number,
        "section_title": fragment.section_title,
        "metadata": fragment.metadata,
        "embedding": hashed_embedding(fragment.text),
    } for fragment in parsed.fragments]
    stored_fragments = store_fragments(session, document.id, fragment_payloads)
    document.chunk_count = len(stored_fragments)

    ingest_mode = parsed.metadata.get("mode")
    if not stored_fragments:
        document.parse_status = "parsed"
        if ingest_mode == "needs_ocr":
            document.ingest_status = "needs_ocr"
        elif ingest_mode == "staged_import":
            document.ingest_status = "partial"
        else:
            document.ingest_status = "metadata_only"
        audit(session, actor="system", action="document_ingested", object_type="document", object_id=document.id, payload={"filename": document.filename, "source_type": document.source_type, "graph_enabled": False, "graph_success": False, "ingest_status": document.ingest_status, "parser_mode": ingest_mode})
        return

    document.parse_status = "chunking"
    document.ingest_status = "extracting"
    facts, entities = extract_facts(parsed, document.source_type)
    store_entities(session, entities)

    fact_payloads = []
    references = []
    for index, fact in enumerate(facts):
        fragment = stored_fragments[min(index, len(stored_fragments) - 1)] if stored_fragments else None
        if not fragment:
            continue
        payload = fact.model_dump()
        payload["fragment_id"] = fragment.id
        fact_payloads.append(payload)
        if document.source_type in {"reference_catalog", "taxonomy_catalog", "expert_directory"}:
            references.append({
                "entry_type": document.source_type,
                "canonical_key": payload["subject"],
                "display_value": payload["object_value"],
                "unit": payload.get("unit"),
                "aliases": [],
                "metadata": payload.get("metadata", {}),
            })

    passports = _build_experiment_passports(document, parsed, stored_fragments, fact_payloads)

    replace_facts(session, document.id, fact_payloads)
    replace_experiment_passports(session, document.id, passports)
    replace_reference_entries(session, document.id, references)

    graph_result = graph_store.write_document_graph(
        document={"id": document.id, "filename": document.filename, "source_type": document.source_type, "language": document.language, "path": document.path, "access_level": document.access_level},
        fragments=[{"id": fragment.id, "document_id": document.id, "fragment_type": fragment.fragment_type, "page_number": fragment.page_number, "ordinal": fragment.ordinal, "text": fragment.text} for fragment in stored_fragments],
        facts=[{**fact, "document_id": document.id, "verification_status": "extracted"} for fact in fact_payloads],
    )

    warning_list = json_loads(document.warning_json, [])
    warning_list.extend(graph_result.warnings)
    document.warning_json = json_dumps(warning_list)
    document.parse_status = "parsed"
    document.ingest_status = "done"
    audit(session, actor="system", action="document_ingested", object_type="document", object_id=document.id, payload={"filename": document.filename, "source_type": document.source_type, "graph_enabled": graph_result.enabled, "graph_success": graph_result.success, "ingest_status": document.ingest_status, "fact_count": len(fact_payloads)})


def _build_experiment_passports(document: DocumentRecord, parsed, stored_fragments, fact_payloads: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if document.source_type != "experiment_protocol":
        return []

    title = document.filename
    material = None
    process = None
    regime_parts: list[str] = []
    result_parts: list[str] = []
    chosen_fragment_id = stored_fragments[0].id if stored_fragments else None

    for fragment, stored in zip(parsed.fragments, stored_fragments):
        entry_type = (fragment.metadata or {}).get("entry_type")
        if entry_type == "material" and not material:
            material = fragment.text.split(":", 1)[-1].strip()
            chosen_fragment_id = stored.id
        elif entry_type == "process" and not process:
            process = fragment.text.split(":", 1)[-1].strip()
            chosen_fragment_id = stored.id
        elif entry_type == "regime":
            regime_parts.append(fragment.text)
        elif entry_type == "result":
            result_parts.append(fragment.text)

    if not material:
        for fact in fact_payloads:
            if fact.get("predicate") == "USES_MATERIAL":
                material = fact.get("object_value")
                break
    if not process:
        for fact in fact_payloads:
            if fact.get("predicate") == "DESCRIBED_IN" and fact.get("object_type") == "Process":
                process = fact.get("object_value")
                break

    if not chosen_fragment_id:
        return []

    return [{
        "fragment_id": chosen_fragment_id,
        "title": title,
        "material": material,
        "process": process,
        "regime": "; ".join(regime_parts)[:500] if regime_parts else None,
        "result_summary": "; ".join(result_parts)[:500] if result_parts else None,
        "metadata": {"source_type": document.source_type, "parser": parsed.metadata.get("parser")},
    }]
