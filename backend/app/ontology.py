from __future__ import annotations

from pathlib import Path

from .config import settings


DEFAULT_SYNONYMS = {
    "электроэкстракция": ["electrowinning", "ew", "nickel electrowinning", "copper electrowinning"],
    "пвп": ["печь взвешенной плавки", "flash smelting furnace", "fluidized bed furnace"],
    "мпг": ["pgm", "platinum group metals", "платиновые металлы"],
    "шахтные воды": ["mine water", "miw"],
    "католит": ["catholyte"],
    "горные породы": ["горных пород", "виды горных пород", "классификация горных пород", "rock types", "rocks"],
    "руда": ["руды", "ore", "ores"],
    "обогащение": ["beneficiation", "mineral processing", "методы обогащения"],
}

DEFAULT_UNITS = {
    "мг/л": "mg/L",
    "мг/дм3": "mg/dm3",
    "г/л": "g/L",
    "°с": "degC",
    "°c": "degC",
    "а/м2": "A/m2",
    "а/дм2": "A/dm2",
    "т/сут": "t/day",
    "%": "percent",
}

ENTITY_HINTS = {
    "Material": ["никель", "медь", "гипс", "сульфат", "хлорид", "шлак", "штейн", "серебро", "платина", "палладий"],
    "Process": ["выщелачивание", "электроэкстракция", "обессоливание", "рафинирование", "очистка", "плавка", "флотация", "сушка", "обогащение"],
    "Equipment": ["ванна", "ячейка", "печь", "скруббер", "фильтр", "реактор", "сгуститель", "мельница"],
    "Condition": ["холодный климат", "мировая практика", "зарубежная практика", "россия", "давление", "температура", "концентрация", "скорость"],
    "Geo": ["россия", "австралия", "монголия", "китай", "канада", "новая каледония", "норильск", "кольский"],
    "Organization": ["норникель", "kgmk", "кольская гмк", "гипроникель", "vale", "glencore", "eramet"],
    "Property": ["извлечение", "плотность тока", "температура", "концентрация", "влажность", "пористость"],
}


CANONICAL_ENTITY_TYPES = {
    canonical: entity_type
    for entity_type, terms in ENTITY_HINTS.items()
    for canonical in terms
}
CANONICAL_ENTITY_TYPES.update({
    "электроэкстракция": "Process",
    "пвп": "Equipment",
    "мпг": "Material",
    "шахтные воды": "Material",
    "католит": "Material",
    "горные породы": "Material",
    "магматические породы": "Material",
    "осадочные породы": "Material",
    "метаморфические породы": "Material",
    "руда": "Material",
    "полезные ископаемые": "Material",
})


def ontology_dir() -> Path:
    return settings.ontology_dir
