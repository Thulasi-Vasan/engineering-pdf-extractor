from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from .models import (
    DimensionCandidate,
    EnvelopeAxisMeasurement,
    EnvelopeCalculation,
    OverallEnvelope,
    RawExtractionResult,
    StructuredEngineeringData,
)


DEFAULT_BEDROCK_VISION_MODEL = "anthropic.claude-3-5-sonnet-20241022-v2:0"


def augment_dimensions_with_vision_llm(
    pdf_path: Path,
    raw: RawExtractionResult,
    data: StructuredEngineeringData,
    *,
    model: str | None = None,
) -> None:
    load_dotenv()

    try:
        page_images = _render_pages_to_png(pdf_path, [page.page_number for page in raw.pages])
    except Exception as exc:
        data.warnings.append(f"Vision LLM dimension extraction could not render PDF pages: {exc}")
        return

    for page in raw.pages:
        image_bytes = page_images.get(page.page_number)
        if not image_bytes:
            continue
        try:
            response = _call_bedrock_vision_dimensions(
                model=model or os.getenv("BEDROCK_VISION_MODEL") or DEFAULT_BEDROCK_VISION_MODEL,
                page_number=page.page_number,
                image_bytes=image_bytes,
            )
            dimensions = _dimensions_from_response(response, page.page_number)
            _merge_dimensions(data, dimensions)
        except Exception as exc:
            data.warnings.append(
                f"Bedrock vision dimension extraction failed on page {page.page_number}: {exc}"
            )

        try:
            envelope_response = _call_bedrock_vision_envelope(
                model=model or os.getenv("BEDROCK_VISION_MODEL") or DEFAULT_BEDROCK_VISION_MODEL,
                page_number=page.page_number,
                image_bytes=image_bytes,
            )
            envelope = _overall_envelope_from_response(envelope_response, page.page_number)
            _validate_envelope_against_page_text(envelope, page.text)
            _merge_overall_envelope(data, envelope)
        except Exception as exc:
            data.warnings.append(
                f"Bedrock vision envelope extraction failed on page {page.page_number}: {exc}"
            )


def _render_pages_to_png(pdf_path: Path, page_numbers: list[int]) -> dict[int, bytes]:
    try:
        import fitz
    except ImportError as exc:
        raise RuntimeError("pymupdf is required for vision LLM page rendering.") from exc

    rendered: dict[int, bytes] = {}
    document = fitz.open(str(pdf_path))
    try:
        matrix = fitz.Matrix(2.5, 2.5)
        for page_number in page_numbers:
            page = document.load_page(page_number - 1)
            pixmap = page.get_pixmap(matrix=matrix, alpha=False)
            rendered[page_number] = pixmap.tobytes("png")
    finally:
        document.close()
    return rendered


def _call_bedrock_vision_dimensions(
    *,
    model: str,
    page_number: int,
    image_bytes: bytes,
) -> dict[str, Any]:
    region = os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION")
    if not region:
        raise RuntimeError("AWS_REGION or AWS_DEFAULT_REGION is required for Bedrock vision extraction.")

    try:
        import boto3
    except ImportError as exc:
        raise RuntimeError("boto3 is required for Bedrock vision extraction.") from exc

    prompt = _dimension_prompt(page_number, include_schema=True)
    client = boto3.client("bedrock-runtime", region_name=region)
    response = client.converse(
        modelId=model,
        system=[{"text": _system_prompt()}],
        messages=[
            {
                "role": "user",
                "content": [
                    {"text": prompt},
                    {"image": {"format": "png", "source": {"bytes": image_bytes}}},
                ],
            }
        ],
        inferenceConfig={"maxTokens": 5000, "temperature": 0},
    )
    return {"output_text": _bedrock_output_text(response)}


def _call_bedrock_vision_envelope(
    *,
    model: str,
    page_number: int,
    image_bytes: bytes,
) -> dict[str, Any]:
    region = os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION")
    if not region:
        raise RuntimeError("AWS_REGION or AWS_DEFAULT_REGION is required for Bedrock vision extraction.")

    try:
        import boto3
    except ImportError as exc:
        raise RuntimeError("boto3 is required for Bedrock vision extraction.") from exc

    client = boto3.client("bedrock-runtime", region_name=region)
    response = client.converse(
        modelId=model,
        system=[{"text": _envelope_system_prompt()}],
        messages=[
            {
                "role": "user",
                "content": [
                    {"text": _envelope_prompt(page_number, include_schema=True)},
                    {"image": {"format": "png", "source": {"bytes": image_bytes}}},
                ],
            }
        ],
        inferenceConfig={"maxTokens": 2400, "temperature": 0},
    )
    return {"output_text": _bedrock_output_text(response)}


