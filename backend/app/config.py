from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class Settings:
    app_name: str = "Science Knot"
    mode: str = os.getenv("SCIENCE_KNOT_MODE", "degraded")
    db_url: str = os.getenv("SCIENCE_KNOT_DB_URL", f"sqlite:///{Path.cwd() / 'data' / 'runtime' / 'science_knot.db'}")
    storage_dir: Path = Path(os.getenv("SCIENCE_KNOT_STORAGE_DIR", Path.cwd() / "data" / "runtime"))
    corpus_dir: Path = Path(os.getenv("SCIENCE_KNOT_CORPUS_DIR", Path.cwd() / "corpus_ascii"))
    ontology_dir: Path = Path(os.getenv("SCIENCE_KNOT_ONTOLOGY_DIR", Path.cwd() / "ontology"))
    demo_manifest: Path = Path(os.getenv("SCIENCE_KNOT_DEMO_MANIFEST", Path.cwd() / "data" / "demo" / "demo_manifest.json"))
    curated_manifest: Path = Path(os.getenv("SCIENCE_KNOT_CURATED_MANIFEST", Path.cwd() / "data" / "curated" / "real_curated_manifest.json"))
    llm_provider: str = os.getenv("SCIENCE_KNOT_LLM_PROVIDER", "stub")
    llm_stub_enabled: bool = os.getenv("SCIENCE_KNOT_LLM_STUB_ENABLED", "1") != "0"
    openai_api_key: str | None = os.getenv("OPENAI_API_KEY")
    openai_base_url: str = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
    yandex_api_key: str | None = os.getenv("YANDEX_AI_API_KEY")
    yandex_folder_id: str | None = os.getenv("YANDEX_AI_FOLDER_ID")
    yandex_base_url: str = os.getenv("YANDEX_AI_BASE_URL", "https://llm.api.cloud.yandex.net")
    yandex_model: str = os.getenv("YANDEX_AI_MODEL", "yandexgpt-lite/latest")
    yandex_model_uri: str | None = os.getenv("YANDEX_AI_MODEL_URI")
    neo4j_http_url: str | None = os.getenv("SCIENCE_KNOT_NEO4J_HTTP_URL")
    neo4j_user: str = os.getenv("SCIENCE_KNOT_NEO4J_USER", "neo4j")
    neo4j_password: str = os.getenv("SCIENCE_KNOT_NEO4J_PASSWORD", "science-knot-demo")

    @property
    def upload_dir(self) -> Path:
        return self.storage_dir / "uploads"

    @property
    def export_dir(self) -> Path:
        return self.storage_dir / "exports"

    @property
    def registry_dir(self) -> Path:
        return self.storage_dir / "registry"


settings = Settings()


def ensure_directories() -> None:
    for path in [settings.storage_dir, settings.upload_dir, settings.export_dir, settings.registry_dir]:
        path.mkdir(parents=True, exist_ok=True)
