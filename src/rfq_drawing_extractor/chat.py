from __future__ import annotations

import json
import os
import re
from typing import Any

from pydantic import BaseModel, Field

from .llm_finalizer import (
    _bedrock_client,
    _bedrock_output_text,
    _extract_json_object,
    _select_finalizer_model,
)


SEARCHABLE_SECTIONS = {
    "title_block",
    "dimensions",
    "threads",
    "bom_items",
    "tables",
    "standards",
    "engineering_requirements",
    "manufacturing_requirements",
    "notes",
    "connections",
    "overall_envelope",
    "drawing_regions",
    "review_items",
}
DEFAULT_MATCH_LIMIT = 20
SEARCH_TEXT_FIELDS = {
    "field",
    "label",
    "description",
    "display_value",
    "value",
    "unit",
    "raw_callout",
    "normalized_callout",
    "dimension_type",
    "role",
    "thread_size",
    "thread_class",
    "component_name",
    "requirement_type",
    "semantic_label",
    "view_label",
    "evidence",
    "warnings",
    "is_duplicate",
    "duplicate_of",
    "linked_dimensions",
}
LOW_SIGNAL_KEYWORDS = {
    "a",
    "an",
    "and",
    "are",
    "body",
    "drawing",
    "is",
    "on",
    "the",
    "there",
    "to",
    "tolerance",
    "tolerances",
    "what",
    "which",
}


class ChatQueryPlan(BaseModel):
    intent: str = "general_lookup"
    sections: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    filters: dict[str, list[Any]] = Field(default_factory=dict)
    limit: int = DEFAULT_MATCH_LIMIT


class ChatCitation(BaseModel):
    section: str
    target_id: str = ""
    label: str = ""
    value: Any = None
    page: int | None = None
    region_id: str = ""
    confidence: str = ""
    evidence: str = ""
    warnings: list[str] = Field(default_factory=list)


class ChatMatch(BaseModel):
    section: str
    target_id: str = ""
    score: float = 0.0
    record: dict[str, Any] = Field(default_factory=dict)
    citation: ChatCitation


class ChatAnswer(BaseModel):
    answer: str
    needs_clarification: bool = False
    clarification_question: str | None = None
    warnings: list[str] = Field(default_factory=list)


def answer_question_from_final_json(
    *,
    final_json: dict[str, Any],
    question: str,
    model: str | None = None,
) -> tuple[ChatAnswer, ChatQueryPlan, list[ChatMatch]]:
    selected_model = _select_finalizer_model(model)
    final_data = final_json.get("final_data") if isinstance(final_json.get("final_data"), dict) else final_json
    if not isinstance(final_data, dict):
        raise ValueError("Final JSON does not contain a usable final_data object.")

    query_plan = _create_query_plan(question=question, final_data=final_data, model=selected_model)
    matches = _search_final_data(final_data=final_data, query_plan=query_plan)
    answer = _create_grounded_answer(
        question=question,
        query_plan=query_plan,
        matches=matches,
        model=selected_model,
    )
    return answer, query_plan, matches


def _create_query_plan(*, question: str, final_data: dict[str, Any], model: str) -> ChatQueryPlan:
    section_counts = {
        section: len(value) if isinstance(value, list) else len(value) if isinstance(value, dict) else 0
        for section, value in final_data.items()
        if section in SEARCHABLE_SECTIONS
    }
    prompt = (
        "Convert the user question into a compact JSON search plan for an engineering drawing final JSON.\n"
        "Return JSON only. Do not answer the question.\n\n"
        "Required shape:\n"
        '{"intent":"","sections":[],"keywords":[],"filters":{},"limit":20}\n\n'
        "Rules:\n"
        "- sections must use only available section names.\n"
        "- keywords should include synonyms and drawing terms useful for deterministic search.\n"
        "- filters should map final JSON field names to allowed values.\n"
        "- Use filters for exact concepts like dimension_type, role, requirement_type, is_duplicate, confidence, thread_size.\n"
        "- For broad list questions, choose the relevant section and use an intent containing list.\n"
        "- Do not include markdown fences.\n\n"
        f"Available sections and counts:\n{json.dumps(section_counts, indent=2)}\n\n"
        f"User question:\n{question}"
    )
    response_text = _call_chat_llm(
        model=model,
        system="You create deterministic retrieval plans over engineering final JSON. Return valid JSON only.",
        prompt=prompt,
        max_tokens=1200,
    )
    payload = _extract_json_object(response_text)
    plan = ChatQueryPlan.model_validate(payload)
    plan.sections = [section for section in plan.sections if section in SEARCHABLE_SECTIONS]
    plan.keywords = _dedupe_strings(plan.keywords)
    plan.limit = max(1, min(plan.limit or DEFAULT_MATCH_LIMIT, 50))
    return plan


