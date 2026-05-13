from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from pydantic import ValidationError

from .models import (
    LLMFinalDimension,
    LLMFinalEngineeringData,
    LLMFinalizationResult,
    LLMReviewItem,
    PageDetectionResult,
    RawExtractionResult,
    StructuredEngineeringData,
)
from .vision_dimensions import DEFAULT_BEDROCK_VISION_MODEL


def finalize_engineering_data_with_llm(
    pdf_path: Path,
    page_detection: PageDetectionResult,
    raw: RawExtractionResult,
    structured: StructuredEngineeringData,
    *,
    model: str | None = None,
) -> LLMFinalizationResult:
    load_dotenv(override=True)
    selected_model = _select_finalizer_model(model)
    response_text = ""
    try:
        image_bytes = _render_pages_to_png_300_dpi(pdf_path, [page.page_number for page in raw.pages])
        context = _build_finalizer_context(page_detection, raw, structured)
        response = _call_bedrock_finalizer(
            model=selected_model,
            context=context,
            page_images=image_bytes,
        )
        response_text = response["output_text"]
        final_data, raw_response, warnings = _parse_finalizer_response_with_repair(
            model=selected_model,
            response_text=response_text,
        )
        _complete_final_data_from_structured(final_data, structured)
        _apply_evidence_guardrails(final_data)
        return LLMFinalizationResult(
            status="success",
            model=selected_model,
            final_data=final_data,
            raw_response=raw_response,
            warnings=warnings,
        )
    except Exception as exc:
        return LLMFinalizationResult(
            status="failed",
            model=selected_model,
            raw_response=response_text,
            warnings=[f"LLM final JSON generation failed: {exc}"],
        )


def _select_finalizer_model(model: str | None) -> str:
    if model:
        return _normalize_bedrock_model_id(model)

    finalizer_model = os.getenv("BEDROCK_FINALIZER_MODEL")
    if finalizer_model:
        return _normalize_bedrock_model_id(finalizer_model)

    vision_model = os.getenv("BEDROCK_VISION_MODEL")
    if vision_model and vision_model.startswith("anthropic.claude"):
        return _normalize_bedrock_model_id(vision_model)

    return DEFAULT_BEDROCK_VISION_MODEL


def _normalize_bedrock_model_id(model: str) -> str:
    if model == "anthropic.claude-sonnet-4-6":
        return "global.anthropic.claude-sonnet-4-6"
    return model


def _render_pages_to_png_300_dpi(pdf_path: Path, page_numbers: list[int]) -> dict[int, bytes]:
    try:
        import fitz
    except ImportError as exc:
        raise RuntimeError("pymupdf is required for LLM final JSON page rendering.") from exc

    rendered: dict[int, bytes] = {}
    document = fitz.open(str(pdf_path))
    try:
        matrix = fitz.Matrix(300 / 72, 300 / 72)
        for page_number in page_numbers:
            page = document.load_page(page_number - 1)
            pixmap = page.get_pixmap(matrix=matrix, alpha=False)
            rendered[page_number] = pixmap.tobytes("png")
    finally:
        document.close()
    return rendered


def _call_bedrock_finalizer(
    *,
    model: str,
    context: dict[str, Any],
    page_images: dict[int, bytes],
) -> dict[str, str]:
    region = os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION")
    if not region:
        raise RuntimeError("AWS_REGION or AWS_DEFAULT_REGION is required for Bedrock final JSON generation.")

    os.environ.setdefault("AWS_EC2_METADATA_DISABLED", "true")
    content: list[dict[str, Any]] = [
        {"text": _finalizer_prompt(context)},
    ]
    for _, image_bytes in sorted(page_images.items()):
        content.append({"image": {"format": "png", "source": {"bytes": image_bytes}}})

    client = _bedrock_client(region)
    response = client.converse(
        modelId=model,
        system=[{"text": _system_prompt()}],
        messages=[{"role": "user", "content": content}],
        inferenceConfig={"maxTokens": 10000, "temperature": 0},
    )
    return {"output_text": _bedrock_output_text(response)}


def _bedrock_client(region: str) -> Any:
    try:
        import boto3
        from botocore.config import Config
    except ImportError as exc:
        raise RuntimeError("boto3 and botocore are required for Bedrock final JSON generation.") from exc

    return boto3.client(
        "bedrock-runtime",
        region_name=region,
        config=Config(connect_timeout=10, read_timeout=300, retries={"max_attempts": 1}),
    )


