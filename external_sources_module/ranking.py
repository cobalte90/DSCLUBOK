from __future__ import annotations

import re
from datetime import datetime
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

from .models import ExternalSourceHit

_TRACKING_PARAMS = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "ref", "fbclid", "gclid"}

_QUALITY_BY_CONNECTOR = {
    "crossref": 0.9,
    "openalex": 0.85,
    "google_patents": 0.85,
    "springer": 0.9,
    "sciencedirect": 0.9,
    "wiley": 0.85,
    "semantic_scholar": 0.8,
    "mdpi": 0.7,
    "cyberleninka": 0.55,
    "elibrary": 0.55,
    "researchgate": 0.45,
}


def canonical_url(url: str) -> str:
    parts = urlsplit(url)
    query = [(k, v) for k, v in parse_qsl(parts.query) if k.lower() not in _TRACKING_PARAMS]
    return urlunsplit((parts.scheme, parts.netloc, parts.path.rstrip("/"), urlencode(query), ""))


def normalize_title(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", title.lower()).strip()


def dedup_key(hit: ExternalSourceHit) -> str:
    if hit.doi:
        return f"doi:{hit.doi.lower().strip()}"
    if hit.patent_number:
        return f"patent:{re.sub(r'[^A-Za-z0-9]', '', hit.patent_number).upper()}"
    if hit.url:
        return f"url:{canonical_url(hit.url)}"
    return f"title:{normalize_title(hit.title)}:{hit.year or ''}"


def lexical_relevance(query: str, hit: ExternalSourceHit) -> float:
    q_terms = set(normalize_title(query).split())
    if not q_terms:
        return 0.0
    haystack = normalize_title(f"{hit.title} {hit.snippet or ''}")
    hay_terms = set(haystack.split())
    if not hay_terms:
        return 0.0
    overlap = len(q_terms & hay_terms)
    return min(1.0, overlap / max(1, len(q_terms)))


def recency_score(hit: ExternalSourceHit) -> float:
    if not hit.year:
        return 0.3
    age = datetime.now().year - hit.year
    if age <= 1:
        return 1.0
    if age <= 3:
        return 0.85
    if age <= 6:
        return 0.65
    if age <= 12:
        return 0.4
    return 0.2


def metadata_completeness(hit: ExternalSourceHit) -> float:
    fields = [hit.doi or hit.patent_number, hit.authors, hit.year, hit.journal or hit.publisher, hit.snippet]
    present = sum(1 for f in fields if f)
    return present / len(fields)


def access_bonus(hit: ExternalSourceHit) -> float:
    return {
        "full_text_available": 1.0,
        "abstract_available": 0.6,
        "metadata_only": 0.3,
        "restricted": 0.0,
    }.get(hit.access_status, 0.2)


def score_hit(query: str, hit: ExternalSourceHit) -> tuple[float, float]:
    """Returns (relevance_score, quality_score) per the v1 formula in spec section 7."""
    lex = lexical_relevance(query, hit)
    quality = _QUALITY_BY_CONNECTOR.get(hit.connector_id, 0.5)
    final = (
        0.50 * lex
        + 0.20 * quality
        + 0.15 * recency_score(hit)
        + 0.10 * metadata_completeness(hit)
        + 0.05 * access_bonus(hit)
    )
    return round(min(1.0, final), 4), quality


def dedup_and_rank(query: str, hits: list[ExternalSourceHit], limit: int) -> list[ExternalSourceHit]:
    seen: dict[str, ExternalSourceHit] = {}
    for hit in hits:
        relevance, quality = score_hit(query, hit)
        hit.relevance_score = relevance
        hit.quality_score = quality
        key = dedup_key(hit)
        existing = seen.get(key)
        if existing is None or hit.relevance_score > existing.relevance_score:
            seen[key] = hit
    ranked = sorted(seen.values(), key=lambda h: h.relevance_score, reverse=True)
    return ranked[:limit]
