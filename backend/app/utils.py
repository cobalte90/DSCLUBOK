from __future__ import annotations

import hashlib
import json
import math
import os
import re
import uuid
from pathlib import Path
from typing import Any


TOKEN_RE = re.compile(r"[A-Za-zА-Яа-яЁё0-9_+\-]{2,}")
SAFE_SLUG_RE = re.compile(r"[^A-Za-z0-9_.-]+")


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


def file_sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            chunk = fh.read(1024 * 1024)
            if not chunk:
                break
            hasher.update(chunk)
    return hasher.hexdigest()


def db_safe_text(value: object, fallback: str = "") -> str:
    """Return text that can always be encoded by UTF-8 DB drivers."""
    text = str(value) if value is not None else fallback
    safe = text.encode("utf-8", "replace").decode("utf-8")
    return safe or fallback


def filesystem_display_name(path: Path, fallback: str = "item") -> str:
    """Recover readable names from files uploaded with legacy Windows encodings."""
    raw = os.fsencode(path.name)
    for encoding in ("utf-8", "cp1251"):
        try:
            value = raw.decode(encoding)
            if value:
                return db_safe_text(value, fallback)
        except UnicodeDecodeError:
            continue
    return db_safe_text(path.name, fallback)


def path_fingerprint(path: Path) -> str:
    return hashlib.sha1(os.fsencode(path)).hexdigest()


def safe_slug(value: object, fallback: str = "item", max_length: int = 72) -> str:
    slug = SAFE_SLUG_RE.sub("_", db_safe_text(value, fallback)).strip("._")
    return (slug[:max_length].strip("._") or fallback)


def ensure_filesystem_alias(path: Path, alias_root: Path, *, is_dir: bool) -> Path:
    """Create a stable ASCII symlink to paths whose names may be DB-unsafe."""
    alias_root.mkdir(parents=True, exist_ok=True)
    extension = ""
    if not is_dir:
        display_suffix = Path(filesystem_display_name(path, "")).suffix.lower()
        raw_suffix = display_suffix or path.suffix.lower()
        suffix_body = safe_slug(raw_suffix.lstrip("."), "", 16)
        extension = f".{suffix_body}" if suffix_body else ""
    alias_name = f"{path_fingerprint(path)[:20]}_{safe_slug(path.stem if not is_dir else path.name)}{extension}"
    alias = alias_root / alias_name
    if alias.exists() or alias.is_symlink():
        return alias
    os.symlink(path, alias, target_is_directory=is_dir)
    return alias


def json_dumps(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False)


def json_loads(data: str | None, default: Any) -> Any:
    if not data:
        return default
    try:
        return json.loads(data)
    except json.JSONDecodeError:
        return default


def normalize_text(text: str) -> str:
    normalized = (text or "").replace("\x00", " ").replace("\u00a0", " ")
    normalized = normalized.replace("–", "-").replace("—", "-")
    return " ".join(normalized.split())


def tokenize(text: str) -> list[str]:
    return [token.lower() for token in TOKEN_RE.findall(normalize_text(text))]


def detect_language(text: str) -> str:
    normalized = normalize_text(text)
    cyrillic = sum(1 for ch in normalized if "А" <= ch <= "я" or ch in "Ёё")
    latin = sum(1 for ch in normalized if ("A" <= ch <= "Z") or ("a" <= ch <= "z"))
    if cyrillic >= latin:
        return "ru"
    return "en"


def hashed_embedding(text: str, dimensions: int = 64) -> list[float]:
    vector = [0.0] * dimensions
    tokens = tokenize(text)
    if not tokens:
        return vector
    for token in tokens:
        bucket = int(hashlib.sha1(token.encode("utf-8")).hexdigest(), 16) % dimensions
        vector[bucket] += 1.0
    norm = math.sqrt(sum(value * value for value in vector)) or 1.0
    return [value / norm for value in vector]


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    return sum(a * b for a, b in zip(left, right))


def clamp_confidence(value: float) -> float:
    return max(0.0, min(1.0, round(value, 4)))
