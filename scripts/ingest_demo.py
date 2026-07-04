from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.config import settings
from app.database import init_db, session_scope
from app.ingestion import queue_import, run_job
from app.repository import create_source_config, register_document


def main() -> None:
    init_db()
    manifest = json.loads(settings.demo_manifest.read_text(encoding="utf-8"))
    source_ids: list[str] = []
    with session_scope() as session:
        for item in manifest["sources"]:
            source = create_source_config(
                session,
                name=item["name"],
                source_type=item["source_type"],
                source_mode=item["source_mode"],
                filesystem_path=None,
                path_alias=item["name"],
                watch_mode="manual",
                recursive=True,
                access_level=item.get("access_level", "internal"),
                tags=[],
                source_metadata={"manifest_import": True},
            )
            source_ids.append(source.id)
            for relative_path in item["documents"]:
                path = Path.cwd() / relative_path
                if not path.exists():
                    path = Path(relative_path)
                register_document(session, source=source, path=path, force=True)
        job = queue_import(session, source_ids, "demo")
        job_id = job.id
    run_job(job_id)
    print(f"Demo ingest finished. Job: {job_id}")


if __name__ == "__main__":
    main()
