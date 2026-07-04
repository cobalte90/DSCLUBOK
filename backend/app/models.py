from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, Text
from sqlalchemy.orm import declarative_base


Base = declarative_base()


class SourceConfig(Base):
    __tablename__ = "source_configs"

    id = Column(Text, primary_key=True)
    name = Column(Text, nullable=False)
    source_type = Column(Text, nullable=False)
    source_mode = Column(Text, nullable=False)
    filesystem_path = Column(Text)
    path_alias = Column(Text)
    watch_mode = Column(Text, default="manual")
    recursive = Column(Boolean, default=True)
    access_level = Column(Text, default="internal")
    tags_json = Column(Text, default="[]")
    status = Column(Text, default="active")
    source_metadata_json = Column(Text, default="{}")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class DocumentRecord(Base):
    __tablename__ = "documents"

    id = Column(Text, primary_key=True)
    source_config_id = Column(Text, ForeignKey("source_configs.id"), nullable=False)
    path = Column(Text, nullable=False)
    filename = Column(Text, nullable=False)
    extension = Column(Text, nullable=False)
    source_type = Column(Text, nullable=False)
    access_level = Column(Text, default="internal")
    file_hash = Column(Text, nullable=False)
    language = Column(Text)
    parse_status = Column(Text, default="queued")
    ingest_status = Column(Text, default="queued")
    warning_json = Column(Text, default="[]")
    source_metadata_json = Column(Text, default="{}")
    page_count = Column(Integer, default=0)
    chunk_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class SourceFragment(Base):
    __tablename__ = "fragments"

    id = Column(Text, primary_key=True)
    document_id = Column(Text, ForeignKey("documents.id"), nullable=False)
    fragment_type = Column(Text, nullable=False)
    page_number = Column(Integer)
    section_title = Column(Text)
    ordinal = Column(Integer, default=0)
    text = Column(Text, nullable=False)
    embedding_json = Column(Text, default="[]")
    metadata_json = Column(Text, default="{}")
    created_at = Column(DateTime, default=datetime.utcnow)


class EntityRecord(Base):
    __tablename__ = "entities"

    id = Column(Text, primary_key=True)
    canonical_name = Column(Text, nullable=False)
    entity_type = Column(Text, nullable=False)
    aliases_json = Column(Text, default="[]")
    metadata_json = Column(Text, default="{}")
    created_at = Column(DateTime, default=datetime.utcnow)


class FactRecord(Base):
    __tablename__ = "facts"

    id = Column(Text, primary_key=True)
    document_id = Column(Text, ForeignKey("documents.id"), nullable=False)
    fragment_id = Column(Text, ForeignKey("fragments.id"), nullable=False)
    subject = Column(Text, nullable=False)
    subject_type = Column(Text)
    predicate = Column(Text, nullable=False)
    object_value = Column(Text, nullable=False)
    object_type = Column(Text)
    numeric_value = Column(Float)
    min_value = Column(Float)
    max_value = Column(Float)
    unit = Column(Text)
    geo = Column(Text)
    time_period = Column(Text)
    confidence = Column(Float, default=0.5)
    verification_status = Column(Text, default="extracted")
    review_comment = Column(Text)
    metadata_json = Column(Text, default="{}")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ExperimentPassportRecord(Base):
    __tablename__ = "experiment_passports"

    id = Column(Text, primary_key=True)
    document_id = Column(Text, ForeignKey("documents.id"), nullable=False)
    fragment_id = Column(Text, ForeignKey("fragments.id"), nullable=False)
    title = Column(Text, nullable=False)
    material = Column(Text)
    process = Column(Text)
    regime = Column(Text)
    result_summary = Column(Text)
    metadata_json = Column(Text, default="{}")
    created_at = Column(DateTime, default=datetime.utcnow)


class ReferenceEntryRecord(Base):
    __tablename__ = "reference_entries"

    id = Column(Text, primary_key=True)
    document_id = Column(Text, ForeignKey("documents.id"), nullable=False)
    entry_type = Column(Text, nullable=False)
    canonical_key = Column(Text, nullable=False)
    display_value = Column(Text, nullable=False)
    unit = Column(Text)
    aliases_json = Column(Text, default="[]")
    metadata_json = Column(Text, default="{}")
    created_at = Column(DateTime, default=datetime.utcnow)


class JobRecord(Base):
    __tablename__ = "jobs"

    id = Column(Text, primary_key=True)
    kind = Column(Text, nullable=False)
    source_config_ids_json = Column(Text, default="[]")
    document_ids_json = Column(Text, default="[]")
    extraction_profile = Column(Text, default="default")
    status = Column(Text, default="queued")
    stage = Column(Text, default="queued")
    progress = Column(Float, default=0.0)
    stats_json = Column(Text, default="{}")
    error_message = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    started_at = Column(DateTime)
    finished_at = Column(DateTime)


class SavedQueryRecord(Base):
    __tablename__ = "saved_queries"

    id = Column(Text, primary_key=True)
    owner = Column(Text, default="demo-user")
    query_text = Column(Text, nullable=False)
    filters_json = Column(Text, default="{}")
    alert_enabled = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class SubscriptionRecord(Base):
    __tablename__ = "subscriptions"

    id = Column(Text, primary_key=True)
    owner = Column(Text, default="demo-user")
    name = Column(Text, nullable=False)
    query_json = Column(Text, default="{}")
    active = Column(Boolean, default=True)
    last_triggered_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)


class AuditEventRecord(Base):
    __tablename__ = "audit_events"

    id = Column(Text, primary_key=True)
    actor = Column(Text, default="system")
    action = Column(Text, nullable=False)
    object_type = Column(Text, nullable=False)
    object_id = Column(Text, nullable=False)
    payload_json = Column(Text, default="{}")
    created_at = Column(DateTime, default=datetime.utcnow)