def _system_prompt() -> str:
    return (
        "You extract visible engineering drawing dimensions from rendered PDF page images. "
        "Return only dimensions that are visually present. Do not infer hidden dimensions. "
        "Keep exact values as shown. If both metric and imperial are shown, put metric in value/unit "
        "and imperial in imperial_value as text. Use an empty string when no imperial pair is shown. "
        "Use evidence and visual_location to explain where the dimension appears."
    )


def _envelope_system_prompt() -> str:
    return (
        "You inspect rendered engineering drawing pages and identify only the overall rectangular "
        "envelope dimensions of the product/equipment. Be conservative. A valid envelope axis must "
        "be visibly supported by an outside/full-span dimension line or an explicit overall dimension "
        "group spanning the complete equipment view. Do not use BOM item numbers, callout balloons, "
        "part labels, local feature dimensions, phone numbers, title block values, flange-only spans, "
        "or dimensions that cover only a subassembly. If an axis is not clear, leave its value empty "
        "and explain the uncertainty. Prefer low confidence over a wrong L/B/H assignment."
    )


def _dimension_prompt(page_number: int, *, include_schema: bool) -> str:
    prompt = (
        f"Extract all visible dimension annotations from page {page_number}. "
        "Include linear dimensions, diameter/radius dimensions, angles, and metric/imperial pairs. "
        "Ignore BOM item numbers, callout balloons, title block fields, part numbers, phone numbers, "
        "and component item numbers. Return only valid compact JSON. "
        "Do not include markdown. If a value is hard to read, include it with low confidence and a warning. "
        "Return at most 60 dimension entries."
    )
    if include_schema:
        prompt += (
            "\n\nReturn JSON with this shape. The example is intentionally empty; do not copy values from it:\n"
            "{\n"
            '  "dimensions": [\n'
            "    {\n"
            '      "value": "",\n'
            '      "unit": "",\n'
            '      "imperial_value": "",\n'
            '      "dimension_type": "",\n'
            '      "role": "",\n'
            '      "visual_location": "",\n'
            '      "evidence": "",\n'
            '      "confidence": "",\n'
            '      "warning": ""\n'
            "    }\n"
            "  ]\n"
            "}\n\n"
            'Allowed unit values: "mm", "inch", "degree", "unknown". '
            'Allowed confidence values: "high", "medium", "low".'
        )
    return prompt


def _envelope_prompt(page_number: int, *, include_schema: bool) -> str:
    prompt = (
        f"From page {page_number}, identify the overall equipment envelope only. "
        "Return length, breadth, and height candidates only when each axis is visibly supported "
        "by a full-span outside dimension line or an explicit overall dimension group. Breadth "
        "means depth/width perpendicular to length when the drawing makes that visible. Do not "
        "return every dimension; this task is only for the bounding box/envelope. Do not use local "
        "feature dimensions, partial spans, BOM item numbers, callout balloons, title block fields, "
        "part numbers, phone numbers, or schema example values. For each axis, include one alternate "
        "candidate if visible and explain why it was not selected. If the drawing does not explicitly "
        "show a safe L/B/H axis, return an empty value for that axis with low confidence and a warning. "
        "Return only compact JSON."
    )
    if include_schema:
        prompt += (
            "\n\nReturn JSON with this shape. The example is intentionally empty; do not copy values from it:\n"
            "{\n"
            '  "overall_envelope": {\n'
            '    "length": {"value": "", "unit": "", "imperial_value": "", "confidence": "", "evidence": "", "visual_location": "", "warning": "", "alternate": ""},\n'
            '    "breadth": {"value": "", "unit": "", "imperial_value": "", "confidence": "", "evidence": "", "visual_location": "", "warning": "", "alternate": ""},\n'
            '    "height": {"value": "", "unit": "", "imperial_value": "", "confidence": "", "evidence": "", "visual_location": "", "warning": "", "alternate": ""},\n'
            '    "confidence": "",\n'
            '    "evidence": "",\n'
            '    "warning": "",\n'
            '    "rejected_candidates": []\n'
            "  }\n"
            "}\n\n"
            'Allowed unit values: "mm", "inch", "unknown". '
            'Allowed confidence values: "high", "medium", "low". '
            'Use empty strings for unknown value or imperial_value.'
        )
    return prompt


