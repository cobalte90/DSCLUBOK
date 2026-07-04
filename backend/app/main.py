from __future__ import annotations

import asyncio
import html
import json
import os
import re
from pathlib import Path
from typing import Any

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .corpus_bootstrap import bootstrap_local_corpus
from .curated_bootstrap import bootstrap_curated_and_run
from .database import init_db, session_scope
from .demo_bootstrap import bootstrap_and_run
from .exports import export_payload
from .external_sources.models import ExternalSearchRequest
from .external_sources.router import router as external_sources_router
from .external_sources.service import ExternalResearchService
from .domain_knowledge import domain_summary, search_domain_knowledge
from .graph_store import graph_store
from .graph_query import run_graph_query
from .ingestion import queue_import, run_job, scan_sources
from .llm import LLMUnavailable, summarize_answer
from .models import DocumentRecord, FactRecord
from .repository import (
    audit,
    create_source_config,
    dashboard_counts,
    get_job,
    get_source,
    list_recent_events,
    list_saved_queries,
    list_sources,
    list_subscriptions,
    register_document,
    save_query,
    save_subscription,
)
from .schemas import (
    AnswerRequest,
    ApiEnvelope,
    CompareRequest,
    ContradictionResolveRequest,
    ExportRequest,
    FactReviewRequest,
    GraphQueryRequest,
    FolderImportRequest,
    ImportRunRequest,
    SavedQueryRequest,
    ScanRequest,
    SearchRequest,
    SubscriptionRequest,
)
from .search import build_graph_neighborhood, collect_experiment_passports, collect_facts_for_fragments, compare_results, evaluate_alerts, search_experts, search_fragments
from .source_registry import SOURCE_TYPE_REGISTRY
from .text_normalization import repair_payload as _repair_payload
from .utils import json_loads, new_id


external_research_service = ExternalResearchService()


DEMO_SCENARIOS = [{'id': 'mine-water-sulfates',
  'title': 'Очистка шахтных вод',
  'query': 'Какие методы очистки шахтных вод применимы при сульфатах 200-300 мг/л?',
  'graph_seed': 'сульфат',
  'why': 'Показывает инженерный поиск по условиям и evidence-first ответ.'},
 {'id': 'nickel-recovery',
  'title': 'Извлечение никеля',
  'query': 'Какие факторы влияют на извлечение никеля и температурный режим процесса?',
  'graph_seed': 'никель',
  'why': 'Показывает числовые параметры, процессы и связи в графе.'},
 {'id': 'electrowinning',
  'title': 'Электроэкстракция',
  'query': 'Какие режимы электроэкстракции встречаются в корпусе и какие есть параметры плотности тока?',
  'graph_seed': 'электроэкстракция',
  'why': 'Показывает table-first извлечение и сравнение диапазонов.'},
 {'id': 'russia-vs-world',
  'title': 'Россия vs world',
  'query': 'Какие решения по переработке никельсодержащего сырья описаны в российских и зарубежных источниках?',
  'graph_seed': 'россия',
  'why': 'Показывает multi-source compare и тематическое покрытие корпуса.'}]

def _safe_upload_filename(filename: str) -> str:
    raw = Path(filename or "document").name
    stem = Path(raw).stem.strip() or "document"
    suffix = Path(raw).suffix.lower()
    safe_stem = re.sub(r"[^0-9A-Za-zА-Яа-яЁё._ -]+", "_", stem).strip(" ._") or "document"
    return f"{safe_stem[:120]}{suffix}"


