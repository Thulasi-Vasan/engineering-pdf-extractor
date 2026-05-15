from __future__ import annotations

import copy
import json
import os
from typing import Any

from pydantic import BaseModel, Field

from .llm_finalizer import (
    _bedrock_client,
    _bedrock_output_text,
    _extract_json_object,
    _select_finalizer_model,
)


class ChatCitation(BaseModel):
    section: str = ""
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
    citations: list[ChatCitation] = Field(default_factory=list)
    needs_clarification: bool = False
    clarification_question: str | None = None
    warnings: list[str] = Field(default_factory=list)


def answer_question_from_final_json(
    *,
    final_json: dict[str, Any],
    question: str,
    model: str | None = None,
) -> ChatAnswer:
    selected_model = _select_finalizer_model(model)
    context = _chat_context(final_json)
    prompt = _chat_prompt(question=question, final_json=context)
    response_text = _call_chat_llm(
        model=selected_model,
        system=(
            "You answer engineering PDF questions using only the provided final JSON. "
            "Return valid JSON only."
        ),
        prompt=prompt,
        max_tokens=2400,
    )
    return ChatAnswer.model_validate(_extract_json_object(response_text))


def matches_from_citations(citations: list[ChatCitation]) -> list[ChatMatch]:
    return [
        ChatMatch(
            section=citation.section,
            target_id=citation.target_id,
            score=1.0,
            record={
                "label": citation.label,
                "value": citation.value,
                "page": citation.page,
                "region_id": citation.region_id,
                "confidence": citation.confidence,
                "evidence": citation.evidence,
                "warnings": citation.warnings,
            },
            citation=citation,
        )
        for citation in citations
    ]


def _chat_context(final_json: dict[str, Any]) -> dict[str, Any]:
    context = copy.deepcopy(final_json)
    context.pop("raw_response", None)
    return context


def _chat_prompt(*, question: str, final_json: dict[str, Any]) -> str:
    return (
        "Answer the user question using only this final engineering JSON.\n"
        "The JSON is already the downstream source of truth. Do not use the original PDF, raw extraction, "
        "or outside knowledge.\n\n"
        "Return compact valid JSON only. Do not include markdown fences.\n\n"
        "Required response shape:\n"
        "{\n"
        '  "answer": "",\n'
        '  "citations": [\n'
        '    {"section": "", "target_id": "", "label": "", "value": null, "page": null, "region_id": "", "confidence": "", "evidence": "", "warnings": []}\n'
        "  ],\n"
        '  "needs_clarification": false,\n'
        '  "clarification_question": null,\n'
        '  "warnings": []\n'
        "}\n\n"
        "Rules:\n"
        "- Use only facts explicitly present in the final JSON.\n"
        "- If the answer is not present, say it was not found in the final JSON.\n"
        "- If multiple matching records exist, list the relevant values instead of forcing one answer.\n"
        "- Cite section names like title_block.material, dimensions.2, threads.0, manufacturing_requirements.3, review_items.0 when possible.\n"
        "- Include page, region_id, confidence, evidence, and warnings in citations when available.\n"
        "- Mention low confidence, review confidence, duplicate dimensions, and warnings when they affect the answer.\n"
        "- Do not infer unresolved GD&T symbols into named controls like cylindricity unless the final JSON explicitly names that control.\n"
        "- Keep the answer concise and user friendly.\n\n"
        f"User question:\n{question}\n\n"
        f"Final JSON without raw_response:\n{json.dumps(final_json, ensure_ascii=False)}"
    )


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
