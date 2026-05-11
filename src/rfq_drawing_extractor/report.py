from __future__ import annotations

import json

from .models import ExtractionRunResult, StructuredEngineeringData


def build_markdown_report(result: ExtractionRunResult) -> str:
    data = result.structured_data
    lines = [
        "# PDF Extraction Report",
        "",
        "## Run",
        "",
        f"- File: `{result.metadata.file_name}`",
        f"- Output directory: `{result.metadata.output_dir}`",
        f"- PDF type: `{result.page_detection.pdf_type}`",
        f"- Page count: {result.page_detection.page_count}",
        "",
        "## Page Detection",
        "",
        "| Page | Type | Method | Text chars | Words | Image coverage | OCR | Warnings |",
        "|---:|---|---|---:|---:|---:|---|---|",
    ]

    for page in result.page_detection.pages:
        warnings = "<br>".join(page.warnings) if page.warnings else ""
        lines.append(
            "| "
            f"{page.page_number} | {page.page_type} | {page.extraction_method} | "
            f"{page.text_strength.character_count} | {page.text_strength.word_count} | "
            f"{page.image_strength.largest_image_coverage:.2f} | "
            f"{'yes' if page.ocr_used else 'no'} | {warnings} |"
        )

    lines.extend(["", "## Structured Fields", ""])
    lines.extend(_title_block_section(data))
    lines.extend(_field_section("Drawing Type", [data.drawing_type] if data.drawing_type else []))
    lines.extend(_field_section("Units", [data.units] if data.units else []))
    lines.extend(_components_section(data))
    lines.extend(_engineering_tables_section(data))
    lines.extend(_engineering_requirements_section(data))
    lines.extend(_thread_requirements_section(data))
    lines.extend(_dimensions_section(data))
    lines.extend(_review_dimensions_section(data))
    lines.extend(_overall_envelope_section(data))
    lines.extend(_connections_section(data))
    lines.extend(_field_section("Tolerances / GD&T Candidates", data.tolerances_gdnt))
    lines.extend(_field_section("Process Signals", data.process_requirements))
    lines.extend(_field_section("Manufacturing Requirements", data.manufacturing_requirements))
    lines.extend(_field_section("Notes", data.notes[:20]))
    lines.extend(_drawing_regions_section(data))
    lines.extend(_structure_section(data))

    lines.extend(["", "## Semantic Summary", "", data.semantic_summary or "No summary generated.", ""])
    lines.extend(["## Warnings", ""])
    if data.warnings:
        lines.extend(f"- {warning}" for warning in data.warnings)
    else:
        lines.append("- None")
    lines.append("")
    return "\n".join(lines)


def _title_block_section(data: StructuredEngineeringData) -> list[str]:
    lines = ["### Title Block", ""]
    if not data.title_block:
        return lines + ["No title block fields parsed.", ""]
    lines.extend(["| Field | Value | Confidence | Evidence |", "|---|---|---|---|"])
    for key, field in data.title_block.items():
        lines.append(f"| {key} | {field.value} | {field.confidence} | {_escape(field.evidence)} |")
    lines.append("")
    return lines


def _field_section(title: str, fields: list[object]) -> list[str]:
    lines = [f"### {title}", ""]
    if not fields:
        return lines + ["None parsed.", ""]
    lines.extend(["| Value | Page | Confidence | Evidence |", "|---|---:|---|---|"])
    for field in fields:
        lines.append(
            f"| {getattr(field, 'value', '')} | {getattr(field, 'page', '') or ''} | "
            f"{getattr(field, 'confidence', '')} | {_escape(getattr(field, 'evidence', ''))} |"
        )
    lines.append("")
    return lines


def _components_section(data: StructuredEngineeringData) -> list[str]:
    lines = ["### BOM / Components", ""]
    if not data.bom_components:
        return lines + ["No component rows parsed.", ""]
    lines.extend(["| Item | Component | Category | Note | Confidence | Evidence |", "|---:|---|---|---|---|---|"])
    for item in data.bom_components[:80]:
        lines.append(
            f"| {item.item_no} | {item.component_name} | {item.category} | {_escape(item.note)} | "
            f"{item.confidence} | {_escape(item.evidence)} |"
        )
    lines.append("")
    return lines


