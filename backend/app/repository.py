from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Iterable

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from .models import AuditEventRecord, DocumentRecord, EntityRecord, ExperimentPassportRecord, FactRecord, JobRecord, ReferenceEntryRecord, SavedQueryRecord, SourceConfig, SourceFragment, SubscriptionRecord
from .source_registry import SOURCE_TYPE_REGISTRY
from .config import settings
from .utils import db_safe_text, ensure_filesystem_alias, file_sha256, filesystem_display_name, json_dumps, json_loads, new_id


SOURCE_TYPE_BASE_SCORES = {
    "reference_catalog": 0.93,
    "experiment_protocol": 0.9,
    "patent_regulation": 0.84,
    "internal_report": 0.81,
    "expert_directory": 0.8,
    "taxonomy_catalog": 0.79,
    "article_review": 0.76,
}


def find_existing_source_config(session: Session, *, name: str, source_type: str, source_mode: str, filesystem_path: str | None, path_alias: str | None, source_metadata: dict) -> SourceConfig | None:
    if filesystem_path:
        existing = session.scalar(select(SourceConfig).where(SourceConfig.filesystem_path == filesystem_path, SourceConfig.source_type == source_type))
        if existing:
            return existing
    manifest_name = source_metadata.get("manifest_name")
    if source_mode == "manifest_import" and manifest_name:
        for item in session.scalars(select(SourceConfig).where(SourceConfig.name == name, SourceConfig.source_type == source_type, SourceConfig.source_mode == source_mode)).all():
            metadata = json_loads(item.source_metadata_json, {})
            if metadata.get("manifest_name") == manifest_name:
                return item
    if path_alias:
        existing = session.scalar(select(SourceConfig).where(SourceConfig.path_alias == path_alias, SourceConfig.source_type == source_type, SourceConfig.source_mode == source_mode))
        if existing:
            return existing
    return None


def create_source_config(session: Session, *, name: str, source_type: str, source_mode: str, filesystem_path: str | None, path_alias: str | None, watch_mode: str, recursive: bool, access_level: str, tags: list[str], source_metadata: dict) -> SourceConfig:
    existing = find_existing_source_config(
        session,
        name=name,
        source_type=source_type,
        source_mode=source_mode,
        filesystem_path=filesystem_path,
        path_alias=path_alias,
        source_metadata=source_metadata,
    )
    if existing:
        existing.name = name
        existing.watch_mode = watch_mode
        existing.recursive = recursive
        existing.access_level = access_level
        existing.tags_json = json_dumps(tags)
        existing.source_metadata_json = json_dumps(source_metadata)
        session.flush()
        return existing

    source = SourceConfig(
        id=new_id("src"),
        name=name,
        source_type=source_type,
        source_mode=source_mode,
        filesystem_path=filesystem_path,
        path_alias=path_alias,
        watch_mode=watch_mode,
        recursive=recursive,
        access_level=access_level,
        tags_json=json_dumps(tags),
        source_metadata_json=json_dumps(source_metadata),
    )
    session.add(source)
    session.flush()
    return source


def find_existing_document(session: Session, *, source: SourceConfig, path: Path) -> DocumentRecord | None:
    file_hash = file_sha256(path)
    return session.scalar(select(DocumentRecord).where(DocumentRecord.file_hash == file_hash, DocumentRecord.source_type == source.source_type, DocumentRecord.source_config_id == source.id))


def register_document(session: Session, *, source: SourceConfig, path: Path, force: bool = False) -> DocumentRecord:
    file_hash = file_sha256(path)
    existing = session.scalar(select(DocumentRecord).where(DocumentRecord.file_hash == file_hash, DocumentRecord.source_type == source.source_type, DocumentRecord.source_config_id == source.id))
    if existing and not force:
        return existing
    try:
        stored_path = ensure_filesystem_alias(path, settings.storage_dir / "document_aliases", is_dir=False)
    except OSError:
        stored_path = path
    display_name = filesystem_display_name(path, "document")
    display_suffix = Path(display_name).suffix.lower().lstrip(".")
    document = DocumentRecord(
        id=new_id("doc"),
        source_config_id=source.id,
        path=db_safe_text(stored_path),
        filename=display_name,
        extension=db_safe_text(display_suffix or path.suffix.lower().lstrip("."), ""),
        source_type=source.source_type,
        access_level=source.access_level,
        file_hash=file_hash,
        source_metadata_json=source.source_metadata_json,
    )
    session.add(document)
    session.flush()
    return document