def _bedrock_output_text(response: dict[str, Any]) -> str:
    parts = []
    message = response.get("output", {}).get("message", {})
    for content in message.get("content", []) or []:
        if content.get("text"):
            parts.append(str(content["text"]))
    if not parts:
        raise RuntimeError("Bedrock response did not include text output.")
    return "\n".join(parts)


def _dimension_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "dimensions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "value": {"type": "number"},
                        "unit": {"type": "string", "enum": ["mm", "inch", "degree", "unknown"]},
                        "imperial_value": {"type": "string"},
                        "dimension_type": {"type": "string"},
                        "role": {"type": "string"},
                        "visual_location": {"type": "string"},
                        "evidence": {"type": "string"},
                        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
                        "warning": {"type": "string"},
                    },
                    "required": [
                        "value",
                        "unit",
                        "imperial_value",
                        "dimension_type",
                        "role",
                        "visual_location",
                        "evidence",
                        "confidence",
                        "warning",
                    ],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["dimensions"],
        "additionalProperties": False,
    }


def _envelope_schema() -> dict[str, Any]:
    axis_schema = {
        "type": "object",
        "properties": {
            "value": {"type": "string"},
            "unit": {"type": "string", "enum": ["mm", "inch", "unknown"]},
            "imperial_value": {"type": "string"},
            "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
            "evidence": {"type": "string"},
            "visual_location": {"type": "string"},
            "warning": {"type": "string"},
            "alternate": {"type": "string"},
        },
        "required": [
            "value",
            "unit",
            "imperial_value",
            "confidence",
            "evidence",
            "visual_location",
            "warning",
            "alternate",
        ],
        "additionalProperties": False,
    }
    return {
        "type": "object",
        "properties": {
            "overall_envelope": {
                "type": "object",
                "properties": {
                    "length": axis_schema,
                    "breadth": axis_schema,
                    "height": axis_schema,
                    "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
                    "evidence": {"type": "string"},
                    "warning": {"type": "string"},
                    "rejected_candidates": {"type": "array", "items": {"type": "string"}},
                },
                "required": [
                    "length",
                    "breadth",
                    "height",
                    "confidence",
                    "evidence",
                    "warning",
                    "rejected_candidates",
                ],
                "additionalProperties": False,
            }
        },
        "required": ["overall_envelope"],
        "additionalProperties": False,
    }


def _dimensions_from_response(response: dict[str, Any], page_number: int) -> list[DimensionCandidate]:
    payload = _response_json(response)
    dimensions = []
    for item in payload.get("dimensions", []):
        try:
            value = float(item["value"])
        except (KeyError, TypeError, ValueError):
            continue

        unit = str(item.get("unit") or "unknown").casefold()
        if unit not in {"mm", "inch", "degree", "unknown"}:
            unit = "unknown"

        imperial_value = item.get("imperial_value")
        if imperial_value is not None:
            try:
                imperial_value = float(imperial_value)
            except (TypeError, ValueError):
                imperial_value = None

        confidence = str(item.get("confidence") or "low").casefold()
        if confidence not in {"high", "medium", "low"}:
            confidence = "low"

        evidence_parts = [
            str(item.get("evidence") or "").strip(),
            str(item.get("visual_location") or "").strip(),
        ]
        evidence = " | ".join(part for part in evidence_parts if part)
        warnings = []
        warning = str(item.get("warning") or "").strip()
        if warning:
            warnings.append(warning)
        if confidence == "low":
            warnings.append("Vision LLM-only low confidence dimension candidate.")

        dimensions.append(
            DimensionCandidate(
                value=value,
                unit=unit,  # type: ignore[arg-type]
                imperial_value=imperial_value,
                dimension_type=str(item.get("dimension_type") or "linear"),
                role=str(item.get("role") or "unknown"),
                role_confidence=confidence,  # type: ignore[arg-type]
                source="vision_llm",
                page=page_number,
                confidence=confidence,  # type: ignore[arg-type]
                evidence=evidence,
                warnings=warnings,
            )
        )
    return dimensions


