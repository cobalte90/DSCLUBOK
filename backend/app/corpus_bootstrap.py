from __future__ import annotations

from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import settings
from .repository import create_source_config
from .models import SourceConfig
from .utils import db_safe_text, ensure_filesystem_alias, filesystem_display_name


CORPUS_SOURCE_MAP = {
    "Доклады": "internal_report",
    "Статьи": "article_review",
    "Журналы": "article_review",
    "Материалы конференций": "article_review",
}


def bootstrap_local_corpus(session: Session) -> dict[str, object]:
    root = settings.corpus_dir
    if not root.exists():
        return {"source_ids": [], "registered": 0, "corpus_dir": db_safe_text(root), "warnings": ["Corpus directory does not exist."]}

    source_ids: list[str] = []
    registered = 0
    warnings: list[str] = []
    alias_root = settings.storage_dir / "corpus_aliases"

    for child in sorted(root.iterdir(), key=lambda item: db_safe_text(item.name)):
        if not child.is_dir():
            continue
        safe_name = filesystem_display_name(child, "corpus-source")
        source_type = CORPUS_SOURCE_MAP.get(safe_name, "internal_report")
        try:
            safe_path = db_safe_text(ensure_filesystem_alias(child, alias_root, is_dir=True))
        except OSError as exc:
            warnings.append(f"Skipped corpus folder {safe_name}: cannot create filesystem alias ({exc}).")
            continue
        existing = session.scalar(select(SourceConfig).where(SourceConfig.filesystem_path == safe_path))
        if existing:
            source_ids.append(existing.id)
            continue
        source = create_source_config(
            session,
            name=safe_name,
            source_type=source_type,
            source_mode="watched_import_folder",
            filesystem_path=safe_path,
            path_alias=safe_name,
            watch_mode="manual",
            recursive=True,
            access_level="internal",
            tags=["real-corpus", safe_name],
            source_metadata={"bootstrap": "local_corpus", "root": db_safe_text(root), "original_name": safe_name},
        )
        source_ids.append(source.id)
        registered += 1

    if not source_ids:
        warnings.append("No corpus folders were registered.")
    return {"source_ids": source_ids, "registered": registered, "corpus_dir": db_safe_text(root), "warnings": warnings}
