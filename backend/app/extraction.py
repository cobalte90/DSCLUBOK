from __future__ import annotations

import re
from collections import defaultdict

from .ontology import DEFAULT_SYNONYMS, DEFAULT_UNITS, ENTITY_HINTS
from .schemas import ExtractedFact, ParsedDocument, ParsedFragment
from .utils import clamp_confidence, normalize_text


NUMERIC_RE = re.compile(
    r"(?P<left>\d+(?:[.,]\d+)?)\s*(?:[-–—]\s*(?P<right>\d+(?:[.,]\d+)?))?\s*(?P<unit>мг/л|мг/дм3|г/л|°с|°c|а/м2|а/дм2|т/сут|%)",
    re.IGNORECASE,
)
YEAR_RE = re.compile(r"\b(?:19|20)\d{2}\b")
KEY_VALUE_RE = re.compile(r"([\w_а-яА-Я/-]+)\s*:\s*([^;]+)")

SUBJECT_PATTERNS = [
    ("temperature", ["температур", "temperature"]),
    ("sulfates", ["сульфат", "sulfate"]),
    ("current_density", ["плотность тока", "current density", "а/м2", "а/дм2", "current_density"]),
    ("flow_rate", ["скорость", "расход", "flow rate"]),
    ("recovery", ["извлеч", "recovery"]),
    ("nickel_content", ["никель", "ni ", "ni,"]),
    ("copper_content", ["медь", "cu ", "cu,"]),
]


def extract_facts(parsed: ParsedDocument, source_type: str) -> tuple[list[ExtractedFact], list[dict[str, str]]]:
    facts: list[ExtractedFact] = []
    entity_candidates: dict[str, set[str]] = defaultdict(set)

    for fragment in parsed.fragments:
        facts.extend(_extract_structured_facts(fragment, source_type, parsed.title))
        detected = _detect_terms(fragment)
        facts.extend(_extract_numeric_facts(fragment, detected))
        facts.extend(_extract_relation_facts(fragment, detected))
        _extract_entity_hints(fragment, entity_candidates)

    if source_type == "experiment_protocol":
        for fragment in parsed.fragments[:12]:
            lowered = normalize_text(fragment.text).lower()
            if "опыт" in lowered or "experiment" in lowered or "проба" in lowered:
                facts.append(
                    ExtractedFact(
                        subject=parsed.title,
                        subject_type="Experiment",
                        predicate="DESCRIBED_IN",
                        object_value=fragment.text[:180],
                        object_type="Claim",
                        confidence=0.72,
                        metadata={"fragment_type": fragment.fragment_type},
                    )
                )

    entities = [
        {"type": entity_type, "name": name}
        for entity_type, names in entity_candidates.items()
        for name in sorted(names)
    ]
    return _deduplicate_facts(facts), entities


def _extract_structured_facts(fragment: ParsedFragment, source_type: str, title: str) -> list[ExtractedFact]:
    metadata = fragment.metadata or {}
    entry_type = metadata.get("entry_type")
    text = normalize_text(fragment.text)
    lowered = text.lower()
    facts: list[ExtractedFact] = []

    if source_type == "reference_catalog" and fragment.fragment_type == "reference_entry":
        values = _parse_key_values(text)
        name = values.get("name")
        aliases = [item.strip() for item in values.get("aliases", "").split(",") if item.strip()]
        normalized = values.get("normalized")
        group = values.get("group") or entry_type or "reference"
        if name:
            facts.append(ExtractedFact(subject=name, subject_type="ReferenceEntry", predicate="DESCRIBED_IN", object_value=group, object_type="Topic", confidence=0.95, metadata=metadata))
        for alias in aliases:
            if name:
                facts.append(ExtractedFact(subject=name, subject_type="ReferenceEntry", predicate="SAME_AS", object_value=alias, object_type="Alias", confidence=0.97, metadata=metadata))
        if name and normalized:
            facts.append(ExtractedFact(subject=name, subject_type="ReferenceEntry", predicate="SAME_AS", object_value=normalized, object_type="NormalizedValue", confidence=0.96, metadata=metadata))

    if source_type == "expert_directory" and fragment.fragment_type == "expert_card":
        values = _parse_key_values(text)
        name = values.get("name")
        topics = [item.strip() for item in values.get("topics", "").split(",") if item.strip()]
        organization = values.get("organization")
        for topic in topics:
            if name:
                facts.append(ExtractedFact(subject=name, subject_type="Expert", predicate="EXPERT_IN", object_value=topic, object_type="Topic", confidence=0.96, metadata=metadata))
        if name and organization:
            facts.append(ExtractedFact(subject=name, subject_type="Expert", predicate="AUTHORED_BY", object_value=organization, object_type="Organization", confidence=0.83, metadata=metadata))

    if source_type == "taxonomy_catalog" and fragment.fragment_type == "taxonomy_topic":
        values = _parse_key_values(text)
        topic = values.get("topic")
        parent = values.get("parent")
        if topic and parent:
            facts.append(ExtractedFact(subject=topic, subject_type="Topic", predicate="DESCRIBED_IN", object_value=parent, object_type="Topic", confidence=0.9, metadata=metadata))

    if source_type == "experiment_protocol":
        values = _parse_key_values(text)
        material = values.get("material")
        process = values.get("process")
        if fragment.fragment_type == "experiment_material" and material:
            facts.append(ExtractedFact(subject=title, subject_type="Experiment", predicate="USES_MATERIAL", object_value=material, object_type="Material", confidence=0.95, metadata=metadata))
        if fragment.fragment_type == "experiment_process" and process:
            facts.append(ExtractedFact(subject=title, subject_type="Experiment", predicate="DESCRIBED_IN", object_value=process, object_type="Process", confidence=0.93, metadata=metadata))
        if fragment.fragment_type == "experiment_result" and values:
            for key, value in values.items():
                facts.append(ExtractedFact(subject=key, subject_type="Result", predicate="PRODUCES_OUTPUT", object_value=value, object_type="Result", confidence=0.88, metadata=metadata))

    if source_type == "patent_regulation" and ("требован" in lowered or "должен" in lowered or "норма" in lowered):
        facts.append(ExtractedFact(subject=title, subject_type="Publication", predicate="VALIDATED_BY", object_value=text[:180], object_type="Claim", confidence=0.74, metadata={"fragment_type": fragment.fragment_type}))

    return facts


