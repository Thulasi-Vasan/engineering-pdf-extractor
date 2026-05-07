from __future__ import annotations

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
    lines.extend(_dimensions_section(data))
    lines.extend(_overall_envelope_section(data))
    lines.extend(_connections_section(data))
    lines.extend(_field_section("Tolerances / GD&T Candidates", data.tolerances_gdnt))
    lines.extend(_field_section("Process Signals", data.process_requirements))
    lines.extend(_field_section("Notes", data.notes[:20]))
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


def _dimensions_section(data: StructuredEngineeringData) -> list[str]:
    lines = ["### Dimensions", ""]
    if not data.dimensions:
        return lines + ["No dimensions parsed.", ""]
    lines.extend(
        [
            "| Value | Unit | Imperial | Type | Role | Source | Confidence | Evidence |",
            "|---:|---|---:|---|---|---|---|---|",
        ]
    )
    for item in data.dimensions[:100]:
        imperial = "" if item.imperial_value is None else str(item.imperial_value)
        lines.append(
            f"| {item.value} | {item.unit} | {imperial} | {item.dimension_type} | "
            f"{item.role} | {item.source} | {item.confidence} | {_escape(item.evidence)} |"
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