def list_sources(session: Session) -> list[dict]:
    sources = session.scalars(select(SourceConfig).order_by(SourceConfig.created_at.desc())).all()
    result = []
    for source in sources:
        documents = list_documents_for_source(session, source.id)
        document_ids = [document.id for document in documents]
        fact_count = session.scalar(select(func.count()).select_from(FactRecord).where(FactRecord.document_id.in_(document_ids))) if document_ids else 0
        fragment_count = session.scalar(select(func.count()).select_from(SourceFragment).where(SourceFragment.document_id.in_(document_ids))) if document_ids else 0
        quality = _source_quality_score(source.source_type, len(documents), int(fact_count or 0), int(fragment_count or 0))
        result.append({
            "id": source.id,
            "name": source.name,
            "source_type": source.source_type,
            "source_mode": source.source_mode,
            "status": source.status,
            "document_count": len(documents),
            "fact_count": int(fact_count or 0),
            "fragment_count": int(fragment_count or 0),
            "quality_score": quality["score"],
            "quality_label": quality["label"],
            "allowed_formats": SOURCE_TYPE_REGISTRY[source.source_type].allowed_formats,
        })
    return result


def get_source(session: Session, source_id: str) -> SourceConfig | None:
    return session.get(SourceConfig, source_id)


def create_job(session: Session, *, kind: str, source_ids: list[str], document_ids: list[str], extraction_profile: str) -> JobRecord:
    job = JobRecord(id=new_id("job"), kind=kind, source_config_ids_json=json_dumps(source_ids), document_ids_json=json_dumps(document_ids), extraction_profile=extraction_profile)
    session.add(job)
    session.flush()
    return job


def get_job(session: Session, job_id: str) -> JobRecord | None:
    return session.get(JobRecord, job_id)


def set_job_state(session: Session, job: JobRecord, *, status: str, stage: str, progress: float, stats: dict | None = None, error_message: str | None = None) -> None:
    job.status = status
    job.stage = stage
    job.progress = progress
    if stats is not None:
        job.stats_json = json_dumps(stats)
    job.error_message = error_message


def store_fragments(session: Session, document_id: str, fragments: list[dict]) -> list[SourceFragment]:
    session.query(SourceFragment).filter(SourceFragment.document_id == document_id).delete()
    stored = []
    for index, fragment in enumerate(fragments, start=1):
        item = SourceFragment(id=new_id("frag"), document_id=document_id, fragment_type=fragment["fragment_type"], page_number=fragment.get("page_number"), section_title=fragment.get("section_title"), ordinal=index, text=fragment["text"], embedding_json=json_dumps(fragment["embedding"]), metadata_json=json_dumps(fragment.get("metadata", {})))
        session.add(item)
        stored.append(item)
    session.flush()
    return stored


def store_entities(session: Session, entities: Iterable[dict]) -> None:
    for entity in entities:
        existing = session.scalar(select(EntityRecord).where(EntityRecord.canonical_name == entity["name"], EntityRecord.entity_type == entity["type"]))
        if existing:
            continue
        session.add(EntityRecord(id=new_id("ent"), canonical_name=entity["name"], entity_type=entity["type"], aliases_json=json_dumps(entity.get("aliases", [])), metadata_json=json_dumps(entity.get("metadata", {}))))


def replace_facts(session: Session, document_id: str, facts: list[dict]) -> None:
    session.query(FactRecord).filter(FactRecord.document_id == document_id).delete()
    for fact in facts:
        fact_id = fact.setdefault("id", new_id("fact"))
        session.add(FactRecord(id=fact_id, document_id=document_id, fragment_id=fact["fragment_id"], subject=fact["subject"], subject_type=fact.get("subject_type"), predicate=fact["predicate"], object_value=fact["object_value"], object_type=fact.get("object_type"), numeric_value=fact.get("numeric_value"), min_value=fact.get("min_value"), max_value=fact.get("max_value"), unit=fact.get("unit"), geo=fact.get("geo"), time_period=fact.get("time_period"), confidence=fact["confidence"], verification_status="extracted", metadata_json=json_dumps(fact.get("metadata", {}))))


def replace_experiment_passports(session: Session, document_id: str, passports: list[dict]) -> None:
    session.query(ExperimentPassportRecord).filter(ExperimentPassportRecord.document_id == document_id).delete()
    for passport in passports:
        session.add(ExperimentPassportRecord(id=new_id("exp"), document_id=document_id, fragment_id=passport["fragment_id"], title=passport["title"], material=passport.get("material"), process=passport.get("process"), regime=passport.get("regime"), result_summary=passport.get("result_summary"), metadata_json=json_dumps(passport.get("metadata", {}))))


def replace_reference_entries(session: Session, document_id: str, entries: list[dict]) -> None:
    session.query(ReferenceEntryRecord).filter(ReferenceEntryRecord.document_id == document_id).delete()
    for entry in entries:
        session.add(ReferenceEntryRecord(id=new_id("ref"), document_id=document_id, entry_type=entry["entry_type"], canonical_key=entry["canonical_key"], display_value=entry["display_value"], unit=entry.get("unit"), aliases_json=json_dumps(entry.get("aliases", [])), metadata_json=json_dumps(entry.get("metadata", {}))))