def _engineering_tables_section(data: StructuredEngineeringData) -> list[str]:
    lines = ["### Engineering Tables", ""]
    if not data.engineering_tables:
        return lines + ["No non-BOM engineering tables parsed.", ""]
    for table in data.engineering_tables[:20]:
        table_title = table.table_id or table.table_type
        lines.extend([f"#### {table_title}", ""])
        lines.append(
            f"- Type: `{table.table_type}` | Page: {table.page or ''} | "
            f"Index: {table.table_index if table.table_index is not None else ''} | Confidence: `{table.confidence}`"
        )
        if table.warnings:
            lines.extend(f"- Warning: {warning}" for warning in table.warnings)
        lines.append("")
        if not table.rows:
            lines.extend(["No rows parsed.", ""])
            continue
        headers = table.headers or list(table.rows[0].keys())
        lines.append("| " + " | ".join(headers) + " |")
        lines.append("|" + "|".join("---" for _ in headers) + "|")
        for row in table.rows[:80]:
            lines.append("| " + " | ".join(_escape(row.get(header, "")) for header in headers) + " |")
        lines.append("")
    return lines


def _engineering_requirements_section(data: StructuredEngineeringData) -> list[str]:
    lines = ["### Engineering Requirements", ""]
    if not data.engineering_requirements:
        return lines + ["No generic engineering requirements parsed.", ""]
    lines.extend(
        [
            "| Type | Value | Page | Region | Confidence | Parsed Fields | Evidence | Warnings |",
            "|---|---|---:|---|---|---|---|---|",
        ]
    )
    for item in data.engineering_requirements[:120]:
        parsed_fields = _escape(json.dumps(item.parsed_fields, ensure_ascii=False, sort_keys=True))
        warnings = "<br>".join(_escape(warning) for warning in item.warnings)
        lines.append(
            f"| {item.requirement_type} | {_escape(item.value)} | {item.page or ''} | "
            f"{item.region_id} | {item.confidence} | {parsed_fields} | {_escape(item.evidence)} | {warnings} |"
        )
    lines.append("")
    return lines


def _thread_requirements_section(data: StructuredEngineeringData) -> list[str]:
    lines = ["### Thread Requirements", ""]
    if not data.thread_requirements:
        return lines + ["No thread requirements parsed.", ""]
    lines.extend(
        [
            "| Thread Size | Pitch | TPI | Class | Min Full Threads | Label | Chart Ref | Source Table | Relief Note | Region | Confidence | Evidence |",
            "|---|---:|---:|---|---:|---|---|---|---|---|---|---|",
        ]
    )
    for item in data.thread_requirements[:80]:
        pitch = "" if item.pitch is None else str(item.pitch)
        tpi = "" if item.threads_per_inch is None else str(item.threads_per_inch)
        min_threads = "" if item.minimum_full_threads is None else str(item.minimum_full_threads)
        lines.append(
            f"| {item.thread_size} | {pitch} | {tpi} | {item.thread_class} | {min_threads} | "
            f"{_escape(item.label)} | {_escape(item.chart_reference)} | {_escape(item.source_table)} | "
            f"{_escape(item.relief_note)} | {item.region_id} | "
            f"{item.confidence} | {_escape(item.evidence)} |"
        )
    lines.append("")
    return lines


def _dimensions_section(data: StructuredEngineeringData) -> list[str]:
    lines = ["### Dimensions", ""]
    if not data.dimensions:
        return lines + ["No dimensions parsed.", ""]
    lines.extend(
        [
            "| Value | Unit | Secondary | Imperial | Type | Qty | Angle | Role | Region | Source | Confidence | Evidence |",
            "|---:|---|---:|---:|---|---:|---:|---|---|---|---|---|",
        ]
    )
    for item in data.dimensions[:100]:
        secondary = "" if item.secondary_value is None else str(item.secondary_value)
        imperial = "" if item.imperial_value is None else str(item.imperial_value)
        quantity = "" if item.quantity is None else str(item.quantity)
        angle = "" if item.angle_value is None else f"{item.angle_value} {item.angle_unit}"
        evidence = item.raw_callout or item.evidence
        lines.append(
            f"| {item.value} | {item.unit} | {secondary} | {imperial} | {item.dimension_type} | "
            f"{quantity} | {angle} | {item.role} | {item.region_id} | {item.source} | "
            f"{item.confidence} | {_escape(evidence)} |"
        )
    lines.append("")
    return lines


