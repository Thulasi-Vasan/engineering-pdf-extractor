from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from .models import (
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
    try:
        image_bytes = _render_pages_to_png_300_dpi(pdf_path, [page.page_number for page in raw.pages])
        context = _build_finalizer_context(page_detection, raw, structured)
        response = _call_bedrock_finalizer(
            model=selected_model,
            context=context,
            page_images=image_bytes,
        )
        final_data = LLMFinalEngineeringData.model_validate(_extract_json_object(response["output_text"]))
        _apply_evidence_guardrails(final_data)
        return LLMFinalizationResult(
            status="success",
            model=selected_model,
            final_data=final_data,
            raw_response=response["output_text"],
        )
    except Exception as exc:
        return LLMFinalizationResult(
            status="failed",
            model=selected_model,
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
    try:
        import boto3
        from botocore.config import Config
    except ImportError as exc:
        raise RuntimeError("boto3 and botocore are required for Bedrock final JSON generation.") from exc

    content: list[dict[str, Any]] = [
        {"text": _finalizer_prompt(context)},
    ]
    for _, image_bytes in sorted(page_images.items()):
        content.append({"image": {"format": "png", "source": {"bytes": image_bytes}}})

    client = boto3.client(
        "bedrock-runtime",
        region_name=region,
        config=Config(connect_timeout=10, read_timeout=90, retries={"max_attempts": 1}),
    )
    response = client.converse(
        modelId=model,
        system=[{"text": _system_prompt()}],
        messages=[{"role": "user", "content": content}],
        inferenceConfig={"maxTokens": 7000, "temperature": 0},
    )
    return {"output_text": _bedrock_output_text(response)}


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
        "Required JSON shape:\n"
        "{\n"
        '  "title_block": {},\n'
        '  "drawing_type": null,\n'
        '  "units": null,\n'
        '  "dimensions": [\n'
        '    {"value": null, "unit": "", "raw_callout": "", "label": "", "description": "", "view_label": "", "region_id": "", "page": null, "confidence": "review", "evidence": "", "warnings": []}\n'
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