def _system_prompt() -> str:
    return (
        "You convert deterministic engineering PDF extraction evidence into a form-ready final JSON object. "
        "The deterministic extraction is the source of truth. Add semantic labels and descriptions only when "
        "supported by the structured data, raw evidence, or rendered page images. Do not invent missing values. "
        "Put uncertain, conflicting, visually inferred, or weakly supported values in review_items."
    )


def _finalizer_prompt(context: dict[str, Any]) -> str:
    return (
        "Create a final engineering extraction JSON for the attached PDF page images.\n\n"
        "Use the deterministic extraction as the source of truth. Enrich labels/descriptions for readability, "
        "consolidate duplicates, and add review items for uncertainty. Do not silently overwrite high-confidence "
        "deterministic values.\n\n"
        "Return only compact valid JSON. Do not include markdown fences.\n\n"
        "Keep string values concise so the JSON remains valid for large drawings.\n\n"
        "Required JSON shape:\n"
        "{\n"
        '  "title_block": {},\n'
        '  "drawing_type": null,\n'
        '  "units": null,\n'
        '  "dimensions": [\n'
        '    {"value": null, "unit": "", "secondary_value": null, "imperial_value": null, "dimension_type": "", "quantity": null, "angle_value": null, "angle_unit": "", "role": "", "role_confidence": "review", "raw_callout": "", "normalized_callout": "", "label": "", "description": "", "view_label": "", "region_id": "", "source": "", "page": null, "confidence": "review", "evidence": "", "warnings": []}\n'
        "  ],\n"
        '  "threads": [\n'
        '    {"thread_size": "", "pitch": null, "threads_per_inch": null, "thread_class": "", "source_type": "", "label": "", "region_id": "", "page": null, "confidence": "review", "evidence": "", "warnings": []}\n'
        "  ],\n"
        '  "tables": [\n'
        '    {"table_type": "", "table_id": "", "title": "", "headers": [], "rows": [], "page": null, "confidence": "review", "evidence": "", "warnings": []}\n'
        "  ],\n"
        '  "manufacturing_requirements": [\n'
        '    {"requirement_type": "", "value": null, "label": "", "region_id": "", "page": null, "confidence": "review", "evidence": "", "warnings": []}\n'
        "  ],\n"
        '  "drawing_regions": [\n'
        '    {"region_id": "", "region_type": "", "label": "", "semantic_label": "", "page": null, "confidence": "review", "evidence": "", "warnings": []}\n'
        "  ],\n"
        '  "review_items": [\n'
        '    {"item_type": "", "value": null, "confidence": "review", "evidence": "", "page": null, "reason": "", "warnings": []}\n'
        "  ],\n"
        '  "warnings": []\n'
        "}\n\n"
        "Rules:\n"
        "- For dimensions, preserve every deterministic field from deterministic_summary.dimensions when the field exists.\n"
        "- Add semantic dimension label, description, and view_label; do not remove raw deterministic fields to make the output shorter.\n"
        "- Preserve evidence text, page numbers, region_id, confidence, and warnings where available.\n"
        "- Use review_items for low-confidence, vision-only, unclear, unsupported, or conflicting values.\n"
        "- Keep dimensions as visible drawing dimensions only; exclude title block numbers, phone numbers, dates, and BOM item numbers.\n"
        "- Never convert units unless explicitly supported. If the visible drawing says inches, keep unit as inch.\n"
        "- Do not treat note/callout text like MIN. THREAD, RELIEF ALLOWED, or THREAD T as drawing view names.\n"
        "- If semantic view naming is uncertain, keep the deterministic region_id and set view_label to a cautious label.\n"
        "- Keep GD&T/font-decoded symbols in review_items unless deterministic evidence confirms the meaning.\n"
        "- Keep drawing_regions as region summaries, not CAD geometry.\n\n"
        "Deterministic context JSON:\n"
        f"{json.dumps(context, ensure_ascii=False, separators=(',', ':'))}"
    )