def create_app() -> FastAPI:
    init_db()
    app = FastAPI(title="Science Knot API", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(external_sources_router)

    @app.get("/health")
    def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "mode": current_mode(),
            "source_types": list(SOURCE_TYPE_REGISTRY),
            "corpus_dir": str(settings.corpus_dir),
            "graph": graph_store.health(),
        }

    @app.get("/api/demo/scenarios")
    def demo_scenarios() -> ApiEnvelope:
        return ApiEnvelope(
            request_id=new_id("req"),
            mode=current_mode(),
            confidence=1.0,
            data={"items": _repair_payload(DEMO_SCENARIOS)},
        )

    @app.get("/api/demo/curated-manifest")
    def curated_manifest() -> ApiEnvelope:
        manifest = json.loads(settings.curated_manifest.read_text(encoding="utf-8-sig"))
        return ApiEnvelope(
            request_id=new_id("req"),
            mode=current_mode(),
            confidence=1.0,
            data=manifest,
        )

    @app.post("/api/demo/bootstrap")
    def demo_bootstrap() -> ApiEnvelope:
        with session_scope() as session:
            job_id, payload = bootstrap_and_run(session)
            return ApiEnvelope(
                request_id=new_id("req"),
                mode=current_mode(),
                confidence=1.0,
                data={"job_id": job_id, "status": "done", **payload},
                warnings=["Demo bootstrap completed using the curated manifest."],
            )

    @app.post("/api/demo/bootstrap-curated")
    def demo_bootstrap_curated() -> ApiEnvelope:
        with session_scope() as session:
            job_id, payload = bootstrap_curated_and_run(session)
            return ApiEnvelope(
                request_id=new_id("req"),
                mode=current_mode(),
                confidence=1.0,
                data={"job_id": job_id, "status": "done", **payload},
                warnings=["Curated real-document bootstrap completed."],
            )

    @app.post("/api/demo/register-corpus")
    def register_corpus() -> ApiEnvelope:
        with session_scope() as session:
            payload = bootstrap_local_corpus(session)
            scan_payload = scan_sources(session, payload["source_ids"])
            warnings = list(payload.get("warnings", []))
            if scan_payload["count"] == 0:
                warnings.append("Corpus folders were registered, but no supported files were discovered yet.")
            return ApiEnvelope(
                request_id=new_id("req"),
                mode=current_mode(),
                confidence=1.0,
                sources=[{"source_id": source_id} for source_id in payload["source_ids"]],
                data={**payload, "scan": scan_payload},
                warnings=warnings,
            )

    @app.get("/api/source-types")
    def source_types() -> dict[str, Any]:
        return {
            "request_id": new_id("req"),
            "mode": current_mode(),
            "source_types": {
                key: {
                    "label": spec.label,
                    "allowed_formats": spec.allowed_formats,
                    "parser": spec.parser,
                    "extraction_profile": spec.extraction_profile,
                    "graph_write_profile": spec.graph_write_profile,
                }
                for key, spec in SOURCE_TYPE_REGISTRY.items()
            },
        }

    @app.post("/api/sources/upload")
    async def upload_sources(
        files: list[UploadFile] = File(...),
        source_type: str = Form(...),
        access_level: str = Form("internal"),
        tags: str = Form("[]"),
        name: str | None = Form(None),
    ) -> ApiEnvelope:
        if source_type not in SOURCE_TYPE_REGISTRY:
            raise HTTPException(status_code=400, detail="Unsupported source_type.")
        spec = SOURCE_TYPE_REGISTRY[source_type]
        for file in files:
            extension = Path(file.filename or "").suffix.lower().lstrip(".")
            if extension not in spec.allowed_formats:
                raise HTTPException(status_code=400, detail=f"Format .{extension or 'unknown'} is not allowed for {source_type}. Allowed: {', '.join(spec.allowed_formats)}")

        with session_scope() as session:
            source = create_source_config(
                session,
                name=name or f"Upload {source_type}",
                source_type=source_type,
                source_mode="ui_upload",
                filesystem_path=None,
                path_alias=None,
                watch_mode="manual",
                recursive=False,
                access_level=access_level,
                tags=json_loads(tags, []),
                source_metadata={"upload_count": len(files)},
            )
            uploaded = []
            target_dir = settings.upload_dir / source.id
            target_dir.mkdir(parents=True, exist_ok=True)
            for file in files:
                destination = target_dir / _safe_upload_filename(file.filename or "document")
                destination.write_bytes(await file.read())
                document = register_document(session, source=source, path=destination, force=False)
                uploaded.append({"document_id": document.id, "filename": destination.name, "status": document.ingest_status})
            audit(session, actor="demo-user", action="source_uploaded", object_type="source", object_id=source.id, payload={"file_count": len(uploaded)})
            return ApiEnvelope(
                request_id=new_id("req"),
                mode=current_mode(),
                sources=[{"source_id": source.id, "name": source.name}],
                confidence=1.0,
                data={"source": {"id": source.id, "name": source.name}, "documents": uploaded},
            )

    @app.post("/api/sources/register-folder")
    def register_folder(request: FolderImportRequest) -> ApiEnvelope:
        path = Path(request.filesystem_path)
        if not path.exists() or not path.is_dir():
            raise HTTPException(status_code=400, detail="filesystem_path must point to an existing directory.")
        if request.source_type not in SOURCE_TYPE_REGISTRY:
            raise HTTPException(status_code=400, detail="Unsupported source_type.")
        with session_scope() as session:
            source = create_source_config(
                session,
                name=request.path_alias,
                source_type=request.source_type,
                source_mode="watched_import_folder",
                filesystem_path=str(path),
                path_alias=request.path_alias,
                watch_mode=request.watch_mode,
                recursive=request.recursive,
                access_level=request.access_level,
                tags=request.tags,
                source_metadata={},
            )
            audit(session, actor="demo-user", action="folder_registered", object_type="source", object_id=source.id, payload={"path": str(path)})
            return ApiEnvelope(
                request_id=new_id("req"),
                mode=current_mode(),
                sources=[{"source_id": source.id, "filesystem_path": str(path)}],
                confidence=1.0,
                data={"source_id": source.id},
            )

    @app.get("/api/sources")
    def get_sources() -> ApiEnvelope:
        with session_scope() as session:
            return ApiEnvelope(
                request_id=new_id("req"),
                mode=current_mode(),
                confidence=1.0,
                data={"items": list_sources(session)},
            )

    @app.post("/api/sources/scan")
    def scan(request: ScanRequest) -> ApiEnvelope:
        with session_scope() as session:
            data = scan_sources(session, request.source_ids)
            return ApiEnvelope(
                request_id=new_id("req"),
                mode=current_mode(),
                confidence=1.0,
                data=data,
            )

    @app.post("/api/sources/import")
    def import_sources(request: ImportRunRequest, background_tasks: BackgroundTasks) -> ApiEnvelope:
        with session_scope() as session:
            for source_id in request.source_ids:
                if not get_source(session, source_id):
                    raise HTTPException(status_code=404, detail=f"Source {source_id} not found.")
            job = queue_import(session, request.source_ids, request.extraction_profile)
        background_tasks.add_task(run_job, job.id)
        return ApiEnvelope(
            request_id=new_id("req"),
            mode=current_mode(),
            sources=[{"source_id": source_id} for source_id in request.source_ids],
            confidence=1.0,
            data={"job_id": job.id, "status": "queued"},
        )

    @app.get("/api/ingest/jobs/{job_id}")
    def job_status(job_id: str) -> ApiEnvelope:
        with session_scope() as session:
            job = get_job(session, job_id)
            if not job:
                raise HTTPException(status_code=404, detail="Job not found.")
            return ApiEnvelope(
                request_id=new_id("req"),
                mode=current_mode(),
                confidence=1.0,
                data={
                    "job": {
                        "id": job.id,
                        "kind": job.kind,
                        "status": job.status,
                        "stage": job.stage,
                        "progress": job.progress,
                        "stats": json_loads(job.stats_json, {}),
                        "error_message": job.error_message,
                    }
                },
            )

    @app.post("/api/search")
    def search(request: SearchRequest) -> ApiEnvelope:
        with session_scope() as session:
            matches = search_fragments(session, request.query, request.filters, request.limit)
            facts = collect_facts_for_fragments(session, [match["fragment_id"] for match in matches])
            return ApiEnvelope(
                request_id=new_id("req"),
                mode=current_mode(),
                sources=[{"document_id": match["document_id"], "filename": match["filename"]} for match in matches],
                confidence=_avg_confidence(facts),
                data={"matches": matches, "facts": facts},
            )

    @app.post("/api/answer")
    def answer(request: AnswerRequest) -> ApiEnvelope:
        with session_scope() as session:
            matches = search_fragments(session, request.query, request.filters, request.limit)
            facts = collect_facts_for_fragments(session, [match["fragment_id"] for match in matches])
            experiments = collect_experiment_passports(session, request.query)
            warnings: list[str] = []
            mode = current_mode()
            external_sources: list[dict[str, Any]] = []
            if request.filters.get("include_external_sources"):
                external_sources, external_warnings = _search_external_sources_for_answer(request)
                warnings.extend(external_warnings)
            domain_matches = search_domain_knowledge(request.query, limit=3)
            summary = _deterministic_summary(request.query, matches, facts, experiments)
            if domain_matches and (not matches or not facts):
                summary = domain_summary(domain_matches)
                warnings.append("Ответ дополнен базовым доменным справочником, потому что в локальных документах мало прямых подтверждений.")
            synthesis_context: dict[str, Any] = {
                "match": matches,
                "facts": facts,
                "experiments": experiments,
                "domain_knowledge": domain_matches,
                "general_llm_fallback_allowed": not bool(matches or facts or domain_matches or external_sources),
            }
            if external_sources:
                synthesis_context["external_sources"] = external_sources
                synthesis_context["external_research_context"] = _external_sources_for_llm(external_sources)
            try:
                mode, generated, llm_warnings = summarize_answer(request.query, [synthesis_context])
                warnings.extend(llm_warnings)
                if generated:
                    summary = generated
            except LLMUnavailable as exc:
                warnings.append(f"LLM is unavailable: {exc}. Degraded answer mode was used.")
            except Exception as exc:
                warnings.append(f"LLM synthesis failed: {exc}. Degraded answer mode was used.")
            return ApiEnvelope(
                request_id=new_id("req"),
                mode=mode,
                sources=[{"document_id": match["document_id"], "filename": match["filename"]} for match in matches] + [
                    {"source_mode": "external", "connector_id": item.get("connector_id"), "title": item.get("title"), "url": item.get("url"), "doi": item.get("doi"), "year": item.get("year")}
                    for item in external_sources
                ],
                confidence=_avg_confidence(facts),
                warnings=warnings,
                data={
                    "summary": summary,
                    "matches": matches,
                    "facts": facts,
                    "experiments": experiments,
                    "domain_knowledge": domain_matches,
                    "evidence_view": [{"fact": fact, "fragment_id": fact["fragment_id"]} for fact in facts[:8]],
                    "external_sources": external_sources,
                },
            )

    @app.post("/api/compare")
    def compare(request: CompareRequest) -> ApiEnvelope:
        with session_scope() as session:
            payload = compare_results(session, request.query, request.filters, request.group_by)
            flat_facts = [fact for group in payload["groups"].values() for fact in group["facts"]]
            return ApiEnvelope(
                request_id=new_id("req"),
                mode=current_mode(),
                confidence=_avg_confidence(flat_facts),
                data=payload,
            )

    @app.post("/api/graph/query")
    def graph_query(request: GraphQueryRequest) -> ApiEnvelope:
        with session_scope() as session:
            payload = run_graph_query(session, request)
            return ApiEnvelope(
                request_id=new_id("req"),
                mode=current_mode(),
                confidence=0.78 if payload.get("graph_mode") != "fallback" else 0.45,
                data=_repair_payload(payload),
                warnings=payload.get("warnings", []),
            )

    @app.get("/api/graph/neighborhood")
    def graph(seed: str, limit: int = 25) -> ApiEnvelope:
        with session_scope() as session:
            payload = run_graph_query(session, GraphQueryRequest(query=seed, max_nodes=limit, max_hops=2))
            return ApiEnvelope(
                request_id=new_id("req"),
                mode=current_mode(),
                confidence=0.78 if payload.get("graph_mode") != "fallback" else 0.45,
                data=_repair_payload(payload),
                warnings=payload.get("warnings", []),
            )


    @app.get("/api/facts/{fact_id}")
    def get_fact(fact_id: str) -> ApiEnvelope:
        with session_scope() as session:
            fact = session.get(FactRecord, fact_id)
            if not fact:
                raise HTTPException(status_code=404, detail="Fact not found.")
            document = session.get(DocumentRecord, fact.document_id)
            return ApiEnvelope(
                request_id=new_id("req"),
                mode=current_mode(),
                confidence=fact.confidence,
                sources=[{"document_id": fact.document_id, "filename": document.filename if document else fact.document_id}],
                data={
                    "fact": {
                        "id": fact.id,
                        "subject": fact.subject,
                        "predicate": fact.predicate,
                        "object_value": fact.object_value,
                        "unit": fact.unit,
                        "min_value": fact.min_value,
                        "max_value": fact.max_value,
                        "verification_status": fact.verification_status,
                        "review_comment": fact.review_comment,
                        "metadata": json_loads(fact.metadata_json, {}),
                    }
                },
            )

    @app.post("/api/facts/{fact_id}/review")
    def review_fact(fact_id: str, request: FactReviewRequest) -> ApiEnvelope:
        with session_scope() as session:
            fact = session.get(FactRecord, fact_id)
            if not fact:
                raise HTTPException(status_code=404, detail="Fact not found.")
            fact.verification_status = request.decision
            fact.review_comment = request.comment
            if request.confidence_override is not None:
                fact.confidence = request.confidence_override
            audit(session, actor=request.actor, action="fact_reviewed", object_type="fact", object_id=fact.id, payload=request.model_dump())
            return ApiEnvelope(
                request_id=new_id("req"),
                mode=current_mode(),
                confidence=fact.confidence,
                data={"fact_id": fact.id, "verification_status": fact.verification_status},
            )

    @app.post("/api/saved-queries")
    def create_saved_query(request: SavedQueryRequest) -> ApiEnvelope:
        with session_scope() as session:
            item = save_query(session, request.owner, request.query, request.filters, request.alert_enabled)
            return ApiEnvelope(
                request_id=new_id("req"),
                mode=current_mode(),
                confidence=1.0,
                data={"saved_query_id": item.id},
            )

    @app.post("/api/subscriptions")
    def create_subscription(request: SubscriptionRequest) -> ApiEnvelope:
        with session_scope() as session:
            item = save_subscription(session, request.owner, request.name, request.query, request.active)
            return ApiEnvelope(
                request_id=new_id("req"),
                mode=current_mode(),
                confidence=1.0,
                data={"subscription_id": item.id},
            )

    @app.get("/api/saved-queries")
    def get_saved_queries() -> ApiEnvelope:
        with session_scope() as session:
            return ApiEnvelope(
                request_id=new_id("req"),
                mode=current_mode(),
                confidence=1.0,
                data={"items": list_saved_queries(session)},
            )

    @app.get("/api/subscriptions")
    def get_subscriptions() -> ApiEnvelope:
        with session_scope() as session:
            return ApiEnvelope(
                request_id=new_id("req"),
                mode=current_mode(),
                confidence=1.0,
                data={"items": list_subscriptions(session)},
            )

    @app.get("/api/experts/search")
    def expert_search(q: str, limit: int = 8) -> ApiEnvelope:
        with session_scope() as session:
            items = search_experts(session, q, limit)
            return ApiEnvelope(
                request_id=new_id("req"),
                mode=current_mode(),
                confidence=0.82 if items else 0.0,
                data={"items": items},
                warnings=[] if items else ["No matching experts were found in the current corpus."],
            )

    @app.get("/api/contradictions")
    def contradictions(query: str, limit: int = 12) -> ApiEnvelope:
        with session_scope() as session:
            payload = compare_results(session, query, {}, "document")
            items = payload["contradictions"][:limit]
            return ApiEnvelope(
                request_id=new_id("req"),
                mode=current_mode(),
                confidence=_avg_confidence([item["left"] for item in items] + [item["right"] for item in items]),
                data={"items": items, "resolutions": payload.get("resolutions", {})},
            )

    @app.post("/api/contradictions/resolve")
    def resolve_contradiction(request: ContradictionResolveRequest) -> ApiEnvelope:
        with session_scope() as session:
            audit(
                session,
                actor=request.actor,
                action="contradiction_resolved",
                object_type="contradiction",
                object_id=request.signature,
                payload=request.model_dump(),
            )
            return ApiEnvelope(
                request_id=new_id("req"),
                mode=current_mode(),
                confidence=1.0,
                data={"signature": request.signature, "decision": request.decision},
            )

    @app.post("/api/alerts/evaluate")
    def alerts_evaluate() -> ApiEnvelope:
        with session_scope() as session:
            items = evaluate_alerts(session)
            for item in items:
                audit(
                    session,
                    actor="system",
                    action="alert_triggered",
                    object_type=item["kind"],
                    object_id=item["id"],
                    payload=item,
                )
            return ApiEnvelope(
                request_id=new_id("req"),
                mode=current_mode(),
                confidence=1.0,
                data={"items": items, "count": len(items)},
            )

    @app.get("/api/alerts/feed")
    def alerts_feed(limit: int = 20) -> ApiEnvelope:
        with session_scope() as session:
            items = list_recent_events(session, actions=["alert_triggered", "contradiction_resolved", "fact_reviewed"], limit=limit)
            return ApiEnvelope(
                request_id=new_id("req"),
                mode=current_mode(),
                confidence=1.0,
                data={"items": items},
            )

    @app.get("/api/dashboard/coverage")
    def dashboard() -> ApiEnvelope:
        with session_scope() as session:
            payload = dashboard_counts(session)
            payload["graph"] = graph_store.health()
            return ApiEnvelope(
                request_id=new_id("req"),
                mode=current_mode(),
                confidence=1.0,
                data=payload,
            )

    @app.post("/api/export")
    def export(request: ExportRequest) -> ApiEnvelope:
        with session_scope() as session:
            matches = search_fragments(session, request.query, request.filters, limit=8)
            facts = collect_facts_for_fragments(session, [match["fragment_id"] for match in matches])
            answer_payload = {
                "summary": _deterministic_summary(request.query, matches, facts, []),
                "sources": matches,
                "facts": facts,
            }
            exported = export_payload(request.query, answer_payload, request.format)
            return ApiEnvelope(
                request_id=new_id("req"),
                mode=current_mode(),
                confidence=_avg_confidence(facts),
                warnings=exported["warnings"],
                data=exported,
            )

    return app