def audit(session: Session, *, actor: str, action: str, object_type: str, object_id: str, payload: dict) -> None:
    session.add(AuditEventRecord(id=new_id("audit"), actor=actor, action=action, object_type=object_type, object_id=object_id, payload_json=json_dumps(payload)))


def dashboard_counts(session: Session) -> dict:
    document_count = session.scalar(select(func.count()).select_from(DocumentRecord)) or 0
    fact_count = session.scalar(select(func.count()).select_from(FactRecord)) or 0
    fragment_count = session.scalar(select(func.count()).select_from(SourceFragment)) or 0
    entity_count = session.scalar(select(func.count()).select_from(EntityRecord)) or 0
    experiment_count = session.scalar(select(func.count()).select_from(ExperimentPassportRecord)) or 0
    source_types = Counter(source_type for (source_type,) in session.execute(select(DocumentRecord.source_type)).all())
    statuses = Counter(status for (status,) in session.execute(select(DocumentRecord.ingest_status)).all())
    quality_ranking = sorted([{
        "source_id": source["id"],
        "name": source["name"],
        "source_type": source["source_type"],
        "quality_score": source["quality_score"],
        "quality_label": source["quality_label"],
        "document_count": source["document_count"],
        "fact_count": source["fact_count"],
    } for source in list_sources(session)], key=lambda item: item["quality_score"], reverse=True)[:10]
    return {
        "documents": document_count,
        "facts": fact_count,
        "fragments": fragment_count,
        "entities": entity_count,
        "experiments": experiment_count,
        "source_types": dict(source_types),
        "statuses": dict(statuses),
        "quality_ranking": quality_ranking,
        "saved_queries": len(list_saved_queries(session)),
        "subscriptions": len(list_subscriptions(session)),
        "alerts": len(list_recent_events(session, actions=["alert_triggered"], limit=50)),
    }


def list_documents_for_source(session: Session, source_id: str) -> list[DocumentRecord]:
    return session.scalars(select(DocumentRecord).where(DocumentRecord.source_config_id == source_id)).all()


def save_query(session: Session, owner: str, query_text: str, filters: dict, alert_enabled: bool) -> SavedQueryRecord:
    item = SavedQueryRecord(id=new_id("sq"), owner=owner, query_text=query_text, filters_json=json_dumps(filters), alert_enabled=alert_enabled)
    session.add(item)
    session.flush()
    return item


def list_saved_queries(session: Session) -> list[dict]:
    rows = session.scalars(select(SavedQueryRecord).order_by(desc(SavedQueryRecord.created_at))).all()
    return [{"id": row.id, "owner": row.owner, "query": row.query_text, "filters": json_loads(row.filters_json, {}), "alert_enabled": row.alert_enabled, "created_at": row.created_at.isoformat() if row.created_at else None} for row in rows]


def save_subscription(session: Session, owner: str, name: str, query: dict, active: bool) -> SubscriptionRecord:
    item = SubscriptionRecord(id=new_id("sub"), owner=owner, name=name, query_json=json_dumps(query), active=active)
    session.add(item)
    session.flush()
    return item


def list_subscriptions(session: Session) -> list[dict]:
    rows = session.scalars(select(SubscriptionRecord).order_by(desc(SubscriptionRecord.created_at))).all()
    return [{"id": row.id, "owner": row.owner, "name": row.name, "query": json_loads(row.query_json, {}), "active": row.active, "last_triggered_at": row.last_triggered_at.isoformat() if row.last_triggered_at else None, "created_at": row.created_at.isoformat() if row.created_at else None} for row in rows]


def list_recent_events(session: Session, *, actions: list[str] | None = None, limit: int = 20) -> list[dict]:
    rows = session.scalars(select(AuditEventRecord).order_by(desc(AuditEventRecord.created_at)).limit(limit)).all()
    items = []
    for row in rows:
        if actions and row.action not in actions:
            continue
        items.append({"id": row.id, "actor": row.actor, "action": row.action, "object_type": row.object_type, "object_id": row.object_id, "payload": json_loads(row.payload_json, {}), "created_at": row.created_at.isoformat() if row.created_at else None})
    return items


def _source_quality_score(source_type: str, document_count: int, fact_count: int, fragment_count: int) -> dict[str, float | str]:
    base = SOURCE_TYPE_BASE_SCORES.get(source_type, 0.74)
    density = min(0.08, fact_count / max(fragment_count, 1) * 0.2)
    breadth = min(0.05, document_count / 100)
    score = round(min(0.99, base + density + breadth), 3)
    if score >= 0.9:
        label = "high"
    elif score >= 0.8:
        label = "strong"
    elif score >= 0.7:
        label = "medium"
    else:
        label = "emerging"
    return {"score": score, "label": label}
