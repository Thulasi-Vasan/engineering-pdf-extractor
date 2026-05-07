from __future__ import annotations

import re
from collections import Counter

from .models import (
    BomComponent,
    ConnectionCandidate,
    DimensionCandidate,
    EngineeringTable,
    ExtractedField,
    RawExtractionResult,
    StructuredEngineeringData,
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
INCH_DIMENSION_RE = re.compile(r"(?<![#A-Z])(?P<value>\d+\.\d+)(?!\s*[-A-Z0-9])")
CHAMFER_RE = re.compile(r"\b(?P<count>\d+\s*x\s*)?(?P<size>\d+(?:\.\d+)?)\s*X\s*(?P<angle>\d+(?:\.\d+)?)\s*°", re.I)
DEFAULT_TOLERANCE_RE = re.compile(r"(?P<precision>\.X{1,4})\s*(?P<tol>±\s*\d+(?:\.\d+)?)\s*\"?", re.I)
Fcf_CANDIDATE_RE = re.compile(r"\b(?P<raw>(?:[a-z]{1,2}\.00\d[A-Z]?|[a-z]{1,2}Ø\.00\d[A-Z]?|\.002[A-Z]?))\b", re.I)


def parse_engineering_data(raw: RawExtractionResult) -> StructuredEngineeringData:
    data = StructuredEngineeringData()
    all_text = _combined_text(raw)
    all_lines = _combined_lines(raw)

    data.title_block = _parse_title_block(raw, all_lines)
    data.units = _parse_units(raw, all_text)
    data.drawing_type = _parse_drawing_type(raw, all_text)
    data.bom_components = _parse_bom_components(raw)
    data.engineering_tables = _parse_engineering_tables(raw)
    data.dimensions = _parse_dimensions(raw)
    data.connections = _parse_connections(raw, data.bom_components)
    data.standards = _parse_standards(raw)
    data.tolerances_gdnt = _parse_tolerances_gdnt(raw)
    data.process_requirements = _parse_process_signals(raw)
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
    label_values = _label_values_from_lines(lines)
    label_values.update(_label_values_from_tables(raw))

    model = _first_match(
        [
            r"Hanbell Model\s*\n?\s*([A-Z0-9/&.-]+)",
            r"\bModel\s*:?\s*\n?\s*([A-Z0-9/&.-]+)",
        ],
        text,
    ) or label_values.get("model", "")
    if model:
        fields["model"] = _field(model, _evidence_for_value(raw, model), "high")

    drawing_name = _first_match(
        [
            r"\bName\s*\n?\s*(Compressor outline)",
            r"(Dimensional Outline Drawing[^\n]*)",
            r"(Compressor outline)",
        ],
        text,
    )
    if drawing_name:
        fields["drawing_name"] = _field(drawing_name, _evidence_for_value(raw, drawing_name), "high")

    date = _first_match([r"\bDate\s*:?\s*\n?\s*(\d{1,2}/\d{1,2}/\d{2,4})", r"\bDate\s*:?\s*\n?\s*(\d{8})"], text)
    if date:
        raw_date = date
        date = _format_compact_date(date)
        fields["date"] = _field(date, _evidence_for_value(raw, raw_date) or _evidence_for_value(raw, date), "high")

    drawn_by = label_values.get("drawn by", "") or _first_match([r"\bDrawn By\s*:?\s*\n?\s*([A-Z][A-Z0-9 .-]{1,40})"], text)
    if drawn_by:
        drawn_by = re.split(r"\b(?:E-mail|Email|Tel|Fax)\b", drawn_by, maxsplit=1, flags=re.I)[0].strip()
        fields["drawn_by"] = _field(drawn_by, _evidence_for_value(raw, drawn_by), "high")

    version = _first_match([r"\b(?:Ver\.?|Rev\.?|Revision\b)\s*:?\s+([A-Z0-9.-]+)\b"], text)
    if version and version.casefold() in {"isions", "revisions", "revision", "sheet"}:
        version = ""
    if version:
        fields["revision_version"] = _field(version, _evidence_for_value(raw, version), "high")

    if re.search(r"\bHANBELL\b", text, re.I):
        fields["manufacturer"] = _field("HANBELL", _evidence_for_value(raw, "HANBELL"), "high")

    company = _first_match([r"(Micro Control Systems,\s*Inc\.)", r"(ADVANCED SENSOR TECHNOLOGY,\s*INC\.)"], text)
    if company:
        fields["company"] = _field(company, _evidence_for_value(raw, company), "high")

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
        value = next((label_values[label] for label in labels if label_values.get(label)), "")
        if value:
            fields[field_name] = _field(value, _evidence_for_value(raw, value), "high")

    part_name = _part_name_from_tables(raw)
    if part_name and "part_name" not in fields:
        fields["part_name"] = _field(part_name, _evidence_for_value(raw, part_name), "medium")

    if fields.get("material") and fields["material"].value.endswith(" COLD DRAW"):
        fields["material"].value += "N"

    return fields


def _parse_units(raw: RawExtractionResult, text: str) -> ExtractedField | None:
    if re.search(r"\bALL DIMENSIONS ARE IN INCHES\b", text, re.I):
        return _field("inch", _evidence_for_value(raw, "ALL DIMENSIONS ARE IN INCHES"), "high")
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
    evidence = _evidence_for_value(raw, value.split()[0]) or _first_nonempty_line(raw)
    confidence = "high" if value != "unknown engineering PDF" else "low"
    return _field(value, evidence, confidence)


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
        for table in page.tables:
            if not table.rows:
                continue
            headers = [cell.strip() for cell in table.rows[0]]
            normalized_headers = [_normalize_header(header) for header in headers]
            if _is_thread_or_item_chart(normalized_headers):
                rows = []
                for raw_row in table.rows[1:]:
                    row = {}
                    for header, value in zip(normalized_headers, raw_row, strict=False):
                        if header:
                            row[header] = value.strip()
                    if any(row.values()):
                        rows.append(row)
                if rows:
                    tables.append(
                        EngineeringTable(
                            table_type="thread_or_item_chart",
                            headers=normalized_headers,
                            rows=rows,
                            page=page.page_number,
                            confidence="high",
                            evidence=" | ".join(headers),
                        )
                    )
    return tables


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
    }
    return aliases.get(normalized, normalized.replace(" ", "_"))


