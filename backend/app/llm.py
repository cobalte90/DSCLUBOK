from __future__ import annotations

import json
from typing import Any

import requests

from .config import settings
from .text_normalization import repair_payload, repair_text


class LLMUnavailable(Exception):
    pass


SYSTEM_PROMPT = """Ты научный R&D-аналитик и объясняешь инженеру ответ на его вопрос.
Пиши по-русски, спокойно, понятно и научно. Не пиши как лог системы и не показывай внутренние названия полей.
Не используй Markdown-разметку: никаких **, таблиц markdown и заголовков с #.

Главная цель:
1. Первая строка после "Короткий ответ:" должна прямо отвечать на вопрос человека.
2. Если вопрос простой или справочный, дай понятное определение/классификацию сначала, а доказательства после.
3. Если вопрос инженерный, сначала дай практический вывод: что подходит, при каких условиях, где есть риски.
4. Затем подкрепи вывод локальными фактами, фрагментами документов, experiment passports, domain_knowledge и внешними metadata-source.

Правила достоверности:
- Локальные документы и факты имеют максимальный приоритет.
- domain_knowledge можно использовать для базовых определений, классификаций и общеизвестных доменных понятий.
- external_sources можно использовать как источники для проверки и расширения, но явно помечай их как внешние источники, пока они не импортированы в корпус.
- Не выдумывай документы, авторов, значения, страницы, режимы и причинно-следственные связи.
- Если точных данных нет, так и скажи, но все равно дай полезный ответ из доступного справочного слоя или внешних источников.
- При числах сохраняй единицы, диапазоны и условия. Не округляй без причины.
- Если источники конфликтуют, покажи конфликт явно.
- Не цитируй длинные фрагменты.

Стиль:
- Пиши человечески: короткие предложения, ясные формулировки, без канцелярита.
- Не начинай ответ словами "по предоставленным данным" если можно дать прямой ответ.
- Не используй фразы "в evidence", "metadata-source", "stub", "pipeline", "fragment_id" в пользовательском тексте.
- Не перегружай ответ. Лучше 5-8 сильных пунктов, чем длинная простыня.

Формат ответа строго такой:
Короткий ответ:
1-4 предложения, прямой ответ на вопрос.

Что известно из документов:
- главный факт или наблюдение;
- главный факт или наблюдение.

Параметры и числа:
- значение, единица, условие, если есть;
- если чисел нет: "Точных числовых параметров в найденных документах нет."

Источники:
- название документа или внешнего источника и что именно он подтверждает.

Ограничения:
- что не найдено, где слабое место, что надо проверить.

Что сделать дальше:
- один-два практичных следующих шага.
"""


def summarize_answer(query: str, context: list[dict[str, Any]]) -> tuple[str, str, list[str]]:
    query = repair_text(query)
    context = repair_payload(context)
    provider = (settings.llm_provider or "stub").lower()
    if provider == "stub":
        return _stub_answer(query, context)
    if provider == "openai":
        text = _openai_answer(query, context)
        return "full", repair_text(text), []
    if provider == "yandex":
        try:
            text = _yandex_answer(query, context)
            return "yandex", repair_text(text), []
        except Exception as exc:
            mode, text, warnings = _stub_answer(query, context)
            warnings.append(f"Yandex AI Studio request failed: {exc}. Stub fallback was used.")
            return mode, repair_text(text), warnings
    raise LLMUnavailable(f"Unsupported LLM provider: {provider}")



def _readable_snippet(value: str) -> str:
    text = repair_text(value or "").strip()
    if not text:
        return ""
    if text.startswith("{") and text.endswith("}"):
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            return text
        parts = []
        for key in ("title", "material", "process", "result_summary", "display_value", "canonical_key", "description"):
            current = payload.get(key)
            if current:
                parts.append(repair_text(str(current)))
        if parts:
            return "; ".join(dict.fromkeys(parts))
    return text