def current_mode() -> str:
    provider = (settings.llm_provider or "stub").lower()
    if provider == "openai" and settings.openai_api_key:
        return "full"
    if provider == "yandex" and settings.yandex_api_key:
        return "yandex"
    if provider == "stub":
        return "stub"
    return settings.mode


def _avg_confidence(facts: list[dict[str, Any]]) -> float:
    if not facts:
        return 0.0
    return round(sum(fact.get("confidence", 0.0) for fact in facts) / len(facts), 4)


def _search_external_sources_for_answer(request: AnswerRequest) -> tuple[list[dict[str, Any]], list[str]]:
    if os.getenv("EXTERNAL_SOURCES_ENABLED", "false").lower() != "true":
        return [], ["External scientific source search is disabled."]
    try:
        result = asyncio.run(
            external_research_service.search(
                ExternalSearchRequest(
                    query=request.query,
                    limit=int(request.filters.get("external_limit") or 5),
                    connectors=list(request.filters.get("external_connectors") or []),
                    language=str(request.filters.get("external_language") or "any"),
                    year_from=request.filters.get("external_year_from"),
                    year_to=request.filters.get("external_year_to"),
                    include_patents=bool(request.filters.get("include_patents", True)),
                    timeout_ms=int(request.filters.get("external_timeout_ms") or 8000),
                )
            )
        )
    except Exception:
        return [], ["External scientific source search failed; local answer was used."]
    warnings = [f"{failure.id}: {failure.reason}" for failure in result.failed_connectors]
    return [_normalize_external_source_item(item.model_dump()) for item in result.items], warnings


