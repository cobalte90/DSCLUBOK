from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy.orm import Session

from .config import settings
from .repository import create_source_config, find_existing_document, register_document
from .utils import filesystem_display_name


def bootstrap_manifest(session: Session, manifest_path: Path) -> tuple[str | None, list[str], dict]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    source_ids: list[str] = []
    document_count = 0
    reused_document_count = 0
    missing_paths: list[str] = []

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
            tags=item.get("tags", []),
            source_metadata={
                "manifest_import": True,
                "manifest_name": manifest.get("name"),
                "manifest_description": manifest.get("description"),
            },
        )
        source_ids.append(source.id)

        for relative_path in item["documents"]:
            path = _resolve_manifest_path(relative_path)
            if not path.exists():
                missing_paths.append(relative_path)
                continue
            existing = find_existing_document(session, source=source, path=path)
            if existing:
                reused_document_count += 1
                continue
            register_document(session, source=source, path=path, force=False)
            document_count += 1

    payload = {
        "manifest_name": manifest.get("name"),
        "description": manifest.get("description"),
        "document_count": document_count,
        "reused_document_count": reused_document_count,
        "missing_paths": missing_paths,
        "source_count": len(source_ids),
        "scenario_count": len(manifest.get("scenarios", [])),
    }
    return manifest.get("name"), source_ids, payload


def _resolve_manifest_path(relative_path: str) -> Path:
    path = Path.cwd() / relative_path
    if path.exists():
        return path

    raw_path = Path(relative_path)
    if raw_path.exists():
        return raw_path

    parts = raw_path.parts
    if parts and parts[0] == "Источники информации":
        remapped = _resolve_corpus_parts(parts[1:])
        if remapped.exists():
            return remapped

    return path


def _resolve_corpus_parts(parts: tuple[str, ...]) -> Path:
    current = settings.corpus_dir
    for part in parts:
        candidate = current / part
        if candidate.exists():
            current = candidate
            continue
        matched = None
        if current.exists() and current.is_dir():
            for child in current.iterdir():
                if filesystem_display_name(child) == part:
                    matched = child
                    break
        if matched is None:
            return candidate
        current = matched
    return current