def _build_finalizer_context(
    page_detection: PageDetectionResult,
    raw: RawExtractionResult,
    structured: StructuredEngineeringData,
) -> dict[str, Any]:
    return {
        "page_detection": {
            "pdf_type": page_detection.pdf_type,
            "page_count": page_detection.page_count,
            "pages": [
                {
                    "page_number": page.page_number,
                    "page_type": page.page_type,
                    "extraction_method": page.extraction_method,
                    "ocr_used": page.ocr_used,
                    "warnings": page.warnings,
                }
                for page in page_detection.pages
            ],
            "document_warnings": page_detection.document_warnings,
        },
        "deterministic_summary": _structured_context(structured),
        "raw_evidence": {
            "pdf_type": raw.pdf_type,
            "page_count": raw.page_count,
            "pages": [_page_context(page) for page in raw.pages],
            "document_warnings": raw.document_warnings,
        },
    }


def _structured_context(structured: StructuredEngineeringData) -> dict[str, Any]:
    return {
        "title_block": _dump_jsonable(structured.title_block),
        "drawing_type": _dump_jsonable(structured.drawing_type),
        "units": _dump_jsonable(structured.units),
        "standards": _dump_jsonable(structured.standards),
        "dimensions": _dump_jsonable(structured.dimensions),
        "review_dimensions": _dump_jsonable(structured.review_dimensions),
        "thread_requirements": _dump_jsonable(structured.thread_requirements),
        "engineering_requirements": _dump_jsonable(structured.engineering_requirements),
        "manufacturing_requirements": _dump_jsonable(structured.manufacturing_requirements),
        "process_requirements": _dump_jsonable(structured.process_requirements),
        "engineering_tables": _dump_jsonable(structured.engineering_tables),
        "drawing_regions": _dump_jsonable(structured.drawing_regions),
        "tolerances_gdnt": _dump_jsonable(structured.tolerances_gdnt),
        "drawing_structure": structured.drawing_structure,
        "warnings": structured.warnings,
    }