def _extract_numeric_facts(fragment: ParsedFragment, detected: dict[str, list[str]]) -> list[ExtractedFact]:
    text = normalize_text(fragment.text)
    lowered = text.lower()
    facts: list[ExtractedFact] = []
    for match in NUMERIC_RE.finditer(lowered):
        left = float(match.group("left").replace(",", "."))
        right_raw = match.group("right")
        right = float(right_raw.replace(",", ".")) if right_raw else None
        unit_key = match.group("unit").lower()
        unit = DEFAULT_UNITS.get(unit_key, match.group("unit"))
        years = YEAR_RE.findall(lowered)
        material = detected.get("Material", [None])[0]
        process = detected.get("Process", [None])[0]
        geo = detected.get("Geo", [None])[0]
        facts.append(
            ExtractedFact(
                subject=_guess_subject(lowered, detected),
                subject_type="Parameter",
                predicate="OPERATES_AT_CONDITION",
                object_value=match.group(0),
                object_type="Condition",
                numeric_value=left if right is None else None,
                min_value=min(left, right) if right is not None else left,
                max_value=max(left, right) if right is not None else left,
                unit=unit,
                geo=geo,
                time_period=years[0] if years else None,
                confidence=clamp_confidence(0.84 if fragment.fragment_type in {"table", "table_row", "experiment_regime"} else 0.72),
                metadata={
                    "raw_text": match.group(0),
                    "material": material,
                    "process": process,
                    "fragment_type": fragment.fragment_type,
                },
            )
        )
    return facts


def _extract_relation_facts(fragment: ParsedFragment, detected: dict[str, list[str]]) -> list[ExtractedFact]:
    facts: list[ExtractedFact] = []
    processes = detected.get("Process", [])[:3]
    materials = detected.get("Material", [])[:4]
    equipment = detected.get("Equipment", [])[:3]
    geos = detected.get("Geo", [])[:2]

    for process in processes:
        for material in materials:
            facts.append(
                ExtractedFact(
                    subject=process,
                    subject_type="Process",
                    predicate="USES_MATERIAL",
                    object_value=material,
                    object_type="Material",
                    confidence=0.69,
                    metadata={"fragment_type": fragment.fragment_type},
                )
            )
        for item in equipment:
            facts.append(
                ExtractedFact(
                    subject=process,
                    subject_type="Process",
                    predicate="USES_EQUIPMENT",
                    object_value=item,
                    object_type="Equipment",
                    confidence=0.66,
                    metadata={"fragment_type": fragment.fragment_type},
                )
            )
        for geo in geos:
            facts.append(
                ExtractedFact(
                    subject=process,
                    subject_type="Process",
                    predicate="LOCATED_IN",
                    object_value=geo,
                    object_type="Geo",
                    confidence=0.62,
                    metadata={"fragment_type": fragment.fragment_type},
                )
            )
    return _deduplicate_facts(facts)


def _extract_entity_hints(fragment: ParsedFragment, bucket: dict[str, set[str]]) -> None:
    lowered = normalize_text(fragment.text).lower()
    for entity_type, hints in ENTITY_HINTS.items():
        for hint in hints:
            if hint in lowered:
                bucket[entity_type].add(hint)
    for canonical, aliases in DEFAULT_SYNONYMS.items():
        if canonical in lowered or any(alias in lowered for alias in aliases):
            bucket["Topic"].add(canonical)


def _detect_terms(fragment: ParsedFragment) -> dict[str, list[str]]:
    lowered = normalize_text(fragment.text).lower()
    detected: dict[str, list[str]] = {}
    for entity_type, hints in ENTITY_HINTS.items():
        matches = [hint for hint in hints if hint in lowered]
        if matches:
            detected[entity_type] = matches
    return detected


def _guess_subject(text: str, detected: dict[str, list[str]]) -> str:
    key_values = _parse_key_values(text)
    if "temperature" in key_values:
        return "temperature"
    if "current_density" in key_values:
        return "current_density"
    if "recovery" in key_values:
        return "recovery"
    for subject, patterns in SUBJECT_PATTERNS:
        if any(pattern in text for pattern in patterns):
            return subject
    properties = detected.get("Property", [])
    if properties:
        return properties[0]
    materials = detected.get("Material", [])
    if materials:
        return materials[0]
    return "parameter"


def _parse_key_values(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for key, value in KEY_VALUE_RE.findall(text):
        values[key.strip().lower()] = value.strip()
    return values


def _deduplicate_facts(facts: list[ExtractedFact]) -> list[ExtractedFact]:
    seen: set[tuple[str, str, str]] = set()
    result: list[ExtractedFact] = []
    for fact in facts:
        key = (fact.subject, fact.predicate, fact.object_value)
        if key in seen:
            continue
        seen.add(key)
        result.append(fact)
    return result