def _review_dimensions_section(data: StructuredEngineeringData) -> list[str]:
    lines = ["### Review Dimension Candidates", ""]
    if not data.review_dimensions:
        return lines + ["No review-only dimension candidates.", ""]
    lines.extend(
        [
            "| Value | Unit | Type | Role | Source | Confidence | Evidence | Warnings |",
            "|---:|---|---|---|---|---|---|---|",
        ]
    )
    for item in data.review_dimensions[:100]:
        warnings = "<br>".join(_escape(warning) for warning in item.warnings)
        evidence = item.raw_callout or item.evidence
        lines.append(
            f"| {item.value} | {item.unit} | {item.dimension_type} | {item.role} | "
            f"{item.source} | {item.confidence} | {_escape(evidence)} | {warnings} |"
        )
    lines.append("")
    return lines


def _overall_envelope_section(data: StructuredEngineeringData) -> list[str]:
    lines = ["### Overall Envelope / Bounding Box", ""]
    envelope = data.overall_envelope
    axes = [
        ("length", envelope.length),
        ("breadth", envelope.breadth),
        ("height", envelope.height),
    ]
    if not any(axis and axis.value is not None for _, axis in axes):
        return lines + ["No overall L/B/H envelope candidates parsed.", ""]

    lines.extend(["| Axis | Value | Unit | Imperial | Source | Confidence | Evidence | Warnings |", "|---|---:|---|---:|---|---|---|---|"])
    for name, axis in axes:
        if axis is None:
            lines.append(f"| {name} |  |  |  |  |  |  | missing |")
            continue
        value = "" if axis.value is None else str(axis.value)
        imperial = "" if axis.imperial_value is None else str(axis.imperial_value)
        warnings = "<br>".join(axis.warnings)
        lines.append(
            f"| {name} | {value} | {axis.unit} | {imperial} | {axis.source} | "
            f"{axis.confidence} | {_escape(axis.evidence)} | {_escape(warnings)} |"
        )

    lines.append("")
    lines.extend(["| Calculation | Value | Unit | Imperial | Formula | Confidence | Warnings |", "|---|---:|---|---:|---|---|---|"])
    for name, calc in (("surface_area", envelope.surface_area), ("volume", envelope.volume)):
        if calc is None or calc.value is None:
            lines.append(f"| {name} |  |  |  |  |  | not calculated |")
            continue
        imperial = "" if calc.imperial_value is None else f"{calc.imperial_value} {calc.imperial_unit}"
        warnings = "<br>".join(calc.warnings)
        lines.append(
            f"| {name} | {calc.value} | {calc.unit} | {imperial} | "
            f"{calc.formula} | {calc.confidence} | {_escape(warnings)} |"
        )

    if envelope.warnings:
        lines.extend(["", "Envelope warnings:"])
        lines.extend(f"- {_escape(warning)}" for warning in envelope.warnings)
    lines.append("")
    return lines


def _connections_section(data: StructuredEngineeringData) -> list[str]:
    lines = ["### Connections / Ports / Valves", ""]
    if not data.connections:
        return lines + ["No connection candidates parsed.", ""]
    lines.extend(["| Label | Size | Type | Option | Confidence | Evidence |", "|---|---|---|---|---|---|"])
    for item in data.connections[:100]:
        lines.append(
            f"| {_escape(item.label)} | {item.size} | {item.connection_type} | "
            f"{'yes' if item.option else 'no'} | {item.confidence} | {_escape(item.evidence)} |"
        )
    lines.append("")
    return lines


def _drawing_regions_section(data: StructuredEngineeringData) -> list[str]:
    lines = ["### Drawing Regions", ""]
    if not data.drawing_regions:
        return lines + ["No drawing regions inferred.", ""]
    lines.extend(["| Region | Page | Type | Label | Confidence | Evidence |", "|---|---:|---|---|---|---|"])
    for region in data.drawing_regions[:80]:
        lines.append(
            f"| {region.region_id} | {region.page} | {region.region_type} | "
            f"{_escape(region.label)} | {region.confidence} | {_escape(region.evidence)} |"
        )
    lines.append("")
    return lines


def _structure_section(data: StructuredEngineeringData) -> list[str]:
    lines = ["### Drawing Structure", ""]
    if not data.drawing_structure:
        return lines + ["No structure signals parsed.", ""]
    for key, value in data.drawing_structure.items():
        lines.append(f"- `{key}`: {value}")
    lines.append("")
    return lines


def _escape(value: str) -> str:
    return str(value).replace("|", "\\|").replace("\n", "<br>")
