from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from pydantic import ValidationError

from .models import (
    LLMEnrichmentResponse,
    LLMFinalBomItem,
    LLMFinalConnection,
    LLMFinalDimension,
    LLMFinalDrawingRegion,
    LLMFinalEngineeringData,
    LLMFinalField,
    LLMFinalManufacturingRequirement,
    LLMFinalTable,
    LLMFinalThread,
    LLMFinalizationResult,
    LLMReviewItem,
    PageDetectionResult,
    RawExtractionResult,
    StructuredEngineeringData,
)
from .vision_dimensions import DEFAULT_BEDROCK_VISION_MODEL


MAX_ENRICHMENT_TARGETS = 110
SECTION_ENRICHMENT_LIMITS = {
    "dimensions": 35,
    "threads": 25,
    "bom_items": 45,
    "tables": 10,
    "standards": 10,
    "engineering_requirements": 25,
    "manufacturing_requirements": 25,
    "notes": 8,
    "connections": 25,
    "drawing_regions": 12,
}


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
    raw_response = ""
    warnings: list[str] = []
    try:
        final_data = _build_base_final_data(structured)
        try:
            image_bytes = _render_pages_to_png_300_dpi(pdf_path, [page.page_number for page in raw.pages])
            context = _build_finalizer_context(page_detection, raw, structured, final_data)
            response = _call_bedrock_finalizer(
                model=selected_model,
                context=context,
                page_images=image_bytes,
            )
            response_text = response["output_text"]
            raw_response = response_text
            enrichment, raw_response, enrichment_warnings = _parse_enrichment_response_with_repair(
                model=selected_model,
                response_text=response_text,
            )
            warnings.extend(enrichment_warnings)
            warnings.extend(_merge_enrichment(final_data, enrichment))
        except Exception as exc:
            raw_response = response_text
            warning = f"LLM enrichment failed; final JSON was built from deterministic extraction only: {exc}"
            warnings.append(warning)
            final_data.warnings.append(warning)
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
        "You enrich deterministic engineering PDF extraction records for form-ready display. "
        "The backend owns the final JSON schema and deterministic facts. Return only semantic enrichment updates "
        "for known target_id values. Do not rewrite, remove, or change extracted factual values."
    )


def _finalizer_prompt(context: dict[str, Any]) -> str:
    return (
        "Create semantic enrichment updates for the attached PDF page images.\n\n"
        "The backend has already built the final engineering JSON from deterministic extraction. "
        "Your job is only to add human-readable labels, descriptions, view labels, semantic labels, warnings, "
        "and review notes for the provided target_id records.\n\n"
        "Return only compact valid JSON. Do not include markdown fences.\n\n"
        "Keep every update compact so the JSON remains valid for large drawings.\n\n"
        "Required JSON shape:\n"
        "{\n"
        '  "updates": [\n'
        '    {"target_id": "dimensions.0", "label": "", "description": "", "view_label": "", "semantic_label": "", "display_value": null, "review_reason": "", "warnings": []}\n'
        "  ],\n"
        '  "review_items": [\n'
        '    {"item_type": "", "value": null, "confidence": "review", "evidence": "", "page": null, "reason": "", "warnings": []}\n'
        "  ],\n"
        '  "warnings": []\n'
        "}\n\n"
        "Rules:\n"
        "- Only use target_id values from enrichment_targets.\n"
        "- Enrichment targets may include title_block, dimensions, threads, bom_items, tables, standards, engineering_requirements, manufacturing_requirements, notes, connections, overall_envelope, and drawing_regions.\n"
        "- Do not return the final engineering JSON; return only updates, review_items, and warnings.\n"
        "- Allowed update fields are target_id, label, description, view_label, semantic_label, display_value, review_reason, and warnings.\n"
        "- label must be at most 8 words.\n"
        "- description must be 1 short sentence and at most 120 characters.\n"
        "- view_label must be at most 6 words.\n"
        "- semantic_label must be a short machine-friendly phrase.\n"
        "- warnings must contain at most 1 item per update, and only for a real downstream risk.\n"
        "- Prefer empty warnings over routine uncertainty notes.\n"
        "- Do not repeat evidence text in descriptions.\n"
        "- Do not explain low-confidence or uncertain feature association for every dimension.\n"
        "- Do not change values, units, raw_callout, page, source, region_id, dimension_type, thread_size, thread_class, confidence, or evidence.\n"
        "- Use both structured evidence and the rendered page image when writing labels, descriptions, and view_label values.\n"
        "- Do not assign a view_label unless the rendered image supports the view association; otherwise leave view_label empty or use a cautious generic region label.\n"
        "- Do not claim exact feature association from the image unless the leader/callout relationship is visually clear.\n"
        "- If the image does not clearly support feature association, keep the description generic; do not add a warning unless it affects downstream use.\n"
        "- Keep descriptions cautious; do not invent design intent, manufacturing purpose, or feature function beyond the visible evidence.\n"
        "- If a label or description is mildly uncertain, keep it generic instead of adding warning text.\n"
        "- Use review_reason only for real downstream risks, not routine low-confidence semantic labels.\n"
        "- Do not treat note/callout text like MIN. THREAD, RELIEF ALLOWED, or THREAD T as drawing view names.\n"
        "- Put only conflicts, GD&T uncertainty, duplicate dimensions, suspected overlay/stamp issues, unsupported claims, or unknown target problems in review_items.\n"
        "- review_items reason must be one short sentence.\n\n"
        "Deterministic context JSON:\n"
        f"{json.dumps(context, ensure_ascii=False, separators=(',', ':'))}"
    )


