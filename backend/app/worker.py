from __future__ import annotations

import time

from sqlalchemy import select

from .database import init_db, session_scope
from .ingestion import run_job
from .models import JobRecord


def main() -> None:
    init_db()
    while True:
        with session_scope() as session:
            queued_job = session.scalars(select(JobRecord).where(JobRecord.status == "queued").order_by(JobRecord.created_at.asc())).first()
            job_id = queued_job.id if queued_job else None
        if job_id:
            run_job(job_id)
        time.sleep(3)


if __name__ == "__main__":
    main()