def _search_final_data(*, final_data: dict[str, Any], query_plan: ChatQueryPlan) -> list[ChatMatch]:
    sections = query_plan.sections or list(SEARCHABLE_SECTIONS)
    records = [
        item
        for section in sections
        for item in _section_records(final_data, section)
    ]
    list_intent = bool(re.search(r"\b(?:list|all|summary|summarize|overview|show)\b", query_plan.intent, re.I))
    scored: list[ChatMatch] = []
    for item in records:
        score = _record_score(item["record"], query_plan, list_intent=list_intent)
        if score <= 0:
            continue
        scored.append(
            ChatMatch(
                section=item["section"],
                target_id=item["target_id"],
                score=score,
                record=item["record"],
                citation=_citation_for_record(item["section"], item["target_id"], item["record"]),
            )
        )

    scored.sort(key=lambda item: item.score, reverse=True)
    return _trim_low_relevance_matches(scored, query_plan.limit)


def _section_records(final_data: dict[str, Any], section: str) -> list[dict[str, Any]]:
    value = final_data.get(section)
    if isinstance(value, list):
        return [
            {
                "section": section,
                "target_id": str(item.get("target_id") or f"{section}.{index}") if isinstance(item, dict) else f"{section}.{index}",
                "record": item if isinstance(item, dict) else {"value": item},
            }
            for index, item in enumerate(value)
        ]
    if isinstance(value, dict):
        if section == "title_block":
            return [
                {
                    "section": section,
                    "target_id": f"title_block.{key}",
                    "record": _record_from_title_field(key, field),
                }
                for key, field in value.items()
            ]
        return [
            {
                "section": section,
                "target_id": f"{section}.{key}",
                "record": _record_from_named_value(key, field),
            }
            for key, field in value.items()
            if isinstance(field, dict) or field not in (None, "", [], {})
        ]
    return []


def _record_from_title_field(key: str, field: Any) -> dict[str, Any]:
    if isinstance(field, dict):
        return {"field": key, "label": field.get("label") or key, **field}
    return {"field": key, "label": key, "value": field, "display_value": field}