def _overall_envelope_from_response(response: dict[str, Any], page_number: int) -> OverallEnvelope:
    payload = _response_json(response)
    envelope_payload = payload.get("overall_envelope", payload)
    confidence = _confidence(envelope_payload.get("confidence"))
    evidence = str(envelope_payload.get("evidence") or "").strip()
    warning = str(envelope_payload.get("warning") or "").strip()
    warnings = [warning] if warning else []
    for rejected in envelope_payload.get("rejected_candidates", []) or []:
        rejected_text = str(rejected).strip()
        if rejected_text:
            warnings.append(f"Rejected candidate: {rejected_text}")

    envelope = OverallEnvelope(
        length=_axis_from_payload(envelope_payload.get("length"), page_number),
        breadth=_axis_from_payload(envelope_payload.get("breadth"), page_number),
        height=_axis_from_payload(envelope_payload.get("height"), page_number),
        source="vision_llm",
        confidence=confidence,  # type: ignore[arg-type]
        evidence=evidence,
        warnings=warnings,
    )
    _calculate_envelope_geometry(envelope)
    return envelope


def _axis_from_payload(payload: object, page_number: int) -> EnvelopeAxisMeasurement | None:
    if not isinstance(payload, dict):
        return None
    value = _float_or_none(payload.get("value"))
    unit = str(payload.get("unit") or "unknown").casefold()
    if unit not in {"mm", "inch", "unknown"}:
        unit = "unknown"
    imperial_value = _float_or_none(payload.get("imperial_value"))
    confidence = _confidence(payload.get("confidence"))
    evidence_parts = [
        str(payload.get("evidence") or "").strip(),
        str(payload.get("visual_location") or "").strip(),
    ]
    evidence = " | ".join(part for part in evidence_parts if part)
    warning = str(payload.get("warning") or "").strip()
    warnings = [warning] if warning else []
    alternate = str(payload.get("alternate") or "").strip()
    if alternate:
        warnings.append(f"Alternate candidate: {alternate}")
    if value is None:
        warnings.append("Envelope axis was not confidently visible in the drawing.")
    return EnvelopeAxisMeasurement(
        value=value,
        unit=unit,  # type: ignore[arg-type]
        imperial_value=imperial_value,
        source="vision_llm",
        page=page_number,
        confidence=confidence,  # type: ignore[arg-type]
        evidence=evidence,
        warnings=warnings,
    )



def _validate_envelope_against_page_text(envelope: OverallEnvelope, page_text: str) -> None:
    """Reject vision envelope axes that are not grounded in the current PDF text layer."""
    normalized_text = _normalize_numeric_text(page_text)
    text_has_content = len(normalized_text) >= 50
    inch_only = "all dimensions are in inches" in normalized_text and " mm" not in normalized_text

    for axis_name in ("length", "breadth", "height"):
        axis = getattr(envelope, axis_name)
        if axis is None or axis.value is None:
            continue

        value_visible = _number_visible_in_text(axis.value, normalized_text)
        imperial_visible = axis.imperial_value is None or _number_visible_in_text(axis.imperial_value, normalized_text)
        unit_suspicious = inch_only and axis.unit == "mm"

        if text_has_content and (not value_visible or not imperial_visible or unit_suspicious):
            reasons = []
            if not value_visible:
                reasons.append(f"{axis.value:g} is not visible in the current PDF text")
            if not imperial_visible and axis.imperial_value is not None:
                reasons.append(f"imperial value {axis.imperial_value:g} is not visible in the current PDF text")
            if unit_suspicious:
                reasons.append("PDF states all dimensions are in inches, but axis was returned in mm")
            axis.warnings.append("Rejected vision envelope axis: " + "; ".join(reasons) + ".")
            axis.value = None
            axis.unit = "unknown"
            axis.imperial_value = None
            axis.confidence = "low"

    if any(axis and axis.value is None for axis in (envelope.length, envelope.breadth, envelope.height)):
        _calculate_envelope_geometry(envelope)


