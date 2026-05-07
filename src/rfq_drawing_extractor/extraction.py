from __future__ import annotations

from pathlib import Path

from .models import PageDetectionResult, PageExtraction, RawExtractionResult, TableExtraction, WordBox
from .normalization import normalize_text
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