def _build_finalizer_context(
    page_detection: PageDetectionResult,
    raw: RawExtractionResult,
    structured: StructuredEngineeringData,
    final_data: LLMFinalEngineeringData,
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
        "enrichment_targets": _enrichment_targets(final_data),
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
        "bom_components": _dump_jsonable(structured.bom_components),
        "dimensions": _dump_jsonable(structured.dimensions),
        "review_dimensions": _dump_jsonable(structured.review_dimensions),
        "thread_requirements": _dump_jsonable(structured.thread_requirements),
        "engineering_requirements": _dump_jsonable(structured.engineering_requirements),
        "manufacturing_requirements": _dump_jsonable(structured.manufacturing_requirements),
        "process_requirements": _dump_jsonable(structured.process_requirements),
        "connections": _dump_jsonable(structured.connections),
        "notes": _dump_jsonable(structured.notes),
        "engineering_tables": _dump_jsonable(structured.engineering_tables),
        "drawing_regions": _dump_jsonable(structured.drawing_regions),
        "tolerances_gdnt": _dump_jsonable(structured.tolerances_gdnt),
        "overall_envelope": _dump_jsonable(structured.overall_envelope),
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


def _build_base_final_data(structured: StructuredEngineeringData) -> LLMFinalEngineeringData:
    final_data = LLMFinalEngineeringData(
        title_block=_dump_jsonable(structured.title_block),
        drawing_type=_field_value(structured.drawing_type),
        units=_field_value(structured.units),
        dimensions=[
            _dimension_from_structured(dimension)
            for dimension in _list_of_dicts(_dump_jsonable(structured.dimensions))
        ],
        threads=[
            _thread_from_structured(thread)
            for thread in _list_of_dicts(_dump_jsonable(structured.thread_requirements))
        ],
        bom_items=[
            _bom_item_from_structured(component)
            for component in _list_of_dicts(_dump_jsonable(structured.bom_components))
        ],
        tables=[
            _table_from_structured(table)
            for table in _list_of_dicts(_dump_jsonable(structured.engineering_tables))
        ],
        standards=[
            _field_from_structured(field, "standard")
            for field in _list_of_dicts(_dump_jsonable(structured.standards))
        ],
        engineering_requirements=[
            _engineering_requirement_from_structured(requirement)
            for requirement in _list_of_dicts(_dump_jsonable(structured.engineering_requirements))
        ],
        manufacturing_requirements=_base_manufacturing_requirements(structured),
        notes=[
            _field_from_structured(note, "note")
            for note in _list_of_dicts(_dump_jsonable(structured.notes))
        ],
        connections=[
            _connection_from_structured(connection)
            for connection in _list_of_dicts(_dump_jsonable(structured.connections))
        ],
        overall_envelope=_overall_envelope_from_structured(structured),
        drawing_regions=[
            _drawing_region_from_structured(region)
            for region in _list_of_dicts(_dump_jsonable(structured.drawing_regions))
        ],
        warnings=list(structured.warnings),
    )
    _add_base_review_items(final_data, structured)
    return final_data


def _field_value(field: Any) -> Any:
    if field is None:
        return None
    dumped = _dump_jsonable(field)
    if isinstance(dumped, dict) and "value" in dumped:
        return dumped["value"]
    return dumped


def _list_of_dicts(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _thread_from_structured(thread: dict[str, Any]) -> LLMFinalThread:
    source_type = "direct_callout"
    if thread.get("source_table"):
        source_type = "thread_chart"
    if thread.get("chart_reference") and not thread.get("thread_size"):
        source_type = "chart_reference"
    return LLMFinalThread(
        thread_size=str(thread.get("thread_size") or thread.get("label") or ""),
        pitch=thread.get("pitch"),
        threads_per_inch=thread.get("threads_per_inch"),
        thread_class=str(thread.get("thread_class") or ""),
        source_type=source_type,
        label=str(thread.get("label") or ""),
        region_id=str(thread.get("region_id") or ""),
        page=thread.get("page"),
        confidence=thread.get("confidence") or "review",
        evidence=str(thread.get("evidence") or ""),
        warnings=list(thread.get("warnings") or []),
    )


def _bom_item_from_structured(component: dict[str, Any]) -> LLMFinalBomItem:
    return LLMFinalBomItem(
        item_no=str(component.get("item_no") or ""),
        component_name=str(component.get("component_name") or ""),
        quantity=component.get("quantity"),
        material=component.get("material"),
        note=str(component.get("note") or ""),
        category=str(component.get("category") or ""),
        label=str(component.get("component_name") or component.get("item_no") or ""),
        source=str(component.get("source") or ""),
        page=component.get("page"),
        confidence=component.get("confidence") or "review",
        evidence=str(component.get("evidence") or ""),
        warnings=list(component.get("warnings") or []),
    )


def _table_from_structured(table: dict[str, Any]) -> LLMFinalTable:
    return LLMFinalTable(
        table_type=str(table.get("table_type") or ""),
        table_id=str(table.get("table_id") or ""),
        title=str(table.get("table_type") or table.get("table_id") or ""),
        headers=list(table.get("headers") or []),
        rows=list(table.get("rows") or []),
        page=table.get("page"),
        confidence=table.get("confidence") or "review",
        evidence=str(table.get("evidence") or ""),
        warnings=list(table.get("warnings") or []),
    )


def _field_from_structured(field: dict[str, Any], field_type: str) -> LLMFinalField:
    value = field.get("value")
    return LLMFinalField(
        field_type=field_type,
        value=value,
        label=_label_from_requirement_type(field_type),
        display_value=value,
        source=str(field.get("source") or ""),
        page=field.get("page"),
        confidence=field.get("confidence") or "review",
        evidence=str(field.get("evidence") or ""),
        warnings=list(field.get("warnings") or []),
    )


def _engineering_requirement_from_structured(requirement: dict[str, Any]) -> LLMFinalField:
    requirement_type = str(requirement.get("requirement_type") or "requirement")
    value = requirement.get("value")
    return LLMFinalField(
        field_type=requirement_type,
        value=value,
        label=_label_from_requirement_type(requirement_type),
        display_value=_requirement_display_value(value, requirement_type),
        region_id=str(requirement.get("region_id") or ""),
        source=str(requirement.get("source") or ""),
        page=requirement.get("page"),
        confidence=requirement.get("confidence") or "review",
        evidence=str(requirement.get("evidence") or ""),
        warnings=list(requirement.get("warnings") or []),
    )


def _base_manufacturing_requirements(
    structured: StructuredEngineeringData,
) -> list[LLMFinalManufacturingRequirement]:
    requirements: list[LLMFinalManufacturingRequirement] = []
    seen: set[tuple[str, str, str, int | None]] = set()
    omitted_process_duplicates: list[str] = []
    source_groups = [
        _list_of_dicts(_dump_jsonable(structured.engineering_requirements)),
        _list_of_dicts(_dump_jsonable(structured.manufacturing_requirements)),
        _list_of_dicts(_dump_jsonable(structured.process_requirements)),
        _list_of_dicts(_dump_jsonable(structured.tolerances_gdnt)),
    ]
    for group in source_groups:
        for requirement in group:
            if requirement.get("requirement_type") == "thread":
                continue
            final_requirement = _requirement_from_structured(requirement)
            key = (
                _requirement_dedupe_type(final_requirement),
                _normalize_requirement_text(final_requirement.value),
                _normalize_requirement_text(final_requirement.evidence),
                final_requirement.page,
            )
            if key in seen:
                continue
            if _is_process_duplicate(final_requirement, requirements):
                omitted_process_duplicates.append(str(final_requirement.evidence or final_requirement.value))
                continue
            seen.add(key)
            requirements.append(final_requirement)
    if omitted_process_duplicates:
        _append_unique_warning(
            requirements,
            "Duplicate heat treatment / finish process placeholder omitted from final requirements.",
            {"heat_treatment", "finish"},
        )
    return requirements


def _requirement_from_structured(requirement: dict[str, Any]) -> LLMFinalManufacturingRequirement:
    raw_value = requirement.get("value")
    requirement_type = str(requirement.get("requirement_type") or _requirement_type_from_value(raw_value))
    display_value = _requirement_display_value(raw_value, requirement_type)
    return LLMFinalManufacturingRequirement(
        requirement_type=requirement_type,
        value=display_value,
        label=_label_from_requirement_type(requirement_type),
        region_id=str(requirement.get("region_id") or _region_for_requirement(requirement_type)),
        page=requirement.get("page"),
        confidence=requirement.get("confidence") or "review",
        evidence=str(requirement.get("evidence") or ""),
        warnings=list(requirement.get("warnings") or []),
    )


def _requirement_dedupe_type(requirement: LLMFinalManufacturingRequirement) -> str:
    if requirement.requirement_type in {"process", "heat_treatment", "finish"} and _is_not_specified_value(
        requirement.value
    ):
        return "heat_treatment_finish_unspecified"
    if _is_gdt_requirement(requirement):
        return f"gdt:{_normalize_requirement_text(requirement.evidence)}"
    return requirement.requirement_type


def _normalize_requirement_text(value: Any) -> str:
    text = _match_text(value)
    text = text.replace("`", "±")
    text = text.replace("~", "°")
    text = re.sub(r"[^a-z0-9.#±°+-]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _is_process_duplicate(
    requirement: LLMFinalManufacturingRequirement,
    existing: list[LLMFinalManufacturingRequirement],
) -> bool:
    if requirement.requirement_type not in {"process", "heat_treatment", "finish"}:
        return False
    if not _is_not_specified_value(requirement.value):
        return False
    existing_types = {
        item.requirement_type
        for item in existing
        if item.requirement_type in {"heat_treatment", "finish"} and _is_not_specified_value(item.value)
    }
    return bool(existing_types)


def _is_not_specified_value(value: Any) -> bool:
    text = _match_text(value)
    return "not specified" in text or text in {"", "none", "n/a"}


def _is_gdt_requirement(requirement: LLMFinalManufacturingRequirement) -> bool:
    text = _match_text(requirement.value)
    evidence = _match_text(requirement.evidence)
    return "feature control frame" in text or "gdt" in text or evidence in {"c.002", "bn.002b", "j.002a", ".002"}


def _append_unique_warning(
    requirements: list[LLMFinalManufacturingRequirement],
    warning: str,
    preferred_types: set[str],
) -> None:
    for requirement in requirements:
        if requirement.requirement_type in preferred_types:
            requirement.warnings = _merge_warnings(requirement.warnings, [warning])
            return


def _requirement_type_from_value(value: Any) -> str:
    text = _match_text(value)
    if "surface finish" in text:
        return "surface_finish"
    if "material" in text:
        return "material"
    if "heat treatment" in text:
        return "heat_treatment"
    if text.startswith("finish"):
        return "finish"
    if "edge" in text or "burr" in text:
        return "edge_break"
    return "requirement"


def _requirement_display_value(value: Any, requirement_type: str) -> Any:
    text = str(value or "")
    if ":" not in text:
        return value
    prefix, suffix = text.split(":", 1)
    if _match_text(prefix).replace(" ", "_") == requirement_type:
        return suffix.strip()
    return value


def _region_for_requirement(requirement_type: str) -> str:
    return ""


def _label_from_requirement_type(requirement_type: str) -> str:
    return requirement_type.replace("_", " ").title()


def _drawing_region_from_structured(region: dict[str, Any]) -> LLMFinalDrawingRegion:
    return LLMFinalDrawingRegion(
        region_id=str(region.get("region_id") or ""),
        region_type=str(region.get("region_type") or ""),
        label=str(region.get("label") or ""),
        page=region.get("page"),
        confidence=region.get("confidence") or "review",
        evidence=str(region.get("evidence") or ""),
        warnings=list(region.get("warnings") or []),
    )


def _connection_from_structured(connection: dict[str, Any]) -> LLMFinalConnection:
    return LLMFinalConnection(
        label=str(connection.get("label") or ""),
        size=str(connection.get("size") or ""),
        connection_type=str(connection.get("connection_type") or ""),
        option=bool(connection.get("option")),
        source=str(connection.get("source") or ""),
        page=connection.get("page"),
        confidence=connection.get("confidence") or "review",
        evidence=str(connection.get("evidence") or ""),
        warnings=list(connection.get("warnings") or []),
    )


def _overall_envelope_from_structured(structured: StructuredEngineeringData) -> dict[str, Any]:
    envelope = _dump_jsonable(structured.overall_envelope)
    return envelope if isinstance(envelope, dict) else {}


def _add_base_review_items(final_data: LLMFinalEngineeringData, structured: StructuredEngineeringData) -> None:
    for dimension in _list_of_dicts(_dump_jsonable(structured.review_dimensions)):
        final_data.review_items.append(
            LLMReviewItem(
                item_type="dimension",
                value=dimension.get("raw_callout") or dimension.get("value"),
                confidence=dimension.get("confidence") or "review",
                evidence=str(dimension.get("evidence") or ""),
                page=dimension.get("page"),
                reason="Deterministic parser marked this dimension for review.",
                warnings=list(dimension.get("warnings") or []),
            )
        )


def _enrichment_targets(final_data: LLMFinalEngineeringData) -> list[dict[str, Any]]:
    targets: list[dict[str, Any]] = []
    skipped_by_section: dict[str, int] = {}
    for key, value in final_data.title_block.items():
        targets.append({"target_id": f"title_block.{key}", "record_type": "title_block", "data": value})
    _append_section_targets(targets, skipped_by_section, "dimensions", "dimension", final_data.dimensions)
    _append_section_targets(targets, skipped_by_section, "threads", "thread", final_data.threads)
    _append_section_targets(targets, skipped_by_section, "bom_items", "bom_item", final_data.bom_items)
    _append_section_targets(targets, skipped_by_section, "tables", "table", final_data.tables)
    _append_section_targets(targets, skipped_by_section, "standards", "standard", final_data.standards)
    _append_section_targets(
        targets,
        skipped_by_section,
        "engineering_requirements",
        "engineering_requirement",
        final_data.engineering_requirements,
    )
    _append_section_targets(
        targets,
        skipped_by_section,
        "manufacturing_requirements",
        "manufacturing_requirement",
        final_data.manufacturing_requirements,
    )
    _append_note_targets(targets, skipped_by_section, final_data.notes)
    _append_section_targets(targets, skipped_by_section, "connections", "connection", final_data.connections)
    _append_section_targets(targets, skipped_by_section, "drawing_regions", "drawing_region", final_data.drawing_regions)
    targets.extend(_overall_envelope_targets(final_data.overall_envelope))
    targets = _apply_total_target_budget(targets, skipped_by_section)
    _record_skipped_target_warnings(final_data, skipped_by_section)
    return targets


def _append_section_targets(
    targets: list[dict[str, Any]],
    skipped_by_section: dict[str, int],
    section: str,
    record_type: str,
    records: list[Any],
) -> None:
    limit = SECTION_ENRICHMENT_LIMITS.get(section, len(records))
    for index, item in enumerate(records):
        if index >= limit:
            skipped_by_section[section] = skipped_by_section.get(section, 0) + 1
            continue
        targets.append(
            {
                "target_id": f"{section}.{index}",
                "record_type": record_type,
                "data": item.model_dump(mode="json"),
            }
        )


def _append_note_targets(
    targets: list[dict[str, Any]],
    skipped_by_section: dict[str, int],
    notes: list[LLMFinalField],
) -> None:
    limit = SECTION_ENRICHMENT_LIMITS["notes"]
    included = 0
    for index, note in enumerate(notes):
        if not _is_standalone_note_for_enrichment(note):
            skipped_by_section["notes"] = skipped_by_section.get("notes", 0) + 1
            continue
        if included >= limit:
            skipped_by_section["notes"] = skipped_by_section.get("notes", 0) + 1
            continue
        included += 1
        targets.append(
            {
                "target_id": f"notes.{index}",
                "record_type": "note",
                "data": note.model_dump(mode="json"),
            }
        )


def _is_standalone_note_for_enrichment(note: LLMFinalField) -> bool:
    text = _match_text(" ".join([str(note.value or ""), note.evidence, note.label, note.description]))
    if len(text) < 8 or text in {"option", "standard", "service valve"}:
        return False
    high_value_terms = [
        "application",
        "standard notes",
        "unless otherwise",
        "legal note",
        "drawing use",
        "disclosure",
        "restriction",
    ]
    if any(term in text for term in high_value_terms) and not _looks_like_bom_or_dimension_fragment(text):
        return True
    return False


def _looks_like_bom_or_dimension_fragment(text: str) -> bool:
    if re.search(r"\b\d+\s+[a-z][a-z0-9/\"() .-]+?\b\d+\s+[a-z]", text):
        return True
    bom_terms = [
        "angle valve",
        "discharge flange",
        "solenoid valve",
        "liquid injection",
        "capillary",
        "checkvalve",
        "check valve",
        "oil drain",
        "oil level",
        "oil connector",
        "oil sight glass",
        "safety valve",
        "service flange",
        "service valve",
        "cable box",
        "flare",
        "npt",
    ]
    term_count = sum(1 for term in bom_terms if term in text)
    number_count = len(re.findall(r"\b\d+(?:\.\d+)?\b", text))
    return term_count >= 2 or (term_count >= 1 and number_count >= 3)


def _apply_total_target_budget(
    targets: list[dict[str, Any]],
    skipped_by_section: dict[str, int],
) -> list[dict[str, Any]]:
    if len(targets) <= MAX_ENRICHMENT_TARGETS:
        return targets
    kept = targets[:MAX_ENRICHMENT_TARGETS]
    for target in targets[MAX_ENRICHMENT_TARGETS:]:
        section = str(target.get("target_id", "")).split(".", 1)[0] or "unknown"
        skipped_by_section[section] = skipped_by_section.get(section, 0) + 1
    return kept


def _record_skipped_target_warnings(
    final_data: LLMFinalEngineeringData,
    skipped_by_section: dict[str, int],
) -> None:
    for section, count in sorted(skipped_by_section.items()):
        if count <= 0:
            continue
        final_data.warnings.append(
            f"Skipped {count} {section} target{'s' if count != 1 else ''} from Claude enrichment to reduce JSON size."
        )


def _overall_envelope_targets(overall_envelope: dict[str, Any]) -> list[dict[str, Any]]:
    targets: list[dict[str, Any]] = []
    for key in ("length", "breadth", "height", "surface_area", "volume"):
        value = overall_envelope.get(key)
        if isinstance(value, dict) and any(item not in (None, "", [], {}) for item in value.values()):
            targets.append({"target_id": f"overall_envelope.{key}", "record_type": "overall_envelope", "data": value})
    return targets


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


def _parse_enrichment_response_with_repair(
    *,
    model: str,
    response_text: str,
) -> tuple[LLMEnrichmentResponse, str, list[str]]:
    try:
        return _parse_enrichment_data(response_text), response_text, []
    except (json.JSONDecodeError, ValueError, ValidationError) as exc:
        repaired_text = _call_bedrock_json_repair(
            model=model,
            invalid_json=response_text,
            error=str(exc),
        )
        return (
            _parse_enrichment_data(repaired_text),
            f"{response_text}\n\n--- JSON REPAIR RESPONSE ---\n{repaired_text}",
            ["Initial Claude enrichment JSON was invalid and was repaired automatically."],
        )


def _parse_enrichment_data(text: str) -> LLMEnrichmentResponse:
    return LLMEnrichmentResponse.model_validate(_extract_json_object(text))


def _call_bedrock_json_repair(*, model: str, invalid_json: str, error: str) -> str:
    region = os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION")
    if not region:
        raise RuntimeError("AWS_REGION or AWS_DEFAULT_REGION is required for Bedrock JSON repair.")

    prompt = (
        "Repair the following JSON response so it is valid compact JSON only.\n"
        "Preserve the same facts and field names. Do not add new facts. Do not explain the repair. "
        "Do not include markdown fences.\n\n"
        "The JSON must match this top-level shape:\n"
        '{"updates":[],"review_items":[],"warnings":[]}\n\n'
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


def _merge_enrichment(
    final_data: LLMFinalEngineeringData,
    enrichment: LLMEnrichmentResponse,
) -> list[str]:
    warnings: list[str] = []
    targets = _target_registry(final_data)
    for update in enrichment.updates:
        target_id = update.target_id.strip()
        target = targets.get(target_id)
        if target is None:
            warning = f"Ignored LLM enrichment update for unknown target_id: {target_id}"
            warnings.append(warning)
            final_data.review_items.append(
                LLMReviewItem(
                    item_type="llm_enrichment",
                    value=target_id,
                    confidence="review",
                    reason="Claude returned an enrichment update for a target_id that does not exist.",
                    warnings=[warning],
                )
            )
            continue
        _apply_semantic_update(target_id, target, update, final_data)

    for review_item in enrichment.review_items:
        if not _is_high_value_review_item(review_item):
            target = targets.get(str(review_item.value or ""))
            if target is not None:
                _add_warning_to_target(target, review_item.reason, review_item.warnings)
            continue
        review_item.confidence = "review"
        review_item.reason = _clip_text(review_item.reason, 300)
        review_item.warnings = [_clip_text(warning, 300) for warning in review_item.warnings]
        final_data.review_items.append(review_item)

    for warning in enrichment.warnings:
        final_data.warnings.append(_clip_text(warning, 300))

    return warnings


def _is_high_value_review_item(review_item: LLMReviewItem) -> bool:
    text = _match_text(
        " ".join(
            [
                review_item.item_type,
                str(review_item.value or ""),
                review_item.reason,
                " ".join(review_item.warnings),
            ]
        )
    )
    high_value_terms = [
        "gdt",
        "gd&t",
        "feature control",
        "font artifact",
        "unknown target",
        "does not exist",
        "unsupported",
        "conflict",
        "overwrite",
        "overlay",
        "stamp",
        "distributor",
        "obscure",
        "not part of the original",
    ]
    if any(term in text for term in high_value_terms):
        return True
    if _match_text(review_item.item_type) not in {"llm_enrichment", "dimension_role", "part_name_confidence"}:
        return True
    return False


def _add_warning_to_target(target: Any, reason: str, warnings: list[str]) -> None:
    merged_warnings = [_clip_text(item, 300) for item in [reason, *warnings] if str(item or "").strip()]
    if not merged_warnings:
        return
    if isinstance(target, dict):
        target["warnings"] = _merge_warnings(target.get("warnings", []), merged_warnings)
    elif hasattr(target, "warnings"):
        target.warnings = _merge_warnings(target.warnings, merged_warnings)


def _target_registry(final_data: LLMFinalEngineeringData) -> dict[str, Any]:
    targets: dict[str, Any] = {}
    for key, value in final_data.title_block.items():
        targets[f"title_block.{key}"] = value
    targets.update({f"dimensions.{index}": item for index, item in enumerate(final_data.dimensions)})
    targets.update({f"threads.{index}": item for index, item in enumerate(final_data.threads)})
    targets.update({f"bom_items.{index}": item for index, item in enumerate(final_data.bom_items)})
    targets.update({f"tables.{index}": item for index, item in enumerate(final_data.tables)})
    targets.update({f"standards.{index}": item for index, item in enumerate(final_data.standards)})
    targets.update(
        {
            f"engineering_requirements.{index}": item
            for index, item in enumerate(final_data.engineering_requirements)
        }
    )
    targets.update(
        {
            f"manufacturing_requirements.{index}": item
            for index, item in enumerate(final_data.manufacturing_requirements)
        }
    )
    targets.update({f"notes.{index}": item for index, item in enumerate(final_data.notes)})
    targets.update({f"connections.{index}": item for index, item in enumerate(final_data.connections)})
    targets.update({f"drawing_regions.{index}": item for index, item in enumerate(final_data.drawing_regions)})
    for key in ("length", "breadth", "height", "surface_area", "volume"):
        value = final_data.overall_envelope.get(key)
        if isinstance(value, dict):
            targets[f"overall_envelope.{key}"] = value
    return targets


def _apply_semantic_update(
    target_id: str,
    target: Any,
    update: Any,
    final_data: LLMFinalEngineeringData,
) -> None:
    if isinstance(target, dict):
        _apply_dict_semantic_update(target, update)
    else:
        _apply_model_semantic_update(target, update)

    if update.review_reason:
        final_data.review_items.append(
            LLMReviewItem(
                item_type="llm_enrichment",
                value=target_id,
                confidence="review",
                evidence=str(getattr(target, "evidence", "") if not isinstance(target, dict) else target.get("evidence", "")),
                page=getattr(target, "page", None) if not isinstance(target, dict) else target.get("page"),
                reason=_clip_text(update.review_reason, 300),
                warnings=[_clip_text(warning, 300) for warning in update.warnings],
            )
        )


def _apply_dict_semantic_update(target: dict[str, Any], update: Any) -> None:
    if update.label:
        target["label"] = _clip_text(update.label, 80)
    if update.description:
        target["description"] = _clip_text(update.description, 300)
    if update.view_label:
        target["view_label"] = _clip_text(update.view_label, 80)
    if update.semantic_label:
        target["semantic_label"] = _clip_text(update.semantic_label, 160)
    if update.display_value is not None:
        target["display_value"] = update.display_value
    if update.warnings:
        target["warnings"] = _merge_warnings(
            target.get("warnings", []),
            [_clip_text(warning, 300) for warning in update.warnings],
        )


def _apply_model_semantic_update(target: Any, update: Any) -> None:
    if update.label and hasattr(target, "label"):
        target.label = _clip_text(update.label, 80)
    if update.description and hasattr(target, "description"):
        target.description = _clip_text(update.description, 300)
    if update.view_label and hasattr(target, "view_label"):
        target.view_label = _clip_text(update.view_label, 80)
    if update.semantic_label and hasattr(target, "semantic_label"):
        target.semantic_label = _clip_text(update.semantic_label, 160)
    if update.display_value is not None and hasattr(target, "display_value"):
        target.display_value = update.display_value
    if update.warnings and hasattr(target, "warnings"):
        target.warnings = _merge_warnings(
            target.warnings,
            [_clip_text(warning, 300) for warning in update.warnings],
        )


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
    _require_evidence(final_data.bom_items, "bom_item", final_data)
    _require_evidence(final_data.tables, "table", final_data)
    _require_evidence(final_data.standards, "standard", final_data)
    _require_evidence(final_data.engineering_requirements, "engineering_requirement", final_data)
    _require_evidence(final_data.manufacturing_requirements, "manufacturing_requirement", final_data)
    _require_evidence(final_data.notes, "note", final_data)
    _require_evidence(final_data.connections, "connection", final_data)
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


def _clip_text(value: Any, limit: int) -> str:
    return _limit_text(str(value or ""), limit)


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
