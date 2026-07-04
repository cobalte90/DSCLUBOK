# External Scientific Sources Module Spec

Цель документа: дать отдельному разработчику точный контракт для модуля внешнего научного поиска, чтобы его можно было подключить к проекту без ломания текущего Ask/Search/Sources/Graph flow.

## 1. Что должен делать модуль

Модуль `external_sources` должен во время пользовательского запроса искать релевантные внешние научные материалы и возвращать 3-5 лучших ссылок с метаданными.

Важно: v1 модуля не обязан скачивать PDF, обходить paywall, извлекать полный текст или писать факты в граф. Его первая задача - дать проверяемые внешние references рядом с ответом.

Минимальный результат для пользователя:

- название статьи/патента/материала;
- авторы;
- год;
- источник/платформа;
- URL;
- DOI/патентный номер, если есть;
- короткий snippet/abstract, если доступен легально;
- score релевантности;
- пометка `external`;
- статус доступности: `metadata_only`, `abstract_available`, `full_text_available`, `restricted`.

## 2. Внешние источники и правила

Поддерживаемые connector IDs:

- `crossref` - рекомендован как базовый metadata connector для DOI.
- `openalex` - рекомендован как базовый scholarly search connector.
- `semantic_scholar` - опционально, если есть API key / допустимые лимиты.
- `springer` - через официальный API Springer Nature, если есть ключ.
- `mdpi` - metadata/pages; без агрессивного scraping.
- `cyberleninka` - metadata/search страницы или официальный доступ, если доступен.
- `google_patents` - ссылки/metadata патентов; не скачивать bulk без отдельного решения.
- `wiley` - через Wiley/TDM/API при наличии доступа.
- `sciencedirect` - через Elsevier API при наличии ключа.
- `elibrary` - только metadata/link, с учетом ограничений доступа.
- `researchgate` - только metadata/link, если доступно без обхода ограничений.

Запрещено для релизного модуля:

- обходить paywall;
- обходить captcha/login;
- массово скачивать PDF без прав;
- использовать Sci-Hub как автоматический source connector;
- подменять внешние ссылки выдуманными источниками;
- добавлять неподтвержденные факты в graph как локальные facts.

Если источник недоступен легально или требует авторизации, connector должен вернуть `status: "restricted"` или warning, а не падать.

## 3. Текущие endpoint'ы проекта

Все ответы API идут через `ApiEnvelope`:

```json
{
  "request_id": "req_...",
  "mode": "yandex|degraded|demo",
  "sources": [],
  "confidence": 0.0,
  "warnings": [],
  "data": {}
}
```

Текущие пользовательские endpoint'ы:

- `POST /api/search`
- `POST /api/answer`
- `POST /api/compare`
- `GET /api/graph/neighborhood?seed=...&limit=25`
- `GET /api/sources`
- `POST /api/sources/upload`
- `POST /api/sources/register-folder`
- `POST /api/sources/import`
- `GET /api/ingest/jobs/{job_id}`
- `GET /api/dashboard/coverage`
- `POST /api/export`

Текущие request DTO:

```json
// POST /api/search and POST /api/answer
{
  "query": "строка вопроса",
  "filters": {},
  "limit": 8
}
```

```json
// POST /api/compare
{
  "query": "строка вопроса",
  "filters": {},
  "group_by": "document"
}
```

## 4. Предлагаемые новые endpoint'ы для модуля

Модуль должен добавить отдельный router, например:

`backend/app/external_sources/router.py`

### 4.1 GET /api/external-sources/connectors

Возвращает список доступных коннекторов и их состояние.

Response:

```json
{
  "request_id": "req_...",
  "mode": "yandex",
  "sources": [],
  "confidence": 1.0,
  "warnings": [],
  "data": {
    "connectors": [
      {
        "id": "openalex",
        "label": "OpenAlex",
        "enabled": true,
        "requires_api_key": false,
        "status": "ok"
      },
      {
        "id": "springer",
        "label": "Springer Nature",
        "enabled": false,
        "requires_api_key": true,
        "status": "missing_api_key"
      }
    ]
  }
}
```

### 4.2 POST /api/external-sources/search

Ищет внешние источники без изменения локальной базы.

Request:

```json
{
  "query": "электроэкстракция никеля скорость потока католита",
  "limit": 5,
  "connectors": ["openalex", "crossref", "springer", "google_patents"],
  "language": "ru|en|any",
  "year_from": 2015,
  "year_to": 2026,
  "include_patents": true,
  "timeout_ms": 8000
}
```

Response:

```json
{
  "request_id": "req_...",
  "mode": "yandex",
  "sources": [
    {
      "source_mode": "external",
      "connector_id": "openalex",
      "title": "Nickel electrowinning catholyte circulation ...",
      "url": "https://...",
      "doi": "10....",
      "year": 2023
    }
  ],
  "confidence": 0.74,
  "warnings": [],
  "data": {
    "items": [
      {
        "id": "external_openalex_...",
        "source_mode": "external",
        "connector_id": "openalex",
        "source_name": "OpenAlex",
        "source_type": "article_review|publication|patent|regulation|dataset|unknown",
        "title": "...",
        "authors": ["..."],
        "year": 2023,
        "url": "https://...",
        "doi": "10....",
        "patent_number": null,
        "journal": "...",
        "publisher": "...",
        "snippet": "short legal abstract/snippet",
        "language": "en",
        "relevance_score": 0.82,
        "quality_score": 0.71,
        "access_status": "metadata_only|abstract_available|full_text_available|restricted",
        "matched_terms": ["nickel", "electrowinning"],
        "retrieved_at": "2026-07-03T12:00:00Z",
        "license": null,
        "raw": {}
      }
    ],
    "took_ms": 1430,
    "used_connectors": ["openalex", "crossref"],
    "failed_connectors": [
      {"id": "springer", "reason": "missing_api_key"}
    ]
  }
}
```

### 4.3 POST /api/external-sources/import-link

Опциональный endpoint. Нужен только если пользователь выбирает внешний материал и хочет добавить его в registry проекта.

Request:

```json
{
  "external_item": {
    "connector_id": "openalex",
    "title": "...",
    "url": "https://...",
    "doi": "10....",
    "year": 2023,
    "snippet": "..."
  },
  "source_type": "article_review",
  "access_level": "external_metadata",
  "tags": ["external", "electrowinning"]
}
```

Response:

```json
{
  "request_id": "req_...",
  "mode": "yandex",
  "sources": [{"source_id": "src_...", "source_mode": "external"}],
  "confidence": 1.0,
  "warnings": [],
  "data": {
    "source_id": "src_...",
    "status": "metadata_only"
  }
}
```

## 5. Как подключить к `/api/answer`

Нужно не ломать текущий endpoint. Добавить опциональный filter flag:

```json
{
  "query": "...",
  "filters": {
    "include_external_sources": true,
    "external_limit": 5,
    "external_connectors": ["openalex", "crossref", "google_patents"]
  },
  "limit": 8
}
```

Если flag отсутствует, поведение `/api/answer` остается прежним.

Если flag включен:

1. Выполнить обычный локальный поиск: `search_fragments(...)`.
2. Параллельно или после него вызвать `ExternalResearchService.search(...)`.
3. Добавить внешние результаты в:
   - `data.external_sources`;
   - top-level `sources` с `source_mode: "external"`;
   - `warnings`, если какие-то connector'ы упали.
4. Не добавлять внешние ссылки в `facts`, `evidence_view` и Neo4j без отдельного import/review шага.
5. LLM summary может использовать внешние metadata как context, но обязан явно отделять:
   - `подтверждено локальными документами`;
   - `найдено во внешних источниках`;
   - `требует проверки/full-text review`.

Пример `data` после расширения:

```json
{
  "summary": "...",
  "matches": [],
  "facts": [],
  "experiments": [],
  "evidence_view": [],
  "external_sources": [
    {
      "title": "...",
      "url": "https://...",
      "connector_id": "openalex",
      "source_name": "OpenAlex",
      "year": 2024,
      "snippet": "...",
      "relevance_score": 0.86,
      "access_status": "metadata_only"
    }
  ]
}
```

## 6. Python interface внутри backend

Рекомендуемая структура:

```text
backend/app/external_sources/
  __init__.py
  models.py
  service.py
  router.py
  ranking.py
  connectors/
    __init__.py
    base.py
    openalex.py
    crossref.py
    google_patents.py
    springer.py
    mdpi.py
    cyberleninka.py
```

`models.py`:

```python
from pydantic import BaseModel, Field

class ExternalSearchRequest(BaseModel):
    query: str
    limit: int = 5
    connectors: list[str] = Field(default_factory=list)
    language: str = "any"
    year_from: int | None = None
    year_to: int | None = None
    include_patents: bool = True
    timeout_ms: int = 8000

class ExternalSourceHit(BaseModel):
    id: str
    source_mode: str = "external"
    connector_id: str
    source_name: str
    source_type: str = "publication"
    title: str
    authors: list[str] = Field(default_factory=list)
    year: int | None = None
    url: str
    doi: str | None = None
    patent_number: str | None = None
    journal: str | None = None
    publisher: str | None = None
    snippet: str | None = None
    language: str | None = None
    relevance_score: float = 0.0
    quality_score: float = 0.0
    access_status: str = "metadata_only"
    matched_terms: list[str] = Field(default_factory=list)
    retrieved_at: str
    license: str | None = None
    raw: dict = Field(default_factory=dict)
```

`connectors/base.py`:

```python
from typing import Protocol
from ..models import ExternalSearchRequest, ExternalSourceHit

class ExternalSourceConnector(Protocol):
    id: str
    label: str
    requires_api_key: bool

    def is_enabled(self) -> bool: ...
    async def search(self, request: ExternalSearchRequest) -> list[ExternalSourceHit]: ...
```