def _normalize_numeric_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.casefold().replace("`", "±"))


def _number_visible_in_text(value: float, normalized_text: str) -> bool:
    candidates = {
        f"{value:g}",
        f"{value:.1f}".rstrip("0").rstrip("."),
        f"{value:.2f}".rstrip("0").rstrip("."),
        f"{value:.3f}".rstrip("0").rstrip("."),
        f"{value:.3f}",
    }
    for candidate in candidates:
        if not candidate:
            continue
        pattern = rf"(?<![0-9.]){re.escape(candidate)}(?![0-9.])"
        if re.search(pattern, normalized_text):
            return True
    return False

def _calculate_envelope_geometry(envelope: OverallEnvelope) -> None:
    envelope.surface_area = None
    envelope.volume = None
    estimate_warning = (
        "Computed as a rectangular bounding-box estimate from 2D drawing envelope candidates; "
        "not true CAD/STEP surface area or material volume."
    )
    envelope.warnings = [warning for warning in envelope.warnings if warning != estimate_warning]
    length_mm = _axis_to_mm(envelope.length)
    breadth_mm = _axis_to_mm(envelope.breadth)
    height_mm = _axis_to_mm(envelope.height)
    length_in = _axis_to_inch(envelope.length)
    breadth_in = _axis_to_inch(envelope.breadth)
    height_in = _axis_to_inch(envelope.height)

    if length_mm is None or breadth_mm is None or height_mm is None:
        envelope.warnings.append("Surface area and volume were not calculated because L/B/H are incomplete.")
        return

    surface_mm2 = 2 * ((length_mm * breadth_mm) + (length_mm * height_mm) + (breadth_mm * height_mm))
    volume_mm3 = length_mm * breadth_mm * height_mm
    surface_in2 = None
    volume_in3 = None
    if length_in is not None and breadth_in is not None and height_in is not None:
        surface_in2 = 2 * ((length_in * breadth_in) + (length_in * height_in) + (breadth_in * height_in))
        volume_in3 = length_in * breadth_in * height_in

    confidence = _combined_axis_confidence(envelope)
    evidence = "L x B x H envelope dimensions from vision LLM."
    envelope.surface_area = EnvelopeCalculation(
        value=round(surface_mm2, 3),
        unit="mm^2",
        imperial_value=round(surface_in2, 3) if surface_in2 is not None else None,
        imperial_unit="in^2",
        formula="2 * (L*B + L*H + B*H)",
        source="inferred",
        confidence=confidence,  # type: ignore[arg-type]
        evidence=evidence,
        warnings=[estimate_warning],
    )
    envelope.volume = EnvelopeCalculation(
        value=round(volume_mm3, 3),
        unit="mm^3",
        imperial_value=round(volume_in3, 3) if volume_in3 is not None else None,
        imperial_unit="in^3",
        formula="L * B * H",
        source="inferred",
        confidence=confidence,  # type: ignore[arg-type]
        evidence=evidence,
        warnings=[estimate_warning],
    )
    if estimate_warning not in envelope.warnings:
        envelope.warnings.append(estimate_warning)


def _response_json(response: dict[str, Any]) -> dict[str, Any]:
    text = response.get("output_text")
    if not text:
        parts = []
        for output in response.get("output", []) or []:
            for content in output.get("content", []) or []:
                if content.get("type") == "output_text" and content.get("text"):
                    parts.append(str(content["text"]))
        text = "\n".join(parts)
    if not text:
        raise RuntimeError("Vision model response did not include output text.")
    text = _extract_json_text(text)
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        partial_payload = _partial_dimensions_json(text)
        if partial_payload is not None:
            return partial_payload
        raise RuntimeError(f"Vision model response was not valid JSON: {text[:500]}") from exc