def _stub_answer(query: str, context: list[dict[str, Any]]) -> tuple[str, str, list[str]]:
    evidence = context[0] if context else {}
    facts = evidence.get("facts", [])
    matches = evidence.get("match", [])
    experiments = evidence.get("experiments", [])
    external_sources = evidence.get("external_research_context") or evidence.get("external_sources") or []
    domain_knowledge = evidence.get("domain_knowledge") or []
    source_names = sorted({repair_text(str(item.get("filename", "unknown"))) for item in matches[:5]})

    readable_fragments = []
    for match in matches[:4]:
        text = _readable_snippet(match.get("text", ""))
        if text:
            readable_fragments.append(text[:260].strip())

    numeric_facts = []
    other_facts = []
    seen_fact_lines = set()
    query_lower = query.lower()
    domain_first = bool(domain_knowledge) and (not facts and not matches or query_lower.startswith(("что такое", "что это", "какие виды", "что относится", "define", "what is")))
    for fact in facts[:8]:
        subject = repair_text(str(fact.get("subject") or "факт"))
        predicate = repair_text(str(fact.get("predicate") or "связано"))
        value = repair_text(str(fact.get("object_value") or ""))
        unit = repair_text(str(fact.get("unit") or "")).strip()
        fact_line = f"- {subject}: {value}" if value else f"- {subject} ({predicate})"
        if unit and unit not in fact_line:
            fact_line += f" {unit}"
        if fact_line in seen_fact_lines:
            continue
        seen_fact_lines.add(fact_line)
        if fact.get("min_value") is not None or fact.get("max_value") is not None or unit:
            numeric_facts.append(fact_line)
        else:
            other_facts.append(fact_line)

    lines = ["Короткий ответ:"]
    if domain_first:
        primary = domain_knowledge[0]
        direct = primary.get("answer") or primary.get("definition") or f"По запросу '{query}' найдено справочное доменное знание."
        lines.append(repair_text(str(direct)))
    elif facts or matches:
        if readable_fragments:
            lines.append(f"По вопросу '{query}' в загруженных документах есть прямые упоминания. Главный найденный фрагмент говорит: {readable_fragments[0][:240].strip()}")
        else:
            lines.append(f"По вопросу '{query}' в загруженных документах найдены структурированные факты. Ниже я отделяю подтвержденные данные от пробелов, чтобы было понятно, на чем держится вывод.")
    elif external_sources:
        lines.append(f"По вопросу '{query}' в локальном корпусе мало подтверждений, но найдены внешние научные источники для проверки и дальнейшего импорта.")
    else:
        lines.append(f"В локальной базе пока нет достаточных данных, чтобы надежно ответить на вопрос '{query}'. Можно дать только общий ориентир после подключения справочного или внешнего источника.")

    lines.extend(["", "Что известно из документов:"])
    if other_facts:
        lines.extend(other_facts[:5])
    elif domain_first:
        for child in (domain_knowledge[0].get("children") or [])[:6]:
            label = repair_text(str(child.get("label") or ""))
            description = repair_text(str(child.get("description") or ""))
            if label and description:
                lines.append(f"- {label}: {description}")
            elif label:
                lines.append(f"- {label}")
    elif readable_fragments:
        lines.extend(f"- {item}" for item in readable_fragments[:3])
    else:
        lines.append("- Прямых подтверждений в локальных документах не найдено.")

    lines.extend(["", "Параметры и числа:"])
    if numeric_facts:
        lines.extend(numeric_facts[:5])
    else:
        lines.append("- Точных числовых параметров в найденных документах нет.")

    lines.extend(["", "Источники:"])
    if source_names:
        lines.extend(f"- {name}" for name in source_names)
    if domain_knowledge:
        for item in domain_knowledge[:3]:
            title = repair_text(str(item.get("title") or item.get("canonical_key") or "Справочная запись"))
            lines.append(f"- Справочный слой: {title}")
    if not source_names and not domain_knowledge:
        lines.append("- Локальные источники для этого ответа пока не найдены.")

    if external_sources:
        lines.extend(["", "Внешние источники для проверки:"])
        for item in external_sources[:5]:
            title = repair_text(str(item.get("title") or "Без названия")).strip()
            source = repair_text(str(item.get("source") or item.get("source_name") or item.get("connector_id") or "external")).strip()
            year = item.get("year")
            suffix = f", {year}" if year else ""
            lines.append(f"- {title} ({source}{suffix})")

    lines.extend(["", "Ограничения:"])
    if domain_first:
        lines.append("- Ответ опирается на справочный слой; для инженерного решения нужны локальные документы или протоколы испытаний.")
    elif domain_knowledge:
        lines.append("- Справочный слой использован только как дополнительный контекст; приоритет отдан найденным документам.")
    if external_sources:
        lines.append("- Внешние источники пока являются ссылками для проверки, а не проиндексированными доказательствами корпуса.")
    if facts:
        lines.append("- Проверьте диапазоны, единицы и условия применения перед инженерным решением.")
    if not experiments:
        lines.append("- Для этого запроса не найден паспорт эксперимента; экспериментальная валидация может быть неполной.")

    lines.extend(["", "Что сделать дальше:", "- При необходимости сузить вопрос условиями: материал, процесс, температура, концентрация, регион или норматив.", "- Добавить релевантные статьи, отчеты или протоколы через загрузку документов и повторить запрос."])
    return "stub", "\n".join(lines), ["LLM stub mode is enabled; answer uses deterministic evidence summary."]


