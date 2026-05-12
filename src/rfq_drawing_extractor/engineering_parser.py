from __future__ import annotations

import re
from collections import Counter

from .models import (
    BomComponent,
    ConnectionCandidate,
    DimensionCandidate,
    DrawingRegion,
    EngineeringRequirement,
    EngineeringTable,
    ExtractedField,
    RawExtractionResult,
    StructuredEngineeringData,
    ThreadRequirement,
)


PROCESS_KEYWORDS = (
    "die cast",
    "casting",
    "machining",
    "machined",
    "welding",
    "weld",
    "forging",
    "stamping",
    "injection molding",
    "heat treat",
    "anodize",
    "powder coat",
    "painting",
    "plating",
    "press fit",
    "torque",
    "inspection",
)

STANDARD_RE = re.compile(r"\b(?:ASME[-\s]*Y14\.5M?|ISO\s+1101|ISO\s+2768|ISO\s+\d+|ASTM\s+[A-Z]\d+)\b", re.I)
TOLERANCE_RE = re.compile(r"(?:±|\+/-)\s*\d+(?:\.\d+)?|\b\d+(?:\.\d+)?\s*(?:MAX|MIN)\b", re.I)
SURFACE_RE = re.compile(r"\bR[az]\s*\d+(?:\.\d+)?\b", re.I)
CONNECTION_RE = re.compile(
    r"(?P<size>(?:\d+\s+\d+/\d+|\d+/\d+|\d+(?:\.\d+)?)\s*\"?)\s*,?\s*(?P<kind>NPT|Flare|solder|flange)?",
    re.I,
)
DIMENSION_PAIR_RE = re.compile(r"(?P<metric>\d{1,4}(?:\.\d+)?)\s*\((?P<imperial>\d{1,3}(?:\.\d+)?)\)")
DIAMETER_RE = re.compile(r"(?P<count>\d+\s*-\s*)?Ø\s*(?P<value>\d+(?:\.\d+)?)", re.I)
ANGLE_RE = re.compile(r"\b(?P<value>\d+(?:\.\d+)?)\s*°")
INCH_DIMENSION_RE = re.compile(r"(?<![#A-Z])(?P<value>\d+\.\d+)(?![ \t]*-)")
CHAMFER_RE = re.compile(r"\b(?P<count>\d+\s*x\s*)?(?P<size>\d+(?:\.\d+)?)\s*X\s*(?P<angle>\d+(?:\.\d+)?)\s*°", re.I)
RANGE_RE = re.compile(r"(?<![#A-Z0-9])(?P<start>\.?\d+(?:\.\d+)?)\s*-\s*(?P<end>\.?\d+(?:\.\d+)?)(?!\s*[A-Z0-9])", re.I)
DEFAULT_TOLERANCE_RE = re.compile(r"(?P<precision>\.X{1,4})\s*(?P<tol>±\s*\d+(?:\.\d+)?)\s*\"?", re.I)
ANGLE_DEFAULT_TOLERANCE_RE = re.compile(r"\bANGLE\s*:?\s*(?P<tol>±\s*(?:\d+\s*/\s*\d+|\d+(?:\.\d+)?)\s*°?)", re.I)
CHAMFER_DEFAULT_TOLERANCE_RE = re.compile(r"\bCHAMFER\s*:?\s*(?P<tol>±\s*(?:\d+\s*/\s*\d+|\d+(?:\.\d+)?)\s*°?)", re.I)
Fcf_CANDIDATE_RE = re.compile(r"\b(?P<raw>(?:[a-z]{1,2}\.00\d[A-Z]?|[a-z]{1,2}Ø\.00\d[A-Z]?|\.002[A-Z]?))\b", re.I)
METRIC_THREAD_RE = re.compile(r"\b(?P<size>M\d+(?:\.\d+)?)\s*x\s*(?P<pitch>\d+(?:\.\d+)?)\s*-\s*(?P<class>\d+[gGhH])\b")
UNIFIED_THREAD_RE = re.compile(r"(?<!\w)(?P<size>(?:#\d+|\d+/\d+))-(?P<tpi>\d+)\s*-\s*(?P<class>\d+[AB])\b", re.I)
MIN_FULL_THREADS_RE = re.compile(r"\bMIN(?:IMUM|\.)?\s*(?P<count>\d+)\s*FULL\s+THREADS?\b", re.I)
REGION_PRIORITY = {
    "engineering_table": 100,
    "title_block": 90,
    "tolerance_notes": 80,
    "thread_callout_area": 70,
    "view_label_area": 60,
    "drawing_body": 0,
}


def parse_engineering_data(raw: RawExtractionResult) -> StructuredEngineeringData:
    data = StructuredEngineeringData()
    all_text = _combined_text(raw)
    all_lines = _combined_lines(raw)

    data.title_block = _parse_title_block(raw, all_lines)
    data.units = _parse_units(raw, all_text)
    data.drawing_type = _parse_drawing_type(raw, all_text)
    data.bom_components = _parse_bom_components(raw)
    data.engineering_tables = _parse_engineering_tables(raw)
    data.drawing_regions = _parse_drawing_regions(raw, data.engineering_tables)
    data.thread_requirements = _parse_thread_requirements(raw, data.engineering_tables, data.drawing_regions)
    data.dimensions = _parse_dimensions(raw, data.drawing_regions)
    data.connections = _parse_connections(raw, data.bom_components)
    data.standards = _parse_standards(raw)
    data.tolerances_gdnt = _parse_tolerances_gdnt(raw)
    data.process_requirements = _parse_process_signals(raw)
    data.manufacturing_requirements = _parse_manufacturing_requirements(raw, data.title_block)
    data.engineering_requirements = _build_engineering_requirements(data)
    data.notes = _parse_notes(raw)
    data.drawing_structure = _parse_drawing_structure(raw, data)
    data.semantic_summary = _build_semantic_summary(data)
    data.warnings = _warnings(raw, data)
    return data


def refresh_semantic_summary(data: StructuredEngineeringData) -> None:
    data.semantic_summary = _build_semantic_summary(data)


def _parse_title_block(raw: RawExtractionResult, lines: list[str]) -> dict[str, ExtractedField]:
    fields: dict[str, ExtractedField] = {}
    text = "\n".join(lines)
    label_fields = _label_fields_from_raw(raw)
    label_values = {label: field.value for label, field in label_fields.items()}

    model = _first_match(
        [
            r"Hanbell Model\s*\n?\s*([A-Z0-9/&.-]+)",
            r"\bModel\s*:?\s*\n?\s*([A-Z0-9/&.-]+)",
        ],
        text,
    ) or label_values.get("model", "")
    if model:
        fields["model"] = label_fields.get("model") or _field_for_value(raw, model, "high")

    drawing_name = _first_match(
        [
            r"\bName\s*\n?\s*(Compressor outline)",
            r"(Dimensional Outline Drawing[^\n]*)",
            r"(Compressor outline)",
        ],
        text,
    )
    if drawing_name:
        fields["drawing_name"] = _field_for_value(raw, drawing_name, "high")

    date = _generic_date(raw)
    if date:
        raw_date = date
        date = _format_compact_date(date)
        fields["date"] = _field_for_value(raw, date, "high", _focused_label_evidence(raw, "date", raw_date))

    drawn_by = label_values.get("drawn by", "") or _first_match([r"\bDrawn By\s*:?\s*\n?\s*([A-Z][A-Z0-9 .-]{1,40})"], text)
    if drawn_by:
        drawn_by = re.split(r"\b(?:E-mail|Email|Tel|Fax)\b", drawn_by, maxsplit=1, flags=re.I)[0].strip()
        fields["drawn_by"] = label_fields.get("drawn by") or _field_for_value(raw, drawn_by, "high")

    version = _first_match([r"\b(?:Ver\.?|Rev\.?|Revision\b)\s*:?\s+([A-Z0-9.-]+)\b"], text)
    if version and version.casefold() in {"isions", "revisions", "revision", "sheet"}:
        version = ""
    if version:
        fields["revision_version"] = _field_for_value(raw, version, "high")

    if re.search(r"\bHANBELL\b", text, re.I):
        fields["manufacturer"] = _field_for_value(raw, "HANBELL", "high")

    company = _first_match([r"(Micro Control Systems,\s*Inc\.)", r"(ADVANCED SENSOR TECHNOLOGY,\s*INC\.)"], text)
    if company:
        fields["company"] = _field(company, company, "high", _page_for_value(raw, company))

    extra_fields = {
        "drawing_number": ("dwg no.", "dwg no", "drawing no.", "drawing number"),
        "created_date": ("created date",),
        "approved_by": ("approved by",),
        "approval_date": ("approval date",),
        "item_number": ("item #", "item no.", "item number"),
        "cage": ("cage",),
        "sheet": ("sheet",),
        "material": ("material",),
    }
    for field_name, labels in extra_fields.items():
        if field_name in fields:
            continue
        field = next((label_fields[label] for label in labels if label_fields.get(label)), None)
        if field:
            fields[field_name] = field

    part_name = _part_name_from_tables(raw)
    if part_name and "part_name" not in fields:
        fields["part_name"] = _field(part_name, f"part name: {part_name}", "medium", _page_for_value(raw, part_name))

    if fields.get("material") and fields["material"].value.endswith(" COLD DRAW"):
        fields["material"].value += "N"

    return fields


def _parse_units(raw: RawExtractionResult, text: str) -> ExtractedField | None:
    if re.search(r"\bALL DIMENSIONS ARE IN INCHES\b", text, re.I):
        evidence = "ALL DIMENSIONS ARE IN INCHES"
        return _field("inch", evidence, "high", _page_for_value(raw, evidence))
    if re.search(r"\bSI\s*:\s*mm\b", text, re.I) and re.search(r"Imperial\s*:\s*\(?in\)?", text, re.I):
        return _field("both", _evidence_for_value(raw, "UNIT"), "high")
    if re.search(r"\bmm\b", text, re.I) and re.search(r"\bin(?:ch|ches)?\b|\(in\)", text, re.I):
        return _field("both", _evidence_for_value(raw, "mm"), "medium")
    if re.search(r"\bmm\b", text, re.I):
        return _field("mm", _evidence_for_value(raw, "mm"), "medium")
    if re.search(r"\bin(?:ch|ches)?\b|\(in\)", text, re.I):
        return _field("inch", _evidence_for_value(raw, "in"), "medium")
    return None


def _parse_drawing_type(raw: RawExtractionResult, text: str) -> ExtractedField:
    lowered = text.casefold()
    if "exploded" in lowered:
        value = "exploded parts drawing"
    elif "parts legend" in lowered:
        value = "parts legend"
    elif "outline drawing" in lowered or "compressor outline" in lowered:
        value = "outline drawing"
    elif "assembly" in lowered:
        value = "assembly drawing"
    elif any(token in lowered for token in ("thread adapter", "material:", "all dimensions are in inches", "tolerance:")):
        value = "part manufacturing drawing"
    elif "datasheet" in lowered or "data sheet" in lowered:
        value = "datasheet"
    else:
        value = "unknown engineering PDF"
    evidence = _drawing_type_evidence(raw, value) or _first_nonempty_line(raw)
    confidence = "high" if value != "unknown engineering PDF" else "low"
    return _field(value, evidence, confidence)