def _normalize_external_source_item(item: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(item)
    for key in ("title", "snippet", "journal", "publisher", "source_name"):
        if normalized.get(key):
            normalized[key] = html.unescape(str(_repair_payload(normalized[key])))
    normalized["authors"] = _repair_payload(normalized.get("authors") or [])
    return normalized


def _external_sources_for_llm(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    context: list[dict[str, Any]] = []
    for item in items[:5]:
        context.append(
            {
                "title": item.get("title"),
                "source": item.get("source_name") or item.get("connector_id"),
                "year": item.get("year"),
                "url": item.get("url"),
                "doi": item.get("doi"),
                "patent_number": item.get("patent_number"),
                "snippet": item.get("snippet"),
                "access_status": item.get("access_status"),
                "relevance_score": item.get("relevance_score"),
                "instruction": "Use title/snippet as external metadata context only; do not treat it as verified local evidence.",
            }
        )
    return context


def _deterministic_summary(query: str, matches: list[dict[str, Any]], facts: list[dict[str, Any]], experiments: list[dict[str, Any]]) -> str:
    if not matches:
        return f"По запросу '{query}' пока не найдено подтвержденных фрагментов. Система рекомендует расширить корпус или смягчить фильтры."
    documents = ", ".join(sorted({match["filename"] for match in matches[:4]}))
    summary = [
        f"По запросу '{query}' найдено {len(matches)} релевантных фрагментов из документов: {documents}.",
        f"Извлечено {len(facts)} фактов с проверяемыми источниками.",
    ]
    if experiments:
        summary.append(f"Найдены связанные экспериментальные паспорта: {len(experiments)}.")
    if any(fact.get("min_value") is not None and fact.get("max_value") is not None and fact.get("min_value") != fact.get("max_value") for fact in facts):
        summary.append("В ответе присутствуют числовые диапазоны, пригодные для инженерного сравнения.")
    return " ".join(summary)