def _is_thread_or_item_chart(headers: list[str]) -> bool:
    header_set = set(headers)
    return "item_number" in header_set and ("thread_size" in header_set or "chart_number" in header_set)


def _parse_dimensions(raw: RawExtractionResult) -> list[DimensionCandidate]:
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
                    page=page.page_number,
                    confidence="medium",
                    evidence=match.group(0),
                )
            )

        for match in CHAMFER_RE.finditer(page_text):
            size = float(match.group("size"))
            key = (size, "inch" if _page_uses_inches(page_text) else "unknown", None)
            if key not in seen:
                seen.add(key)
                dimensions.append(
                    DimensionCandidate(
                        value=size,
                        unit="inch" if _page_uses_inches(page_text) else "unknown",
                        dimension_type="chamfer",
                        role="chamfer",
                        role_confidence="high",
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
                    role="hole_or_diameter",
                    role_confidence="medium",
                    page=page.page_number,
                    confidence="medium",
                    evidence=match.group(0),
                )
            )

        for match in ANGLE_RE.finditer(page_text):
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
                    page=page.page_number,
                    confidence="medium",
                    evidence=match.group(0),
                )
            )

        for match in INCH_DIMENSION_RE.finditer(page_text):
            value = float(match.group("value"))
            if value > 10 or _inside_thread_or_tolerance_context(page_text, match.start()):
                continue
            key = (value, "inch", None)
            if key in seen:
                continue
            seen.add(key)
            dimensions.append(
                DimensionCandidate(
                    value=value,
                    unit="inch",
                    page=page.page_number,
                    confidence="medium",
                    evidence=match.group(0),
                )
            )

    return dimensions


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
        for regex in (STANDARD_RE, TOLERANCE_RE, SURFACE_RE):
            for match in regex.finditer(page_text):
                fields.append(_field(match.group(0), match.group(0), "high", page.page_number))

        for match in DEFAULT_TOLERANCE_RE.finditer(page_text):
            fields.append(_field(f"{match.group('precision')} {match.group('tol')}\"", match.group(0), "high", page.page_number))

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


def _parse_notes(raw: RawExtractionResult) -> list[ExtractedField]:
    notes = []
    seen: set[str] = set()
    for page in raw.pages:
        for line in _page_parse_lines(page):
            lowered = line.casefold()
            if not any(token in lowered for token in ("option", "standard", "application", "service", "capacity")):
                continue
            if line in seen:
                continue
            seen.add(line)
            notes.append(_field(line, line, "medium", page.page_number))
    return notes[:40]


def _parse_drawing_structure(raw: RawExtractionResult, data: StructuredEngineeringData) -> dict[str, object]:
    text = _combined_text(raw)
    return {
        "page_count": raw.page_count,
        "has_title_block": bool(data.title_block),
        "has_bom_table": bool(data.bom_components),
        "has_callout_balloons": _callout_count(text) >= 3,
        "callout_count_estimate": _callout_count(text),
        "has_outline_views": bool(data.drawing_type and "outline" in data.drawing_type.value),
        "has_exploded_views": "exploded" in text.casefold(),
        "has_gdnt_requirement_candidates": bool(data.tolerances_gdnt),
        "has_process_requirements": bool(data.process_requirements),
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
        f"{len(data.dimensions)} dimension candidates, "
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
                    match.group(0),
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