def _openai_answer(query: str, context: list[dict[str, Any]]) -> str:
    if not settings.openai_api_key:
        raise LLMUnavailable("OPENAI_API_KEY is not configured.")
    payload = {
        "model": settings.openai_model,
        "input": [
            {"role": "system", "content": [{"type": "input_text", "text": SYSTEM_PROMPT}]},
            {"role": "user", "content": [{"type": "input_text", "text": json.dumps({"query": query, "evidence": context}, ensure_ascii=False)}]},
        ],
    }
    response = requests.post(f"{settings.openai_base_url}/responses", headers={"Authorization": f"Bearer {settings.openai_api_key}", "Content-Type": "application/json"}, json=payload, timeout=30)
    response.raise_for_status()
    data = response.json()
    text = ""
    for item in data.get("output", []):
        for chunk in item.get("content", []):
            if chunk.get("type") == "output_text":
                text += chunk.get("text", "")
    return text.strip()


def _yandex_answer(query: str, context: list[dict[str, Any]]) -> str:
    if not settings.yandex_api_key:
        raise LLMUnavailable("YANDEX_AI_API_KEY is not configured.")
    if not settings.yandex_folder_id and not settings.yandex_model_uri:
        raise LLMUnavailable("YANDEX_AI_FOLDER_ID or YANDEX_AI_MODEL_URI must be configured.")
    model_uri = _yandex_model_uri()
    payload = {
        "modelUri": model_uri,
        "completionOptions": {"stream": False, "temperature": 0.12, "maxTokens": "1800"},
        "messages": [
            {"role": "system", "text": SYSTEM_PROMPT},
            {"role": "user", "text": json.dumps({"query": query, "evidence": context}, ensure_ascii=False)},
        ],
    }
    headers = {"Authorization": f"Api-Key {settings.yandex_api_key}", "Content-Type": "application/json"}
    if settings.yandex_folder_id:
        headers["x-folder-id"] = settings.yandex_folder_id
    response = requests.post(f"{settings.yandex_base_url.rstrip('/')}/foundationModels/v1/completion", headers=headers, json=payload, timeout=45)
    response.raise_for_status()
    data = response.json()
    result = data.get("result", data)
    alternatives = result.get("alternatives", [])
    if not alternatives:
        raise LLMUnavailable("Yandex response did not contain alternatives.")
    message = alternatives[0].get("message", {})
    text = message.get("text") or alternatives[0].get("text") or ""
    if not text:
        raise LLMUnavailable("Yandex response did not contain output text.")
    return text.strip()


def _yandex_model_uri() -> str:
    if settings.yandex_model_uri:
        return settings.yandex_model_uri
    if not settings.yandex_folder_id:
        raise LLMUnavailable("YANDEX_AI_FOLDER_ID is required to construct modelUri.")
    model = settings.yandex_model.strip()
    if model.startswith("gpt://"):
        return model
    return f"gpt://{settings.yandex_folder_id}/{model}"