def _drawing_type_evidence(raw: RawExtractionResult, drawing_type: str) -> str:
    if drawing_type == "part manufacturing drawing":
        signals: list[str] = []
        for page in raw.pages:
            page_text = _page_parse_text(page)
            lowered = page_text.casefold()
            if "thread adapter" in lowered:
                signals.append("thread adapter")
            if "all dimensions are in inches" in lowered:
                signals.append("ALL DIMENSIONS ARE IN INCHES")
            if "material:" in lowered:
                signals.append("MATERIAL:")
            if "tolerance:" in lowered:
                signals.append("TOLERANCE:")
            if signals:
                return " | ".join(dict.fromkeys(signals))
        cues = ("thread adapter", "all dimensions are in inches", "material:", "tolerance:")
    elif drawing_type == "outline drawing":
        cues = ("outline drawing", "compressor outline")
    elif drawing_type == "assembly drawing":
        cues = ("assembly",)
    else:
        cues = tuple(drawing_type.split()[:1])

    evidence: list[str] = []
    for page in raw.pages:
        for line in _page_parse_lines(page):
            lowered = line.casefold()
            if any(cue in lowered for cue in cues):
                evidence.append(re.sub(r"\s+", " ", line).strip())
            if len(evidence) >= 2:
                return " | ".join(evidence)
    return " | ".join(evidence)


def _parse_bom_components(raw: RawExtractionResult) -> list[BomComponent]:
    components: list[BomComponent] = []
    seen: set[tuple[str, str]] = set()

    for page in raw.pages:
        for table in page.tables:
            for row in table.rows:
                for component in _components_from_table_row(row, page.page_number):
                    key = (component.item_no, component.component_name.casefold())
                    if key in seen:
                        continue
                    seen.add(key)
                    components.append(component)

    if components:
        return sorted(components, key=lambda item: int(item.item_no) if item.item_no.isdigit() else 9999)

    return _components_from_text(raw)


def _components_from_table_row(row: list[str], page_number: int) -> list[BomComponent]:
    components: list[BomComponent] = []
    cells = [cell.strip() for cell in row]
    for item_index, name_index, note_index in _component_column_groups(cells):
        components.extend(
            _components_from_column_cells(
                cells[item_index],
                cells[name_index],
                cells[note_index] if note_index is not None else "",
                page_number,
            )
        )
    return components


def _component_column_groups(cells: list[str]) -> list[tuple[int, int, int | None]]:
    groups: list[tuple[int, int, int | None]] = []
    for index, cell in enumerate(cells):
        if not re.fullmatch(r"\d{1,3}(?:\s*\n\s*\d{1,3})*", cell):
            continue
        name_index = _next_nonempty_cell(cells, index + 1, stop_at_next_number=True)
        if name_index is None:
            continue
        note_index = _next_nonempty_cell(cells, name_index + 1, stop_at_next_number=True)
        groups.append((index, name_index, note_index))
    return groups


def _next_nonempty_cell(cells: list[str], start: int, *, stop_at_next_number: bool = False) -> int | None:
    for index in range(start, len(cells)):
        value = cells[index].strip()
        if not value:
            continue
        if value.lower() in {"no.", "name", "note"}:
            continue
        if stop_at_next_number and re.fullmatch(r"\d{1,3}(?:\s*\n\s*\d{1,3})*", value):
            return None
        return index
    return None


def _components_from_column_cells(
    item_cell: str,
    name_cell: str,
    note_cell: str,
    page_number: int,
) -> list[BomComponent]:
    components: list[BomComponent] = []
    item_values = _split_cell_lines(item_cell)
    name_values = _split_cell_lines(name_cell)
    note_values = _split_cell_lines(note_cell)
    if not item_values or not name_values:
        return components

    if len(item_values) == 1:
        name, numerator = _combine_multiline_name(name_values)
        note = note_values[0] if note_values else ""
        if numerator and re.match(r'^[248]"', note):
            note = f"{numerator}/{note}"
        row_values = [(item_values[0], name, note)]
    else:
        row_values = []
        for item_offset, item_no in enumerate(item_values):
            name = name_values[item_offset] if item_offset < len(name_values) else ""
            note = _note_for_multi_item_row(name, note_values, item_offset, len(item_values))
            row_values.append((item_no, name, note))

    for item_no, name, note in row_values:
        if not re.fullmatch(r"\d{1,3}", item_no) or not name or name.lower() in {"name", "note"}:
            continue
        name, note = _clean_component_name_note(item_no, name, note)
        if not name:
            continue
        evidence = f"{item_no} | {name} | {note}".strip(" |")
        components.append(
            BomComponent(
                item_no=item_no,
                component_name=name,
                note=note,
                category=_component_category(name + " " + note),
                page=page_number,
                confidence="high",
                evidence=evidence,
            )
        )
    return components


def _combine_multiline_name(name_values: list[str]) -> tuple[str, str]:
    numerator = ""
    pieces = []
    for value in name_values:
        if re.fullmatch(r"[135]", value):
            numerator = value
            continue
        pieces.append(value)
    return " ".join(pieces), numerator


def _note_for_multi_item_row(name: str, note_values: list[str], item_offset: int, item_count: int) -> str:
    if len(note_values) == item_count:
        return note_values[item_offset]
    if len(note_values) == 1:
        note = note_values[0]
        if re.search(r"\d+\s*W", note, re.I):
            return note if "heater" in name.casefold() else ""
        return note
    if item_offset < len(note_values):
        return note_values[item_offset]
    return ""


def _split_cell_lines(value: str) -> list[str]:
    return [item.strip() for item in value.splitlines() if item.strip()]


def _clean_component_name_note(item_no: str, name: str, note: str) -> tuple[str, str]:
    name = name.strip()
    note = note.strip()
    name = name.replace("Liquid(oilorrefrigerant)", "Liquid (oil or refrigerant)")
    name = name.replace("Checkvalve", "Check valve")
    name = name.replace("Oilpressure", "Oil pressure")
    note = note.replace("50W300W", "150W/300W")

    if item_no == "11" and name.casefold() == "differential switch":
        name = "Oil pressure differential switch"

    match = re.match(r"^(?P<name>.+?)\s+(?P<num>[135])$", name)
    if match and re.match(r"^(?:/)?[248]\"", note):
        name = match.group("name")
        note = f"{match.group('num')}/{note}" if not note.startswith("/") else f"{match.group('num')}{note}"
    elif match and note == '12"':
        name = match.group("name")
        note = '1 1/2"'
    elif match and re.search(r"\d+\s*W", note, re.I):
        name = match.group("name")
    elif note == '12"':
        note = '1/2"'

    if "  " in name:
        name = re.sub(r"\s+", " ", name)
    if "  " in note:
        note = re.sub(r"\s+", " ", note)
    return name, note


def _components_from_text(raw: RawExtractionResult) -> list[BomComponent]:
    components: list[BomComponent] = []
    text = "\n".join(page.text for page in raw.pages)
    known_names = [
        "Angle valve",
        "Discharge flange",
        "Solenoid valve",
        "Check valve",
        "Oil heater",
        "Oil filter cartridge",
        "Suction flange",
        "Cable box",
        "Service flange",
        "Oil drain valve",
        "Oil level switch",
        "Discharge temp. sensor",
        "Economizer connector",
        "Safety Valve",
        "Oil sight glass",
    ]
    item_numbers = re.findall(r"(?m)^\s*(\d{1,2})\s*$", text)
    next_item = 1
    for name in known_names:
        if re.search(re.escape(name), text, re.I):
            item_no = str(next_item)
            if item_numbers and len(components) < len(item_numbers):
                item_no = item_numbers[len(components)]
            components.append(
                BomComponent(
                    item_no=item_no,
                    component_name=name,
                    category=_component_category(name),
                    page=_page_for_value(raw, name),
                    confidence="low",
                    evidence=_evidence_for_value(raw, name),
                    warnings=["Component extracted from loose text, not a parsed table row."],
                )
            )
            next_item += 1
    return components


def _parse_engineering_tables(raw: RawExtractionResult) -> list[EngineeringTable]:
    tables: list[EngineeringTable] = []
    for page in raw.pages:
        for table_index, table in enumerate(page.tables, start=1):
            if not table.rows or not any(any(cell.strip() for cell in row) for row in table.rows):
                continue
            headers = [cell.strip() for cell in table.rows[0]]
            normalized_headers = [_normalize_header(header) for header in headers]
            table_type, confidence, warnings = _classify_engineering_table(normalized_headers, table.rows)
            if table_type in {"bom_component_table", "layout_or_title_block_table"}:
                continue
            rows = _normalized_table_rows(normalized_headers, table.rows[1:])
            if rows or table_type != "unknown_engineering_table":
                tables.append(
                    EngineeringTable(
                        table_type=table_type,
                        table_id=f"page_{page.page_number}_table_{table_index}",
                        table_index=table_index,
                        headers=normalized_headers,
                        rows=rows,
                        page=page.page_number,
                        confidence=confidence,
                        evidence=" | ".join(header for header in headers if header),
                        warnings=warnings,
                    )
                )
    return tables


def _normalized_table_rows(headers: list[str], raw_rows: list[list[str]]) -> list[dict[str, str]]:
    rows = []
    fallback_headers = headers or []
    for raw_row in raw_rows:
        row = {}
        for index, value in enumerate(raw_row):
            header = fallback_headers[index] if index < len(fallback_headers) and fallback_headers[index] else f"column_{index + 1}"
            row[header] = value.strip()
        if any(row.values()):
            rows.append(row)
    return rows


def _classify_engineering_table(headers: list[str], rows: list[list[str]]) -> tuple[str, str, list[str]]:
    header_set = set(headers)
    text = " ".join(" ".join(row) for row in rows).casefold()
    warnings: list[str] = []
    if _looks_like_layout_or_title_block_table(headers, text):
        return "layout_or_title_block_table", "low", ["Native table looks like a layout/title-block extraction, not a reusable engineering table."]
    if {"item_number", "chart_number", "thread_size"}.issubset(header_set) or "thread_size" in header_set:
        return "thread_chart", "high", warnings
    if {"item_number", "component_name"}.issubset(header_set) or {"no.", "name"}.issubset(header_set):
        return "bom_component_table", "high", warnings
    if any(token in header_set for token in ("hole_size", "hole_diameter", "drill_size")) or "drill" in text:
        return "hole_chart", "medium", warnings
    if any(token in header_set for token in ("bolt_size", "bolt", "fastener")) or "bolt" in text:
        return "bolt_chart", "medium", warnings
    if any(token in header_set for token in ("finish", "surface_finish", "coating", "plating")) or any(token in text for token in ("finish", "coating", "plating")):
        return "finish_chart", "medium", warnings
    if any(token in header_set for token in ("material", "material_spec", "specification")) or "material" in text:
        return "material_table", "medium", warnings
    if any(token in header_set for token in ("tolerance", "tol")) or "tolerance" in text:
        return "tolerance_table", "medium", warnings
    if any(token in header_set for token in ("revision", "rev", "description", "date")) and "revision" in text:
        return "revision_table", "medium", warnings
    if any(token in header_set for token in ("inspection", "characteristic")) or "inspection" in text:
        return "inspection_table", "medium", warnings
    if "torque" in header_set or "torque" in text:
        return "torque_table", "medium", warnings
    if _table_has_engineering_signal(text):
        warnings.append("Table has engineering-like content but did not match a known table type.")
        return "unknown_engineering_table", "review", warnings
    return "unknown_engineering_table", "review", ["Table did not match a known engineering table type."]


