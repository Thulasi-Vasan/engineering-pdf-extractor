from __future__ import annotations

from pathlib import Path

from .models import PageDetectionResult, PageExtraction, RawExtractionResult, TableExtraction, TextLine, WordBox
from .normalization import normalize_reconstructed_text, normalize_text
from .textract_ocr import analyze_page_with_textract


def extract_raw_content(pdf_path: Path, detection: PageDetectionResult) -> RawExtractionResult:
    try:
        import pdfplumber
    except ImportError as exc:
        raise RuntimeError("pdfplumber is required. Install dependencies with uv sync.") from exc

    pages: list[PageExtraction] = []
    document_warnings = list(detection.document_warnings)

    with pdfplumber.open(str(pdf_path)) as pdf:
        for page_detection, page in zip(detection.pages, pdf.pages, strict=False):
            raw_text = page_detection.native_text or page.extract_text() or ""
            normalized_text = normalize_text(raw_text)
            words = _extract_words(page)
            tables = _extract_tables(page, page_detection.page_number)
            warnings = list(page_detection.warnings)
            textract_lines = []

            if page_detection.page_type == "image_page":
                ocr = analyze_page_with_textract(pdf_path, page_detection.page_number)
                if ocr.text:
                    raw_text = ocr.text
                    normalized_text = normalize_text(ocr.text)
                words = ocr.words or words
                tables = ocr.tables or tables
                textract_lines = ocr.lines
                warnings.extend(ocr.warnings)
            elif page_detection.page_type == "hybrid_page" and _native_content_is_incomplete(normalized_text, tables):
                ocr = analyze_page_with_textract(pdf_path, page_detection.page_number)
                if ocr.text:
                    normalized_text = _merge_text(normalized_text, normalize_text(ocr.text))
                    raw_text = _merge_text(raw_text, ocr.text)
                    words.extend(ocr.words)
                    tables.extend(ocr.tables)
                    textract_lines = ocr.lines
                warnings.extend(ocr.warnings)

            reconstructed_lines = _reconstruct_lines(words, page_detection.page_number)
            pages.append(
                PageExtraction(
                    page_number=page_detection.page_number,
                    page_type=page_detection.page_type,
                    extraction_method=page_detection.extraction_method,
                    text=normalized_text,
                    raw_text=raw_text,
                    page_width=float(page.width),
                    page_height=float(page.height),
                    words=words,
                    reconstructed_lines=reconstructed_lines,
                    tables=tables,
                    textract_lines=textract_lines,
                    warnings=warnings,
                )
            )

    return RawExtractionResult(
        pdf_type=detection.pdf_type,
        page_count=len(pages),
        pages=pages,
        document_warnings=document_warnings,
    )


def _extract_words(page: object) -> list[WordBox]:
    words = []
    for item in page.extract_words() or []:
        text = str(item.get("text", "")).strip()
        if not text:
            continue
        words.append(
            WordBox(
                text=text,
                x0=float(item.get("x0", 0.0) or 0.0),
                top=float(item.get("top", 0.0) or 0.0),
                x1=float(item.get("x1", 0.0) or 0.0),
                bottom=float(item.get("bottom", 0.0) or 0.0),
                source="text",
                confidence=1.0,
            )
        )
    return words


def _extract_tables(page: object, page_number: int) -> list[TableExtraction]:
    tables: list[TableExtraction] = []
    try:
        raw_tables = page.extract_tables() or []
    except Exception as exc:
        return [TableExtraction(source=f"pdfplumber_error:{exc}", rows=[], page=page_number)]

    for raw_table in raw_tables:
        rows = []
        for row in raw_table:
            if not row:
                continue
            cleaned = [normalize_text(str(cell or "")) for cell in row]
            if any(cell for cell in cleaned):
                rows.append(cleaned)
        if rows:
            tables.append(TableExtraction(source="pdfplumber", rows=rows, page=page_number, confidence=1.0))
    return tables


def _reconstruct_lines(words: list[WordBox], page_number: int) -> list[TextLine]:
    if not words:
        return []

    heights = [max(0.1, word.bottom - word.top) for word in words]
    median_height = sorted(heights)[len(heights) // 2]
    line_tolerance = max(2.0, median_height * 0.55)

    groups: list[list[WordBox]] = []
    for word in sorted(words, key=lambda item: (item.top, item.x0)):
        target_group = None
        for group in groups:
            group_top = sum(item.top for item in group) / len(group)
            if abs(word.top - group_top) <= line_tolerance:
                target_group = group
                break
        if target_group is None:
            groups.append([word])
        else:
            target_group.append(word)

    lines: list[TextLine] = []
    for group in groups:
        ordered = sorted(group, key=lambda item: item.x0)
        text = _join_line_words(ordered)
        normalized_text, warnings = normalize_reconstructed_text(text)
        if not normalized_text:
            continue
        lines.append(
            TextLine(
                text=text,
                normalized_text=normalized_text,
                x0=min(item.x0 for item in ordered),
                top=min(item.top for item in ordered),
                x1=max(item.x1 for item in ordered),
                bottom=max(item.bottom for item in ordered),
                page=page_number,
                source="text",
                confidence=min(item.confidence for item in ordered),
                warnings=warnings,
            )
        )
    return sorted(lines, key=lambda line: (line.top, line.x0))


def _join_line_words(words: list[WordBox]) -> str:
    if not words:
        return ""
    if _looks_like_tracked_text(words):
        return _join_tracked_words(words)

    pieces = [words[0].text]
    for previous, current in zip(words, words[1:], strict=False):
        gap = current.x0 - previous.x1
        if gap <= 0.8 and _join_without_space(previous.text, current.text):
            pieces[-1] += current.text
        else:
            pieces.append(current.text)
    return " ".join(pieces)


def _looks_like_tracked_text(words: list[WordBox]) -> bool:
    letterish = [word for word in words if len(word.text) <= 2 and word.text.replace(".", "").isalpha()]
    if len(letterish) < 8 or len(letterish) / len(words) < 0.75:
        return False
    return max(word.bottom for word in words) - min(word.top for word in words) <= 12


def _join_tracked_words(words: list[WordBox]) -> str:
    clusters: list[str] = []
    current = words[0].text
    gaps = [max(0.0, current_word.x0 - previous_word.x1) for previous_word, current_word in zip(words, words[1:], strict=False)]
    median_gap = sorted(gaps)[len(gaps) // 2] if gaps else 0.0
    break_gap = max(1.8, median_gap * 1.7)
    for previous, word in zip(words, words[1:], strict=False):
        gap = word.x0 - previous.x1
        if gap > break_gap or previous.text.endswith(","):
            clusters.append(current)
            current = word.text
        else:
            current += word.text
    clusters.append(current)
    return " ".join(clusters)


def _join_without_space(previous: str, current: str) -> bool:
    if previous.endswith(("/", "-", "±", "Ø")):
        return True
    if current in {".", ",", ":", ";", ")", "\"", "°"}:
        return True
    if current.startswith((".", ",", ":", ";", ")", "\"", "°")):
        return True
    return False


def _native_content_is_incomplete(text: str, tables: list[TableExtraction]) -> bool:
    if len(text) < 100:
        return True
    if not tables and ("No." in text or "ITEM" in text.upper()):
        return True
    return False


def _merge_text(first: str, second: str) -> str:
    if not first.strip():
        return second.strip()
    if not second.strip():
        return first.strip()
    if second.strip() in first:
        return first.strip()
    return first.strip() + "\n" + second.strip()