def _record_from_named_value(key: str, value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return {"field": key, "label": value.get("label") or key, **value}
    return {"field": key, "label": key, "value": value, "display_value": value}


def _record_score(record: dict[str, Any], query_plan: ChatQueryPlan, *, list_intent: bool) -> float:
    searchable_text = _searchable_text(record)
    score = 0.0
    if list_intent:
        score += 1.0

    for keyword in query_plan.keywords:
        normalized = str(keyword).casefold().strip()
        if not normalized or normalized in LOW_SIGNAL_KEYWORDS:
            continue
        if _keyword_matches(searchable_text, normalized):
            score += 3.0 if len(normalized) > 2 else 1.0

    for field, expected_values in query_plan.filters.items():
        value = _nested_field(record, field)
        if _filter_matches(value, expected_values):
            score += 5.0
        elif _filter_matches(searchable_text, expected_values):
            score += 2.0

    return score


def _keyword_matches(searchable_text: str, keyword: str) -> bool:
    if keyword in searchable_text:
        return True
    tokens = _significant_tokens(keyword)
    return len(tokens) > 1 and all(token in searchable_text for token in tokens)


def _trim_low_relevance_matches(matches: list[ChatMatch], limit: int) -> list[ChatMatch]:
    if not matches:
        return []
    best_score = matches[0].score
    floor = max(1.0, best_score * 0.45)
    return [match for match in matches if match.score >= floor][:limit]


def _filter_matches(value: Any, expected_values: list[Any]) -> bool:
    if value is None:
        return False
    actual = _normalize_search_value(value)
    for expected in expected_values:
        normalized_expected = _normalize_search_value(expected)
        if not normalized_expected:
            continue
        if actual == normalized_expected or normalized_expected in actual:
            return True
        expected_tokens = _significant_tokens(normalized_expected)
        if len(expected_tokens) > 1 and all(token in actual for token in expected_tokens):
            return True
    return False


def _nested_field(record: dict[str, Any], field: str) -> Any:
    current: Any = record
    for part in field.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def _citation_for_record(section: str, target_id: str, record: dict[str, Any]) -> ChatCitation:
    return ChatCitation(
        section=section,
        target_id=target_id,
        label=str(record.get("label") or record.get("field") or record.get("component_name") or ""),
        value=record.get("display_value") or record.get("raw_callout") or record.get("value") or record.get("thread_size") or record.get("component_name"),
        page=_int_or_none(record.get("page")),
        region_id=str(record.get("region_id") or ""),
        confidence=str(record.get("confidence") or ""),
        evidence=str(record.get("evidence") or ""),
        warnings=[str(item) for item in record.get("warnings") or [] if str(item)],
    )


def _create_grounded_answer(
    *,
    question: str,
    query_plan: ChatQueryPlan,
    matches: list[ChatMatch],
    model: str,
) -> ChatAnswer:
    if not matches:
        return ChatAnswer(
            answer="I could not find that in the final JSON.",
            warnings=["No matching final JSON records were found for the query plan."],
        )

    compact_matches = [
        {
            "section": match.section,
            "target_id": match.target_id,
            "score": match.score,
            "record": _compact_record(match.record),
            "citation": match.citation.model_dump(mode="json"),
        }
        for match in matches
    ]
    prompt = (
        "Answer the user question using only the matched final JSON records below.\n"
        "Return JSON only. Do not include markdown fences.\n\n"
        "Required shape:\n"
        '{"answer":"","needs_clarification":false,"clarification_question":null,"warnings":[]}\n\n'
        "Rules:\n"
        "- Do not invent values or use outside knowledge.\n"
        "- If the matches do not answer the question, say it was not found in the final JSON.\n"
        "- Do not map an unknown or unresolved GD&T characteristic to a named characteristic unless the matched record explicitly says so.\n"
        "- Mention page, region, confidence, and warnings when relevant.\n"
        "- If multiple plausible records exist and the question is ambiguous, summarize them and set needs_clarification true.\n"
        "- Keep the answer concise and demo-friendly.\n\n"
        f"User question:\n{question}\n\n"
        f"Query plan:\n{query_plan.model_dump_json(indent=2)}\n\n"
        f"Matched records:\n{json.dumps(compact_matches, indent=2)}"
    )
    response_text = _call_chat_llm(
        model=model,
        system="You answer engineering PDF questions from provided final JSON records only.",
        prompt=prompt,
        max_tokens=1800,
    )
    return ChatAnswer.model_validate(_extract_json_object(response_text))


def _call_chat_llm(*, model: str, system: str, prompt: str, max_tokens: int) -> str:
    region = os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION")
    if not region:
        raise RuntimeError("AWS_REGION or AWS_DEFAULT_REGION is required for chat.")

    os.environ.setdefault("AWS_EC2_METADATA_DISABLED", "true")
    response = _bedrock_client(region).converse(
        modelId=model,
        system=[{"text": system}],
        messages=[{"role": "user", "content": [{"text": prompt}]}],
        inferenceConfig={"maxTokens": max_tokens, "temperature": 0},
    )
    return _bedrock_output_text(response)


def _compact_record(record: dict[str, Any]) -> dict[str, Any]:
    allowed = {
        "field",
        "label",
        "description",
        "display_value",
        "value",
        "unit",
        "raw_callout",
        "normalized_callout",
        "dimension_type",
        "role",
        "thread_size",
        "thread_class",
        "component_name",
        "requirement_type",
        "semantic_label",
        "view_label",
        "page",
        "region_id",
        "confidence",
        "evidence",
        "warnings",
        "is_duplicate",
        "duplicate_of",
        "linked_dimensions",
    }
    return {key: value for key, value in record.items() if key in allowed and value not in (None, "", [], {})}


def _searchable_text(value: Any) -> str:
    pieces: list[str] = []

    def collect(item: Any, key: str = "") -> None:
        if item is None:
            return
        if key and key not in SEARCH_TEXT_FIELDS:
            return
        if isinstance(item, (str, int, float, bool)):
            pieces.append(str(item))
            return
        if isinstance(item, list):
            for child in item:
                collect(child, key)
            return
        if isinstance(item, dict):
            for child_key, child in item.items():
                collect(child, str(child_key))

    collect(value)
    return " ".join(pieces).casefold()


def _normalize_search_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value).casefold().strip()


def _significant_tokens(value: str) -> list[str]:
    return [
        token
        for token in re.findall(r"[a-z0-9Øø.#+-]+", value.casefold())
        if token and token not in LOW_SIGNAL_KEYWORDS
    ]


def _dedupe_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        normalized = str(value).strip()
        key = normalized.casefold()
        if not normalized or key in seen:
            continue
        seen.add(key)
        deduped.append(normalized)
    return deduped


def _int_or_none(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
