from __future__ import annotations

from sqlalchemy.orm import Session

from .config import settings
from .ingestion import queue_import, run_job
from .manifest_bootstrap import bootstrap_manifest


def bootstrap_curated(session: Session) -> tuple[str, dict]:
    _, source_ids, payload = bootstrap_manifest(session, settings.curated_manifest)
    job = queue_import(session, source_ids, "curated")
    payload["job_id"] = job.id
    return job.id, payload


def bootstrap_curated_and_run(session: Session) -> tuple[str, dict]:
    job_id, payload = bootstrap_curated(session)
    session.flush()
    session.commit()
    run_job(job_id)
    return job_id, payload