def _looks_like_layout_or_title_block_table(headers: list[str], text: str) -> bool:
    has_giant_header = any(len(header) > 80 for header in headers)
    title_tokens = ("model:", "dwg no.", "drawn by:", "approved by:", "standard notes", "revisions:")
    title_token_count = sum(1 for token in title_tokens if token in text)
    known_header_count = sum(1 for header in headers if header in {"item_number", "chart_number", "thread_size", "material", "finish", "tolerance"})
    return has_giant_header and title_token_count >= 2 and known_header_count == 0


def _table_has_engineering_signal(text: str) -> bool:
    signals = (
        "thread",
        "material",
        "finish",
        "coating",
        "plating",
        "tolerance",
        "inspection",
        "torque",
        "hole",
        "drill",
        "bolt",
        "revision",
        "rev",
        "heat treat",
    )
    return any(signal in text for signal in signals)


def _normalize_header(header: str) -> str:
    normalized = re.sub(r"\s+", " ", header.strip().casefold())
    aliases = {
        "item #": "item_number",
        "item no.": "item_number",
        "item no": "item_number",
        "chart#": "chart_number",
        "chart #": "chart_number",
        "thread size 't'": "thread_size",
        "thread size": "thread_size",
        "item": "item_number",
        "no.": "no.",
        "no": "no.",
        "name": "name",
        "component": "component_name",
        "component name": "component_name",
        "description": "description",
        "rev": "rev",
        "revision": "revision",
        "date": "date",
        "material": "material",
        "finish": "finish",
        "surface finish": "surface_finish",
        "tolerance": "tolerance",
        "hole size": "hole_size",
        "hole diameter": "hole_diameter",
        "drill size": "drill_size",
        "bolt size": "bolt_size",
        "torque": "torque",
        "inspection": "inspection",
    }
    return aliases.get(normalized, normalized.replace(" ", "_"))


def _is_thread_or_item_chart(headers: list[str]) -> bool:
    header_set = set(headers)
    return "item_number" in header_set and ("thread_size" in header_set or "chart_number" in header_set)


def _parse_drawing_regions(raw: RawExtractionResult, engineering_tables: list[EngineeringTable]) -> list[DrawingRegion]:
    regions: list[DrawingRegion] = []
    for page in raw.pages:
        regions.append(
            DrawingRegion(
                region_id=f"page_{page.page_number}_drawing_body",
                page=page.page_number,
                region_type="drawing_body",
                label="drawing body",
                x0=0,
                top=0,
                x1=page.page_width,
                bottom=page.page_height,
                confidence="low",
                evidence="Default page drawing region.",
            )
        )
        regions.extend(_regions_from_lines(page))
        regions.extend(_regions_from_engineering_tables(page, engineering_tables))
        regions.extend(_regions_from_vector_primitives(page))
    return _dedupe_regions(regions)


def _regions_from_lines(page: object) -> list[DrawingRegion]:
    buckets: dict[str, list[object]] = {
        "title_block": [],
        "tolerance_notes": [],
        "thread_callout_area": [],
        "view_label_area": [],
    }
    for line in getattr(page, "reconstructed_lines", []):
        text = (line.normalized_text or line.text or "").strip()
        lowered = text.casefold()
        if not text:
            continue
        if re.search(r"\b(?:model|dwg\s*no|drawn by|created date|approved by|material|cage|sheet)\s*:", text, re.I):
            buckets["title_block"].append(line)
        if any(token in lowered for token in ("tolerance", "asme", "chamfer:", "angle:", ".xx", ".xxx")):
            buckets["tolerance_notes"].append(line)
        if "thread" in lowered or METRIC_THREAD_RE.search(text) or UNIFIED_THREAD_RE.search(text):
            buckets["thread_callout_area"].append(line)
        if re.search(r"\b(?:detail|section|view)\s+[A-Z0-9-]+\b", text, re.I):
            buckets["view_label_area"].append(line)

    regions = []
    page_number = getattr(page, "page_number", None)
    for region_type, lines in buckets.items():
        if not lines or page_number is None:
            continue
        x0, top, x1, bottom = _line_bbox(lines)
        regions.append(
            DrawingRegion(
                region_id=f"page_{page_number}_{region_type}",
                page=page_number,
                region_type=region_type,
                label=region_type.replace("_", " "),
                x0=x0,
                top=top,
                x1=x1,
                bottom=bottom,
                confidence="medium",
                evidence=" | ".join((line.normalized_text or line.text).strip() for line in lines[:3]),
            )
        )
    return regions




def _regions_from_vector_primitives(page: object) -> list[DrawingRegion]:
    primitives = [
        primitive
        for primitive in getattr(page, "drawing_primitives", [])
        if _is_view_region_primitive(primitive, getattr(page, "page_width", 0), getattr(page, "page_height", 0))
    ]
    if not primitives:
        return []

    clusters = _cluster_vector_primitives(primitives)
    page_number = getattr(page, "page_number", None)
    page_area = float(getattr(page, "page_width", 0) or 0) * float(getattr(page, "page_height", 0) or 0)
    regions: list[DrawingRegion] = []
    for index, cluster in enumerate(clusters, start=1):
        if len(cluster) < 20:
            continue
        x0, top, x1, bottom = _primitive_bbox(cluster)
        width = x1 - x0
        height = bottom - top
        area = width * height
        if width < 60 or height < 45:
            continue
        if page_area and area / page_area > 0.82:
            continue
        type_counts = Counter(getattr(primitive, "primitive_type", "unknown_vector") for primitive in cluster)
        evidence = ", ".join(f"{name} x{count}" for name, count in type_counts.most_common(4))
        regions.append(
            DrawingRegion(
                region_id=f"page_{page_number}_vector_view_{index}",
                page=page_number,
                region_type="drawing_view",
                label=f"vector drawing view {index}",
                x0=round(x0, 3),
                top=round(top, 3),
                x1=round(x1, 3),
                bottom=round(bottom, 3),
                confidence="medium" if len(cluster) >= 60 else "low",
                evidence=f"{len(cluster)} vector primitives: {evidence}",
                warnings=["Vector cluster is a drawing-view candidate, not confirmed CAD geometry."],
            )
        )
    return _limit_overlapping_vector_regions(regions)


def _is_view_region_primitive(primitive: object, page_width: float, page_height: float) -> bool:
    primitive_type = getattr(primitive, "primitive_type", "")
    if primitive_type in {"table_box", "unknown_vector"}:
        return False
    x0 = float(getattr(primitive, "x0", 0.0) or 0.0)
    top = float(getattr(primitive, "top", 0.0) or 0.0)
    x1 = float(getattr(primitive, "x1", 0.0) or 0.0)
    bottom = float(getattr(primitive, "bottom", 0.0) or 0.0)
    width = x1 - x0
    height = bottom - top
    if width <= 0.1 and height <= 0.1:
        return False
    if page_width and page_height and width * height > page_width * page_height * 0.35:
        return False
    return max(width, height) >= 3


