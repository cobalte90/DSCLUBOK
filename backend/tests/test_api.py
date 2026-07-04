from __future__ import annotations

import sys
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.main import create_app  # noqa: E402


client = TestClient(create_app())


def test_health_endpoint() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert "corpus_dir" in payload


def test_upload_import_and_search_flow() -> None:
    sample_file = ROOT / "data" / "demo" / "sources" / "sample_regulation.txt"
    with sample_file.open("rb") as fh:
        response = client.post(
            "/api/sources/upload",
            data={"source_type": "patent_regulation", "access_level": "internal", "tags": "[]"},
            files={"files": ("sample_regulation.txt", fh.read(), "text/plain")},
        )
    assert response.status_code == 200
    source_id = response.json()["data"]["source"]["id"]

    import_response = client.post(
        "/api/sources/import",
        json={"source_ids": [source_id], "extraction_profile": "test", "force_reingest": False},
    )
    assert import_response.status_code == 200
    job_id = import_response.json()["data"]["job_id"]

    job_response = client.get(f"/api/ingest/jobs/{job_id}")
    assert job_response.status_code == 200

    search_response = client.post("/api/search", json={"query": "диапазон значений 200-300 мг/л", "filters": {}, "limit": 5})
    assert search_response.status_code == 200
    assert "matches" in search_response.json()["data"]

    compare_response = client.post("/api/compare", json={"query": "диапазон значений 200-300 мг/л", "filters": {}, "group_by": "document"})
    assert compare_response.status_code == 200
    compare_payload = compare_response.json()["data"]
    assert "contradictions" in compare_payload
    assert "coverage_gaps" in compare_payload
    assert "overview" in compare_payload
    assert "source_quality" in compare_payload


def test_saved_queries_alerts_and_exports() -> None:
    sample_file = ROOT / "data" / "demo" / "sources" / "sample_regulation.txt"
    with sample_file.open("rb") as fh:
        response = client.post(
            "/api/sources/upload",
            data={"source_type": "patent_regulation", "access_level": "internal", "tags": "[]"},
            files={"files": ("sample_regulation.txt", fh.read(), "text/plain")},
        )
    assert response.status_code == 200
    source_id = response.json()["data"]["source"]["id"]
    client.post("/api/sources/import", json={"source_ids": [source_id], "extraction_profile": "test", "force_reingest": False})

    saved = client.post("/api/saved-queries", json={"query": "200-300 ??/?", "filters": {}, "alert_enabled": True, "owner": "demo-user"})
    assert saved.status_code == 200
    listed = client.get("/api/saved-queries")
    assert listed.status_code == 200
    assert "items" in listed.json()["data"]

    subscription = client.post("/api/subscriptions", json={"name": "range watch", "query": {"query": "200-300 ??/?", "filters": {}}, "owner": "demo-user", "active": True})
    assert subscription.status_code == 200
    alerts = client.post("/api/alerts/evaluate")
    assert alerts.status_code == 200
    assert "items" in alerts.json()["data"]

    contradictions = client.get("/api/contradictions", params={"query": "200-300 ??/?"})
    assert contradictions.status_code == 200

    resolved = client.post("/api/contradictions/resolve", json={"signature": "demo|sig", "left_fact_id": "left", "right_fact_id": "right", "decision": "prefer_left", "comment": "demo", "actor": "tester"})
    assert resolved.status_code == 200

    export_pdf = client.post("/api/export", json={"query": "200-300 ??/?", "filters": {}, "format": "pdf"})
    assert export_pdf.status_code == 200
    assert export_pdf.json()["data"]["path"].endswith(".pdf")