def _extract_json_text(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    if text.startswith("{"):
        return text
    match = re.search(r"\{.*\}", text, re.S)
    if match:
        return match.group(0)
    return text


def _partial_dimensions_json(text: str) -> dict[str, Any] | None:
    start = text.find('"dimensions"')
    if start == -1:
        return None
    array_start = text.find("[", start)
    if array_start == -1:
        return None

    objects: list[dict[str, Any]] = []
    depth = 0
    object_start: int | None = None
    in_string = False
    escaped = False

    for index in range(array_start + 1, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue

        if char == '"':
            in_string = True
            continue
        if char == "{":
            if depth == 0:
                object_start = index
            depth += 1
            continue
        if char == "}":
            depth -= 1
            if depth == 0 and object_start is not None:
                candidate = text[object_start : index + 1]
                try:
                    objects.append(json.loads(candidate))
                except json.JSONDecodeError:
                    pass
                object_start = None

    if not objects:
        return None
    return {"dimensions": objects}


def _merge_overall_envelope(data: StructuredEngineeringData, candidate: OverallEnvelope) -> None:
    current_score = _envelope_score(data.overall_envelope)
    candidate_score = _envelope_score(candidate)
    if candidate_score >= current_score:
        data.overall_envelope = candidate


def _envelope_score(envelope: OverallEnvelope) -> int:
    axes = [envelope.length, envelope.breadth, envelope.height]
    visible_axes = sum(1 for axis in axes if axis and axis.value is not None)
    confidence_score = {"low": 0, "medium": 1, "high": 2}.get(envelope.confidence, 0)
    return visible_axes * 10 + confidence_score


def _merge_dimensions(data: StructuredEngineeringData, candidates: list[DimensionCandidate]) -> None:
    for candidate in candidates:
        existing = _matching_dimension(data.dimensions, candidate)
        if existing is None:
            data.dimensions.append(candidate)
            continue

        existing.source = "mixed"
        existing.confidence = _higher_confidence(existing.confidence, candidate.confidence)  # type: ignore[assignment]
        if existing.role == "unknown" and candidate.role != "unknown":
            existing.role = candidate.role
            existing.role_confidence = candidate.role_confidence
        if existing.imperial_value is None and candidate.imperial_value is not None:
            existing.imperial_value = candidate.imperial_value
        if candidate.evidence and candidate.evidence not in existing.evidence:
            existing.evidence = (existing.evidence + " | Vision: " + candidate.evidence).strip(" |")
        for warning in candidate.warnings:
            if warning not in existing.warnings:
                existing.warnings.append(warning)


def _matching_dimension(existing_dimensions: list[DimensionCandidate], candidate: DimensionCandidate) -> DimensionCandidate | None:
    for existing in existing_dimensions:
        if existing.unit != candidate.unit:
            continue
        if abs(existing.value - candidate.value) > _dimension_tolerance(candidate):
            continue
        if existing.imperial_value is not None and candidate.imperial_value is not None:
            if abs(existing.imperial_value - candidate.imperial_value) > 0.15:
                continue
        return existing
    return None


def _dimension_tolerance(candidate: DimensionCandidate) -> float:
    if candidate.unit == "degree":
        return 0.2
    if abs(candidate.value) >= 100:
        return 0.5
    return 0.15


def _float_or_none(value: object) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    text = text.replace(",", "")
    match = re.search(r"-?\d+(?:\.\d+)?", text)
    if not match:
        return None
    try:
        return float(match.group(0))
    except ValueError:
        return None


def _confidence(value: object) -> str:
    confidence = str(value or "low").casefold()
    if confidence not in {"high", "medium", "low"}:
        return "low"
    return confidence


def _axis_to_mm(axis: EnvelopeAxisMeasurement | None) -> float | None:
    if axis is None or axis.value is None:
        return None
    if axis.unit == "mm":
        return axis.value
    if axis.unit == "inch":
        return axis.value * 25.4
    return None


def _axis_to_inch(axis: EnvelopeAxisMeasurement | None) -> float | None:
    if axis is None or axis.value is None:
        return None
    if axis.imperial_value is not None:
        return axis.imperial_value
    if axis.unit == "inch":
        return axis.value
    if axis.unit == "mm":
        return axis.value / 25.4
    return None


def _combined_axis_confidence(envelope: OverallEnvelope) -> str:
    axes = [envelope.length, envelope.breadth, envelope.height]
    if any(axis is None or axis.value is None or axis.confidence == "low" for axis in axes):
        return "low"
    if any(axis.confidence == "medium" for axis in axes):
        return "medium"
    return "high"


def _higher_confidence(left: str, right: str) -> str:
    order = {"low": 0, "medium": 1, "high": 2}
    return left if order.get(left, 0) >= order.get(right, 0) else right