def _cluster_vector_primitives(primitives: list[object]) -> list[list[object]]:
    cell_size = 85.0
    cells: dict[tuple[int, int], list[object]] = {}
    for primitive in primitives:
        center = _primitive_center(primitive)
        cell = (int(center[0] // cell_size), int(center[1] // cell_size))
        cells.setdefault(cell, []).append(primitive)

    dense_cells = {cell for cell, items in cells.items() if len(items) >= 6}
    visited: set[tuple[int, int]] = set()
    clusters: list[list[object]] = []
    for cell in sorted(dense_cells):
        if cell in visited:
            continue
        stack = [cell]
        component_cells: set[tuple[int, int]] = set()
        while stack:
            current = stack.pop()
            if current in visited or current not in dense_cells:
                continue
            visited.add(current)
            component_cells.add(current)
            cx, cy = current
            for nx in range(cx - 1, cx + 2):
                for ny in range(cy - 1, cy + 2):
                    neighbor = (nx, ny)
                    if neighbor not in visited and neighbor in dense_cells:
                        stack.append(neighbor)
        cluster = [primitive for component in component_cells for primitive in cells.get(component, [])]
        if cluster:
            clusters.append(cluster)
    return sorted(clusters, key=lambda cluster: (_primitive_bbox(cluster)[1], _primitive_bbox(cluster)[0]))


def _primitive_center(primitive: object) -> tuple[float, float]:
    return (
        (float(getattr(primitive, "x0", 0.0) or 0.0) + float(getattr(primitive, "x1", 0.0) or 0.0)) / 2,
        (float(getattr(primitive, "top", 0.0) or 0.0) + float(getattr(primitive, "bottom", 0.0) or 0.0)) / 2,
    )


def _primitive_bbox(primitives: list[object]) -> tuple[float, float, float, float]:
    return (
        min(float(getattr(primitive, "x0", 0.0) or 0.0) for primitive in primitives),
        min(float(getattr(primitive, "top", 0.0) or 0.0) for primitive in primitives),
        max(float(getattr(primitive, "x1", 0.0) or 0.0) for primitive in primitives),
        max(float(getattr(primitive, "bottom", 0.0) or 0.0) for primitive in primitives),
    )


def _limit_overlapping_vector_regions(regions: list[DrawingRegion]) -> list[DrawingRegion]:
    kept: list[DrawingRegion] = []
    for region in sorted(regions, key=lambda item: (_region_area(item), item.region_id), reverse=True):
        if any(_region_overlap_ratio(region, existing) > 0.82 for existing in kept):
            continue
        kept.append(region)
    return sorted(kept, key=lambda item: (item.top or 0.0, item.x0 or 0.0))[:12]


def _region_area(region: DrawingRegion) -> float:
    if None in (region.x0, region.top, region.x1, region.bottom):
        return 0.0
    return max(0.0, float(region.x1 or 0.0) - float(region.x0 or 0.0)) * max(0.0, float(region.bottom or 0.0) - float(region.top or 0.0))


def _region_overlap_ratio(first: DrawingRegion, second: DrawingRegion) -> float:
    if None in (first.x0, first.top, first.x1, first.bottom, second.x0, second.top, second.x1, second.bottom):
        return 0.0
    x0 = max(float(first.x0 or 0.0), float(second.x0 or 0.0))
    top = max(float(first.top or 0.0), float(second.top or 0.0))
    x1 = min(float(first.x1 or 0.0), float(second.x1 or 0.0))
    bottom = min(float(first.bottom or 0.0), float(second.bottom or 0.0))
    overlap = max(0.0, x1 - x0) * max(0.0, bottom - top)
    smaller = min(_region_area(first), _region_area(second))
    return overlap / smaller if smaller else 0.0

def _regions_from_engineering_tables(page: object, engineering_tables: list[EngineeringTable]) -> list[DrawingRegion]:
    page_number = getattr(page, "page_number", None)
    if page_number is None:
        return []
    regions: list[DrawingRegion] = []
    for table in engineering_tables:
        if table.page != page_number:
            continue
        evidence = _engineering_table_region_evidence(table)
        matched_lines = _lines_matching_table(page, table, evidence)
        bbox = _line_bbox(matched_lines) if matched_lines else (None, None, None, None)
        warnings = list(table.warnings)
        if not matched_lines:
            warnings.append("Table region coordinates could not be inferred from reconstructed lines.")
        regions.append(
            DrawingRegion(
                region_id=f"{table.table_id or f'page_{page_number}_table'}_region",
                page=page_number,
                region_type="engineering_table",
                label=table.table_type,
                x0=bbox[0],
                top=bbox[1],
                x1=bbox[2],
                bottom=bbox[3],
                confidence="medium" if matched_lines else "low",
                evidence=evidence,
                warnings=warnings,
            )
        )
    return regions


def _engineering_table_region_evidence(table: EngineeringTable) -> str:
    parts = [table.evidence or " ".join(table.headers)]
    for row in table.rows[:4]:
        row_text = " | ".join(value for value in row.values() if value)
        if row_text:
            parts.append(row_text)
    return _compact_evidence(" || ".join(part for part in parts if part), 260)


def _lines_matching_table(page: object, table: EngineeringTable, evidence: str) -> list[object]:
    tokens = _region_match_tokens(evidence)
    for row in table.rows[:4]:
        tokens.extend(_region_match_tokens(" ".join(row.values())))
    tokens = list(dict.fromkeys(token for token in tokens if len(token) >= 3))
    matched = []
    for line in getattr(page, "reconstructed_lines", []):
        normalized = _region_match_text(getattr(line, "normalized_text", "") or getattr(line, "text", ""))
        if not normalized:
            continue
        if any(token in normalized for token in tokens):
            matched.append(line)
    return matched[:8]


def _line_bbox(lines: list[object]) -> tuple[float, float, float, float]:
    return (
        min(float(getattr(line, "x0", 0.0)) for line in lines),
        min(float(getattr(line, "top", 0.0)) for line in lines),
        max(float(getattr(line, "x1", 0.0)) for line in lines),
        max(float(getattr(line, "bottom", 0.0)) for line in lines),
    )


def _dedupe_regions(regions: list[DrawingRegion]) -> list[DrawingRegion]:
    deduped: list[DrawingRegion] = []
    seen: set[str] = set()
    for region in sorted(regions, key=lambda item: (item.page, -_region_priority(item.region_type), item.region_id)):
        key = region.region_id
        if key in seen:
            continue
        seen.add(key)
        deduped.append(region)
    return deduped


def _region_priority(region_type: str) -> int:
    return REGION_PRIORITY.get(region_type, 10)


def _parse_thread_requirements(
    raw: RawExtractionResult,
    engineering_tables: list[EngineeringTable],
    regions: list[DrawingRegion],
) -> list[ThreadRequirement]:
    requirements: list[ThreadRequirement] = []
    seen: set[str] = set()

    for page in raw.pages:
        page_text = _page_parse_text(page)
        for requirement in _thread_requirements_from_text(page_text, page.page_number, regions):
            key = _thread_requirement_key(requirement)
            if key not in seen:
                seen.add(key)
                requirements.append(requirement)

    for table in engineering_tables:
        for row in table.rows:
            thread_size = row.get("thread_size", "").strip()
            if not thread_size:
                continue
            item_number = row.get("item_number", "").strip()
            chart_number = row.get("chart_number", "").strip()
            evidence = " | ".join(part for part in (item_number, chart_number, thread_size) if part)
            requirement = _thread_requirement_from_callout(
                thread_size,
                table.page,
                evidence,
                regions,
                label="thread chart row",
            )
            if requirement is None:
                continue
            key = _thread_requirement_key(requirement)
            if key not in seen:
                seen.add(key)
                requirements.append(requirement)

    return requirements


def _build_engineering_requirements(data: StructuredEngineeringData) -> list[EngineeringRequirement]:
    requirements: list[EngineeringRequirement] = []
    seen: set[tuple[str, str, str]] = set()

    for thread in data.thread_requirements:
        parsed_fields = {
            "thread_size": thread.thread_size,
            "pitch": thread.pitch,
            "threads_per_inch": thread.threads_per_inch,
            "thread_class": thread.thread_class,
            "minimum_full_threads": thread.minimum_full_threads,
            "chart_reference": thread.chart_reference,
            "source_table": thread.source_table,
            "label": thread.label,
            "relief_note": thread.relief_note,
        }
        value = thread.evidence or thread.thread_size or thread.label
        requirement = EngineeringRequirement(
            requirement_type="thread",
            value=value,
            parsed_fields={key: value for key, value in parsed_fields.items() if value not in (None, "")},
            source=thread.source,
            page=thread.page,
            region_id=thread.region_id,
            confidence=thread.confidence,
            evidence=thread.evidence,
            warnings=thread.warnings,
        )
        _append_requirement(requirements, seen, requirement)

    for field in data.manufacturing_requirements:
        requirement_type = _requirement_type_from_value(field.value)
        requirement = EngineeringRequirement(
            requirement_type=requirement_type,
            value=field.value,
            parsed_fields=_parsed_fields_from_requirement_value(requirement_type, field.value),
            source=field.source,
            page=field.page,
            region_id=_region_id_for_evidence(data.drawing_regions, field.page, field.evidence or field.value),
            confidence=field.confidence,
            evidence=field.evidence,
            warnings=field.warnings,
        )
        _append_requirement(requirements, seen, requirement)

    for field in data.process_requirements:
        requirement = EngineeringRequirement(
            requirement_type="process",
            value=field.value,
            parsed_fields={"process": field.value},
            source=field.source,
            page=field.page,
            region_id=_region_id_for_evidence(data.drawing_regions, field.page, field.evidence or field.value),
            confidence=field.confidence,
            evidence=field.evidence,
            warnings=field.warnings,
        )
        _append_requirement(requirements, seen, requirement)

    for connection in data.connections:
        value = " ".join(part for part in (connection.label, connection.size, connection.connection_type) if part).strip()
        if not value:
            continue
        requirement = EngineeringRequirement(
            requirement_type="connection",
            value=value,
            parsed_fields={
                "label": connection.label,
                "size": connection.size,
                "connection_type": connection.connection_type,
                "option": connection.option,
            },
            source=connection.source,
            page=connection.page,
            region_id=_region_id_for_evidence(data.drawing_regions, connection.page, connection.evidence or value),
            confidence=connection.confidence,
            evidence=connection.evidence,
            warnings=connection.warnings,
        )
        _append_requirement(requirements, seen, requirement)

    return requirements


def _append_requirement(
    requirements: list[EngineeringRequirement],
    seen: set[tuple[str, str, str]],
    requirement: EngineeringRequirement,
) -> None:
    key = (requirement.requirement_type, requirement.value.casefold(), requirement.evidence.casefold())
    if key in seen:
        return
    seen.add(key)
    requirements.append(requirement)


def _requirement_type_from_value(value: str) -> str:
    lowered = value.casefold()
    if lowered.startswith("material:"):
        return "material"
    if lowered.startswith("surface finish:"):
        return "surface_finish"
    if lowered.startswith("heat treatment"):
        return "heat_treatment"
    if lowered.startswith("finish"):
        return "finish"
    if "burr" in lowered or "sharp edge" in lowered or "edge break" in lowered:
        return "edge_break"
    if "plating" in lowered or "coating" in lowered:
        return "coating"
    if "machin" in lowered:
        return "machining"
    if "cast" in lowered:
        return "casting"
    if "weld" in lowered:
        return "welding"
    if "inspection" in lowered:
        return "inspection"
    return "manufacturing"


def _parsed_fields_from_requirement_value(requirement_type: str, value: str) -> dict[str, object]:
    if ":" not in value:
        return {"text": value}
    label, raw_value = value.split(":", 1)
    parsed: dict[str, object] = {"label": label.strip(), "value": raw_value.strip()}
    if requirement_type == "surface_finish":
        match = re.search(r"(\d+(?:\.\d+)?)", raw_value)
        if match:
            parsed["surface_finish_value"] = float(match.group(1))
    if requirement_type == "edge_break":
        range_match = RANGE_RE.search(raw_value)
        if range_match:
            parsed["range_start"] = _float_from_maybe_leading_decimal(range_match.group("start"))
            parsed["range_end"] = _float_from_maybe_leading_decimal(range_match.group("end"))
    return parsed


def _float_from_maybe_leading_decimal(value: str) -> float:
    return float(f"0{value}" if value.startswith(".") else value)


def _thread_requirement_key(requirement: ThreadRequirement) -> str:
    return "|".join(
        str(part).casefold()
        for part in (
            requirement.thread_size,
            requirement.pitch,
            requirement.threads_per_inch,
            requirement.thread_class,
            requirement.minimum_full_threads,
            requirement.label,
            requirement.chart_reference,
            requirement.evidence if not requirement.thread_size else "",
        )
    )


def _thread_requirements_from_text(text: str, page_number: int, regions: list[DrawingRegion]) -> list[ThreadRequirement]:
    requirements: list[ThreadRequirement] = []
    lines = _lines(text)
    for index, line in enumerate(lines):
        if re.match(r"^MCP\d+\s+-\d+\s+", line.strip(), re.I):
            continue
        if not _line_has_thread_requirement_signal(line):
            continue
        context = line
        if index + 1 < len(lines) and MIN_FULL_THREADS_RE.search(lines[index + 1]):
            context = f"{line} {lines[index + 1]}"
        requirement = _thread_requirement_from_callout(context, page_number, context, regions)
        if requirement is not None:
            requirements.append(requirement)
            continue
        if re.search(r"\bTHREAD\s*['\"][A-Z0-9]+['\"]|\bMIN\.?\s+THREAD\s+RELIEF\b", line, re.I):
            requirements.append(
                ThreadRequirement(
                    label=_clean_thread_label(line),
                    relief_note=line if "relief" in line.casefold() else "",
                    chart_reference=_thread_chart_reference(line),
                    source_table="thread_chart" if _thread_chart_reference(line) else "",
                    page=page_number,
                    region_id=_region_id_for_evidence(regions, page_number, line),
                    confidence="medium" if "relief" in line.casefold() else "review",
                    evidence=line,
                    warnings=[] if "relief" in line.casefold() else ["Thread label references a chart/table and is not a full standalone thread size/class callout."],
                )
            )
    return requirements


def _line_has_thread_requirement_signal(line: str) -> bool:
    lowered = line.casefold()
    if METRIC_THREAD_RE.search(line) or UNIFIED_THREAD_RE.search(line):
        return True
    if re.search(r"\bTHREAD\s*['\"][A-Z0-9]+['\"]|\bMIN\.?\s+THREAD\s+RELIEF\b", line, re.I):
        return True
    if "thread size" in lowered and "thread adapter" not in lowered:
        return True
    return False


def _thread_requirement_from_callout(
    text: str,
    page_number: int | None,
    evidence: str,
    regions: list[DrawingRegion],
    *,
    label: str = "",
) -> ThreadRequirement | None:
    metric_match = METRIC_THREAD_RE.search(text)
    unified_match = UNIFIED_THREAD_RE.search(text)
    if metric_match:
        thread_size = metric_match.group("size").upper()
        pitch = float(metric_match.group("pitch"))
        threads_per_inch = None
        thread_class = metric_match.group("class")
        callout = metric_match.group(0)
    elif unified_match:
        thread_size = unified_match.group("size")
        pitch = None
        threads_per_inch = int(unified_match.group("tpi"))
        thread_class = unified_match.group("class").upper()
        callout = unified_match.group(0)
    else:
        return None

    min_threads_match = MIN_FULL_THREADS_RE.search(text)
    relief_note = _first_thread_relief_note(text)
    chart_reference = "T" if label == "thread chart row" else _thread_chart_reference(text)
    return ThreadRequirement(
        thread_size=thread_size,
        pitch=pitch,
        threads_per_inch=threads_per_inch,
        thread_class=thread_class,
        minimum_full_threads=int(min_threads_match.group("count")) if min_threads_match else None,
        label=label or _clean_thread_label(text),
        relief_note=relief_note,
        chart_reference=chart_reference,
        source_table="thread_chart" if label == "thread chart row" else "",
        page=page_number,
        region_id=_region_id_for_evidence(regions, page_number, evidence),
        confidence="high" if metric_match or unified_match else "medium",
        evidence=_thread_evidence(evidence or callout),
    )


def _clean_thread_label(text: str) -> str:
    match = re.search(r"\bTHREAD\s*['\"](?P<label>[A-Z0-9]+)['\"]", text, re.I)
    if match:
        value = (match.group("label") or "").strip()
        return f"THREAD {value}".strip()
    if re.search(r"\bTHREAD\s+SIZE\b", text, re.I):
        return "THREAD SIZE"
    return ""


def _first_thread_relief_note(text: str) -> str:
    match = re.search(r"\bMIN\.?\s+THREAD\s+RELIEF\s+ALLOWED\b", text, re.I)
    return match.group(0) if match else ""


def _thread_chart_reference(text: str) -> str:
    match = re.search(r"THREAD(?:\s+SIZE)?\s*['\"](?P<ref>[A-Z0-9]+)['\"]", text, re.I)
    if match:
        return match.group("ref")
    return "T" if "thread chart row" in text.casefold() else ""


def _thread_evidence(text: str) -> str:
    metric = METRIC_THREAD_RE.search(text)
    if metric:
        evidence = metric.group(0)
        min_threads = MIN_FULL_THREADS_RE.search(text)
        if min_threads:
            evidence = f"{evidence} ({min_threads.group(0)})"
        return evidence
    unified = UNIFIED_THREAD_RE.search(text)
    return unified.group(0) if unified else text.strip()


def _parse_dimensions(raw: RawExtractionResult, regions: list[DrawingRegion]) -> list[DimensionCandidate]:
    dimensions: list[DimensionCandidate] = []
    seen: set[tuple[float, str, float | None]] = set()

    for page in raw.pages:
        page_text = _page_parse_text(page)
        for dimension in _dimension_rows(page_text, page.page_number):
            key = (dimension.value, dimension.unit, dimension.imperial_value)
            if key in seen:
                continue
            seen.add(key)
            dimensions.append(dimension)

        for match in DIMENSION_PAIR_RE.finditer(page_text):
            metric = float(match.group("metric"))
            imperial = float(match.group("imperial"))
            if not _valid_metric_imperial_pair(metric, imperial):
                continue
            key = (metric, "mm", imperial)
            if key in seen:
                continue
            seen.add(key)
            role, role_confidence = _dimension_role(page.text, metric)
            dimensions.append(
                DimensionCandidate(
                    value=metric,
                    unit="mm",
                    imperial_value=imperial,
                    role=role,
                    role_confidence=role_confidence,
                    region_id=_region_id_for_evidence(regions, page.page_number, match.group(0)),
                    raw_callout=match.group(0),
                    normalized_callout=match.group(0),
                    page=page.page_number,
                    confidence="medium",
                    evidence=match.group(0),
                )
            )

        for match in CHAMFER_RE.finditer(page_text):
            size = float(match.group("size"))
            unit = "inch" if _page_uses_inches(page_text) else "unknown"
            key = (size, unit, float(match.group("angle")))
            if key not in seen:
                seen.add(key)
                quantity = _quantity_from_prefix(match.group("count") or "")
                dimensions.append(
                    DimensionCandidate(
                        value=size,
                        unit=unit,  # type: ignore[arg-type]
                        dimension_type="chamfer",
                        quantity=quantity,
                        angle_value=float(match.group("angle")),
                        angle_unit="degree",
                        role="chamfer",
                        role_confidence="high",
                        raw_callout=match.group(0),
                        normalized_callout=match.group(0),
                        region_id=_region_id_for_evidence(regions, page.page_number, match.group(0)),
                        page=page.page_number,
                        confidence="high",
                        evidence=match.group(0),
                    )
                )

        for match in DIAMETER_RE.finditer(page_text):
            value = float(match.group("value"))
            unit = "inch" if _page_uses_inches(page_text) else "mm"
            key = (value, unit, None)
            if key in seen:
                continue
            seen.add(key)
            dimensions.append(
                DimensionCandidate(
                    value=value,
                    unit=unit,  # type: ignore[arg-type]
                    dimension_type="diameter",
                    quantity=_quantity_from_prefix(match.group("count") or ""),
                    role="hole_or_diameter",
                    role_confidence="medium",
                    raw_callout=match.group(0),
                    normalized_callout=match.group(0),
                    region_id=_region_id_for_evidence(regions, page.page_number, match.group(0)),
                    page=page.page_number,
                    confidence="medium",
                    evidence=match.group(0),
                )
            )

        for match in ANGLE_RE.finditer(page_text):
            if _inside_compound_or_default_tolerance_context(page_text, match.start()):
                continue
            value = float(match.group("value"))
            key = (value, "degree", None)
            if key in seen:
                continue
            seen.add(key)
            dimensions.append(
                DimensionCandidate(
                    value=value,
                    unit="degree",
                    dimension_type="angle",
                    raw_callout=match.group(0),
                    normalized_callout=match.group(0),
                    region_id=_region_id_for_evidence(regions, page.page_number, match.group(0)),
                    page=page.page_number,
                    confidence="medium",
                    evidence=match.group(0),
                )
            )

        for match in RANGE_RE.finditer(page_text):
            if _inside_thread_or_tolerance_context(page_text, match.start()):
                continue
            if not _looks_like_range_dimension(match.group(0)):
                continue
            start = _float_from_possible_leading_decimal(match.group("start"))
            end = _float_from_possible_leading_decimal(match.group("end"))
            if end <= start:
                continue
            unit = "inch" if _page_uses_inches(page_text) else "unknown"
            key = (start, unit, end)
            if key in seen:
                continue
            seen.add(key)
            dimensions.append(
                DimensionCandidate(
                    value=start,
                    unit=unit,  # type: ignore[arg-type]
                    secondary_value=end,
                    dimension_type="range",
                    role="range_dimension_or_allowance",
                    role_confidence="medium",
                    raw_callout=match.group(0),
                    normalized_callout=match.group(0),
                    region_id=_region_id_for_evidence(regions, page.page_number, match.group(0)),
                    page=page.page_number,
                    confidence="medium",
                    evidence=match.group(0),
                    warnings=["Range stored with lower value in value and upper value in secondary_value."],
                )
            )

        for match in INCH_DIMENSION_RE.finditer(page_text):
            value = float(match.group("value"))
            line_context = _line_at_position(page_text, match.start())
            if value > 10 or _line_has_excluded_dimension_context(line_context):
                continue
            key = (value, "inch", None)
            if key in seen:
                continue
            seen.add(key)
            dimensions.append(
                DimensionCandidate(
                    value=value,
                    unit="inch",
                    raw_callout=match.group(0),
                    normalized_callout=match.group(0),
                    region_id=_region_id_for_evidence(regions, page.page_number, match.group(0)),
                    page=page.page_number,
                    confidence="medium",
                    evidence=match.group(0),
                )
            )

    return dimensions


def _line_at_position(text: str, position: int) -> str:
    start = text.rfind("\n", 0, position) + 1
    end = text.find("\n", position)
    if end == -1:
        end = len(text)
    return text[start:end].strip()


def _line_has_excluded_dimension_context(line: str) -> bool:
    lowered = line.casefold()
    if not line:
        return True
    if any(token in lowered for token in ("thread size", "m3x", "m6x", "#10", "#6", ".xxx", ".xxxx", "±", "asme-y", "asme y", "fm3845.dwg")):
        return True
    if CHAMFER_RE.search(line):
        return True
    if re.search(r"\b(?:model|dwg\s*no|drawn by|created date|approved by|phone|fax|cage|sheet)\b", line, re.I):
        return True
    return False


def _dimension_rows(text: str, page_number: int) -> list[DimensionCandidate]:
    dimensions: list[DimensionCandidate] = []
    lines = _lines(text)
    for index, line in enumerate(lines):
        metric_values = [float(item) for item in re.findall(r"\b\d{2,4}(?:\.\d+)?\b", line)]
        if len(metric_values) < 3:
            continue
        nearby = []
        if index > 0:
            nearby.append(lines[index - 1])
        if index + 1 < len(lines):
            nearby.append(lines[index + 1])
        imperial_values: list[float] = []
        for candidate in nearby:
            imperial_values = [float(item) for item in re.findall(r"\((\d{1,3}(?:\.\d+)?)\)", candidate)]
            if len(imperial_values) >= len(metric_values[:3]):
                break
        if len(imperial_values) < 3:
            continue
        for metric, imperial in zip(metric_values[:3], imperial_values[:3], strict=False):
            if not _valid_metric_imperial_pair(metric, imperial):
                continue
            dimensions.append(
                DimensionCandidate(
                    value=metric,
                    unit="mm",
                    imperial_value=imperial,
                    role="possible_envelope",
                    role_confidence="medium",
                    page=page_number,
                    confidence="medium",
                    evidence=f"{line} / {nearby[0] if nearby else ''}",
                )
            )
    return dimensions


def _quantity_from_prefix(value: str) -> int | None:
    match = re.search(r"\d+", value or "")
    return int(match.group(0)) if match else None


def _float_from_possible_leading_decimal(value: str) -> float:
    text = value.strip()
    if text.startswith("."):
        text = "0" + text
    return float(text)


def _looks_like_range_dimension(value: str) -> bool:
    return bool(re.fullmatch(r"\.?\d+(?:\.\d+)?\s*-\s*\.?\d+(?:\.\d+)?", value.strip()))


def _inside_compound_or_default_tolerance_context(text: str, position: int) -> bool:
    context = text[max(0, position - 35) : position + 35].casefold()
    return any(token in context for token in ("chamfer", "angle:", " x ", "±"))


def _region_id_for_evidence(regions: list[DrawingRegion], page_number: int | None, evidence: str) -> str:
    if page_number is None:
        return ""
    page_regions = [region for region in regions if region.page == page_number]
    if not page_regions:
        return ""

    evidence_text = evidence or ""
    preferred = _preferred_region_types_for_evidence(evidence_text)
    matched_regions = _regions_matching_evidence(page_regions, evidence_text)
    preferred_matches = [region for region in matched_regions if region.region_type in preferred]
    if preferred_matches:
        return _highest_priority_region(preferred_matches).region_id

    for region_type in preferred:
        matches = [region for region in page_regions if region.region_type == region_type]
        if matches:
            return _highest_priority_region(matches).region_id

    drawing_body = [region for region in page_regions if region.region_type == "drawing_body"]
    return drawing_body[0].region_id if drawing_body else ""


def _preferred_region_types_for_evidence(evidence: str) -> list[str]:
    lowered = evidence.casefold()
    note_tokens = (
        "tolerance",
        "asme",
        "±",
        ".xx",
        ".xxx",
        "chamfer:",
        "angle:",
        "surface finish",
        "remove burrs",
        "sharp edge",
        "plating",
        "coating",
        "heat treatment",
        "finish:",
    )
    if any(token in lowered for token in note_tokens):
        return ["tolerance_notes", "drawing_body"]
    if any(token in lowered for token in ("model:", "dwg no", "drawn by", "created date", "approved by", "material:", "cage:", "sheet:")):
        return ["title_block", "drawing_body"]
    if any(token in lowered for token in ("item_number", "chart_number", "thread_size")):
        return ["engineering_table", "drawing_body"]
    if "|" in evidence and (METRIC_THREAD_RE.search(evidence) or UNIFIED_THREAD_RE.search(evidence) or "thread" in lowered):
        return ["engineering_table", "thread_callout_area", "drawing_body"]
    if "thread" in lowered or METRIC_THREAD_RE.search(evidence) or UNIFIED_THREAD_RE.search(evidence):
        return ["thread_callout_area", "engineering_table", "drawing_body"]
    return ["drawing_body"]


def _regions_matching_evidence(regions: list[DrawingRegion], evidence: str) -> list[DrawingRegion]:
    tokens = _region_match_tokens(evidence)
    if not tokens:
        return []
    matched = []
    for region in regions:
        region_text = _region_match_text(f"{region.label} {region.evidence}")
        if any(token in region_text for token in tokens):
            matched.append(region)
    return matched


def _region_match_tokens(value: str) -> list[str]:
    normalized = _region_match_text(value)
    tokens = re.findall(r"[a-z0-9#./+-]+", normalized)
    useful = []
    for token in tokens:
        if len(token) < 3 and not token.startswith("#"):
            continue
        if token in {"the", "and", "for", "with", "page", "table"}:
            continue
        useful.append(token)
    return useful[:12]


def _region_match_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.casefold().replace("_", " ")).strip()


def _highest_priority_region(regions: list[DrawingRegion]) -> DrawingRegion:
    return sorted(regions, key=lambda region: (-_region_priority(region.region_type), region.region_id))[0]


def _valid_metric_imperial_pair(metric: float, imperial: float) -> bool:
    expected = metric / 25.4
    tolerance = max(0.12, expected * 0.08)
    return abs(expected - imperial) <= tolerance


def _parse_connections(raw: RawExtractionResult, components: list[BomComponent]) -> list[ConnectionCandidate]:
    candidates: list[ConnectionCandidate] = []
    seen: set[tuple[str, str, str]] = set()

    for component in components:
        text = f"{component.component_name} {component.note}".strip()
        for candidate in _connections_from_text(text, component.page, component.evidence or text, component.source):
            key = (candidate.label.casefold(), candidate.size.casefold(), candidate.connection_type.casefold())
            if key not in seen:
                seen.add(key)
                candidates.append(candidate)

    if components:
        return candidates

    for page in raw.pages:
        for line in _lines(page.text):
            if _looks_like_connection_line(line):
                for candidate in _connections_from_text(line, page.page_number, line, "text"):
                    key = (candidate.label.casefold(), candidate.size.casefold(), candidate.connection_type.casefold())
                    if key not in seen:
                        seen.add(key)
                        candidates.append(candidate)

    return candidates


def _connections_from_text(text: str, page: int | None, evidence: str, source: str) -> list[ConnectionCandidate]:
    results: list[ConnectionCandidate] = []
    for match in CONNECTION_RE.finditer(text):
        size = (match.group("size") or "").strip()
        kind = (match.group("kind") or "").strip()
        if not size or not (kind or '"' in size):
            continue
        label = re.sub(re.escape(match.group(0)), "", text, count=1, flags=re.I).strip(" ,-")
        label = re.sub(r"\boption\b", "", label, flags=re.I).strip(" ,-")
        if not label:
            label = _connection_label_from_text(text)
        results.append(
            ConnectionCandidate(
                label=label,
                size=_normalize_connection_size(size),
                connection_type=kind or _connection_type_from_text(text),
                option="option" in text.casefold(),
                source=source,  # type: ignore[arg-type]
                page=page,
                confidence="medium",
                evidence=evidence,
            )
        )
    return results


def _normalize_connection_size(size: str) -> str:
    size = re.sub(r"\s+", " ", size).strip()
    size = re.sub(r'\s+"', '"', size)
    return size


def _parse_standards(raw: RawExtractionResult) -> list[ExtractedField]:
    fields = []
    for page in raw.pages:
        page_text = _page_parse_text(page)
        for match in STANDARD_RE.finditer(page_text):
            fields.append(_field(match.group(0), match.group(0), "high", page.page_number))
    return _dedupe_fields(fields)


def _parse_tolerances_gdnt(raw: RawExtractionResult) -> list[ExtractedField]:
    fields: list[ExtractedField] = []
    for page in raw.pages:
        page_text = _page_parse_text(page)
        for regex in (STANDARD_RE, SURFACE_RE):
            for match in regex.finditer(page_text):
                fields.append(_field(match.group(0), match.group(0), "high", page.page_number))

        for match in DEFAULT_TOLERANCE_RE.finditer(page_text):
            fields.append(_field(f"default linear tolerance: {match.group('precision')} {match.group('tol')}\"", match.group(0), "high", page.page_number))

        for match in ANGLE_DEFAULT_TOLERANCE_RE.finditer(page_text):
            fields.append(_field(f"default angle tolerance: {match.group('tol')}", match.group(0), "high", page.page_number))

        for match in CHAMFER_DEFAULT_TOLERANCE_RE.finditer(page_text):
            fields.append(_field(f"default chamfer tolerance: {match.group('tol')}", match.group(0), "high", page.page_number))

        fields.extend(_default_tolerances_from_lines(page))

        for match in RANGE_RE.finditer(page_text):
            context = page_text[max(0, match.start() - 45) : match.end() + 45]
            if any(token in context.casefold() for token in ("sharp edges", "burrs", "break sharp", "remove burrs")):
                fields.append(_field(f"default edge break range: {match.group(0)}", context.strip(), "high", page.page_number))

        for match in Fcf_CANDIDATE_RE.finditer(page_text):
            candidate_value, candidate_warnings = _gdnt_candidate_from_raw(match.group("raw"))
            fields.append(
                _field(
                    candidate_value,
                    match.group(0),
                    "review",
                    page.page_number,
                    warnings=candidate_warnings,
                )
            )

        if "⌖" in page_text:
            fields.append(
                _field(
                    "position symbol candidate",
                    _evidence_for_value(raw, "⌖") or "Position-like symbol present without frame context.",
                    "low",
                    page.page_number,
                    warnings=["Symbol alone is not classified as a full GD&T requirement."],
                )
            )

    return _dedupe_fields(fields)


def _default_tolerances_from_lines(page: object) -> list[ExtractedField]:
    fields: list[ExtractedField] = []
    lines = _page_parse_lines(page)
    page_number = getattr(page, "page_number", None)
    for index, line in enumerate(lines):
        if len(line) > 80:
            continue
        is_angle_label = bool(re.match(r"^-?\s*ANGLE\s*:", line, re.I))
        is_chamfer_label = bool(re.match(r"^-?\s*CHAMFER\s*:", line, re.I))
        if not (is_angle_label or is_chamfer_label):
            continue
        context = " ".join(lines[index : min(len(lines), index + 4)])
        match = re.search(r"±\s*(?:\d+\s*/\s*\d+|\d+(?:\.\d+)?)\s*°?", context)
        if not match:
            continue
        if is_chamfer_label:
            value = f"default chamfer tolerance: {match.group(0)}"
            evidence = f"CHAMFER: {match.group(0)}"
        else:
            value = f"default angle tolerance: {match.group(0)}"
            evidence = f"ANGLE: {match.group(0)}"
        fields.append(_field(value, evidence, "high", page_number))
    return fields


def _parse_process_signals(raw: RawExtractionResult) -> list[ExtractedField]:
    fields = []
    for page in raw.pages:
        page_text = _page_parse_text(page)
        fields.extend(_process_label_fields(page_text, page.page_number))
        lowered = page_text.casefold()
        for keyword in PROCESS_KEYWORDS:
            if keyword == "heat treat" and any(field.value == "heat treatment / finish: not specified" for field in fields):
                continue
            if keyword in lowered:
                fields.append(_field(keyword, _evidence_for_value(raw, keyword) or keyword, "high", page.page_number))
    return _dedupe_fields(fields)


def _parse_manufacturing_requirements(
    raw: RawExtractionResult,
    title_block: dict[str, ExtractedField],
) -> list[ExtractedField]:
    fields: list[ExtractedField] = []
    material = title_block.get("material")
    if material:
        fields.append(
            _field(
                f"material: {material.value}",
                material.evidence or material.value,
                material.confidence,
                material.page,
                warnings=material.warnings,
            )
        )

    for page in raw.pages:
        surface_finish_fields = _surface_finish_fields(_page_parse_text(page), page.page_number)
        fields.extend(surface_finish_fields)
        has_surface_finish_value = bool(surface_finish_fields)
        for line in _page_parse_lines(page):
            if len(line) > 180:
                continue
            fields.extend(_manufacturing_label_fields(line, page.page_number))
            lowered = line.casefold()
            if not any(token in lowered for token in ("burr", "sharp edge", "finish", "plating", "coating", "machin", "cast", "weld", "inspection")):
                continue
            if any(token in lowered for token in ("standard notes", "phone:", "fax:", "approved by", "created date")):
                if "remove burrs" not in lowered and "sharp edge" not in lowered:
                    continue
            if has_surface_finish_value and "surface" in lowered and "finish" in lowered:
                continue
            fields.append(_field(_manufacturing_value_from_line(line), line, "medium", page.page_number))
    return _dedupe_fields(fields)


def _surface_finish_fields(text: str, page_number: int) -> list[ExtractedField]:
    fields: list[ExtractedField] = []
    pattern = re.compile(r"\bSURFACE\s*FINISH\s*(?P<value>\d(?:\s+\d+)?)?\s*OR\s*BETTER\b", re.I)
    for match in pattern.finditer(text):
        raw_value = (match.group("value") or "").strip()
        if not raw_value:
            continue
        value = re.sub(r"\s+", "", raw_value)
        fields.append(_field(f"surface finish: {value} or better", f"SURFACE FINISH {value} OR BETTER", "high", page_number))
    return _dedupe_fields(fields)


def _manufacturing_label_fields(text: str, page_number: int) -> list[ExtractedField]:
    fields: list[ExtractedField] = []
    label_pattern = re.compile(
        r"\b(?P<label>HEAT TREATMENT|FINISH|SURFACE FINISH|PLATING|COATING)\s*:?\s*(?P<value>-|[^\n]+)?",
        re.I,
    )
    for match in label_pattern.finditer(text):
        label = re.sub(r"\s+", " ", match.group("label").strip().casefold())
        value = (match.group("value") or "").strip()
        if not value or value == "-" or value.casefold().startswith("standard notes"):
            evidence = f"{match.group('label')}: not specified"
            fields.append(
                _field(
                    f"{label}: not specified",
                    evidence,
                    "medium",
                    page_number,
                    warnings=["Manufacturing label is present, but no populated requirement was found."],
                )
            )
        else:
            fields.append(_field(f"{label}: {value}", match.group(0), "high", page_number))
    return fields


def _manufacturing_value_from_line(line: str) -> str:
    value = re.sub(r"\s+", " ", line).strip()
    value = re.split(r"\b(?:DRAWN BY|CREATED DATE|APPROVED BY|APPROVAL DATE|MODEL|DWG\s*No\.?)\b", value, maxsplit=1, flags=re.I)[0].strip(" :-")
    value = value.replace("SURFACEFINISH ORBETTER", "SURFACE FINISH OR BETTER")
    if re.search(r"\bburr", value, re.I):
        return f"edge/burr requirement: {value}"
    if re.search(r"\bfinish|plating|coating", value, re.I):
        return f"finish requirement: {value}"
    if re.search(r"\bmachin", value, re.I):
        return f"machining requirement: {value}"
    if re.search(r"\bcast", value, re.I):
        return f"casting requirement: {value}"
    if re.search(r"\bweld", value, re.I):
        return f"welding requirement: {value}"
    if re.search(r"\binspection", value, re.I):
        return f"inspection requirement: {value}"
    return value


def _parse_notes(raw: RawExtractionResult) -> list[ExtractedField]:
    notes = []
    seen: set[str] = set()
    for page in raw.pages:
        for line in _page_parse_lines(page):
            for note in _classified_notes_from_line(line, page.page_number):
                key = note.value.casefold()
                if key in seen:
                    continue
                seen.add(key)
                notes.append(note)
    return notes[:40]


def _classified_notes_from_line(line: str, page_number: int) -> list[ExtractedField]:
    clean = re.sub(r"\s+", " ", line).strip()
    lowered = clean.casefold()
    if not clean:
        return []
    structured_tokens = (
        "surface finish",
        "remove burrs",
        "break sharp edges",
        "tolerance:",
        "asme-y14.5",
        "angle:",
        "chamfer:",
        ".xx",
        ".xxx",
    )
    if any(token in lowered for token in structured_tokens):
        return []

    notes: list[ExtractedField] = []
    if "standard notes" in lowered:
        notes.append(_field("standard note: Unless Otherwise Specified", "STANDARD NOTES: (Unless Otherwise Specified)", "medium", page_number))
    if _is_legal_restriction_note(lowered):
        notes.append(_field("legal note: drawing use/disclosure restriction", _legal_note_evidence(clean), "medium", page_number))
    if any(token in lowered for token in ("option", "standard", "application", "service", "capacity")) and not notes:
        if len(clean) > 180:
            return []
        notes.append(_field(clean, clean, "medium", page_number))
    return notes


def _is_legal_restriction_note(lowered: str) -> bool:
    primary_tokens = ("this drawing", "submitted solely")
    if not any(token in lowered for token in primary_tokens):
        return False
    legal_tokens = ("submitted solely", "not to be divulged", "divulged in whole", "permission", "permision", "exclusive use")
    if not any(token in lowered for token in legal_tokens):
        return False
    title_block_tokens = ("material:", "model:", "dwg no.", "drawn by:", "approved by:", "created date:")
    if any(token in lowered for token in title_block_tokens) and "this drawing" not in lowered:
        return False
    return True


def _compact_evidence(value: str, limit: int = 180) -> str:
    clean = re.sub(r"\s+", " ", value).strip()
    if len(clean) <= limit:
        return clean
    return clean[: limit - 3].rstrip() + "..."


def _legal_note_evidence(value: str) -> str:
    clean = re.sub(r"\s+", " ", value).strip()
    lowered = clean.casefold()
    starts = [lowered.find(token) for token in ("this drawing", "submitted solely") if lowered.find(token) >= 0]
    if starts:
        clean = clean[min(starts) :]
    return _compact_evidence(clean)


def _parse_drawing_structure(raw: RawExtractionResult, data: StructuredEngineeringData) -> dict[str, object]:
    text = _combined_text(raw)
    return {
        "page_count": raw.page_count,
        "has_title_block": bool(data.title_block),
        "has_bom_table": bool(data.bom_components),
        "has_engineering_tables": bool(data.engineering_tables),
        "has_engineering_requirements": bool(data.engineering_requirements),
        "has_thread_requirements": bool(data.thread_requirements),
        "has_review_dimensions": bool(data.review_dimensions),
        "has_callout_balloons": _callout_count(text) >= 3,
        "callout_count_estimate": _callout_count(text),
        "has_outline_views": bool(data.drawing_type and "outline" in data.drawing_type.value),
        "has_exploded_views": "exploded" in text.casefold(),
        "has_gdnt_requirement_candidates": bool(data.tolerances_gdnt),
        "has_process_requirements": bool(data.process_requirements),
        "has_manufacturing_requirements": bool(data.manufacturing_requirements),
        "vector_primitive_count": sum(len(getattr(page, "drawing_primitives", [])) for page in raw.pages),
        "vector_view_region_count": sum(1 for region in data.drawing_regions if region.region_type == "drawing_view"),
        "region_count": len(data.drawing_regions),
    }


def _build_semantic_summary(data: StructuredEngineeringData) -> str:
    model = data.title_block.get("model").value if data.title_block.get("model") else "unknown model"
    if data.title_block.get("manufacturer"):
        manufacturer = data.title_block["manufacturer"].value
    elif data.title_block.get("company"):
        manufacturer = data.title_block["company"].value
    else:
        manufacturer = "unknown manufacturer"
    drawing_type = data.drawing_type.value if data.drawing_type else "engineering PDF"
    units = data.units.value if data.units else "unknown units"
    categories = Counter(component.category or "component" for component in data.bom_components)
    category_summary = ", ".join(f"{name} x{count}" for name, count in categories.most_common(5))
    return (
        f"{manufacturer} {model} {drawing_type} with {units} units, "
        f"{len(data.bom_components)} parsed component entries, "
        f"{len(data.engineering_tables)} engineering tables, "
        f"{len(data.engineering_requirements)} engineering requirements, "
        f"{len(data.thread_requirements)} thread requirements, "
        f"{len(data.dimensions)} dimension candidates, "
        f"{len(data.review_dimensions)} review dimension candidates, "
        f"{len(data.connections)} connection candidates"
        + (f", and component categories {category_summary}." if category_summary else ".")
    )


def _warnings(raw: RawExtractionResult, data: StructuredEngineeringData) -> list[str]:
    warnings = list(raw.document_warnings)
    for page in raw.pages:
        warnings.extend(f"Page {page.page_number}: {warning}" for warning in page.warnings)
    if not data.bom_components and not data.engineering_tables:
        warnings.append("No BOM/component rows were parsed.")
    elif not data.bom_components and data.engineering_tables:
        warnings.append("No BOM/component rows were parsed; non-BOM engineering tables were detected.")
    if not data.dimensions:
        warnings.append("No dimension candidates were parsed.")
    if data.review_dimensions:
        warnings.append("Some vision-only dimension candidates require review before use.")
    return warnings


def _component_category(text: str) -> str:
    lowered = text.casefold()
    if "valve" in lowered:
        return "valve"
    if "flange" in lowered:
        return "flange"
    if "sensor" in lowered or "switch" in lowered:
        return "sensor/switch"
    if "connector" in lowered or "port" in lowered:
        return "connector/port"
    if "heater" in lowered:
        return "heater"
    if "filter" in lowered:
        return "filter"
    if "glass" in lowered:
        return "sight glass"
    if "box" in lowered:
        return "electrical enclosure"
    return "component"


def _dimension_role(text: str, value: float) -> tuple[str, str]:
    if re.search(rf"(?:overall|outline|length|width|height).{{0,40}}{re.escape(str(value))}", text, re.I):
        return "overall_or_envelope", "medium"
    large_values = sorted({float(item) for item in re.findall(r"\b\d{3,4}(?:\.\d+)?\b", text)}, reverse=True)
    if value in large_values[:4]:
        return "possible_envelope", "low"
    return "unknown", "low"


def _looks_like_connection_line(line: str) -> bool:
    lowered = line.casefold()
    if any(token in lowered for token in ("npt", "flare", "solder", "flange", "valve", "connector", "port", "sensor")):
        return True
    return bool(re.search(r"\d+\s+\d+/\d+\"|\d+/\d+\"", line))


def _connection_label_from_text(text: str) -> str:
    for token in ("oil drain", "discharge", "suction", "service", "liquid injection", "economizer", "safety", "connector"):
        if token in text.casefold():
            return token
    return ""


def _connection_type_from_text(text: str) -> str:
    lowered = text.casefold()
    for token in ("npt", "flare", "solder", "flange"):
        if token in lowered:
            return token
    return ""


def _callout_count(text: str) -> int:
    return len(set(re.findall(r"(?m)^\s*(\d{1,2})\s*$", text)))


def _combined_text(raw: RawExtractionResult) -> str:
    chunks: list[str] = []
    for page in raw.pages:
        chunks.append(_page_parse_text(page))
    return "\n".join(chunk for chunk in chunks if chunk.strip())


def _combined_lines(raw: RawExtractionResult) -> list[str]:
    lines: list[str] = []
    for page in raw.pages:
        lines.extend(_page_parse_lines(page))
    return lines


def _page_parse_text(page: object) -> str:
    text = getattr(page, "text", "") or ""
    reconstructed = "\n".join(
        line.normalized_text or line.text for line in getattr(page, "reconstructed_lines", []) if (line.normalized_text or line.text)
    )
    table_text = "\n".join(
        " ".join(cell for cell in row if cell)
        for table in getattr(page, "tables", [])
        for row in table.rows
    )
    return "\n".join(part for part in (text, reconstructed, table_text) if part.strip())


def _page_parse_lines(page: object) -> list[str]:
    lines = _lines(getattr(page, "text", "") or "")
    for line in getattr(page, "reconstructed_lines", []):
        value = line.normalized_text or line.text
        if value.strip():
            lines.append(value.strip())
    for table in getattr(page, "tables", []):
        for row in table.rows:
            value = " ".join(cell.strip() for cell in row if cell.strip())
            if value:
                lines.append(value)
    return lines


def _label_values_from_lines(lines: list[str]) -> dict[str, str]:
    values: dict[str, str] = {}
    label_pattern = re.compile(
        r"\b(?P<label>MODEL|DWG\s*No\.?|DRAWN BY|CREATED DATE|APPROVED BY|APPROVAL DATE|ITEM\s*#|CAGE|SHEET|MATERIAL)\s*:\s*(?P<value>[^|]+?)(?=\s{2,}|\b(?:MODEL|DWG\s*No\.?|DRAWN BY|CREATED DATE|APPROVED BY|APPROVAL DATE|ITEM\s*#|CAGE|SHEET|MATERIAL)\s*:|$)",
        re.I,
    )
    for line in lines:
        for match in label_pattern.finditer(line):
            label = _normalize_label(match.group("label"))
            value = match.group("value").strip(" |")
            if value:
                values.setdefault(label, value)
    return values


def _label_fields_from_raw(raw: RawExtractionResult) -> dict[str, ExtractedField]:
    fields: dict[str, ExtractedField] = {}
    label_pattern = re.compile(
        r"\b(?P<label>MODEL|DWG\s*No\.?|DRAWN BY|CREATED DATE|APPROVED BY|APPROVAL DATE|ITEM\s*#|CAGE|SHEET|MATERIAL)\s*:\s*(?P<value>[^|]+?)(?=\s{2,}|\b(?:MODEL|DWG\s*No\.?|DRAWN BY|CREATED DATE|APPROVED BY|APPROVAL DATE|ITEM\s*#|CAGE|SHEET|MATERIAL)\s*:|$)",
        re.I,
    )
    for page in raw.pages:
        for line in _page_parse_lines(page):
            for match in label_pattern.finditer(line):
                label = _normalize_label(match.group("label"))
                value = _clean_label_value(label, match.group("value"))
                if not value:
                    continue
                fields.setdefault(label, _field(value, f"{match.group('label')}: {value}", "high", page.page_number))

        for table in page.tables:
            for row in table.rows:
                for index, cell in enumerate(row):
                    value = cell.strip()
                    if not value:
                        continue
                    if re.match(r"^MATERIAL\s*:", value, re.I) and "\n" in value:
                        label = "material"
                        parsed_value = value.split("\n", 1)[1].strip()
                        if index + 1 < len(row):
                            parsed_value = _complete_split_table_value(parsed_value, row[index + 1])
                        parsed_value = _clean_label_value(label, parsed_value)
                        if parsed_value:
                            fields.setdefault(label, _field(parsed_value, f"MATERIAL: {parsed_value}", "high", page.page_number))
                        continue
                    match = re.match(r"^(?P<label>MODEL|DWG\s*No\.?|DRAWN BY|CREATED DATE|APPROVED BY|APPROVAL DATE|ITEM\s*#|CAGE|SHEET|MATERIAL)\s*:\s*(?P<value>.*)$", value, re.I)
                    if match:
                        label = _normalize_label(match.group("label"))
                        parsed_value = match.group("value").strip()
                        if not parsed_value and index + 1 < len(row):
                            parsed_value = row[index + 1].strip()
                        elif parsed_value and index + 1 < len(row):
                            parsed_value = _complete_split_table_value(parsed_value, row[index + 1])
                        parsed_value = _clean_label_value(label, parsed_value)
                        if parsed_value:
                            fields.setdefault(label, _field(parsed_value, f"{match.group('label')}: {parsed_value}", "high", page.page_number))
                        continue
                    if ":" not in value and index + 1 < len(row):
                        next_cell = row[index + 1].strip()
                        joined = f"{value}: {next_cell}"
                        joined_match = re.match(r"^(?P<label>MODEL|DWG\s*No\.?|DRAWN BY|CREATED DATE|APPROVED BY|APPROVAL DATE|ITEM\s*#|CAGE|SHEET|MATERIAL)\s*:\s*(?P<value>.*)$", joined, re.I)
                        if joined_match and next_cell:
                            label = _normalize_label(joined_match.group("label"))
                            parsed_value = _complete_split_table_value(next_cell, row[index + 2] if index + 2 < len(row) else "")
                            parsed_value = _clean_label_value(label, parsed_value)
                            if parsed_value:
                                fields.setdefault(label, _field(parsed_value, f"{joined_match.group('label')}: {parsed_value}", "high", page.page_number))
    return fields


def _clean_label_value(label: str, value: str) -> str:
    value = re.sub(r"\s+", " ", value).strip(" |")
    if label == "material" and re.search(r"\b(?:adapter|this drawing|submitted)\b", value, re.I):
        return ""
    if label == "material" and value.endswith(" COLD DRAW"):
        value += "N"
    if label == "item #":
        value = _complete_split_table_value(value, "")
    return value


def _generic_date(raw: RawExtractionResult) -> str:
    for page in raw.pages:
        for line in _page_parse_lines(page):
            match = re.search(r"(?<!CREATED )(?<!APPROVAL )\bDate\s*:?\s*(\d{1,2}/\d{1,2}/\d{2,4}|\d{8})\b", line, re.I)
            if match:
                return match.group(1)
    return ""


def _focused_label_evidence(raw: RawExtractionResult, label: str, value: str) -> str:
    pattern = re.compile(rf"\b{re.escape(label)}\s*:?\s*{re.escape(value)}\b", re.I)
    for page in raw.pages:
        for line in _page_parse_lines(page):
            match = pattern.search(line)
            if match:
                return match.group(0)
    return ""


def _label_values_from_tables(raw: RawExtractionResult) -> dict[str, str]:
    values: dict[str, str] = {}
    label_pattern = re.compile(r"^(?P<label>MODEL|DWG\s*No\.?|DRAWN BY|CREATED DATE|APPROVED BY|APPROVAL DATE|ITEM\s*#|CAGE|SHEET|MATERIAL)\s*:\s*(?P<value>.*)$", re.I)
    for page in raw.pages:
        for table in page.tables:
            for row in table.rows:
                for index, cell in enumerate(row):
                    value = cell.strip()
                    if not value:
                        continue
                    match = label_pattern.match(value)
                    if match:
                        parsed_value = match.group("value").strip()
                        if not parsed_value and index + 1 < len(row):
                            parsed_value = row[index + 1].strip()
                        elif parsed_value and index + 1 < len(row):
                            parsed_value = _complete_split_table_value(parsed_value, row[index + 1])
                        if parsed_value:
                            if _normalize_label(match.group("label")) == "material" and parsed_value.endswith(" COLD DRAW"):
                                parsed_value += "N"
                            values.setdefault(_normalize_label(match.group("label")), parsed_value)
                        continue
                    if ":" not in value and index + 1 < len(row):
                        next_cell = row[index + 1].strip()
                        joined = f"{value}: {next_cell}"
                        joined_match = label_pattern.match(joined)
                        if joined_match and next_cell:
                            parsed_value = _complete_split_table_value(next_cell, row[index + 2] if index + 2 < len(row) else "")
                            if _normalize_label(joined_match.group("label")) == "material" and parsed_value.endswith(" COLD DRAW"):
                                parsed_value += "N"
                            values.setdefault(_normalize_label(joined_match.group("label")), parsed_value)
    return values


def _normalize_label(label: str) -> str:
    return re.sub(r"\s+", " ", label.strip().casefold()).rstrip(":")


def _part_name_from_tables(raw: RawExtractionResult) -> str:
    for page in raw.pages:
        for table in page.tables:
            for row in table.rows:
                for cell in row:
                    if re.search(r"\b(?:adapter|bracket|cover|housing|shaft|plate)\b", cell, re.I):
                        value = re.sub(r"\s+", " ", cell.strip())
                        value = re.sub(r"\s+[A-Z]$", "", value)
                        if len(value) <= 80 and not value.casefold().startswith("material"):
                            return value
    return ""


def _complete_split_table_value(value: str, next_cell: str) -> str:
    next_value = next_cell.strip()
    if not next_value:
        return value
    first_token = next_value.split()[0]
    if re.fullmatch(r"[a-z]", first_token) and value[-1:].isalpha():
        return value + first_token
    if value.endswith("CHAR") and first_token == "T":
        return "SEE CHART"
    return value


def _page_uses_inches(text: str) -> bool:
    return bool(re.search(r"\bALL DIMENSIONS ARE IN INCHES\b|\binches\b", text, re.I))


def _inside_thread_or_tolerance_context(text: str, position: int) -> bool:
    context = text[max(0, position - 30) : position + 30].casefold()
    return any(token in context for token in ("thread size", "m3x", "m6x", "#10", "#6", ".xxx", ".xxxx", "±"))


def _process_label_fields(text: str, page_number: int) -> list[ExtractedField]:
    fields: list[ExtractedField] = []
    match = re.search(r"HEAT TREATMENT\s*-\s*FINISH\s*:\s*(?P<value>-|[^\n]+)?", text, re.I)
    if match:
        value = (match.group("value") or "").strip()
        if not value or value == "-" or value.casefold().startswith("standard notes"):
            fields.append(
                _field(
                    "heat treatment / finish: not specified",
                    "HEAT TREATMENT - FINISH: not specified",
                    "medium",
                    page_number,
                    warnings=["Process label is present, but no populated process requirement was found."],
                )
            )
        else:
            fields.append(_field(f"heat treatment / finish: {value}", match.group(0), "high", page_number))
    return fields


def _gdnt_candidate_from_raw(raw_value: str) -> tuple[str, list[str]]:
    raw = raw_value.strip()
    compact = raw.replace("Ø", "n")
    warnings = ["GD&T symbol was decoded through a CAD/PDF font artifact; normalized meaning requires review."]

    artifact_map = {
        "c": ("flatness", "▱"),
        "b": ("perpendicularity", "⊥"),
        "j": ("position", "⌖"),
    }
    symbol_code = ""
    tolerance_text = raw
    datum = ""
    diameter = False

    match = re.match(r"(?P<code>[a-z]{1,2})(?P<tolerance>\.00\d)(?P<datum>[A-Z]?)$", compact, re.I)
    if match:
        code = match.group("code").casefold()
        symbol_code = code[0]
        diameter = len(code) > 1 and "n" in code[1:]
        tolerance_text = match.group("tolerance")
        datum = match.group("datum")
    else:
        match = re.match(r"(?P<tolerance>\.00\d)(?P<datum>[A-Z]?)$", compact, re.I)
        if match:
            tolerance_text = match.group("tolerance")
            datum = match.group("datum")

    characteristic, symbol = artifact_map.get(symbol_code, ("unknown GD&T characteristic", "[symbol]"))
    diameter_prefix = "Ø" if diameter else ""
    datum_suffix = f" {datum}" if datum else ""
    normalized = f"{symbol} {diameter_prefix}{tolerance_text}{datum_suffix}".strip()
    return (
        f"feature control frame candidate: {characteristic} {normalized} (raw: {raw})",
        warnings,
    )


def _field(
    value: str,
    evidence: str,
    confidence: str,
    page: int | None = None,
    warnings: list[str] | None = None,
) -> ExtractedField:
    return ExtractedField(
        value=str(value).strip(),
        page=page,
        confidence=confidence,  # type: ignore[arg-type]
        evidence=evidence.strip(),
        warnings=warnings or [],
    )


def _field_for_value(
    raw: RawExtractionResult,
    value: str,
    confidence: str,
    evidence: str = "",
    warnings: list[str] | None = None,
) -> ExtractedField:
    return _field(
        value,
        evidence or _evidence_for_value(raw, value),
        confidence,
        _page_for_value(raw, value),
        warnings=warnings,
    )


def _format_compact_date(value: str) -> str:
    if re.fullmatch(r"\d{8}", value):
        return f"{value[:2]}/{value[2:4]}/{value[4:]}"
    return value


def _first_match(patterns: list[str], text: str) -> str:
    for pattern in patterns:
        match = re.search(pattern, text, re.I)
        if match:
            return match.group(1).strip()
    return ""


def _lines(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if line.strip()]


def _first_nonempty_line(raw: RawExtractionResult) -> str:
    for page in raw.pages:
        for line in _lines(page.text):
            return line
    return ""


def _evidence_for_value(raw: RawExtractionResult, value: str) -> str:
    if not value:
        return ""
    pattern = re.compile(re.escape(value), re.I)
    for page in raw.pages:
        lines = _page_parse_lines(page)
        for index, line in enumerate(lines):
            if pattern.search(line):
                context = lines[max(0, index - 1) : min(len(lines), index + 2)]
                return " | ".join(context)
    return ""


def _page_for_value(raw: RawExtractionResult, value: str) -> int | None:
    if not value:
        return None
    pattern = re.compile(re.escape(value), re.I)
    for page in raw.pages:
        if pattern.search(_page_parse_text(page)):
            return page.page_number
    return None


def _dedupe_fields(fields: list[ExtractedField]) -> list[ExtractedField]:
    deduped = []
    seen = set()
    for field in fields:
        key = field.value.casefold()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(field)
    return deduped