`service.py` должен:

- запускать connector'ы с timeout;
- не падать целиком, если один источник упал;
- дедуплицировать по DOI, URL canonical, title+year;
- ранжировать результаты;
- возвращать максимум `limit` лучших;
- писать warnings по упавшим источникам;
- кэшировать результаты хотя бы на 15-60 минут.

## 7. Дедупликация и ranking

Dedup key priority:

1. DOI lowercased.
2. Patent number normalized.
3. Canonical URL без tracking query params.
4. Normalized title + year.

Ranking formula v1:

```text
final_score =
  0.50 * lexical_relevance +
  0.20 * source_quality +
  0.15 * recency_score +
  0.10 * metadata_completeness +
  0.05 * access_bonus
```

Source quality examples:

- official publisher/API: high;
- DOI metadata: high;
- patent metadata: high;
- repository page: medium;
- restricted/login page: low-medium.

## 8. Timeout, fallback, устойчивость

Hard requirements:

- общий timeout внешнего поиска: 8 секунд по умолчанию;
- timeout одного connector'а: 2-4 секунды;
- ошибка одного connector'а не ломает `/api/answer`;
- если все внешние источники упали, `/api/answer` все равно возвращает локальный ответ;
- все ошибки connector'ов идут в `warnings`, не raw stacktrace;
- URLs валидируются;
- snippets ограничиваются по длине, например 800 символов;
- raw HTML не отдавать в UI.

## 9. ENV configuration

Добавить переменные в `.env.example` / README, но не коммитить реальные ключи:

```env
EXTERNAL_SOURCES_ENABLED=false
EXTERNAL_SOURCES_DEFAULT_LIMIT=5
EXTERNAL_SOURCES_TIMEOUT_MS=8000
OPENALEX_ENABLED=true
CROSSREF_ENABLED=true
SPRINGER_API_KEY=
ELSEVIER_API_KEY=
SEMANTIC_SCHOLAR_API_KEY=
WILEY_API_KEY=
```

Если `EXTERNAL_SOURCES_ENABLED=false`, endpoint `/api/external-sources/search` должен возвращать friendly warning, а `/api/answer` работать как раньше.

## 10. Frontend integration contract

Frontend должен получить данные из `answer.data.external_sources` и показать отдельный блок:

Title: `Внешние научные источники`

Для каждого item:

- title;
- source_name;
- year;
- DOI/patent number;
- snippet;
- relevance badge;
- access status badge;
- button/link `Открыть источник`.

Не смешивать external metadata с локальным `Evidence View`. В UI подпись должна быть честной:

`Эти материалы найдены во внешних источниках и требуют проверки полного текста перед добавлением в граф.`

## 11. Как интегрировать готовый модуль в проект

Checklist для разработчика модуля:

1. Положить код в `backend/app/external_sources/`.
2. Добавить router в `backend/app/main.py`:

```python
from .external_sources.router import router as external_sources_router
app.include_router(external_sources_router)
```

3. Добавить вызов сервиса в `/api/answer` только при `filters.include_external_sources == true`.
4. Добавить `external_sources` в `data`, не меняя старые поля.
5. Добавить тесты:
   - connector success;
   - connector timeout;
   - connector failure does not fail service;
   - dedup by DOI;
   - `/api/answer` without flag unchanged;
   - `/api/answer` with flag includes `data.external_sources`.
6. Обновить frontend блок Sources/AnswerWorkspace, если его еще нет.
7. Проверить:

```bash
python -m py_compile backend/app/external_sources/*.py backend/app/external_sources/connectors/*.py
```

```bash
docker compose build api
```

```bash
docker compose run --rm frontend npm run build
```

## 12. Acceptance criteria

Модуль считается готовым, если:

- `POST /api/external-sources/search` стабильно возвращает до 5 релевантных ссылок;
- `/api/answer` без внешнего flag работает как раньше;
- `/api/answer` с `include_external_sources=true` добавляет `data.external_sources`;
- ошибки внешних сайтов не ломают ответ;
- нет raw HTML/stacktrace в API/UI;
- есть dedup;
- есть timeout;
- есть rate limit/cache;
- источники открываются по ссылке;
- Sci-Hub/paywall обход не автоматизирован;
- build API и frontend проходят.

## 13. Минимальный demo сценарий

Request:

```json
POST /api/answer
{
  "query": "Какие технические решения организации циркуляции католита при электроэкстракции никеля описаны в мировой практике?",
  "filters": {
    "include_external_sources": true,
    "external_limit": 5,
    "external_connectors": ["openalex", "crossref", "google_patents"]
  },
  "limit": 8
}
```

Expected:

- обычный локальный answer не ломается;
- `data.external_sources` содержит 3-5 ссылок;
- `warnings` содержит только понятные сообщения, если какой-то connector недоступен;
- UI показывает внешний блок отдельно от локальных доказательств.