def _dump_jsonable(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, list):
        return [_dump_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {key: _dump_jsonable(item) for key, item in value.items()}
    return value


def _page_context(page: object) -> dict[str, Any]:
    return {
        "page_number": getattr(page, "page_number", None),
        "page_type": getattr(page, "page_type", ""),
        "extraction_method": getattr(page, "extraction_method", ""),
        "page_width": getattr(page, "page_width", None),
        "page_height": getattr(page, "page_height", None),
        "text": _limit_text(getattr(page, "text", "") or "", 12000),
        "drawing_primitive_summary": _primitive_summary(getattr(page, "drawing_primitives", []) or []),
        "reconstructed_lines": [
            {
                "text": getattr(line, "normalized_text", "") or getattr(line, "text", ""),
                "bbox": [
                    getattr(line, "x0", None),
                    getattr(line, "top", None),
                    getattr(line, "x1", None),
                    getattr(line, "bottom", None),
                ],
                "warnings": getattr(line, "warnings", []),
            }
            for line in list(getattr(page, "reconstructed_lines", []) or [])[:220]
        ],
        "tables": [
            table.model_dump(mode="json") if hasattr(table, "model_dump") else table
            for table in list(getattr(page, "tables", []) or [])[:20]
        ],
        "warnings": getattr(page, "warnings", []),
    }


def _primitive_summary(primitives: list[object]) -> dict[str, Any]:
    counts: dict[str, int] = {}
    for primitive in primitives:
        primitive_type = str(getattr(primitive, "primitive_type", "unknown_vector") or "unknown_vector")
        counts[primitive_type] = counts.get(primitive_type, 0) + 1
    return {"total": len(primitives), "by_type": counts}


def _parse_finalizer_response_with_repair(
    *,
    model: str,
    response_text: str,
) -> tuple[LLMFinalEngineeringData, str, list[str]]:
    try:
        return _parse_final_data(response_text), response_text, []
    except (json.JSONDecodeError, ValueError, ValidationError) as exc:
        repaired_text = _call_bedrock_json_repair(
            model=model,
            invalid_json=response_text,
            error=str(exc),
        )
        return (
            _parse_final_data(repaired_text),
            f"{response_text}\n\n--- JSON REPAIR RESPONSE ---\n{repaired_text}",
            ["Initial Claude JSON was invalid and was repaired automatically."],
        )


def _parse_final_data(text: str) -> LLMFinalEngineeringData:
    return LLMFinalEngineeringData.model_validate(_extract_json_object(text))


def _call_bedrock_json_repair(*, model: str, invalid_json: str, error: str) -> str:
    region = os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION")
    if not region:
        raise RuntimeError("AWS_REGION or AWS_DEFAULT_REGION is required for Bedrock JSON repair.")

    prompt = (
        "Repair the following JSON response so it is valid compact JSON only.\n"
        "Preserve the same facts and field names. Do not add new facts. Do not explain the repair. "
        "Do not include markdown fences.\n\n"
        "The JSON must match this top-level shape:\n"
        '{"title_block":{},"drawing_type":null,"units":null,"dimensions":[],"threads":[],"tables":[],'
        '"manufacturing_requirements":[],"drawing_regions":[],"review_items":[],"warnings":[]}\n\n'
        f"Parser error:\n{_limit_text(error, 2000)}\n\n"
        f"Invalid JSON response:\n{_limit_text(invalid_json, 60000)}"
    )
    response = _bedrock_client(region).converse(
        modelId=model,
        system=[{"text": "You repair malformed JSON. Return valid JSON only."}],
        messages=[{"role": "user", "content": [{"text": prompt}]}],
        inferenceConfig={"maxTokens": 10000, "temperature": 0},
    )
    return _bedrock_output_text(response)


def _complete_final_data_from_structured(
    final_data: LLMFinalEngineeringData,
    structured: StructuredEngineeringData,
) -> None:
    deterministic_dimensions = _dump_jsonable(structured.dimensions)
    if not isinstance(deterministic_dimensions, list):
        return

    used_indexes: set[int] = set()
    completed_dimensions: list[LLMFinalDimension] = []
    for dimension in final_data.dimensions:
        match_index, match = _best_dimension_match(dimension, deterministic_dimensions, used_indexes)
        if match is None:
            dimension.warnings.append(
                "Could not match this LLM dimension to a deterministic structured dimension."
            )
            if dimension.confidence != "review":
                dimension.confidence = "review"
            final_data.review_items.append(
                LLMReviewItem(
                    item_type="dimension",
                    value=dimension.raw_callout or dimension.value,
                    confidence="review",
                    evidence=dimension.evidence,
                    page=dimension.page,
                    reason="LLM finalizer returned a dimension that could not be grounded to structured data.",
                    warnings=["Review before using this dimension for form filling."],
                )
            )
            completed_dimensions.append(dimension)
            continue

        used_indexes.add(match_index)
        completed_dimensions.append(_merge_dimension_with_structured(dimension, match))

    for index, deterministic_dimension in enumerate(deterministic_dimensions):
        if index in used_indexes or not isinstance(deterministic_dimension, dict):
            continue
        added_dimension = _dimension_from_structured(deterministic_dimension)
        added_dimension.warnings.append(
            "Added from deterministic structured data because the LLM finalizer omitted this dimension."
        )
        completed_dimensions.append(added_dimension)

    final_data.dimensions = completed_dimensions


def _best_dimension_match(
    dimension: LLMFinalDimension,
    candidates: list[Any],
    used_indexes: set[int],
) -> tuple[int, dict[str, Any] | None]:
    best_index = -1
    best_score = 0
    for index, candidate in enumerate(candidates):
        if index in used_indexes or not isinstance(candidate, dict):
            continue
        score = _dimension_match_score(dimension, candidate)
        if score > best_score:
            best_index = index
            best_score = score

    if best_index == -1 or best_score < 4:
        return -1, None
    return best_index, candidates[best_index]


def _dimension_match_score(dimension: LLMFinalDimension, candidate: dict[str, Any]) -> int:
    score = 0
    if dimension.page is not None and dimension.page == candidate.get("page"):
        score += 2
    if _same_non_empty(dimension.region_id, candidate.get("region_id")):
        score += 2
    if _same_non_empty(dimension.raw_callout, candidate.get("raw_callout")):
        score += 5
    if _same_non_empty(dimension.evidence, candidate.get("evidence")):
        score += 4
    if _same_non_empty(dimension.normalized_callout, candidate.get("normalized_callout")):
        score += 4
    if _same_number(dimension.value, candidate.get("value")):
        score += 2
    if _same_non_empty(dimension.unit, candidate.get("unit")):
        score += 1
    return score


def _merge_dimension_with_structured(
    llm_dimension: LLMFinalDimension,
    deterministic_dimension: dict[str, Any],
) -> LLMFinalDimension:
    semantic_fields = {
        "label": llm_dimension.label,
        "description": llm_dimension.description,
        "view_label": llm_dimension.view_label,
    }
    merged = _dimension_from_structured(deterministic_dimension)
    merged.label = semantic_fields["label"]
    merged.description = semantic_fields["description"]
    merged.view_label = semantic_fields["view_label"]
    merged.warnings = _merge_warnings(
        deterministic_dimension.get("warnings", []),
        llm_dimension.warnings,
    )
    return merged


def _dimension_from_structured(dimension: dict[str, Any]) -> LLMFinalDimension:
    return LLMFinalDimension(
        value=dimension.get("value"),
        unit=str(dimension.get("unit") or ""),
        secondary_value=dimension.get("secondary_value"),
        imperial_value=dimension.get("imperial_value"),
        dimension_type=str(dimension.get("dimension_type") or ""),
        quantity=dimension.get("quantity"),
        angle_value=dimension.get("angle_value"),
        angle_unit=str(dimension.get("angle_unit") or ""),
        role=str(dimension.get("role") or ""),
        role_confidence=dimension.get("role_confidence") or "review",
        raw_callout=str(dimension.get("raw_callout") or ""),
        normalized_callout=str(dimension.get("normalized_callout") or ""),
        region_id=str(dimension.get("region_id") or ""),
        source=str(dimension.get("source") or ""),
        page=dimension.get("page"),
        confidence=dimension.get("confidence") or "review",
        evidence=str(dimension.get("evidence") or ""),
        warnings=list(dimension.get("warnings") or []),
    )


def _same_non_empty(left: Any, right: Any) -> bool:
    left_text = _match_text(left)
    right_text = _match_text(right)
    return bool(left_text and right_text and left_text == right_text)


def _match_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip().lower()


def _same_number(left: Any, right: Any) -> bool:
    try:
        return abs(float(left) - float(right)) < 0.000001
    except (TypeError, ValueError):
        return False


def _merge_warnings(*warning_lists: Any) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for warning_list in warning_lists:
        if not isinstance(warning_list, list):
            continue
        for warning in warning_list:
            text = str(warning)
            if text in seen:
                continue
            seen.add(text)
            merged.append(text)
    return merged


def _apply_evidence_guardrails(final_data: LLMFinalEngineeringData) -> None:
    _require_evidence(final_data.dimensions, "dimension", final_data)
    _require_evidence(final_data.threads, "thread", final_data)
    _require_evidence(final_data.tables, "table", final_data)
    _require_evidence(final_data.manufacturing_requirements, "manufacturing_requirement", final_data)
    _require_evidence(final_data.drawing_regions, "drawing_region", final_data)


def _require_evidence(records: list[object], item_type: str, final_data: LLMFinalEngineeringData) -> None:
    for record in records:
        evidence = str(getattr(record, "evidence", "") or "").strip()
        if evidence:
            continue
        warnings = getattr(record, "warnings", None)
        if isinstance(warnings, list):
            warnings.append("No supporting evidence was provided by the LLM finalizer.")
        if getattr(record, "confidence", "review") != "review":
            setattr(record, "confidence", "review")
        final_data.review_items.append(
            LLMReviewItem(
                item_type=item_type,
                value=getattr(record, "value", None) or getattr(record, "label", "") or getattr(record, "table_id", ""),
                confidence="review",
                evidence="",
                page=getattr(record, "page", None),
                reason="LLM finalizer returned a factual item without supporting evidence.",
                warnings=["Evidence is required before this item can be trusted for form filling."],
            )
        )


def _limit_text(value: str, limit: int) -> str:
    compact = re.sub(r"\s+", " ", value).strip()
    return compact if len(compact) <= limit else compact[: limit - 3].rstrip() + "..."


def _bedrock_output_text(response: dict[str, Any]) -> str:
    parts = []
    message = response.get("output", {}).get("message", {})
    for content in message.get("content", []) or []:
        if content.get("text"):
            parts.append(str(content["text"]))
    if not parts:
        raise RuntimeError("Bedrock response did not include text output.")
    return "\n".join(parts)


def _extract_json_object(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        payload = json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise
        payload = json.loads(cleaned[start : end + 1])
    if not isinstance(payload, dict):
        raise ValueError("LLM finalizer response must be a JSON object.")
    return payload
